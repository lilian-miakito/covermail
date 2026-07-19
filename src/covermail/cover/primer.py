"""Visible first-sentence primer rules for Covermail."""

from __future__ import annotations

import unicodedata

from covermail.errors import CarrierStructureError

MAX_PRIMER_UTF8_BYTES = 512
TERMINAL_PUNCTUATION = frozenset(".!?")


def validate_primer(primer: str) -> str:
    """Validate an exact, unambiguous, single-sentence visible primer."""
    try:
        raw = primer.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise CarrierStructureError("primer is not valid Unicode") from error
    if not raw or len(raw) > MAX_PRIMER_UTF8_BYTES:
        raise CarrierStructureError("primer byte length is outside 1..512")
    if primer[0].isspace() or primer[-1].isspace():
        raise CarrierStructureError("primer has leading or trailing whitespace")
    if any(character in primer for character in ("\r", "\n", "\t", "\x00")):
        raise CarrierStructureError("primer contains a forbidden control")
    if "<|" in primer or "|>" in primer:
        raise CarrierStructureError("primer contains a model control-token substring")
    if any(unicodedata.category(character) in {"Cc", "Cs", "Co", "Cn"} for character in primer):
        raise CarrierStructureError("primer contains a forbidden Unicode code point")
    terminal_offsets = [
        index for index, character in enumerate(primer) if character in TERMINAL_PUNCTUATION
    ]
    if terminal_offsets != [len(primer) - 1]:
        raise CarrierStructureError("primer must contain exactly one terminal punctuation at end")
    return primer


def extract_primer(carrier: str) -> str:
    """Extract the first terminal-punctuation-delimited sentence from a carrier."""
    for index, character in enumerate(carrier):
        if character in TERMINAL_PUNCTUATION:
            primer = validate_primer(carrier[: index + 1])
            if index + 1 == len(carrier):
                raise CarrierStructureError("carrier contains only its primer")
            return primer
    raise CarrierStructureError("carrier has no primer terminator")
