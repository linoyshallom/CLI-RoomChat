import json
import os
import socket
import uuid
from concurrent.futures import ThreadPoolExecutor

from config import FileServerConfig
from db import ChatDB
from definitions import DownloadFileError, UploadFileError, FileHandlerTypes, FileTransferStatus, UploadFileData, DownloadFileData
from utils import chunkify


class FileTransferServer:
    def __init__(self, host: str, listen_port: int):
        self.file_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.file_server.bind((host, listen_port))
        except Exception as e:
            print(f"Unable to bind to host and port : {repr(e)}")

        self.file_server.listen(FileServerConfig.listener_limit_number)

        self.chat_db = ChatDB()

    def file_handler(self, conn: socket.socket) -> None:
        while True:
            handler = conn.recv(1024).decode()

            if not handler:
                break

            try:
                handler_type = FileHandlerTypes[handler]
            except KeyError:
                raise Exception(f"Got unexpected handler type {handler}")   #todo don't catch error for some reason

            json_data = conn.recv(1024).decode()

            if handler_type == FileHandlerTypes.UPLOAD:
                upload_data = UploadFileData(**json.loads(json_data))
                self._upload_file(conn=conn, data=upload_data)

            elif handler_type == FileHandlerTypes.DOWNLOAD:
                download_data = DownloadFileData(**json.loads(json_data))
                self._download_file(conn=conn, data=download_data)

    def _upload_file(self, *, conn: socket.socket, data: UploadFileData) -> None: #todo no support multiple of requested
        file_id = self._generate_file_id(file_name=data.filename)
        file_size = data.file_size

        if int(file_size) > int(FileServerConfig.max_file_size):
            conn.send(FileTransferStatus.EXCEEDED.value.encode('utf-8'))
            return

        uploaded_file_path = os.path.join(FileServerConfig.upload_dir_dst_path(), file_id)
        aggregated_chunks = b""

        try:
            with open(uploaded_file_path, 'wb') as file:
                while True:
                    chunk = conn.recv(1024)
                    aggregated_chunks += chunk
                    file.write(chunk)

                    if len(aggregated_chunks) == file_size:
                        break

        except Exception as e:
            raise UploadFileError(f"Failed write to {uploaded_file_path}") from e

        self.chat_db.store_file_in_files(file_path=uploaded_file_path, file_id=file_id)
        conn.send(file_id.encode('utf-8'))
        conn.close()

    def _download_file(self, *, conn: socket.socket, data: DownloadFileData) -> None:
        file_id = data.file_id
        user_dir_dst_path = data.dst_path
        print(f"file id {file_id}")

        if uploaded_file_path := self.chat_db.get_file_path_by_file_id(file_id=file_id):
            file_name = os.path.basename(uploaded_file_path).rsplit('-', 1)[1]

            try:
                with open(uploaded_file_path, 'rb') as src_file, open(os.path.join(user_dir_dst_path, file_name), 'wb') as dst_file:
                    for chunk in chunkify(reader_file=src_file):
                        dst_file.write(chunk)
                conn.send(FileTransferStatus.SUCCEED.value.encode('utf-8'))

            except Exception as e:
                raise DownloadFileError(f"Failed to download {file_id}") from e

        else:
            print("got into not found")
            conn.send(FileTransferStatus.NOT_FOUND.value.encode('utf-8'))


    @staticmethod
    def _generate_file_id(*, file_name: str) -> str:
        return f"file-{uuid.uuid4()}-{file_name}"

    def start(self):
        print("File Server started...")
        with ThreadPoolExecutor(max_workers=FileServerConfig.max_threads_number) as executor:
            while True:
                client_sock, addr = self.file_server.accept()
                print(f"Successfully connected client {addr[0]} {addr[1]} to files server \n")
                executor.submit(self.file_handler, client_sock)

def main():
    file_transfer_server = FileTransferServer(host='127.0.0.1', listen_port=FileServerConfig.listening_port)
    file_transfer_server.start()


if __name__ == "__main__":
    main()

