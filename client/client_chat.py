import os.path
import re
import socket
import threading
import time
from datetime import datetime
import typing

from pyexpat.errors import messages

from server.server_file_transfer import DownloadFileError, FileIdNotFound
from utils.utils import MessageInfo
from threading import Event
from concurrent.futures import ThreadPoolExecutor

from client.client_config import ClientConfig
from server.db.chat_db import END_HISTORY_RETRIEVAL
from server.server_config import ServerConfig
from utils.utils import RoomTypes, chunkify


class InvalidInput(Exception):
    pass


class MessageClient:
    def __init__(self, host: str, port: int):
        self.message_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.received_history_messages = threading.Event()  #indicate when all history batch messages got to client
        self.received_messages = threading.Event()   #while receiving first display the received messages and then ask for enter messages (check if relevant)

        try:
            self.message_socket.connect((host, port))
            print(f"Client Successfully connected to Chat Server")

        except Exception as e:
            raise Exception(f"Unable to connect to server - {host}, {ServerConfig.listening_port}") from e


    def enter_room(self, *, room_name: str) -> None :
        while True:
            try:
                room_type = RoomTypes[room_name.upper()]

            except KeyError:
                print(f"\n Got unexpected room name {room_name}, try again")

            else:
                self.message_socket.send(room_name.encode('utf-8'))

                if room_type == RoomTypes.PRIVATE:
                    group_name = input("Enter private group name you want to chat: ").strip()
                    self.message_socket.send(group_name.encode('utf-8'))

                self.received_history_messages.clear()
                self.received_messages.clear()   #prevant infinite blocking if flag have set
                # self.received_messages.wait()
                break

    def send_text(self, text: str) -> None :
        ...

    # stop_event is activated by the caller upon switching room or closing the chat.
    def receive_messages(self) -> typing.Generator[str, None, None]:
        # while not self.stop_event.is_set():
        while True:
            try:
                msg = self.message_socket.recv(2048).decode('utf-8')
                print(f"{msg}")
                if msg == END_HISTORY_RETRIEVAL:
                    self.received_history_messages.set() #so clients dont get others messages before the history?
                    self.received_messages.set()   #so clients can send after received history
                    continue #todo still printing the

                # if not msg:
                #     break
                self.received_messages.set()
                yield msg

            except Exception as e:
                self.message_socket.close()
                raise Exception("Cannot receiving messages...") from e



class FileClient:
    def __init__(self, host: str, port: int):
        self.file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.file_socket.connect((host, ServerConfig.listening_port))
            print(f"Client Successfully connected to File Server")

        except Exception as e:
            raise Exception(f"Unable to connect to server - {host}, {...}") from e


    def send_file(self, *, file_path: str) -> None :
        if os.path.isfile(file_path):
            self.file_socket.send("UPLOAD".encode('utf-8'))

            filename = os.path.basename(file_path)
            self.file_socket.send(filename.encode('utf-8'))

            time.sleep(0.01)  # Separate the file name msg from the chunk msg
            with open(file_path, 'rb') as file:
                for chunk in chunkify(reader_file=file, chunk_size=1024):
                    self.file_socket.send(chunk)
        else:
            print(f"{file_path} isn't a proper file, try again ")

    def get_file_id(self) -> str:  # todo should be thread that listen to file server?
        while True:
            file_id = self.file_socket.recv(1024).decode()
            return file_id

    def download_file(self, msg):
        file_id = msg.split()[1]
        user_dir_dst_path = msg.split()[2]

        time.sleep(0.01)
        self.file_socket.send(file_id.encode('utf-8'))
        self.file_socket.send(user_dir_dst_path.encode('utf-8'))


