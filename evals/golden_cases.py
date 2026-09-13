"""Golden eval cases — drawn from real runs already in the database, not
invented (see DAYS_9_10_evals_and_polish.md: "never trust unverified claims"
applies to the eval set too). Deliberately spans pre- and post-verification
runs: Stripe/harness engineering predate fact extraction (Days 4-5) and the
cited brief (Days 6-7) entirely, so they're expected to score 0% on citation
coverage — a real before/after data point for the eval writeup, not a case
we're expected to "pass."

`expected_facts` is checked against a run's extracted Fact values
(evals/metrics.py::fact_recall) — left empty for runs that predate fact
extraction, since there's nothing there to recall.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GoldenCase(BaseModel):
    """One eval case: a topic to look up the latest matching run for, plus
    real-world-verifiable facts that should show up in its extracted facts.
    """

    topic: str
    expected_facts: list[str] = Field(default_factory=list)
    note: str = ""


GOLDEN_CASES: list[GoldenCase] = [
    GoldenCase(
        topic="Stripe",
        note="Pre-Days-4-5 run (run #3) — no fact extraction existed yet; "
        "expect 0% citation coverage (old one-paragraph brief format).",
    ),
    GoldenCase(
        topic="harness engineering",
        note="Pre-Days-4-5 run (run #4) — same as Stripe: no facts, old "
        "brief format, expect 0% citation coverage.",
    ),
    GoldenCase(
        topic="Notion",
        expected_facts=["2013", "Ivan Zhao", "San Francisco"],
        note="Days 4-5 proof run (run #7) — real facts extracted, but "
        "predates the cited brief (Days 6-7); expect good fact recall, "
        "0% citation coverage.",
    ),
    GoldenCase(
        topic="Figma",
        expected_facts=["2012", "Dylan Field", "Evan Wallace"],
        note="Days 6-7 proof run (run #9) — post-verification pipeline; "
        "expect good fact recall AND near-100% citation coverage.",
    ),
    GoldenCase(
        topic="Linear",
        expected_facts=["2019", "Karri Saarinen", "San Francisco"],
        note="Day 8 proof run (run #10) — post-verification pipeline; "
        "expect good fact recall AND near-100% citation coverage.",
    ),
]
