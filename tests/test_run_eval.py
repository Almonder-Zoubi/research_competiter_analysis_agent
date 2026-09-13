"""Offline tests for evals/run_eval.py — a real temp SQLite DB stands in for
the persisted runs, and a fake Anthropic client for the optional --judge
path, so this never touches the network or a real DB (see CLAUDE.md: no live
calls in the test suite).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agent.schemas import Fact, Source
from evals.golden_cases import GoldenCase
from evals.run_eval import EvalResult, render_eval_report, run_evals
from memory.db import make_engine, make_session_factory
from memory.repository import save_brief, save_facts, save_run, save_sources


class _FakeMessages:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)

    def create(self, **kwargs: Any) -> Any:
        text = self._replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class _FakeAnthropicClient:
    def __init__(self, replies: list[str]) -> None:
        self.messages = _FakeMessages(replies)


def _session_factory(tmp_path: Path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    return make_session_factory(engine)


def _seed_run(session_factory, *, topic: str, cited: bool) -> None:
    with session_factory() as session:
        run_id = save_run(session, topic=topic)
        save_sources(session, run_id, [Source(url="https://a.example/page")])
        save_facts(
            session,
            run_id,
            [
                Fact(
                    attribute="founded_year",
                    value="2016",
                    source_url="https://a.example/page",
                )
            ],
        )
        brief = (
            "Acme was founded in 2016. [https://a.example/page]"
            if cited
            else "Acme was founded in 2016, a plain uncited paragraph."
        )
        save_brief(session, run_id, brief)


def test_run_evals_scores_a_seeded_run(tmp_path: Path, monkeypatch) -> None:
    session_factory = _session_factory(tmp_path)
    _seed_run(session_factory, topic="Acme", cited=True)
    monkeypatch.setattr(
        "evals.run_eval.GOLDEN_CASES",
        [GoldenCase(topic="Acme", expected_facts=["2016"])],
    )

    results = run_evals(session_factory=session_factory)

    assert len(results) == 1
    assert results[0].run_id is not None
    assert results[0].citation_coverage == 1.0
    assert results[0].fact_recall == 1.0
    assert results[0].judgment is None  # use_judge defaults to False


def test_run_evals_skips_topic_with_no_matching_run(
    tmp_path: Path, monkeypatch
) -> None:
    session_factory = _session_factory(tmp_path)
    monkeypatch.setattr(
        "evals.run_eval.GOLDEN_CASES", [GoldenCase(topic="Nonexistent Co")]
    )

    results = run_evals(session_factory=session_factory)

    assert len(results) == 1
    assert results[0].run_id is None
    assert results[0].citation_coverage is None


def test_run_evals_picks_the_latest_run_when_topic_researched_twice(
    tmp_path: Path, monkeypatch
) -> None:
    session_factory = _session_factory(tmp_path)
    _seed_run(session_factory, topic="Acme", cited=False)  # older, uncited
    _seed_run(session_factory, topic="Acme", cited=True)  # newer, cited
    monkeypatch.setattr("evals.run_eval.GOLDEN_CASES", [GoldenCase(topic="Acme")])

    results = run_evals(session_factory=session_factory)

    assert results[0].citation_coverage == 1.0  # picked the newer, cited run


def test_run_evals_with_judge_calls_the_model(tmp_path: Path, monkeypatch) -> None:
    session_factory = _session_factory(tmp_path)
    _seed_run(session_factory, topic="Acme", cited=True)
    monkeypatch.setattr("evals.run_eval.GOLDEN_CASES", [GoldenCase(topic="Acme")])
    reply = json.dumps(
        {"clarity_score": 5, "groundedness_score": 5, "reasoning": "Clear and cited."}
    )
    client = _FakeAnthropicClient([reply])

    results = run_evals(
        session_factory=session_factory,
        anthropic_client=client,  # type: ignore[arg-type]
        judge_model="fake-model",
        use_judge=True,
    )

    assert results[0].judgment is not None
    assert results[0].judgment.clarity_score == 5


def test_render_eval_report_includes_averages_and_skips() -> None:
    scored = EvalResult(
        case=GoldenCase(topic="Acme", expected_facts=["2016"]),
        run_id=1,
        citation_coverage=1.0,
        fact_recall=1.0,
        judgment=None,
    )
    skipped = EvalResult(
        case=GoldenCase(topic="Nonexistent Co"),
        run_id=None,
        citation_coverage=None,
        fact_recall=None,
        judgment=None,
    )

    report = render_eval_report([scored, skipped])

    assert "Acme (run #1)" in report
    assert "citation_coverage=100%" in report
    assert "fact_recall=100%" in report
    assert "Nonexistent Co: SKIPPED" in report
    assert "Average citation coverage: 100%" in report
