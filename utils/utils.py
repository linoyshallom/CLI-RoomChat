import socket
import struct
import typing
from typing import IO


def chunkify(*, reader_file: IO[bytes], chunk_size: typing.Optional[int] = 65_536) -> typing.Generator[bytes, None, None]:
    while True:
        chunk = reader_file.read(chunk_size)

        if not chunk:
            break

        yield chunk


def recv_exact(sock: socket.socket, num_bytes: int) -> bytes:
    """Reads exactly num_bytes from sock. A single recv() can return fewer bytes than
    requested (TCP is a byte stream, not a message stream), so this loops until enough
    data has actually arrived."""
    chunks = []
    remaining = num_bytes
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Socket closed before the expected data was fully received")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def send_framed(sock: socket.socket, payload: bytes) -> None:
    """Sends payload prefixed with a 4-byte big-endian length header, so recv_framed on the
    other end reads exactly this message regardless of how TCP happens to batch consecutive
    sends on the wire."""
    sock.sendall(struct.pack("!I", len(payload)) + payload)


def recv_framed(sock: socket.socket) -> bytes:
    """Reads one length-prefixed message written by send_framed."""
    header = recv_exact(sock, 4)
    (length,) = struct.unpack("!I", header)
    return recv_exact(sock, length)