class ClientUI:
    def __init__(self, *, max_history_size: int):
        # Save here all the messages that should be displayed in the UI
        self.messages: typing.List[str] = list()
        self.max_history_size: int = max_history_size

    def add_message(self, message: str):
        # If max_history_size is reached - delete the oldest message
        if len(self.messages) >= self.max_history_size:
            self.messages.pop(0)
        self.messages.append(message)


    def clear_history(self):  # Use this when switching rooms
        self.messages.clear()

    def render(self):
        # print("\033c", end="") Clear screen
        # Print all messages
        for msg in self.messages:
            print(f"{msg} \n")

    def start_receiving(self, message_client: MessageClient):
        print("get into receiving function")
        for msg in message_client.receive_messages():
            self.add_message(msg)
            self.render()


def main():
    message_client = MessageClient(host=ServerConfig.host_ip, port=ServerConfig.listening_port)
    file_client = FileClient(host=ServerConfig.host_ip, port=ServerConfig.file_server_config.listening_port)
    ui = ClientUI(max_history_size=100)

    username = input("Enter your username:")
    message_client.message_socket.send(username.encode('utf-8'))

    with ThreadPoolExecutor(max_workers=5) as background_threads:
        # background_threads.submit(...)  # Start a thread that calls draw_ui() forever

        while True:
            # Ask user to choose room
            print(f"\n Available rooms to chat:")
            for room in RoomTypes:
                print(f"- {room.value}")

            chosen_room = input("Enter room type: ").strip().upper()
            message_client.enter_room(room_name=chosen_room)

            # message_client.stop_event.wait() # ?? Stop the previous "receiver" thread and wait for it to stop
            ui.clear_history()
            background_threads.submit(ui.start_receiving,
                                      message_client)  # Start a "receiver" thread that receives messages and adds them to ClientUI, suppose to keep order of messages
            time.sleep(1) #waits for all messages to come and then writing a message

            while True:
                # Ask user to enter message. The prompt should be displayed in an area in the CLI window that cannot be reached by ClientUI, which is shitty but possible using `curses` library (ask chatgpt)
                msg = input(f"Enter a message (text, /switch, /file <path>, /download <id> <path> :  ")

                if not msg:
                    print("An empy message could not be sent ...")

                if msg.lower() == "/switch":
                    message_client.message_socket.send(msg.encode('utf-8'))
                    message_client.received_history_messages.clear()
                    break

                elif msg.startswith("/file"):
                    print(f"\n Uploading file ...")

                    if len(msg.split(' ', 1)) != 2:
                        print(" No file path provided. Usage: /file <path>")
                        continue

                    file_path_from_msg = msg.split(' ', 1)[1]
                    try:
                        file_client.send_file(file_path=file_path_from_msg) #by thread
                        if file_id := file_client.get_file_id():
                            print(f" file is uploaded successfully!")

                        message_client.message_socket.send(file_id.encode('utf-8'))
                        ui.add_message(message=file_id)

                    except Exception as e:
                        raise Exception(f"Error in uploading the file") from e

                elif msg.startswith("/download"):
                    print(f"\n Downloading file ...")
                    file_client.file_socket.send("DOWNLOAD".encode('utf-8'))

                    if len(msg.split()) != 3:
                        print(" You should provide link file and destination path , Usage: /download <link_file> <dst_path>")
                        continue

                    try:
                        file_client.download_file(msg) #by thread

                    except FileIdNotFound:
                        print(f"file id {file_id} doesn't exist, so cannot be downloaded")

                    except DownloadFileError as e:
                        raise repr(e)

                    else:
                        print(" file is downloaded successfully!")

                else:
                    message_client.message_socket.send(msg.encode('utf-8'))
                    ui.add_message(message=msg)


if __name__ == '__main__':
    main()

"""
server_chat
Chat Server started...
Successfully connected client 127.0.0.1 65284 to messages server

server got username lin
Successfully connected client 127.0.0.1 65285 to messages server
"""

"""
client_chat
Enter your username:lin

 Available rooms to chat:
- GLOBAL
- PRIVATE
Enter room type: global
get into receiving function
No messages in this chat yet ...
No messages in this chat yet ... 

END_HISTORY_RETRIEVAL
lin joined GLOBAL
No messages in this chat yet ... 

lin joined GLOBAL 

"""
