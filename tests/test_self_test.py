from __future__ import annotations

import pytest

from covermail.codec.fake_model import FakeLanguageModel
from covermail.codec.self_test import compute_self_test, verify_self_test
from covermail.errors import ModelCompatibilityError


def test_self_test_transcript_fixture_and_verification() -> None:
    model = FakeLanguageModel(top_n=4)
    result = compute_self_test(model, "fixed prompt", [0, 1, 3, 0])
    assert result.sha256 == "44f7a06566c84fb01767532de48dbef651754b668ba1d61cccd902615374a4d2"
    assert len(result.transcript) == 4 * (4 + 32 + 2 + 4 * 6)
    assert len(result.selected_token_ids) == 4
    assert verify_self_test(model, "fixed prompt", [0, 1, 3, 0], result.sha256) == result


def test_self_test_fails_closed_on_digest_mismatch() -> None:
    with pytest.raises(ModelCompatibilityError, match="failed"):
        verify_self_test(FakeLanguageModel(top_n=4), "fixed prompt", [0, 1, 3, 0], "0" * 64)
