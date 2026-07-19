"""Strict JSON and base64url primitives used by Covermail addresses."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from covermail.errors import AddressParseError, AddressValidationError

MAX_PUBLIC_ADDRESS_BYTES = 1 << 20
MIN_SIGNED_64 = -(1 << 63)
MAX_SIGNED_64 = (1 << 63) - 1


def encode_base64url(value: bytes) -> str:
    """Encode bytes using unpadded RFC 4648 base64url."""
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def decode_base64url(text: str) -> bytes:
    """Decode only the canonical unpadded base64url representation."""
    try:
        encoded = text.encode("ascii", errors="strict")
    except UnicodeEncodeError as error:
        raise AddressValidationError("base64url must be ASCII") from error
    if b"=" in encoded or len(encoded) % 4 == 1:
        raise AddressValidationError("non-canonical base64url length or padding")
    padding = b"=" * ((4 - len(encoded) % 4) % 4)
    try:
        value = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
    except binascii.Error as error:
        raise AddressValidationError("invalid base64url") from error
    if encode_base64url(value) != text:
        raise AddressValidationError("non-canonical base64url")
    return value


def _reject_duplicate_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AddressParseError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate_json_value(value: object, path: str = "$") -> None:
    if value is None or isinstance(value, str | bool):
        if isinstance(value, str):
            try:
                value.encode("utf-8", errors="strict")
            except UnicodeEncodeError as error:
                raise AddressValidationError(f"{path} contains invalid Unicode") from error
        return
    if isinstance(value, int):
        if not MIN_SIGNED_64 <= value <= MAX_SIGNED_64:
            raise AddressValidationError(f"{path} integer is outside signed 64-bit range")
        return
    if isinstance(value, float):
        raise AddressValidationError(f"{path} floating-point values are forbidden")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AddressValidationError(f"{path} has a non-string object key")
            _validate_json_value(key, f"{path}.<key>")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise AddressValidationError(f"{path} has unsupported JSON type {type(value).__name__}")


def load_address_json(raw: bytes) -> dict[str, Any]:
    """Parse strict UTF-8 JSON, rejecting duplicate keys before validation."""
    if len(raw) > MAX_PUBLIC_ADDRESS_BYTES:
        raise AddressParseError("address too large")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise AddressParseError("address is not valid UTF-8") from error
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_object)
    except AddressParseError:
        raise
    except (json.JSONDecodeError, RecursionError) as error:
        raise AddressParseError("address is not valid JSON") from error
    if not isinstance(value, dict):
        raise AddressParseError("address must be an object")
    _validate_json_value(value)
    return value


def read_address_file(path: Path) -> dict[str, Any]:
    """Read an address with its byte cap enforced before parsing or full allocation."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_PUBLIC_ADDRESS_BYTES + 1)
    except OSError as error:
        raise AddressParseError("address file could not be read") from error
    return load_address_json(raw)


def canonical_json(value: object) -> bytes:
    """Render the restricted Covermail canonical JSON profile."""
    _validate_json_value(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise AddressValidationError("value cannot be rendered as canonical JSON") from error
