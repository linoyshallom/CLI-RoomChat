import pytest
from pydantic import ValidationError

from definitions import UsernameData, SetupRoomData, UploadFileData, DownloadFileData


class TestUsernameData:
    @pytest.mark.parametrize("username", ["shalom", "shalom_31", "User.Name123"])
    def test_valid_usernames_accepted(self, username):
        assert UsernameData(username=username).username == username

    @pytest.mark.parametrize(
        "username",
        [
            "",              # empty
            "has space",     # spaces not allowed by pattern
            "semi;colon",
            "quote'here",
            "emoji😀name",
        ],
    )
    def test_invalid_usernames_rejected(self, username):
        with pytest.raises(ValidationError):
            UsernameData(username=username)


class TestSetupRoomData:
    def test_global_room_without_group_name(self):
        data = SetupRoomData(room_type="GLOBAL")
        assert data.group_name is None

    def test_private_room_with_group_name(self):
        data = SetupRoomData(room_type="PRIVATE", group_name="friends")
        assert data.group_name == "friends"

    def test_missing_room_type_rejected(self):
        with pytest.raises(ValidationError):
            SetupRoomData()


class TestUploadFileData:
    def test_valid_upload(self):
        data = UploadFileData(filename="photo.png", file_size=1024)
        assert data.file_size == 1024

    @pytest.mark.parametrize("bad_size", ["not-a-number", None])
    def test_invalid_file_size_rejected(self, bad_size):
        with pytest.raises(ValidationError):
            UploadFileData(filename="photo.png", file_size=bad_size)

    def test_missing_filename_rejected(self):
        with pytest.raises(ValidationError):
            UploadFileData(file_size=1024)


class TestDownloadFileData:
    def test_valid_download(self):
        data = DownloadFileData(file_id="abc123", dst_path="C:\\Downloads\\photo.png")
        assert data.file_id == "abc123"

    def test_missing_fields_rejected(self):
        with pytest.raises(ValidationError):
            DownloadFileData(file_id="abc123")
