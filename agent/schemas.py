"""Pydantic models shared across tools, the DB layer, and RunState.

Kept intentionally minimal for Day 1 — verification fields (confidence
reconciliation, conflict flags) get added once the verify/ step exists.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Source(BaseModel):
    """A single fetched web page used as evidence."""

    url: str
    title: str = ""
    content: str = ""
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Fact(BaseModel):
    """One atomic claim extracted from a single source."""

    attribute: str
    value: str
    source_url: str
    confidence: float = 1.0


class RunRecord(BaseModel):
    """A run as read back from the DB — what the dashboard/CLI load() returns."""

    id: int
    topic: str
    brief: str | None
    report_path: str | None = None
    created_at: datetime
    sources: list[Source] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)


class SearchPlan(BaseModel):
    """Validated output of the LLM-driven planner — a handful of targeted queries."""

    queries: list[str] = Field(min_length=1, max_length=5)


class RunSummary(BaseModel):
    """One row for listing runs — counts only, no sources/facts loaded."""

    id: int
    topic: str
    created_at: datetime
    has_brief: bool
    has_report: bool = False
    source_count: int
    fact_count: int


SubjectType = Literal["company", "field", "initiative", "general"]


class DeepResearchPlan(BaseModel):
    """Validated output of the deep-research query planner (agent/deep_research.py).

    Unlike SearchPlan, this also names the subject type — deep-mode synthesis
    needs it a second time (to pick section headings), so we ask the model to
    classify once here and reuse the answer rather than risk an inconsistent
    second classification.
    """

    subject_type: SubjectType
    queries: list[str] = Field(min_length=3, max_length=8)


class ReportSection(BaseModel):
    """One section of a deep-research report: a heading, a few sentences of
    prose, and the source URLs (from among the run's fetched sources) that
    back it."""

    heading: str
    content: str
    source_urls: list[str] = Field(default_factory=list)


class DeepResearchReport(BaseModel):
    """The synthesized deep-research report for one run — validated LLM output.

    subject_type is a plain str here (not the planner's Literal) because the
    no-sources/total-failure fallback in agent/deep_research.py needs to build
    one without depending on the planner call having succeeded.
    """

    topic: str
    subject_type: str
    sections: list[ReportSection] = Field(min_length=1)


class ConflictingValue(BaseModel):
    """One of the differing values seen for an attribute during reconciliation
    (verify/reconcile.py), with the source it came from."""

    value: str
    source_url: str


class Conflict(BaseModel):
    """Sources disagree on this attribute's value — surfaced to the user
    instead of silently picking one (see CLAUDE.md's headline feature:
    verification)."""

    attribute: str
    values: list[ConflictingValue] = Field(min_length=2)


class CitedClaim(BaseModel):
    """One sentence of a brief, grounded in exactly one source — the atomic
    unit the project's headline metric (% of brief claims grounded in a cited
    source) is measured against."""

    claim: str
    source_url: str


class VerifiedBrief(BaseModel):
    """Validated LLM output from agent/cited_brief.py: a brief expressed as
    one cited claim per reconciled fact, instead of one ungrounded paragraph."""

    topic: str
    claims: list[CitedClaim] = Field(min_length=1)
