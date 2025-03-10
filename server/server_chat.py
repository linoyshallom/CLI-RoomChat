import socket
import threading
import typing
from collections import defaultdict
from datetime import datetime

from client.client_chat import ClientInfo
from server.db.chat_db import ChatDB
from server_config import ServerConfig
from utils import RoomTypes
from server_file_transfer import FileTransferServer


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

    def client_handler(self, conn):
        print(f"conn type {type(conn)}")  #CHECK
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
                #manage room-users-timestamp table if user exist in this room then I will take its join timestamp, else I will take from db
                user_join_timestamp = conn.recv(1024).decode('utf-8')
                client_info.user_joined_timestamp = user_join_timestamp
                print(f"user join to room timestamp {user_join_timestamp}, {type(user_join_timestamp)}")

                self.chat_db.create_room(room_name=group_name)
                self.chat_db.send_previous_messages_in_room(conn=client_info.client_conn, room_name=group_name, join_timestamp=user_join_timestamp)

            else:
                group_name = room_type
                self.chat_db.create_room(room_name=group_name)
                self.chat_db.send_previous_messages_in_room(conn=client_info.client_conn, room_name=group_name)

            client_info.room_type = room_type
            client_info.current_room = group_name
            self.room_name_to_active_clients[group_name].append(client_info)

            self.room_setup_done_flag.set()
            print(f"set setup flag")
            print(f"client in setup: {client_info}")
            print(f"mapping room to clients: {self.room_name_to_active_clients}")

            break

    def _receiving_messages(self, conn, client_info: ClientInfo):
        while True:
                self.room_setup_done_flag.wait()

                if msg := conn.recv(2048).decode('utf-8'):
                    if msg == '/switch':
                        self.room_setup_done_flag.clear() #clear set so all messages send to the setup from this time
                        print(f"clear setup flag ")

                        self._remove_client_in_current_room(current_room=client_info.current_room, sender_username=client_info.username)

                        self._broadcast_to_all_active_clients_in_room(
                            msg=f"{client_info.username} left {client_info.current_room}",
                            current_room=client_info.current_room,
                            sender_name=client_info.username,
                            pattern=False
                        )

                        print(f"removing client mapping: {self.room_name_to_active_clients}")
                        self._room_setup(conn, client_info)

                    else:
                        print(f"got message {msg}")
                        msg_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                        self._broadcast_to_all_active_clients_in_room(
                            msg=msg,
                            current_room=client_info.current_room,
                            sender_name=client_info.username,
                            msg_timestamp=msg_timestamp
                        )

                        self.chat_db.store_message(text_message=msg, sender_name=client_info.username, room_name=client_info.current_room, timestamp=msg_timestamp)

    def _broadcast_to_all_active_clients_in_room(self, *, msg: str, current_room: str, sender_name: str, msg_timestamp: typing.Optional[str] = None, pattern:typing.Optional[bool] = True):
        if clients_in_room := self.room_name_to_active_clients.get(current_room):
            final_msg = msg
            for client in clients_in_room:
                if client.current_room == current_room:
                    if pattern:
                        final_msg = ServerConfig.message_pattern.format(
                            msg_timestamp=msg_timestamp, sender_name=sender_name, message=msg
                        )
                    client.client_conn.send(final_msg.encode('utf-8'))
                    print(f"send to {client.username}")

    def _remove_client_in_current_room(self, *, current_room: str, sender_username: str):
        self.room_name_to_active_clients[current_room] = [client for client in self.room_name_to_active_clients[current_room]
                                                          if client.username != sender_username]

    def start(self):
        print("Chat Server started...")
        while True:
            client_sock, addr = self.server.accept()
            print(f"Successfully connected client {addr[0]} {addr[1]} to messages server")
            thread = threading.Thread(target=self.client_handler, args=(client_sock,))
            thread.start()

def main():
    chat_server = ChatServer(host='127.0.0.1', listen_port=2)
    chat_server.start()

    # file_transfer_server = FileTransferServer(host='127.0.0.1', listen_port=3)
    # file_transfer_server.start()


if __name__ == '__main__':
    main()



# todo add some ttl if x not happens in x time
# todo use threadPoolExecutor to chat server

# thread = threading.Thread(target=self.client_handler, kwargs={"conn":client_sock})  #is it better?

#notes
# add note that users in private will get only messages came after his join timestamps
# users in global get all messages ever written
# broadcast is for users that connect to the same room so they will fetch messages real-time instead of fetching from db

