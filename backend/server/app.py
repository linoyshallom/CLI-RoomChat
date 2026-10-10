import asyncio
import datetime
import os
import typing
import uuid
from contextlib import asynccontextmanager
from logging import getLogger

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from config import ServerConfig
from definitions import (
    MessageInfo, ServerMessage, SetupRoomData, ChatMessageData, SwitchRoomData, UsernameData,
    RoomTypes, MessageTypes, UploadFileError, FileTooLargeError,
)
from server.db.chat_db import ChatDB
from server.rooms import ClientInfo, RoomRegistry
from utils import chunkify
from utils.logging_config import configure_logging

logger = getLogger(__name__)

chat_db = ChatDB()
room_registry = RoomRegistry()

# Guards the store-a-message and read-messages-after-cursor db operations against each other,
# since both run via asyncio.to_thread and sqlite's own threading.Lock gives no ordering
# guarantee between two independently-submitted thread-pool calls - without this, a joining
# client's catch-up query could race a concurrent sender's store and observe neither the live
# broadcast (not registered yet) nor the persisted row (not committed yet), losing the message.
# Created in `lifespan`, not here at import time: asyncio.Lock binds to whichever event loop
# first uses it, and a module-level instance would get reused - and mismatched - across the
# fresh event loop each new `TestClient(app)` (or a second real app instance) actually runs on.
_message_write_lock: typing.Optional[asyncio.Lock] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _message_write_lock
    _message_write_lock = asyncio.Lock()
    with chat_db.session() as db_conn:
        chat_db.setup_database(db_conn=db_conn)
    yield


app = FastAPI(lifespan=lifespan)


# --- sync helpers, always called through asyncio.to_thread so a slow sqlite write never
# blocks the event loop (and therefore every other connected client) ---

def _store_user_sync(*, sender_name: str) -> None:
    with chat_db.session() as db_conn:
        chat_db.store_user(db_conn=db_conn, sender_name=sender_name)


def _store_message_sync(*, text_message: str, sender_name: str, room_name: str, timestamp: str) -> None:
    with chat_db.session() as db_conn:
        chat_db.store_message(db_conn=db_conn, text_message=text_message, sender_name=sender_name, room_name=room_name, timestamp=timestamp)


def _private_room_setup_sync(*, username: str, join_timestamp: str, group_name: str) -> typing.Tuple[list, typing.Optional[int]]:
    with chat_db.session() as db_conn:
        room_id = chat_db.get_room_id_from_rooms(db_conn=db_conn, room_name=group_name)
        user_join_timestamp = chat_db.get_user_join_timestamp(db_conn=db_conn, sender_name=username, room_name=group_name)

        # If room still not exist, then create and add to 'checkin_room' table
        if not room_id:
            chat_db.create_room(db_conn=db_conn, room_name=group_name)
            user_join_timestamp = join_timestamp
            chat_db.create_user_checkin_room(db_conn=db_conn, sender_name=username, room_name=group_name, join_timestamp=user_join_timestamp)

        # If room exists but user haven't checkin to this room yet
        if not user_join_timestamp:
            user_join_timestamp = join_timestamp
            chat_db.create_user_checkin_room(db_conn=db_conn, sender_name=username, room_name=group_name, join_timestamp=user_join_timestamp)

        # Users in private rooms will get only messages came after their first joining group timestamp
        formatted_messages = list(chat_db.send_previous_messages_in_room(db_conn=db_conn, room_name=group_name, join_timestamp=user_join_timestamp))
        # Read inside the same session as the replay itself - the session lock keeps any concurrent
        # write from landing between the two, so the cursor can't skip a message.
        return formatted_messages, chat_db.get_last_message_id_in_room(db_conn=db_conn, room_name=group_name)


def _global_room_setup_sync(*, group_name: str) -> typing.Tuple[list, typing.Optional[int]]:
    with chat_db.session() as db_conn:
        chat_db.create_room(db_conn=db_conn, room_name=group_name)
        formatted_messages = list(chat_db.send_previous_messages_in_room(db_conn=db_conn, room_name=group_name))
        return formatted_messages, chat_db.get_last_message_id_in_room(db_conn=db_conn, room_name=group_name)


