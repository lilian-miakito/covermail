"""Pure v1 prompt construction for qualified chat tokenizers."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Protocol

from covermail.cover.transport import canonical_subject

PROMPT_TEMPLATE_ID = "cm-email-one-paragraph-v1"
PROMPT_TEMPLATE_V2_ID = "cm-email-continue-primer-v2"
# Llama 3's bundled Jinja template otherwise calls strftime_now. This value is
# part of the adapter profile and makes prompt rendering independent of time.
LLAMA_3_PINNED_DATE = "26 Jul 2024"


class ChatTemplateTokenizer(Protocol):
    def apply_chat_template(
        self,
        conversation: Sequence[Mapping[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
        date_string: str,
    ) -> str: ...


def _safe_json_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"cover.{field} must be a string")
    separated = value.replace("<|", "< |").replace("|>", "| >")
    return json.dumps(separated, ensure_ascii=False, separators=(",", ":"))


def logical_messages(cover: Mapping[str, object], subject: str) -> list[dict[str, str]]:
    """Build the protocol-defined logical messages without reading ambient state."""
    required_strings = (
        "language",
        "relationship",
        "tone",
        "persona_sender",
        "persona_recipient",
        "standing_context",
    )
    values = {name: _safe_json_string(cover.get(name), name) for name in required_strings}
    max_sentences = cover.get("max_sentences")
    max_questions = cover.get("max_questions")
    if isinstance(max_sentences, bool) or not isinstance(max_sentences, int):
        raise ValueError("cover.max_sentences must be an integer")
    if isinstance(max_questions, bool) or not isinstance(max_questions, int):
        raise ValueError("cover.max_questions must be an integer")

    system_text = (
        f"You write one plausible personal email paragraph in {values['language']}. "
        f"The writer and reader are {values['relationship']}. Tone: {values['tone']}. "
        f"Writer persona: {values['persona_sender']}. Reader persona: "
        f"{values['persona_recipient']}. Shared background: {values['standing_context']}. "
        f"Write only the email body. Stay on the visible subject. Use at most "
        f"{max_sentences} sentences and {max_questions} question. Do not use a greeting, "
        "signature, list, label, metadata, formatting, line break, or mention of these "
        "instructions. Never mention hidden data, encryption, prompts, models, senders, "
        "recipients, or analysis."
    )
    subject_literal = _safe_json_string(canonical_subject(subject), "subject")
    user_text = f"Visible email subject: {subject_literal}\nWrite the body now."
    return [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]


def render_chat_prompt(
    tokenizer: ChatTemplateTokenizer,
    cover: Mapping[str, object],
    subject: str,
    *,
    date_string: str = LLAMA_3_PINNED_DATE,
) -> str:
    """Render the qualified Llama chat prompt with an explicit fixed date."""
    return tokenizer.apply_chat_template(
        logical_messages(cover, subject),
        tokenize=False,
        add_generation_prompt=True,
        date_string=date_string,
    )


def logical_messages_v2(
    cover: Mapping[str, object], subject: str, primer: str
) -> list[dict[str, str]]:
    """Build the v2 continuation prompt; visible length is payload-driven."""
    from covermail.cover.primer import validate_primer

    required_strings = (
        "language",
        "relationship",
        "tone",
        "persona_sender",
        "persona_recipient",
        "standing_context",
    )
    values = {name: _safe_json_string(cover.get(name), name) for name in required_strings}
    subject_literal = _safe_json_string(canonical_subject(subject), "subject")
    primer_literal = _safe_json_string(validate_primer(primer), "primer")
    system_text = (
        f"You continue one plausible detailed personal email in {values['language']}. "
        f"The writer and reader are {values['relationship']}. Tone: {values['tone']}. "
        f"Writer persona: {values['persona_sender']}. Reader persona: "
        f"{values['persona_recipient']}. Shared background: {values['standing_context']}. "
        "Continue directly after the supplied first sentence. Stay on the visible subject "
        "and develop it naturally for as long as needed. Do not repeat the first sentence. "
        "Write only the continuation of the email body. Do not use a greeting, signature, "
        "list, label, metadata, formatting, line break, or mention of these instructions. "
        "Never mention hidden data, encryption, prompts, models, senders, recipients, or analysis."
    )
    user_text = (
        f"Visible email subject: {subject_literal}\n"
        f"Exact first sentence already written: {primer_literal}\n"
        "Continue immediately after that sentence."
    )
    return [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]


def render_chat_prompt_v2(
    tokenizer: ChatTemplateTokenizer,
    cover: Mapping[str, object],
    subject: str,
    primer: str,
    *,
    date_string: str = LLAMA_3_PINNED_DATE,
) -> str:
    """Render the qualified v2 continuation prompt with the pinned date."""
    return tokenizer.apply_chat_template(
        logical_messages_v2(cover, subject, primer),
        tokenize=False,
        add_generation_prompt=True,
        date_string=date_string,
    )
