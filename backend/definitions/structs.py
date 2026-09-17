import dataclasses
import typing

from pydantic import BaseModel, Field

from config import ClientConfig
from .types import RoomTypes, MessageTypes


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

class ServerMessage(BaseModel):
    """Outbound envelope sent to the client over the chat websocket. `text` is already
    rendered via MessageInfo.formatted_msg() so there is a single source of formatting."""
    type: MessageTypes
    text: str

class UsernameData(BaseModel):
    username: str = Field(min_length=1, pattern=ClientConfig.allowed_input_user_pattern)

class SetupRoomData(BaseModel):
    """Inbound 'join' action - sent on initial connect and again after a '/switch'."""
    action: typing.Literal["join"] = "join"
    room_type: str
    group_name: typing.Optional[str] = None

class ChatMessageData(BaseModel):
    """Inbound 'message' action - a chat message sent to the client's current room."""
    action: typing.Literal["message"] = "message"
    text: str = Field(min_length=1)

class SwitchRoomData(BaseModel):
    """Inbound 'switch' action - leave the current room; a 'join' is expected to follow."""
    action: typing.Literal["switch"] = "switch"
