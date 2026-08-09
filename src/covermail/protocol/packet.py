"""Canonical public length header for one encrypted packet capsule."""

from __future__ import annotations

from covermail.errors import OuterFrameError
from covermail.protocol.varint import decode_uvarint, encode_uvarint

MIN_CAPSULE_BYTES = 51
MAX_CAPSULE_BYTES = 131_072
MAX_HEADER_BYTES = 3


def pack_header(capsule_bytes: int) -> bytes:
    if not MIN_CAPSULE_BYTES <= capsule_bytes <= MAX_CAPSULE_BYTES:
        raise OuterFrameError("capsule length is outside protocol bounds")
    header = encode_uvarint(capsule_bytes)
    if len(header) > MAX_HEADER_BYTES:
        raise OuterFrameError("capsule length header is too large")
    return header


def parse_header(data: bytes) -> tuple[int, int] | None:
    try:
        capsule_bytes, consumed = decode_uvarint(data, max_bytes=MAX_HEADER_BYTES)
    except EOFError:
        return None
    except ValueError as error:
        raise OuterFrameError("invalid capsule length header") from error
    if not MIN_CAPSULE_BYTES <= capsule_bytes <= MAX_CAPSULE_BYTES:
        raise OuterFrameError("capsule length is outside protocol bounds")
    return capsule_bytes, consumed


def unpack_header(header: bytes) -> int:
    parsed = parse_header(header)
    if parsed is None:
        raise OuterFrameError("incomplete capsule length header")
    capsule_bytes, consumed = parsed
    if consumed != len(header):
        raise OuterFrameError("capsule length header has trailing bytes")
    return capsule_bytes


def validate_packet(header: bytes, capsule: bytes) -> None:
    if unpack_header(header) != len(capsule):
        raise OuterFrameError("capsule length does not match header")
