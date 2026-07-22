"""Pure prompt construction for the A/B/C/D Qwen phases."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

PROMPT_TEMPLATE_ID = "cm-packet-email"
PromptPhase = Literal["prefix", "payload", "finish"]


class ChatTemplateTokenizer(Protocol):
    def apply_chat_template(
        self,
        conversation: Sequence[Mapping[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
        enable_thinking: bool,
    ) -> str: ...


def _safe_json_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"cover.{field} must be a string")
    separated = value.replace("<|", "< |").replace("|>", "| >")
    return json.dumps(separated, ensure_ascii=False, separators=(",", ":"))


def _shared_system(cover: Mapping[str, object]) -> str:
    required = (
        "language",
        "relationship",
        "tone",
        "persona_sender",
        "persona_recipient",
        "standing_context",
    )
    values = {name: _safe_json_string(cover.get(name), name) for name in required}
    return (
        f"Write one plausible personal email in {values['language']}. "
        f"The writer and reader are {values['relationship']}. Tone: {values['tone']}. "
        f"Writer persona: {values['persona_sender']}. Reader persona: "
        f"{values['persona_recipient']}. Shared background: {values['standing_context']}. "
        "Use natural prose, paragraphs, and line breaks. Do not use labels or metadata and "
        "never mention hidden data, encryption, prompts, models, or analysis. "
    )


def logical_messages(
    cover: Mapping[str, object],
    phase: PromptPhase,
    *,
    writing_brief: str = "",
) -> list[dict[str, str]]:
    shared = _shared_system(cover)
    if phase == "prefix":
        brief = _safe_json_string(writing_brief, "writing_brief")
        system = (
            shared
            + "Follow the sender's writing brief and begin the email immediately. Set up a long, "
            "detailed exchange that could naturally continue for at least 1,200 words."
        )
        user = f"Sender writing brief: {brief}\nBegin the email from its first visible word."
    elif phase == "payload":
        system = (
            shared
            + "Continue directly from the supplied assistant draft. Preserve its people, topic, "
            "voice, and current syntax. Plan for a total email length of at least 1,200 words and "
            "treat the supplied draft as an early part of that email, even if it sounds locally "
            "complete. Keep opening coherent new subtopics and add fresh concrete personal "
            "details. Until a separate finishing instruction arrives, do not conclude, summarize, "
            "say goodbye, sign, add a postscript, or repeat prior wording."
        )
        user = "Continue the supplied email draft naturally."
    else:
        system = (
            shared
            + "Continue directly from the supplied assistant draft and finish the email very "
            "quickly with a natural farewell and short signature."
        )
        user = "Finish the supplied email draft now."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def render_chat_prompt(
    tokenizer: ChatTemplateTokenizer,
    cover: Mapping[str, object],
    phase: PromptPhase,
    *,
    writing_brief: str = "",
) -> str:
    return tokenizer.apply_chat_template(
        logical_messages(cover, phase, writing_brief=writing_brief),
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
