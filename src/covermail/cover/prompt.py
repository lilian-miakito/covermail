"""Pure prompt construction for the A/B/C/D carrier phases."""

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
        f"Relationship: {values['relationship']}. Tone: {values['tone']}. "
        f"Sender: {values['persona_sender']}. Recipient: {values['persona_recipient']}. "
        f"Shared context: {values['standing_context']}. "
        "Write natural prose and paragraphs only. Do not add a subject line, heading, "
        "Markdown, list, metadata, or commentary about the task. Never mention hidden data, "
        "encryption, prompts, models, or analysis. "
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
            + "Follow the sender's writing brief. Start the email immediately and establish its "
            "subject clearly within the first two sentences. Do not conclude, say goodbye, or "
            "sign yet."
        )
        user = f"Writing brief: {brief}\nStart the email."
    elif phase == "payload":
        system = (
            shared
            + "Continue directly from the supplied assistant draft. Preserve its topic, people, "
            "tone, point of view, tense, and current syntax. Continue naturally, but do not "
            "conclude, say goodbye, sign, or comment on the task. Do not introduce unrelated "
            "topics merely to extend the draft."
        )
        user = "Continue the draft."
    else:
        system = (
            shared
            + "Finish the supplied assistant draft immediately. Write exactly one short closing "
            "sentence, then a sign-off on its own line and a first name on the following line. "
            "Use a common first name, never a placeholder or brackets. Add no new information. "
            "Output nothing after the signature."
        )
        user = "Finish this email now with one short sentence and sign it."
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
