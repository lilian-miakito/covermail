from __future__ import annotations

import json
from pathlib import Path

import pytest

from covermail.address.canonical import (
    canonical_json,
    decode_base64url,
    encode_base64url,
    load_address_json,
    read_address_file,
)
from covermail.errors import AddressParseError, AddressValidationError


@pytest.mark.parametrize("value", [b"", b"\x00", b"hello", bytes(range(256))])
def test_base64url_round_trip(value: bytes) -> None:
    assert decode_base64url(encode_base64url(value)) == value


@pytest.mark.parametrize("text", ["YQ==", "a", "+w", "/w", "é", "YW Jj"])
def test_base64url_rejects_noncanonical_input(text: str) -> None:
    with pytest.raises(AddressValidationError):
        decode_base64url(text)


def test_canonical_json_ignores_input_order_and_whitespace() -> None:
    first = load_address_json(b'{"b": 2, "a": [true, null, "caf\\u00e9"]}')
    second = load_address_json('{"a":[true,null,"café"],"b":2}'.encode())
    expected = '{"a":[true,null,"café"],"b":2}'.encode()
    assert canonical_json(first) == canonical_json(second) == expected


def test_duplicate_keys_are_rejected() -> None:
    with pytest.raises(AddressParseError, match="duplicate"):
        load_address_json(b'{"a": 1, "a": 2}')


@pytest.mark.parametrize(
    "raw",
    [
        b"[]",
        b'{"value": NaN}',
        b'{"value": 1.5}',
        b'{"value": 9223372036854775808}',
        b"\xff",
    ],
)
def test_restricted_json_profile(raw: bytes) -> None:
    with pytest.raises((AddressParseError, AddressValidationError)):
        load_address_json(raw)


def test_address_size_is_checked_before_parse() -> None:
    with pytest.raises(AddressParseError, match="too large"):
        load_address_json(b" " * ((1 << 20) + 1))


def test_address_file_read_is_bounded(tmp_path: Path) -> None:
    path = tmp_path / "huge.json"
    path.write_bytes(b" " * ((1 << 20) + 2))
    with pytest.raises(AddressParseError, match="too large"):
        read_address_file(path)


def test_canonical_rejects_python_float() -> None:
    with pytest.raises(AddressValidationError):
        canonical_json({"x": 1.0})


def test_json_loader_matches_standard_semantics() -> None:
    loaded = load_address_json(b'{"x":"\\ud83d\\ude00"}')
    assert loaded == json.loads('{"x":"\\ud83d\\ude00"}')
