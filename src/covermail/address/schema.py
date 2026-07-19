"""Strict v1 Covermail Address schema validation."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, cast

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.canonical import decode_base64url
from covermail.errors import AddressValidationError

type Address = dict[str, Any]

_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{7,128}\Z")
_LANGUAGE = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*\Z")
_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_BACKEND = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_PROFILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_PYTHON_VERSION = re.compile(r"3\.1[2-3]\.\d+(?:[a-z0-9.+-]*)?\Z")
_PACKAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_PACKAGE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.!+_-]{0,127}\Z")

_TOP_LEVEL = {"format", "version", "recipient", "hpke", "model", "codec", "cover"}
_RECIPIENT = {"label", "hpke_public_key"}
_HPKE = {"kem", "kdf", "aead", "mode"}
_MODEL = {"backend", "model_id", "revision", "artifacts", "runtime"}
_ARTIFACT = {"path", "size", "sha256"}
_RUNTIME = {
    "profile",
    "python_version",
    "packages",
    "logits_dtype",
    "trust_remote_code",
}
_CODEC = {
    "id",
    "top_n",
    "candidate_pool_multiplier",
    "frequency_total",
    "logit_scale",
    "temperature_milli",
    "length_bias_milli",
    "finish_tokens",
    "visible_filter",
    "prompt_template",
    "self_test",
}
_SELF_TEST = {"steps", "path_indices", "expected_sha256"}
_COVER = {
    "language",
    "relationship",
    "tone",
    "persona_sender",
    "persona_recipient",
    "standing_context",
    "max_sentences",
    "max_questions",
    "max_visible_characters",
}
_FORBIDDEN_ARTIFACT_SUFFIXES = {".bin", ".pt", ".pth", ".pkl", ".pickle", ".py", ".pyc"}


def _object(value: object, path: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AddressValidationError(f"{path} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise AddressValidationError(f"{path} has a non-string field name")
    keys = set(value)
    missing = fields - keys
    unknown = keys - fields
    if missing:
        raise AddressValidationError(f"{path} is missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise AddressValidationError(f"{path} has unknown fields: {', '.join(sorted(unknown))}")
    return cast(dict[str, Any], value)


def _string(
    value: object,
    path: str,
    *,
    minimum: int = 0,
    maximum: int,
    ascii_only: bool = False,
) -> str:
    if not isinstance(value, str):
        raise AddressValidationError(f"{path} must be a string")
    try:
        raw = value.encode("ascii" if ascii_only else "utf-8", errors="strict")
    except UnicodeError as error:
        label = "ASCII" if ascii_only else "valid Unicode"
        raise AddressValidationError(f"{path} must be {label}") from error
    if not minimum <= len(raw) <= maximum:
        raise AddressValidationError(f"{path} byte length is outside {minimum}..{maximum}")
    return value


def _integer(value: object, path: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AddressValidationError(f"{path} must be an integer")
    if not minimum <= value <= maximum:
        raise AddressValidationError(f"{path} is outside {minimum}..{maximum}")
    return value


def _literal(value: object, path: str, expected: object) -> None:
    if type(value) is not type(expected) or value != expected:
        raise AddressValidationError(f"{path} must equal {expected!r}")


def _matching(value: object, path: str, pattern: re.Pattern[str], maximum: int) -> str:
    text = _string(value, path, minimum=1, maximum=maximum, ascii_only=True)
    if pattern.fullmatch(text) is None:
        raise AddressValidationError(f"{path} has invalid syntax")
    return text


def _validate_recipient(value: object) -> None:
    recipient = _object(value, "recipient", _RECIPIENT)
    _string(recipient["label"], "recipient.label", minimum=1, maximum=128)
    key_text = _string(
        recipient["hpke_public_key"],
        "recipient.hpke_public_key",
        minimum=1,
        maximum=64,
        ascii_only=True,
    )
    raw = decode_base64url(key_text)
    if len(raw) != 32:
        raise AddressValidationError("recipient.hpke_public_key must contain 32 bytes")
    try:
        x25519.X25519PublicKey.from_public_bytes(raw)
    except ValueError as error:
        raise AddressValidationError("recipient.hpke_public_key is not X25519") from error


def _validate_hpke(value: object) -> None:
    hpke = _object(value, "hpke", _HPKE)
    expected = {
        "kem": "DHKEM_X25519_HKDF_SHA256",
        "kdf": "HKDF_SHA256",
        "aead": "AES_128_GCM",
        "mode": "BASE",
    }
    for name, literal in expected.items():
        _literal(hpke[name], f"hpke.{name}", literal)


def _validate_artifact(value: object, index: int) -> None:
    path_label = f"model.artifacts[{index}]"
    artifact = _object(value, path_label, _ARTIFACT)
    text = _string(artifact["path"], f"{path_label}.path", minimum=1, maximum=512)
    if "\x00" in text or "\\" in text or text.startswith("/"):
        raise AddressValidationError(f"{path_label}.path is not a safe relative POSIX path")
    parsed = PurePosixPath(text)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in text.split("/")):
        raise AddressValidationError(f"{path_label}.path is not a safe relative POSIX path")
    if re.match(r"^[A-Za-z]:", text) or parsed.suffix.casefold() in _FORBIDDEN_ARTIFACT_SUFFIXES:
        raise AddressValidationError(f"{path_label}.path refers to a forbidden artifact type")
    _integer(artifact["size"], f"{path_label}.size", 0, (1 << 40) - 1)
    digest = _string(
        artifact["sha256"], f"{path_label}.sha256", minimum=64, maximum=64, ascii_only=True
    )
    if _HEX_64.fullmatch(digest) is None:
        raise AddressValidationError(f"{path_label}.sha256 must be lowercase hexadecimal")


def _validate_model(value: object) -> None:
    model = _object(value, "model", _MODEL)
    _matching(model["backend"], "model.backend", _BACKEND, 64)
    _matching(model["model_id"], "model.model_id", _MODEL_ID, 256)
    _matching(model["revision"], "model.revision", _REVISION, 128)

    artifacts = model["artifacts"]
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 256:
        raise AddressValidationError("model.artifacts must contain 1..256 entries")
    seen_paths: set[str] = set()
    for index, artifact in enumerate(artifacts):
        _validate_artifact(artifact, index)
        artifact_path = cast(dict[str, object], artifact)["path"]
        if not isinstance(artifact_path, str):  # guarded above; keeps this local assertion explicit
            raise AddressValidationError("model artifact path must be a string")
        if artifact_path in seen_paths:
            raise AddressValidationError("model.artifacts contains a duplicate path")
        seen_paths.add(artifact_path)

    runtime = _object(model["runtime"], "model.runtime", _RUNTIME)
    _matching(runtime["profile"], "model.runtime.profile", _PROFILE, 128)
    _matching(runtime["python_version"], "model.runtime.python_version", _PYTHON_VERSION, 64)
    packages = runtime["packages"]
    if not isinstance(packages, dict) or not 1 <= len(packages) <= 64:
        raise AddressValidationError("model.runtime.packages must contain 1..64 entries")
    for name, version in packages.items():
        _matching(name, "model.runtime.packages.<name>", _PACKAGE_NAME, 128)
        _matching(version, f"model.runtime.packages.{name}", _PACKAGE_VERSION, 128)
    _literal(runtime["logits_dtype"], "model.runtime.logits_dtype", "float32")
    _literal(runtime["trust_remote_code"], "model.runtime.trust_remote_code", False)


def _validate_codec(value: object) -> None:
    codec = _object(value, "codec", _CODEC)
    codec_id = _string(codec["id"], "codec.id", minimum=1, maximum=64, ascii_only=True)
    if codec_id not in {"cm-arithmetic-v1", "cm-arithmetic-v2"}:
        raise AddressValidationError("codec.id is not a supported arithmetic profile")
    top_n = _integer(codec["top_n"], "codec.top_n", 2, 512)
    multiplier = _integer(
        codec["candidate_pool_multiplier"], "codec.candidate_pool_multiplier", 1, 16
    )
    if top_n * multiplier > 4096:
        raise AddressValidationError("codec candidate pool exceeds 4096")
    _literal(codec["frequency_total"], "codec.frequency_total", 32768)
    _literal(codec["logit_scale"], "codec.logit_scale", 1024)
    _integer(codec["temperature_milli"], "codec.temperature_milli", 100, 2000)
    length_bias = _integer(codec["length_bias_milli"], "codec.length_bias_milli", 0, 1000)
    _integer(codec["finish_tokens"], "codec.finish_tokens", 0, 128)
    _literal(codec["visible_filter"], "codec.visible_filter", "cm-visible-email-v1")
    expected_prompt = (
        "cm-email-one-paragraph-v1"
        if codec_id == "cm-arithmetic-v1"
        else "cm-email-continue-primer-v2"
    )
    _literal(codec["prompt_template"], "codec.prompt_template", expected_prompt)
    if codec_id == "cm-arithmetic-v2" and length_bias != 0:
        raise AddressValidationError("cm-arithmetic-v2 requires zero length bias")

    self_test = _object(codec["self_test"], "codec.self_test", _SELF_TEST)
    _literal(self_test["steps"], "codec.self_test.steps", 4)
    path = self_test["path_indices"]
    if not isinstance(path, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in path
    ):
        raise AddressValidationError("codec.self_test.path_indices must be an integer array")
    if path != [0, 1, top_n - 1, 0]:
        raise AddressValidationError("codec.self_test.path_indices is not the required path")
    digest = _string(
        self_test["expected_sha256"],
        "codec.self_test.expected_sha256",
        minimum=64,
        maximum=64,
        ascii_only=True,
    )
    if _HEX_64.fullmatch(digest) is None:
        raise AddressValidationError("codec.self_test.expected_sha256 must be lowercase hex")


def _validate_cover(value: object) -> None:
    cover = _object(value, "cover", _COVER)
    language = _string(cover["language"], "cover.language", minimum=2, maximum=64, ascii_only=True)
    if _LANGUAGE.fullmatch(language) is None:
        raise AddressValidationError("cover.language has invalid BCP-47-like syntax")
    for name in ("relationship", "tone", "persona_sender", "persona_recipient"):
        _string(cover[name], f"cover.{name}", minimum=1, maximum=512)
    _string(cover["standing_context"], "cover.standing_context", maximum=512)
    max_sentences = _integer(cover["max_sentences"], "cover.max_sentences", 1, 8)
    max_questions = _integer(cover["max_questions"], "cover.max_questions", 0, 2)
    if max_questions > max_sentences:
        raise AddressValidationError("cover.max_questions exceeds max_sentences")
    _integer(cover["max_visible_characters"], "cover.max_visible_characters", 200, 20000)


def validate_address(value: object) -> Address:
    """Validate and return a v1 address without mutating it."""
    address = _object(value, "$", _TOP_LEVEL)
    _literal(address["format"], "format", "covermail-address")
    _literal(address["version"], "version", 1)
    _validate_recipient(address["recipient"])
    _validate_hpke(address["hpke"])
    _validate_model(address["model"])
    _validate_codec(address["codec"])
    _validate_cover(address["cover"])
    return address
