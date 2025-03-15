import os.path
import re
import socket
import threading
import time
from datetime import datetime
import typing

from pyexpat.errors import messages

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

        self.stop_event = threading.Event()

        try:
            self.message_socket.connect((host, ServerConfig.listening_port))
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

                    time.sleep(0.01)

                    join_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") #servr can get time itself
                    self.message_socket.send(join_timestamp.encode('utf-8'))

                self.stop_event.wait()
                break

    def send_text(self, text: str) -> None :
        ...

    # stop_event is activated by the caller upon switching room or closing the chat.
    def receive_messages(self) -> typing.Generator[str, None, None]:
        while not self.stop_event.is_set():
            try:
                msg = self.message_socket.recv(2048).decode('utf-8')
                if not msg:
                    break

                # yield MessageInfo(text_message=msg, sender_name=)
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
        try:
            self.file_socket.send("UPLOAD".encode('utf-8'))
            filename = os.path.basename(file_path)
            self.file_socket.send(filename.encode('utf-8'))

            time.sleep(0.01)  # Separate the file name from the chunk
            with open(file_path, 'rb') as file:
                for chunk in chunkify(reader_file=file, chunk_size=1024):
                    self.file_socket.send(chunk)

        except Exception as e:  # LIELREVIEW:   I would not catch exception here, i would let caller decide how exception should be treated.
            print(f"Error uploading file: {e}")

    def get_file(file_id: str) -> str : # Returns file path
        ...


class ClientUI:
    def __init__(self, *, max_history_size: int):
        # Save here all of the messages that should be displayed in the UI
        self.messages: typing.List[str] = list()
        self.max_history_size: int = max_history_size

    def add_message(self, message: str):
        # If max_history_size is reached - delete oldest message
        if len(self.messages) >= self.max_history_size:
            self.messages.pop(0)
        self.messages.append(message)

    def clear_history(self):  # Use this when switching rooms
        self.messages.clear()

    def render(self):
        # print("\033c", end="") Clear screen
        # Print all messages
        for msg in self.messages:
            print(msg)

    def start_receiving(self, message_client: MessageClient):
        for msg in message_client.receive_messages():
            self.add_message(msg)
            self.render()

class Client:
    def __init__(self, host, port):
        self.message_client = MessageClient(host=..., port=...)
        self.file_client = FileClient(host=..., port=...)
        self.ui = ClientUI(max_history_size=100)

    def main(self):
        username = input("Enter your username:")
        self.message_client.message_socket.send(username.encode('utf-8'))

        with ThreadPoolExecutor(...) as background_threads:
            background_threads.submit(...)  # Start a thread that calls draw_ui() forever

            while True:
                # Ask user to choose room
                 print(f"\n Available rooms to chat:")
                 for room in RoomTypes:
                     print(f"- {room.value}")

                 chosen_room = input("Enter room type: ").strip().upper()
                 self.message_client.enter_room(room_name=chosen_room)

                 self.message_client.stop_event.set() #?? Stop the previous "receiver" thread and wait for it to stop
                 self.ui.clear_history()

                 background_threads.submit(self.ui.start_receiving, self.message_client)  # Start a "receiver" thread that receives messages and adds them to ClientUI

                while True:
                    # Ask user to enter message. The prompt should be displayed in an area in the CLI window that cannot be reached by ClientUI, which is shitty but possible using `curses` library (ask chatgpt)
                    msg = input(f"Enter a message (text, /switch, /file <path>, /download <id> <path> :  ")

                    try:
                        if msg:
                            if msg.lower() == "/switch":
                                self.message_client.message_socket.send(msg.encode('utf-8'))
                                break

                            elif msg.startswith("/file"):
                                print(f"\n Uploading file ...")

                                if len(msg.split(' ', 1)) != 2:
                                    print(" No file path provided. Usage: /file <path>")
                                    continue

                                file_path_from_msg = msg.split(' ', 1)[1]

                                if os.path.isfile(file_path_from_msg):
                                    file_client(file_path=file_path_from_msg)

                                    file_id = self._get_file_id()
                                    self.message_socket.send(file_id.encode('utf-8'))
                                    self.ui.add_messa
                                else:
                                    print(f"{file_path_from_msg} isn't a proper file, try again ")

                            elif msg.startswith("/download"):
                                print(f"\n Downloading file ...")
                                self.file_socket.send("DOWNLOAD".encode('utf-8'))

                                if len(msg.split()) != 3:
                                    print(
                                        " You should provide link file and destination path , Usage: /download <link_file> <dst_path>")
                                    continue

                                file_id = msg.split()[1]
                                user_dir_dst_path = msg.split()[2]

                                print(f"file id {file_id}")
                                time.sleep(0.01)
                                self.file_socket.send(file_id.encode('utf-8'))
                                self.file_socket.send(user_dir_dst_path.encode('utf-8'))

                                response = self._response_from_server()  # LIELREVIEW:  Func name should be a verb. _get_response_from_server
                                print(response)  # LIELREVIEW:  You are printing the file? probably better to save it somewhere no?
                                continue

                            else:
                                self.chat_socket.send(msg.encode('utf-8'))

                        else:
                            print("An empy message could not be sent ...")


                #     if < is upload file >
                #     client.add_message(...)
                #     background_threads.submit(...)  # Submit task that uploads file
                #
                # if < is download file >
                # client.add_message(..)
                # background_threads.submit(...)  # Submit task that downloads file
                #
                #




