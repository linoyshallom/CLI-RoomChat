import datetime
import json
import logging
import socket
import sqlite3
import threading
import time
import typing
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from logging import getLogger

from config import MessageServerConfig, END_OF_MSG_INDICATOR
from definitions import ClientInfo, MessageInfo, SetupRoomData, RoomTypes, MessageTypes
from server.db.chat_db import ChatDB

logger = getLogger(__name__)

class ChatServer:
    def __init__(self, *, host: str, listen_port: int):
        self._chat_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._chat_server.bind((host, listen_port))
        except Exception as e:
            logger.exception(f"Unable to bind to host and port : {repr(e)}")

        self._chat_server.listen(MessageServerConfig.listener_limit_number)

        self.active_clients: typing.Set[ClientInfo] = set()
        self.room_name_to_active_clients: typing.DefaultDict[str, typing.List[ClientInfo]] = defaultdict(list)

        self.chat_db = ChatDB()

        self.room_setup_done_flag = threading.Event()

    @property
    def chat_server(self) -> socket.socket:
        return self._chat_server

    def client_handler(self, conn: socket.socket):
        sender_name = conn.recv(1024).decode('utf-8')

        with self.chat_db.session() as db_conn:
            self.chat_db.setup_database(db_conn=db_conn)
            self.chat_db.store_user(db_conn=db_conn, sender_name=sender_name.strip())

        client_info = ClientInfo(client_conn=conn, username=sender_name)

        room_setup_thread = threading.Thread(target=self._setup_room, args=(conn, client_info))
        room_setup_thread.start()

        # Listen for chat massages after setup thread has finished
        received_messages_thread = threading.Thread(target=self._receive_messages, args=(conn, client_info,))
        received_messages_thread.start()

    def _setup_room(self, conn: socket.socket, client_info: ClientInfo) -> None:
        json_data = conn.recv(1024).decode('utf-8')
        setup_room_data = SetupRoomData(**json.loads(json_data))

        room_type = setup_room_data.room_type

        if RoomTypes[room_type.upper()] == RoomTypes.PRIVATE:
            join_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            group_name = setup_room_data.group_name
            self._private_room_setup_handler(conn=conn, username=client_info.username, join_timestamp=join_timestamp, group_name=group_name)

        else:
            group_name = room_type
            self._global_room_setup_handler(conn=conn, group_name=group_name)

        client_info.room_type = RoomTypes(room_type.upper())
        client_info.current_room = group_name
        self.room_name_to_active_clients[group_name].append(client_info)

        client_info.room_setup_done_flag.set()

        time.sleep(0.1)  # Ensure displaying joining msg after fetching messages from db (I know that's weird, just for displaying)
        msg_obj = MessageInfo( type=MessageTypes.SYSTEM, text_message=f"{client_info.username} joined '{group_name}' group")
        self._broadcast_to_all_active_clients_in_room(msg=msg_obj, current_room=client_info.current_room)

    def _private_room_setup_handler(self, *, conn: socket.socket, username: str, join_timestamp: str, group_name: str) -> None:
        with self.chat_db.session() as db_conn:
            room_id = self.chat_db.get_room_id_from_rooms(db_conn=db_conn, room_name=group_name)

            user_join_timestamp = self.chat_db.get_user_join_timestamp(
                db_conn=db_conn,
                sender_name=username,
                room_name=group_name
            )
            # If room still not exist, then create and add to 'checkin_room' table
            if not room_id:
                self.chat_db.create_room(db_conn=db_conn, room_name=group_name)
                user_join_timestamp = join_timestamp
                self.chat_db.create_user_checkin_room(db_conn=db_conn, sender_name=username, room_name=group_name, join_timestamp=user_join_timestamp)

            # If room exists but user haven't checkin to this room yet
            if not user_join_timestamp:
                user_join_timestamp = join_timestamp
                self.chat_db.create_user_checkin_room(db_conn=db_conn, sender_name=username, room_name=group_name, join_timestamp=user_join_timestamp)

            # Users in private rooms will get only messages came after their first joining group timestamp
            self._fetch_history_messages(conn=conn, db_conn=db_conn, group_name=group_name, join_timestamp=user_join_timestamp)

    def _global_room_setup_handler(self, *, conn: socket.socket, group_name: str) -> None:
        with self.chat_db.session() as db_conn:
            self.chat_db.create_room(db_conn=db_conn, room_name=group_name)
            self._fetch_history_messages(conn=conn, db_conn=db_conn, group_name=group_name)

    def _fetch_history_messages(self, *, conn: socket.socket, db_conn: sqlite3.Connection, group_name: str, join_timestamp: typing.Optional[str] = None) -> None:
        formated_messages_from_db = self.chat_db.send_previous_messages_in_room(db_conn=db_conn, room_name=group_name, join_timestamp=join_timestamp)

        first_msg = next(formated_messages_from_db, None)

        if not first_msg:
            msg_obj = MessageInfo(type=MessageTypes.SYSTEM, text_message=f"No messages in this chat yet ...{END_OF_MSG_INDICATOR}")
            conn.send((msg_obj.formatted_msg()).encode('utf-8'))

        else:
            msg_with_indicator = first_msg + END_OF_MSG_INDICATOR
            conn.send(msg_with_indicator.encode('utf-8'))

            for msg in formated_messages_from_db:
                msg_with_indicator = msg + END_OF_MSG_INDICATOR
                conn.send(msg_with_indicator.encode('utf-8'))

    def _receive_messages(self, conn: socket.socket, client_info: ClientInfo) -> None:
        client_info.room_setup_done_flag.wait()

        while True:
            if msg := conn.recv(2048).decode('utf-8'):
                if msg == '/switch':
                    client_info.room_setup_done_flag.clear() # Clear flag so all messages will be sent to the setup from this time

                    self._remove_client_in_current_room(current_room=client_info.current_room, sender_username=client_info.username)

                    msg_obj = MessageInfo( type=MessageTypes.SYSTEM, text_message=f"{client_info.username} disconnected from '{client_info.current_room}'")
                    self._broadcast_to_all_active_clients_in_room(
                        msg= msg_obj,
                        current_room=client_info.current_room
                    )

                    self._setup_room(conn, client_info)

                else:
                    msg_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    msg_obj = MessageInfo(type=MessageTypes.CHAT, text_message=msg, sender_name=client_info.username, msg_timestamp=msg_timestamp)

                    self._broadcast_to_all_active_clients_in_room(
                        msg=msg_obj,
                        current_room=client_info.current_room
                    )

                    with self.chat_db.session() as db_conn:
                        self.chat_db.store_message(db_conn=db_conn, text_message=msg, sender_name=client_info.username, room_name=client_info.current_room, timestamp=msg_timestamp)

    def _broadcast_to_all_active_clients_in_room(self, *, msg: MessageInfo, current_room: str) -> None:
        #clients who are connected to the client current room gets messages in real-time, and clients
        #connected to another room will fetch the messages from db while joining . e.g. chat, joining chat, leaving chat messages ...
        if clients_in_room := self.room_name_to_active_clients.get(current_room):
            for client in clients_in_room:
                final_msg = msg.formatted_msg() + END_OF_MSG_INDICATOR
                client.client_conn.send(final_msg.encode('utf-8'))

    def _remove_client_in_current_room(self, *, current_room: str, sender_username: str) -> None:
        self.room_name_to_active_clients[current_room] = [
            client for client in self.room_name_to_active_clients[current_room] if client.username != sender_username
        ]

    def start(self):
        print("Chat Server started...")
        while True:
            with ThreadPoolExecutor(max_workers=1) as executor:
                client_sock, addr = self.chat_server.accept()
                logger.info(f"Successfully connected client {addr[0]} {addr[1]} to messages server\n")
                executor.submit(self.client_handler, client_sock)

def main():
    chat_server = ChatServer(host='127.0.0.1', listen_port=MessageServerConfig.listening_port)
    chat_server.start()

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    main()


