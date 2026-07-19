from __future__ import annotations

import copy
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.schema import validate_address
from covermail.errors import DecryptionError, OuterFrameError
from covermail.protocol.v2_frame import (
    V2StreamLengthResolver,
    pack_v2_stream,
    unpack_v2_stream,
)
from covermail.service_v2 import decrypt_message_v2, encrypt_message_v2

SUBJECT = "Des nouvelles du jardin"
PRIMER = "Je voulais te raconter calmement ce qui s'est passé."


def _v2_address(address: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(address)
    result["codec"]["id"] = "cm-arithmetic-v2"
    result["codec"]["length_bias_milli"] = 0
    result["codec"]["prompt_template"] = "cm-email-continue-primer-v2"
    return validate_address(result)


def test_v2_stream_random_prefix_masked_length_and_round_trip(
    address: dict[str, Any],
) -> None:
    validated = _v2_address(address)
    hpke_blob = bytes(range(32)) + b"ciphertext-and-tag"
    stream = pack_v2_stream(validated, hpke_blob, SUBJECT, PRIMER)
    assert stream[:32] == bytes(range(32))
    assert stream[32] != len(stream) - 33
    resolver = V2StreamLengthResolver(validated, SUBJECT, PRIMER)
    assert resolver.resolve(stream[:32]) is None
    assert resolver.resolve(stream[:33]) == len(stream)
    assert unpack_v2_stream(validated, stream, SUBJECT, PRIMER) == hpke_blob


def test_v2_stream_context_or_tamper_fails(address: dict[str, Any]) -> None:
    validated = _v2_address(address)
    hpke_blob = bytes(range(32)) + b"ciphertext-and-tag"
    stream = pack_v2_stream(validated, hpke_blob, SUBJECT, PRIMER)
    with pytest.raises(OuterFrameError):
        unpack_v2_stream(validated, stream, "Autre sujet", PRIMER)
    tampered = stream[:-1] + bytes([stream[-1] ^ 1])
    # Framing is only uniformization; HPKE supplies authentication. Structure
    # remains parseable here and produces a different authenticated blob.
    assert unpack_v2_stream(validated, tampered, SUBJECT, PRIMER) != hpke_blob


def test_v2_hpke_binds_subject_and_primer(
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
) -> None:
    validated = _v2_address(address)
    stream = encrypt_message_v2(validated, "Secret v2 🔐", SUBJECT, PRIMER)
    assert decrypt_message_v2(validated, private_key, stream, SUBJECT, PRIMER)[1] == "Secret v2 🔐"
    with pytest.raises((DecryptionError, OuterFrameError)):
        decrypt_message_v2(validated, private_key, stream, "Autre sujet", PRIMER)
    with pytest.raises((DecryptionError, OuterFrameError)):
        decrypt_message_v2(
            validated,
            private_key,
            stream,
            SUBJECT,
            "Je voulais te raconter autre chose aujourd'hui.",
        )
