import os

import pytest
from fastapi.testclient import TestClient

import server.app as app_module
from config import ServerConfig
from server.app import app
from server.db.chat_db import ChatDB, ChatDBConfig
from server.rooms import RoomRegistry


@pytest.fixture
def client(tmp_path, monkeypatch):
    """An app instance backed by a throwaway sqlite file and a throwaway uploads dir,
    with a fresh (empty) room registry per test."""
    monkeypatch.setattr(ChatDBConfig, "db_path", str(tmp_path / "test_chat.db"))
    test_db = ChatDB()
    with test_db.session() as conn:
        test_db.setup_database(db_conn=conn)
    monkeypatch.setattr(app_module, "chat_db", test_db)
    monkeypatch.setattr(app_module, "room_registry", RoomRegistry())

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    monkeypatch.setattr(ServerConfig, "upload_dir_dst_path", classmethod(lambda cls: str(uploads_dir)))

    with TestClient(app) as test_client:
        yield test_client


class TestChatWebsocket:
    def test_join_global_room_with_no_history(self, client):
        with client.websocket_connect("/ws/chat?username=alice") as ws:
            ws.send_json({"action": "join", "room_type": "GLOBAL"})
            msg = ws.receive_json()
            assert msg["type"] == "SYSTEM"
            assert "No messages" in msg["text"]

    def test_broadcast_between_two_clients_in_same_room(self, client):
        with client.websocket_connect("/ws/chat?username=alice") as ws_alice:
            ws_alice.send_json({"action": "join", "room_type": "GLOBAL"})
            ws_alice.receive_json()  # no-history system message
            ws_alice.receive_json()  # alice's own join broadcast (she's in the room by then)

            with client.websocket_connect("/ws/chat?username=bob") as ws_bob:
                ws_bob.send_json({"action": "join", "room_type": "GLOBAL"})
                ws_bob.receive_json()  # no-history system message
                ws_bob.receive_json()  # bob's own join broadcast

                # alice sees bob's join broadcast too
                join_msg = ws_alice.receive_json()
                assert "bob" in join_msg["text"]
                assert "joined" in join_msg["text"]

                ws_bob.send_json({"action": "message", "text": "hello from bob"})

                received = ws_alice.receive_json()
                assert received["type"] == "CHAT"
                assert "hello from bob" in received["text"]
                assert "bob" in received["text"]

    def test_private_room_history_filtered_by_join_timestamp(self, client):
        with client.websocket_connect("/ws/chat?username=alice") as ws:
            ws.send_json({"action": "join", "room_type": "PRIVATE", "group_name": "friends"})
            ws.receive_json()  # no-history system message
            ws.send_json({"action": "message", "text": "first message"})
            ws.receive_json()  # broadcast of alice's own message

        # bob joins the same private room after the message was sent - he checks in now,
        # so he should not see history from before his own join timestamp.
        with client.websocket_connect("/ws/chat?username=bob") as ws:
            ws.send_json({"action": "join", "room_type": "PRIVATE", "group_name": "friends"})
            msg = ws.receive_json()
            assert msg["type"] == "SYSTEM"
            assert "No messages" in msg["text"]

    def test_switch_room(self, client):
        with client.websocket_connect("/ws/chat?username=alice") as ws:
            ws.send_json({"action": "join", "room_type": "GLOBAL"})
            ws.receive_json()  # no-history system message
            ws.receive_json()  # alice's own join broadcast

            ws.send_json({"action": "switch"})
            ws.send_json({"action": "join", "room_type": "PRIVATE", "group_name": "friends"})

            msg = ws.receive_json()
            assert msg["type"] == "SYSTEM"
            assert "No messages" in msg["text"]

            assert any(
                c.username == "alice"
                for c in app_module.room_registry._room_name_to_active_clients["friends"]
            )
            assert not any(
                c.username == "alice"
                for c in app_module.room_registry._room_name_to_active_clients["GLOBAL"]
            )

    def test_disconnect_evicts_client_from_room(self, client):
        with client.websocket_connect("/ws/chat?username=alice") as ws:
            ws.send_json({"action": "join", "room_type": "GLOBAL"})
            ws.receive_json()
            assert any(
                c.username == "alice"
                for c in app_module.room_registry._room_name_to_active_clients["GLOBAL"]
            )

        assert not any(
            c.username == "alice"
            for c in app_module.room_registry._room_name_to_active_clients["GLOBAL"]
        )

    def test_invalid_username_is_rejected(self, client):
        # The server accepts the handshake, sends a validation error, then closes -
        # the client only observes the failure on the following receive.
        with client.websocket_connect("/ws/chat?username=has space") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "SYSTEM"
            assert "Invalid username" in msg["text"]
            with pytest.raises(Exception):
                ws.receive_json()


class TestFileTransfer:
    def test_upload_then_download_round_trip(self, client):
        upload_response = client.post("/files", files={"file": ("photo.png", b"some file bytes")})
        assert upload_response.status_code == 200
        file_id = upload_response.json()["file_id"]

        download_response = client.get(f"/files/{file_id}")
        assert download_response.status_code == 200
        assert download_response.content == b"some file bytes"
        assert "photo.png" in download_response.headers["content-disposition"]

    def test_oversized_upload_returns_413_and_leaves_no_partial_file(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(ServerConfig, "max_file_size", 10)

        response = client.post("/files", files={"file": ("big.bin", b"x" * 100)})

        assert response.status_code == 413
        uploads_dir = ServerConfig.upload_dir_dst_path()
        assert os.listdir(uploads_dir) == []

    def test_download_unknown_file_id_returns_404(self, client):
        response = client.get("/files/does-not-exist")
        assert response.status_code == 404
