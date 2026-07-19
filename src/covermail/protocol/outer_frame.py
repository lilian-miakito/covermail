"""Address-bound outer payload."""

from __future__ import annotations

import hmac

from covermail.address.fingerprint import address_id
from covermail.address.schema import Address
from covermail.errors import OuterFrameError, WrongAddressError

PROTOCOL_VERSION = 1
ADDRESS_ID_LENGTH = 16
OUTER_HEADER_LENGTH = 1 + ADDRESS_ID_LENGTH
MAX_STEGO_PAYLOAD_BYTES = 131072


def outer_header(address: Address) -> bytes:
    return bytes([PROTOCOL_VERSION]) + address_id(address)


def build_outer_payload(address: Address, hpke_blob: bytes) -> bytes:
    payload = outer_header(address) + hpke_blob
    if len(payload) > MAX_STEGO_PAYLOAD_BYTES:
        raise OuterFrameError("outer payload exceeds protocol limit")
    return payload


def parse_outer_payload(address: Address, payload: bytes) -> bytes:
    if len(payload) < OUTER_HEADER_LENGTH:
        raise OuterFrameError("outer payload is too short")
    if payload[0] != PROTOCOL_VERSION:
        raise OuterFrameError("unsupported protocol version")
    if not hmac.compare_digest(payload[1:OUTER_HEADER_LENGTH], address_id(address)):
        raise WrongAddressError("outer payload is for another address")
    return payload[OUTER_HEADER_LENGTH:]
