import os
import sqlite3
import threading
import typing
from contextlib import contextmanager
from logging import getLogger

from definitions import MessageInfo, MessageTypes, UserNotFoundError

logger = getLogger(__name__)

class ChatDBConfig:
    # Resolved relative to this file (not the process cwd) so the DB always lands in server/db/,
    # regardless of the directory the server scripts are launched from.
    db_path: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chat.db')

class ChatDB:
    def __init__(self):
        self.db_path = ChatDBConfig.db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        # One long-lived connection for the process instead of opening/closing a fresh sqlite3
        # connection on every single query. Chat server and file server are separate processes,
        # each holding one of these; WAL mode is what lets two different connections read/write the same file
        # concurrently without "database is locked" errors, and the lock below just serializes
        # access from this process's own threads (sqlite3 connections aren't thread-safe by
        # default). This gets simplified further in the asyncio rewrite.
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False) #So few threads use the same connection
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.Lock()

    @contextmanager
    def session(self):
        with self._lock:
            try:
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback() #so we wont keep an half transaction if somethings breaks
                raise

    def setup_database(self, db_conn: sqlite3.Connection):
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
           CREATE INDEX IF NOT EXISTS idx_messages_room_timestamp
           ON messages(room_id, timestamp);
           ''')

        cursor.execute('''
             CREATE TABLE IF NOT EXISTS room_checkins (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 sender_id INTEGER NOT NULL,
                 room_id INTEGER NOT NULL,
                 join_timestamp DATETIME NOT NULL,
                 FOREIGN KEY (sender_id) REFERENCES users(id),
                 FOREIGN KEY (room_id) REFERENCES rooms(id),
                 UNIQUE (sender_id, room_id)
                 );
             ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            file_id TEXT UNIQUE NOT NULL,
            file_name TEXT NOT NULL
            );
        ''')

        # CREATE TABLE IF NOT EXISTS above is a no-op against a files table that already exists
        # from before file_name was added to this schema, so older db files never pick the
        # column up on their own - every upload against them fails with "no column named
        # file_name", outside any try/except, silently killing the handler thread.
        existing_file_columns = {row[1] for row in cursor.execute('PRAGMA table_info(files)').fetchall()}
        if 'file_name' not in existing_file_columns:
            cursor.execute("ALTER TABLE files ADD COLUMN file_name TEXT NOT NULL DEFAULT ''")

    @classmethod
    def send_previous_messages_in_room(cls, *, db_conn: sqlite3.Connection, room_name: str, join_timestamp: typing.Optional[str] = None) -> typing.Generator[str, None, None]:
        cursor = db_conn.cursor()

        room_id = cls.get_room_id_from_rooms(db_conn=db_conn, room_name=room_name)

        # Single JOIN instead of one extra query per row to resolve each sender's username.
        if join_timestamp:
            cursor.execute('''
              SELECT m.text_message, u.username, m.timestamp
              FROM messages m
              JOIN users u ON u.id = m.sender_id
              WHERE m.room_id = ?
              AND m.timestamp > ?
              ORDER BY m.timestamp ASC
               ''', (room_id, join_timestamp))

        else:
            cursor.execute('''
              SELECT m.text_message, u.username, m.timestamp
              FROM messages m
              JOIN users u ON u.id = m.sender_id
              WHERE m.room_id = ?
              ORDER BY m.timestamp ASC
                  ''', (room_id,))

        for text_message, sender_name, timestamp in cursor.fetchall():
            msg = MessageInfo(type=MessageTypes.CHAT, text_message=text_message, sender_name=sender_name, msg_timestamp=timestamp)
            yield msg.formatted_msg()

    @classmethod
    def store_user(cls, *, db_conn: sqlite3.Connection, sender_name: str):
        cursor = db_conn.cursor()
        # Rely on the UNIQUE constraint rather than check-then-insert, which races when two
        # clients with the same username connect concurrently.
        cursor.execute('INSERT INTO users (username) VALUES (?) ON CONFLICT(username) DO NOTHING', (sender_name,))

    @classmethod
    def create_room(cls, *, db_conn: sqlite3.Connection, room_name: str):
        cursor = db_conn.cursor()
        cursor.execute('INSERT INTO rooms (room_name) VALUES (?) ON CONFLICT(room_name) DO NOTHING', (room_name,))

    @classmethod
    def store_message(cls, *, db_conn: sqlite3.Connection, text_message: str, sender_name: str, room_name: str, timestamp: str):
        cursor = db_conn.cursor()

        sender_id, room_id = cls._get_sender_and_room_ids(db_conn=db_conn, sender_name=sender_name, room_name=room_name)

        cursor.execute('''
           INSERT INTO messages (text_message, sender_id, room_id, timestamp)
           VALUES (?,?,?,?)''', (text_message, sender_id, room_id, timestamp))

    @classmethod
    def create_user_checkin_room(cls, *, db_conn: sqlite3.Connection, sender_name: str, room_name: str, join_timestamp: str):
        cursor = db_conn.cursor()

        sender_id, room_id = cls._get_sender_and_room_ids(db_conn=db_conn, sender_name=sender_name, room_name=room_name)

        cursor.execute(
            '''
            INSERT INTO room_checkins (sender_id, room_id, join_timestamp)
            VALUES (?, ?, ?)
            ON CONFLICT(sender_id, room_id) DO NOTHING
            ''',
            (sender_id, room_id, join_timestamp)
        )

    @classmethod
    def get_user_join_timestamp(cls, *, db_conn: sqlite3.Connection, sender_name: str, room_name: str) -> typing.Optional[str]:
        cursor = db_conn.cursor()

        sender_id, room_id = cls._get_sender_and_room_ids(db_conn=db_conn, sender_name=sender_name, room_name=room_name)

        cursor.execute(
            'SELECT join_timestamp FROM room_checkins WHERE sender_id = ? AND room_id = ?',
            (sender_id, room_id)
        )
        user_join_timestamp = cursor.fetchone()

        if not user_join_timestamp:
            return None
        return user_join_timestamp[0]

    @classmethod
    def store_file_in_files(cls, *, db_conn: sqlite3.Connection, file_path: str, file_id: str, file_name: str):
        cursor = db_conn.cursor()
        cursor.execute('''
               INSERT INTO files (file_path, file_id, file_name)
               VALUES (?,?,?)''', (file_path, file_id, file_name))

    @classmethod
    def get_file_record_by_file_id(cls, *, db_conn: sqlite3.Connection, file_id: str) -> typing.Optional[typing.Tuple[str, str]]:
        """Returns (file_path, original file_name) for a given file_id, or None if not found."""
        cursor = db_conn.cursor()
        cursor.execute('SELECT file_path, file_name FROM files WHERE file_id = ?', (file_id,))
        record = cursor.fetchone()
        if record:
            return record[0], record[1]
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
    def _get_sender_and_room_ids(cls, *, db_conn: sqlite3.Connection, sender_name: str, room_name: str) -> typing.Tuple[int, typing.Optional[int]]:
        """Resolves a username and room name to their ids in a single round trip (instead of two
        separate SELECTs). room_id may legitimately be None (room not created yet); a sender
        that doesn't exist is always a bug upstream, so that raises."""
        cursor = db_conn.cursor()
        cursor.execute(
            '''
            SELECT (SELECT id FROM users WHERE username = ?),
                   (SELECT id FROM rooms WHERE room_name = ?)
            ''',
            (sender_name, room_name)
        )
        sender_id, room_id = cursor.fetchone()
        if sender_id is None:
            raise UserNotFoundError(f"No user found with username '{sender_name}'")
        return sender_id, room_id