def _room_catch_up_sync(*, group_name: str, after_message_id: typing.Optional[int]) -> list:
    with chat_db.session() as db_conn:
        return list(chat_db.send_messages_in_room_after_id(db_conn=db_conn, room_name=group_name, after_message_id=after_message_id or 0))


def _write_upload_sync(*, src_file, dst_path: str, file_id: str, filename: str, max_size: int) -> None:
    total_bytes = 0
    try:
        with open(dst_path, 'wb') as dst:
            for chunk in chunkify(reader_file=src_file, chunk_size=65_536):
                total_bytes += len(chunk)
                if total_bytes > max_size:
                    raise FileTooLargeError(filename)
                dst.write(chunk)

    except FileTooLargeError:
        if os.path.exists(dst_path):
            os.remove(dst_path)
        raise

    except Exception as e:
        if os.path.exists(dst_path):
            os.remove(dst_path)
        raise UploadFileError(f"Failed write to {dst_path}") from e

    with chat_db.session() as db_conn:
        chat_db.store_file_in_files(db_conn=db_conn, file_path=dst_path, file_id=file_id, file_name=filename)


def _get_file_record_sync(*, file_id: str):
    with chat_db.session() as db_conn:
        return chat_db.get_file_record_by_file_id(db_conn=db_conn, file_id=file_id)


def _generate_file_id(*, file_name: str) -> str:
    # basename strips any path separators/".." the client sent as a filename, since this id
    # is joined directly onto the uploads dir to build the on-disk path.
    return f"file_id-{uuid.uuid4()}-{os.path.basename(file_name)}"


# --- chat websocket ---

async def _send(websocket: WebSocket, *, msg_type: MessageTypes, text: str) -> None:
    await websocket.send_json(ServerMessage(type=msg_type, text=text).model_dump(mode="json"))


async def _receive_frame(websocket: WebSocket) -> dict:
    """Wraps receive_json() so every caller gets either a dict or a ValueError - a frame that's
    valid JSON but not an object (e.g. the client sends "42" or "[1,2,3]") would otherwise reach
    pydantic's **frame unpacking as a bare TypeError, which nothing catches."""
    frame = await websocket.receive_json()
    if not isinstance(frame, dict):
        raise ValueError(f"Expected a JSON object frame, got {type(frame).__name__}")
    return frame


async def _send_history(websocket: WebSocket, formatted_messages: list) -> None:
    if not formatted_messages:
        await _send(websocket, msg_type=MessageTypes.SYSTEM, text="No messages in this chat yet ...")
        return

    for msg in formatted_messages:
        await websocket.send_json({"type": MessageTypes.CHAT.value, "text": msg})


