"""A/B/C/D token orchestration for Covermail packet carriers."""

from __future__ import annotations

import secrets
from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from covermail.codec.arithmetic import ArithmeticBitEncoder, ArithmeticSymbolDecoder
from covermail.codec.bits import BitCollector, FramedBitSource
from covermail.codec.candidates import CandidateTable, GreedyTokenModel, TokenModel
from covermail.codec.frequencies import table_counts
from covermail.errors import (
    CarrierArithmeticError,
    CarrierGenerationError,
    CarrierStructureError,
    CarrierTokenizationError,
)

DEFAULT_PREFIX_TOKENS = 64
DEFAULT_FINISH_TOKENS = 64
MAX_FAKE_CARRIER_CHARACTERS = 200_000

CarrierPhase = Literal["prefix", "metadata", "body", "finish"]


@dataclass(frozen=True, slots=True)
class CarrierMetrics:
    prefix_tokens: int
    payload_tokens: int
    finish_tokens: int
    metadata_bits: int
    body_bits: int


@dataclass(frozen=True, slots=True)
class CarrierResult:
    text: str
    token_ids: tuple[int, ...]
    prefix_token_ids: tuple[int, ...]
    metadata: bytes
    body: bytes
    metrics: CarrierMetrics


@dataclass(frozen=True, slots=True)
class DecodedCarrier:
    prefix_token_ids: tuple[int, ...]
    metadata: bytes
    body: bytes
    consumed_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class CarrierTokenEvent:
    token_id: int
    text: str
    phase: CarrierPhase
    token_index: int
    section_tokens: int
    confirmed_bits: int
    total_bits: int


@dataclass(frozen=True, slots=True)
class CarrierDecodeProgress:
    processed_tokens: int
    total_tokens: int
    phase: Literal["metadata", "body"]
    recovered_bits: int
    target_bits: int


def _validate_table(table: CandidateTable) -> None:
    try:
        table_counts(table.cumulative)
    except ValueError as error:
        raise CarrierArithmeticError("model returned an invalid frequency table") from error


def _validate_carrier_structure(text: str, *, maximum_characters: int) -> None:
    if not text:
        raise CarrierStructureError("carrier is empty")
    if len(text) > maximum_characters:
        raise CarrierStructureError("carrier exceeds character limit")
    if "\r" in text or "\x00" in text:
        raise CarrierStructureError("carrier contains a non-canonical control")


def _validate_round_trip(model: TokenModel, token_ids: Sequence[int], text: str) -> None:
    if model.tokenize(text) != list(token_ids):
        raise CarrierTokenizationError("carrier does not retokenize exactly")


def generate_prefix_tokens(
    model: TokenModel,
    *,
    count: int = DEFAULT_PREFIX_TOKENS,
    random_below: Callable[[int], int] = secrets.randbelow,
    on_token: Callable[[CarrierTokenEvent], None] | None = None,
) -> tuple[int, ...]:
    """Sample an observed, non-reconstructed assistant prefix."""
    if count <= 0:
        raise ValueError("prefix token count must be positive")
    token_ids: list[int] = []
    for section_index in range(1, count + 1):
        table = model.next_table(token_ids)
        _validate_table(table)
        total = table.cumulative[-1]
        draw = random_below(total)
        if not 0 <= draw < total:
            raise ValueError("prefix random source returned an out-of-range value")
        symbol = bisect_right(table.cumulative, draw) - 1
        selected = table.candidates[symbol]
        token_ids.append(selected.token_id)
        if on_token is not None:
            on_token(
                CarrierTokenEvent(
                    selected.token_id,
                    selected.token_text,
                    "prefix",
                    len(token_ids),
                    section_index,
                    0,
                    0,
                )
            )
    return tuple(token_ids)


def _encode_payload(
    metadata: bytes,
    body: bytes,
    model: TokenModel,
    token_ids: list[int],
    on_token: Callable[[CarrierTokenEvent], None] | None,
) -> int:
    if not metadata or not body:
        raise CarrierGenerationError("metadata and body sections must be non-empty")
    data = metadata + body
    source = FramedBitSource(data, lambda offset: secrets.randbits(1))
    read_offset = 0

    def read_bit() -> int:
        nonlocal read_offset
        value = source.bit(read_offset)
        read_offset += 1
        return value

    confirmed = 0
    desynchronized = False

    def confirm(bit: int) -> None:
        nonlocal confirmed, desynchronized
        if bit != source.bit(confirmed):
            desynchronized = True
        confirmed += 1

    decoder = ArithmeticSymbolDecoder(read_bit)
    mirror = ArithmeticBitEncoder(confirm)
    section_tokens = 0
    token_guard = max(1024, len(data) * 64 + 1024)
    while confirmed < source.real_bits:
        table = model.next_table(token_ids)
        _validate_table(table)
        symbol = decoder.symbol(table.cumulative)
        mirror.symbol(symbol, table.cumulative)
        if desynchronized:
            raise CarrierArithmeticError("payload arithmetic mirror desynchronized")
        selected = table.candidates[symbol]
        token_ids.append(selected.token_id)
        section_tokens += 1
        if on_token is not None:
            phase: Literal["metadata", "body"] = (
                "metadata" if confirmed <= len(metadata) * 8 else "body"
            )
            on_token(
                CarrierTokenEvent(
                    selected.token_id,
                    selected.token_text,
                    phase,
                    len(token_ids),
                    section_tokens,
                    min(confirmed, source.real_bits),
                    source.real_bits,
                )
            )
        if section_tokens > token_guard:
            raise CarrierGenerationError("payload arithmetic coder failed to make progress")
    return section_tokens


