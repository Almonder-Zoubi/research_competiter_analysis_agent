"""Offline tests for cited-brief synthesis. A fake Anthropic client stands in,
so this suite never touches the network (see CLAUDE.md: no live calls in the
test suite).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from agent.cited_brief import render_brief_text, synthesize_cited_brief
from agent.schemas import CitedClaim, Fact, VerifiedBrief


class _FakeMessages:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)

    def create(self, **kwargs: Any) -> Any:
        text = self._replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class _FakeAnthropicClient:
    def __init__(self, replies: list[str]) -> None:
        self.messages = _FakeMessages(replies)


def _facts() -> list[Fact]:
    return [
        Fact(
            attribute="founded_year",
            value="2016",
            source_url="https://acme.example/about",
            confidence=1.0,
        ),
        Fact(
            attribute="employee_count",
            value="210",
            source_url="https://acme.example/careers",
            confidence=0.6,
        ),
    ]


def _valid_reply() -> str:
    return json.dumps(
        {
            "topic": "Acme",
            "claims": [
                {
                    "claim": "Acme was founded in 2016.",
                    "source_url": "https://acme.example/about",
                },
                {
                    "claim": "Acme has 210 employees.",
                    "source_url": "https://acme.example/careers",
                },
            ],
        }
    )


def test_synthesize_cited_brief_parses_valid_claims() -> None:
    client = _FakeAnthropicClient([_valid_reply()])

    brief = synthesize_cited_brief(
        client,  # type: ignore[arg-type]
        "fake-model",
        topic="Acme",
        facts=_facts(),
    )

    assert brief is not None
    assert brief.topic == "Acme"
    assert len(brief.claims) == 2
    assert brief.claims[0].source_url == "https://acme.example/about"


def test_synthesize_cited_brief_repairs_invalid_json_once() -> None:
    client = _FakeAnthropicClient(["not json", _valid_reply()])

    brief = synthesize_cited_brief(
        client,  # type: ignore[arg-type]
        "fake-model",
        topic="Acme",
        facts=_facts(),
    )

    assert brief is not None
    assert len(brief.claims) == 2


def test_synthesize_cited_brief_gives_up_after_failed_repair() -> None:
    client = _FakeAnthropicClient(["not json", "still not json"])

    brief = synthesize_cited_brief(
        client,  # type: ignore[arg-type]
        "fake-model",
        topic="Acme",
        facts=_facts(),
    )

    assert brief is None


def test_render_brief_text_includes_claim_and_citation() -> None:
    brief = VerifiedBrief(
        topic="Acme",
        claims=[
            CitedClaim(
                claim="Acme was founded in 2016.", source_url="https://a.example"
            ),
            CitedClaim(claim="Acme makes widgets.", source_url="https://b.example"),
        ],
    )

    text = render_brief_text(brief)

    assert "Acme was founded in 2016. [https://a.example]" in text
    assert "Acme makes widgets. [https://b.example]" in text
    assert text.count("\n") == 1
