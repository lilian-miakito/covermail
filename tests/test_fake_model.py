from __future__ import annotations

from covermail.codec.candidates import is_copy_safe
from covermail.codec.fake_model import FakeLanguageModel


def test_default_tokenizer_is_reversible() -> None:
    model = FakeLanguageModel()
    text = "abcéωя.!?"
    assert model.detokenize(model.tokenize(text)) == text


def test_merge_prone_candidate_is_not_copy_safe() -> None:
    model = FakeLanguageModel(merge_tokens={"ab": 1000})
    prefix = model.tokenize("a")
    token_b = model.tokenize("b")[0]
    assert not is_copy_safe(model, prefix, token_b)
    assert is_copy_safe(model, [], 1000)


def test_special_token_is_filtered_from_candidate_table() -> None:
    baseline = FakeLanguageModel(top_n=64)
    special_id = baseline.tokenize("a")[0]
    model = FakeLanguageModel(top_n=64, special_token_ids={special_id})
    assert special_id in model.special_token_ids()
    assert all(candidate.token_id != special_id for candidate in model.next_table([]).candidates)


def test_candidate_tables_are_context_deterministic() -> None:
    model = FakeLanguageModel(top_n=8)
    prefix = model.tokenize("bonjour")
    assert model.next_table(prefix) == model.next_table(prefix)
    assert model.next_table(prefix) != model.next_table(prefix[:-1])
