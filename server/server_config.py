import dataclasses
import os

@dataclasses.dataclass(frozen=True)
class ServerConfig:
    listener_limit_number: int = 5
    db_path: str = os.path.join(os.path.dirname(__file__), 'db', 'chat.db')
    message_pattern = "[{msg_timestamp}] [{sender_name}]: {message}"
    # temp_file_base_dir: str = os.path.join(...,'temp')
