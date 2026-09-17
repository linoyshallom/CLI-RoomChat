import asyncio
import json
import logging
import os
import re
import typing
import urllib.parse
from logging import getLogger

import httpx
import websockets
from pydantic import ValidationError

from config import ClientConfig, ServerConfig
from definitions import MessageInfo, MessageTypes, RoomTypes, UsernameData

logger = getLogger(__name__)

_CONTENT_DISPOSITION_FILENAME = re.compile(r'filename="?([^";]+)"?')


def _filename_from_content_disposition(header: typing.Optional[str]) -> typing.Optional[str]:
    if not header:
        return None
    match = _CONTENT_DISPOSITION_FILENAME.search(header)
    return match.group(1) if match else None


class ChatClient:
    """Owns the chat websocket and an HTTP client for file transfer - both talk to the same
    FastAPI app on one port."""

    def __init__(self, *, host: str, port: int, username: str):
        self.username = username
        self._ws_url = f"ws://{host}:{port}/ws/chat?username={urllib.parse.quote(username)}"
        self._http_client = httpx.AsyncClient(base_url=f"http://{host}:{port}")
        self.websocket: typing.Optional[websockets.WebSocketClientProtocol] = None

    async def connect(self) -> None:
        try:
            self.websocket = await websockets.connect(self._ws_url)
            logger.info("Client successfully connected to server")
        except Exception as e:
            logger.exception("Failed to connect to server ...")
            raise Exception(f"Unable to connect to server - {self._ws_url}") from e

    async def close(self) -> None:
        if self.websocket is not None:
            await self.websocket.close()
        await self._http_client.aclose()

    async def join_room(self, *, room_type: str, group_name: typing.Optional[str] = None) -> None:
        payload = {"action": "join", "room_type": room_type}
        if group_name:
            payload["group_name"] = group_name
        await self.websocket.send(json.dumps(payload))

    async def send_message(self, text: str) -> None:
        await self.websocket.send(json.dumps({"action": "message", "text": text}))

    async def switch_room(self) -> None:
        await self.websocket.send(json.dumps({"action": "switch"}))

    async def receive_messages(self) -> typing.AsyncGenerator[dict, None]:
        async for raw in self.websocket:
            yield json.loads(raw)

    # Triggers upload_file in server.app
    async def upload_file(self, file_path: str) -> str:
        filename = os.path.basename(file_path)
        with open(file_path, 'rb') as file:
            response = await self._http_client.post("/files", files={"file": (filename, file)})
        response.raise_for_status()
        return response.json()["file_id"]

    # Triggers download_file in server.app
    async def download_file(self, *, file_id: str, dst_dir: str) -> str:
        async with self._http_client.stream("GET", f"/files/{file_id}") as response:
            response.raise_for_status()

            # Sanitize the server-supplied filename before joining it to the destination
            # directory - a stored file_name containing '..' could otherwise escape dst_dir.
            filename = os.path.basename(_filename_from_content_disposition(response.headers.get("content-disposition")) or file_id)
            dst_path = os.path.join(dst_dir, filename)

            with open(dst_path, 'wb') as file:
                async for chunk in response.aiter_bytes():
                    file.write(chunk)

        return dst_path


class ClientUI:

    @classmethod
    def render(cls, *, msg_type, text):
        msg = MessageInfo(type=msg_type, text_message=text)
        print(msg.formatted_msg())

    @classmethod
    def clear_screen(cls):
        os.system('cls' if os.name == 'nt' else 'clear')


async def _receive_loop(client: ChatClient) -> None:
    try:
        async for msg in client.receive_messages():
            print(f"\n {msg.get('text', '')}")
    except websockets.exceptions.ConnectionClosed:
        return


async def _prompt_room(client: ChatClient) -> None:
    while True:
        print(f"\n Available rooms to chat:")
        for room in RoomTypes:
            print(f"- {room.value}")

        chosen_room = (await asyncio.to_thread(input, "Enter room type: ")).strip().upper()

        try:
            room_type = RoomTypes[chosen_room]
        except KeyError:
            ClientUI.clear_screen()
            ClientUI.render(msg_type=MessageTypes.SYSTEM, text=f"Got an unexpected room type {chosen_room}, try again")
            continue

        group_name = None
        if room_type == RoomTypes.PRIVATE:
            group_name = (await asyncio.to_thread(input, "Enter private group name you want to chat: ")).strip()

        await client.join_room(room_type=chosen_room, group_name=group_name)
        return


async def _input_loop(client: ChatClient) -> None:
    while True:
        await _prompt_room(client)

        while True:
            msg = await asyncio.to_thread(
                input, "\n Enter a message (text, /switch, /file <path>, /download <file_id> <path> :  "
            )

            if not msg:
                ClientUI.render(msg_type=MessageTypes.SYSTEM, text="An empy message could not be sent ...")
                continue

            if msg.lower() == "/switch":
                await client.switch_room()
                ClientUI.clear_screen()
                break

            elif msg.startswith("/file"):
                if len(msg.split(' ', 1)) != 2:
                    ClientUI.render(msg_type=MessageTypes.SYSTEM, text="No file path provided. Usage: /file <path>")
                    continue

                # Windows silently tolerates a trailing space in os.path.isfile()/open(),
                # so an unstripped path here would still upload fine while baking the
                # stray space into the filename permanently.
                file_path_from_msg = msg.split(' ', 1)[1].strip()

                if not os.path.isfile(file_path_from_msg):
                    ClientUI.render(msg_type=MessageTypes.SYSTEM, text=f"'{file_path_from_msg}' isn't a proper file, try again")
                    continue

                ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Uploading file ...")
                try:
                    file_id = await client.upload_file(file_path_from_msg)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 413:
                        ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Upload failed, file size exceeded")
                    else:
                        ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Upload failed ...")
                except Exception:
                    logger.exception("Error in uploading the file")
                    ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Upload failed ...")
                else:
                    ClientUI.render(msg_type=MessageTypes.SYSTEM, text="File is uploaded successfully!")
                    await client.send_message(file_id)

            elif msg.startswith("/download"):
                if len(msg.split()) != 3:
                    ClientUI.render(
                        msg_type=MessageTypes.SYSTEM,
                        text="You should provide file id and destination path , Usage: /download <file_id> <dst_path>"
                    )
                    continue

                file_id, dst_dir = msg.split()[1].strip(), msg.split()[2].strip()

                ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Downloading file ...")
                try:
                    await client.download_file(file_id=file_id, dst_dir=dst_dir)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Download failed, file id was not found")
                    else:
                        ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Download failed! (try check your destination path")
                except Exception:
                    logger.exception("Error in downloading the file")
                    ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Download failed! (try check your destination path")
                else:
                    ClientUI.render(msg_type=MessageTypes.SYSTEM, text="File is downloaded successfully!")

            elif msg.startswith("/quit"):
                ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Exiting chat...")
                await client.websocket.close()
                return

            else:
                await client.send_message(msg)


async def main():
    while True:
        username = await asyncio.to_thread(input, "Enter your username: ")
        try:
            UsernameData(username=username)
        except ValidationError:
            ClientUI.render(
                msg_type=MessageTypes.SYSTEM,
                text="Invalid username - only letters, numbers, '.' and '_' are allowed, try again... \n"
            )
        else:
            break

    client = ChatClient(host=ClientConfig.host_ip, port=ServerConfig.listening_port, username=username)
    await client.connect()

    try:
        await asyncio.gather(_receive_loop(client), _input_loop(client))
    finally:
        await client.close()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    asyncio.run(main())
