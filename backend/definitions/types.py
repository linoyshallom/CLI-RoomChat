import enum

class RoomTypes(enum.Enum):
    GLOBAL = "GLOBAL"
    PRIVATE = "PRIVATE"

class MessageTypes(enum.Enum):
    SYSTEM = "SYSTEM"
    CHAT = "CHAT"
