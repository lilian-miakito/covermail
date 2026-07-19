"""Covermail's 32-bit inverse arithmetic coder."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable, Sequence

from covermail.codec.frequencies import FREQUENCY_TOTAL, table_counts

PRECISION = 32
FULL = 1 << PRECISION
MASK = FULL - 1
HALF = 1 << 31
QUARTER = 1 << 30
THREE_QUARTERS = 3 << 30


class ArithmeticSymbolDecoder:
    """Consume source bits and select arithmetic symbols."""

    def __init__(self, read_bit: Callable[[], int]) -> None:
        self.low = 0
        self.high = MASK
        self.code = 0
        self.read_bit = read_bit
        for _ in range(PRECISION):
            self.code = ((self.code << 1) | self._read()) & MASK

    def _read(self) -> int:
        bit = self.read_bit()
        if bit not in (0, 1):
            raise ValueError("arithmetic bit source returned a non-bit")
        return bit

    def symbol(self, cumulative: Sequence[int]) -> int:
        table_counts(list(cumulative))
        range_size = self.high - self.low + 1
        scaled = ((self.code - self.low + 1) * FREQUENCY_TOTAL - 1) // range_size
        symbol = bisect_right(cumulative, scaled) - 1
        if symbol < 0 or symbol + 1 >= len(cumulative):
            raise RuntimeError("arithmetic symbol outside table")

        old_low = self.low
        self.high = (
            old_low + range_size * cumulative[symbol + 1] // FREQUENCY_TOTAL - 1
        )
        self.low = old_low + range_size * cumulative[symbol] // FREQUENCY_TOTAL

        while True:
            if self.high < HALF:
                pass
            elif self.low >= HALF:
                self.low -= HALF
                self.high -= HALF
                self.code -= HALF
            elif self.low >= QUARTER and self.high < THREE_QUARTERS:
                self.low -= QUARTER
                self.high -= QUARTER
                self.code -= QUARTER
            else:
                break

            self.low = (self.low << 1) & MASK
            self.high = ((self.high << 1) | 1) & MASK
            self.code = ((self.code << 1) | self._read()) & MASK
        return symbol


class ArithmeticBitEncoder:
    """Consume arithmetic symbols and emit only confirmed prefix bits."""

    def __init__(self, emit_bit: Callable[[int], None]) -> None:
        self.low = 0
        self.high = MASK
        self.pending = 0
        self.emit_bit = emit_bit

    def _output(self, bit: int) -> None:
        self.emit_bit(bit)
        while self.pending:
            self.emit_bit(bit ^ 1)
            self.pending -= 1

    def symbol(self, symbol: int, cumulative: Sequence[int]) -> None:
        table_counts(list(cumulative))
        if symbol < 0 or symbol + 1 >= len(cumulative):
            raise ValueError("invalid arithmetic symbol")
        range_size = self.high - self.low + 1
        old_low = self.low
        self.high = (
            old_low + range_size * cumulative[symbol + 1] // FREQUENCY_TOTAL - 1
        )
        self.low = old_low + range_size * cumulative[symbol] // FREQUENCY_TOTAL

        while True:
            if self.high < HALF:
                self._output(0)
            elif self.low >= HALF:
                self._output(1)
                self.low -= HALF
                self.high -= HALF
            elif self.low >= QUARTER and self.high < THREE_QUARTERS:
                self.pending += 1
                self.low -= QUARTER
                self.high -= QUARTER
            else:
                break

            self.low = (self.low << 1) & MASK
            self.high = ((self.high << 1) | 1) & MASK
