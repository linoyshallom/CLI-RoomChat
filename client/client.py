import json
import logging
import os.path
import socket
import time
import typing
from concurrent.futures import ThreadPoolExecutor
from logging import getLogger

from config import ClientConfig, MessageServerConfig, FileServerConfig, END_OF_MSG_INDICATOR, END_OF_FILE_INDICATOR
from definitions import DownloadFileError, FileIdNotFoundError
from definitions import InvalidInput
from definitions import MessageInfo
from definitions import RoomTypes, MessageTypes
from utils import chunkify, split_messages_in_buffer

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

    def enter_room(self, *, room_name: str) -> None :
        setup_room_data = {}
        while True:
            try:
                room_type = RoomTypes[room_name.upper()]
            except KeyError:
                logger.error(f"\n Got unexpected room type {room_name}, try again")

            else:
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

    def receive_messages(self) -> typing.Generator[str, None, None]: #not ready to be checked, still working on it
        fragmented_msg = ""
        while True:
            try:
                buffer_msg = self._message_socket.recv(50).decode('utf-8')  # I consumed buffer of 1024 bytes which can contains more than one message

                aggrigated_buffers = fragmented_msg + buffer_msg
                yield from split_messages_in_buffer(aggrigated_buffers)

                if END_OF_MSG_INDICATOR not in buffer_msg:   # If no END_OF_MSG_INDICATOR at all, store the entire buffer as a fragment - msg can be bigger then 1024
                    fragmented_msg += buffer_msg

                elif buffer_msg[-1] != END_OF_MSG_INDICATOR:   # If the last char isn't END_OF_MSG_INDICATOR, extract the remaining fragment
                    fragmented_msg = buffer_msg.rsplit(END_OF_MSG_INDICATOR, 1)[1]

                else:
                    fragmented_msg = ""

            except Exception as e:
                self._message_socket.close()
                logger.exception("Failed to receive messages")
                raise Exception("Cannot receiving messages...") from e

    @property
    def message_socket(self):
        return self._message_socket

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
    def file_socket(self):
        return self._file_socket

    # Triggers upload_file methode in FileServerTransfer
    def upload_file(self, file_path: str) -> None :
        if os.path.isfile(file_path):

            self._file_socket.send("UPLOAD".encode('utf-8'))

            filename = os.path.basename(file_path)
            upload_data = {
                "filename": filename
            }
            self._file_socket.sendall(json.dumps(upload_data).encode('utf-8'))

            # time.sleep(0.01)  # Separate the file name msg from the chunk msg
            with open(file_path, 'rb') as file:
                while True:
                    try:
                        chunk = next(chunkify(reader_file=file, chunk_size=1024))
                        self._file_socket.sendall(chunk)
                    except StopIteration:
                        print("sending INDICATOR")
                        self._file_socket.sendall(END_OF_FILE_INDICATOR)
                        break
        else:
            raise InvalidInput(f"Client entered inappropriate file")

    # Triggers download_file methode in FileServerTransfer
    def download_file(self, message: str) -> str:
        self.file_socket.send("DOWNLOAD".encode('utf-8'))
        file_id = message.split()[1]
        user_dir_dst_path = message.split()[2]

        download_data = {
            "file_id": file_id,
            "dst_path": user_dir_dst_path
        }
        self.file_socket.sendall(json.dumps(download_data).encode('utf-8'))

        final_response_from_server = self.file_socket.recv(1024).decode()
        return final_response_from_server

    def get_file_id(self) -> str:
        file_id = self.file_socket.recv(1024).decode()
        return file_id

class ClientUI:
    def __init__(self, *, max_history_size: int):
        # Save here all the messages that should be displayed in the UI
        self._messages: typing.List[str] = list()
        self._max_history_size: int = max_history_size

    def add_message(self, message: str):
        if len(self._messages) >= self._max_history_size:
            self._messages.pop(0)
        self._messages.append(message)

    def clear_history(self):
        self._messages.clear()

    @staticmethod
    def clear_screen():
        os.system('cls' if os.name == 'nt' else 'clear')

    def start_receiving(self, message_client: MessageClient):
        print(f"get into receiving function:")
        for msg in message_client.receive_messages():
            self.add_message(msg)
            print(f"\n {msg}", flush=True)

    @staticmethod
    def render(*, msg_type, text):  #should be thread that clean screen and print all messages list
        msg = MessageInfo(type=msg_type, text_message=text)
        print(msg.formatted_msg())


