import enum

class RoomTypes(enum.Enum):
    GLOBAL = "GLOBAL"
    PRIVATE = "PRIVATE"

class MessageTypes(enum.Enum):
    SYSTEM = "SYSTEM"
    CHAT = "CHAT"

class FileHandlerTypes(enum.Enum):
    UPLOAD = "UPLOAD"
    DOWNLOAD = "DOWNLOAD"

class FileTransferStatus(enum.Enum):
    SUCCEED = "SUCCEED"
    FAILED = "FAILED"
    NOT_FOUND = "NOT_FOUND"
    EXCEEDED = "EXCEEDED"
