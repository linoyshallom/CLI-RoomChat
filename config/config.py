import dataclasses
import os

END_OF_MSG_INDICATOR = '@'

@dataclasses.dataclass(frozen=True)
class ClientConfig:
    host_ip: str = '127.0.0.1'
    # Was previously unused and not a valid Python regex (JS-style /../ literal). Now enforced
    # via definitions.structs.UsernameData on both client and server.
    allowed_input_user_pattern: str = r"^[a-zA-Z0-9._]+$"

@dataclasses.dataclass(frozen=True)
class MessageServerConfig:
    listening_port: int = 5000
    listener_limit_number: int = 5
    max_threads_number: int = 7

@dataclasses.dataclass(frozen=True)
class FileServerConfig:
    listening_port: int = 5001
    listener_limit_number: int = 5
    max_file_size: int = 16_000_000  #16mb
    max_files_stored_in_uploads: int = 20
    max_threads_number: int = 7

    @classmethod
    def upload_dir_dst_path(cls)-> str:
        if os.name == 'nt':  # For Windows
            upload_dir = r"C:\Uploads"
        else:  # For Linux/macOS
            upload_dir = "/opt/uploads"
        try:
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)

        except Exception as e:
            raise Exception(f"Failed to create uploads dir") from e

        return upload_dir


