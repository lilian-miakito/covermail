from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.canonical import read_address_file
from covermail.address.schema import validate_address
from covermail.models.mlx_adapter import (
    MODEL_ARTIFACT_PATHS,
    MODEL_ID,
    MODEL_REVISION,
    PROFILE_ID,
    QUALIFIED_PACKAGES,
)


def test_real_profile_address_fixture_is_complete_and_valid() -> None:
    path = Path(__file__).parent / "fixtures/mlx_llama32_3b_4bit/address.json"
    address = validate_address(read_address_file(path))
    assert address["model"]["model_id"] == MODEL_ID
    assert address["model"]["revision"] == MODEL_REVISION
    assert address["model"]["runtime"]["profile"] == PROFILE_ID
    assert address["model"]["runtime"]["packages"] == QUALIFIED_PACKAGES
    assert [entry["path"] for entry in address["model"]["artifacts"]] == sorted(
        MODEL_ARTIFACT_PATHS
    )
    assert address["codec"]["self_test"]["expected_sha256"] != "0" * 64


def test_real_profile_encrypted_frame_fixture_decrypts() -> None:
    from covermail.service import decrypt_message

    directory = Path(__file__).parent / "fixtures/mlx_llama32_3b_4bit"
    address = validate_address(read_address_file(directory / "address.json"))
    fixture = json.loads((directory / "fixture.json").read_text(encoding="utf-8"))
    private_key = x25519.X25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    frame = base64.b64decode(fixture["frame_base64"], validate=True)
    _, plaintext = decrypt_message(address, private_key, frame)
    assert plaintext == fixture["plaintext"]
    carrier = (directory / "carrier.txt").read_text(encoding="utf-8").removesuffix("\n")
    assert len(carrier) == fixture["metrics"]["characters"]
    assert carrier.endswith((".", "!", "?"))
