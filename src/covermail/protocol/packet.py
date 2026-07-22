"""Fixed metadata and variable encrypted-body packet framing."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from covermail.errors import OuterFrameError

PACKET_VERSION = 1
METADATA_PLAINTEXT_BYTES = 1 + 4
MAX_BODY_CAPSULE_BYTES = 131_072


@dataclass(frozen=True, slots=True)
class PacketMetadata:
    body_bytes: int


def pack_metadata(body_capsule: bytes) -> bytes:
    if not 1 <= len(body_capsule) <= MAX_BODY_CAPSULE_BYTES:
        raise OuterFrameError("body capsule length is outside protocol bounds")
    return bytes([PACKET_VERSION]) + struct.pack(">I", len(body_capsule))


def unpack_metadata(frame: bytes) -> PacketMetadata:
    if len(frame) != METADATA_PLAINTEXT_BYTES:
        raise OuterFrameError("metadata frame has the wrong fixed length")
    if frame[0] != PACKET_VERSION:
        raise OuterFrameError("unsupported packet metadata version")
    body_bytes = struct.unpack(">I", frame[1:5])[0]
    if not 1 <= body_bytes <= MAX_BODY_CAPSULE_BYTES:
        raise OuterFrameError("metadata body length is outside protocol bounds")
    return PacketMetadata(body_bytes)


def validate_body(metadata: PacketMetadata, body_capsule: bytes) -> None:
    if len(body_capsule) != metadata.body_bytes:
        raise OuterFrameError("body capsule length does not match metadata")
