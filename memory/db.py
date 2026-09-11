"""Engine/session setup for the SQL fact store (SQLite by default, see CLAUDE.md)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, text
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


def _ensure_report_path_column(engine: Engine) -> None:
    """create_all() only creates *missing tables*, never adds *missing columns*
    to a table that already exists. This project has no migration tool
    (Alembic would be overkill for one nullable column) — patch existing
    on-disk databases in place instead of forcing users to delete real run
    data whenever a column gets added. SQLite-specific (PRAGMA); revisit if
    this project ever moves off SQLite.
    """
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(runs)"))}
        if "report_path" not in columns:
            conn.execute(text("ALTER TABLE runs ADD COLUMN report_path VARCHAR"))
            conn.commit()


def make_engine(database_url: str) -> Engine:
    """Create the engine, ensure all tables exist, and patch in any columns
    added to an existing table since the DB file was created."""
    _ensure_sqlite_dir(database_url)
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    _ensure_report_path_column(engine)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)
