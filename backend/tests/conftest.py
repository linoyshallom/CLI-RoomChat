import pytest

from server.db.chat_db import ChatDB, ChatDBConfig


@pytest.fixture
def chat_db(tmp_path, monkeypatch) -> ChatDB:
    """A ChatDB backed by a throwaway sqlite file instead of server/db/chat.db."""
    monkeypatch.setattr(ChatDBConfig, "db_path", str(tmp_path / "test_chat.db"))
    db = ChatDB()
    with db.session() as conn:
        db.setup_database(db_conn=conn)
    return db
