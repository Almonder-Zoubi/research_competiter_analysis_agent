from __future__ import annotations

from agent.schemas import Fact, Source
from agent.state import RunState


def test_new_run_state_starts_empty() -> None:
    state = RunState(topic="Acme Corp")
    assert state.topic == "Acme Corp"
    assert state.plan == []
    assert state.sources == []
    assert state.facts == []
    assert state.brief is None
    assert state.steps_used == 0
    assert state.sources_used == 0


def test_budget_checks() -> None:
    state = RunState(topic="Acme Corp", steps_used=2, sources_used=1)
    assert state.can_take_step(max_steps=3) is True
    assert state.can_take_step(max_steps=2) is False
    assert state.can_fetch_source(max_sources=5) is True
    assert state.can_fetch_source(max_sources=1) is False


def test_accumulates_sources_and_facts() -> None:
    state = RunState(topic="Acme Corp")
    state.sources.append(Source(url="https://example.com", title="Example"))
    state.facts.append(
        Fact(attribute="founded_year", value="2015", source_url="https://example.com")
    )
    assert len(state.sources) == 1
    assert len(state.facts) == 1
    assert state.facts[0].source_url == state.sources[0].url
