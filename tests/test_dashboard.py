"""Offline test for the Streamlit dashboard — runs the real dashboard.py via
Streamlit's AppTest harness (streamlit.testing.v1) against a temp SQLite DB
seeded with fake data. No LLM/network calls (see CLAUDE.md: no live calls in
the test suite); $0, same as the dashboard itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent.config import get_settings
from agent.schemas import Fact, Source
from memory.db import make_engine, make_session_factory
from memory.repository import save_brief, save_facts, save_run, save_sources

_DASHBOARD_PATH = Path(__file__).parent.parent / "dashboard.py"


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """get_settings() is @lru_cache'd — clear it so each test's monkeypatched
    DATABASE_URL env var actually takes effect instead of returning whatever
    a previous test (or run) already cached."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _seed_db(db_url: str) -> None:
    engine = make_engine(db_url)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        run_id = save_run(session, topic="Acme")
        save_sources(
            session,
            run_id,
            [
                Source(
                    url="https://acme.example/about",
                    title="About Acme",
                    content="Acme makes widgets.",
                )
            ],
        )
        save_facts(
            session,
            run_id,
            [
                Fact(
                    attribute="founded_year",
                    value="2016",
                    source_url="https://acme.example/about",
                    confidence=0.6,
                )
            ],
        )
        save_brief(
            session,
            run_id,
            "Acme was founded in 2016. [https://acme.example/about]",
        )


def _set_required_env(monkeypatch: pytest.MonkeyPatch, db_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")


def test_dashboard_renders_run_list_and_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    _seed_db(db_url)
    _set_required_env(monkeypatch, db_url)

    at = AppTest.from_file(str(_DASHBOARD_PATH)).run()

    assert not at.exception
    runs_table = at.dataframe[0].value
    assert runs_table["Topic"].tolist() == ["Acme"]
    assert runs_table["Facts"].tolist() == [1]

    markdown_text = " ".join(m.value for m in at.markdown)
    assert "Run #1: Acme" in markdown_text
    assert "Acme was founded in 2016. [https://acme.example/about]" in markdown_text

    facts_table = at.dataframe[2].value
    assert facts_table["Attribute"].tolist() == ["founded_year"]
    assert facts_table["Confidence"].tolist() == [0.6]


def test_dashboard_shows_empty_state_with_no_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_url = f"sqlite:///{tmp_path / 'empty.db'}"
    _set_required_env(monkeypatch, db_url)
    make_engine(db_url)  # creates the (empty) schema, no runs inserted

    at = AppTest.from_file(str(_DASHBOARD_PATH)).run()

    assert not at.exception
    assert any("No runs stored yet" in i.value for i in at.info)


def test_dashboard_surfaces_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    _set_required_env(monkeypatch, db_url)
    engine = make_engine(db_url)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        run_id = save_run(session, topic="Acme")
        save_facts(
            session,
            run_id,
            [
                Fact(
                    attribute="employee_count",
                    value="210",
                    source_url="https://a.example/page",
                ),
                Fact(
                    attribute="employee_count",
                    value="250",
                    source_url="https://b.example/page",
                ),
            ],
        )
        save_brief(session, run_id, "No verifiable facts were found for 'Acme'.")

    at = AppTest.from_file(str(_DASHBOARD_PATH)).run()

    assert not at.exception
    warning_text = " ".join(w.value for w in at.warning)
    assert "employee_count" in warning_text
    assert "210" in warning_text and "250" in warning_text
