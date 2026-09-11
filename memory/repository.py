"""Converts between ORM rows and the Pydantic models in agent/schemas.py.

The loop only ever talks to these functions — never to RunORM/SourceORM/FactORM
directly — so the persistence shape can change without touching agent/loop.py.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from agent.schemas import Fact, RunRecord, Source
from memory.models import FactORM, RunORM, SourceORM


def save_run(session: Session, topic: str) -> int:
    """Create a new run row (no brief yet) and return its id."""
    run = RunORM(topic=topic)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run.id


def save_sources(session: Session, run_id: int, sources: list[Source]) -> None:
    for source in sources:
        session.add(
            SourceORM(
                run_id=run_id,
                url=source.url,
                title=source.title,
                content=source.content,
                fetched_at=source.fetched_at,
            )
        )
    session.commit()


def save_facts(session: Session, run_id: int, facts: list[Fact]) -> None:
    for fact in facts:
        session.add(
            FactORM(
                run_id=run_id,
                attribute=fact.attribute,
                value=fact.value,
                source_url=fact.source_url,
                confidence=fact.confidence,
            )
        )
    session.commit()


def save_brief(session: Session, run_id: int, brief: str) -> None:
    run = session.get(RunORM, run_id)
    if run is None:
        raise ValueError(f"no run with id {run_id}")
    run.brief = brief
    session.commit()


def load_run(session: Session, run_id: int) -> RunRecord | None:
    run = session.get(RunORM, run_id)
    if run is None:
        return None
    return RunRecord(
        id=run.id,
        topic=run.topic,
        brief=run.brief,
        created_at=run.created_at,
        sources=[
            Source(url=s.url, title=s.title, content=s.content, fetched_at=s.fetched_at)
            for s in run.sources
        ],
        facts=[
            Fact(
                attribute=f.attribute,
                value=f.value,
                source_url=f.source_url,
                confidence=f.confidence,
            )
            for f in run.facts
        ],
    )
