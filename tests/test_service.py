from __future__ import annotations

import copy
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import x25519
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from covermail.address.schema import validate_address
from covermail.errors import DecryptionError, OuterFrameError, WrongAddressError
from covermail.service import decrypt_message, encrypt_message


def test_end_to_end_round_trip(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    message_id, plaintext = decrypt_message(
        validated,
        private_key,
        encrypt_message(validated, "Rendez-vous à 18 h ? 🔐"),
    )
    assert len(message_id) == 16
    assert plaintext == "Rendez-vous à 18 h ? 🔐"


@given(text=st.text(alphabet=st.characters(codec="utf-8"), max_size=1000))
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_end_to_end_unicode_property(
    text: str,
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
) -> None:
    validated = validate_address(address)
    _, recovered = decrypt_message(validated, private_key, encrypt_message(validated, text))
    assert recovered == text


def test_tamper_fails_authentication(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    frame = bytearray(encrypt_message(validated, "secret"))
    frame[-1] ^= 1
    with pytest.raises(DecryptionError):
        decrypt_message(validated, private_key, bytes(frame))


def test_wrong_address_fails_before_decryption(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    original = validate_address(address)
    changed = copy.deepcopy(address)
    changed["recipient"]["label"] = "Mallory"
    with pytest.raises(WrongAddressError):
        decrypt_message(validate_address(changed), private_key, encrypt_message(original, "secret"))


def test_truncation_and_trailing_bytes_fail(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    frame = encrypt_message(validated, "secret")
    for malformed in (frame[:-1], frame + b"x"):
        with pytest.raises(OuterFrameError):
            decrypt_message(validated, private_key, malformed)
