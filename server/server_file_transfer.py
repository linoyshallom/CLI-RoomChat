import os
import socket
import dataclasses
import uuid


@dataclasses.dataclass(frozen=True)
class FileServerConfig:
    listening_port: int = 6
    listener_limit_number: int = 5
    max_file_size: int = ...
    upload_dir_dst_path: str = ...
    # temp_file_base_dir: str = os.path.join(...,'temp')

class FileTransferServer:
    def __init__(self, host, listen_port):
        self.file_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.file_server.bind((host, listen_port))
        except Exception as e:
            print(f"Unable to bind to host and port : {repr(e)}")

        self.file_server.listen(FileServerConfig.listener_limit_number)

    #write the file into Upload directory  (writing should be in chunks)
    @staticmethod
    def upload_file(conn):
        while True:
            file_name = conn.recv(1024).decode()

            file_id = f"{str(uuid.uuid4())}_{file_name}"
            #conn.send(file_id.encode('utf-8'))
            file_dst_path = os.path.join(FileServerConfig.upload_dir_dst_path, "upload", file_id)

            try:
                os.makedirs(os.path.dirname(FileServerConfig.upload_dir_dst_path), exist_ok=True)

            except Exception as e:
                raise "Failed to create dir" from e

            try:
                with open(file_dst_path, 'wb') as file:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    file.write(chunk)

                print(f"file {file_id} is uploaded successfully! , now people can download it")
                #send this file if in chat db messages

            except Exception as e:
                raise f"Failed to write to {file_dst_path}" from e

    def download_file(self, conn):
        file_id = conn.rcev(1024).decode()
        dst_path = conn.rcev(1024).decode()#where to download




    def start(self):
        ...


#todo zip file handle in future? or nor necessary