import dataclasses
import re
import socket
import threading
import typing
from datetime import datetime

from client.client_config import ClientConfig
from utils.utils import RoomTypes


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
    def __init__(self,* , host, listen_port):
        self.client =  socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.received_history_flag = threading.Event()
        self.receive_message_flag = threading.Event()  #while receiving, display first receive and then send the message in real time

        try:
            self.client.connect((host,listen_port))
            print(f"Successfully connected to server")

        except Exception as e:
            raise Exception(f"Unable to connect to server {host,listen_port} {repr(e)} ")

        self.username = input("Enter your username:")
        self.client.send(self.username.encode('utf-8'))

        self._choose_room()

        send_thread = threading.Thread(target=self._send_message(), daemon=True)
        send_thread.start()

    def _choose_room(self):
        while True:
            print(f"\n Available rooms to chat:")
            for room in RoomTypes:
                print(f"- {room.value}")

            chosen_room = input("Enter room type: ").strip().upper()
            group_name = ""

            try:
                if room_type := RoomTypes[chosen_room.upper()]:
                    self.client.send(chosen_room.encode('utf-8'))

                    if room_type == RoomTypes.PRIVATE:
                        group_name = input("Enter private group name you want to chat: ").strip()
                        self.client.send(group_name.encode('utf-8'))

                        join_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.client.send(join_timestamp.encode('utf-8'))

                    received_thread = threading.Thread(target=self._receive_message, daemon=True)
                    received_thread.start()

                    self.client.send(f"Joined {chosen_room} {group_name}".encode('utf-8'))
                    print(f"\n you Joined {chosen_room} {group_name}")

                    self.received_history_flag.wait() #waiting this to be set before sending a message, so after one messages I receive
                    self.receive_message_flag.wait()

                    break

            except KeyError:
                print(f"\n Got unexpected room name {chosen_room}, try again")

    def _receive_message(self):
        while True:
            try:
                if msg := self.client.recv(2048).decode('utf-8'):
                    if msg == 'END_HISTORY_RETRIEVAL':
                        self.received_history_flag.set()
                        self.receive_message_flag.set()
                        continue

                    print(f'\n {msg}')
                    self.receive_message_flag.set()

            except Exception as e:
                self.client.close()
                raise f"Cannot receiving messages... \n {repr(e)}"

    def _send_message(self):
        self.received_history_flag.wait()

        while True:
            if self.receive_message_flag.wait(1.5):
                msg = input(f"\n Enter your message : ")

            else:
                msg = input(f"Enter your message :  ") # enable send a message if flag wasn't set

            if msg:
                if msg.lower() == "/switch":
                    self.client.send(msg.encode('utf-8'))
                    self.received_history_flag.clear()
                    self._choose_room()
                else:
                    self.client.send(msg.encode('utf-8'))

                self.receive_message_flag.clear()    #block writing before receiving again

    @staticmethod
    def _user_input_validation(*, username):
        if username:
            if not re.match(ClientConfig.allowed_input_user_pattern, username):
                raise InvalidInput("Input username is not allowed \n Only letters, numbers, dots, and underscores are allowed.")
        else:
            raise InvalidInput("Input username is empty")


def main():
    _ = ChatClient(host='127.0.0.1', listen_port=2)

if __name__ == '__main__':
    main()
