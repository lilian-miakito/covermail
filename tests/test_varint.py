from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from covermail.protocol.varint import decode_uvarint, encode_uvarint


@pytest.mark.parametrize(
    ("value", "encoded"),
    [
        (0, b"\x00"),
        (1, b"\x01"),
        (127, b"\x7f"),
        (128, b"\x80\x01"),
        (16383, b"\xff\x7f"),
        (16384, b"\x80\x80\x01"),
        ((1 << 32) - 1, b"\xff\xff\xff\xff\x0f"),
    ],
)
def test_boundaries(value: int, encoded: bytes) -> None:
    assert encode_uvarint(value) == encoded
    assert decode_uvarint(encoded) == (value, len(encoded))


@given(st.integers(min_value=0, max_value=(1 << 35) - 1))
def test_round_trip(value: int) -> None:
    encoded = encode_uvarint(value)
    assert decode_uvarint(encoded, max_bytes=5) == (value, len(encoded))


@pytest.mark.parametrize("encoded", [b"", b"\x80", b"\x80\x00", b"\x81\x00"])
def test_rejects_incomplete_or_noncanonical(encoded: bytes) -> None:
    with pytest.raises((EOFError, ValueError)):
        decode_uvarint(encoded)


def test_rejects_byte_limit() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        decode_uvarint(b"\x80\x80\x01", max_bytes=2)
