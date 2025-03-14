import dataclasses

from server.server_file_transfer import FileServerConfig


@dataclasses.dataclass(frozen=True)
class ServerConfig:
    listener_limit_number: int = 5
    listening_port: int = 6
    max_threads_number: int = 7
    file_server_config: FileServerConfig()= FileServerConfig
    #todo ip host server also in this config?

