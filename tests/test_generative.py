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
HEADER_BYTES = 1


def _encode(
    header: bytes, capsule: bytes, *, finish_tokens: int = 64
) -> tuple[FakeLanguageModel, CarrierResult]:
    model = FakeLanguageModel()
    prefix = generate_prefix_tokens(model, count=PREFIX_TOKENS, random_below=lambda total: 0)
    result = encode_carrier_sections(
        prefix, header, capsule, model, model, finish_tokens=finish_tokens
    )
    return model, result


def _decode(carrier: str, model: FakeLanguageModel, capsule_bytes: int) -> DecodedCarrier:
    return decode_carrier_sections(
        carrier,
        model,
        prefix_tokens=PREFIX_TOKENS,
        packet_layout_resolver=lambda available, prefix: (
            (HEADER_BYTES, capsule_bytes) if len(available) >= HEADER_BYTES else None
        ),
    )


@given(st.binary(min_size=1, max_size=256))
@settings(max_examples=60, deadline=None)
def test_header_and_capsule_round_trip(body: bytes) -> None:
    header = os.urandom(HEADER_BYTES)
    model, result = _encode(header, body)
    decoded = _decode(result.text, model, len(body))
    assert decoded.prefix_token_ids == result.prefix_token_ids
    assert decoded.header == header
    assert decoded.capsule == body
    assert decoded.consumed_tokens < decoded.total_tokens
    assert result.metrics.header_bits == HEADER_BYTES * 8
    assert result.metrics.capsule_bits == len(body) * 8


def test_header_boundary_keeps_one_continuous_arithmetic_state() -> None:
    model, result = _encode(b"h", b"independent capsule")
    assert result.metrics.payload_tokens > 0
    assert _decode(result.text, model, len(result.capsule)).capsule == result.capsule


def test_finish_is_ignored_and_may_be_replaced() -> None:
    model, result = _encode(b"h", b"capsule")
    payload_text = model.detokenize(result.token_ids[: -result.metrics.finish_tokens])
    decoded = _decode(payload_text + "xyz", model, len(result.capsule))
    assert decoded.header == result.header
    assert decoded.capsule == result.capsule
    assert decoded.total_tokens - decoded.consumed_tokens == 3


def test_finish_budget_can_cut_without_eos() -> None:
    _, result = _encode(b"h", b"capsule", finish_tokens=2)
    assert result.metrics.finish_tokens == 2


def test_truncated_body_fails() -> None:
    model, result = _encode(b"h", b"truncate me", finish_tokens=0)
    with pytest.raises(CarrierArithmeticError, match="B/C packet"):
        _decode(result.text[:-1], model, len(result.capsule))


def test_structural_controls_and_character_limit_fail() -> None:
    model = FakeLanguageModel()
    with pytest.raises(CarrierStructureError):
        _decode("bad\x00carrier", model, 1)
    _, result = _encode(b"h", b"capsule")
    with pytest.raises(CarrierStructureError, match="character limit"):
        decode_carrier_sections(
            result.text,
            model,
            prefix_tokens=64,
            packet_layout_resolver=lambda available, prefix: (1, 7),
            maximum_characters=len(result.text) - 1,
        )


def test_prefix_and_payload_publish_section_progress() -> None:
    model = FakeLanguageModel()
    events: list[CarrierTokenEvent] = []
    prefix = generate_prefix_tokens(
        model, count=64, random_below=lambda total: 0, on_token=events.append
    )
    result = encode_carrier_sections(
        prefix, b"h", b"capsule", model, model, on_token=events.append
    )
    assert [event.phase for event in events[:64]] == ["prefix"] * 64
    assert {event.phase for event in events[64:]} == {"header", "capsule", "finish"}
    assert "".join(event.text for event in events) == result.text

    progress: list[CarrierDecodeProgress] = []
    decoded = decode_carrier_sections(
        result.text,
        model,
        prefix_tokens=64,
        packet_layout_resolver=lambda available, prefix_ids: (1, 7),
        on_token=progress.append,
    )
    assert decoded.capsule == b"capsule"
    assert {event.phase for event in progress} == {"header", "capsule"}
