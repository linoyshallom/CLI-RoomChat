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
    listening_port: int = 78
    listener_limit_number: int = 5
    max_file_size: int = 16_000_000
    upload_dir_dst_path: str = r"C:\Users\Administrator\Desktop\Uploads"  #todo environment variable so we can run in any computer
    download_dir_dst_path: str = r"C:\Users\Administrator\Downloads"
    max_threads_number: int = 7

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
        command = conn.recv(1024).decode()
        print(f"file server got {command}")
        if command == "UPLOAD":
            upload_thread = threading.Thread(target=self._upload_file, args=(conn,))
            upload_thread.start()

        if command == "DOWNLOAD":
            download_thread = threading.Thread(target=self._download_file, kwargs={"conn":conn})
            download_thread.start()


    def _upload_file(self, conn):
        file_size = 0
        while True:
            file_name = conn.recv(1024).decode('utf-8')
            try:
                os.makedirs(os.path.dirname(FileServerConfig.upload_dir_dst_path), exist_ok=True)
            except Exception as e:
                raise UploadFileError("Upload failed, failed to create Uploads dir") from e

            file_id = self._generate_file_id(file_name=file_name)

            upload_file_path = os.path.join(FileServerConfig.upload_dir_dst_path, file_id)

            try:
                with open(upload_file_path, 'wb') as file:
                    if chunk := conn.recv(1024):
                        file_size += len(chunk)

                        if file_size > FileServerConfig.max_file_size:
                            raise UploadFileError("Upload failed, file size exceeded")

                        file.write(chunk)

            except Exception as e:
                raise UploadFileError(f"Failed write to {upload_file_path}") from e

            print("store file in files")
            self.chat_db.store_file_in_files(file_path=upload_file_path, file_id=file_id)
            conn.send(file_id.encode('utf-8'))   # Only when upload succeed

    def _download_file(self, conn):
        while True:
            file_id = conn.recv(1024).decode()
            print(file_id)
            user_dir_dst_path = conn.recv(1024).decode().strip()
            print(f"dit path {user_dir_dst_path}")

            if uploaded_file_path := self.chat_db.file_path_by_file_id(file_id=file_id):
                file_name = os.path.basename(uploaded_file_path).rsplit('-',1)[1]
                print(f" file name {file_name}")
                try:
                    with open(uploaded_file_path, 'rb') as src_file, open(os.path.join(user_dir_dst_path,file_name), 'wb') as dst_file:
                        for chunk in chunkify(reader_file=src_file):
                            dst_file.write(chunk)
                    print(" file is downloaded successfully!")
                    conn.send(" file is downloaded successfully!".encode('utf8'))

                except Exception as e:
                    raise DownloadFileError(f"Failed to download {file_id}") from e
            else:
                print(f"Failed to download, file id {file_id} doesn't exist, so cannot be downloaded")
                conn.send(f"Failed to download, file id {file_id} doesn't exist, so cannot be downloaded".encode('utf-8')) #send to client
                return

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
"fd".rsplit()
def main():
    file_transfer_server = FileTransferServer(host='127.0.0.1', listen_port=FileServerConfig.listening_port)

    file_server_thread = threading.Thread(target=file_transfer_server.start, daemon=True)
    file_server_thread.start()
    file_server_thread.join()

if __name__ == "__main__":
    main()



#todo const command to UPLOAD and DOWNLOAD
# check file exceeded
# servers execution in one place
# images, pdf and more transfers ..
# environment variables for paths
# is logic supports 2 parallel
# non increment id in tables
# logging file?
# black