from __future__ import annotations

import copy
from typing import Any

import pytest

from covermail.address.schema import validate_address
from covermail.errors import OuterFrameError, WrongAddressError
from covermail.protocol.outer_frame import (
    MAX_STEGO_PAYLOAD_BYTES,
    build_outer_payload,
    parse_outer_payload,
)


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


def test_outer_payload_hard_limit(address: dict[str, Any]) -> None:
    validated = validate_address(address)
    with pytest.raises(OuterFrameError, match="exceeds"):
        build_outer_payload(validated, b"x" * MAX_STEGO_PAYLOAD_BYTES)


def test_protocol_version_checked(address: dict[str, Any]) -> None:
    validated = validate_address(address)
    payload = bytearray(build_outer_payload(validated, b"hpke"))
    payload[0] = 2
    with pytest.raises(OuterFrameError, match="version"):
        parse_outer_payload(validated, bytes(payload))
