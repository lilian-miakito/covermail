"""Fast deterministic model/tokenizer for core codec tests and demos."""

from __future__ import annotations

import string
from collections.abc import Iterable, Mapping, Sequence

from covermail.codec.candidates import Candidate, CandidateTable, GreedyToken, is_copy_safe
from covermail.codec.frequencies import (
    FREQUENCY_TOTAL,
    cumulative_counts,
    deterministic_weights,
    frequency_counts,
)
from covermail.errors import CarrierGenerationError, CarrierTokenizationError

_VISIBLE_CHARACTERS = tuple(
    dict.fromkeys(
        string.ascii_letters
        + " \n"
        + "àâäçéèêëîïôöùûüÿœæ"
        + "αβγδεζηθικλμνξοπρστυφχψω"
        + "абвгдежзийклмнопрстуфхцчшщыэюя"
        + ".!?"
    )
)
_FAKE_CLOSING = "\n\namicalement."


class FakeLanguageModel:
    """A reversible character tokenizer with deterministic candidate tables.

    It is intentionally not a plausible language model. Optional merge tokens,
    special tokens, custom scores, and low-entropy steps exercise codec edges.
    """

    def __init__(
        self,
        *,
        top_n: int = 16,
        temperature_milli: int = 1000,
        finish_period: int = 7,
        candidate_pool_multiplier: int = 4,
        low_entropy_steps: Iterable[int] = (),
        merge_tokens: Mapping[str, int] | None = None,
        special_token_ids: Iterable[int] = (),
    ) -> None:
        if not 2 <= top_n <= 64:
            raise ValueError("fake model top_n must be 2..64")
        if finish_period < 1:
            raise ValueError("finish_period must be positive")
        if not 1 <= candidate_pool_multiplier <= 16:
            raise ValueError("candidate_pool_multiplier must be 1..16")
        self.top_n = top_n
        self.temperature_milli = temperature_milli
        self.finish_period = finish_period
        self.candidate_pool_multiplier = candidate_pool_multiplier
        self.low_entropy_steps = frozenset(low_entropy_steps)
        self._texts: dict[int, str] = {
            token_id: text for token_id, text in enumerate(_VISIBLE_CHARACTERS)
        }
        self._single_ids = {text: token_id for token_id, text in self._texts.items()}
        self._merge_tokens = dict(merge_tokens or {})
        for text, token_id in self._merge_tokens.items():
            if len(text) < 2 or token_id in self._texts or token_id < 0:
                raise ValueError("merge tokens need unique non-negative IDs and multi-char text")
            if any(character not in self._single_ids for character in text):
                raise ValueError("merge token contains an unknown character")
            self._texts[token_id] = text
        self._special_token_ids = frozenset(special_token_ids)
        self._period_token = self._single_ids["."]
        self._ordinary_ids = tuple(
            token_id for token_id, text in self._texts.items() if text not in {".", "!", "?"}
        )

    def tokenize(self, text: str) -> list[int]:
        merge_items = sorted(self._merge_tokens.items(), key=lambda item: (-len(item[0]), item[1]))
        result: list[int] = []
        offset = 0
        while offset < len(text):
            matched = False
            for merge_text, token_id in merge_items:
                if text.startswith(merge_text, offset):
                    result.append(token_id)
                    offset += len(merge_text)
                    matched = True
                    break
            if matched:
                continue
            character = text[offset]
            try:
                result.append(self._single_ids[character])
            except KeyError as error:
                raise CarrierTokenizationError(
                    "fake carrier contains an unknown character"
                ) from error
            offset += 1
        return result

    def detokenize(self, token_ids: Sequence[int]) -> str:
        try:
            return "".join(self._texts[token_id] for token_id in token_ids)
        except KeyError as error:
            raise CarrierTokenizationError("fake token sequence contains an unknown ID") from error

    def special_token_ids(self) -> set[int]:
        return set(self._special_token_ids)

    def _candidate_pool(self, visible_prefix: Sequence[int]) -> list[int]:
        position = len(visible_prefix)
        seed = sum((index + 1) * (token_id + 17) for index, token_id in enumerate(visible_prefix))
        ordinary = self._ordinary_ids
        offset = (seed + position * 29) % len(ordinary)
        rotated = [*ordinary[offset:], *ordinary[:offset]]
        if (position + 1) % self.finish_period == 0:
            rotated.insert(0, self._period_token)
        else:
            rotated.append(self._period_token)
        return rotated[: self.top_n * self.candidate_pool_multiplier]

    def next_table(self, visible_prefix: Sequence[int]) -> CandidateTable:
        candidates: list[Candidate] = []
        for token_id in self._candidate_pool(visible_prefix):
            if token_id in self._special_token_ids:
                continue
            if not is_copy_safe(self, visible_prefix, token_id):
                continue
            candidates.append(
                Candidate(
                    token_id=token_id,
                    token_text=self._texts[token_id],
                    adjusted_score=-len(candidates),
                )
            )
            if len(candidates) == self.top_n:
                break
        if len(candidates) != self.top_n:
            raise CarrierGenerationError("fake model produced too few copy-safe candidates")

        if len(visible_prefix) in self.low_entropy_steps:
            counts = [FREQUENCY_TOTAL - (self.top_n - 1), *([1] * (self.top_n - 1))]
        else:
            scores = [candidate.adjusted_score for candidate in candidates]
            counts = frequency_counts(deterministic_weights(scores, self.temperature_milli))
        return CandidateTable(tuple(candidates), tuple(cumulative_counts(counts)))

    def next_greedy_token(self, visible_prefix: Sequence[int]) -> GreedyToken | None:
        visible = self.detokenize(visible_prefix)
        matched = 0
        for length in range(min(len(visible), len(_FAKE_CLOSING)), -1, -1):
            if visible.endswith(_FAKE_CLOSING[:length]):
                matched = length
                break
        if matched == len(_FAKE_CLOSING):
            return None
        token_id = self._single_ids[_FAKE_CLOSING[matched]]
        return GreedyToken(token_id, self._texts[token_id])
