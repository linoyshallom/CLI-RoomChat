import dataclasses

from server.server_file_transfer import FileServerConfig


@dataclasses.dataclass(frozen=True)
class ServerConfig:
    host_ip: str = '127.0.0.1'
    listener_limit_number: int = 5
    listening_port: int = 6
    max_threads_number: int = 7
    file_server_config: FileServerConfig()= FileServerConfig

