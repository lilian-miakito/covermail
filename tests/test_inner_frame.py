from __future__ import annotations

import zlib
from contextlib import suppress

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from covermail.errors import InnerFrameError
from covermail.protocol.inner_frame import (
    FLAG_DEFLATE,
    MAX_SECRET_UTF8_BYTES,
    pack_inner,
    unpack_inner,
)
from covermail.protocol.varint import encode_uvarint

MESSAGE_ID = bytes(range(16))


@pytest.mark.parametrize("text", ["", "bonjour", "émoji 😀", "a" * 1000])
def test_inner_round_trip(text: str) -> None:
    frame = pack_inner(text, random_bytes=lambda size: MESSAGE_ID)
    assert unpack_inner(frame) == (MESSAGE_ID, text)


def test_compression_is_used_only_when_shorter() -> None:
    compressed = pack_inner("a" * 1000, random_bytes=lambda size: MESSAGE_ID)
    raw = pack_inner("x", random_bytes=lambda size: MESSAGE_ID)
    assert compressed[1] == FLAG_DEFLATE
    assert raw[1] == 0


@given(st.text(alphabet=st.characters(codec="utf-8"), max_size=2000))
@settings(max_examples=100)
def test_unicode_property_round_trip(text: str) -> None:
    frame = pack_inner(text, random_bytes=lambda size: MESSAGE_ID)
    assert unpack_inner(frame) == (MESSAGE_ID, text)


def test_secret_limit() -> None:
    with pytest.raises(InnerFrameError, match="exceeds"):
        pack_inner("a" * (MAX_SECRET_UTF8_BYTES + 1))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda frame: b"",
        lambda frame: bytes([2]) + frame[1:],
        lambda frame: frame[:1] + b"\x80" + frame[2:],
        lambda frame: frame[:18] + b"\x80\x00" + frame[19:],
        lambda frame: frame[:-1],
    ],
)
def test_malformed_frames_fail(mutate: object) -> None:
    frame = pack_inner("hello", random_bytes=lambda size: MESSAGE_ID)
    with pytest.raises(InnerFrameError):
        unpack_inner(mutate(frame))  # type: ignore[operator]


def _compressed_frame(plaintext_len: int, compressed_body: bytes) -> bytes:
    return b"\x01\x01" + MESSAGE_ID + encode_uvarint(plaintext_len) + compressed_body


def test_rejects_decompression_bomb() -> None:
    compressor = zlib.compressobj(level=9, wbits=-15)
    body = compressor.compress(b"A" * 100_000) + compressor.flush()
    with pytest.raises(InnerFrameError, match="exceeded"):
        unpack_inner(_compressed_frame(10, body))


def test_rejects_trailing_compressed_data() -> None:
    compressor = zlib.compressobj(level=9, wbits=-15)
    body = compressor.compress(b"hello") + compressor.flush()
    with pytest.raises(InnerFrameError, match="trailing"):
        unpack_inner(_compressed_frame(5, body + b"junk"))


def test_rejects_truncated_compressed_data() -> None:
    compressor = zlib.compressobj(level=9, wbits=-15)
    body = compressor.compress(b"hello" * 100) + compressor.flush()
    with pytest.raises(InnerFrameError, match="malformed"):
        unpack_inner(_compressed_frame(500, body[:-1]))


def test_rejects_invalid_utf8() -> None:
    frame = b"\x01\x00" + MESSAGE_ID + b"\x01\xff"
    with pytest.raises(InnerFrameError, match="UTF-8"):
        unpack_inner(frame)


def test_rejects_wrong_declared_raw_length() -> None:
    frame = b"\x01\x00" + MESSAGE_ID + b"\x02x"
    with pytest.raises(InnerFrameError, match="length mismatch"):
        unpack_inner(frame)


@given(st.binary(max_size=256))
def test_arbitrary_inner_frames_never_leak_parser_exceptions(frame: bytes) -> None:
    with suppress(InnerFrameError):
        unpack_inner(frame)
