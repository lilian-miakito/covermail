from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from covermail.codec.candidates import (
    CandidateConfig,
    PromptedLanguageModel,
    adjusted_score,
    build_candidate_table,
    is_visible_token,
    quantize_logit,
)


class CharacterLogitModel:
    def __init__(self) -> None:
        self.texts = [
            "a",
            "b",
            "c",
            "d",
            "e",
            "prompt",
            "<|x|>",
            " ",
            "!",
            "f",
            "g",
            "h",
        ]
        self.ids = {text: index for index, text in enumerate(self.texts)}
        self.last_context: tuple[int, ...] = ()

    def tokenize(self, text: str) -> list[int]:
        return [self.ids[character] for character in text]

    def detokenize(self, token_ids: Sequence[int]) -> str:
        return "".join(self.texts[token_id] for token_id in token_ids)

    def ranked_logits(self, context_ids: Sequence[int], limit: int) -> Sequence[tuple[int, float]]:
        self.last_context = tuple(context_ids)
        logits = [9.0, 8.0, 7.0, 6.0, 5.0, 20.0, 19.0, 18.0, 4.0, 3.0, 2.0, 1.0]
        specials = self.special_token_ids()
        ranked = sorted(
            (
                (token_id, logit)
                for token_id, logit in enumerate(logits)
                if token_id not in specials
            ),
            key=lambda item: (-quantize_logit(item[1]), item[0]),
        )
        return ranked[:limit]

    def special_token_ids(self) -> set[int]:
        return {5, 6, 7, 8}

    def ranked_logits_including_specials(
        self, context_ids: Sequence[int], limit: int
    ) -> Sequence[tuple[int, float]]:
        self.last_context = tuple(context_ids)
        logits = [9.0, 8.0, 7.0, 6.0, 5.0, 20.0, 19.0, 18.0, 4.0, 3.0, 2.0, 1.0]
        return sorted(
            enumerate(logits),
            key=lambda item: (-quantize_logit(item[1]), item[0]),
        )[:limit]

    def eos_token_ids(self) -> set[int]:
        return {11}


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


def test_greedy_finish_selects_the_highest_copy_safe_visible_token() -> None:
    model = CharacterLogitModel()
    prompted = PromptedLanguageModel(model, [5], CandidateConfig(2, 2, 1000))
    selected = prompted.next_greedy_token([])
    assert selected is not None
    assert selected.token_id == model.ids["a"]


def test_greedy_finish_uses_only_the_configured_visible_suffix() -> None:
    model = CharacterLogitModel()
    prompted = PromptedLanguageModel(
        model,
        [model.ids["prompt"]],
        CandidateConfig(2, 2, 1000),
        context_token_limit=2,
    )
    prefix = [model.ids[character] for character in "abcd"]
    assert prompted.next_greedy_token(prefix) is not None
    assert model.last_context == (
        model.ids["prompt"],
        model.ids["c"],
        model.ids["d"],
    )
