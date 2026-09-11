"""Save -> load round-trip against a temporary sqlite file. Offline, $0."""

from __future__ import annotations

from pathlib import Path

from agent.schemas import Fact, Source
from memory.db import make_engine, make_session_factory
from memory.repository import (
    list_runs,
    load_run,
    save_brief,
    save_facts,
    save_report_path,
    save_run,
    save_sources,
)


def test_round_trip_persists_sources_facts_and_brief(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    engine = make_engine(f"sqlite:///{db_path}")
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        run_id = save_run(session, topic="Stripe")
        save_sources(
            session,
            run_id,
            [
                Source(
                    url="https://stripe.com/about", title="About Stripe", content="..."
                ),
                Source(
                    url="https://en.wikipedia.org/wiki/Stripe",
                    title="Wikipedia",
                    content="...",
                ),
            ],
        )
        save_facts(
            session,
            run_id,
            [
                Fact(
                    attribute="founded_year",
                    value="2010",
                    source_url="https://stripe.com/about",
                )
            ],
        )
        save_brief(
            session,
            run_id,
            "Stripe is a payments infrastructure company founded in 2010.",
        )

    with session_factory() as session:
        record = load_run(session, run_id)

    assert record is not None
    assert record.id == run_id
    assert record.topic == "Stripe"
    assert (
        record.brief == "Stripe is a payments infrastructure company founded in 2010."
    )
    assert {s.url for s in record.sources} == {
        "https://stripe.com/about",
        "https://en.wikipedia.org/wiki/Stripe",
    }
    assert len(record.facts) == 1
    assert record.facts[0].attribute == "founded_year"
    assert record.facts[0].value == "2010"


def test_load_run_returns_none_for_unknown_id(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        assert load_run(session, run_id=999) is None


def test_list_runs_summarizes_without_loading_full_detail(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        run_with_brief = save_run(session, topic="Stripe")
        save_sources(
            session,
            run_with_brief,
            [Source(url="https://stripe.com/about", title="About Stripe")],
        )
        save_facts(
            session,
            run_with_brief,
            [
                Fact(
                    attribute="founded_year",
                    value="2010",
                    source_url="https://stripe.com/about",
                )
            ],
        )
        save_brief(session, run_with_brief, "Stripe is a payments company.")

        run_without_brief = save_run(session, topic="Anthropic")

    with session_factory() as session:
        summaries = list_runs(session)

    assert [s.id for s in summaries] == [run_with_brief, run_without_brief]

    first, second = summaries
    assert first.topic == "Stripe"
    assert first.has_brief is True
    assert first.source_count == 1
    assert first.fact_count == 1

    assert second.topic == "Anthropic"
    assert second.has_brief is False
    assert second.source_count == 0
    assert second.fact_count == 0


def test_list_runs_empty_db_returns_empty_list(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        assert list_runs(session) == []


def test_save_report_path_persists_and_loads(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        run_id = save_run(session, topic="Acme")
        save_report_path(session, run_id, "reports/run_1_acme.pdf")

    with session_factory() as session:
        record = load_run(session, run_id)

    assert record is not None
    assert record.report_path == "reports/run_1_acme.pdf"


def test_list_runs_reports_has_report_flag(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        with_report = save_run(session, topic="Acme")
        save_report_path(session, with_report, "reports/run_1_acme.pdf")
        without_report = save_run(session, topic="Beta")

    with session_factory() as session:
        summaries = {s.id: s for s in list_runs(session)}

    assert summaries[with_report].has_report is True
    assert summaries[without_report].has_report is False
