from __future__ import annotations

import pytest

from covermail.cover.transport import canonical_carrier
from covermail.errors import CarrierStructureError


def test_canonical_carrier_normalizes_email_line_endings() -> None:
    assert canonical_carrier("premier\r\nsecond\rtroisième\n") == ("premier\nsecond\ntroisième\n")


def test_canonical_carrier_rejects_nul() -> None:
    with pytest.raises(CarrierStructureError):
        canonical_carrier("bad\x00carrier")
