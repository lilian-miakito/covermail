"""Deterministic candidate construction and tokenizer-stability helpers."""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Protocol, cast

from covermail.codec.frequencies import (
    LOGIT_SCALE,
    cumulative_counts,
    deterministic_weights,
    frequency_counts,
    table_counts,
)
from covermail.errors import CarrierGenerationError

MAX_MODEL_CANDIDATES = 4096


@dataclass(frozen=True, slots=True)
class Candidate:
    token_id: int
    token_text: str
    adjusted_score: int


@dataclass(frozen=True, slots=True)
class CandidateTable:
    candidates: tuple[Candidate, ...]
    cumulative: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.candidates) < 2:
            raise ValueError("candidate table needs at least two symbols")
        if len(self.cumulative) != len(self.candidates) + 1:
            raise ValueError("candidate and cumulative table sizes differ")
        table_counts(self.cumulative)
        token_ids = [candidate.token_id for candidate in self.candidates]
        if len(set(token_ids)) != len(token_ids):
            raise ValueError("candidate token IDs must be unique")


class TokenizerModel(Protocol):
    def tokenize(self, text: str) -> list[int]: ...

    def detokenize(self, token_ids: Sequence[int]) -> str: ...


class TokenModel(TokenizerModel, Protocol):
    def next_table(self, visible_prefix: Sequence[int]) -> CandidateTable: ...


class LogitModel(TokenizerModel, Protocol):
    def next_logits(self, context_ids: Sequence[int]) -> Sequence[float]: ...

    def special_token_ids(self) -> set[int]: ...


def is_copy_safe(model: TokenizerModel, visible_prefix: Sequence[int], token_id: int) -> bool:
    expected = [*visible_prefix, token_id]
    return model.tokenize(model.detokenize(expected)) == expected


def _float32(value: float) -> float:
    try:
        result = struct.unpack("!f", struct.pack("!f", float(value)))[0]
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError("model logit cannot be represented as float32") from error
    if not math.isfinite(result):
        raise ValueError("non-finite model logit")
    return cast(float, result)


def quantize_logit(value: float) -> int:
    finite32 = _float32(value)
    with localcontext() as context:
        context.prec = 50
        scaled = Decimal.from_float(finite32) * LOGIT_SCALE
        return int(scaled.to_integral_value(rounding=ROUND_HALF_EVEN))


def adjusted_score(logit: float) -> int:
    return quantize_logit(logit)


def is_visible_token(token_text: str) -> bool:
    """Allow ordinary text, including LF paragraphs; reject transport-breaking text."""
    if not token_text:
        return False
    if "\r" in token_text or "\x00" in token_text:
        return False
    try:
        token_text.encode("utf-8", errors="strict")
    except UnicodeError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    top_n: int
    candidate_pool_multiplier: int
    temperature_milli: int

    def __post_init__(self) -> None:
        requested = self.top_n * self.candidate_pool_multiplier
        if self.top_n < 2 or requested > MAX_MODEL_CANDIDATES:
            raise ValueError("candidate pool size outside protocol range")
        if not 1 <= self.candidate_pool_multiplier <= 16:
            raise ValueError("candidate pool multiplier outside protocol range")
        if not 100 <= self.temperature_milli <= 2000:
            raise ValueError("temperature outside protocol range")


def build_candidate_table(
    model: LogitModel,
    context_ids: Sequence[int],
    visible_prefix: Sequence[int],
    config: CandidateConfig,
) -> CandidateTable:
    """Build one exact candidate and frequency table from full logits."""
    logits = model.next_logits(context_ids)
    specials = model.special_token_ids()
    ranked: list[tuple[int, int, float]] = []
    for token_id, value in enumerate(logits):
        if token_id in specials:
            continue
        try:
            finite32 = _float32(value)
            raw_score = quantize_logit(finite32)
        except ValueError as error:
            raise CarrierGenerationError("model returned a non-finite float32 logit") from error
        ranked.append((-raw_score, token_id, finite32))
    ranked.sort(key=lambda item: (item[0], item[1]))
    requested = config.top_n * config.candidate_pool_multiplier

    candidates: list[Candidate] = []
    for _, token_id, logit in ranked[:requested]:
        token_text = model.detokenize([token_id])
        if not is_visible_token(token_text):
            continue
        if not is_copy_safe(model, visible_prefix, token_id):
            continue
        candidates.append(
            Candidate(
                token_id=token_id,
                token_text=token_text,
                adjusted_score=adjusted_score(logit),
            )
        )

    candidates.sort(key=lambda candidate: (-candidate.adjusted_score, candidate.token_id))
    selected = candidates[: config.top_n]
    if len(selected) != config.top_n:
        raise CarrierGenerationError("model produced too few copy-safe visible candidates")
    scores = [candidate.adjusted_score for candidate in selected]
    counts = frequency_counts(deterministic_weights(scores, config.temperature_milli))
    return CandidateTable(tuple(selected), tuple(cumulative_counts(counts)))


class PromptedLanguageModel:
    """Bind prompt token IDs and codec settings to a deterministic logit adapter."""

    def __init__(
        self,
        adapter: LogitModel,
        prompt_ids: Sequence[int],
        config: CandidateConfig,
    ) -> None:
        self.adapter = adapter
        self.prompt_ids = tuple(prompt_ids)
        self.config = config

    def tokenize(self, text: str) -> list[int]:
        return self.adapter.tokenize(text)

    def detokenize(self, token_ids: Sequence[int]) -> str:
        return self.adapter.detokenize(token_ids)

    def next_table(self, visible_prefix: Sequence[int]) -> CandidateTable:
        context = (*self.prompt_ids, *visible_prefix)
        return build_candidate_table(self.adapter, context, visible_prefix, self.config)
