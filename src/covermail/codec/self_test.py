"""Address-bound deterministic model compatibility self-test."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Sequence
from dataclasses import dataclass

from covermail.codec.candidates import TokenModel
from covermail.codec.frequencies import table_counts
from covermail.errors import ModelCompatibilityError

SELF_TEST_SUBJECT = "Covermail deterministic compatibility test"
SELF_TEST_PRIMER = "Je voulais te donner quelques nouvelles tranquillement."
SELF_TEST_STEPS = 4


@dataclass(frozen=True, slots=True)
class SelfTestResult:
    sha256: str
    transcript: bytes
    selected_token_ids: tuple[int, ...]


def compute_self_test(
    model: TokenModel,
    rendered_prompt: str,
    path_indices: Sequence[int],
    *,
    initial_prefix: Sequence[int] = (),
) -> SelfTestResult:
    """Compute the exact Section 16 transcript and SHA-256 digest."""
    if len(path_indices) != SELF_TEST_STEPS:
        raise ValueError("self-test requires exactly four steps")
    prompt_digest = hashlib.sha256(rendered_prompt.encode("utf-8", errors="strict")).digest()
    transcript = bytearray()
    prefix = list(initial_prefix)
    selected: list[int] = []
    for state, path_index in enumerate(path_indices):
        table = model.next_table(prefix)
        counts = table_counts(table.cumulative)
        if not 0 <= path_index < len(table.candidates):
            raise ValueError("self-test path index exceeds candidate count")
        transcript.extend(struct.pack(">I", state))
        transcript.extend(prompt_digest if state == 0 else bytes(32))
        transcript.extend(struct.pack(">H", len(table.candidates)))
        for candidate, count in zip(table.candidates, counts, strict=True):
            try:
                transcript.extend(struct.pack(">iH", candidate.token_id, count))
            except struct.error as error:
                raise ValueError("self-test value is outside transcript range") from error
        chosen = table.candidates[path_index].token_id
        prefix.append(chosen)
        selected.append(chosen)
    return SelfTestResult(
        sha256=hashlib.sha256(transcript).hexdigest(),
        transcript=bytes(transcript),
        selected_token_ids=tuple(selected),
    )


def verify_self_test(
    model: TokenModel,
    rendered_prompt: str,
    path_indices: Sequence[int],
    expected_sha256: str,
    *,
    initial_prefix: Sequence[int] = (),
) -> SelfTestResult:
    result = compute_self_test(
        model,
        rendered_prompt,
        path_indices,
        initial_prefix=initial_prefix,
    )
    if result.sha256 != expected_sha256:
        raise ModelCompatibilityError("model compatibility self-test failed")
    return result
