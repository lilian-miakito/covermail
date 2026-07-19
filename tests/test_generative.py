from __future__ import annotations

from collections.abc import Callable

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from covermail.codec.fake_model import FakeLanguageModel
from covermail.codec.generative import decode_carrier_stream, encode_carrier_stream
from covermail.errors import CarrierArithmeticError, CarrierGenerationError, CarrierStructureError
from covermail.protocol.varint import decode_uvarint, encode_uvarint


def _pack(payload: bytes) -> bytes:
    return encode_uvarint(len(payload)) + payload


def _resolver(maximum: int = 1024) -> Callable[[bytes], int | None]:
    def resolve(complete: bytes) -> int | None:
        try:
            length, header = decode_uvarint(complete, 0, max_bytes=3)
        except EOFError:
            return None
        if length > maximum:
            raise ValueError("test stream exceeds protocol limit")
        return header + length

    return resolve


def _decode(carrier: str, model: FakeLanguageModel, *, maximum: int = 1024) -> bytes:
    return decode_carrier_stream(
        carrier,
        model,
        length_resolver=_resolver(maximum),
        final_validator=lambda stream: None,
    )


@given(st.binary(max_size=256))
@settings(max_examples=80, deadline=None)
def test_arbitrary_payload_round_trip(payload: bytes) -> None:
    stream = _pack(payload)
    model = FakeLanguageModel()
    result = encode_carrier_stream(stream, model)
    assert _decode(result.text, model) == stream
    assert model.tokenize(result.text) == list(result.token_ids)
    assert result.text.endswith((".", "!", "?"))


def test_low_entropy_tables_still_update_arithmetic_state() -> None:
    model = FakeLanguageModel(low_entropy_steps={0, 1, 2})
    stream = _pack(b"fractional information")
    result = encode_carrier_stream(stream, model)
    assert result.metrics.data_tokens == len(result.token_ids) - result.metrics.finish_tokens
    assert _decode(result.text, model) == stream


def test_long_low_entropy_prefix_is_not_a_special_case() -> None:
    model = FakeLanguageModel(low_entropy_steps=range(33))
    stream = _pack(b"fractional state")
    result = encode_carrier_stream(stream, model)
    assert _decode(result.text, model) == stream


def test_finish_tokens_are_validated() -> None:
    model = FakeLanguageModel(finish_period=19)
    stream = _pack(b"finish")
    result = encode_carrier_stream(stream, model)
    assert 0 < result.metrics.finish_tokens <= 18
    finish_start = len(result.token_ids) - result.metrics.finish_tokens
    replacement = "z" if result.text[finish_start] != "z" else "y"
    tampered = result.text[:finish_start] + replacement + result.text[finish_start + 1 :]
    with pytest.raises(CarrierArithmeticError, match="finish"):
        _decode(tampered, model)


def test_finish_limit_failure() -> None:
    model = FakeLanguageModel(finish_period=1000)
    with pytest.raises(CarrierGenerationError, match="sentence ending"):
        encode_carrier_stream(_pack(b"short"), model, finish_tokens=2)


def test_truncated_carrier_fails() -> None:
    model = FakeLanguageModel()
    result = encode_carrier_stream(_pack(b"truncate me"), model)
    data_end = len(result.text) - result.metrics.finish_tokens
    with pytest.raises((CarrierArithmeticError, CarrierStructureError)):
        _decode(result.text[: data_end - 1], model)


def test_structural_controls_fail_before_tokenization() -> None:
    with pytest.raises(CarrierStructureError):
        _decode("bad\x00carrier.", FakeLanguageModel())


def test_decode_enforces_local_payload_limit() -> None:
    model = FakeLanguageModel()
    carrier = encode_carrier_stream(_pack(b"payload"), model).text
    with pytest.raises(CarrierArithmeticError, match="invalid stream declaration"):
        _decode(carrier, model, maximum=3)


def test_decode_enforces_character_limit() -> None:
    model = FakeLanguageModel()
    carrier = encode_carrier_stream(_pack(b"payload"), model).text
    with pytest.raises(CarrierStructureError, match="character limit"):
        decode_carrier_stream(
            carrier,
            model,
            length_resolver=_resolver(),
            final_validator=lambda stream: None,
            maximum_characters=len(carrier) - 1,
        )
