from __future__ import annotations

import copy
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import x25519
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from covermail.address.schema import validate_address
from covermail.errors import DecryptionError, OuterFrameError
from covermail.service import decrypt_message, encrypt_message

SUBJECT = "Des nouvelles"
PRIMER = "Je voulais justement te donner quelques nouvelles."


def test_end_to_end_round_trip(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    message_id, plaintext = decrypt_message(
        validated,
        private_key,
        encrypt_message(validated, "Rendez-vous à 18 h ? 🔐", SUBJECT, PRIMER),
        SUBJECT,
        PRIMER,
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
    stream = encrypt_message(validated, text, SUBJECT, PRIMER)
    _, recovered = decrypt_message(validated, private_key, stream, SUBJECT, PRIMER)
    assert recovered == text


def test_tamper_fails_authentication(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    stream = bytearray(encrypt_message(validated, "secret", SUBJECT, PRIMER))
    stream[-1] ^= 1
    with pytest.raises(DecryptionError):
        decrypt_message(validated, private_key, bytes(stream), SUBJECT, PRIMER)


def test_wrong_address_fails_before_decryption(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    original = validate_address(address)
    changed = copy.deepcopy(address)
    changed["recipient"]["label"] = "Mallory"
    with pytest.raises(OuterFrameError):
        decrypt_message(
            validate_address(changed),
            private_key,
            encrypt_message(original, "secret", SUBJECT, PRIMER),
            SUBJECT,
            PRIMER,
        )


def test_truncation_and_trailing_bytes_fail(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    stream = encrypt_message(validated, "secret", SUBJECT, PRIMER)
    for malformed in (stream[:-1], stream + b"x"):
        with pytest.raises(OuterFrameError):
            decrypt_message(validated, private_key, malformed, SUBJECT, PRIMER)
