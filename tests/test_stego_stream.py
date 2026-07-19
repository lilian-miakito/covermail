from __future__ import annotations

from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.schema import validate_address
from covermail.errors import DecryptionError, OuterFrameError
from covermail.protocol.stego_stream import StreamLengthResolver, pack_stream, unpack_stream
from covermail.service import decrypt_message, encrypt_message

SUBJECT = "Des nouvelles du jardin"
PRIMER = "Je voulais te raconter calmement ce qui s'est passé."


def test_stream_random_prefix_masked_length_and_round_trip(address: dict[str, Any]) -> None:
    validated = validate_address(address)
    hpke_blob = bytes(range(32)) + b"ciphertext-and-tag"
    stream = pack_stream(validated, hpke_blob, SUBJECT, PRIMER)
    assert stream[:32] == bytes(range(32))
    assert stream[32] != len(stream) - 33
    resolver = StreamLengthResolver(validated, SUBJECT, PRIMER)
    assert resolver.resolve(stream[:32]) is None
    assert resolver.resolve(stream[:33]) == len(stream)
    assert unpack_stream(validated, stream, SUBJECT, PRIMER) == hpke_blob


def test_stream_context_or_tamper_fails(address: dict[str, Any]) -> None:
    validated = validate_address(address)
    hpke_blob = bytes(range(32)) + b"ciphertext-and-tag"
    stream = pack_stream(validated, hpke_blob, SUBJECT, PRIMER)
    with pytest.raises(OuterFrameError):
        unpack_stream(validated, stream, "Autre sujet", PRIMER)
    tampered = stream[:-1] + bytes([stream[-1] ^ 1])
    assert unpack_stream(validated, tampered, SUBJECT, PRIMER) != hpke_blob


def test_hpke_binds_subject_and_primer(
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
) -> None:
    validated = validate_address(address)
    stream = encrypt_message(validated, "Secret 🔐", SUBJECT, PRIMER)
    assert decrypt_message(validated, private_key, stream, SUBJECT, PRIMER)[1] == "Secret 🔐"
    with pytest.raises((DecryptionError, OuterFrameError)):
        decrypt_message(validated, private_key, stream, "Autre sujet", PRIMER)
    with pytest.raises((DecryptionError, OuterFrameError)):
        decrypt_message(
            validated,
            private_key,
            stream,
            SUBJECT,
            "Je voulais te raconter autre chose aujourd'hui.",
        )
