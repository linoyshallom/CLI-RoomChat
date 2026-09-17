import typing
from typing import IO


def chunkify(*, reader_file: IO[bytes], chunk_size: typing.Optional[int] = 65_536) -> typing.Generator[bytes, None, None]:
    while True:
        chunk = reader_file.read(chunk_size)

        if not chunk:
            break

        yield chunk

