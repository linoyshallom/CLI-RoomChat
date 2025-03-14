import dataclasses
import os.path
import re
import socket
import threading
import time
import typing
from datetime import datetime

from client.client_config import ClientConfig
from server.db.chat_db import END_HISTORY_RETRIEVAL
from server.server_config import ServerConfig
from utils.utils import RoomTypes, chunkify


class InvalidInput(Exception):
    pass

@dataclasses.dataclass
class ClientInfo:
    client_conn: socket.socket
    username: str
    room_type: RoomTypes = None
    current_room: typing.Optional[str] = None
    room_setup_done_flag: threading.Event = dataclasses.field(default_factory=threading.Event)

class ChatClient:
    def __init__(self, *, host):
        self.chat_socket =  socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.received_history_flag = threading.Event()
        self.receive_message_flag = threading.Event()             # While receiving, display first receive and then send the message in real time

        try:
            self.chat_socket.connect((host, ServerConfig.listening_port))
            print(f"Client Successfully connected to Chat Server")
        except Exception as e:
            raise Exception(f"Unable to connect to server - {host}, {ServerConfig.listening_port} {repr(e)} ")

        try:
            self.file_socket.connect((host, ServerConfig.file_server_config.listening_port))
            print(f"Client Successfully connected to File Server")
        except Exception as e:
            raise Exception(f"Unable to connect to server - {host}, {ServerConfig.file_server_config.listening_port} {repr(e)} ")

        self.username = input("Enter your username:")
        self.chat_socket.send(self.username.encode('utf-8'))

        self._choose_room()

        send_thread = threading.Thread(target=self._send_message(), daemon=True)
        send_thread.start()

    def _choose_room(self):
        while True:
            print(f"\n Available rooms to chat:")
            for room in RoomTypes:
                print(f"- {room.value}")

            chosen_room = input("Enter room type: ").strip().upper()

            try:
                if room_type := RoomTypes[chosen_room.upper()]:
                    self.chat_socket.send(chosen_room.encode('utf-8'))

                    if room_type == RoomTypes.PRIVATE:
                        group_name = input("Enter private group name you want to chat: ").strip()
                        self.chat_socket.send(group_name.encode('utf-8'))

                        time.sleep(0.01)

                        join_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.chat_socket.send(join_timestamp.encode('utf-8'))

                    received_thread = threading.Thread(target=self._receive_message, daemon=True)
                    received_thread.start()

                    self.received_history_flag.wait()             # Waiting this to be set before sending a message, so after one messages I receive
                    self.receive_message_flag.wait()

                    break

            except KeyError:
                print(f"\n Got unexpected room name {chosen_room}, try again")

    def _receive_message(self):
        while True:
            try:
                if msg := self.chat_socket.recv(2048).decode('utf-8'):
                    if msg == END_HISTORY_RETRIEVAL:
                        self.received_history_flag.set()
                        self.receive_message_flag.set()
                        continue

                    print(f'\n {msg}')
                    self.receive_message_flag.set()

            except Exception as e:
                self.chat_socket.close()
                raise f"Cannot receiving messages... \n {repr(e)}"

    def _send_message(self):
        self.received_history_flag.wait()
        time.sleep(0.5)              # So after old messages get the joining msg and then send

        while True:
            if self.receive_message_flag.wait():
                msg = input(f"\n Enter your message : ")
            else:
                msg = input(f"Enter your message :  ")            # enable send a message if flag wasn't set

            try:
                if msg:
                    if msg.lower() == "/switch":
                        self.chat_socket.send(msg.encode('utf-8'))
                        self.received_history_flag.clear()
                        self._choose_room()

                    elif msg.startswith("/file"):
                        print(f"\n Uploading file ...")
                        # self.file_socket.send("UPLOAD".encode('utf-8'))

                        if len(msg.split(' ',1)) != 2:
                            print(" No file path provided. Usage: /file <path>")
                            continue

                        file_path_from_msg = msg.split(' ',1)[1]
                        print(file_path_from_msg)

                        if os.path.isfile(file_path_from_msg):
                            self.send_file_to_file_server(file_path=file_path_from_msg)

                            file_id = self._get_file_id()
                            self.chat_socket.send(file_id.encode('utf-8'))
                        else:
                            print(f"{file_path_from_msg} isn't a proper file, try again ")

                    elif msg.startswith("/download"):
                        print(f"\n Downloading file ...")
                        self.file_socket.send("DOWNLOAD".encode('utf-8'))

                        if len(msg.split()) != 3:
                            print(" You should provide link file and destination path , Usage: /download <link_file> <dst_path>")
                            continue

                        file_id = msg.split()[1]
                        user_dir_dst_path = msg.split()[2]

                        print(f"file id {file_id}")
                        time.sleep(0.01)
                        self.file_socket.send(file_id.encode('utf-8'))
                        self.file_socket.send(user_dir_dst_path.encode('utf-8'))

                        response = self._response_from_server()
                        print(response)
                        continue

                    else:
                        self.chat_socket.send(msg.encode('utf-8'))

                    self.receive_message_flag.clear()           # Block writing before receiving again

                else:
                    print("An empy message could not be sent ...")

            except Exception as e:
                raise f"Sending message error occurs: {repr(e)}"

    def send_file_to_file_server(self, *, file_path: str):
        try:
            self.file_socket.send("UPLOAD".encode('utf-8'))
            filename = os.path.basename(file_path)
            self.file_socket.send(filename.encode('utf-8'))

            time.sleep(0.01)           # Separate the file name from the chunk
            with open(file_path, 'rb') as file:
                for chunk in chunkify(reader_file=file, chunk_size=1024):
                    self.file_socket.send(chunk)

        except Exception as e:
            print(f"Error uploading file: {e}")

    def _get_file_id(self) -> str:  #todo should be thread that listen to file server?
        while True:
            file_id = self.file_socket.recv(1024).decode()
            print(f" file is uploaded successfully!")
            return file_id

    def _response_from_server(self):
        while True:
            return  self.file_socket.recv(1024).decode()

    @staticmethod
    def _user_input_validation(*, username):
        if username:
            if not re.match(ClientConfig.allowed_input_user_pattern, username):
                raise InvalidInput("Input username is not allowed \n Only letters, numbers, dots, and underscores are allowed.")
        else:
            raise InvalidInput("Input username is empty")


def main():
    _ = ChatClient(host='127.0.0.1')

if __name__ == '__main__':
    main()
