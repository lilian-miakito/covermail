from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from covermail.codec.candidates import (
    CandidateConfig,
    adjusted_score,
    build_candidate_table,
    is_visible_token,
    quantize_logit,
)


class CharacterLogitModel:
    def __init__(self) -> None:
        self.texts = ["a", "b", "c", "d", "e", "prompt", "<|x|>", " ", "!"]
        self.ids = {text: index for index, text in enumerate(self.texts)}

    def tokenize(self, text: str) -> list[int]:
        return [self.ids[character] for character in text]

    def detokenize(self, token_ids: Sequence[int]) -> str:
        return "".join(self.texts[token_id] for token_id in token_ids)

    def next_logits(self, context_ids: Sequence[int]) -> Sequence[float]:
        del context_ids
        return [9.0, 8.0, 7.0, 6.0, 5.0, 20.0, 19.0, 18.0, 4.0]

    def special_token_ids(self) -> set[int]:
        return {5, 6, 7, 8}


def test_quantize_logit_casts_to_float32_and_ties_even() -> None:
    assert quantize_logit(1.5 / 1024) == 2
    assert quantize_logit(2.5 / 1024) == 2
    assert quantize_logit(1.00000001) == 1024
    with pytest.raises(ValueError, match="non-finite"):
        quantize_logit(math.inf)


def test_adjusted_score_is_the_quantized_logit() -> None:
    assert adjusted_score(1.0) == quantize_logit(1.0)


@pytest.mark.parametrize(
    "text",
    ["", "bad\rline", "bad\x00text", "\ud800"],
)
def test_visible_filter_rejects_transport_breaking_text(text: str) -> None:
    assert not is_visible_token(text)


@pytest.mark.parametrize(
    "text",
    ["bonjour", " ", "prompt", "<|x|>", "[hello]", "hello\n", "\n\n", "\t"],
)
def test_visible_filter_accepts_stable_email_text(text: str) -> None:
    assert is_visible_token(text)


def test_candidate_pool_filters_then_orders_and_builds_frequencies() -> None:
    model = CharacterLogitModel()
    table = build_candidate_table(
        model,
        context_ids=[99],
        visible_prefix=[],
        config=CandidateConfig(4, 2, 1000),
    )
    assert [candidate.token_id for candidate in table.candidates] == [0, 1, 2, 3]
    assert table.cumulative[0] == 0
    assert table.cumulative[-1] == 32768
