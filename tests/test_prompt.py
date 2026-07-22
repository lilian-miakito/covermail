from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from covermail.cover.prompt import logical_messages, render_chat_prompt


class RecordingTokenizer:
    def __init__(self) -> None:
        self.call: dict[str, Any] = {}

    def apply_chat_template(
        self,
        conversation: Sequence[Mapping[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
        enable_thinking: bool,
    ) -> str:
        self.call = {
            "conversation": conversation,
            "tokenize": tokenize,
            "add_generation_prompt": add_generation_prompt,
            "enable_thinking": enable_thinking,
        }
        return "rendered"


def _cover() -> dict[str, object]:
    return {
        "language": "fr-FR",
        "relationship": "deux amis proches",
        "tone": "familier",
        "persona_sender": "une personne ordinaire",
        "persona_recipient": "un ami",
        "standing_context": "Ils parlent de <|contrôle|>.",
    }


def test_prefix_prompt_contains_only_the_sender_writing_brief() -> None:
    messages = logical_messages(_cover(), "prefix", writing_brief='Parle du café "bleu".')
    assert messages[0]["role"] == "system"
    assert "begin the email immediately" in messages[0]["content"]
    assert "at least 1,200 words" in messages[0]["content"]
    assert 'Parle du café \\"bleu\\".' in messages[1]["content"]
    assert "subject" not in " ".join(message["content"].lower() for message in messages)


def test_payload_prompt_is_fixed_and_continues_observed_a() -> None:
    messages = logical_messages(_cover(), "payload")
    assert "supplied assistant draft" in messages[0]["content"]
    assert "Preserve its people, topic" in messages[0]["content"]
    assert "at least 1,200 words" in messages[0]["content"]
    assert "do not conclude" in messages[0]["content"]
    assert "separate finishing instruction" in messages[0]["content"]


def test_finish_prompt_is_short_but_not_a_decoder_rule() -> None:
    messages = logical_messages(_cover(), "finish")
    assert "finish the email very quickly" in messages[0]["content"]
    assert "Finish the supplied email draft now" in messages[1]["content"]


def test_render_disables_thinking_and_enables_generation() -> None:
    tokenizer = RecordingTokenizer()
    assert render_chat_prompt(tokenizer, _cover(), "payload") == "rendered"
    assert tokenizer.call["enable_thinking"] is False
    assert tokenizer.call["tokenize"] is False
    assert tokenizer.call["add_generation_prompt"] is True
