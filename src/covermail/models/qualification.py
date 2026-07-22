"""Portable A/B/C/D real-model qualification bundles."""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from covermail.address.canonical import canonical_json, decode_base64url, encode_base64url
from covermail.address.schema import Address, validate_address
from covermail.codec.candidates import CandidateTable, GreedyToken, GreedyTokenModel, TokenModel
from covermail.codec.carrier import encode_carrier
from covermail.codec.generative import decode_carrier_sections
from covermail.errors import CarrierGenerationError, CovermailError, ModelCompatibilityError
from covermail.models.profile import load_profile
from covermail.service import METADATA_CAPSULE_BYTES

QUALIFICATION_FORMAT = "covermail-model-qualification"
QUALIFICATION_VERIFICATION_FORMAT = "covermail-model-qualification-verification"
QUALIFICATION_VERSION = 1
MAX_QUALIFICATION_BUNDLE_BYTES = 1 << 20
MAX_QUALIFICATION_GENERATED_TOKENS = 4096
MAX_QUALIFICATION_TRIALS = 3


@dataclass(frozen=True, slots=True)
class QualificationCase:
    case_id: str
    writing_brief: str
    plaintext: str


QUALIFICATION_CASES = (
    QualificationCase(
        "garden",
        "Écris à un ami proche pour lui donner des nouvelles concrètes du jardin.",
        "On se retrouve jeudi à 18 h.\n",
    ),
    QualificationCase(
        "journey",
        "Commence un mail personnel sur le trajet de cette semaine et le train.",
        "Le train arrivera vendredi en début de soirée.\n",
    ),
    QualificationCase(
        "dinner",
        "Écris naturellement à propos du dîner prévu samedi entre amis.",
        "Pense à apporter le livre dont nous avons parlé.\n",
    ),
)

_WORD = re.compile(r"[^\W\d_]+(?:['\N{RIGHT SINGLE QUOTATION MARK}][^\W\d_]+)*", re.UNICODE)
_SENTENCE = re.compile(r"[^.!?]+[.!?]")
_SIGNOFF = re.compile(
    r"(?:^|[.!?]\s+)(?:amicalement|bien à toi|ton ami|à bientôt|affectueusement)\b",
    re.IGNORECASE,
)


class _QualificationTrialRejected(ModelCompatibilityError):
    pass


class _QualificationModel(TokenModel, GreedyTokenModel, Protocol):
    pass


class _QualificationTokenBudget:
    def __init__(
        self,
        model: _QualificationModel,
        case_id: str,
        progress: Callable[[str], None] | None,
        counter: list[int],
    ) -> None:
        self.model = model
        self.case_id = case_id
        self.progress = progress
        self.counter = counter

    @property
    def calls(self) -> int:
        return self.counter[0]

    def _consume(self) -> None:
        if self.calls >= MAX_QUALIFICATION_GENERATED_TOKENS:
            raise _QualificationTrialRejected("qualification exceeded its local token budget")
        self.counter[0] += 1
        if self.progress is not None and self.calls % 100 == 0:
            self.progress(f"{self.case_id}: {self.calls} model steps generated")

    def tokenize(self, text: str) -> list[int]:
        return self.model.tokenize(text)

    def detokenize(self, token_ids: Sequence[int]) -> str:
        return self.model.detokenize(token_ids)

    def next_table(self, visible_prefix: Sequence[int]) -> CandidateTable:
        self._consume()
        return self.model.next_table(visible_prefix)

    def next_greedy_token(self, visible_prefix: Sequence[int]) -> GreedyToken | None:
        self._consume()
        return self.model.next_greedy_token(visible_prefix)


def quality_signals(carrier: str) -> dict[str, object]:
    words = [word.casefold() for word in _WORD.findall(carrier)]
    sentences = _SENTENCE.findall(carrier)
    trigrams = list(zip(words, words[1:], words[2:], strict=False))
    repeated = sum(count - 1 for count in Counter(trigrams).values() if count > 1)
    sentence_lengths = [len(_WORD.findall(sentence)) for sentence in sentences]
    flags: list[str] = []
    if trigrams and repeated / len(trigrams) >= 0.08:
        flags.append("repeated_trigrams")
    if sentence_lengths and max(sentence_lengths) > 80:
        flags.append("long_sentence")
    if any(
        unicodedata.category(character).startswith("L")
        and "LATIN" not in unicodedata.name(character, "")
        for character in carrier
    ):
        flags.append("unexpected_script")
    return {
        "distinct_word_ratio": len(set(words)) / len(words) if words else 0.0,
        "flags": flags,
        "has_signoff_language": _SIGNOFF.search(carrier) is not None,
        "line_feeds": carrier.count("\n"),
        "longest_sentence_words": max(sentence_lengths, default=0),
        "paragraphs": carrier.count("\n\n") + 1,
        "repeated_trigram_ratio": repeated / len(trigrams) if trigrams else 0.0,
        "sentences": len(sentences),
        "words": len(words),
    }


