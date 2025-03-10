import dataclasses
import os
import socket
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from server.db.chat_db import ChatDB
from utils import chunkify


class UploadFileError(Exception):
    pass

class DownloadFileError(Exception):
    pass

@dataclasses.dataclass(frozen=True)
class FileServerConfig:
    listening_port: int = 6
    listener_limit_number: int = 5
    max_file_size: int = 16_000_000
    upload_dir_dst_path: str = ...  #environment variable?
    threads_number: int = 7

class FileTransferServer:
    def __init__(self, host, listen_port):
        self.file_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.file_server.bind((host, listen_port))
        except Exception as e:
            print(f"Unable to bind to host and port : {repr(e)}")

        self.file_server.listen(FileServerConfig.listener_limit_number)

        self.chat_db = ChatDB()

    def file_handler(self, conn):
        upload_thread = threading.Thread(target=self._upload_file, args=(conn,))
        upload_thread.start()

        download_thread = threading.Thread(target=self._download_file, kwargs={"conn":conn})
        download_thread.start()


    def _upload_file(self, conn):
        while True:
            file_name = conn.recv(1024).decode()

            file_id = self._generate_file_id(file_name=file_name)
            conn.send(file_id.encode('utf-8'))

            try:
                os.makedirs(os.path.dirname(FileServerConfig.upload_dir_dst_path), exist_ok=True)
            except Exception as e:
                raise UploadFileError("Upload failed, failed to create dir") from e

            upload_file_path = os.path.join(FileServerConfig.upload_dir_dst_path, "upload", file_id)
            self.chat_db.store_file(file_path=upload_file_path, file_id=file_id)

            self._save_file(upload_file_path=upload_file_path)

    def _download_file(self, *, conn):
        file_id = conn.rcev(1024).decode()
        upload_file_path = self.chat_db.file_path_by_file_id(file_id=file_id)

        user_dst_path = conn.rcev(1024).decode()

        try:
            with open(upload_file_path, 'rb') as src_file, open(user_dst_path, 'wb') as dst_file:
                for chunk in chunkify(reader_file=src_file):
                    dst_file.write(chunk)

        except Exception as e:
            raise DownloadFileError(f"Failed to download {file_id}") from e

    @staticmethod
    def _save_file(*, upload_file_path: str):
        file_size = 0
        try:
            with open(upload_file_path, 'wb') as file:
                if file_size >= FileServerConfig.max_file_size:
                    raise UploadFileError("Upload failed, file size exceeded")

                for chunk in chunkify(reader_file=file):
                    file.write(chunk)
                    file_size += len(chunk)

        except Exception as e:
            raise UploadFileError(f"Failed to write to {upload_file_path}") from e

    @staticmethod
    def _generate_file_id(*, file_name: str) -> str:
        return f"{uuid.uuid4()}_{file_name}"

    def start(self):
        print("File Server started...")
        with ThreadPoolExecutor(max_workers=FileServerConfig.threads_number) as executor:
            while True:
                client_sock, addr = self.file_server.accept()
                print(f"Successfully connected client {addr[0]} {addr[1]} to files server")
                executor.submit(self.file_handler, client_sock)
