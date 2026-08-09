from __future__ import annotations

from typing import Any

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.schema import validate_address
from covermail.codec.carrier import decode_carrier, encode_carrier
from covermail.codec.fake_model import FakeLanguageModel


def test_fake_model_abcd_hpke_round_trip(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    model = FakeLanguageModel()
    carrier = encode_carrier(
        "Message carried through the cover text",
        model,
        model,
        model,
        validated,
        random_below=lambda total: 0,
    )
    assert carrier.metrics.prefix_tokens == 64
    assert carrier.metrics.payload_tokens > 0
    decoded = decode_carrier(carrier.text, model, validated, private_key)
    assert decoded.secret == "Message carried through the cover text"
    assert decoded.carrier.prefix_token_ids == carrier.prefix_token_ids


def test_decoder_ignores_a_manually_replaced_finish(
    address: dict[str, Any], private_key: x25519.X25519PrivateKey
) -> None:
    validated = validate_address(address)
    model = FakeLanguageModel()
    carrier = encode_carrier("secret", model, model, model, validated, random_below=lambda total: 0)
    body_end = len(carrier.token_ids) - carrier.metrics.finish_tokens
    edited = model.detokenize(carrier.token_ids[:body_end]) + "finmanuelle"
    decoded = decode_carrier(edited, model, validated, private_key)
    assert decoded.secret == "secret"
    assert decoded.carrier.total_tokens - decoded.carrier.consumed_tokens == 11
