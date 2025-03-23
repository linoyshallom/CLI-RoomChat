import json
import logging
import os.path
import socket
import time
import typing
from concurrent.futures import ThreadPoolExecutor
from logging import getLogger

from config import ClientConfig, MessageServerConfig, FileServerConfig, END_OF_MSG_INDICATOR
from definitions import InvalidInputError, MessageInfo, RoomTypes, MessageTypes, FileTransferStatus
from utils import chunkify

logger = getLogger(__name__)

class MessageClient:
    def __init__(self, host: str, port: int):
        self._message_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self._message_socket.connect((host, port))
            logger.info(f"Client Successfully connected to Chat Server")

        except Exception as e:
            logger.exception("Failed to connect message server ... ")
            raise Exception(f"Unable to connect to messages server - {host}, with port {port}") from e

    @property
    def message_socket(self) -> socket.socket:
        return self._message_socket

    def enter_room(self, *, room_name: str) -> None :
        setup_room_data = {}
        while True:
            room_type = RoomTypes[room_name.upper()]

            if room_type == RoomTypes.GLOBAL:
                setup_room_data = {
                    "room_type": room_name
                }

            elif room_type == RoomTypes.PRIVATE:
                group_name = input("Enter private group name you want to chat: ").strip()
                setup_room_data = {
                    "room_type": room_name,
                    "group_name": group_name
                }

            self._message_socket.send(json.dumps(setup_room_data).encode('utf-8'))
            break

    def receive_messages(self) -> typing.Generator[str, None, None]:
        fragmented_msg = ""
        while True:
            try:
                # I consumed buffer of 1024 bytes which can contains more than one message, so I split by end msg indicator
                buffer_msg = self._message_socket.recv(1024).decode('utf-8')
                aggrigated_buffer = fragmented_msg + buffer_msg

                messages_in_buffer = aggrigated_buffer.split(END_OF_MSG_INDICATOR)

                if not aggrigated_buffer.endswith(END_OF_MSG_INDICATOR):
                    fragmented_msg = messages_in_buffer[-1]
                else:
                    fragmented_msg = ""

                yield from messages_in_buffer[:-1]

            except Exception as e:
                self._message_socket.close()
                logger.exception("Failed to receive messages")
                raise Exception("Cannot receiving messages...") from e

class FileClient:
    def __init__(self, host: str, port: int):
        self._file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self._file_socket.connect((host, port))
            logger.info(f"Client Successfully connected to File Server")

        except Exception as e:
            logger.exception("Failed to connect file server ... ")
            raise Exception(f"Unable to connect to file server - {host}, {port}") from e

    @property
    def file_socket(self) -> socket.socket:
        return self._file_socket

    # Triggers upload_file methode in FileServerTransfer
    def upload_file(self, file_path: str) -> None :
        if os.path.isfile(file_path):

            self._file_socket.send("UPLOAD".encode('utf-8'))

            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            upload_data = {
                "filename": filename,
                "file_size": file_size
            }
            self._file_socket.sendall(json.dumps(upload_data).encode('utf-8'))

            with open(file_path, 'rb') as file:
                for chunk in chunkify(reader_file=file, chunk_size=1024):
                    self._file_socket.sendall(chunk)
        else:
            raise InvalidInputError(f"Client entered inappropriate file")

    # Triggers download_file methode in FileServerTransfer
    def download_file(self, message: str) -> None:
        self.file_socket.send("DOWNLOAD".encode('utf-8'))
        file_id = message.split()[1]
        user_dir_dst_path = message.split()[2]

        download_data = {
            "file_id": file_id,
            "dst_path": user_dir_dst_path
        }
        self.file_socket.sendall(json.dumps(download_data).encode('utf-8'))

class ClientUI:

    @classmethod
    def start_receiving(cls, message_client: MessageClient):  # Fetch messages from db
        for msg in message_client.receive_messages():
            print(f"\n {msg}")

    @classmethod
    def render(cls, *, msg_type, text):
        msg = MessageInfo(type=msg_type, text_message=text)
        print(msg.formatted_msg())

    @classmethod
    def clear_screen(cls):
        os.system('cls' if os.name == 'nt' else 'clear')


