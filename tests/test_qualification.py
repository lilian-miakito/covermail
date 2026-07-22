from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from covermail.codec.fake_model import FakeLanguageModel
from covermail.errors import ModelCompatibilityError
from covermail.models.qualification import (
    QUALIFICATION_CASES,
    QUALIFICATION_FORMAT,
    QUALIFICATION_VERIFICATION_FORMAT,
    generate_qualification_bundle,
    quality_signals,
    verify_qualification_bundle,
)


def _install_fake_profile(monkeypatch: Any) -> None:
    model = FakeLanguageModel()

    def load_profile(address: object, model_root: Path, writing_brief: str = "") -> object:
        del address, model_root, writing_brief
        return SimpleNamespace(
            prefix_model=model,
            payload_model=model,
            finish_model=model,
            self_test=SimpleNamespace(
                selected_token_ids=(10, 11, 12, 13),
                sha256="a" * 64,
            ),
        )

    monkeypatch.setattr("covermail.models.qualification.load_profile", load_profile)
    monkeypatch.setattr(
        "covermail.models.qualification.quality_signals",
        lambda carrier: {"flags": []},
    )


def test_quality_signals_surface_repetition_and_signoff() -> None:
    carrier = (
        "Bonjour. Un petit mot revient souvent. Un petit mot revient souvent. "
        + "Un petit mot revient souvent. Ton ami pense à toi."
    )
    signals = quality_signals(carrier)
    flags = cast(list[str], signals["flags"])
    assert "repeated_trigrams" in flags
    assert signals["has_signoff_language"] is True
    assert signals["sentences"] == 5


def test_quality_signals_reject_non_latin_letters_for_the_french_corpus() -> None:
    signals = quality_signals("Bonjour. Un 插曲 est apparu dans le texte.")
    assert "unexpected_script" in cast(list[str], signals["flags"])


def test_fixed_corpus_bundle_round_trip_and_cross_verification(
    tmp_path: Path,
    address: dict[str, Any],
    monkeypatch: Any,
) -> None:
    _install_fake_profile(monkeypatch)
    bundle = generate_qualification_bundle(address, tmp_path)

    assert bundle["format"] == QUALIFICATION_FORMAT
    cases = cast(list[dict[str, Any]], bundle["cases"])
    assert [case["case_id"] for case in cases] == [case.case_id for case in QUALIFICATION_CASES]
    assert all(case["metrics"]["packet_bytes"] > 0 for case in cases)
    assert all(case["writing_brief"] for case in cases)

    verification = verify_qualification_bundle(address, tmp_path, bundle)
    assert verification["format"] == QUALIFICATION_VERIFICATION_FORMAT
    assert verification["all_packets_exact"] is True
    verified_cases = cast(list[dict[str, Any]], verification["cases"])
    assert all(case["exact_packet_match"] is True for case in verified_cases)


def test_bundle_verification_rejects_non_fixed_or_modified_evidence(
    tmp_path: Path,
    address: dict[str, Any],
    monkeypatch: Any,
) -> None:
    _install_fake_profile(monkeypatch)
    bundle = generate_qualification_bundle(address, tmp_path)
    modified = copy.deepcopy(bundle)
    modified_cases = cast(list[dict[str, Any]], modified["cases"])
    modified_cases[0]["writing_brief"] = "Un autre brief"

    with pytest.raises(ModelCompatibilityError, match="fixed corpus"):
        verify_qualification_bundle(address, tmp_path, modified)

    modified = copy.deepcopy(bundle)
    modified_cases = cast(list[dict[str, Any]], modified["cases"])
    modified_cases[0]["metadata_base64url"] = "AA"
    with pytest.raises(ModelCompatibilityError):
        verify_qualification_bundle(address, tmp_path, modified)


def test_bundle_verification_ignores_d_mutation(
    tmp_path: Path,
    address: dict[str, Any],
    monkeypatch: Any,
) -> None:
    _install_fake_profile(monkeypatch)
    bundle = generate_qualification_bundle(address, tmp_path)
    modified = copy.deepcopy(bundle)
    cases = cast(list[dict[str, Any]], modified["cases"])
    cases[0]["carrier"] += "x"
    assert verify_qualification_bundle(address, tmp_path, modified)["all_packets_exact"]
