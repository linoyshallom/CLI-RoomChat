import dataclasses
import os

@dataclasses.dataclass(frozen=True)
class ClientConfig:
    host_ip: str = '127.0.0.1'
    allowed_input_user_pattern: str = "/^[a-zA-Z0-9._]+$/"  # For future use login enforcement

@dataclasses.dataclass(frozen=True)
class FileServerConfig:
    listening_port: int = 78
    listener_limit_number: int = 5
    max_file_size: int = 16_000_000
    max_threads_number: int = 7

    @classmethod
    def upload_dir_dst_path(cls)-> str:
        if os.name == 'nt':  # Windows
            upload_dir = r"C:\Uploads"
        else:  # Linux/macOS
            upload_dir = "/opt/uploads"
        try:
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)

        except Exception as e:
            raise Exception(f"Failed to create uploads dir") from e

        return upload_dir


@dataclasses.dataclass(frozen=True)
class MessageServerConfig:
    listening_port: int = 6
    listener_limit_number: int = 5
    max_threads_number: int = 7

END_OF_MSG_INDICATOR = '@'

