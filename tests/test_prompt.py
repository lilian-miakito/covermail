from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from covermail.cover.prompt import LLAMA_3_PINNED_DATE, logical_messages, render_chat_prompt


class RecordingTokenizer:
    def __init__(self) -> None:
        self.call: dict[str, Any] = {}

    def apply_chat_template(
        self,
        conversation: Sequence[Mapping[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
        date_string: str,
    ) -> str:
        self.call = {
            "conversation": conversation,
            "tokenize": tokenize,
            "add_generation_prompt": add_generation_prompt,
            "date_string": date_string,
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
        "max_sentences": 4,
        "max_questions": 1,
    }


def test_logical_messages_use_json_literals_and_separate_control_tokens() -> None:
    messages = logical_messages(_cover(), '  Café "bleu"  ')
    assert messages[0]["role"] == "system"
    assert 'in "fr-FR"' in messages[0]["content"]
    assert "< |contrôle| >" in messages[0]["content"]
    assert messages[1] == {
        "role": "user",
        "content": 'Visible email subject: "Café \\"bleu\\""\nWrite the body now.',
    }


def test_render_chat_prompt_pins_date_and_generation_mode() -> None:
    tokenizer = RecordingTokenizer()
    assert render_chat_prompt(tokenizer, _cover(), "Sujet") == "rendered"
    assert tokenizer.call["date_string"] == LLAMA_3_PINNED_DATE
    assert tokenizer.call["tokenize"] is False
    assert tokenizer.call["add_generation_prompt"] is True
