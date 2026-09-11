"""Pydantic models shared across tools, the DB layer, and RunState.

Kept intentionally minimal for Day 1 — verification fields (confidence
reconciliation, conflict flags) get added once the verify/ step exists.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Source(BaseModel):
    """A single fetched web page used as evidence."""

    url: str
    title: str = ""
    content: str = ""
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Fact(BaseModel):
    """One atomic claim extracted from a single source."""

    attribute: str
    value: str
    source_url: str
    confidence: float = 1.0
