"""Frame-to-token and token-to-frame orchestration for cm-arithmetic-v1."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from covermail.codec.arithmetic import ArithmeticBitEncoder, ArithmeticSymbolDecoder
from covermail.codec.bits import BitCollector, FramedBitSource
from covermail.codec.candidates import CandidateTable, TokenModel
from covermail.codec.frequencies import (
    MAX_CODING_SYMBOL_FREQUENCY,
    table_counts,
)
from covermail.errors import (
    CarrierArithmeticError,
    CarrierGenerationError,
    CarrierStructureError,
    CarrierTokenizationError,
    OuterFrameError,
)
from covermail.protocol.outer_frame import MAX_STEGO_PAYLOAD_BYTES, unpack_stego_frame
from covermail.protocol.varint import decode_uvarint

MAX_CONSECUTIVE_BRIDGE_TOKENS = 32
MAX_FINISH_TOKENS = 128
DEFAULT_FINISH_TOKENS = 32
MAX_FAKE_CARRIER_CHARACTERS = 200000


@dataclass(frozen=True, slots=True)
class CarrierMetrics:
    data_tokens: int
    bridge_tokens: int
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
        raise ValueError("finish_tokens outside v1 range")


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
    if any(character in text for character in ("\r", "\n", "\t", "\x00")):
        raise CarrierStructureError("carrier contains a forbidden control")
    if text[0].isspace() or text[-1].isspace():
        raise CarrierStructureError("carrier has leading or trailing whitespace")


def _validate_round_trip(model: TokenModel, token_ids: Sequence[int], text: str) -> None:
    if model.tokenize(text) != list(token_ids):
        raise CarrierTokenizationError("carrier does not retokenize exactly")


def encode_carrier(
    stego_frame: bytes,
    model: TokenModel,
    *,
    finish_tokens: int = DEFAULT_FINISH_TOKENS,
    maximum_characters: int = MAX_FAKE_CARRIER_CHARACTERS,
) -> CarrierResult:
    """Map one complete stego frame to deterministic fake-model token choices."""
    _validate_finish_limit(finish_tokens)
    try:
        unpack_stego_frame(stego_frame)
    except OuterFrameError as error:
        raise CarrierGenerationError("input is not one complete stego frame") from error

    source = FramedBitSource(stego_frame)
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
    token_ids: list[int] = []
    data_tokens = 0
    bridge_tokens = 0
    consecutive_bridges = 0
    token_guard = max(1024, len(stego_frame) * 64 + 1024)

    while confirmed < source.real_bits:
        table = model.next_table(token_ids)
        counts = _validate_table(table)
        if max(counts) > MAX_CODING_SYMBOL_FREQUENCY:
            consecutive_bridges += 1
            bridge_tokens += 1
            if consecutive_bridges > MAX_CONSECUTIVE_BRIDGE_TOKENS:
                raise CarrierGenerationError("model context remained too low-entropy")
            token_ids.append(table.candidates[0].token_id)
        else:
            consecutive_bridges = 0
            symbol = decoder.symbol(table.cumulative)
            mirror.symbol(symbol, table.cumulative)
            if desynchronized:
                raise CarrierArithmeticError("arithmetic mirror desynchronized")
            token_ids.append(table.candidates[symbol].token_id)
            data_tokens += 1
        if len(token_ids) > token_guard:
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
            data_tokens=data_tokens,
            bridge_tokens=bridge_tokens,
            finish_tokens=added_finish,
            confirmed_bits=confirmed,
            source_bits_read=read_offset,
        ),
    )


def decode_carrier(
    carrier: str,
    model: TokenModel,
    *,
    finish_tokens: int = DEFAULT_FINISH_TOKENS,
    maximum_characters: int = MAX_FAKE_CARRIER_CHARACTERS,
    maximum_payload_bytes: int = MAX_STEGO_PAYLOAD_BYTES,
) -> bytes:
    """Recover one exact stego frame and validate suffix and finish tokens."""
    _validate_finish_limit(finish_tokens)
    _validate_carrier_structure(carrier, maximum_characters=maximum_characters)
    observed = model.tokenize(carrier)
    if model.detokenize(observed) != carrier:
        raise CarrierTokenizationError("carrier tokenizer round trip changed visible text")

    collector = BitCollector()
    target_bits: int | None = None

    def emit(bit: int) -> None:
        nonlocal target_bits
        collector.append(bit)
        complete = collector.complete_bytes()
        if target_bits is None and complete:
            try:
                payload_length, header_bytes = decode_uvarint(complete, 0, max_bytes=3)
            except EOFError:
                pass
            except ValueError as error:
                raise CarrierArithmeticError("carrier has an invalid frame length") from error
            else:
                if payload_length > maximum_payload_bytes:
                    raise CarrierArithmeticError("carrier frame declaration exceeds protocol limit")
                target_bits = (header_bytes + payload_length) * 8
        if target_bits is not None and collector.count > target_bits:
            suffix_offset = collector.count - target_bits - 1
            expected = 1 if suffix_offset % 2 == 0 else 0
            if bit != expected:
                raise CarrierArithmeticError("carrier has invalid virtual suffix bits")

    encoder = ArithmeticBitEncoder(emit)
    visible_prefix: list[int] = []
    data_end: int | None = None
    consecutive_bridges = 0

    for index, token_id in enumerate(observed):
        table = model.next_table(visible_prefix)
        counts = _validate_table(table)
        if max(counts) > MAX_CODING_SYMBOL_FREQUENCY:
            consecutive_bridges += 1
            if consecutive_bridges > MAX_CONSECUTIVE_BRIDGE_TOKENS:
                raise CarrierArithmeticError("carrier exceeded the bridge-token limit")
            if token_id != table.candidates[0].token_id:
                raise CarrierArithmeticError("carrier has an invalid bridge token")
            visible_prefix.append(token_id)
            continue

        consecutive_bridges = 0
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
    frame = collector.complete_bytes()[: target_bits // 8]
    try:
        unpack_stego_frame(frame)
    except OuterFrameError as error:
        raise CarrierArithmeticError("recovered carrier frame is malformed") from error
    return frame