def encode_carrier_sections(
    prefix_token_ids: Sequence[int],
    metadata: bytes,
    body: bytes,
    payload_model: TokenModel,
    finish_model: GreedyTokenModel,
    *,
    finish_tokens: int = DEFAULT_FINISH_TOKENS,
    maximum_characters: int = MAX_FAKE_CARRIER_CHARACTERS,
    on_token: Callable[[CarrierTokenEvent], None] | None = None,
) -> CarrierResult:
    """Encode fixed B and variable C, then append an unverified local finish D."""
    if finish_tokens < 0:
        raise ValueError("finish token budget cannot be negative")
    token_ids = list(prefix_token_ids)
    payload_tokens = _encode_payload(metadata, body, payload_model, token_ids, on_token)
    added_finish = 0
    while added_finish < finish_tokens:
        selected = finish_model.next_greedy_token(token_ids)
        if selected is None:
            break
        token_ids.append(selected.token_id)
        added_finish += 1
        if on_token is not None:
            on_token(
                CarrierTokenEvent(
                    selected.token_id,
                    selected.text,
                    "finish",
                    len(token_ids),
                    added_finish,
                    0,
                    0,
                )
            )
    text = payload_model.detokenize(token_ids)
    _validate_round_trip(payload_model, token_ids, text)
    _validate_carrier_structure(text, maximum_characters=maximum_characters)
    return CarrierResult(
        text,
        tuple(token_ids),
        tuple(prefix_token_ids),
        metadata,
        body,
        CarrierMetrics(
            len(prefix_token_ids),
            payload_tokens,
            added_finish,
            len(metadata) * 8,
            len(body) * 8,
        ),
    )


def _decode_payload(
    observed: Sequence[int],
    start: int,
    metadata_bytes: int,
    model: TokenModel,
    visible_prefix: list[int],
    body_length_resolver: Callable[[bytes, tuple[int, ...]], int],
    prefix_token_ids: tuple[int, ...],
    on_token: Callable[[CarrierDecodeProgress], None] | None,
) -> tuple[bytes, bytes, int]:
    metadata_bits = metadata_bytes * 8
    target_bits: int | None = None
    collector = BitCollector()

    def emit(bit: int) -> None:
        collector.append(bit)

    encoder = ArithmeticBitEncoder(emit)
    for index in range(start, len(observed)):
        token_id = observed[index]
        table = model.next_table(visible_prefix)
        _validate_table(table)
        candidate_index = next(
            (
                candidate_index
                for candidate_index, candidate in enumerate(table.candidates)
                if candidate.token_id == token_id
            ),
            None,
        )
        if candidate_index is None:
            raise CarrierArithmeticError("payload token is outside its candidate table")
        encoder.symbol(candidate_index, table.cumulative)
        visible_prefix.append(token_id)
        if target_bits is None and collector.count >= metadata_bits:
            metadata = collector.complete_bytes()[:metadata_bytes]
            body_bytes = body_length_resolver(metadata, prefix_token_ids)
            if body_bytes <= 0:
                raise CarrierArithmeticError("metadata declared an invalid body length")
            target_bits = (metadata_bytes + body_bytes) * 8
        if on_token is not None:
            phase: Literal["metadata", "body"] = "metadata" if target_bits is None else "body"
            progress_target = target_bits or metadata_bits
            on_token(
                CarrierDecodeProgress(
                    index + 1,
                    len(observed),
                    phase,
                    min(collector.count, progress_target),
                    progress_target,
                )
            )
        if target_bits is not None and collector.count >= target_bits:
            complete = collector.complete_bytes()[: target_bits // 8]
            return complete[:metadata_bytes], complete[metadata_bytes:], index + 1
    raise CarrierArithmeticError("carrier ended before complete B/C payload")


def decode_carrier_sections(
    carrier: str,
    payload_model: TokenModel,
    *,
    prefix_tokens: int,
    metadata_bytes: int,
    body_length_resolver: Callable[[bytes, tuple[int, ...]], int],
    maximum_characters: int = MAX_FAKE_CARRIER_CHARACTERS,
    on_token: Callable[[CarrierDecodeProgress], None] | None = None,
) -> DecodedCarrier:
    """Recover B/C and deliberately ignore every trailing D token."""
    _validate_carrier_structure(carrier, maximum_characters=maximum_characters)
    observed = payload_model.tokenize(carrier)
    if payload_model.detokenize(observed) != carrier:
        raise CarrierTokenizationError("carrier tokenizer round trip changed visible text")
    if len(observed) <= prefix_tokens:
        raise CarrierStructureError("carrier ends inside its observed prefix")
    prefix = tuple(observed[:prefix_tokens])
    visible_prefix = list(prefix)
    metadata, body, body_end = _decode_payload(
        observed,
        prefix_tokens,
        metadata_bytes,
        payload_model,
        visible_prefix,
        body_length_resolver,
        prefix,
        on_token,
    )
    return DecodedCarrier(prefix, metadata, body, body_end, len(observed))
