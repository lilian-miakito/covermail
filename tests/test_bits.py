from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from covermail.codec.bits import BitCollector, FramedBitSource


def test_framed_bit_source_is_msb_first_then_alternating() -> None:
    source = FramedBitSource(b"\xa1")
    assert [source.bit(index) for index in range(14)] == [
        1,
        0,
        1,
        0,
        0,
        0,
        0,
        1,
        1,
        0,
        1,
        0,
        1,
        0,
    ]


@given(st.binary(max_size=512))
def test_source_and_collector_round_trip(data: bytes) -> None:
    source = FramedBitSource(data)
    collector = BitCollector()
    for offset in range(source.real_bits):
        collector.append(source.bit(offset))
    assert collector.count == len(data) * 8
    assert collector.complete_bytes() == data


def test_partial_collector_omits_incomplete_byte() -> None:
    collector = BitCollector()
    for bit in (1, 0, 1):
        collector.append(bit)
    assert collector.complete_bytes() == b""
    assert [collector.bit(index) for index in range(3)] == [1, 0, 1]


@pytest.mark.parametrize("bit", [-1, 2, 9])
def test_collector_rejects_non_bits(bit: int) -> None:
    with pytest.raises(ValueError):
        BitCollector().append(bit)


def test_bit_offsets_are_bounded() -> None:
    with pytest.raises(ValueError):
        FramedBitSource(b"").bit(-1)
    with pytest.raises(IndexError):
        BitCollector().bit(0)


def test_custom_suffix_is_generated_once_and_cached() -> None:
    draws: list[int] = []

    def draw(offset: int) -> int:
        draws.append(offset)
        return offset % 2

    source = FramedBitSource(b"\x00", draw)
    assert source.bit(10) == 0
    assert source.bit(9) == 1
    assert draws == [0, 1, 2]
