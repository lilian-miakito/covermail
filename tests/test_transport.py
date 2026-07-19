from __future__ import annotations

import pytest

from covermail.cover.transport import canonical_carrier, canonical_subject
from covermail.errors import CarrierStructureError


def test_canonical_carrier_normalizes_email_line_endings() -> None:
    assert canonical_carrier("premier\r\nsecond\rtroisième\n") == ("premier\nsecond\ntroisième\n")


def test_canonical_carrier_rejects_nul() -> None:
    with pytest.raises(CarrierStructureError):
        canonical_carrier("bad\x00carrier")


def test_canonical_subject_normalizes_and_collapses_ascii_space() -> None:
    assert canonical_subject("  Cafe\u0301\t demain  ") == "Café demain"


@pytest.mark.parametrize("subject", ["", " \t ", "hello\nworld", "x\x00y"])
def test_canonical_subject_rejects_invalid_values(subject: str) -> None:
    with pytest.raises(ValueError):
        canonical_subject(subject)


def test_canonical_subject_enforces_utf8_byte_limit() -> None:
    assert canonical_subject("é" * 128) == "é" * 128
    with pytest.raises(ValueError, match="256"):
        canonical_subject("é" * 129)
