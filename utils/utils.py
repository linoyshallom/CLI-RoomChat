import dataclasses
import datetime
import enum
import socket
import typing


class RoomTypes(enum.Enum):
    GLOBAL = "GLOBAL"
    PRIVATE = "PRIVATE"

@dataclasses.dataclass
class ClientInfo:
    client_conn: socket.socket
    username: str
    room_type: RoomTypes = None
    current_room: typing.Optional[str] = None
    user_joined_timestamp:typing.Optional[datetime] = None

@dataclasses.dataclass
class MessageInfo:
    text_message: str
    sender_name: typing.Optional[str] = None
    msg_timestamp: typing.Optional[str] = None

    def formatted_msg(self) -> str:
        return f"[{self.msg_timestamp}] [{self.sender_name}]: {self.text_message}"

    #server messages format for join and leave

#class FileInfo , instead utils rename to common and add structs file

def chunkify(*, reader_file: typing.IO[bytes], chunk_size: typing.Optional[int] = 65536) -> typing.Generator[bytes, None, None]:
    while True:
        chunk = reader_file.read(chunk_size)

        if not chunk:
            break

        yield chunk
