"""Offline tests for deep-research query planning and section synthesis. A
fake Anthropic client stands in, so this suite never touches the network (see
CLAUDE.md: no live calls in the test suite).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from agent.deep_research import (
    make_deep_research_queries,
    plan_deep_research_queries,
    synthesize_deep_report,
)
from agent.schemas import Source


class _FakeMessages:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)

    def create(self, **kwargs: Any) -> Any:
        text = self._replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class _FakeAnthropicClient:
    def __init__(self, replies: list[str]) -> None:
        self.messages = _FakeMessages(replies)


# --- plan_deep_research_queries ---------------------------------------------


def test_parses_valid_deep_plan() -> None:
    reply = json.dumps(
        {
            "subject_type": "company",
            "queries": [
                "Acme overview",
                "Acme ownership",
                "Acme financials",
                "Acme controversies",
            ],
        }
    )
    client = _FakeAnthropicClient([reply])

    plan = plan_deep_research_queries(
        "Acme",
        client=client,  # type: ignore[arg-type]
        model="fake-model",
    )

    assert plan.subject_type == "company"
    assert "Acme controversies" in plan.queries


def test_deep_planner_repairs_invalid_json_once() -> None:
    bad_reply = "Sure, here are some queries: ..."
    good_reply = json.dumps(
        {
            "subject_type": "field",
            "queries": [
                "harness engineering overview",
                "harness engineering key players",
                "harness engineering criticisms",
            ],
        }
    )
    client = _FakeAnthropicClient([bad_reply, good_reply])

    plan = plan_deep_research_queries(
        "harness engineering",
        client=client,  # type: ignore[arg-type]
        model="fake-model",
    )

    assert plan.subject_type == "field"
    assert len(plan.queries) == 3


def test_deep_planner_falls_back_to_template_after_failed_repair() -> None:
    client = _FakeAnthropicClient(["not json", "still not json"])

    plan = plan_deep_research_queries(
        "Acme",
        client=client,  # type: ignore[arg-type]
        model="fake-model",
    )

    assert plan.subject_type == "general"
    assert plan == make_deep_research_queries("Acme")


# --- synthesize_deep_report ---------------------------------------------


def _sources() -> list[Source]:
    return [
        Source(
            url="https://acme.example/about",
            title="About Acme",
            content="Acme makes widgets.",
        ),
        Source(
            url="https://acme.example/legal",
            title="Legal",
            content="No lawsuits on record.",
        ),
    ]


def _valid_report_reply() -> str:
    return json.dumps(
        {
            "topic": "Acme",
            "subject_type": "company",
            "sections": [
                {
                    "heading": "Origin & History",
                    "content": "Acme was founded to make widgets.",
                    "source_urls": ["https://acme.example/about"],
                },
                {
                    "heading": "Controversies & Legal Issues",
                    "content": "No notable controversies were found in the available sources.",
                    "source_urls": ["https://acme.example/legal"],
                },
            ],
        }
    )


def test_synthesize_deep_report_parses_valid_sections() -> None:
    client = _FakeAnthropicClient([_valid_report_reply()])

    report = synthesize_deep_report(
        client,  # type: ignore[arg-type]
        "fake-model",
        topic="Acme",
        subject_type="company",
        sources=_sources(),
    )

    assert report.topic == "Acme"
    assert len(report.sections) == 2
    assert report.sections[0].heading == "Origin & History"


def test_synthesize_deep_report_repairs_invalid_json_once() -> None:
    client = _FakeAnthropicClient(["not json", _valid_report_reply()])

    report = synthesize_deep_report(
        client,  # type: ignore[arg-type]
        "fake-model",
        topic="Acme",
        subject_type="company",
        sources=_sources(),
    )

    assert len(report.sections) == 2


def test_synthesize_deep_report_gives_up_after_failed_repair_returns_fallback() -> None:
    client = _FakeAnthropicClient(["not json", "still not json"])

    report = synthesize_deep_report(
        client,  # type: ignore[arg-type]
        "fake-model",
        topic="Acme",
        subject_type="company",
        sources=_sources(),
    )

    assert len(report.sections) == 1
    assert report.sections[0].heading == "Note"
    assert "could not synthesize" in report.sections[0].content.lower()


def test_synthesize_deep_report_no_sources_returns_fallback_without_calling_model() -> (
    None
):
    client = _FakeAnthropicClient(
        []
    )  # no replies queued — a call would raise IndexError

    report = synthesize_deep_report(
        client,  # type: ignore[arg-type]
        "fake-model",
        topic="Acme",
        subject_type="company",
        sources=[],
    )

    assert len(report.sections) == 1
    assert "no sources were found" in report.sections[0].content.lower()


def test_synthesize_deep_report_drops_hallucinated_source_urls() -> None:
    reply = json.dumps(
        {
            "topic": "Acme",
            "subject_type": "company",
            "sections": [
                {
                    "heading": "Origin & History",
                    "content": "Acme was founded to make widgets.",
                    "source_urls": [
                        "https://acme.example/about",
                        "https://not-a-real-source.example/made-up",
                    ],
                }
            ],
        }
    )
    client = _FakeAnthropicClient([reply])

    report = synthesize_deep_report(
        client,  # type: ignore[arg-type]
        "fake-model",
        topic="Acme",
        subject_type="company",
        sources=_sources(),
    )

    assert report.sections[0].source_urls == ["https://acme.example/about"]
