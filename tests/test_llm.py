"""Offline tests for the shared repair-retry structured-output helper. A fake
Anthropic client stands in, so this suite never touches the network (see
CLAUDE.md: no live calls in the test suite).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

from agent.llm import call_for_structured_output


class _Echo(BaseModel):
    value: str


class _FakeMessages:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        text = self._replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class _FakeAnthropicClient:
    def __init__(self, replies: list[str]) -> None:
        self.messages = _FakeMessages(replies)


def _call(client: _FakeAnthropicClient) -> _Echo | None:
    return call_for_structured_output(
        client,  # type: ignore[arg-type]
        "fake-model",
        system_prompt="sys",
        user_prompt="user",
        schema=_Echo,
        schema_hint='{"value": "..."}',
        max_tokens=50,
    )


def test_parses_valid_json_on_first_try() -> None:
    client = _FakeAnthropicClient([json.dumps({"value": "ok"})])

    assert _call(client) == _Echo(value="ok")


def test_strips_markdown_code_fence() -> None:
    fenced = "```json\n" + json.dumps({"value": "ok"}) + "\n```"
    client = _FakeAnthropicClient([fenced])

    assert _call(client) == _Echo(value="ok")


def test_repairs_once_on_invalid_json() -> None:
    client = _FakeAnthropicClient(["not json", json.dumps({"value": "fixed"})])

    assert _call(client) == _Echo(value="fixed")


def test_gives_up_after_one_failed_repair() -> None:
    client = _FakeAnthropicClient(["not json", "still not json"])

    assert _call(client) is None


def test_repair_prompt_includes_the_validation_error_and_quote_guidance() -> None:
    """A generic "try again" doesn't help the model fix its own mistake —
    the repair prompt must say what was actually wrong, and warn against the
    most common cause of broken JSON (an unescaped literal quote), since a
    quote-heavy topic (see PROGRESS.md's Wirecard finding) can't be fixed by
    the schema hint alone."""
    client = _FakeAnthropicClient(["not json", json.dumps({"value": "fixed"})])

    _call(client)

    assert len(client.messages.calls) == 2
    repair_prompt = client.messages.calls[1]["messages"][0]["content"]
    assert "error:" in repair_prompt
    assert "double-quote" in repair_prompt or "double quote" in repair_prompt
