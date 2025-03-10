import enum
import os
import typing


class RoomTypes(enum.Enum):
    GLOBAL = "GLOBAL"
    PRIVATE = "PRIVATE"

def chunkify(reader_file: typing.IO[bytes], chunk_size: 65536 ) -> typing.Generator[bytes,None,None]:
    ...

# class WriteError(Exception):
#     pass
#
# class FileWriter:
#
#     @staticmethod
#     def writer(*, dst_path: str):  #dst_path = os.path.join(upload_dir, "upload", str(uuid.uuid4())_file_name)
#         try:
#             os.makedirs(os.path.dirname(dst_path), exist_ok=True)
#
#         except Exception as e:
#             raise WriteError(f"Failed to create destination directory") from e
#
#         try:
#             f = open(dst_path, 'wb')
#         except Exception as e:
#             raise WriteError(f"Failed to open destination file") from e
#
#         try:
#             while True:
#                 chunk = yield
#
#                 if not chunk:
#                     break
#
#                 try:
#                     f.write(chunk)
#                 except Exception as e:
#                     raise WriteError(f"Failed to Write chunk") from e
#
#         finally:
#             try:
#                 f.close()
#             except Exception as e:
#                 raise WriteError(f"Failed to close file") from e