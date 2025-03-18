import dataclasses

@dataclasses.dataclass(frozen=True)
class ClientConfig:
    host_ip: str = '127.0.0.1'
    allowed_input_user_pattern: str = "/^[a-zA-Z0-9._]+$/"  # For future enforcement

@dataclasses.dataclass(frozen=True)
class FileServerConfig:
    listening_port: int = 78
    listener_limit_number: int = 5
    max_file_size: int = 16_000_000
    upload_dir_dst_path: str = r"C:\Users\shalo\Desktop\Uploads"  #todo environment variable so we can run in any computer
    download_dir_dst_path: str = r"C:\Users\shalo\Downloads"
    max_threads_number: int = 7

@dataclasses.dataclass(frozen=True)
class MessageServerConfig:
    listening_port: int = 6
    listener_limit_number: int = 5
    max_threads_number: int = 7

