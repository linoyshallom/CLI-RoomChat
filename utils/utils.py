import typing
from typing import IO

from config import END_OF_MSG_INDICATOR


def chunkify(*, reader_file: IO[bytes], chunk_size: typing.Optional[int] = 65_536) -> typing.Generator[bytes, None, None]:
    while True:
        chunk = reader_file.read(chunk_size)

        if not chunk:
            break

        yield chunk

def split_messages_in_buffer(buffer_msg: str) -> typing.Generator[str, None, None]:
    if END_OF_MSG_INDICATOR in buffer_msg:
        completed_messages = buffer_msg.rsplit(END_OF_MSG_INDICATOR,1)[0]
        yield from completed_messages.split(END_OF_MSG_INDICATOR)


