from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from covermail.codec.frequencies import (
    FREQUENCY_TOTAL,
    cumulative_counts,
    deterministic_weights,
    frequency_counts,
    table_counts,
)


def test_deterministic_weight_fixture() -> None:
    assert deterministic_weights([0, -1024, -2048], 1000) == [16777216, 6171993, 2270549]


def test_largest_remainder_ties_follow_candidate_order() -> None:
    assert frequency_counts([1, 1, 1], total=8) == [3, 3, 2]


@given(st.lists(st.integers(min_value=1, max_value=1 << 40), min_size=2, max_size=128))
def test_frequency_normalization_property(weights: list[int]) -> None:
    counts = frequency_counts(weights)
    cumulative = cumulative_counts(counts)
    assert all(count > 0 for count in counts)
    assert sum(counts) == FREQUENCY_TOTAL
    assert table_counts(cumulative) == counts


@pytest.mark.parametrize("temperature", [99, 2001])
def test_temperature_range(temperature: int) -> None:
    with pytest.raises(ValueError):
        deterministic_weights([0, 1], temperature)


@pytest.mark.parametrize("weights", [[], [1], [0, 1], [-1, 2]])
def test_invalid_weights(weights: list[int]) -> None:
    with pytest.raises(ValueError):
        frequency_counts(weights)


@pytest.mark.parametrize(
    "cumulative",
    [[], [0, FREQUENCY_TOTAL], [1, 2, FREQUENCY_TOTAL], [0, 0, FREQUENCY_TOTAL]],
)
def test_invalid_cumulative_tables(cumulative: list[int]) -> None:
    with pytest.raises(ValueError):
        table_counts(cumulative)
