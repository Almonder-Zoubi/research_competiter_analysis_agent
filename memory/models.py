"""ORM tables mirroring the Pydantic schemas in agent/schemas.py.

Facts are minimal for now (the walking skeleton only persists sources + a brief) —
full fact extraction lands in Days 4-7 — but the table exists so that work is
additive, not a migration.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RunORM(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    brief: Mapped[str | None] = mapped_column(Text, default=None)
    report_path: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    sources: Mapped[list[SourceORM]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    facts: Mapped[list[FactORM]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class SourceORM(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    run: Mapped[RunORM] = relationship(back_populates="sources")


class FactORM(Base):
    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    attribute: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    run: Mapped[RunORM] = relationship(back_populates="facts")
