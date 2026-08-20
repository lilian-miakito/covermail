"""Qualified MLX-LM adapter for the active Qwen 3.5 darwin-arm64 profile."""

from __future__ import annotations

import json
import platform
import sys
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal, cast

from covermail.codec.candidates import quantize_logit
from covermail.cover.prompt import ChatTemplateTokenizer, render_chat_prompt
from covermail.errors import ModelProfileError
from covermail.models.manifest import verify_artifact_manifest

PROFILE_ID = "darwin-arm64-mlx"
MODEL_ID = "mlx-community/Qwen3.5-4B-4bit"
MODEL_REVISION = "0e7ffd5c629ef7719d4cbc04069232580bfa9d9c"
MODEL_ARTIFACT_PATHS = (
    "chat_template.jinja",
    "config.json",
    "model.safetensors",
    "model.safetensors.index.json",
    "tokenizer.json",
    "tokenizer_config.json",
)
QUALIFIED_PYTHON = "3.12.8"
QUALIFIED_PACKAGES = {
    "jinja2": "3.1.6",
    "mlx": "0.31.2",
    "mlx-lm": "0.31.3",
    "numpy": "2.5.1",
    "safetensors": "0.8.0",
    "tokenizers": "0.22.2",
    "transformers": "5.14.1",
}

_CONTROL_TOKEN_TEXTS = (
    "<think>",
    "</think>",
    "<|endoftext|>",
    "<|im_start|>",
    "<|im_end|>",
    "<|vision_start|>",
    "<|vision_end|>",
    "<|vision_pad|>",
    "<|image_pad|>",
    "<|video_pad|>",
)


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
    if not isinstance(value, dict) or value.get("model_type") != "qwen3_5":
        raise ModelProfileError("model config is not the qualified Qwen 3.5 architecture")
    if value.get("architectures") != ["Qwen3_5ForConditionalGeneration"]:
        raise ModelProfileError("model config does not name the qualified Qwen 3.5 class")
    if "model_file" in value or "auto_map" in value:
        raise ModelProfileError("model config requests executable or remote model code")
    text_config = value.get("text_config")
    if not isinstance(text_config, dict) or text_config.get("model_type") != "qwen3_5_text":
        raise ModelProfileError("model config has no qualified Qwen 3.5 text architecture")
    expected_text = {
        "head_dim": 256,
        "hidden_size": 2560,
        "num_attention_heads": 16,
        "num_hidden_layers": 32,
        "num_key_value_heads": 4,
        "vocab_size": 248320,
    }
    if any(text_config.get(name) != expected for name, expected in expected_text.items()):
        raise ModelProfileError("model config does not match the qualified Qwen 3.5 layout")
    if "model_file" in text_config or "auto_map" in text_config:
        raise ModelProfileError("Qwen 3.5 text config requests executable or remote model code")
    quantization = value.get("quantization")
    if not isinstance(quantization, dict):
        raise ModelProfileError("model config has no qualified MLX quantization")
    if (
        quantization.get("bits") != 4
        or quantization.get("group_size") != 64
        or quantization.get("mode") != "affine"
    ):
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
        self._special_ids: set[int] | None = None

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

    def render_prompt(
        self,
        cover: Mapping[str, object],
        phase: Literal["prefix", "payload", "finish"],
        *,
        writing_brief: str = "",
    ) -> str:
        return render_chat_prompt(self.chat_tokenizer, cover, phase, writing_brief=writing_brief)

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
        if self._special_ids is not None:
            return self._special_ids
        values = set(self._tokenizer.all_special_ids)
        values.update(self._tokenizer.eos_token_ids)
        for attribute in (
            "think_start_tokens",
            "think_end_tokens",
            "tool_call_start_tokens",
            "tool_call_end_tokens",
        ):
            tokens = getattr(self._tokenizer, attribute, None)
            if tokens is not None:
                values.update(tokens)
        vocabulary = self._tokenizer.get_vocab()
        values.update(vocabulary[token] for token in _CONTROL_TOKEN_TEXTS if token in vocabulary)
        self._special_ids = {int(token_id) for token_id in values if token_id is not None}
        return self._special_ids

    def eos_token_ids(self) -> set[int]:
        return {int(token_id) for token_id in self._tokenizer.eos_token_ids}

    def _next_logits(self, context_ids: Sequence[int]) -> Any:
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
        self._last_context = context
        return logits

    def _ranked_logits(
        self,
        context_ids: Sequence[int],
        limit: int,
        *,
        excluded_ids: set[int],
    ) -> Sequence[tuple[int, float]]:
        """Return an exact quantized ranking without copying the full vocabulary.

        MLX selects a growing raw-logit superset on Metal. CPU float32
        quantization and token-ID tie breaking remain normative. Expansion
        continues until the requested quantized boundary is provably complete.
        """
        if limit <= 0:
            raise ModelProfileError("ranked-logit limit must be positive")
        logits = self._next_logits(context_ids)
        vocabulary_size = int(logits.shape[0])
        if limit + len(excluded_ids) > vocabulary_size:
            raise ModelProfileError("ranked-logit limit exceeds the model vocabulary")

        finite = self._mx.all(self._mx.isfinite(logits))
        self._mx.eval(logits, finite)
        if not bool(finite.item()):
            raise ModelProfileError("MLX returned a non-finite float32 logit")

        target = limit + len(excluded_ids)
        fetch = min(vocabulary_size, max(target * 2, target + 256))
        while True:
            if fetch == vocabulary_size:
                token_ids = list(range(vocabulary_size))
                values = logits.tolist()
            else:
                partitioned = self._mx.argpartition(logits, vocabulary_size - fetch)
                selected_ids = partitioned[vocabulary_size - fetch :]
                selected_values = self._mx.take(logits, selected_ids)
                self._mx.eval(selected_ids, selected_values)
                token_ids = selected_ids.tolist()
                values = selected_values.tolist()
            if not isinstance(token_ids, list) or not isinstance(values, list):
                raise ModelProfileError("MLX returned an invalid ranked-logit vector")

            scored = [
                (quantize_logit(float(value)), int(token_id), float(value))
                for token_id, value in zip(token_ids, values, strict=True)
            ]
            eligible = [item for item in scored if item[1] not in excluded_ids]
            eligible.sort(key=lambda item: (-item[0], item[1]))
            if len(eligible) < limit:
                raise ModelProfileError("MLX returned too few eligible ranked logits")
            cutoff_score = eligible[limit - 1][0]
            fetched_floor = min(item[0] for item in scored)
            if fetch == vocabulary_size or cutoff_score > fetched_floor:
                return [(token_id, value) for _, token_id, value in eligible[:limit]]
            fetch = min(vocabulary_size, fetch * 2)

    def ranked_logits(self, context_ids: Sequence[int], limit: int) -> Sequence[tuple[int, float]]:
        """Return the exact arithmetic-candidate ranking, excluding special IDs."""
        return self._ranked_logits(
            context_ids,
            limit,
            excluded_ids=self.special_token_ids(),
        )

    def ranked_logits_including_specials(
        self, context_ids: Sequence[int], limit: int
    ) -> Sequence[tuple[int, float]]:
        """Return the exact greedy ranking, including EOS as a possible stop."""
        return self._ranked_logits(context_ids, limit, excluded_ids=set())
