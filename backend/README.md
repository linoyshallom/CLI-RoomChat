# CLI--RoomChat
in order to run the program : 
- activate venv
- run `python -m server.app` (or `uvicorn server.app:app --host 127.0.0.1 --port 5000`) to start the chat/file server
- run client (important to run by cmd): `python -m client.client`

## Web UI (single-app deploy)

The server also serves the web UI from the same host:port, once it's built:
- `cd ../UI && npm install && npm run build` (produces `UI/dist`)
- start the server as above - it detects `UI/dist` and serves it at `/`, alongside `/ws/chat` and `/files`

No separate UI server and no CORS setup needed; everything is one process on one port.
