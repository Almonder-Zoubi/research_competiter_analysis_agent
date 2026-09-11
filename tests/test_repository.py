"""Save -> load round-trip against a temporary sqlite file. Offline, $0."""

from __future__ import annotations

from pathlib import Path

from agent.schemas import Fact, Source
from memory.db import make_engine, make_session_factory
from memory.repository import load_run, save_brief, save_facts, save_run, save_sources


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
