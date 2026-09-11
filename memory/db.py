"""Engine/session setup for the SQL fact store (SQLite by default, see CLAUDE.md)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from memory.models import Base

_SQLITE_FILE_PREFIX = "sqlite:///"


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create the parent directory for a file-based sqlite URL, if needed.

    create_engine() doesn't do this itself, and a fresh clone won't have data/ yet.
    """
    if not database_url.startswith(_SQLITE_FILE_PREFIX):
        return
    path = database_url.removeprefix(_SQLITE_FILE_PREFIX)
    if path in ("", ":memory:"):
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def make_engine(database_url: str) -> Engine:
    """Create the engine and ensure all tables exist."""
    _ensure_sqlite_dir(database_url)
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)
