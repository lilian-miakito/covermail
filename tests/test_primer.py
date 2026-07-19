from __future__ import annotations

import pytest

from covermail.cover.primer import extract_primer, validate_primer
from covermail.errors import CarrierStructureError


def test_valid_primer_and_carrier_extraction() -> None:
    primer = "Je voulais te raconter calmement ce qui s'est passé."
    assert validate_primer(primer) == primer
    assert extract_primer(primer + " La suite vient ici.") == primer


@pytest.mark.parametrize(
    "primer",
    [
        "",
        " Sans début propre.",
        "Pas de terminaison",
        "Deux phrases. Interdites.",
        "Abréviation M. puis suite.",
        "Contrôle\ninterdit.",
        "Modèle <|control|>.",
    ],
)
def test_invalid_primer_fails(primer: str) -> None:
    with pytest.raises(CarrierStructureError):
        validate_primer(primer)


def test_carrier_cannot_contain_only_primer() -> None:
    with pytest.raises(CarrierStructureError, match="only"):
        extract_primer("Une seule phrase.")
