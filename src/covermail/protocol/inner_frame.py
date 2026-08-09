"""Authenticated secret-message frame with bounded raw DEFLATE support."""

from __future__ import annotations

import zlib

from covermail.errors import InnerFrameError
from covermail.protocol.varint import decode_uvarint, encode_uvarint

INNER_VERSION = 1
FLAG_DEFLATE = 0x01
MAX_SECRET_UTF8_BYTES = 65535


def pack_inner(text: str) -> bytes:
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

    return bytes([INNER_VERSION, flags]) + encode_uvarint(len(plaintext)) + body


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


def unpack_inner(frame: bytes) -> str:
    if len(frame) < 3:
        raise InnerFrameError("inner frame too short")
    version, flags = frame[0], frame[1]
    if version != INNER_VERSION:
        raise InnerFrameError("unsupported inner version")
    if flags & ~FLAG_DEFLATE:
        raise InnerFrameError("reserved inner flags are set")

    try:
        original_len, consumed = decode_uvarint(frame, 2, max_bytes=3)
    except (EOFError, ValueError) as error:
        raise InnerFrameError("invalid inner plaintext length") from error
    if original_len > MAX_SECRET_UTF8_BYTES:
        raise InnerFrameError("declared plaintext exceeds limit")
    body = frame[2 + consumed :]

    plaintext = _decompress_exact(body, original_len) if flags & FLAG_DEFLATE else body
    if len(plaintext) != original_len:
        raise InnerFrameError("plaintext length mismatch")
    try:
        text = plaintext.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise InnerFrameError("inner plaintext is not valid UTF-8") from error
    return text
