import json
import os
import socket
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from config.config import FileServerConfig
from definitions.structs import UploadFileData, DownloadFileData
from definitions.types import FileHandlerTypes
from server.db.chat_db import ChatDB
from utils import chunkify


class UploadFileError(Exception):
    pass

class DownloadFileError(Exception):
    pass

class FileIdNotFoundError(Exception):
    pass


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
        handler = conn.recv(1024).decode()
        try:
            handler_type = FileHandlerTypes[handler]
        except KeyError:
            raise Exception(f"Got unexpected handler type {handler}")   #todo don't catch error for some reason

        json_data = conn.recv(1024).decode()

        if handler_type == FileHandlerTypes.UPLOAD:
            print("into upload")
            upload_data = UploadFileData(**json.loads(json_data))

            upload_thread = threading.Thread(target=self._upload_file, kwargs={"conn": conn, "data": upload_data})
            upload_thread.start()

        elif handler_type == FileHandlerTypes.DOWNLOAD:
            download_data = DownloadFileData(**json.loads(json_data))

            download_thread = threading.Thread(target=self._download_file, kwargs={"conn": conn, "data": download_data })
            download_thread.start()

    def _upload_file(self, *, conn: socket.socket, data: UploadFileData):
        file_size = 0
        file_id = self._generate_file_id(file_name=data.filename)
        uploaded_file_path = os.path.join(FileServerConfig.upload_dir_dst_path(), file_id)

        try:
            with open(uploaded_file_path, 'ab') as file:
                while True:
                    chunk = conn.recv(1024)
                    print(f"chunk - {chunk}")

                    if not chunk:
                        break

                    file_size += len(chunk)
                    if file_size > FileServerConfig.max_file_size:
                        raise UploadFileError("Upload failed, file size exceeded")

                    file.write(chunk)
                    print(f"writing {chunk} to file  ")

        except Exception as e:
            raise UploadFileError(f"Failed write to {uploaded_file_path}") from e

        print("store file in files")
        self.chat_db.store_file_in_files(file_path=uploaded_file_path, file_id=file_id)
        conn.send(file_id.encode('utf-8'))

    def _download_file(self, *, conn: socket.socket, data: DownloadFileData):
        print("into download")
        while True:
            file_id = data.file_id
            user_dir_dst_path = data.dst_path

            if uploaded_file_path := self.chat_db.get_file_path_by_file_id(file_id=file_id):
                file_name = os.path.basename(uploaded_file_path).rsplit('-',1)[1]

                try:
                    with open(uploaded_file_path, 'rb') as src_file, open(os.path.join(user_dir_dst_path,file_name), 'wb') as dst_file:
                        for chunk in chunkify(reader_file=src_file):
                            dst_file.write(chunk)
                    conn.send("done downloading".encode('utf-8'))


                except Exception as e:
                    raise DownloadFileError(f"Failed to download {file_id}") from e

            else:
                raise FileIdNotFoundError(f"Failed to download")

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


#ignore
#todo servers execution should be in one place ?
# binary files like images, pdf uploaded and downloaded wired  ..
# is logic supports 2 parallel
# if user want to upload file that exist in uploads i won't Writing it again !
# set max files to store, if gets to max then i delete the oldest file
# check maximum file size if raise exception
# solve uploading and downloading in the same socket
# if something failed in the server i want to allow chat anyway
# if downloads exist maby try with (1)
# uploading and then downloading