# Build a web chat UI for an existing FastAPI WebSocket backend

You are building **only the frontend**. A backend already exists and must not be changed — build the UI to match its exact wire protocol below. Do not invent extra REST endpoints, auth, or message fields; the backend doesn't have them.

## Overview

It's a multi-room chat app ("RoomChat"): a user picks a username, joins either a global room or a named private room, chats in real time over one WebSocket, and can upload/download files through two plain HTTP endpoints. There are no accounts, passwords, or sessions — a username is just a display name typed at connect time.

Backend runs as a single FastAPI app serving both the WebSocket and the HTTP file routes on **one host:port** (dev default `http://127.0.0.1:5000`). Make the base URL configurable (env var / settings field), don't hardcode it.

**Important — CORS**: if your UI is hosted on a different origin than the backend, the backend currently has no CORS middleware, so the two `fetch`/`XHR` calls to `/files` will be blocked by the browser (WebSocket itself isn't subject to CORS preflight, so `/ws/chat` is unaffected). Flag this to the user — they'll need to add `CORSMiddleware` on the FastAPI side allowing your UI's origin, or you'll need to proxy `/files` through your own dev server. Don't try to work around it purely client-side.

## Connecting

```
ws://<host>:<port>/ws/chat?username=<username>
```

- `username` is a required query param, URL-encoded.
- Allowed characters: letters, digits, `.`, `_` only (regex `^[a-zA-Z0-9._]+$`), min length 1. Validate this client-side before connecting so you can show an inline error instead of relying on the server rejection.
- If the server rejects the username, it sends one `SYSTEM` message (`"Invalid username - only letters, numbers, '.' and '_' are allowed"`) and then closes the socket with code `1008`. Handle that close code as "go back to the username screen with this error."
- On any malformed frame (bad JSON, or valid JSON that fails the schema below), the server sends a `SYSTEM` message `"Malformed message, closing connection"` and closes with code `1008`. Treat 1008 generically as "connection rejected, show the message and return to a safe screen."

## Outbound frames (UI → server, JSON text over the WebSocket)

Exactly three shapes, discriminated by `"action"`. No other fields are read.

**1. Join a room** — send once right after connecting, and again any time the user wants to change rooms:
```json
{ "action": "join", "room_type": "GLOBAL" }
```
or
```json
{ "action": "join", "room_type": "PRIVATE", "group_name": "my-team" }
```
- `room_type` is one of `"GLOBAL"` or `"PRIVATE"` (case-insensitive on the server, but send uppercase to be safe).
- `group_name` is **required** when `room_type` is `PRIVATE` (any non-empty string — this is the room/channel name, freeform, created on first use). Omit it for `GLOBAL`.
- The server holds the connection in a "waiting for join" state until it gets a valid one of these — if it rejects the frame it replies with a `SYSTEM` message and waits for another join frame on the same connection, so on an invalid/incomplete join just re-show the room picker and keep listening, don't reconnect.

**2. Send a chat message** (only valid after a successful join):
```json
{ "action": "message", "text": "hello everyone" }
```
- `text` must be non-empty.

**3. Leave the current room / switch rooms**:
```json
{ "action": "switch" }
```
- This just leaves the current room. The server then expects a fresh `join` frame next (same as the initial connect) — so after sending `switch`, show the room picker again and wait for the user to pick a new room before sending `join`.

There's no explicit "leave app" frame — closing the WebSocket is how a client disconnects for good.

## Inbound frames (server → UI)

Always this shape:
```json
{ "type": "SYSTEM" | "CHAT", "text": "<string>" }
```

- **`SYSTEM`**: status/notification text, e.g. `"[SYSTEM]: alice joined 'GLOBAL' group"`, `"No messages in this chat yet ..."`, `"[SYSTEM]: bob disconnected from 'my-team'"`, error strings. Render distinctly from chat bubbles (e.g. centered gray small text).
- **`CHAT`**: a message line. Two shapes appear in the `text` string depending on what produced it:
  - Live/historical chat messages arrive **pre-formatted as one string**: `"[2026-09-13 14:03:11] [alice]: hello everyone"`.
  - The server does not send sender/timestamp as separate JSON fields — they're baked into `text`. If you want proper chat bubbles (avatar/name on one line, text below, timestamp aligned right) rather than one flat string, parse it client-side with:
    - Chat line: `/^\[(?<timestamp>[^\]]+)\] \[(?<sender>[^\]]+)\]: (?<body>.*)$/`
    - System line (also arrives with a `[SYSTEM]:` prefix baked in even though `type` already says `SYSTEM`): `/^\[SYSTEM\]: (?<body>.*)$/`
  - Fall back to displaying the raw `text` verbatim if a line doesn't match the pattern (be defensive — don't crash the render on an unexpected format).

