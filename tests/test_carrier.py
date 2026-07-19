from __future__ import annotations

from typing import Any

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.schema import validate_address
from covermail.codec.carrier import decode_carrier, encode_carrier
from covermail.codec.fake_model import FakeLanguageModel
from covermail.service import decrypt_message, encrypt_message


def test_fake_model_primer_stream_and_hpke_round_trip(
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
) -> None:
    validated = validate_address(address)
    subject = "Sujet du quotidien"
    primer = "abc."
    model = FakeLanguageModel()
    primer_ids = tuple(model.tokenize(primer))
    stream = encrypt_message(validated, "Message à travers le carrier", subject, primer)
    carrier = encode_carrier(
        stream,
        model,
        validated,
        subject,
        primer,
        primer_ids,
    )
    assert carrier.text.startswith(primer)
    assert carrier.metrics.primer_tokens == len(primer_ids)
    recovered = decode_carrier(
        carrier.text,
        model,
        validated,
        subject,
        primer,
        primer_ids,
    )
    assert recovered == stream
    assert decrypt_message(validated, private_key, recovered, subject, primer)[1] == (
        "Message à travers le carrier"
    )
