from __future__ import annotations

import copy
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.hpke import KEM

from covermail.address.schema import validate_address
from covermail.crypto.hpke import (
    HPKE_ENCAPSULATED_KEY_BYTES,
    HPKE_INFO_LABEL,
    HPKE_TAG_BYTES,
    decrypt_inner,
    encrypt_inner,
    hpke_info,
)
from covermail.errors import DecryptionError


def test_fixed_suite_overhead_and_round_trip(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    plaintext = b"authenticated inner frame"
    blob = encrypt_inner(validated, plaintext)
    assert KEM.X25519.enc_length() == HPKE_ENCAPSULATED_KEY_BYTES == 32
    assert len(blob) == len(plaintext) + HPKE_ENCAPSULATED_KEY_BYTES + HPKE_TAG_BYTES
    assert decrypt_inner(validated, private_key, blob) == plaintext


def test_fresh_ephemeral_key_each_time(address: dict[str, Any]) -> None:
    validated = validate_address(address)
    first = encrypt_inner(validated, b"same")
    second = encrypt_inner(validated, b"same")
    assert first != second
    assert first[:32] != second[:32]


def test_info_is_address_bound(address: dict[str, Any]) -> None:
    validated = validate_address(address)
    info = hpke_info(validated)
    assert info.startswith(HPKE_INFO_LABEL)
    assert len(info) == len(HPKE_INFO_LABEL) + 32 + 17


@pytest.mark.parametrize("failure", ["wrong-key", "tamper", "wrong-info"])
def test_authentication_failures_are_generic(
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
    failure: str,
) -> None:
    validated = validate_address(address)
    blob = encrypt_inner(validated, b"secret")
    decrypt_address = validated
    decrypt_key = private_key
    if failure == "wrong-key":
        decrypt_key = x25519.X25519PrivateKey.generate()
    elif failure == "tamper":
        blob = blob[:-1] + bytes([blob[-1] ^ 1])
    else:
        changed = copy.deepcopy(address)
        changed["recipient"]["label"] = "Mallory"
        decrypt_address = validate_address(changed)
    with pytest.raises(DecryptionError, match="not an authentic"):
        decrypt_inner(decrypt_address, decrypt_key, blob)
