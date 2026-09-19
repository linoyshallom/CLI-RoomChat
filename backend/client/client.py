import asyncio
import json
import os
import re
import typing
import urllib.parse
import zlib
from logging import getLogger

import httpx
import websockets
from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.patch_stdout import patch_stdout
from pydantic import ValidationError

from config import ClientConfig, ServerConfig
from definitions import MessageTypes, RoomTypes, UsernameData
from utils.logging_config import configure_logging

logger = getLogger(__name__)

_CONTENT_DISPOSITION_FILENAME = re.compile(r'filename="?([^";]+)"?')

# Every chat/system line the server sends is pre-formatted server-side (definitions.structs.
# MessageInfo.formatted_msg() - "single source of formatting"). These mirror that exact shape
# so the client can pull sender/timestamp back out for coloring without the server needing to
# know anything about how the client chooses to render.
_CHAT_LINE = re.compile(r"^\[(?P<timestamp>[^\]]+)] \[(?P<sender>[^\]]+)]: (?P<text>.*)$", re.DOTALL)
_SYSTEM_LINE = re.compile(r"^\[SYSTEM]: (?P<text>.*)$", re.DOTALL)

# Named ANSI colors prompt_toolkit understands out of the box - no custom Style needed.
# "You" and SYSTEM get their own fixed styles so they're never confused with another sender's.
_SENDER_PALETTE = (
    "ansicyan", "ansigreen", "ansiyellow", "ansiblue", "ansimagenta",
    "ansired", "ansibrightgreen", "ansibrightblue", "ansibrightmagenta", "ansibrightred",
)
_SELF_STYLE = "bold ansibrightcyan"
_SYSTEM_STYLE = "italic ansiyellow"
_TIMESTAMP_STYLE = "ansibrightblack"


def _color_for_sender(sender: str) -> str:
    # Deterministic (not random/cached) so the same username always renders in the same color,
    # both within a session and across separate runs of the client.
    return _SENDER_PALETTE[zlib.crc32(sender.encode()) % len(_SENDER_PALETTE)]


def _render_chat_line(line: str, *, own_username: str) -> FormattedText:
    match = _CHAT_LINE.match(line)
    if not match:
        # Display-only concern - fall back to the raw line rather than risk hiding a message
        # whose shape doesn't match what the server is currently sending.
        return FormattedText([("", line)])

    sender = match["sender"]
    is_self = sender == own_username
    sender_style = _SELF_STYLE if is_self else f"bold {_color_for_sender(sender)}"
    display_name = "You" if is_self else sender

    return FormattedText([
        (_TIMESTAMP_STYLE, f"[{match['timestamp']}] "),
        (sender_style, display_name),
        ("", f": {match['text']}"),
    ])


def _render_system_line(line: str) -> FormattedText:
    match = _SYSTEM_LINE.match(line)
    text = match["text"] if match else line
    return FormattedText([(_SYSTEM_STYLE, f"[SYSTEM]: {text}")])


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
    def render(cls, *, msg_type: MessageTypes, text: str) -> None:
        if msg_type == MessageTypes.SYSTEM:
            print_formatted_text(FormattedText([(_SYSTEM_STYLE, f"[SYSTEM]: {text}")]))
        else:
            print_formatted_text(FormattedText([("", text)]))

    @classmethod
    def clear_screen(cls):
        os.system('cls' if os.name == 'nt' else 'clear')


async def _receive_loop(client: ChatClient) -> None:
    try:
        async for msg in client.receive_messages():
            text = msg.get("text", "")
            if msg.get("type") == MessageTypes.SYSTEM.value:
                print_formatted_text(_render_system_line(text))
            else:
                print_formatted_text(_render_chat_line(text, own_username=client.username))
    except websockets.exceptions.ConnectionClosed:
        return


async def _prompt_room(client: ChatClient, session: PromptSession) -> None:
    while True:
        print_formatted_text(FormattedText([("bold", "\nAvailable rooms to chat:")]))
        for room in RoomTypes:
            print_formatted_text(FormattedText([("", f"- {room.value}")]))

        chosen_room = (await session.prompt_async("Enter room type: ")).strip().upper()

        try:
            room_type = RoomTypes[chosen_room]
        except KeyError:
            ClientUI.clear_screen()
            ClientUI.render(msg_type=MessageTypes.SYSTEM, text=f"Got an unexpected room type {chosen_room}, try again")
            continue

        group_name = None
        if room_type == RoomTypes.PRIVATE:
            group_name = (await session.prompt_async("Enter private group name you want to chat: ")).strip()

        await client.join_room(room_type=chosen_room, group_name=group_name)
        return


async def _input_loop(client: ChatClient, session: PromptSession) -> None:
    while True:
        await _prompt_room(client, session)

        while True:
            msg = await session.prompt_async(
                "\nEnter a message (text, /switch, /file <path>, /download <file_id> <path>: "
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
    session = PromptSession()

    # patch_stdout() makes prompt_toolkit redraw the active prompt whenever something else
    # writes to stdout while it's up - without it, a message arriving mid-keystroke from
    # _receive_loop would print straight into the input line instead of above it.
    with patch_stdout():
        while True:
            username = (await session.prompt_async("Enter your username: ")).strip()
            try:
                UsernameData(username=username)
            except ValidationError:
                ClientUI.render(
                    msg_type=MessageTypes.SYSTEM,
                    text="Invalid username - only letters, numbers, '.' and '_' are allowed, try again..."
                )
            else:
                break

        client = ChatClient(host=ClientConfig.host_ip, port=ServerConfig.listening_port, username=username)
        await client.connect()

        try:
            await asyncio.gather(_receive_loop(client), _input_loop(client, session))
        finally:
            await client.close()


if __name__ == '__main__':
    configure_logging(
        source="client",
        log_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"),
        console=False,
    )
    asyncio.run(main())
