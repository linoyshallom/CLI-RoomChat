import os
import socket
import sqlite3
import typing
from utils import MessageInfo

END_HISTORY_RETRIEVAL = "END_HISTORY_RETRIEVAL"

class ChatDBConfig:
    db_path: str = os.path.join(os.path.dirname(__file__), 'db', 'chat.db')

class ChatDB:
    def __init__(self):
        self.db_path = ChatDBConfig.db_path

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
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            file_id TEXT NOT NULL
            );
        ''')

        db.commit()
        db.close()

    def send_previous_messages_in_room(self, *, conn: socket.socket, room_name: str, join_timestamp: typing.Optional[str] = None):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        room_id = ChatDB.get_room_id_from_rooms(room_name=room_name, cursor=cursor)
        print(f"room name: {room_name}, room id {room_id}, joined timestamp {join_timestamp}")

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

        print(f"fetch : {cursor.fetchall()} ")
        if old_messages := cursor.fetchall():
            print("old messages section")
            for text_message, sender_id, timestamp in old_messages:
                 old_msg_sender = ChatDB.get_sender_name_from_users(sender_id=sender_id, cursor=cursor)
                 msg = MessageInfo(text_message=text_message, sender_name=old_msg_sender, msg_timestamp=timestamp)
                 print(f"msg {msg}")
                 conn.send(msg.formatted_msg().encode('utf-8'))
                #sleep?

        else:
            conn.send("No messages in this chat yet ...".encode('utf-8'))

        conn.send(END_HISTORY_RETRIEVAL.encode())

        db.close()

    def store_user(self, *, sender_name: str):  #todo if exist do not increase the id
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('INSERT OR IGNORE INTO users (username) VALUES (?)', (sender_name,))
        db.commit()
        db.close()

    def create_room(self, *, room_name: str): #todo if exist do not increase the id
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('INSERT OR IGNORE INTO rooms (room_name) VALUES (?)', (room_name,))
        db.commit()
        db.close()

    def store_message(self, *, text_message: str, sender_name: str, room_name: str, timestamp: str):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        sender_id = ChatDB.get_sender_id_from_users(sender_name=sender_name, cursor=cursor)
        room_id = ChatDB.get_room_id_from_rooms(room_name=room_name, cursor=cursor)

        cursor.execute('''
           INSERT INTO messages (text_message, sender_id, room_id, timestamp)
           VALUES (?,?,?,?)''', (text_message, sender_id, room_id, timestamp))
        db.commit()
        db.close()

    def store_file(self, *, file_path: str, file_id: str):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('''
            INSERT INTO messages (file_path, file_id)
            VALUES (?,?,?,?)''', (file_path, file_id))
        db.commit()
        db.close()

    def file_path_by_file_id(self, *, file_id: str) -> str:
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()
        cursor.execute('SELECT file_path FROM files WHERE file_id = ?', (file_id,))
        return cursor.fetchone()[0]

    @staticmethod
    def get_sender_id_from_users(*, sender_name: str, cursor) -> int:  # check if I need to validate return value not None else raise ValueError don't exist
        cursor.execute('SELECT id FROM users where username = ?', (sender_name,))
        return cursor.fetchone()[0]

    @staticmethod
    def get_sender_name_from_users(*, sender_id: int , cursor) -> str:  # check if I need to validate return value not None else raise ValueError don't exist
        cursor.execute('SELECT username FROM users where id = ?', (sender_id,))
        return cursor.fetchone()[0]

    @staticmethod
    def get_room_id_from_rooms(*, room_name: str, cursor: sqlite3.Cursor) -> int:
        cursor.execute('SELECT id FROM rooms WHERE room_name = ?', (room_name,))
        return cursor.fetchone()[0]

def main():
    db = sqlite3.connect(ChatDBConfig.db_path)
    cursor = db.cursor()

    cursor.execute('''
              SELECT text_message, sender_id, timestamp FROM messages
               WHERE room_id = ? 
               ORDER BY timestamp ASC
               ''', (10,))
    print(cursor.fetchall())


if __name__ == "__main__":
    main()