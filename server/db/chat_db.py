import os
import sqlite3
import typing
from logging import getLogger

from definitions.structs import MessageInfo
from definitions.types import MessageTypes

logger = getLogger(__name__)

class ChatDBConfig:
    db_path: str = os.path.join(os.getcwd(),'db', 'chat.db')

class ChatDB:     #todo contxt manager for opening and closing db??
    def __init__(self):
        self.db_path = ChatDBConfig.db_path
        # self.db = sqlite3.connect(self.db_path)

    def setup_database(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

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

        db.commit()
        db.close()

    def send_previous_messages_in_room(self, *, room_name: str, join_timestamp: typing.Optional[str] = None) -> typing.Generator[str, None, None]:
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        room_id = self.get_room_id_from_rooms(room_name=room_name)

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
                 old_msg_sender = self.get_sender_name_from_users(sender_id=sender_id, cursor=cursor)
                 msg = MessageInfo(type=MessageTypes.CHAT,text_message=text_message, sender_name=old_msg_sender, msg_timestamp=timestamp)
                 yield msg.formatted_msg()  #if stop iteration then send the HISTORY
        else:
            return None

        db.close()

    def store_user(self, *, sender_name: str):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('SELECT username from users WHERE username = ?', (sender_name,))
        username = cursor.fetchone()

        if not username:
            cursor.execute('INSERT INTO users (username) VALUES (?)', (sender_name,))
            db.commit()

        db.close()

    def create_room(self, *, room_name: str):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('SELECT room_name from rooms WHERE room_name = ?', (room_name,))
        record = cursor.fetchone()

        if not record:
            try:
                cursor.execute('INSERT INTO rooms (room_name) VALUES (?)', (room_name,))
                db.commit()
            except sqlite3.IntegrityError:
                logger.exception(f"Room '{room_name}' already exists")

        db.close()

    def store_message(self, *, text_message: str, sender_name: str, room_name: str, timestamp: str):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        sender_id = self.get_sender_id_from_users(sender_name=sender_name, cursor=cursor)
        room_id = self.get_room_id_from_rooms(room_name=room_name)

        cursor.execute('''
           INSERT INTO messages (text_message, sender_id, room_id, timestamp)
           VALUES (?,?,?,?)''', (text_message, sender_id, room_id, timestamp))
        db.commit()
        db.close()

    def create_user_checkin_room(self, *, sender_name: str, room_name: str, join_timestamp: str):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        sender_id = self.get_sender_id_from_users(sender_name=sender_name, cursor=cursor)
        room_id = self.get_room_id_from_rooms(room_name=room_name)

        cursor.execute(
            '''
            INSERT INTO room_checkins (sender_id, room_id, join_timestamp)
            VALUES (?, ?, ?)
            ''',
            (sender_id, room_id, join_timestamp)
        )
        db.commit()
        db.close()

    def get_user_join_timestamp(self, sender_name: str, room_name: str) -> typing.Optional[str]:
        db = sqlite3.connect(self.db_path)
        try:
            cursor = db.cursor()

            sender_id = self.get_sender_id_from_users(sender_name=sender_name, cursor=cursor)
            room_id = self.get_room_id_from_rooms(room_name=room_name)

            cursor.execute(
                'SELECT join_timestamp FROM room_checkins WHERE sender_id = ? AND room_id = ?',
                (sender_id, room_id)
            )
            user_join_timestamp = cursor.fetchone()

            if not user_join_timestamp:
                return None

            return user_join_timestamp[0]

        finally:
            db.close()

    def store_file_in_files(self, *, file_path: str, file_id: str):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('''
               INSERT INTO files (file_path, file_id)
               VALUES (?,?)''', (file_path, file_id))
        db.commit()
        db.close()

    def get_file_path_by_file_id(self, *, file_id: str) -> typing.Optional[str]:
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()
        try:
            cursor.execute('SELECT file_path FROM files WHERE file_id = ?', (file_id,))
            record = cursor.fetchone()
            if record:
                return record[0]
            return None

        finally:
            db.close()

    @staticmethod
    def get_sender_id_from_users(*, sender_name: str, cursor: sqlite3.Cursor) -> int:
        cursor.execute('SELECT id FROM users where username = ?', (sender_name,))
        return cursor.fetchone()[0]

    @staticmethod
    def get_sender_name_from_users(*, sender_id: int , cursor: sqlite3.Cursor) -> typing.Optional[str]:
        cursor.execute('SELECT username FROM users where id = ?', (sender_id,))
        record = cursor.fetchone()
        if record:
            return record[0]

        return None

    def get_room_id_from_rooms(self, *, room_name: str) -> typing.Optional[int]:
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('SELECT id FROM rooms WHERE room_name = ?', (room_name,))
        record = cursor.fetchone()
        try:
            if record:
                return record[0]
            return None

        finally:
            db.close()

