"""Authenticated secret-message frame with bounded raw DEFLATE support."""

from __future__ import annotations

import secrets
import zlib
from collections.abc import Callable

from covermail.errors import InnerFrameError
from covermail.protocol.varint import decode_uvarint, encode_uvarint

INNER_VERSION = 1
FLAG_DEFLATE = 0x01
MAX_SECRET_UTF8_BYTES = 65535
MESSAGE_ID_BYTES = 16


def pack_inner(text: str, *, random_bytes: Callable[[int], bytes] = secrets.token_bytes) -> bytes:
    try:
        plaintext = text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise InnerFrameError("secret is not valid Unicode") from error
    if len(plaintext) > MAX_SECRET_UTF8_BYTES:
        raise InnerFrameError("secret message exceeds protocol limit")

    compressor = zlib.compressobj(level=9, wbits=-15)
    compressed = compressor.compress(plaintext) + compressor.flush()
    if len(compressed) < len(plaintext):
        flags = FLAG_DEFLATE
        body = compressed
    else:
        flags = 0
        body = plaintext

    message_id = random_bytes(MESSAGE_ID_BYTES)
    if len(message_id) != MESSAGE_ID_BYTES:
        raise InnerFrameError("random source returned an invalid message ID")
    return bytes([INNER_VERSION, flags]) + message_id + encode_uvarint(len(plaintext)) + body


def _decompress_exact(body: bytes, original_len: int) -> bytes:
    decompressor = zlib.decompressobj(wbits=-15)
    try:
        plaintext = decompressor.decompress(body, original_len + 1)
        if len(plaintext) > original_len:
            raise InnerFrameError("decompression exceeded declared size")
        plaintext += decompressor.flush(original_len + 1 - len(plaintext))
    except zlib.error as error:
        raise InnerFrameError("malformed compressed stream") from error
    if len(plaintext) > original_len:
        raise InnerFrameError("decompression exceeded declared size")
    if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
        raise InnerFrameError("malformed or trailing compressed stream")
    return plaintext


def unpack_inner(frame: bytes) -> tuple[bytes, str]:
    if len(frame) < 19:
        raise InnerFrameError("inner frame too short")
    version, flags = frame[0], frame[1]
    if version != INNER_VERSION:
        raise InnerFrameError("unsupported inner version")
    if flags & ~FLAG_DEFLATE:
        raise InnerFrameError("reserved inner flags are set")

    message_id = frame[2:18]
    try:
        original_len, consumed = decode_uvarint(frame, 18, max_bytes=3)
    except (EOFError, ValueError) as error:
        raise InnerFrameError("invalid inner plaintext length") from error
    if original_len > MAX_SECRET_UTF8_BYTES:
        raise InnerFrameError("declared plaintext exceeds limit")
    body = frame[18 + consumed :]

    plaintext = _decompress_exact(body, original_len) if flags & FLAG_DEFLATE else body
    if len(plaintext) != original_len:
        raise InnerFrameError("plaintext length mismatch")
    try:
        text = plaintext.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise InnerFrameError("inner plaintext is not valid UTF-8") from error
    return message_id, text
