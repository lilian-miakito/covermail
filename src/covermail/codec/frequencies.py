"""Deterministic integer frequency construction."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, localcontext

LOGIT_SCALE = 1024
WEIGHT_SCALE = 1 << 24
FREQUENCY_TOTAL = 32768


def deterministic_weights(scores: list[int], temperature_milli: int) -> list[int]:
    if not scores:
        raise ValueError("scores must not be empty")
    if not 100 <= temperature_milli <= 2000:
        raise ValueError("temperature outside protocol range")
    maximum = max(scores)
    weights: list[int] = []
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        denominator = Decimal(LOGIT_SCALE * temperature_milli)
        for score in scores:
            exponent = Decimal((score - maximum) * 1000) / denominator
            scaled = exponent.exp() * Decimal(WEIGHT_SCALE)
            weight = int(scaled.to_integral_value(rounding=ROUND_HALF_EVEN))
            weights.append(max(1, weight))
    return weights


def frequency_counts(weights: list[int], total: int = FREQUENCY_TOTAL) -> list[int]:
    count = len(weights)
    if count < 2 or count >= total:
        raise ValueError("invalid candidate count")
    if any(weight <= 0 for weight in weights):
        raise ValueError("weights must be positive")

    available = total - count
    weight_sum = sum(weights)
    counts: list[int] = []
    remainders: list[int] = []
    for weight in weights:
        numerator = weight * available
        quotient, remainder = divmod(numerator, weight_sum)
        counts.append(1 + quotient)
        remainders.append(remainder)

    missing = total - sum(counts)
    order = sorted(range(count), key=lambda index: (-remainders[index], index))
    for index in order[:missing]:
        counts[index] += 1

    if any(value <= 0 for value in counts) or sum(counts) != total:
        raise RuntimeError("frequency normalization invariant failed")
    return counts


def cumulative_counts(counts: list[int]) -> list[int]:
    if len(counts) < 2 or any(count <= 0 for count in counts):
        raise ValueError("frequency counts must contain at least two positive values")
    cumulative = [0]
    for count in counts:
        cumulative.append(cumulative[-1] + count)
    if cumulative[-1] != FREQUENCY_TOTAL:
        raise ValueError("frequency total mismatch")
    return cumulative


def table_counts(cumulative: list[int] | tuple[int, ...]) -> list[int]:
    if len(cumulative) < 3 or cumulative[0] != 0 or cumulative[-1] != FREQUENCY_TOTAL:
        raise ValueError("invalid cumulative frequency table")
    counts = [cumulative[index + 1] - cumulative[index] for index in range(len(cumulative) - 1)]
    if any(count <= 0 for count in counts):
        raise ValueError("cumulative frequencies must be strictly increasing")
    return counts