# class ChatClient:
#     def __init__(self, *, host):
#         #todo close the socket somewhere
#         self.chat_socket =  socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#         self.file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#
#         self.received_history_flag = threading.Event()
#         self.receive_message_flag = threading.Event()             # While receiving, display first receive and then send the message in real time
#
#         try:
#             self.chat_socket.connect((host, ServerConfig.listening_port))
#             print(f"Client Successfully connected to Chat Server")
#         except Exception as e:
#             raise Exception(f"Unable to connect to server - {host}, {ServerConfig.listening_port} {repr(e)} ")
#
#         try:
#             self.file_socket.connect((host, ServerConfig.file_server_config.listening_port))
#             print(f"Client Successfully connected to File Server")
#         except Exception as e:
#             raise Exception(f"Unable to connect to server - {host}, {ServerConfig.file_server_config.listening_port} {repr(e)} ")
#
#         self.username = input("Enter your username:")
#         self.chat_socket.send(self.username.encode('utf-8'))
#
#         self._choose_room()
#
#         send_thread = threading.Thread(target=self._send_message(), daemon=True)
#         send_thread.start()
#
#     def _choose_room(self):
#         while True:
#             print(f"\n Available rooms to chat:")
#             for room in RoomTypes:
#                 print(f"- {room.value}")
#
#             chosen_room = input("Enter room type: ").strip().upper()
#
#             try:
#                 if room_type := RoomTypes[chosen_room.upper()]:
#                     self.chat_socket.send(chosen_room.encode('utf-8'))
#
#                     if room_type == RoomTypes.PRIVATE:
#                         group_name = input("Enter private group name you want to chat: ").strip()
#                         self.chat_socket.send(group_name.encode('utf-8'))
#
#                         time.sleep(0.01)
#
#                         join_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#                         self.chat_socket.send(join_timestamp.encode('utf-8'))
#
#                     received_thread = threading.Thread(target=self._receive_message, daemon=True)
#                     received_thread.start()
#
#                     self.received_history_flag.wait()             # Waiting this to be set before sending a message, so after one messages I receive
#                     self.receive_message_flag.wait()
#
#                     break
#
#             except KeyError:
#                 print(f"\n Got unexpected room name {chosen_room}, try again")
#
#     def _receive_message(self):
#         while True:
#             try:
#                 if msg := self.chat_socket.recv(2048).decode('utf-8'):
#                     if msg == END_HISTORY_RETRIEVAL:
#                         self.received_history_flag.set()
#                         self.receive_message_flag.set()
#                         continue
#
#                     print(f'\n {msg}')
#                     self.receive_message_flag.set()
#
#             except Exception as e:
#                 self.chat_socket.close()
#                 raise f"Cannot receiving messages... \n {repr(e)}"
#
#     def _send_message(self):
#         self.received_history_flag.wait()
#         time.sleep(0.5)              # So after old messages get the joining msg and then send
#
#         while True:
#             if self.receive_message_flag.wait():
#                 msg = input(f"\n Enter your message : ")
#             else:
#                 msg = input(f"Enter your message :  ")            # enable send a message if flag wasn't set
#
#             try:
#                 if msg:
#                     if msg.lower() == "/switch":
#                         self.chat_socket.send(msg.encode('utf-8'))
#                         self.received_history_flag.clear()
#                         self._choose_room()
#
#                     elif msg.startswith("/file"):
#                         print(f"\n Uploading file ...")
#                         # self.file_socket.send("UPLOAD".encode('utf-8'))
#
#                         if len(msg.split(' ',1)) != 2:
#                             print(" No file path provided. Usage: /file <path>")
#                             continue
#
#                         file_path_from_msg = msg.split(' ',1)[1]
#                         print(file_path_from_msg)
#
#                         if os.path.isfile(file_path_from_msg):
#                             self.send_file_to_file_server(file_path=file_path_from_msg)
#
#                             file_id = self._get_file_id()
#                             self.chat_socket.send(file_id.encode('utf-8'))
#                         else:
#                             print(f"{file_path_from_msg} isn't a proper file, try again ")
#
#                     elif msg.startswith("/download"):
#                         print(f"\n Downloading file ...")
#                         self.file_socket.send("DOWNLOAD".encode('utf-8'))
#
#                         if len(msg.split()) != 3:
#                             print(" You should provide link file and destination path , Usage: /download <link_file> <dst_path>")
#                             continue
#
#                         file_id = msg.split()[1]
#                         user_dir_dst_path = msg.split()[2]
#
#                         print(f"file id {file_id}")
#                         time.sleep(0.01)
#                         self.file_socket.send(file_id.encode('utf-8'))
#                         self.file_socket.send(user_dir_dst_path.encode('utf-8'))
#
#                         response = self._response_from_server()
#                         print(response)
#                         continue
#
#                     else:
#                         self.chat_socket.send(msg.encode('utf-8'))
#
#                     self.receive_message_flag.clear()           # Block writing before receiving again
#
#                 else:
#                     print("An empy message could not be sent ...")
#
#             except Exception as e:
#                 raise f"Sending message error occurs: {repr(e)}"
#
#     def send_file_to_file_server(self, *, file_path: str):
#         try:
#             self.file_socket.send("UPLOAD".encode('utf-8'))
#             filename = os.path.basename(file_path)
#             self.file_socket.send(filename.encode('utf-8'))
#
#             time.sleep(0.01)           # Separate the file name from the chunk
#             with open(file_path, 'rb') as file:
#                 for chunk in chunkify(reader_file=file, chunk_size=1024):
#                     self.file_socket.send(chunk)
#
#         except Exception as e:
#             print(f"Error uploading file: {e}")
#
#     def _get_file_id(self) -> str:  #todo should be thread that listen to file server?
#         while True:
#             file_id = self.file_socket.recv(1024).decode()
#             print(f" file is uploaded successfully!")
#             return file_id
#
#     def _response_from_server(self):
#         while True:
#             return  self.file_socket.recv(1024).decode()
#
#     @staticmethod
#     def _user_input_validation(*, username):
#         if username:
#             if not re.match(ClientConfig.allowed_input_user_pattern, username):
#                 raise InvalidInput("Input username is not allowed \n Only letters, numbers, dots, and underscores are allowed.")
#         else:
#             raise InvalidInput("Input username is empty")


# def main():
#     _ = ChatClient(host='127.0.0.1')

if __name__ == '__main__':
    main()
