import json
import logging
import os.path
import socket
import threading
import time
import typing
from concurrent.futures import ThreadPoolExecutor
from logging import getLogger

from config.config import ClientConfig, MessageServerConfig, FileServerConfig
from definitions.errors import DownloadFileError, FileIdNotFoundError
from definitions.structs import MessageInfo
from definitions.types import RoomTypes, MessageTypes
from utils.utils import chunkify

logger = getLogger(__name__)

class InvalidInput(Exception):
    pass

class MessageClient:
    def __init__(self, host: str, port: int):
        self.message_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.received_history_messages = threading.Event()  #indicate when all history batch messages retrieve to client
        self.received_messages = threading.Event()   #while receiving first display the received messages and then ask for enter messages (check if relevant)

        try:
            self.message_socket.connect((host, port))
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

                self.message_socket.send(json.dumps(setup_room_data).encode('utf-8'))
                self.received_history_messages.clear()
                self.received_messages.clear()              #prevant infinite blocking if flag have set
                break

    def receive_messages(self) -> typing.Generator[str, None, None]:
        while True:
            try:
                msg = self.message_socket.recv(2048).decode('utf-8')
                self.received_messages.set()
                yield msg

            except Exception as e:
                self.message_socket.close()
                logger.exception("Failed to receive messages")
                raise Exception("Cannot receiving messages...") from e

class FileClient:
    def __init__(self, host: str, port: int):
        self.file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.file_socket.connect((host, port))
            logger.info(f"Client Successfully connected to File Server")

        except Exception as e:
            logger.exception("Failed to connect file server ... ")
            raise Exception(f"Unable to connect to file server - {host}, {port}") from e

    def upload_file(self, file_path: str) -> None :
        if os.path.isfile(file_path):

            self.file_socket.send("UPLOAD".encode('utf-8'))

            filename = os.path.basename(file_path)
            upload_data = {
                "filename": filename
            }
            self.file_socket.sendall(json.dumps(upload_data).encode('utf-8'))

            time.sleep(0.01)  # Separate the file name msg from the chunk msg
            with open(file_path, 'rb') as file:
                while True:
                    try:
                        # for chunk in chunkify(reader_file=file, chunk_size=1024):
                        chunk = next(chunkify(reader_file=file, chunk_size=1024))
                        self.file_socket.send(chunk)
                    except StopIteration:
                        print("sending empty") #not sent to server
                        self.file_socket.send(b"")
                        break

        else:
            raise InvalidInput(f"{file_path} isn't a proper file, try again ")

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
        while True:
            file_id = self.file_socket.recv(1024).decode()
            return file_id

class ClientUI:
    def __init__(self, *, max_history_size: int):
        # Save here all the messages that should be displayed in the UI
        self.messages: typing.List[str] = list()
        self.max_history_size: int = max_history_size
        self.ui_lock = threading.Lock()         #Updating ui should be ThreadSafe
        self.receive_lock = threading.Lock()

    def add_message(self, message: str):
        with self.ui_lock:
            if len(self.messages) >= self.max_history_size:
                self.messages.pop(0)
            self.messages.append(message)

    def clear_history(self):
        with self.ui_lock:
            self.messages.clear()

    def clear_screen(self):  # Unfortunately working only on regular CLI
        with self.ui_lock:
            os.system('cls' if os.name == 'nt' else 'clear')

    def start_receiving(self, message_client: MessageClient): #keep order of messages with lock don't helping in regular CLI
        print(f"get into receiving function:")
        for msg in message_client.receive_messages():
            self.add_message(msg)
            with self.receive_lock:
                print(f"\n {msg}", flush=True)

    def render(self, *, msg_type, text):
        msg = MessageInfo(type=msg_type, text_message=text)
        with self.ui_lock:
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
            message_client.received_messages.wait()

            while True:
                time.sleep(0.01)
                msg = input(f"Enter a message (text, /switch, /file <path>, /download <id> <path> :  ")

                if not msg:
                    ui.render(msg_type=MessageTypes.SYSTEM, text="An empy message could not be sent ...")

                if msg.lower() == "/switch":
                    message_client.message_socket.send(msg.encode('utf-8'))
                    message_client.received_history_messages.clear()
                    ui.clear_screen()
                    break

                elif msg.startswith("/file"):
                    ui.render(msg_type=MessageTypes.SYSTEM, text=f"\n Uploading file ...")

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

                    except InvalidInput as e:
                        logger.exception(f"{repr(e)}")
                        continue

                    except Exception as e:
                        file_client.file_socket.close()
                        raise Exception(f"Error in uploading the file") from e

                elif msg.startswith("/download"):
                    ui.render(msg_type=MessageTypes.SYSTEM, text=f"\n Downloading file ...")

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


#todo error file handleing dont working
#todo check necessary of many things (history)
#todo join message cannot be previous to the history messages, why generator dot keep the order and lock don't work here -> history event
