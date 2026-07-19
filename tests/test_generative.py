from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import x25519
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from covermail.address.schema import validate_address
from covermail.codec.fake_model import FakeLanguageModel
from covermail.codec.generative import decode_carrier, encode_carrier
from covermail.errors import (
    CarrierArithmeticError,
    CarrierGenerationError,
    CarrierStructureError,
    CovermailError,
)
from covermail.protocol.outer_frame import pack_stego_frame
from covermail.service import decrypt_message, encrypt_message


@given(st.binary(max_size=256))
@settings(max_examples=80, deadline=None)
def test_arbitrary_payload_round_trip(payload: bytes) -> None:
    frame = pack_stego_frame(payload)
    model = FakeLanguageModel()
    result = encode_carrier(frame, model)
    assert decode_carrier(result.text, model) == frame
    assert model.tokenize(result.text) == list(result.token_ids)
    assert result.text.endswith((".", "!", "?"))


def test_carrier_fixture_is_deterministic() -> None:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "fake_carrier_v1.json").read_text(encoding="utf-8")
    )
    frame = bytes.fromhex(fixture["frame_hex"])
    model = FakeLanguageModel(**fixture["model"])
    first = encode_carrier(frame, model)
    second = encode_carrier(frame, model)
    assert first == second
    assert first.text == fixture["carrier"]
    assert decode_carrier(fixture["carrier"], model) == frame


def test_bridge_tokens_round_trip() -> None:
    model = FakeLanguageModel(low_entropy_steps={0, 1, 2})
    frame = pack_stego_frame(b"bridge")
    result = encode_carrier(frame, model)
    assert result.metrics.bridge_tokens == 3
    assert decode_carrier(result.text, model) == frame


def test_thirty_third_consecutive_bridge_fails() -> None:
    model = FakeLanguageModel(low_entropy_steps=range(33))
    with pytest.raises(CarrierGenerationError, match="low-entropy"):
        encode_carrier(pack_stego_frame(b"bridge limit"), model)


def test_invalid_bridge_token_is_rejected() -> None:
    model = FakeLanguageModel(low_entropy_steps={0})
    result = encode_carrier(pack_stego_frame(b"bridge"), model)
    replacement = "z" if result.text[0] != "z" else "y"
    with pytest.raises(CarrierArithmeticError, match="bridge"):
        decode_carrier(replacement + result.text[1:], model)


def test_finish_tokens_are_validated() -> None:
    model = FakeLanguageModel(finish_period=19)
    frame = pack_stego_frame(b"finish")
    result = encode_carrier(frame, model)
    assert 0 < result.metrics.finish_tokens <= 18
    finish_start = len(result.token_ids) - result.metrics.finish_tokens
    replacement = "z" if result.text[finish_start] != "z" else "y"
    tampered = result.text[:finish_start] + replacement + result.text[finish_start + 1 :]
    with pytest.raises(CarrierArithmeticError, match="finish"):
        decode_carrier(tampered, model)


def test_finish_limit_failure() -> None:
    model = FakeLanguageModel(finish_period=1000)
    with pytest.raises(CarrierGenerationError, match="sentence ending"):
        encode_carrier(pack_stego_frame(b"short"), model, finish_tokens=2)


def test_truncated_carrier_fails() -> None:
    model = FakeLanguageModel()
    result = encode_carrier(pack_stego_frame(b"truncate me"), model)
    data_end = len(result.text) - result.metrics.finish_tokens
    with pytest.raises((CarrierArithmeticError, CarrierStructureError)):
        decode_carrier(result.text[: data_end - 1], model)


def test_structural_controls_fail_before_tokenization() -> None:
    with pytest.raises(CarrierStructureError):
        decode_carrier("bad\ncarrier.", FakeLanguageModel())


def test_decode_enforces_local_payload_limit() -> None:
    model = FakeLanguageModel()
    carrier = encode_carrier(pack_stego_frame(b"payload"), model).text
    with pytest.raises(CarrierArithmeticError, match="protocol limit"):
        decode_carrier(carrier, model, maximum_payload_bytes=3)


def test_decode_enforces_character_limit() -> None:
    model = FakeLanguageModel()
    carrier = encode_carrier(pack_stego_frame(b"payload"), model).text
    with pytest.raises(CarrierStructureError, match="character limit"):
        decode_carrier(carrier, model, maximum_characters=len(carrier) - 1)


def test_end_to_end_hpke_through_fake_carrier(
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
) -> None:
    validated = validate_address(address)
    original_frame = encrypt_message(validated, "Stage 2 complet 🔐")
    model = FakeLanguageModel()
    carrier = encode_carrier(original_frame, model).text
    recovered_frame = decode_carrier(carrier, model)
    _, secret = decrypt_message(validated, private_key, recovered_frame)
    assert secret == "Stage 2 complet 🔐"


@given(text=st.text(alphabet=st.characters(codec="utf-8"), max_size=300))
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_end_to_end_unicode_property(
    text: str,
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
) -> None:
    validated = validate_address(address)
    model = FakeLanguageModel()
    frame = encrypt_message(validated, text)
    recovered = decode_carrier(encode_carrier(frame, model).text, model)
    assert decrypt_message(validated, private_key, recovered)[1] == text


def test_single_token_substitution_fails_by_codec_or_hpke(
    address: dict[str, Any],
    private_key: x25519.X25519PrivateKey,
) -> None:
    validated = validate_address(address)
    model = FakeLanguageModel()
    result = encode_carrier(encrypt_message(validated, "authenticated"), model)
    index = len(result.text) // 2
    replacement = "z" if result.text[index] != "z" else "y"
    tampered = result.text[:index] + replacement + result.text[index + 1 :]
    with pytest.raises(CovermailError):
        recovered = decode_carrier(tampered, model)
        decrypt_message(validated, private_key, recovered)
