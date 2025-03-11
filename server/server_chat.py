import socket
import threading
import typing
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from server.db.chat_db import ChatDB
from server.server_config import ServerConfig
from server.server_file_transfer import FileTransferServer
from utils import RoomTypes, ClientInfo, MessageInfo


class ChatServer:
    def __init__(self, *, host, listen_port):   #should be init class or not?
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.server.bind((host, listen_port))
        except Exception as e:
            print(f"Unable to bind to host and port : {repr(e)}")

        self.server.listen(ServerConfig.listener_limit_number)

        self.active_clients: typing.Set[ClientInfo] = set()
        self.room_name_to_active_clients: typing.DefaultDict[str, typing.List[ClientInfo]] = defaultdict(list)

        self.chat_db = ChatDB()
        self.chat_db.setup_database()

        self.room_setup_done_flag = threading.Event()

    def client_handler(self, conn: socket.socket):
        sender_name = conn.recv(1024).decode('utf-8')
        print(f"Got username {sender_name}")
        self.chat_db.store_user(sender_name=sender_name.strip())

        client_info = ClientInfo(client_conn=conn, username=sender_name)

        print(f"start setup")
        room_setup_thread = threading.Thread(target=self._room_setup, args=(conn, client_info))
        room_setup_thread.start()

        #listen for massages after setup
        print("start listen")
        received_messages_thread = threading.Thread(target=self._receiving_messages, args=(conn, client_info,)) #get client info?
        received_messages_thread.start()

    def _room_setup(self, conn, client_info: ClientInfo):
        while True:
            room_type = conn.recv(1024).decode('utf-8')

            if RoomTypes[room_type.upper()] == RoomTypes.PRIVATE:
                group_name = conn.recv(1024).decode('utf-8')
                user_join_timestamp = conn.recv(1024).decode('utf-8')
                client_info.user_joined_timestamp = user_join_timestamp
                print(f"user join to room timestamp {user_join_timestamp}")

                self.chat_db.create_room(room_name=group_name)
                self.chat_db.send_previous_messages_in_room(conn=client_info.client_conn, room_name=group_name, join_timestamp=user_join_timestamp)

            else:
                group_name = room_type
                self.chat_db.create_room(room_name=group_name)
                self.chat_db.send_previous_messages_in_room(conn=client_info.client_conn, room_name=group_name)

            # msg_obj = MessageInfo(text_message=f"{client_info.username} joined {room_type} {group_name}")
            # print(f"msg_obj {msg_obj} ")
            # self._broadcast_to_all_active_clients_in_room(msg=msg_obj, current_room=client_info.current_room, format_msg=False)

            client_info.room_type = room_type
            client_info.current_room = group_name
            self.room_name_to_active_clients[group_name].append(client_info)

            self.room_setup_done_flag.set()
            print(f"set setup flag")
            break

    def _receiving_messages(self, conn, client_info: ClientInfo):
        while True:
                self.room_setup_done_flag.wait()

                if msg := conn.recv(2048).decode('utf-8'):
                    if msg == '/switch':
                        self.room_setup_done_flag.clear() #clear set so all messages send to the setup from this time
                        print(f"clear setup flag ")

                        self._remove_client_in_current_room(current_room=client_info.current_room, sender_username=client_info.username)

                        msg_obj = MessageInfo(text_message=f"{client_info.username} left {client_info.current_room}")
                        self._broadcast_to_all_active_clients_in_room(
                            msg= msg_obj,
                            current_room=client_info.current_room,
                            format_msg=False
                        )

                        print(f"removing client mapping: {self.room_name_to_active_clients}")
                        self._room_setup(conn, client_info)

                    else:
                        print(f"got message {msg}")
                        msg_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        msg_obj = MessageInfo(text_message=msg, sender_name=client_info.username, msg_timestamp=msg_timestamp)

                        self._broadcast_to_all_active_clients_in_room(
                            msg=msg_obj,
                            current_room=client_info.current_room,
                            format_msg=True
                        )

                        self.chat_db.store_message(text_message=msg, sender_name=client_info.username, room_name=client_info.current_room, timestamp=msg_timestamp)

    def _broadcast_to_all_active_clients_in_room(self, *, msg: MessageInfo, current_room: str, format_msg: bool):
        '''
        clients who are connected to the current room gets messages in real-time, and clients
        connected to another room will fetch the messages form db while joining .
        '''
        if clients_in_room := self.room_name_to_active_clients.get(current_room):
            for client in clients_in_room:
                if client.current_room == current_room:
                    msg = msg.formatted_msg() if format_msg else msg.text_message
                    client.client_conn.send(msg.encode('utf-8'))

                print(f"send to {client.username}")

    def _remove_client_in_current_room(self, *, current_room: str, sender_username: str):
        self.room_name_to_active_clients[current_room] = [client for client in self.room_name_to_active_clients[current_room]
                                                          if client.username != sender_username]

    def start(self):
        print("Chat Server started...")
        while True:
            with ThreadPoolExecutor(max_workers=ServerConfig.max_threads_number) as executor:
                client_sock, addr = self.server.accept()
                print(f"Successfully connected client {addr[0]} {addr[1]} to messages server\n")
                executor.submit(self.client_handler, client_sock)

def main():
    chat_server = ChatServer(host='127.0.0.1', listen_port=ServerConfig.listening_port)
    file_transfer_server = FileTransferServer(host='127.0.0.1', listen_port=ServerConfig.file_server_config.listening_port)

    chat_server_thread = threading.Thread(target=chat_server.start, daemon=True)
    chat_server_thread.start()

    file_server_thread = threading.Thread(target=file_transfer_server.start, daemon=True)
    file_server_thread.start()

    chat_server_thread.join()
    file_server_thread.join()


if __name__ == '__main__':
    main()


# todo add some ttl if x not happens in x time
# todo use threadPoolExecutor to chat server
# todo thread = threading.Thread(target=self.client_handler, kwargs={"conn":client_sock})  is it better?


