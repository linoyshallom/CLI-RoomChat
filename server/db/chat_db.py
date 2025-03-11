import os
import sqlite3
import time
import typing

from server.server_config import ServerConfig

END_HISTORY_RETRIEVAL = "END_HISTORY_RETRIEVAL"

class ChatDB:
    def __init__(self, *, db_path: str):
        self.db_path =db_path

    def setup_database(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True) # create a directory f doesn't exist
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

        db.commit()
        db.close()

    def send_previous_messages_in_room(self, conn, room_name: str, join_timestamp: typing.Optional[str] = None):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        room_id = ChatDB.get_room_id_from_rooms(room_name=room_name, cursor=cursor)

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
                old_msg_sender = ChatDB.get_sender_name_from_users(sender_id=sender_id, cursor=cursor)
                final_msg = ServerConfig.message_pattern.format(
                    msg_timestamp=timestamp, sender_name=old_msg_sender, message=text_message
                )
                conn.send(final_msg.encode('utf-8'))
                time.sleep(0.01)
        else:
            conn.send("No messages in this chat yet ...".encode('utf-8'))

        conn.send(END_HISTORY_RETRIEVAL.encode())

        db.close()

    def store_user(self, *, sender_name):  #todo if exist do not increase the id
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('INSERT OR IGNORE INTO users (username) VALUES (?)', (sender_name,))
        db.commit()
        db.close()

    def create_room(self, *, room_name): #todo if exist do not increase the id
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('INSERT OR IGNORE INTO rooms (room_name) VALUES (?)', (room_name,))
        db.commit()
        db.close()

    def store_message(self, *, text_message:str, sender_name:str, room_name:str, timestamp:str):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        sender_id = ChatDB.get_sender_id_from_users(sender_name=sender_name, cursor=cursor)
        room_id = ChatDB.get_room_id_from_rooms(room_name=room_name, cursor=cursor)

        cursor.execute('''
           INSERT INTO messages (text_message, sender_id, room_id, timestamp)
           VALUES (?,?,?,?)''', (text_message, sender_id, room_id, timestamp))
        db.commit()
        db.close()

    def get_user_join_timestamp(self, sender_name: str, room_name: str, join_timestamp: str) -> typing.Optional[str]:
        db = sqlite3.connect(self.db_path)
        try:
            cursor = db.cursor()

            sender_id = ChatDB.get_sender_id_from_users(sender_name=sender_name, cursor=cursor)
            room_id = ChatDB.get_room_id_from_rooms(room_name=room_name, cursor=cursor)

            cursor.execute(
                'SELECT join_timestamp FROM room_checkins WHERE sender_id = ? AND room_id = ?',
                (sender_id, room_id)
            )
            user_join_timestamp = cursor.fetchone()

            # If no join_timestamp exists, insert a new row with the input timestamp
            if not user_join_timestamp:
                cursor.execute(
                    '''
                    INSERT INTO room_checkins (sender_id, room_id, join_timestamp)
                    VALUES (?, ?, ?)
                    ''',
                    (sender_id, room_id, join_timestamp)
                )
                db.commit()
                return join_timestamp

            return user_join_timestamp[0]

        finally:
            db.close()


    @staticmethod
    def get_sender_id_from_users(*, sender_name:str, cursor) -> int:  # check if I need to validate return value not None else raise ValueError don't exist
        cursor.execute('SELECT id FROM users where username = ?', (sender_name,))
        return cursor.fetchone()[0]

    @staticmethod
    def get_sender_name_from_users(*, sender_id:int , cursor) -> int:  # check if I need to validate return value not None else raise ValueError don't exist
        cursor.execute('SELECT username FROM users where id = ?', (sender_id,))
        return cursor.fetchone()[0]

    @staticmethod
    def get_room_id_from_rooms(*, room_name: str, cursor) -> int:   #CHECK cursor type
        cursor.execute('SELECT id FROM rooms WHERE room_name = ?', (room_name,))
        return cursor.fetchone()[0]
