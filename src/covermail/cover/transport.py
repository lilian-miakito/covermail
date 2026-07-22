"""Visible email transport canonicalization."""

from __future__ import annotations

from covermail.errors import CarrierStructureError


def canonical_carrier(carrier: str) -> str:
    """Canonicalize email line endings to the tokenizer's LF representation."""
    canonical = carrier.replace("\r\n", "\n").replace("\r", "\n")
    if "\x00" in canonical:
        raise CarrierStructureError("carrier contains NUL")
    return canonical
