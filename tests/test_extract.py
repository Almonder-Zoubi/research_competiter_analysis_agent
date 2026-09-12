"""Offline tests for ExtractTool. A fake Anthropic client stands in, so this
suite never touches the network (see CLAUDE.md: no live calls in the test
suite).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from anthropic import AnthropicError

from agent.schemas import Source
from tools.base import ToolErrorCategory
from tools.extract import ExtractInput, ExtractTool

SOURCE = Source(
    url="https://acme.example/about",
    title="About Acme",
    content="Acme Robotics was founded in 2016 in Austin, Texas.",
)


class _FakeMessages:
    def __init__(self, replies: list[str | Exception]) -> None:
        self._replies = list(replies)

    def create(self, **kwargs: Any) -> Any:
        item = self._replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=item)])


class _FakeAnthropicClient:
    def __init__(self, replies: list[str | Exception]) -> None:
        self.messages = _FakeMessages(replies)


def test_parses_valid_fact_list() -> None:
    reply = json.dumps(
        {
            "facts": [
                {"attribute": "founded", "value": "2016"},
                {"attribute": "headquarters", "value": "Austin, Texas"},
            ]
        }
    )
    tool = ExtractTool(client=_FakeAnthropicClient([reply]), model="fake-model")  # type: ignore[arg-type]

    result = tool.run(ExtractInput(source=SOURCE, topic="Acme Robotics"))

    assert result.ok is True
    assert result.value is not None
    assert len(result.value) == 2
    assert result.value[0].attribute == "founded"
    assert result.value[0].value == "2016"
    # source_url is filled in by the tool, never trusted from the model:
    assert all(f.source_url == SOURCE.url for f in result.value)


def test_repairs_invalid_json_once() -> None:
    bad_reply = "here are the facts: ..."
    good_reply = json.dumps({"facts": [{"attribute": "founded", "value": "2016"}]})
    tool = ExtractTool(
        client=_FakeAnthropicClient([bad_reply, good_reply]),  # type: ignore[arg-type]
        model="fake-model",
    )

    result = tool.run(ExtractInput(source=SOURCE, topic="Acme Robotics"))

    assert result.ok is True
    assert result.value is not None
    assert len(result.value) == 1


def test_gives_up_after_failed_repair_maps_to_validation() -> None:
    tool = ExtractTool(
        client=_FakeAnthropicClient(["not json", "still not json"]),  # type: ignore[arg-type]
        model="fake-model",
    )

    result = tool.run(ExtractInput(source=SOURCE, topic="Acme Robotics"))

    assert result.ok is False
    assert result.error_category == ToolErrorCategory.VALIDATION


def test_empty_content_short_circuits_without_calling_model() -> None:
    empty_source = Source(url="https://acme.example/blank", content="   ")
    tool = ExtractTool(client=_FakeAnthropicClient([]), model="fake-model")  # type: ignore[arg-type]

    result = tool.run(ExtractInput(source=empty_source, topic="Acme Robotics"))

    assert result.ok is True
    assert result.value == []


def test_anthropic_error_maps_to_transient() -> None:
    tool = ExtractTool(
        client=_FakeAnthropicClient([AnthropicError("connection reset")]),  # type: ignore[arg-type]
        model="fake-model",
    )

    result = tool.run(ExtractInput(source=SOURCE, topic="Acme Robotics"))

    assert result.ok is False
    assert result.error_category == ToolErrorCategory.TRANSIENT


def test_empty_fact_list_from_model_is_ok() -> None:
    tool = ExtractTool(
        client=_FakeAnthropicClient([json.dumps({"facts": []})]),  # type: ignore[arg-type]
        model="fake-model",
    )

    result = tool.run(ExtractInput(source=SOURCE, topic="Acme Robotics"))

    assert result.ok is True
    assert result.value == []
