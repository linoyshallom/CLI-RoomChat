import pytest

from definitions import UserNotFoundError


class TestStoreUser:
    def test_store_user_persists(self, chat_db):
        with chat_db.session() as conn:
            chat_db.store_user(db_conn=conn, sender_name="shalom")
            row = conn.execute("SELECT username FROM users WHERE username = ?", ("shalom",)).fetchone()
        assert row == ("shalom",)

    def test_store_user_duplicate_is_noop(self, chat_db):
        # store_user relies on ON CONFLICT DO NOTHING instead of check-then-insert
        # (avoids a race between concurrent clients picking the same username).
        with chat_db.session() as conn:
            chat_db.store_user(db_conn=conn, sender_name="shalom")
            chat_db.store_user(db_conn=conn, sender_name="shalom")
            count = conn.execute("SELECT COUNT(*) FROM users WHERE username = ?", ("shalom",)).fetchone()[0]
        assert count == 1


class TestRooms:
    def test_create_room_then_lookup_id(self, chat_db):
        with chat_db.session() as conn:
            chat_db.create_room(db_conn=conn, room_name="general")
            room_id = chat_db.get_room_id_from_rooms(db_conn=conn, room_name="general")
        assert room_id is not None

    def test_lookup_missing_room_returns_none(self, chat_db):
        with chat_db.session() as conn:
            room_id = chat_db.get_room_id_from_rooms(db_conn=conn, room_name="does-not-exist")
        assert room_id is None


class TestMessages:
    def test_store_and_retrieve_message(self, chat_db):
        with chat_db.session() as conn:
            chat_db.store_user(db_conn=conn, sender_name="shalom")
            chat_db.create_room(db_conn=conn, room_name="general")
            chat_db.store_message(
                db_conn=conn,
                text_message="hello world",
                sender_name="shalom",
                room_name="general",
                timestamp="2026-08-15 10:00:00",
            )
            messages = list(chat_db.send_previous_messages_in_room(db_conn=conn, room_name="general"))

        assert len(messages) == 1
        assert "hello world" in messages[0]
        assert "shalom" in messages[0]

    def test_send_previous_messages_filters_by_join_timestamp(self, chat_db):
        with chat_db.session() as conn:
            chat_db.store_user(db_conn=conn, sender_name="shalom")
            chat_db.create_room(db_conn=conn, room_name="general")
            chat_db.store_message(
                db_conn=conn, text_message="before", sender_name="shalom",
                room_name="general", timestamp="2026-08-15 09:00:00",
            )
            chat_db.store_message(
                db_conn=conn, text_message="after", sender_name="shalom",
                room_name="general", timestamp="2026-08-15 11:00:00",
            )
            messages = list(chat_db.send_previous_messages_in_room(
                db_conn=conn, room_name="general", join_timestamp="2026-08-15 10:00:00",
            ))

        assert len(messages) == 1
        assert "after" in messages[0]

    def test_store_message_for_unknown_sender_raises(self, chat_db):
        with chat_db.session() as conn:
            chat_db.create_room(db_conn=conn, room_name="general")
            with pytest.raises(UserNotFoundError):
                chat_db.store_message(
                    db_conn=conn, text_message="hi", sender_name="ghost",
                    room_name="general", timestamp="2026-08-15 10:00:00",
                )


class TestRoomCheckins:
    def test_checkin_then_get_join_timestamp(self, chat_db):
        with chat_db.session() as conn:
            chat_db.store_user(db_conn=conn, sender_name="shalom")
            chat_db.create_room(db_conn=conn, room_name="private-room")
            chat_db.create_user_checkin_room(
                db_conn=conn, sender_name="shalom", room_name="private-room",
                join_timestamp="2026-08-15 10:00:00",
            )
            join_ts = chat_db.get_user_join_timestamp(db_conn=conn, sender_name="shalom", room_name="private-room")
        assert join_ts == "2026-08-15 10:00:00"

    def test_get_join_timestamp_before_checkin_returns_none(self, chat_db):
        with chat_db.session() as conn:
            chat_db.store_user(db_conn=conn, sender_name="shalom")
            chat_db.create_room(db_conn=conn, room_name="private-room")
            join_ts = chat_db.get_user_join_timestamp(db_conn=conn, sender_name="shalom", room_name="private-room")
        assert join_ts is None

    def test_duplicate_checkin_keeps_first_timestamp(self, chat_db):
        with chat_db.session() as conn:
            chat_db.store_user(db_conn=conn, sender_name="shalom")
            chat_db.create_room(db_conn=conn, room_name="private-room")
            chat_db.create_user_checkin_room(
                db_conn=conn, sender_name="shalom", room_name="private-room",
                join_timestamp="2026-08-15 10:00:00",
            )
            chat_db.create_user_checkin_room(
                db_conn=conn, sender_name="shalom", room_name="private-room",
                join_timestamp="2026-08-15 12:00:00",
            )
            join_ts = chat_db.get_user_join_timestamp(db_conn=conn, sender_name="shalom", room_name="private-room")
        assert join_ts == "2026-08-15 10:00:00"


class TestFiles:
    def test_store_and_get_file_record(self, chat_db):
        with chat_db.session() as conn:
            chat_db.store_file_in_files(db_conn=conn, file_path="C:\\Uploads\\abc.png", file_id="abc123", file_name="photo.png")
            record = chat_db.get_file_record_by_file_id(db_conn=conn, file_id="abc123")
        assert record == ("C:\\Uploads\\abc.png", "photo.png")

    def test_get_file_record_missing_id_returns_none(self, chat_db):
        with chat_db.session() as conn:
            record = chat_db.get_file_record_by_file_id(db_conn=conn, file_id="does-not-exist")
        assert record is None
