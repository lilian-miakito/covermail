"""Fail-closed loading of the first exact real-model profile."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from covermail.address.schema import Address, validate_address
from covermail.codec.candidates import CandidateConfig, PromptedLanguageModel
from covermail.codec.self_test import (
    SELF_TEST_PRIMER_V2,
    SELF_TEST_SUBJECT,
    SelfTestResult,
    verify_self_test,
)
from covermail.cover.primer import validate_primer
from covermail.errors import ModelProfileError
from covermail.models.mlx_adapter import (
    MODEL_ID,
    MODEL_REVISION,
    PROFILE_ID,
    MlxLanguageModel,
    runtime_fingerprint,
)


@dataclass(frozen=True, slots=True)
class LoadedProfile:
    model: PromptedLanguageModel
    rendered_prompt: str
    primer_ids: tuple[int, ...]
    self_test: SelfTestResult


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ModelProfileError(f"address {label} is not an object")
    return cast(Mapping[str, Any], value)


def _require_exact_profile(address: Address) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    model = _mapping(address["model"], "model")
    codec = _mapping(address["codec"], "codec")
    expected_model = {
        "backend": "mlx-lm",
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
    }
    if any(model.get(name) != value for name, value in expected_model.items()):
        raise ModelProfileError("address does not name the exact qualified MLX model")
    runtime = _mapping(model.get("runtime"), "model.runtime")
    if runtime.get("profile") != PROFILE_ID or dict(runtime) != runtime_fingerprint():
        raise ModelProfileError("address runtime does not match the installed qualified profile")
    return model, codec


def load_profile(
    address: Address,
    model_root: Path,
    subject: str,
    primer: str | None = None,
) -> LoadedProfile:
    """Verify artifacts/runtime/self-test, then bind the ordinary subject prompt."""
    validated = validate_address(address)
    model_fields, codec = _require_exact_profile(validated)
    artifacts = model_fields.get("artifacts")
    if not isinstance(artifacts, list):
        raise ModelProfileError("address model artifacts are invalid")
    adapter = MlxLanguageModel.load(model_root, artifacts)
    cover = _mapping(validated["cover"], "cover")
    config = CandidateConfig(
        top_n=cast(int, codec["top_n"]),
        candidate_pool_multiplier=cast(int, codec["candidate_pool_multiplier"]),
        temperature_milli=cast(int, codec["temperature_milli"]),
        length_bias_milli=cast(int, codec["length_bias_milli"]),
    )

    codec_id = codec["id"]
    if codec_id == "cm-arithmetic-v2":
        test_prompt = adapter.render_prompt_v2(
            cover,
            SELF_TEST_SUBJECT,
            SELF_TEST_PRIMER_V2,
        )
        test_primer_ids = adapter.tokenize(SELF_TEST_PRIMER_V2)
    else:
        test_prompt = adapter.render_prompt(cover, SELF_TEST_SUBJECT)
        test_primer_ids = []
    test_model = PromptedLanguageModel(adapter, adapter.tokenize(test_prompt), config)
    self_test_fields = _mapping(codec["self_test"], "codec.self_test")
    path_indices = self_test_fields["path_indices"]
    if not isinstance(path_indices, list) or not all(
        isinstance(item, int) for item in path_indices
    ):
        raise ModelProfileError("address self-test path is invalid")
    result = verify_self_test(
        test_model,
        test_prompt,
        cast(list[int], path_indices),
        cast(str, self_test_fields["expected_sha256"]),
        initial_prefix=test_primer_ids,
    )

    if codec_id == "cm-arithmetic-v2":
        if primer is None:
            raise ModelProfileError("cm-arithmetic-v2 requires a visible primer")
        exact_primer = validate_primer(primer)
        rendered_prompt = adapter.render_prompt_v2(cover, subject, exact_primer)
        primer_ids = adapter.tokenize(exact_primer)
        if adapter.detokenize(primer_ids) != exact_primer:
            raise ModelProfileError("visible primer does not round-trip through the tokenizer")
    else:
        rendered_prompt = adapter.render_prompt(cover, subject)
        primer_ids = []
    prompted = PromptedLanguageModel(adapter, adapter.tokenize(rendered_prompt), config)
    return LoadedProfile(prompted, rendered_prompt, tuple(primer_ids), result)