def main():
    ui = ClientUI(max_history_size=100)
    message_client = MessageClient(host=ClientConfig.host_ip, port=MessageServerConfig.listening_port)
    file_client = FileClient(host=ClientConfig.host_ip, port=FileServerConfig.listening_port)

    time.sleep(0.01)                          #logger info messages should be before this section
    username = input("Enter your username:")
    message_client.message_socket.send(username.encode('utf-8'))

    with ThreadPoolExecutor(max_workers=5) as background_threads:
        while True:
            print(f"\n Available rooms to chat:")
            for room in RoomTypes:
                print(f"- {room.value}")

            chosen_room = input("Enter room type: ").strip().upper()
            message_client.enter_room(room_name=chosen_room)

            ui.clear_history()
            background_threads.submit(ui.start_receiving,message_client)  # Start a "receiver" thread that receives messages and adds them to ClientUI
            time.sleep(1)    #waits for all messages to arrive and then writing a message

            while True:
                msg = input(f"\n Enter a message (text, /switch, /file <path>, /download <id> <path> :  ")

                if not msg:
                    ui.render(msg_type=MessageTypes.SYSTEM, text="An empy message could not be sent ...")

                if msg.lower() == "/switch":
                    message_client.message_socket.send(msg.encode('utf-8'))
                    ui.clear_screen()
                    break

                elif msg.startswith("/file"):
                    ui.render(msg_type=MessageTypes.SYSTEM, text=f" Uploading file ...")

                    if len(msg.split(' ', 1)) != 2:
                        ui.render(msg_type=MessageTypes.SYSTEM, text=" No file path provided. Usage: /file <path>")
                        continue

                    file_path_from_msg = msg.split(' ', 1)[1]
                    try:
                        upload_thread = background_threads.submit(file_client.upload_file, file_path_from_msg)
                        upload_thread.result()

                        if file_id := file_client.get_file_id():
                            ui.render(msg_type=MessageTypes.SYSTEM, text=f"file is uploaded successfully!")

                        message_client.message_socket.send(file_id.encode('utf-8'))
                        ui.add_message(message=file_id)

                    except InvalidInput:
                        ui.render(msg_type=MessageTypes.SYSTEM, text=f"{file_path_from_msg} isn't a proper file, try again")
                        continue

                    except Exception as e:
                        file_client.file_socket.close()
                        raise Exception(f"Error in uploading the file") from e

                elif msg.startswith("/download"):
                    ui.render(msg_type=MessageTypes.SYSTEM, text=f"vDownloading file ...")

                    if len(msg.split()) != 3:
                        ui.render(
                            msg_type=MessageTypes.SYSTEM,
                            text=" You should provide link file and destination path , Usage: /download <link_file> <dst_path>"
                        )
                        continue

                    download_thread = background_threads.submit(file_client.download_file, msg)
                    try:
                        download_thread.result()
                        ui.render(msg_type=MessageTypes.SYSTEM, text="File is downloaded successfully!")

                    except DownloadFileError as e:
                         ui.render(msg_type=MessageTypes.SYSTEM, text=f"Failed to download this file, {repr(e)} ")
                         continue

                    except FileIdNotFoundError:
                        ui.render(msg_type=MessageTypes.SYSTEM, text="File id was NOT found, check your id or try send this file again")
                        continue

                elif msg.startswith("/quit"):
                    ui.render(msg_type=MessageTypes.SYSTEM, text="Exiting chat...")
                    message_client.message_socket.close()
                    return

                else:
                    message_client.message_socket.send(msg.encode('utf-8'))
                    ui.add_message(message=msg)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    main()

#todo render function
#todo error file handling don't working
