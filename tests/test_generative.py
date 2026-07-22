from __future__ import annotations

import os

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from covermail.codec.fake_model import FakeLanguageModel
from covermail.codec.generative import (
    CarrierDecodeProgress,
    CarrierResult,
    CarrierTokenEvent,
    DecodedCarrier,
    decode_carrier_sections,
    encode_carrier_sections,
    generate_prefix_tokens,
)
from covermail.errors import CarrierArithmeticError, CarrierStructureError

PREFIX_TOKENS = 64
METADATA_BYTES = 53


def _encode(
    metadata: bytes, body: bytes, *, finish_tokens: int = 64
) -> tuple[FakeLanguageModel, CarrierResult]:
    model = FakeLanguageModel()
    prefix = generate_prefix_tokens(model, count=PREFIX_TOKENS, random_below=lambda total: 0)
    result = encode_carrier_sections(
        prefix, metadata, body, model, model, finish_tokens=finish_tokens
    )
    return model, result


def _decode(carrier: str, model: FakeLanguageModel, body_bytes: int) -> DecodedCarrier:
    return decode_carrier_sections(
        carrier,
        model,
        prefix_tokens=PREFIX_TOKENS,
        metadata_bytes=METADATA_BYTES,
        body_length_resolver=lambda metadata, prefix: body_bytes,
    )


@given(st.binary(min_size=1, max_size=256))
@settings(max_examples=60, deadline=None)
def test_two_arithmetic_sections_round_trip(body: bytes) -> None:
    metadata = os.urandom(METADATA_BYTES)
    model, result = _encode(metadata, body)
    decoded = _decode(result.text, model, len(body))
    assert decoded.prefix_token_ids == result.prefix_token_ids
    assert decoded.metadata == metadata
    assert decoded.body == body
    assert decoded.consumed_tokens < decoded.total_tokens
    assert result.metrics.metadata_bits == METADATA_BYTES * 8
    assert result.metrics.body_bits == len(body) * 8


def test_metadata_boundary_keeps_one_continuous_arithmetic_state() -> None:
    model, result = _encode(bytes(range(53)), b"independent body section")
    assert result.metrics.payload_tokens > 0
    assert _decode(result.text, model, len(result.body)).body == result.body


def test_finish_is_ignored_and_may_be_replaced() -> None:
    model, result = _encode(b"m" * 53, b"body")
    payload_text = model.detokenize(result.token_ids[: -result.metrics.finish_tokens])
    decoded = _decode(payload_text + "xyz", model, len(result.body))
    assert decoded.metadata == result.metadata
    assert decoded.body == result.body
    assert decoded.total_tokens - decoded.consumed_tokens == 3


def test_finish_budget_can_cut_without_eos() -> None:
    _, result = _encode(b"m" * 53, b"body", finish_tokens=2)
    assert result.metrics.finish_tokens == 2


def test_truncated_body_fails() -> None:
    model, result = _encode(b"m" * 53, b"truncate me", finish_tokens=0)
    with pytest.raises(CarrierArithmeticError, match="B/C payload"):
        _decode(result.text[:-1], model, len(result.body))


def test_structural_controls_and_character_limit_fail() -> None:
    model = FakeLanguageModel()
    with pytest.raises(CarrierStructureError):
        _decode("bad\x00carrier", model, 1)
    _, result = _encode(b"m" * 53, b"body")
    with pytest.raises(CarrierStructureError, match="character limit"):
        decode_carrier_sections(
            result.text,
            model,
            prefix_tokens=64,
            metadata_bytes=53,
            body_length_resolver=lambda metadata, prefix: 4,
            maximum_characters=len(result.text) - 1,
        )


def test_prefix_and_payload_publish_section_progress() -> None:
    model = FakeLanguageModel()
    events: list[CarrierTokenEvent] = []
    prefix = generate_prefix_tokens(
        model, count=64, random_below=lambda total: 0, on_token=events.append
    )
    result = encode_carrier_sections(
        prefix, b"m" * 53, b"body", model, model, on_token=events.append
    )
    assert [event.phase for event in events[:64]] == ["prefix"] * 64
    assert {event.phase for event in events[64:]} == {"metadata", "body", "finish"}
    assert "".join(event.text for event in events) == result.text

    progress: list[CarrierDecodeProgress] = []
    decoded = decode_carrier_sections(
        result.text,
        model,
        prefix_tokens=64,
        metadata_bytes=53,
        body_length_resolver=lambda metadata, prefix_ids: 4,
        on_token=progress.append,
    )
    assert decoded.body == b"body"
    assert {event.phase for event in progress} == {"metadata", "body"}
