import dataclasses
import os
from server_file_transfer import FileServerConfig

@dataclasses.dataclass(frozen=True)
class ServerConfig:
    listener_limit_number: int = 5
    listening_port: int = 5
    db_path: str = os.path.join(os.path.dirname(__file__), 'db', 'chat.db')
    message_pattern = "[{msg_timestamp}] [{sender_name}]: {message}"
    file_server_config: FileServerConfig()= FileServerConfig

