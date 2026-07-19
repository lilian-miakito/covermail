from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.canonical import read_address_file
from covermail.address.schema import validate_address
from covermail.cover.primer import extract_primer
from covermail.models.mlx_adapter import (
    MODEL_ARTIFACT_PATHS,
    MODEL_ID,
    MODEL_REVISION,
    PROFILE_ID,
    QUALIFIED_PACKAGES,
)
from covermail.service import decrypt_message


def test_real_profile_address_fixture_is_complete_and_valid() -> None:
    directory = Path(__file__).parent / "fixtures/mlx_llama32_3b_4bit"
    address = validate_address(read_address_file(directory / "address.json"))
    assert address["model"]["model_id"] == MODEL_ID
    assert address["model"]["revision"] == MODEL_REVISION
    assert address["model"]["runtime"]["profile"] == PROFILE_ID
    assert address["model"]["runtime"]["packages"] == QUALIFIED_PACKAGES
    assert [entry["path"] for entry in address["model"]["artifacts"]] == sorted(
        MODEL_ARTIFACT_PATHS
    )
    assert address["codec"]["id"] == "cm-arithmetic"
    assert address["codec"]["self_test"]["expected_sha256"] != "0" * 64


def test_real_profile_carrier_fixture_round_trip_evidence() -> None:
    directory = Path(__file__).parent / "fixtures/mlx_llama32_3b_4bit"
    address = validate_address(read_address_file(directory / "address.json"))
    fixture = json.loads((directory / "fixture.json").read_text(encoding="utf-8"))
    carrier = base64.b64decode(fixture["carrier_base64"], validate=True).decode("utf-8")
    stream = base64.b64decode(fixture["stream_base64"], validate=True)
    private_key = x25519.X25519PrivateKey.from_private_bytes(bytes(range(1, 33)))

    assert extract_primer(carrier) == fixture["primer"]
    assert len(carrier) == fixture["metrics"]["characters_all"]
    assert len(carrier.encode()) == fixture["metrics"]["utf8_bytes_all"]
    assert carrier.count("\n") == fixture["metrics"]["line_feeds"]
    assert len(carrier) / len(stream) == fixture["ratios"]["k_all_characters_per_stream_byte"]
    assert decrypt_message(
        address,
        private_key,
        stream,
        fixture["subject"],
        fixture["primer"],
    )[1] == fixture["plaintext"]
