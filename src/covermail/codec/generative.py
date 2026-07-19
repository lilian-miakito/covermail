"""Byte-stream-to-token orchestration for the Covermail arithmetic codec."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from covermail.codec.arithmetic import ArithmeticBitEncoder, ArithmeticSymbolDecoder
from covermail.codec.bits import BitCollector, FramedBitSource
from covermail.codec.candidates import CandidateTable, TokenModel
from covermail.codec.frequencies import table_counts
from covermail.errors import (
    CarrierArithmeticError,
    CarrierGenerationError,
    CarrierStructureError,
    CarrierTokenizationError,
    OuterFrameError,
)

MAX_FINISH_TOKENS = 128
DEFAULT_FINISH_TOKENS = 32
MAX_FAKE_CARRIER_CHARACTERS = 200000


@dataclass(frozen=True, slots=True)
class CarrierMetrics:
    primer_tokens: int
    data_tokens: int
    finish_tokens: int
    confirmed_bits: int
    source_bits_read: int


@dataclass(frozen=True, slots=True)
class CarrierResult:
    text: str
    token_ids: tuple[int, ...]
    metrics: CarrierMetrics


def _validate_finish_limit(finish_tokens: int) -> None:
    if not 0 <= finish_tokens <= MAX_FINISH_TOKENS:
        raise ValueError("finish_tokens outside protocol range")


def _validate_table(table: CandidateTable) -> list[int]:
    try:
        return table_counts(table.cumulative)
    except ValueError as error:
        raise CarrierArithmeticError("model returned an invalid frequency table") from error


def _validate_carrier_structure(text: str, *, maximum_characters: int) -> None:
    if not text:
        raise CarrierStructureError("carrier is empty")
    if len(text) > maximum_characters:
        raise CarrierStructureError("carrier exceeds character limit")
    if "\r" in text or "\x00" in text:
        raise CarrierStructureError("carrier contains a non-canonical control")
    if text[0].isspace() or text[-1].isspace():
        raise CarrierStructureError("carrier has leading or trailing whitespace")


def _validate_round_trip(model: TokenModel, token_ids: Sequence[int], text: str) -> None:
    if model.tokenize(text) != list(token_ids):
        raise CarrierTokenizationError("carrier does not retokenize exactly")


def encode_carrier_stream(
    stream: bytes,
    model: TokenModel,
    *,
    initial_token_ids: Sequence[int] = (),
    finish_tokens: int = DEFAULT_FINISH_TOKENS,
    maximum_characters: int = MAX_FAKE_CARRIER_CHARACTERS,
) -> CarrierResult:
    """Map a validated byte stream after an optional visible primer to tokens."""
    _validate_finish_limit(finish_tokens)
    if not stream:
        raise CarrierGenerationError("carrier byte stream is empty")
    initial = list(initial_token_ids)
    if model.tokenize(model.detokenize(initial)) != initial:
        raise CarrierTokenizationError("initial visible token prefix is not copy-safe")

    source = FramedBitSource(stream)
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
    token_ids = initial.copy()
    primer_tokens = len(initial)
    data_tokens = 0
    token_guard = max(1024, len(stream) * 64 + 1024)

    while confirmed < source.real_bits:
        table = model.next_table(token_ids)
        _validate_table(table)
        symbol = decoder.symbol(table.cumulative)
        mirror.symbol(symbol, table.cumulative)
        if desynchronized:
            raise CarrierArithmeticError("arithmetic mirror desynchronized")
        token_ids.append(table.candidates[symbol].token_id)
        data_tokens += 1
        if len(token_ids) - primer_tokens > token_guard:
            raise CarrierGenerationError("arithmetic coder failed to make progress")

    added_finish = 0
    text = model.detokenize(token_ids)
    while not text.endswith((".", "!", "?")) and added_finish < finish_tokens:
        table = model.next_table(token_ids)
        _validate_table(table)
        token_ids.append(table.candidates[0].token_id)
        added_finish += 1
        text = model.detokenize(token_ids)
    if not text.endswith((".", "!", "?")):
        raise CarrierGenerationError("fake carrier did not reach a sentence ending")

    _validate_round_trip(model, token_ids, text)
    _validate_carrier_structure(text, maximum_characters=maximum_characters)
    return CarrierResult(
        text=text,
        token_ids=tuple(token_ids),
        metrics=CarrierMetrics(
            primer_tokens=primer_tokens,
            data_tokens=data_tokens,
            finish_tokens=added_finish,
            confirmed_bits=confirmed,
            source_bits_read=read_offset,
        ),
    )


def decode_carrier_stream(
    carrier: str,
    model: TokenModel,
    *,
    length_resolver: Callable[[bytes], int | None],
    final_validator: Callable[[bytes], None],
    initial_token_ids: Sequence[int] = (),
    finish_tokens: int = DEFAULT_FINISH_TOKENS,
    maximum_characters: int = MAX_FAKE_CARRIER_CHARACTERS,
) -> bytes:
    """Recover an exact byte stream after skipping an observed visible primer."""
    _validate_finish_limit(finish_tokens)
    _validate_carrier_structure(carrier, maximum_characters=maximum_characters)
    observed = model.tokenize(carrier)
    if model.detokenize(observed) != carrier:
        raise CarrierTokenizationError("carrier tokenizer round trip changed visible text")
    initial = list(initial_token_ids)
    if observed[: len(initial)] != initial:
        raise CarrierTokenizationError("carrier does not start with the expected primer tokens")

    collector = BitCollector()
    target_bits: int | None = None

    def emit(bit: int) -> None:
        nonlocal target_bits
        collector.append(bit)
        complete = collector.complete_bytes()
        if target_bits is None:
            try:
                target_bytes = length_resolver(complete)
            except (OuterFrameError, ValueError) as error:
                raise CarrierArithmeticError("carrier has an invalid stream declaration") from error
            if target_bytes is not None:
                if target_bytes <= 0:
                    raise CarrierArithmeticError("carrier declared an invalid stream length")
                target_bits = target_bytes * 8
        if target_bits is not None and collector.count > target_bits:
            suffix_offset = collector.count - target_bits - 1
            expected = 1 if suffix_offset % 2 == 0 else 0
            if bit != expected:
                raise CarrierArithmeticError("carrier has invalid virtual suffix bits")

    encoder = ArithmeticBitEncoder(emit)
    visible_prefix = initial.copy()
    data_end: int | None = None
    for index, token_id in enumerate(observed[len(initial) :], start=len(initial)):
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
            raise CarrierArithmeticError("carrier token is outside the candidate table")
        encoder.symbol(candidate_index, table.cumulative)
        visible_prefix.append(token_id)
        if target_bits is not None and collector.count >= target_bits:
            data_end = index + 1
            break

    if target_bits is None or collector.count < target_bits or data_end is None:
        raise CarrierArithmeticError("carrier ended before its complete frame")

    trailing = observed[data_end:]
    if len(trailing) > finish_tokens:
        raise CarrierArithmeticError("carrier has too many finish tokens")
    for token_id in trailing:
        table = model.next_table(visible_prefix)
        _validate_table(table)
        if token_id != table.candidates[0].token_id:
            raise CarrierArithmeticError("carrier has an invalid finish token")
        visible_prefix.append(token_id)

    if not carrier.endswith((".", "!", "?")):
        raise CarrierStructureError("carrier does not end as a sentence")
    stream = collector.complete_bytes()[: target_bits // 8]
    try:
        final_validator(stream)
    except (OuterFrameError, ValueError) as error:
        raise CarrierArithmeticError("recovered carrier stream is malformed") from error
    return stream
