import dataclasses
import socket
import threading
import typing

from pydantic import BaseModel

from .types import RoomTypes, MessageTypes  # change this pattern for all imports if works


@dataclasses.dataclass
class ClientInfo:
    client_conn: socket.socket
    username: str
    room_type: RoomTypes = None
    current_room: typing.Optional[str] = None
    room_setup_done_flag: threading.Event = dataclasses.field(default_factory=threading.Event)

@dataclasses.dataclass
class MessageInfo:
    type: MessageTypes
    text_message: str
    sender_name: typing.Optional[str] = None
    msg_timestamp: typing.Optional[str] = None

    def formatted_msg(self) -> str:
        if self.type == MessageTypes.SYSTEM:
            return f"[SYSTEM]: {self.text_message}"

        else:
            return f"[{self.msg_timestamp}] [{self.sender_name}]: {self.text_message}"

class SetupRoomData(BaseModel):
    room_type: str
    group_name: typing.Optional[str] = None

class UploadFileData(BaseModel):
    filename: str


class DownloadFileData(BaseModel):
    file_id: str
    dst_path: str



#todo consider others class with basemodel