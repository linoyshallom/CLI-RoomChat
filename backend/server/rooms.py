import dataclasses
import typing
from collections import defaultdict
from logging import getLogger

from fastapi import WebSocket

from definitions import MessageInfo, RoomTypes

logger = getLogger(__name__)


@dataclasses.dataclass
class ClientInfo:
    websocket: WebSocket
    username: str
    room_type: typing.Optional[RoomTypes] = None
    current_room: typing.Optional[str] = None


class RoomRegistry:
    """Tracks which clients are currently active in which room, and broadcasts to them.
    Single event-loop coroutine per connection, so - unlike the thread-per-connection model
    this replaces - no lock is needed around the dict."""

    def __init__(self):
        self._room_name_to_active_clients: typing.DefaultDict[str, typing.List[ClientInfo]] = defaultdict(list)

    def add(self, *, client_info: ClientInfo) -> None:
        self._room_name_to_active_clients[client_info.current_room].append(client_info)

    def remove(self, *, current_room: str, username: str) -> bool:
        """Returns whether a client was actually removed, so a caller can tell a real departure
        apart from a no-op on a client that was never registered (e.g. it disconnected mid-join,
        before `add()` ran)."""
        before = self._room_name_to_active_clients.get(current_room, [])
        after = [client for client in before if client.username != username]
        self._room_name_to_active_clients[current_room] = after
        return len(after) != len(before)

    def active_clients_in_room(self, *, current_room: str) -> typing.List[ClientInfo]:
        return list(self._room_name_to_active_clients.get(current_room, []))  # A snapshot, so callers can't mutate the registry through it

    async def broadcast(self, *, msg: MessageInfo, current_room: str) -> None:
        # clients connected to the current room get messages in real-time, and clients
        # connected to another room will fetch the messages from db while joining. e.g. chat, joining chat, leaving chat messages ...
        clients_in_room = self.active_clients_in_room(current_room=current_room)

        dead_clients = []
        for client in clients_in_room:
            try:
                await client.websocket.send_json({"type": msg.type.value, "text": msg.formatted_msg()})
            except Exception as e:
                # If a send fails because a client disconnected, the entire broadcast isn't discarded, it is cleaned up after.
                # Logged so a genuine bug in here is still traceable, and not hidden among the routine disconnects.
                logger.debug(f"Dropping client '{client.username}' from '{current_room}' after a failed send: {e!r}")
                dead_clients.append(client)

        for client in dead_clients:
            self.remove(current_room=current_room, username=client.username)
