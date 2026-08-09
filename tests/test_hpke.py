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
    decrypt_capsule,
    encrypt_capsule,
    hpke_info,
)
from covermail.errors import DecryptionError

PREFIX = tuple(range(32))
HEADER = b"a"


def test_rfc_9180_appendix_a1_base_vector_with_single_shot_empty_aad() -> None:
    private_key = x25519.X25519PrivateKey.from_private_bytes(
        bytes.fromhex("4612c550263fc8ad58375df3f557aac531d26850903e55a9f23f21d8534e8ac8")
    )
    encapsulated_key = bytes.fromhex(
        "37fda3567bdbd628e88668c3c8d7e97d1d1253b6d4ea6d44c150f741f1bf4431"
    )
    ciphertext = bytes.fromhex(
        "f938558b5d72f1a23810b4be2ab4f84331acc02fc97babc53a52ae821807a370ad4546513b00cf03048f6b793c"
    )
    info = bytes.fromhex("4f6465206f6e2061204772656369616e2055726e")
    plaintext = bytes.fromhex("4265617574792069732074727574682c20747275746820626561757479")
    assert HPKE_SUITE.decrypt(encapsulated_key + ciphertext, private_key, info=info) == plaintext


def test_capsule_overhead_round_trip_and_freshness(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    first = encrypt_capsule(validated, b"packet", PREFIX, HEADER)
    second = encrypt_capsule(validated, b"packet", PREFIX, HEADER)
    assert KEM.X25519.enc_length() == HPKE_ENCAPSULATED_KEY_BYTES == 32
    assert len(first) == 6 + HPKE_ENCAPSULATED_KEY_BYTES + HPKE_TAG_BYTES
    assert first != second
    assert decrypt_capsule(validated, private_key, first, PREFIX, HEADER) == b"packet"


def test_info_binds_address_prefix_and_header(address: dict[str, Any]) -> None:
    validated = validate_address(address)
    packet_info = hpke_info(validated, PREFIX, HEADER)
    assert packet_info.startswith(HPKE_INFO_LABEL)
    assert packet_info != hpke_info(validated, PREFIX, b"b")
    assert packet_info != hpke_info(validated, (*PREFIX[:-1], 99), HEADER)


@pytest.mark.parametrize("failure", ["wrong-key", "tamper", "wrong-address", "wrong-prefix"])
def test_authentication_failures_are_generic(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey, failure: str
) -> None:
    validated = validate_address(address)
    capsule = encrypt_capsule(validated, b"secret", PREFIX, HEADER)
    decrypt_address = validated
    decrypt_key = private_key
    prefix = PREFIX
    if failure == "wrong-key":
        decrypt_key = x25519.X25519PrivateKey.generate()
    elif failure == "tamper":
        capsule = capsule[:-1] + bytes([capsule[-1] ^ 1])
    elif failure == "wrong-address":
        changed = copy.deepcopy(address)
        changed["recipient"]["label"] = "Mallory"
        decrypt_address = validate_address(changed)
    else:
        prefix = (*PREFIX[:-1], 99)
    with pytest.raises(DecryptionError, match="not an authentic"):
        decrypt_capsule(decrypt_address, decrypt_key, capsule, prefix, HEADER)
