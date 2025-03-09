import datetime
import os
import sqlite3
import time
import typing

from pyexpat.errors import messages

from server.server_config import ServerConfig
# from datetime import datetime, timedelta
# from server.config import ServerConfig

END_HISTORY_RETRIEVAL = "END_HISTORY_RETRIEVAL"

class ChatDB:
    def __init__(self, *, db_path: str):
        self.db_path =db_path

    def setup_database(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True) #  create a directory if doesn't exist
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
        db.commit()
        db.close()

    def send_previous_messages_in_room(self, conn, room_name: str, join_timestamp: typing.Optional[str] = None):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        room_id = ChatDB.get_room_id_from_rooms(room_name, cursor)
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

        if old_messages := cursor.fetchall():
            for text_message, sender_id, timestamp in old_messages:
                old_msg_sender = ChatDB.get_user_name_from_users(sender_id, cursor)
                # final_msg = f"[{timestamp}] [{old_msg_sender}]: {text_message}"
                final_msg = ServerConfig.message_pattern.format(
                    msg_timestamp=timestamp, sender_name=old_msg_sender, message=text_message
                )
                #CHECK
                print(final_msg)
                conn.send(final_msg.encode('utf-8'))
                time.sleep(0.01)
        else:
            conn.send("No messages in this chat yet ...".encode('utf-8'))

        conn.send(END_HISTORY_RETRIEVAL.encode())

        db.close()

    def store_user(self,username):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('INSERT OR IGNORE INTO users (username) VALUES (?)', (username,))
        db.commit()
        db.close()

        # check if user is None conn.send() to user to write again

    def store_message(self, text_message, username, room_name, timestamp):  # not sent to db as well
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        sender_id = ChatDB.get_user_id_from_users(username, cursor)
        room_id = ChatDB.get_room_id_from_rooms(room_name, cursor)

        cursor.execute('''
           INSERT INTO messages (text_message, sender_id, room_id, timestamp)
           VALUES (?,?,?,?)''', (text_message, sender_id, room_id, timestamp))
        db.commit()
        db.close()

    def create_room(self,room_name):
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()

        cursor.execute('INSERT OR IGNORE INTO rooms (room_name) VALUES (?)', (room_name,))
        db.commit()
        db.close()

    @staticmethod
    def get_user_id_from_users(username, cursor) -> int:  # check if i need to validate return value not None else raise ValueError don't exist
        cursor.execute('SELECT id FROM users where username = ?', (username,))
        return cursor.fetchone()[0]

    @staticmethod
    def get_user_name_from_users(user_id, cursor) -> int:  # check if i need to validate return value not None else raise ValueError don't exist
        cursor.execute('SELECT username FROM users where id = ?', (user_id,))
        return cursor.fetchone()[0]

    @staticmethod
    def get_room_id_from_rooms(room_name, cursor) -> int:
        cursor.execute('SELECT id FROM rooms WHERE room_name = ?', (room_name,))
        return cursor.fetchone()[0]

def main():
    ...
    # chat_db = ChatDB(db_path=ServerConfig.db_path)
    # chat_db.setup_database()

    # sqlite3.register_adapter(datetime , lambda dt: dt.strftime("%Y-%m-%d %H:%M:%S"))
    # sqlite3.register_converter("DATETIME", lambda s: datetime.datetime.strptime(s.decode(), "%Y-%m-%d %H:%M:%S"))
    #
    # db = sqlite3.connect('chat.db')
    # cursor = db.cursor()
    # ChatDB.setup_database()
    #
    # cursor.execute('''
    #           SELECT text_message, sender_id, timestamp FROM messages
    #            WHERE room_id = ?
    #            AND timestamp > ?
    #            ORDER BY timestamp ASC
    #            ''', (1, datetime.now() - timedelta(hours=2)))
    #
    # if old_messages := cursor.fetchall():
    #     for text_message, sender_id, timestamp in old_messages:
    #         old_msg_sender = ChatDB.get_user_name_from_users(sender_id, cursor)
    #         final_msg = f"[{timestamp}] [{old_msg_sender}]: {text_message}"
    #         print(final_msg)
    #         time.sleep(0.01)
    # else:
    #     print("No messages in this chat yet ...".encode('utf-8'))


if __name__ == "__main__":
    main()