"""Qualified MLX-LM adapter for the first darwin-arm64 model profile."""

from __future__ import annotations

import json
import platform
import sys
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

from covermail.cover.prompt import (
    ChatTemplateTokenizer,
    render_chat_prompt,
    render_chat_prompt_v2,
)
from covermail.errors import ModelProfileError
from covermail.models.manifest import verify_artifact_manifest

PROFILE_ID = "darwin-arm64-mlx-v1"
MODEL_ID = "mlx-community/Llama-3.2-3B-Instruct-4bit"
MODEL_REVISION = "7f0dc925e0d0afb0322d96f9255cfddf2ba5636e"
MODEL_ARTIFACT_PATHS = (
    "config.json",
    "model.safetensors",
    "model.safetensors.index.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)
QUALIFIED_PYTHON = "3.12.5"
QUALIFIED_PACKAGES = {
    "jinja2": "3.1.6",
    "mlx": "0.31.2",
    "mlx-lm": "0.31.3",
    "numpy": "2.5.1",
    "safetensors": "0.8.0",
    "tokenizers": "0.22.2",
    "transformers": "5.14.1",
}


def runtime_fingerprint() -> dict[str, object]:
    packages: dict[str, str] = {}
    for package in QUALIFIED_PACKAGES:
        try:
            packages[package] = version(package)
        except PackageNotFoundError as error:
            raise ModelProfileError(f"qualified runtime package is missing: {package}") from error
    return {
        "profile": PROFILE_ID,
        "python_version": platform.python_version(),
        "packages": packages,
        "logits_dtype": "float32",
        "trust_remote_code": False,
    }


def verify_runtime() -> dict[str, object]:
    fingerprint = runtime_fingerprint()
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise ModelProfileError("MLX profile requires darwin-arm64")
    if fingerprint["python_version"] != QUALIFIED_PYTHON:
        raise ModelProfileError("Python patch version does not match the qualified profile")
    if fingerprint["packages"] != QUALIFIED_PACKAGES:
        raise ModelProfileError("package versions do not match the qualified profile")
    return fingerprint


def _validate_model_config(root: Path) -> None:
    try:
        value = json.loads((root / "config.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ModelProfileError("model config is not valid local JSON") from error
    if not isinstance(value, dict) or value.get("model_type") != "llama":
        raise ModelProfileError("model config is not the qualified Llama architecture")
    if "model_file" in value or "auto_map" in value:
        raise ModelProfileError("model config requests executable or remote model code")
    quantization = value.get("quantization")
    if not isinstance(quantization, dict):
        raise ModelProfileError("model config has no qualified MLX quantization")
    if quantization.get("bits") != 4 or quantization.get("group_size") != 64:
        raise ModelProfileError("model config quantization does not match the profile")


class MlxLanguageModel:
    """Direct-logit adapter; construction is possible only after all checks pass."""

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        mx_module: Any,
        cache_factory: Callable[[Any], Any],
    ) -> None:
        self._model = model
        self._tokenizer = tokenizer
        self._mx = mx_module
        self._cache_factory = cache_factory
        self._cache: Any = None
        self._last_context: tuple[int, ...] = ()

    @classmethod
    def load(
        cls,
        root: Path,
        artifacts: Sequence[Mapping[str, object]],
    ) -> MlxLanguageModel:
        verify_runtime()
        verify_artifact_manifest(root, artifacts)
        _validate_model_config(root)
        try:
            import mlx.core as mx
            from mlx_lm import load
            from mlx_lm.models.cache import make_prompt_cache

            model, tokenizer = cast(
                tuple[Any, Any],
                load(
                    str(root),
                    tokenizer_config={
                        "local_files_only": True,
                        "trust_remote_code": False,
                    },
                    lazy=False,
                    return_config=False,
                ),
            )
            model.eval()
        except Exception as error:
            raise ModelProfileError("qualified MLX model could not be loaded") from error
        return cls(model, tokenizer, mx, make_prompt_cache)

    @property
    def chat_tokenizer(self) -> ChatTemplateTokenizer:
        return cast(ChatTemplateTokenizer, self._tokenizer)

    def render_prompt(self, cover: Mapping[str, object], subject: str) -> str:
        return render_chat_prompt(self.chat_tokenizer, cover, subject)

    def render_prompt_v2(
        self, cover: Mapping[str, object], subject: str, primer: str
    ) -> str:
        return render_chat_prompt_v2(self.chat_tokenizer, cover, subject, primer)

    def tokenize(self, text: str) -> list[int]:
        token_ids = self._tokenizer.encode(text, add_special_tokens=False)
        return [int(token_id) for token_id in token_ids]

    def detokenize(self, token_ids: Sequence[int]) -> str:
        result = self._tokenizer.decode(
            list(token_ids),
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        )
        if not isinstance(result, str):
            raise ModelProfileError("tokenizer returned a non-text decoding")
        return result

    def special_token_ids(self) -> set[int]:
        values = set(self._tokenizer.all_special_ids)
        values.update(self._tokenizer.eos_token_ids)
        return {int(token_id) for token_id in values if token_id is not None}

    def next_logits(self, context_ids: Sequence[int]) -> Sequence[float]:
        if not context_ids:
            raise ModelProfileError("model context is empty")
        context = tuple(context_ids)
        if (
            self._cache is not None
            and len(context) == len(self._last_context) + 1
            and context[:-1] == self._last_context
        ):
            input_ids = [context[-1]]
        else:
            self._cache = self._cache_factory(self._model)
            input_ids = list(context)
        inputs = self._mx.array([input_ids], dtype=self._mx.int32)
        logits = self._model(inputs, cache=self._cache)[0, -1, :].astype(self._mx.float32)
        self._mx.eval(logits)
        self._last_context = context
        values = logits.tolist()
        if not isinstance(values, list):
            raise ModelProfileError("MLX returned an invalid logit vector")
        return cast(list[float], values)
