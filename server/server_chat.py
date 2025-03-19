import datetime
import json
import socket
import threading
import typing
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from config.config import MessageServerConfig
from definitions.structs import ClientInfo, MessageInfo, SetupRoomData
from definitions.types import RoomTypes, MessageTypes
from server.db.chat_db import ChatDB


class ChatServer:
    def __init__(self, *, host, listen_port):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.server.bind((host, listen_port))
        except Exception as e:
            print(f"Unable to bind to host and port : {repr(e)}")

        self.server.listen(MessageServerConfig.listener_limit_number)

        self.active_clients: typing.Set[ClientInfo] = set()
        self.room_name_to_active_clients: typing.DefaultDict[str, typing.List[ClientInfo]] = defaultdict(list)

        self.chat_db = ChatDB()
        self.chat_db.setup_database()

        self.room_setup_done_flag = threading.Event()

    def client_handler(self, conn: socket.socket):
        sender_name = conn.recv(1024).decode('utf-8')
        print(f"server got username {sender_name}")
        self.chat_db.store_user(sender_name=sender_name.strip())
        print("done storing use in db")

        client_info = ClientInfo(client_conn=conn, username=sender_name)

        room_setup_thread = threading.Thread(target=self._setup_room, args=(conn, client_info))
        room_setup_thread.start()

        # Listen for massages after setup thread finished
        received_messages_thread = threading.Thread(target=self._receive_messages, args=(conn, client_info,))
        received_messages_thread.start()

    def _setup_room(self, conn: socket.socket, client_info: ClientInfo):   #todo should not be a thread?
        json_data = conn.recv(1024).decode('utf-8')
        setup_room_data = SetupRoomData(**json.loads(json_data))
        print(setup_room_data)
        room_type = setup_room_data.room_type
        print(f"room type {room_type}")

        if RoomTypes[room_type.upper()] == RoomTypes.PRIVATE:
            join_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            group_name = setup_room_data.group_name
            print(f"group name {group_name}")
            self._private_room_setup_handler(conn=conn, username=client_info.username, join_timestamp=join_timestamp, group_name=group_name)
        else:
            group_name = room_type
            self._global_room_setup_handler(conn=conn, group_name=group_name)

        client_info.room_type = RoomTypes(room_type.upper())
        client_info.current_room = group_name
        self.room_name_to_active_clients[group_name].append(client_info)

        msg_obj = MessageInfo( type=MessageTypes.SYSTEM, text_message=f"{client_info.username} joined {group_name}")
        self._broadcast_to_all_active_clients_in_room(msg=msg_obj, current_room=client_info.current_room)

        client_info.room_setup_done_flag.set()
        print(f"finish room setup")

    def _private_room_setup_handler(self, *, conn, username, join_timestamp, group_name):
        room_id = self.chat_db.get_room_id_from_rooms(room_name=group_name)

        user_join_timestamp = self.chat_db.get_user_join_timestamp(
            sender_name=username,
            room_name=group_name
        )
        # If room still not exist , then add to checkins table
        if not room_id:
            self.chat_db.create_room(room_name=group_name)
            user_join_timestamp = join_timestamp
            self.chat_db.create_user_checkin_room(sender_name=username, room_name=group_name, join_timestamp=user_join_timestamp)

        # If room exists but user haven't checkin to this room yet
        if not user_join_timestamp:
            user_join_timestamp = join_timestamp
            self.chat_db.create_user_checkin_room(sender_name=username, room_name=group_name, join_timestamp=user_join_timestamp)

        # Users in private rooms will get only messages came after their first joining group timestamp
        self._fetch_history_messages(conn=conn, group_name=group_name, join_timestamp=user_join_timestamp)

    def _global_room_setup_handler(self, *, conn, group_name):
        self.chat_db.create_room(room_name=group_name)
        self._fetch_history_messages(conn=conn, group_name=group_name)

    def _fetch_history_messages(self, *, conn: socket.socket, group_name: str, join_timestamp: typing.Optional[str] = None):
        if join_timestamp:
            messages_from_db = self.chat_db.send_previous_messages_in_room(room_name=group_name, join_timestamp=join_timestamp)
        else:
            messages_from_db = self.chat_db.send_previous_messages_in_room(room_name=group_name)

        try:
            msg = next(messages_from_db)
            print(f"{msg} from db")
            conn.send(msg.encode('utf-8'))

            for msg in iter(messages_from_db):
                conn.send(msg.encode('utf-8'))

        except StopIteration:
            print("no messages in this room")
            conn.send("No messages in this chat yet ...".encode('utf-8'))

    def _receive_messages(self, conn, client_info: ClientInfo):
        client_info.room_setup_done_flag.wait()

        while True:
            if msg := conn.recv(2048).decode('utf-8'):
                if msg == '/switch':
                    client_info.room_setup_done_flag.clear() #clear flag so all messages send to the setup from this time

                    self._remove_client_in_current_room(current_room=client_info.current_room, sender_username=client_info.username)

                    msg_obj = MessageInfo( type=MessageTypes.SYSTEM, text_message=f"{client_info.username} left {client_info.current_room}")
                    self._broadcast_to_all_active_clients_in_room(
                        msg= msg_obj,
                        current_room=client_info.current_room
                    )

                    print(f"removing client mapping: {self.room_name_to_active_clients}")
                    self._setup_room(conn, client_info)

                else:
                    print(f"got message {msg}")
                    msg_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    msg_obj = MessageInfo(type=MessageTypes.CHAT, text_message=msg, sender_name=client_info.username, msg_timestamp=msg_timestamp)

                    self._broadcast_to_all_active_clients_in_room(
                        msg=msg_obj,
                        current_room=client_info.current_room
                    )

                    self.chat_db.store_message(text_message=msg, sender_name=client_info.username, room_name=client_info.current_room, timestamp=msg_timestamp)

    def _broadcast_to_all_active_clients_in_room(self, *, msg: MessageInfo, current_room: str):
        #clients who are connected to the current room gets messages in real-time, and clients
        #connected to another room will fetch the messages from db while joining .

        if clients_in_room := self.room_name_to_active_clients.get(current_room):
            for client in clients_in_room:

                if client.current_room == current_room:
                    final_msg = msg.formatted_msg()
                    client.client_conn.send(final_msg.encode('utf-8'))

                print(f"send msg to {client.username}")

    def _remove_client_in_current_room(self, *, current_room: str, sender_username: str):
        self.room_name_to_active_clients[current_room] = [
            client for client in self.room_name_to_active_clients[current_room] if client.username != sender_username
        ]

    def start(self):
        print("Chat Server started...")
        while True:
            with ThreadPoolExecutor(max_workers=1) as executor:
                client_sock, addr = self.server.accept()
                print(f"Successfully connected client {addr[0]} {addr[1]} to messages server\n")
                executor.submit(self.client_handler, client_sock)

def main():
    chat_server = ChatServer(host='127.0.0.1', listen_port=MessageServerConfig.listening_port)
    chat_server.start()

if __name__ == '__main__':
    main()


