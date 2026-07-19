from __future__ import annotations

import copy
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from covermail.address.schema import validate_address
from covermail.errors import OuterFrameError, WrongAddressError
from covermail.protocol.outer_frame import (
    MAX_STEGO_PAYLOAD_BYTES,
    build_outer_payload,
    pack_stego_frame,
    parse_outer_payload,
    unpack_stego_frame,
)


@given(st.binary(max_size=4096))
def test_stego_frame_property(payload: bytes) -> None:
    assert unpack_stego_frame(pack_stego_frame(payload)) == payload


def test_outer_payload_round_trip(address: dict[str, Any]) -> None:
    validated = validate_address(address)
    payload = build_outer_payload(validated, b"hpke")
    assert parse_outer_payload(validated, payload) == b"hpke"


def test_wrong_address_fails(address: dict[str, Any]) -> None:
    original = validate_address(address)
    changed = copy.deepcopy(address)
    changed["recipient"]["label"] = "Mallory"
    other = validate_address(changed)
    with pytest.raises(WrongAddressError):
        parse_outer_payload(other, build_outer_payload(original, b"hpke"))


@pytest.mark.parametrize(
    "frame",
    [
        b"",
        b"\x80",
        b"\x80\x00",
        b"\x02x",
        b"\x01xy",
        b"\x81\x80\x08",
    ],
)
def test_malformed_stego_frames_fail(frame: bytes) -> None:
    with pytest.raises(OuterFrameError):
        unpack_stego_frame(frame)


def test_payload_hard_limit() -> None:
    with pytest.raises(OuterFrameError, match="exceeds"):
        pack_stego_frame(b"x" * (MAX_STEGO_PAYLOAD_BYTES + 1))


def test_protocol_version_checked(address: dict[str, Any]) -> None:
    validated = validate_address(address)
    payload = bytearray(build_outer_payload(validated, b"hpke"))
    payload[0] = 2
    with pytest.raises(OuterFrameError, match="version"):
        parse_outer_payload(validated, bytes(payload))