async def _setup_room(websocket: WebSocket, client_info: ClientInfo) -> None:
    """Handles one 'join' frame: validates it, resolves/creates the room, replays history,
    then (only after history is fully sent) registers the client and broadcasts the join -
    this ordering is what guarantees a live message can never land in the middle of a
    history replay. Fetching that history yields the event loop, so anything another client
    sent meanwhile is replayed from the db right after the registration - it arrived too
    late for the history query and too early for the broadcast registry.
    Re-prompts in place on invalid input instead of recursing, so a client spamming bad join
    frames can't grow the stack without bound."""
    while True:
        frame = await _receive_frame(websocket)

        try:
            setup_room_data = SetupRoomData(**frame)
            room_type = RoomTypes[setup_room_data.room_type.upper()]
        except (ValidationError, KeyError):
            await _send(websocket, msg_type=MessageTypes.SYSTEM, text="Expected a join request with a valid room type, try again")
            continue

        if room_type == RoomTypes.PRIVATE:
            group_name = setup_room_data.group_name
            if not group_name:
                await _send(websocket, msg_type=MessageTypes.SYSTEM, text="A private room requires a group name, try again")
                continue

            join_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_messages, last_message_id = await asyncio.to_thread(
                _private_room_setup_sync, username=client_info.username, join_timestamp=join_timestamp, group_name=group_name
            )

        else:
            group_name = setup_room_data.room_type
            formatted_messages, last_message_id = await asyncio.to_thread(_global_room_setup_sync, group_name=group_name)

        break

    client_info.room_type = room_type
    client_info.current_room = group_name

    await _send_history(websocket, formatted_messages)

    room_registry.add(client_info=client_info)

    # Only a client already sitting in this room could have stored a message into it while the
    # history above was being fetched, so an otherwise empty room has nothing to catch up on -
    # worth skipping, since the query costs a full db round trip on every single join.
    if len(room_registry.active_clients_in_room(current_room=group_name)) > 1:
        async with _message_write_lock:
            catch_up_messages = await asyncio.to_thread(_room_catch_up_sync, group_name=group_name, after_message_id=last_message_id)
        for msg in catch_up_messages:
            await websocket.send_json({"type": MessageTypes.CHAT.value, "text": msg})

    logger.info(
        "client joined room",
        extra={"event": "room_join", "username": client_info.username, "room_type": room_type.value, "room": group_name},
    )
    join_msg = MessageInfo(type=MessageTypes.SYSTEM, text_message=f"{client_info.username} joined '{group_name}' group")
    await room_registry.broadcast(msg=join_msg, current_room=client_info.current_room)


async def _handle_disconnect(client_info: ClientInfo) -> None:
    if not client_info.current_room:
        return
    # current_room is set before room_registry.add() runs (add() needs it to pick the bucket),
    # so a disconnect during the history replay in between would otherwise announce a leave for
    # a join no one ever saw. Only broadcast if the client was actually registered.
    if not room_registry.remove(current_room=client_info.current_room, username=client_info.username):
        return
    logger.info(
        "client disconnected from room",
        extra={"event": "disconnect", "username": client_info.username, "room": client_info.current_room},
    )
    leave_msg = MessageInfo(type=MessageTypes.SYSTEM, text_message=f"{client_info.username} disconnected from '{client_info.current_room}'")
    await room_registry.broadcast(msg=leave_msg, current_room=client_info.current_room)


@app.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket, username: str) -> None:
    await websocket.accept()

    client_host = websocket.client.host if websocket.client else None

    try:
        validated_username = UsernameData(username=username).username
    except ValidationError:
        logger.warning(
            "rejected connection with invalid username",
            extra={"event": "connect_rejected", "username": username, "client_host": client_host},
        )
        await _send(websocket, msg_type=MessageTypes.SYSTEM, text="Invalid username - only letters, numbers, '.' and '_' are allowed")
        await websocket.close(code=1008)
        return

    logger.info(
        "client connected",
        extra={"event": "connect", "username": validated_username, "client_host": client_host},
    )
    await asyncio.to_thread(_store_user_sync, sender_name=validated_username)
    client_info = ClientInfo(websocket=websocket, username=validated_username)

    try:
        await _setup_room(websocket, client_info)

        while True:
            frame = await _receive_frame(websocket)
            action = frame.get("action")

            if action == "switch":
                SwitchRoomData(**frame)
                await _handle_disconnect(client_info)
                client_info.current_room = None
                await _setup_room(websocket, client_info)

            elif action == "message":
                data = ChatMessageData(**frame)
                msg_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                msg_obj = MessageInfo(type=MessageTypes.CHAT, text_message=data.text, sender_name=client_info.username, msg_timestamp=msg_timestamp)

                # Persisted before broadcasting: a joining client's catch-up query (guarded by
                # the same lock) must never be able to observe a message that's been announced
                # live but not yet committed.
                async with _message_write_lock:
                    await asyncio.to_thread(
                        _store_message_sync, text_message=data.text, sender_name=client_info.username,
                        room_name=client_info.current_room, timestamp=msg_timestamp
                    )
                await room_registry.broadcast(msg=msg_obj, current_room=client_info.current_room)
                # Message content itself is not logged - only metadata, since the audit log is
                # a file on disk and chat content isn't ours to persist twice over.
                logger.info(
                    "chat message sent",
                    extra={
                        "event": "message", "username": client_info.username,
                        "room": client_info.current_room, "length": len(data.text),
                    },
                )

            else:
                await _send(websocket, msg_type=MessageTypes.SYSTEM, text=f"Unknown action '{action}'")

    except WebSocketDisconnect:
        # Peer closed the connection (e.g. terminal closed, network drop) - clean it out of
        # its room so the next broadcast doesn't try to send to a dead socket.
        await _handle_disconnect(client_info)

    except (ValidationError, ValueError):
        # ValueError covers the json.JSONDecodeError that receive_json() raises on a non-json
        # frame - without it that escapes uncaught and the client is left in the registry
        # holding a socket nobody ever closes.
        await _send(websocket, msg_type=MessageTypes.SYSTEM, text="Malformed message, closing connection")
        await _handle_disconnect(client_info)
        await websocket.close(code=1008)


