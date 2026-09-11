"""Offline test for the in-place report_path column migration in make_engine().

create_all() only creates missing tables, never adds missing columns to a
table that already exists — see memory/db.py::_ensure_report_path_column.
This simulates exactly that situation: an existing sqlite file with the old
`runs` schema (no report_path column, but with a real row in it).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import text

from memory.db import make_engine


def test_make_engine_adds_report_path_column_to_existing_db(tmp_path: Path) -> None:
    db_path = tmp_path / "old.db"
    con = sqlite3.connect(db_path)
    con.execute(
        """
        CREATE TABLE runs (
            id INTEGER NOT NULL,
            topic VARCHAR NOT NULL,
            brief TEXT,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )
    con.execute(
        "INSERT INTO runs (id, topic, brief, created_at) VALUES (1, 'Acme', 'a brief', '2026-01-01 00:00:00')"
    )
    con.commit()
    con.close()

    engine = make_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(runs)"))}
        assert "report_path" in columns

        row = conn.execute(
            text("SELECT topic, brief, report_path FROM runs WHERE id = 1")
        ).one()
        assert row.topic == "Acme"
        assert row.brief == "a brief"
        assert row.report_path is None


def test_make_engine_is_idempotent_on_a_fresh_db(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"

    make_engine(f"sqlite:///{db_path}")
    engine = make_engine(f"sqlite:///{db_path}")  # second call must not error

    with engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(runs)"))}
        assert "report_path" in columns