def _address_digest(address: Address) -> str:
    return hashlib.sha256(canonical_json(address)).hexdigest()


def _self_test(loaded: object) -> dict[str, object]:
    result = cast(Any, loaded).self_test
    return {"selected_token_ids": list(result.selected_token_ids), "sha256": result.sha256}


def _fixed_body_length(length: int) -> Callable[[bytes, tuple[int, ...]], int]:
    def resolve(metadata: bytes, prefix_token_ids: tuple[int, ...]) -> int:
        del metadata, prefix_token_ids
        return length

    return resolve


def generate_qualification_bundle(
    address: Address,
    model_root: Path,
    *,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    validated = validate_address(address)
    codec = cast(dict[str, Any], validated["codec"])
    cover = cast(dict[str, Any], validated["cover"])
    cases: list[dict[str, object]] = []
    observed_self_test: dict[str, object] | None = None
    for case in QUALIFICATION_CASES:
        if progress is not None:
            progress(f"{case.case_id}: preparing model profile")
        loaded = load_profile(validated, model_root, case.writing_brief)
        current_self_test = _self_test(loaded)
        if observed_self_test is not None and current_self_test != observed_self_test:
            raise ModelCompatibilityError("qualification self-test changed between cases")
        observed_self_test = current_self_test
        rejected: list[dict[str, object]] = []
        for trial in range(1, MAX_QUALIFICATION_TRIALS + 1):
            counter = [0]
            prefix = _QualificationTokenBudget(
                cast(_QualificationModel, loaded.prefix_model), case.case_id, progress, counter
            )
            payload = _QualificationTokenBudget(
                cast(_QualificationModel, loaded.payload_model), case.case_id, progress, counter
            )
            finish = _QualificationTokenBudget(
                cast(_QualificationModel, loaded.finish_model), case.case_id, progress, counter
            )
            started = time.perf_counter()
            try:
                result = encode_carrier(
                    case.plaintext,
                    prefix,
                    payload,
                    finish,
                    validated,
                    prefix_tokens=cast(int, codec["prefix_tokens"]),
                    maximum_characters=cast(int, cover["max_visible_characters"]),
                )
                quality = quality_signals(result.text)
            except (CarrierGenerationError, _QualificationTrialRejected) as error:
                rejected.append(
                    {
                        "attempt": trial,
                        "model_steps": counter[0],
                        "reason": str(error),
                    }
                )
                if progress is not None:
                    progress(f"{case.case_id}: trial {trial} rejected: {error}")
                continue
            encoded_seconds = time.perf_counter() - started
            decoded = decode_carrier_sections(
                result.text,
                loaded.payload_model,
                prefix_tokens=cast(int, codec["prefix_tokens"]),
                metadata_bytes=METADATA_CAPSULE_BYTES,
                body_length_resolver=_fixed_body_length(len(result.body)),
                maximum_characters=cast(int, cover["max_visible_characters"]),
            )
            if (
                decoded.prefix_token_ids != result.prefix_token_ids
                or decoded.metadata != result.metadata
                or decoded.body != result.body
            ):
                raise ModelCompatibilityError("qualification packet did not round-trip exactly")
            packet_bytes = len(result.metadata) + len(result.body)
            cases.append(
                {
                    "attempts": trial,
                    "body_base64url": encode_base64url(result.body),
                    "carrier": result.text,
                    "case_id": case.case_id,
                    "metadata_base64url": encode_base64url(result.metadata),
                    "prefix_token_ids": list(result.prefix_token_ids),
                    "metrics": {
                        "carrier": asdict(result.metrics),
                        "characters_all": len(result.text),
                        "encode_seconds": encoded_seconds,
                        "encode_tokens_per_second": len(result.token_ids) / encoded_seconds,
                        "k_all_characters_per_packet_byte": len(result.text) / packet_bytes,
                        "packet_bytes": packet_bytes,
                        "tokens_all": len(result.token_ids),
                        "utf8_bytes_all": len(result.text.encode("utf-8")),
                    },
                    "quality": quality,
                    "rejected_trials": rejected,
                    "writing_brief": case.writing_brief,
                }
            )
            break
        else:
            raise ModelCompatibilityError(
                f"qualification case {case.case_id} exhausted its packet trials"
            )
    assert observed_self_test is not None
    return {
        "address_sha256": _address_digest(validated),
        "cases": cases,
        "format": QUALIFICATION_FORMAT,
        "model_id": cast(dict[str, Any], validated["model"])["model_id"],
        "model_revision": cast(dict[str, Any], validated["model"])["revision"],
        "self_test": observed_self_test,
        "version": QUALIFICATION_VERSION,
    }


def read_qualification_bundle(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_QUALIFICATION_BUNDLE_BYTES:
        raise ModelCompatibilityError("qualification bundle is too large")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ModelCompatibilityError("qualification bundle is not valid JSON") from error
    if not isinstance(value, dict):
        raise ModelCompatibilityError("qualification bundle is not an object")
    return cast(dict[str, Any], value)


def verify_qualification_bundle(
    address: Address,
    model_root: Path,
    bundle: dict[str, Any],
    *,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    validated = validate_address(address)
    expected_header = {
        "format": QUALIFICATION_FORMAT,
        "version": QUALIFICATION_VERSION,
        "address_sha256": _address_digest(validated),
        "model_id": cast(dict[str, Any], validated["model"])["model_id"],
        "model_revision": cast(dict[str, Any], validated["model"])["revision"],
    }
    for field, expected in expected_header.items():
        if bundle.get(field) != expected:
            raise ModelCompatibilityError(f"qualification bundle has wrong {field}")
    raw_cases = bundle.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != len(QUALIFICATION_CASES):
        raise ModelCompatibilityError("qualification bundle has the wrong fixed corpus")
    codec = cast(dict[str, Any], validated["codec"])
    cover = cast(dict[str, Any], validated["cover"])
    verified: list[dict[str, object]] = []
    observed_self_test: dict[str, object] | None = None
    for expected_case, raw_case in zip(QUALIFICATION_CASES, raw_cases, strict=True):
        if not isinstance(raw_case, dict):
            raise ModelCompatibilityError("qualification case is not an object")
        case = cast(dict[str, Any], raw_case)
        if (
            case.get("case_id") != expected_case.case_id
            or case.get("writing_brief") != expected_case.writing_brief
        ):
            raise ModelCompatibilityError("qualification bundle does not use the fixed corpus")
        try:
            metadata = decode_base64url(cast(str, case["metadata_base64url"]))
            body = decode_base64url(cast(str, case["body_base64url"]))
            carrier = cast(str, case["carrier"])
            raw_prefix = case["prefix_token_ids"]
        except Exception as error:
            raise ModelCompatibilityError("qualification case encoding is invalid") from error
        if not isinstance(raw_prefix, list) or not all(
            isinstance(token_id, int) for token_id in raw_prefix
        ):
            raise ModelCompatibilityError("qualification prefix token IDs are invalid")
        loaded = load_profile(validated, model_root)
        current_self_test = _self_test(loaded)
        if observed_self_test is not None and current_self_test != observed_self_test:
            raise ModelCompatibilityError("qualification self-test changed between cases")
        observed_self_test = current_self_test
        started = time.perf_counter()
        try:
            decoded = decode_carrier_sections(
                carrier,
                loaded.payload_model,
                prefix_tokens=cast(int, codec["prefix_tokens"]),
                metadata_bytes=METADATA_CAPSULE_BYTES,
                body_length_resolver=_fixed_body_length(len(body)),
                maximum_characters=cast(int, cover["max_visible_characters"]),
            )
        except CovermailError as error:
            raise ModelCompatibilityError("qualification carrier could not be decoded") from error
        if (
            decoded.prefix_token_ids != tuple(raw_prefix)
            or decoded.metadata != metadata
            or decoded.body != body
        ):
            raise ModelCompatibilityError("qualification packet bytes differ")
        elapsed = time.perf_counter() - started
        if progress is not None:
            progress(f"{expected_case.case_id}: exact B/C recovery confirmed")
        verified.append(
            {
                "case_id": expected_case.case_id,
                "decode_seconds": elapsed,
                "exact_packet_match": True,
                "quality": quality_signals(carrier),
            }
        )
    if bundle.get("self_test") != observed_self_test:
        raise ModelCompatibilityError("qualification bundle has the wrong self-test result")
    return {
        "address_sha256": _address_digest(validated),
        "all_packets_exact": True,
        "cases": verified,
        "format": QUALIFICATION_VERIFICATION_FORMAT,
        "self_test": observed_self_test,
        "source_bundle_sha256": hashlib.sha256(
            json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "version": QUALIFICATION_VERSION,
    }