# --- file transfer (HTTP) ---

@app.post("/files")
async def upload_file(file: UploadFile = File(...)) -> dict:
    logger.info("upload requested", extra={"event": "upload_requested", "file_name": file.filename})
    file_id = _generate_file_id(file_name=file.filename)
    upload_dir = await asyncio.to_thread(ServerConfig.upload_dir_dst_path)
    uploaded_file_path = os.path.join(upload_dir, file_id)

    try:
        await asyncio.to_thread(
            _write_upload_sync, src_file=file.file, dst_path=uploaded_file_path,
            file_id=file_id, filename=file.filename, max_size=ServerConfig.max_file_size
        )

    except FileTooLargeError:
        logger.warning(
            "upload rejected: too large",
            extra={"event": "upload_rejected", "file_name": file.filename, "max_size": ServerConfig.max_file_size},
        )
        raise HTTPException(status_code=413, detail="File size exceeded")

    except UploadFileError as e:
        logger.exception("upload failed", extra={"event": "upload_failed", "file_name": file.filename})
        raise HTTPException(status_code=500, detail="Upload failed") from e

    logger.info(
        "upload complete",
        extra={"event": "upload_complete", "file_name": file.filename, "file_id": file_id, "path": uploaded_file_path},
    )
    return {"file_id": file_id}


@app.get("/files/{file_id}")
async def download_file(file_id: str) -> FileResponse:
    logger.info("download requested", extra={"event": "download_requested", "file_id": file_id})
    record = await asyncio.to_thread(_get_file_record_sync, file_id=file_id)

    if not record:
        logger.warning("download rejected: unknown file id", extra={"event": "download_rejected", "file_id": file_id})
        raise HTTPException(status_code=404, detail="File id was not found")

    file_path, file_name = record
    if not await asyncio.to_thread(os.path.exists, file_path):
        logger.warning(
            "download rejected: file missing on disk",
            extra={"event": "download_rejected", "file_id": file_id, "path": file_path},
        )
        raise HTTPException(status_code=404, detail="File id was not found")

    logger.info(
        "download complete", extra={"event": "download_complete", "file_id": file_id, "file_name": file_name},
    )
    return FileResponse(path=file_path, filename=file_name, media_type="application/octet-stream")


# --- serve the built UI (npm run build in UI/) from this same app/port, so the whole thing
# deploys as one process - mounted last so it only matches requests the routes above didn't ---

_ui_dist_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "UI", "dist"))
if os.path.isdir(_ui_dist_dir):
    app.mount("/", StaticFiles(directory=_ui_dist_dir, html=True), name="ui")
else:
    logger.warning(
        "UI build not found, not serving a frontend",
        extra={"event": "ui_build_missing", "expected_path": _ui_dist_dir},
    )


def main():
    import uvicorn
    uvicorn.run(app, host=ServerConfig.host, port=ServerConfig.listening_port)


if __name__ == '__main__':
    configure_logging(source="server", log_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"))
    main()
