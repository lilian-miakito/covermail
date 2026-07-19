from __future__ import annotations

from pathlib import Path

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
