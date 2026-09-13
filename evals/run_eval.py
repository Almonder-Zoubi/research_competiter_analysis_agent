"""Orchestrates the golden-case eval suite against real, already-persisted
runs (see DAYS_9_10_evals_and_polish.md's "evaluate retrospectively" design
call — no fresh searches are run, so this is $0 without --judge). Wired into
the CLI as `research-agent eval [--judge]`.
"""

from __future__ import annotations

from dataclasses import dataclass

from anthropic import Anthropic
from sqlalchemy.orm import sessionmaker

from evals.golden_cases import GOLDEN_CASES, GoldenCase
from evals.judge import BriefQualityJudgment, judge_brief_quality
from evals.metrics import citation_coverage, fact_recall
from memory.repository import list_runs, load_run


@dataclass
class EvalResult:
    case: GoldenCase
    run_id: int | None
    citation_coverage: float | None
    fact_recall: float | None
    judgment: BriefQualityJudgment | None


def run_evals(
    *,
    session_factory: sessionmaker,
    anthropic_client: Anthropic | None = None,
    judge_model: str | None = None,
    use_judge: bool = False,
) -> list[EvalResult]:
    """Scores every golden case against the latest matching run already in
    the DB. anthropic_client/judge_model are only required when use_judge is
    True — kept optional so the $0 path never needs an API client at all.
    """
    results = []
    for case in GOLDEN_CASES:
        run_id = _latest_run_id_for_topic(session_factory, case.topic)
        if run_id is None:
            results.append(
                EvalResult(
                    case=case,
                    run_id=None,
                    citation_coverage=None,
                    fact_recall=None,
                    judgment=None,
                )
            )
            continue

        with session_factory() as session:
            record = load_run(session, run_id)
        if record is None:  # pragma: no cover - list_runs just confirmed it exists
            continue

        judgment = None
        if use_judge and record.brief and anthropic_client is not None:
            assert judge_model is not None
            judgment = judge_brief_quality(
                anthropic_client, judge_model, topic=case.topic, brief_text=record.brief
            )

        results.append(
            EvalResult(
                case=case,
                run_id=run_id,
                citation_coverage=citation_coverage(record),
                fact_recall=fact_recall(record, case.expected_facts),
                judgment=judgment,
            )
        )
    return results


def _latest_run_id_for_topic(session_factory: sessionmaker, topic: str) -> int | None:
    with session_factory() as session:
        matches = [
            s
            for s in list_runs(session)
            if s.topic.lower() == topic.lower() and s.has_brief
        ]
    if not matches:
        return None
    return max(matches, key=lambda s: s.id).id


def render_eval_report(results: list[EvalResult]) -> str:
    """Pure: turns eval results into the plain-text report printed by the
    CLI and suitable for pasting into a writeup."""
    lines = []
    scored = [r for r in results if r.run_id is not None]
    skipped = [r for r in results if r.run_id is None]

    for r in scored:
        recall_str = "n/a" if r.fact_recall is None else f"{r.fact_recall:.0%}"
        line = (
            f"- {r.case.topic} (run #{r.run_id}): "
            f"citation_coverage={r.citation_coverage:.0%}, fact_recall={recall_str}"
        )
        if r.judgment is not None:
            line += (
                f", clarity={r.judgment.clarity_score}/5, "
                f"groundedness={r.judgment.groundedness_score}/5"
            )
        lines.append(line)

    for r in skipped:
        lines.append(f"- {r.case.topic}: SKIPPED (no run with a brief found in the DB)")

    if scored:
        avg_coverage = sum(r.citation_coverage or 0.0 for r in scored) / len(scored)
        recall_scored = [r for r in scored if r.fact_recall is not None]
        avg_recall = (
            sum(r.fact_recall or 0.0 for r in recall_scored) / len(recall_scored)
            if recall_scored
            else None
        )
        lines.append("")
        lines.append(
            f"Average citation coverage: {avg_coverage:.0%} ({len(scored)} cases)"
        )
        if avg_recall is not None:
            lines.append(
                f"Average fact recall: {avg_recall:.0%} ({len(recall_scored)} cases)"
            )

    return "\n".join(lines)
