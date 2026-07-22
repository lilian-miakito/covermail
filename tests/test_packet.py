from __future__ import annotations

import pytest

from covermail.errors import OuterFrameError
from covermail.protocol.packet import (
    METADATA_PLAINTEXT_BYTES,
    pack_metadata,
    unpack_metadata,
    validate_body,
)


def test_fixed_metadata_declares_body_length() -> None:
    body = b"encrypted body capsule"
    frame = pack_metadata(body)
    assert len(frame) == METADATA_PLAINTEXT_BYTES == 5
    metadata = unpack_metadata(frame)
    assert metadata.body_bytes == len(body)
    validate_body(metadata, body)


def test_metadata_rejects_wrong_size_version_length_or_body() -> None:
    body = b"body"
    frame = pack_metadata(body)
    malformed_values = (
        frame[:-1],
        bytes([2]) + frame[1:],
        frame[:1] + b"\0\0\0\0",
    )
    for malformed in malformed_values:
        with pytest.raises(OuterFrameError):
            unpack_metadata(malformed)
    with pytest.raises(OuterFrameError, match="length"):
        validate_body(unpack_metadata(frame), b"copies")
