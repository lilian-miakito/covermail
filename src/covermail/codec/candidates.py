"""Candidate records and tokenizer-stability helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from covermail.codec.frequencies import table_counts


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


class TokenModel(Protocol):
    def tokenize(self, text: str) -> list[int]: ...

    def detokenize(self, token_ids: Sequence[int]) -> str: ...

    def next_table(self, visible_prefix: Sequence[int]) -> CandidateTable: ...


def is_copy_safe(model: TokenModel, visible_prefix: Sequence[int], token_id: int) -> bool:
    expected = [*visible_prefix, token_id]
    return model.tokenize(model.detokenize(expected)) == expected
