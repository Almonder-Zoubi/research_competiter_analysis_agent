"""Pydantic models shared across tools, the DB layer, and RunState.

Kept intentionally minimal for Day 1 — verification fields (confidence
reconciliation, conflict flags) get added once the verify/ step exists.
"""

from __future__ import annotations

from datetime import UTC, datetime

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


class Brief(BaseModel):
    """The synthesized research brief for one run — validated LLM output.

    Kept intentionally small for the Day 2-3 walking skeleton: a single summary
    paragraph, not yet the fully cited, claim-by-claim brief that's the project's
    headline feature (that lands once verify/ exists).
    """

    topic: str
    summary: str


class RunRecord(BaseModel):
    """A run as read back from the DB — what the dashboard/CLI load() returns."""

    id: int
    topic: str
    brief: str | None
    created_at: datetime
    sources: list[Source] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
