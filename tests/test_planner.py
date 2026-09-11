"""Offline tests for the LLM-driven planner. A fake Anthropic client stands in,
so this suite never touches the network (see CLAUDE.md: no live calls in the
test suite).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from agent.planner import make_search_queries, plan_search_queries


class _FakeMessages:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)

    def create(self, **kwargs: Any) -> Any:
        text = self._replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class _FakeAnthropicClient:
    def __init__(self, replies: list[str]) -> None:
        self.messages = _FakeMessages(replies)


def test_parses_valid_query_plan() -> None:
    reply = json.dumps(
        {
            "queries": [
                "harness engineering overview",
                "harness engineering key companies",
            ]
        }
    )
    client = _FakeAnthropicClient([reply])

    queries = plan_search_queries(
        "harness engineering",
        client=client,  # type: ignore[arg-type]
        model="fake-model",
    )

    assert queries == [
        "harness engineering overview",
        "harness engineering key companies",
    ]


def test_repairs_invalid_json_once() -> None:
    bad_reply = "Sure, here are some queries: ..."
    good_reply = json.dumps({"queries": ["Hochtief GmbH overview"]})
    client = _FakeAnthropicClient([bad_reply, good_reply])

    queries = plan_search_queries(
        "Hochtief GmbH",
        client=client,  # type: ignore[arg-type]
        model="fake-model",
    )

    assert queries == ["Hochtief GmbH overview"]


def test_falls_back_to_template_after_failed_repair() -> None:
    client = _FakeAnthropicClient(["not json", "still not json"])

    queries = plan_search_queries(
        "Acme",
        client=client,  # type: ignore[arg-type]
        model="fake-model",
    )

    assert queries == make_search_queries("Acme")


def test_fallback_template_does_not_assume_a_company() -> None:
    queries = make_search_queries("harness engineering")

    joined = " ".join(queries).lower()
    assert "funding" not in joined
    assert "founders" not in joined
