import os
import sqlite3
import typing
from logging import getLogger

from definitions import MessageInfo, MessageTypes
from contextlib import contextmanager

logger = getLogger(__name__)

class ChatDBConfig:
    db_path: str = os.path.join(os.getcwd(),'db', 'chat.db')

class ChatDB:
    def __init__(self):
        self.db_path = ChatDBConfig.db_path

    @contextmanager
    def session(self):
        connection = sqlite3.connect(self.db_path)
        try:
            yield connection
        finally:
            connection.commit()
            connection.close()

    def setup_database(self, db_conn: sqlite3.Connection):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        cursor = db_conn.cursor()

        cursor.execute('''
           CREATE TABLE IF NOT EXISTS users (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               username TEXT UNIQUE NOT NULL
               );
           ''')

        cursor.execute('''
           CREATE TABLE IF NOT EXISTS rooms (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               room_name TEXT UNIQUE NOT NULL
               );
           ''')

        cursor.execute('''
           CREATE TABLE IF NOT EXISTS messages (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               text_message TEXT NOT NULL,
               sender_id INTEGER NOT NULL,
               room_id INTEGER NOT NULL,
               timestamp DATETIME NOT NULL,
               FOREIGN KEY (sender_id) REFERENCES users(id), 
               FOREIGN KEY (room_id) REFERENCES rooms(id) 
               );
           ''')

        cursor.execute('''
             CREATE TABLE IF NOT EXISTS room_checkins (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 sender_id INTEGER NOT NULL,
                 room_id INTEGER NOT NULL,
                 join_timestamp DATETIME NOT NULL,
                 FOREIGN KEY (sender_id) REFERENCES users(id), 
                 FOREIGN KEY (room_id) REFERENCES rooms(id) 
                 );
             ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            file_id TEXT NOT NULL
            );
        ''')

    @classmethod
    def send_previous_messages_in_room(cls, *, db_conn: sqlite3.Connection, room_name: str, join_timestamp: typing.Optional[str] = None) -> typing.Generator[str, None, None]:
        cursor = db_conn.cursor()

        room_id = cls.get_room_id_from_rooms(db_conn=db_conn, room_name=room_name)

        if join_timestamp:
            cursor.execute('''
              SELECT text_message, sender_id, timestamp FROM messages
               WHERE room_id = ? 
               AND timestamp > ? 
               ORDER BY timestamp ASC
               ''', (room_id, join_timestamp))

        else:
            cursor.execute('''
                 SELECT text_message, sender_id, timestamp FROM messages
                  WHERE room_id = ? 
                  ORDER BY timestamp ASC
                  ''', (room_id,))

        if old_messages := cursor.fetchall():
            for text_message, sender_id, timestamp in old_messages:
                 old_msg_sender = cls._get_sender_name_from_users(sender_id=sender_id, cursor=cursor)
                 msg = MessageInfo(type=MessageTypes.CHAT,text_message=text_message, sender_name=old_msg_sender, msg_timestamp=timestamp)
                 yield msg.formatted_msg()
        else:
            return None

    @classmethod
    def store_user(cls, *, db_conn: sqlite3.Connection, sender_name: str):
        cursor = db_conn.cursor()

        cursor.execute('SELECT username from users WHERE username = ?', (sender_name,))
        username = cursor.fetchone()

        if not username:
            cursor.execute('INSERT INTO users (username) VALUES (?)', (sender_name,))

    @classmethod
    def create_room(cls, *, db_conn: sqlite3.Connection, room_name: str):
        cursor = db_conn.cursor()
        cursor.execute('INSERT INTO rooms (room_name) VALUES (?) ON CONFLICT(room_name) DO NOTHING', (room_name,))

    @classmethod
    def store_message(cls, *, db_conn: sqlite3.Connection, text_message: str, sender_name: str, room_name: str, timestamp: str):
        cursor = db_conn.cursor()

        sender_id = cls._get_sender_id_from_users(sender_name=sender_name, cursor=cursor)
        room_id = cls.get_room_id_from_rooms(db_conn=db_conn, room_name=room_name)

        cursor.execute('''
           INSERT INTO messages (text_message, sender_id, room_id, timestamp)
           VALUES (?,?,?,?)''', (text_message, sender_id, room_id, timestamp))

    @classmethod
    def create_user_checkin_room(cls, *, db_conn: sqlite3.Connection, sender_name: str, room_name: str, join_timestamp: str):
        cursor = db_conn.cursor()

        sender_id = cls._get_sender_id_from_users(sender_name=sender_name, cursor=cursor)
        room_id = cls.get_room_id_from_rooms(db_conn=db_conn, room_name=room_name)

        cursor.execute(
            '''
            INSERT INTO room_checkins (sender_id, room_id, join_timestamp)
            VALUES (?, ?, ?)
            ''',
            (sender_id, room_id, join_timestamp)
        )

    @classmethod
    def get_user_join_timestamp(cls, *, db_conn: sqlite3.Connection, sender_name: str, room_name: str) -> typing.Optional[str]:
        cursor = db_conn.cursor()

        sender_id = cls._get_sender_id_from_users(sender_name=sender_name, cursor=cursor)
        room_id = cls.get_room_id_from_rooms(db_conn=db_conn, room_name=room_name)

        cursor.execute(
            'SELECT join_timestamp FROM room_checkins WHERE sender_id = ? AND room_id = ?',
            (sender_id, room_id)
        )
        user_join_timestamp = cursor.fetchone()

        if not user_join_timestamp:
            return None
        return user_join_timestamp[0]

    @classmethod
    def store_file_in_files(cls, *, db_conn: sqlite3.Connection, file_path: str, file_id: str):
        cursor = db_conn.cursor()
        cursor.execute('''
               INSERT INTO files (file_path, file_id)
               VALUES (?,?)''', (file_path, file_id))

    @classmethod
    def get_file_path_by_file_id(cls, *, db_conn: sqlite3.Connection, file_id: str) -> typing.Optional[str]:
        cursor = db_conn.cursor()
        cursor.execute('SELECT file_path FROM files WHERE file_id = ?', (file_id,))
        record = cursor.fetchone()
        if record:
            return record[0]
        return None

    @classmethod
    def get_room_id_from_rooms(cls, *, db_conn: sqlite3.Connection, room_name: str) -> typing.Optional[int]:
        cursor = db_conn.cursor()

        cursor.execute('SELECT id FROM rooms WHERE room_name = ?', (room_name,))
        record = cursor.fetchone()

        if record:
            return record[0]
        return None

    @classmethod
    def _get_sender_id_from_users(cls, *, sender_name: str, cursor: sqlite3.Cursor) -> int:
        cursor.execute('SELECT id FROM users where username = ?', (sender_name,))
        return cursor.fetchone()[0]

    @classmethod
    def _get_sender_name_from_users(cls, *, sender_id: int, cursor: sqlite3.Cursor) -> typing.Optional[str]:
        cursor.execute('SELECT username FROM users where id = ?', (sender_id,))
        record = cursor.fetchone()
        if record:
            return record[0]
        return None

