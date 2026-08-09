from __future__ import annotations

import copy
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import x25519
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from covermail.address.schema import validate_address
from covermail.errors import DecryptionError, OuterFrameError
from covermail.protocol.inner_frame import pack_inner
from covermail.protocol.packet import pack_header
from covermail.service import EncryptedPacket, decrypt_message, encrypt_message

PREFIX = tuple(range(32))


def test_end_to_end_packet_round_trip(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    packet = encrypt_message(validated, "Meet me at 6 p.m. 🔐", PREFIX)
    message_id, plaintext = decrypt_message(validated, private_key, packet, PREFIX)
    assert len(message_id) == 16
    assert plaintext == "Meet me at 6 p.m. 🔐"


@given(text=st.text(alphabet=st.characters(codec="utf-8"), max_size=1000))
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_end_to_end_unicode_property(
    text: str, address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    packet = encrypt_message(validated, text, PREFIX)
    assert decrypt_message(validated, private_key, packet, PREFIX)[1] == text


def test_header_or_capsule_tamper_fails(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    packet = encrypt_message(validated, "secret", PREFIX)
    malformed = (
        EncryptedPacket(bytes([packet.header[0] + 1]), packet.capsule),
        EncryptedPacket(
            packet.header,
            packet.capsule[:-1] + bytes([packet.capsule[-1] ^ 1]),
        ),
    )
    for value in malformed:
        with pytest.raises((DecryptionError, OuterFrameError)):
            decrypt_message(validated, private_key, value, PREFIX)


def test_authenticated_header_cannot_be_replaced(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    packet = encrypt_message(validated, "secret", PREFIX)
    extended_capsule = packet.capsule + b"\x00"
    replaced_header = pack_header(len(extended_capsule))
    with pytest.raises(DecryptionError):
        decrypt_message(
            validated,
            private_key,
            EncryptedPacket(replaced_header, extended_capsule),
            PREFIX,
        )


def test_packet_has_one_hpke_overhead(
    address: dict[str, Any],
) -> None:
    validated = validate_address(address)
    secret = "A short carrier payload with no second capsule."
    packet = encrypt_message(validated, secret, PREFIX)
    assert len(packet.capsule) == len(pack_inner(secret)) + 48
    assert packet.header == pack_header(len(packet.capsule))


def test_message_id_is_derived_from_the_capsule(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    first = encrypt_message(validated, "secret", PREFIX)
    second = encrypt_message(validated, "secret", PREFIX)
    first_id = decrypt_message(validated, private_key, first, PREFIX)[0]
    second_id = decrypt_message(validated, private_key, second, PREFIX)[0]
    assert len(first_id) == 16
    assert first_id != second_id


def test_wrong_address_or_prefix_fails(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    original = validate_address(address)
    packet = encrypt_message(original, "secret", PREFIX)
    changed = copy.deepcopy(address)
    changed["recipient"]["label"] = "Mallory"
    with pytest.raises(DecryptionError):
        decrypt_message(validate_address(changed), private_key, packet, PREFIX)
    with pytest.raises(DecryptionError):
        decrypt_message(original, private_key, packet, (*PREFIX[:-1], 99))
