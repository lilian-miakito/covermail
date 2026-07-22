from __future__ import annotations

import copy
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import x25519
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from covermail.address.schema import validate_address
from covermail.errors import DecryptionError, OuterFrameError
from covermail.service import EncryptedPacket, decrypt_message, encrypt_message

PREFIX = tuple(range(32))


def test_end_to_end_packet_round_trip(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    packet = encrypt_message(validated, "Rendez-vous à 18 h ? 🔐", PREFIX)
    message_id, plaintext = decrypt_message(validated, private_key, packet, PREFIX)
    assert len(message_id) == 16
    assert plaintext == "Rendez-vous à 18 h ? 🔐"


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


def test_metadata_or_body_tamper_fails(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    packet = encrypt_message(validated, "secret", PREFIX)
    malformed = (
        EncryptedPacket(packet.metadata[:-1] + bytes([packet.metadata[-1] ^ 1]), packet.body),
        EncryptedPacket(packet.metadata, packet.body[:-1] + bytes([packet.body[-1] ^ 1])),
    )
    for value in malformed:
        with pytest.raises((DecryptionError, OuterFrameError)):
            decrypt_message(validated, private_key, value, PREFIX)


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