def main():
    message_client = MessageClient(host=ClientConfig.host_ip, port=MessageServerConfig.listening_port)
    file_client = FileClient(host=ClientConfig.host_ip, port=FileServerConfig.listening_port)

    time.sleep(0.01)                # Ensure displaying logger info messages before this section (I know that's weird, only for displaying)
    username = input("Enter your username:")
    message_client.message_socket.send(username.encode('utf-8'))

    with ThreadPoolExecutor(max_workers=5) as background_threads:
        while True:
            try:
                print(f"\n Available rooms to chat:")
                for room in RoomTypes:
                    print(f"- {room.value}")

                chosen_room = input("Enter room type: ").strip().upper()
                message_client.enter_room(room_name=chosen_room)

            except KeyError:
                ClientUI.clear_screen()
                ClientUI.render(msg_type=MessageTypes.SYSTEM, text=f"Got unexpected room type {chosen_room}, try again")

            else:
                background_threads.submit(ClientUI.start_receiving,message_client)
                while True:
                    time.sleep(1)     # Waits for all messages to arrive and then writing a message
                    msg = input(f"\n Enter a message (text, /switch, /file <path>, /download <id> <path> :  ")

                    if not msg:
                        ClientUI.render(msg_type=MessageTypes.SYSTEM, text="An empy message could not be sent ...")

                    if msg.lower() == "/switch":
                        message_client.message_socket.send(msg.encode('utf-8'))
                        ClientUI.clear_screen()
                        break

                    elif msg.startswith("/file"):
                        ClientUI.render(msg_type=MessageTypes.SYSTEM, text=f"Uploading file ...")

                        if len(msg.split(' ', 1)) != 2:
                            ClientUI.render(msg_type=MessageTypes.SYSTEM, text=" No file path provided. Usage: /file <path>")
                            continue

                        file_path_from_msg = msg.split(' ', 1)[1]
                        try:
                            background_threads.submit(file_client.upload_file, file_path_from_msg)

                            if result_from_server := file_client.file_socket.recv(1024).decode():

                                if result_from_server == FileTransferStatus.EXCEEDED.value:
                                    ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Upload failed, file size exceeded")

                                else:
                                    file_id = result_from_server
                                    ClientUI.render(msg_type=MessageTypes.SYSTEM, text=f"File is uploaded successfully!")
                                    message_client.message_socket.send(file_id.encode('utf-8'))

                        except InvalidInputError:
                            ClientUI.render(msg_type=MessageTypes.SYSTEM, text=f"{file_path_from_msg} isn't a proper file, try again")

                        except Exception as e:
                            file_client.file_socket.close()
                            ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Upload failed ...")
                            raise Exception(f"Error in uploading the file") from e

                    elif msg.startswith("/download"):
                        ClientUI.render(msg_type=MessageTypes.SYSTEM, text=f"Downloading file ...")

                        if len(msg.split()) != 3:
                            ClientUI.render(
                                msg_type=MessageTypes.SYSTEM,
                                text=" You should provide link file and destination path , Usage: /download <link_file> <dst_path>"
                            )
                            continue

                        background_threads.submit(file_client.download_file, msg)

                        if result_from_server := file_client.file_socket.recv(1024).decode():

                            if result_from_server == FileTransferStatus.SUCCEED.value:
                                ClientUI.render(msg_type=MessageTypes.SYSTEM, text="File is downloaded successfully!")

                            elif result_from_server == FileTransferStatus.NOT_FOUND.value:
                                ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Download failed, file id was not found")

                            elif result_from_server == FileTransferStatus.FAILED.value:
                                ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Download failed! (try check your destination path")

                    elif msg.startswith("/quit"):
                        ClientUI.render(msg_type=MessageTypes.SYSTEM, text="Exiting chat...")
                        message_client.message_socket.close()
                        return

                    else:
                        message_client.message_socket.send(msg.encode('utf-8'))


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    main()



