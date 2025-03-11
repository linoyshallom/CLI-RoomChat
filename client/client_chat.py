import os.path
import re
import socket
import threading
from datetime import datetime

from client.client_config import ClientConfig
from server.server_config import ServerConfig
from utils.utils import RoomTypes, chunkify


class InvalidInput(Exception):
    pass


class ChatClient:
    def __init__(self, *, host):
        self.chat_socket =  socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.file_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.received_history_flag = threading.Event()
        self.receive_message_flag = threading.Event()

        try:
            self.chat_socket.connect((host, ServerConfig.listening_port))
            print(f"Successfully connected to Chat Server")
        except Exception as e:
            raise Exception(f"Unable to connect to server - {host}, {ServerConfig.listening_port} {repr(e)} ")

        try:
            self.file_socket.connect((host, ServerConfig.file_server_config.listening_port))
            print(f"Successfully connected to File Server")
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

                        join_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.chat_socket.send(join_timestamp.encode('utf-8'))

                    received_thread = threading.Thread(target=self._receive_message, daemon=True)
                    received_thread.start()

                    # self.chat_socket.send(f"Joined {chosen_room} {group_name}".encode('utf-8'))  # send to server so it send to all the connected - cant separate the pattern of this to regular messages
                    # print(f"\n you Joined {chosen_room} {group_name}")

                    self.received_history_flag.wait() #waiting this to be set before sending a message, so after one messages I receive
                    self.receive_message_flag.wait()

                    break

            except KeyError:
                print(f"\n Got unexpected room name {chosen_room}, try again")

    def _receive_message(self):
        while True:
            try:
                if msg := self.chat_socket.recv(2048).decode('utf-8'):
                    if msg == 'END_HISTORY_RETRIEVAL':  #save it as a const variable somewhere accesses here and in db file
                        self.received_history_flag.set()
                        self.receive_message_flag.set()
                        continue

                    print(f'\n {msg}')
                    self.receive_message_flag.set()

            except Exception as e:
                # Ensure conn.recv() doesn’t block forever (consider adding a timeout if needed).
                self.chat_socket.close()
                raise f"Cannot receiving messages... \n {repr(e)}"

    def _send_message(self):
        # Wait until history is completely received, waiting for .set()
        self.received_history_flag.wait()

        while True:
            if self.receive_message_flag.wait(1.5): #change to 2
                msg = input(f"\n Enter your message : ")

            else:
                msg = input(f"Enter your message :  ") #still send a message if flag wasn't set

            try:
                if msg:
                    if msg.lower() == "/switch":
                        self.chat_socket.send(msg.encode('utf-8'))
                        self.received_history_flag.clear()
                        self._choose_room()

                    elif msg.startswith('/file'):
                        file_path = msg.split()[1]
                        if os.path.isfile(file_path):
                            self.file_socket.send("UPLOAD".encode('utf-8'))
                            self.upload_file_to_server(file_path=file_path)
                            file_id = self._get_generated_file_id()
                            self.chat_socket.send(file_id.encode('utf-8'))  #CHECK send file id to messages table

                    elif msg.startswith('/download'):
                        self.file_socket.send("DOWNLOAD".encode('utf-8'))
                        file_id = msg.split()[1]
                        user_dst_path= msg.split()[2]
                        self.file_socket.send(file_id.encode('utf-8'))
                        self.file_socket.send(user_dst_path.encode('utf-8'))

                    else:
                        self.chat_socket.send(msg.encode('utf-8'))

                    #block writing before receiving again
                    self.receive_message_flag.clear()

                else:
                    #CHECK
                    print("you entered an empty message")

            except Exception as e:
                raise f"Error sending message: {repr(e)}"

    def upload_file_to_server(self, *, file_path: str):
        try:
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            self.file_socket.send(filename.encode('utf-8'))
            self.file_socket.send(str(file_size).encode('utf-8'))

            with open(file_path, 'rb') as file:
                for chunk in chunkify(reader_file=file):
                    self.file_socket.send(chunk)

        except Exception as e:
            print(f"Error uploading file: {e}")

    def _get_generated_file_id(self) -> str:
        file_id = self.file_socket.recv(1024).decode()
        print(f"file {file_id} is uploaded successfully! , now people can download it")
        return file_id

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


#todo validate path, add return value?
#todo File Transfer - needs to occurs parallel so maybe thread of transfer and other of the chat management