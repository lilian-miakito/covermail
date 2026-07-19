from __future__ import annotations

import copy
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from covermail.address.canonical import canonical_json
from covermail.address.fingerprint import (
    address_digest,
    address_id,
    human_fingerprint,
    machine_address_id,
)
from covermail.address.schema import validate_address
from covermail.errors import AddressValidationError


def test_valid_address_and_fixed_fingerprint(address: dict[str, Any]) -> None:
    validated = validate_address(address)
    assert address_digest(validated).hex() == (
        "3fb5c2670e2dae673cec33d7b0b0e2471d9e8390e8f40e905216523b48f06360"
    )
    assert address_id(validated).hex() == "3fb5c2670e2dae673cec33d7b0b0e247"
    assert machine_address_id(validated) == "P7XCZw4trmc87DPXsLDiRw"
    assert human_fingerprint(validated) == (
        "H624 EZYO FWXG OPHM GPL3 BMHC I4OZ 5A4Q 5D2A 5ECS CZJD WSHQ MNQA"
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("extra",), True),
        (("version",), 2),
        (("recipient", "label"), ""),
        (("recipient", "hpke_public_key"), "AA"),
        (("hpke", "aead"), "CHACHA20_POLY1305"),
        (("model", "model_id"), "../local"),
        (("model", "revision"), "latest"),
        (("model", "artifacts", 0, "path"), "../weights.bin"),
        (("model", "artifacts", 0, "path"), "weights.pt"),
        (("model", "runtime", "trust_remote_code"), True),
        (("codec", "top_n"), 1),
        (("codec", "frequency_total"), 65536),
        (("codec", "self_test", "path_indices"), [0, 1, 2, 0]),
        (("cover", "language"), "not a tag"),
        (("cover", "max_visible_characters"), 5),
    ],
)
def test_schema_mutations_fail(
    address: dict[str, Any], path: tuple[str | int, ...], value: object
) -> None:
    mutated = copy.deepcopy(address)
    cursor: Any = mutated
    for component in path[:-1]:
        cursor = cursor[component]
    cursor[path[-1]] = value
    with pytest.raises(AddressValidationError):
        validate_address(mutated)


def test_duplicate_artifact_paths_fail(address: dict[str, Any]) -> None:
    address["model"]["artifacts"].append(copy.deepcopy(address["model"]["artifacts"][0]))
    with pytest.raises(AddressValidationError, match="duplicate"):
        validate_address(address)


def test_direct_non_string_field_name_is_typed_error(address: dict[str, Any]) -> None:
    address[1] = "invalid"  # type: ignore[index]
    with pytest.raises(AddressValidationError, match="non-string"):
        validate_address(address)


@given(
    st.one_of(
        st.integers(max_value=-(1 << 63) - 1),
        st.integers(min_value=1 << 63),
    )
)
def test_canonical_json_rejects_out_of_range_integers(value: int) -> None:
    with pytest.raises(AddressValidationError):
        canonical_json({"value": value})
