"""Offline tests for evals/judge.py. A fake Anthropic client stands in, so
this suite never touches the network (see CLAUDE.md: no live calls in the
test suite) — the whole point of the --judge flag being opt-in is that this
module is never called live except when the user explicitly asks for it.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from evals.judge import judge_brief_quality


class _FakeMessages:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)

    def create(self, **kwargs: Any) -> Any:
        text = self._replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class _FakeAnthropicClient:
    def __init__(self, replies: list[str]) -> None:
        self.messages = _FakeMessages(replies)


def _valid_reply() -> str:
    return json.dumps(
        {
            "clarity_score": 4,
            "groundedness_score": 5,
            "reasoning": "Well-cited and specific.",
        }
    )


def test_parses_valid_judgment() -> None:
    client = _FakeAnthropicClient([_valid_reply()])

    judgment = judge_brief_quality(
        client,  # type: ignore[arg-type]
        "fake-model",
        topic="Acme",
        brief_text="Acme was founded in 2016. [https://a.example]",
    )

    assert judgment is not None
    assert judgment.clarity_score == 4
    assert judgment.groundedness_score == 5


def test_repairs_invalid_json_once() -> None:
    client = _FakeAnthropicClient(["not json", _valid_reply()])

    judgment = judge_brief_quality(
        client,  # type: ignore[arg-type]
        "fake-model",
        topic="Acme",
        brief_text="Acme was founded in 2016.",
    )

    assert judgment is not None
    assert judgment.clarity_score == 4


def test_gives_up_after_failed_repair_returns_none() -> None:
    client = _FakeAnthropicClient(["not json", "still not json"])

    judgment = judge_brief_quality(
        client,  # type: ignore[arg-type]
        "fake-model",
        topic="Acme",
        brief_text="Acme was founded in 2016.",
    )

    assert judgment is None


def test_rejects_out_of_range_score() -> None:
    bad_reply = json.dumps(
        {"clarity_score": 9, "groundedness_score": 5, "reasoning": "x"}
    )
    client = _FakeAnthropicClient([bad_reply, _valid_reply()])

    judgment = judge_brief_quality(
        client,  # type: ignore[arg-type]
        "fake-model",
        topic="Acme",
        brief_text="Acme was founded in 2016.",
    )

    # first reply fails Pydantic's ge=1,le=5 validation -> repair retry kicks in
    assert judgment is not None
    assert judgment.clarity_score == 4