### What happens right after a successful join

The server replays room history immediately as a burst of `CHAT` frames (or one `SYSTEM` "No messages in this chat yet ..." if the room is empty), **before** any live traffic for that room reaches you. So: clear the message list when you send a `join`, then just append whatever arrives in order — you don't need to sort or de-duplicate, the server orders it correctly (history first, then live). A `SYSTEM` "`<username> joined '<room>' group`" line arrives after history replay, broadcast to everyone already in the room including yourself.

Private-room history is scoped to messages sent **after the user's own first join timestamp** for that group — i.e. a private room's history is personalized per-user, not the full room history. This is expected behavior, not a bug — don't build a "load full history" feature for private rooms.

## File transfer (plain HTTP, not over the WebSocket)

Two REST endpoints on the same host:port as the WebSocket:

**Upload**
```
POST /files
Content-Type: multipart/form-data
field name: "file"
```
Response `200`: `{ "file_id": "file_id-<uuid>-<original-filename>" }`
Response `413`: file exceeded the server's max size (16 MB) — show "file too large."
Response `500`: generic upload failure.

**Download**
```
GET /files/{file_id}
```
Response `200`: binary stream with `Content-Disposition: attachment; filename="..."` and `Content-Type: application/octet-stream` — trigger a normal browser file save using that filename.
Response `404`: unknown/missing file id — show "file not found."

**How file sharing actually works in this app** (important, non-obvious): uploading a file does **not** by itself notify anyone. The convention is:
1. UI uploads the file via `POST /files`, gets back `file_id`.
2. UI then sends that `file_id` as an ordinary chat message: `{ "action": "message", "text": "file_id-xxxxx-report.pdf" }`.
3. Everyone in the room sees it appear as a normal chat line containing the file id string.
4. Any recipient can then `GET /files/{file_id}` to download it.

So the natural UI is: an "attach file" button that uploads on selection, then auto-sends the resulting `file_id` as a chat message (optionally rendered as a distinct "file" chat bubble — you can detect the `file_id-` prefix client-side to show a download button/icon instead of raw text, and wire that button to `GET /files/{file_id}`). This detection is a client-side convenience only; the server has no concept of "file messages," they're indistinguishable from text on the wire.

## Suggested screens/flow

1. **Username screen** — text input, client-side regex validation, "Connect" button. On connect, open the WebSocket with the username query param.
2. **Room picker** — shown right after connecting, and again after a `switch`. Choice of Global or Private; Private reveals a group-name text field. Submits a `join` frame.
3. **Chat screen** — message list (chat bubbles + system notices per the parsing above), text input + send button, attach-file button, a "switch room" control that sends `switch` and returns to the room picker, and a way to leave/close the connection entirely (close the socket).
4. Handle disconnects/reconnects gracefully: on an unexpected socket close that isn't a deliberate user action, show a reconnect prompt rather than silently failing. There's no session resume — reconnecting means going through username → join again.

## Explicitly not in scope for this backend (don't build UI for these)

- No login/password, no per-user auth tokens, no read receipts, no typing indicators, no message editing/deletion, no reactions, no user presence list beyond join/leave system messages, no room listing endpoint (you can't fetch "all existing rooms" — the user must know/type the private room name).
