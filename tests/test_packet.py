from __future__ import annotations

import pytest

from covermail.errors import OuterFrameError
from covermail.protocol.packet import (
    pack_header,
    parse_header,
    unpack_header,
    validate_packet,
)


def test_canonical_header_declares_capsule_length() -> None:
    capsule = b"x" * 97
    header = pack_header(len(capsule))
    assert header == b"a"
    assert parse_header(header + capsule) == (len(capsule), 1)
    assert unpack_header(header) == len(capsule)
    validate_packet(header, capsule)


def test_header_rejects_incomplete_noncanonical_or_wrong_capsule_length() -> None:
    capsule = b"x" * 97
    with pytest.raises(OuterFrameError):
        unpack_header(b"\xe1")
    with pytest.raises(OuterFrameError):
        unpack_header(b"\xe1\x00")
    with pytest.raises(OuterFrameError, match="length"):
        validate_packet(pack_header(len(capsule)), capsule + b"x")
