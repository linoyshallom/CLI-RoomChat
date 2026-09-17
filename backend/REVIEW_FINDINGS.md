# Review findings - server/app.py, server/rooms.py

> Note: this file did not exist in the repo when the fixes below were applied; the findings are
> restated from the review brief so each one has its status recorded alongside it.

## 1. Unhandled JSONDecodeError crashes the connection without cleanup

`server/app.py`, `chat_ws` and the `websocket.receive_json()` calls in `_setup_room` and the main
loop. `receive_json()` raises `json.JSONDecodeError` on a non-json frame, which neither the
`except WebSocketDisconnect` nor the `except ValidationError` handler catches, so
`_handle_disconnect` never runs and the client is left stale in `RoomRegistry` holding a socket
nobody closes.

Fixed: widened the handler to `except (ValidationError, ValueError):` so a non-json frame takes the
same "malformed message, `_handle_disconnect`, `close(code=1008)`" path - `server/app.py:244`.
(`json.JSONDecodeError` subclasses `ValueError`; in pydantic 2.10.6 `ValidationError` does too, so
`ValidationError` is kept in the tuple for readability rather than necessity.)

## 2. Race: a message sent during a joining client's history fetch is lost for that client

`server/app.py`, `_setup_room`. The sequence was: fetch history via `asyncio.to_thread(...)` (which
yields the event loop) -> `_send_history` -> `room_registry.add()` -> broadcast join. A message
stored and broadcast by another client during that `to_thread` await is in neither the replay nor
the broadcast, and is silently lost for the joiner.

Fixed: the history fetch now also returns a replay cursor, and after `room_registry.add()` the
client is sent any messages stored past that cursor, before the join announcement - the catch-up
query runs off the event loop like every other db call - `server/app.py:181-184`, cursor plumbed
through `_private_room_setup_sync`/`_global_room_setup_sync` at `server/app.py:72,79` and the
catch-up helper at `server/app.py:82`.

The cursor is a message id, not a timestamp: stored timestamps have second resolution, so a
timestamp cursor with the existing `m.timestamp > ?` filter would drop any message sharing a second
with the last replayed one. Two query-only classmethods were added for it -
`ChatDB.get_last_message_id_in_room` (`server/db/chat_db.py:137`) and
`ChatDB.send_messages_in_room_after_id` (`server/db/chat_db.py:153`); no existing db logic changed.
The cursor is read inside the same `session()` as the replay, so the session lock keeps a
concurrent write from slipping between the two.

The catch-up query is skipped when the joining client is alone in the room (`RoomRegistry.
active_clients_in_room`, `server/rooms.py:37`): only a client already in the room can store a
message into it, so an otherwise empty room has nothing to catch up on, and skipping keeps a
db round trip off every single join.

## 3. Unbounded recursion in `_setup_room`

`server/app.py`, `_setup_room` re-prompted by `return await _setup_room(websocket, client_info)` on
the invalid-room-type and missing-group-name paths, so a client sending bad join frames grows the
stack without bound.

Fixed: converted to a `while True:` loop that `continue`s on invalid input, with identical prompts
and behaviour otherwise - `server/app.py:144-169`.

## 4. Silent broad `except Exception` in `RoomRegistry.broadcast`

`server/rooms.py`. A failed send was swallowed into `dead_clients` with no record, so a genuine bug
in the send path was indistinguishable from a routine disconnect.

Fixed: added a `logger.debug` with the client's username and the exception before the client is
queued for eviction - `server/rooms.py:52`.

## 5. Unwrapped blocking call in `download_file`

`server/app.py`, `os.path.exists(file_path)` ran a blocking stat on the event loop.

Fixed: wrapped in `await asyncio.to_thread(os.path.exists, file_path)` - `server/app.py:289`.

## Second pass (fresh independent review, not trusting the fixes above)

## 6. Non-object JSON frame raises an uncaught `TypeError`

`server/app.py`, `_setup_room` and the main loop. `receive_json()` only raises on invalid JSON
text; a frame that's valid JSON but not an object (e.g. the client sends `42` or `[1,2,3]`)
parses fine and then blows up as a plain `TypeError` on `SetupRoomData(**frame)`, which
`except (ValidationError, ValueError)` doesn't catch - same failure mode as finding #1, still
reachable.

Fixed: added `_receive_frame()` (`server/app.py:129`), a thin wrapper around `receive_json()`
that raises `ValueError` itself when the frame isn't a dict, so every existing `ValueError`
handler already covers it. Both call sites (`server/app.py:154`, `224`) now go through it.

## 7. Broadcast-before-persist race could permanently drop a message for a joining client

`server/app.py`, message handler vs. the catch-up query. Both `_store_message_sync` and
`_room_catch_up_sync` ran as independent `asyncio.to_thread` calls with no ordering guarantee
between them; a joining client's catch-up could observe neither the live broadcast (not yet
registered) nor the persisted row (not yet committed), losing the message outright.

Fixed: added `_message_write_lock` (an `asyncio.Lock`, `server/app.py:31`) around both the store
call (`server/app.py:242`) and the catch-up call (`server/app.py:192`), so the two can never be
in flight at once, and reordered the message handler to persist before broadcasting
(`server/app.py:238-244`) so a message is never announced before it's durable.

## 8. Blocking directory creation on the event loop in `upload_file`

`server/app.py`, `ServerConfig.upload_dir_dst_path()` (`config/config.py`) does a synchronous
`os.path.exists`/`os.makedirs` and was called directly from `async def upload_file`, stalling
every connected client for the syscall's duration.

Fixed: wrapped in `await asyncio.to_thread(ServerConfig.upload_dir_dst_path)` - `server/app.py`.

## 9. Path traversal via unsanitized upload filename

`server/app.py`, `_generate_file_id`. `file.filename` from the multipart upload was embedded
verbatim into the file id, which is joined directly onto the uploads dir - a crafted
`filename="../../../evil"` could write outside it. `client/client.py` already does this
sanitization on the download side; the upload side didn't.

Fixed: `_generate_file_id` now applies `os.path.basename(file_name)` before embedding it.

## 10. `_handle_disconnect` could announce a leave with no matching join

`server/app.py`/`server/rooms.py`. `client_info.current_room` is set before
`room_registry.add()` runs (required, since `add()` needs it to pick the bucket). A disconnect
during the history replay in between left `_handle_disconnect`'s `if not client_info.current_room`
guard unable to tell "never registered" apart from "registered then left," so it would still
broadcast a "disconnected" message to a room that never saw the join.

Fixed: `RoomRegistry.remove` now returns whether a client was actually removed
(`server/rooms.py:32`), and `_handle_disconnect` only broadcasts when it was
(`server/app.py:190-197`).

## 11. Minor: stale two-process comment in `ChatDB.__init__`

Comment described a pre-refactor architecture (separate chat/file-transfer processes each
holding a connection, WAL for cross-process coordination) that no longer exists post-refactor.
Reworded to describe the current single-process, thread-pool-workers-behind-one-lock reality -
`server/db/chat_db.py:22-26`.
