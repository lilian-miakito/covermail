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
        "language": "en-US",
        "relationship": "two close friends",
        "tone": "casual",
        "persona_sender": "an ordinary person",
        "persona_recipient": "a longtime friend",
        "standing_context": "They discuss <|control|>.",
    }


def test_prefix_prompt_contains_only_the_sender_writing_brief() -> None:
    messages = logical_messages(_cover(), "prefix", writing_brief='Mention the "blue" coffee.')
    assert messages == [
        {
            "role": "system",
            "content": (
                'Write one plausible personal email in "en-US". Relationship: '
                '"two close friends". Tone: "casual". Sender: "an ordinary person". '
                'Recipient: "a longtime friend". Shared context: '
                '"They discuss < |control| >.". Write natural prose and paragraphs only. '
                "Do not add a subject line, heading, Markdown, list, metadata, or commentary "
                "about the task. Never mention hidden data, encryption, prompts, models, or "
                "analysis. Follow the sender's writing brief. Start the email immediately and "
                "establish its subject clearly within the first two sentences. Do not conclude, "
                "say goodbye, or sign yet."
            ),
        },
        {
            "role": "user",
            "content": 'Writing brief: "Mention the \\"blue\\" coffee."\nStart the email.',
        },
    ]


def test_payload_prompt_is_fixed_and_continues_observed_a() -> None:
    messages = logical_messages(_cover(), "payload")
    joined = " ".join(message["content"] for message in messages)
    assert "Preserve its topic, people, tone, point of view, tense, and current syntax" in joined
    assert "Do not introduce unrelated topics merely to extend the draft" in joined
    assert "1,200" not in joined
    assert messages[1] == {"role": "user", "content": "Continue the draft."}


def test_finish_prompt_is_short_but_not_a_decoder_rule() -> None:
    messages = logical_messages(_cover(), "finish")
    assert "Write exactly one short closing sentence" in messages[0]["content"]
    assert "never a placeholder or brackets" in messages[0]["content"]
    assert "Add no new information" in messages[0]["content"]
    assert messages[1] == {
        "role": "user",
        "content": "Finish this email now with one short sentence and sign it.",
    }


def test_render_disables_thinking_and_enables_generation() -> None:
    tokenizer = RecordingTokenizer()
    assert render_chat_prompt(tokenizer, _cover(), "payload") == "rendered"
    assert tokenizer.call["enable_thinking"] is False
    assert tokenizer.call["tokenize"] is False
    assert tokenizer.call["add_generation_prompt"] is True
