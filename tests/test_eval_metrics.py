"""Offline tests for evals/metrics.py — pure functions, no LLM/network/DB
calls at all (see CLAUDE.md: no live calls in the test suite, trivially true
for this module).
"""

from __future__ import annotations

from datetime import UTC, datetime

from agent.schemas import Fact, RunRecord, Source
from evals.metrics import citation_coverage, fact_recall


def _record(
    *,
    brief: str | None,
    sources: list[Source] | None = None,
    facts: list[Fact] | None = None,
) -> RunRecord:
    return RunRecord(
        id=1,
        topic="Acme",
        brief=brief,
        created_at=datetime.now(UTC),
        sources=sources or [],
        facts=facts or [],
    )


def test_citation_coverage_full_marks_when_every_line_cites_a_real_source() -> None:
    record = _record(
        brief=(
            "Acme was founded in 2016. [https://a.example/page]\n"
            "Acme makes widgets. [https://b.example/page]"
        ),
        sources=[
            Source(url="https://a.example/page"),
            Source(url="https://b.example/page"),
        ],
    )

    assert citation_coverage(record) == 1.0


def test_citation_coverage_zero_for_old_uncited_paragraph_format() -> None:
    record = _record(
        brief="Acme is a company that makes widgets and was founded in 2016.",
        sources=[Source(url="https://a.example/page")],
    )

    assert citation_coverage(record) == 0.0


def test_citation_coverage_partial_when_some_lines_uncited() -> None:
    record = _record(
        brief=(
            "Acme was founded in 2016. [https://a.example/page]\n"
            "Acme makes widgets, no citation here."
        ),
        sources=[Source(url="https://a.example/page")],
    )

    assert citation_coverage(record) == 0.5


def test_citation_coverage_rejects_a_citation_to_an_unknown_source() -> None:
    record = _record(
        brief="Acme was founded in 2016. [https://hallucinated.example/x]",
        sources=[Source(url="https://a.example/page")],
    )

    assert citation_coverage(record) == 0.0


def test_citation_coverage_zero_when_no_brief() -> None:
    assert citation_coverage(_record(brief=None)) == 0.0


def test_fact_recall_full_marks_when_all_expected_facts_found() -> None:
    record = _record(
        brief="x",
        facts=[
            Fact(
                attribute="founded_year", value="2016", source_url="https://a.example"
            ),
            Fact(
                attribute="headquarters",
                value="Austin, Texas",
                source_url="https://a.example",
            ),
        ],
    )

    assert fact_recall(record, ["2016", "Austin"]) == 1.0


def test_fact_recall_is_case_insensitive() -> None:
    record = _record(
        brief="x",
        facts=[
            Fact(
                attribute="founders", value="Ivan Zhao", source_url="https://a.example"
            )
        ],
    )

    assert fact_recall(record, ["ivan zhao"]) == 1.0


def test_fact_recall_partial_when_some_facts_missing() -> None:
    record = _record(
        brief="x",
        facts=[
            Fact(attribute="founded_year", value="2016", source_url="https://a.example")
        ],
    )

    assert fact_recall(record, ["2016", "Austin"]) == 0.5


def test_fact_recall_zero_when_no_facts_match() -> None:
    record = _record(brief="x", facts=[])

    assert fact_recall(record, ["2016"]) == 0.0


def test_fact_recall_returns_none_when_no_expected_facts_given() -> None:
    record = _record(brief="x", facts=[])

    assert fact_recall(record, []) is None
