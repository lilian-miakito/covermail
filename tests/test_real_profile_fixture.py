from __future__ import annotations

import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import x25519

from covermail.address.canonical import decode_base64url, read_address_file
from covermail.address.schema import validate_address
from covermail.models.mlx_adapter import (
    MODEL_ARTIFACT_PATHS,
    MODEL_ID,
    MODEL_REVISION,
    PROFILE_ID,
    QUALIFIED_PACKAGES,
)
from covermail.models.qualification import QUALIFICATION_CASES, QUALIFICATION_FORMAT
from covermail.service import EncryptedPacket, decrypt_message


def test_real_profile_address_fixture_is_complete_and_valid() -> None:
    directory = Path(__file__).parent / "fixtures/mlx_qwen35_4b_4bit"
    address = validate_address(read_address_file(directory / "address.json"))
    assert address["model"]["model_id"] == MODEL_ID
    assert address["model"]["revision"] == MODEL_REVISION
    assert address["model"]["runtime"]["profile"] == PROFILE_ID
    assert address["model"]["runtime"]["packages"] == QUALIFIED_PACKAGES
    assert [entry["path"] for entry in address["model"]["artifacts"]] == sorted(
        MODEL_ARTIFACT_PATHS
    )
    assert address["codec"]["id"] == "cm-arithmetic"
    assert address["codec"]["prefix_tokens"] == 64
    assert address["codec"]["self_test"]["expected_sha256"] != "0" * 64


def test_real_profile_qualification_bundle_hpke_evidence() -> None:
    directory = Path(__file__).parent / "fixtures/mlx_qwen35_4b_4bit"
    address = validate_address(read_address_file(directory / "address.json"))
    bundle = json.loads((directory / "qualification.json").read_text(encoding="utf-8"))
    private_key = x25519.X25519PrivateKey.from_private_bytes(bytes(range(1, 33)))

    assert bundle["format"] == QUALIFICATION_FORMAT
    assert len(bundle["cases"]) == len(QUALIFICATION_CASES)
    expected_by_id = {case.case_id: case for case in QUALIFICATION_CASES}
    for evidence in bundle["cases"]:
        expected = expected_by_id[evidence["case_id"]]
        carrier = evidence["carrier"]
        metadata = decode_base64url(evidence["metadata_base64url"])
        body = decode_base64url(evidence["body_base64url"])
        prefix = tuple(evidence["prefix_token_ids"])
        metrics = evidence["metrics"]
        assert len(carrier) == metrics["characters_all"]
        assert len(carrier.encode()) == metrics["utf8_bytes_all"]
        assert carrier.count("\n") == evidence["quality"]["line_feeds"]
        assert (
            decrypt_message(
                address,
                private_key,
                EncryptedPacket(metadata, body),
                prefix,
            )[1]
            == expected.plaintext
        )
