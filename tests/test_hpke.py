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
    HPKE_SUITE,
    HPKE_TAG_BYTES,
    decrypt_inner,
    encrypt_inner,
    hpke_info,
)
from covermail.errors import DecryptionError


def test_rfc_9180_appendix_a1_base_vector_with_single_shot_empty_aad() -> None:
    """Use RFC 9180 A.1 values, adapting only AAD to the single-shot API's empty AAD."""
    private_key = x25519.X25519PrivateKey.from_private_bytes(
        bytes.fromhex("4612c550263fc8ad58375df3f557aac531d26850903e55a9f23f21d8534e8ac8")
    )
    encapsulated_key = bytes.fromhex(
        "37fda3567bdbd628e88668c3c8d7e97d1d1253b6d4ea6d44c150f741f1bf4431"
    )
    # A.1's sequence-0 plaintext encrypted under its published key/base_nonce
    # with empty AAD, because Suite.decrypt() intentionally exposes no AAD parameter.
    ciphertext = bytes.fromhex(
        "f938558b5d72f1a23810b4be2ab4f84331acc02fc97babc53a52ae821807a370"
        "ad4546513b00cf03048f6b793c"
    )
    info = bytes.fromhex("4f6465206f6e2061204772656369616e2055726e")
    plaintext = bytes.fromhex("4265617574792069732074727574682c20747275746820626561757479")
    assert HPKE_SUITE.decrypt(encapsulated_key + ciphertext, private_key, info=info) == plaintext


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
