from __future__ import annotations

from collections.abc import Iterator
from itertools import cycle

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from covermail.codec.arithmetic import ArithmeticBitEncoder, ArithmeticSymbolDecoder
from covermail.codec.bits import FramedBitSource
from covermail.codec.frequencies import cumulative_counts, frequency_counts

HALVES = [0, 16384, 32768]


def _code_bits(code: int) -> Iterator[int]:
    for shift in range(31, -1, -1):
        yield (code >> shift) & 1
    while True:
        yield 0


@pytest.mark.parametrize(
    ("code", "expected"),
    [(0, 0), ((1 << 31) - 1, 0), (1 << 31, 1), ((1 << 32) - 1, 1)],
)
def test_symbol_interval_boundaries(code: int, expected: int) -> None:
    bits = _code_bits(code)
    decoder = ArithmeticSymbolDecoder(lambda: next(bits))
    assert decoder.symbol(HALVES) == expected


@pytest.mark.parametrize(("symbol", "expected"), [(0, [0]), (1, [1])])
def test_encoder_confirms_half_interval(symbol: int, expected: list[int]) -> None:
    emitted: list[int] = []
    encoder = ArithmeticBitEncoder(emitted.append)
    encoder.symbol(symbol, HALVES)
    assert emitted == expected


def test_decoder_rejects_non_bit_source() -> None:
    with pytest.raises(ValueError, match="non-bit"):
        ArithmeticSymbolDecoder(lambda: 2)


def test_encoder_rejects_symbol_outside_table() -> None:
    with pytest.raises(ValueError, match="invalid arithmetic symbol"):
        ArithmeticBitEncoder(lambda bit: None).symbol(2, HALVES)


@given(
    data=st.binary(min_size=1, max_size=64),
    weights=st.lists(st.integers(min_value=50, max_value=100), min_size=2, max_size=24),
)
@settings(max_examples=80, deadline=None)
def test_randomized_bits_symbols_bits_recovery(data: bytes, weights: list[int]) -> None:
    cumulative = cumulative_counts(frequency_counts(weights))
    source = FramedBitSource(data)
    read_offset = 0

    def read_bit() -> int:
        nonlocal read_offset
        bit = source.bit(read_offset)
        read_offset += 1
        return bit

    confirmed = 0

    def confirm(bit: int) -> None:
        nonlocal confirmed
        assert bit == source.bit(confirmed)
        confirmed += 1

    decoder = ArithmeticSymbolDecoder(read_bit)
    mirror = ArithmeticBitEncoder(confirm)
    symbols = 0
    while confirmed < source.real_bits:
        symbol = decoder.symbol(cumulative)
        mirror.symbol(symbol, cumulative)
        symbols += 1
        assert symbols < len(data) * 64 + 1024
    assert confirmed >= source.real_bits


def test_skewed_boundary_table_round_trip() -> None:
    cumulative = [0, 24576, 32768]
    bits = cycle([1, 0, 1, 1])
    decoder = ArithmeticSymbolDecoder(lambda: next(bits))
    emitted: list[int] = []
    encoder = ArithmeticBitEncoder(emitted.append)
    for _ in range(20):
        symbol = decoder.symbol(cumulative)
        encoder.symbol(symbol, cumulative)
    assert emitted
