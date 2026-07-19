"""Visible email transport canonicalization."""

from __future__ import annotations

import re
import unicodedata


def canonical_subject(subject: str) -> str:
    """Return the exact v1 canonical visible email subject."""
    if any(character in subject for character in ("\x00", "\r", "\n")):
        raise ValueError("invalid subject control character")
    normalized = unicodedata.normalize("NFC", subject)
    normalized = re.sub(r"[\t ]+", " ", normalized).strip(" ")
    if not normalized:
        raise ValueError("subject is empty")
    if len(normalized.encode("utf-8", errors="strict")) > 256:
        raise ValueError("subject exceeds 256 UTF-8 bytes")
    return normalized
