"""Offline test of the full plan -> search -> store -> synthesize -> store loop.

Both the Tavily client and the Anthropic client are faked, so this never touches
the network or spends real money (see CLAUDE.md: no live calls in the test suite).
The one deliberate real run happens manually via the CLI, not in the test suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agent.config import Settings
from agent.loop import run_research
from memory.db import make_engine, make_session_factory
from memory.repository import load_run
from tools.search import SearchTool


class _FakeTavilyClient:
    def __init__(self, results_by_query: dict[str, list[dict[str, Any]]]) -> None:
        self._results_by_query = results_by_query

    def search(
        self, query: str, max_results: int | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        results = self._results_by_query.get(query, [])
        return {"results": results[:max_results] if max_results else results}


class _FakeMessages:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)

    def create(self, **kwargs: Any) -> Any:
        text = self._replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class _FakeAnthropicClient:
    def __init__(self, replies: list[str]) -> None:
        self.messages = _FakeMessages(replies)


def _settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        anthropic_api_key="test-key",
        tavily_api_key="test-key",
        **overrides,
    )


def _session_factory(tmp_path: Path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    return make_session_factory(engine)


def test_run_research_end_to_end_offline(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    search_tool = SearchTool(
        client=_FakeTavilyClient(
            {
                "Acme company overview": [
                    {
                        "url": "https://acme.example/about",
                        "title": "About Acme",
                        "content": "Acme makes widgets.",
                    }
                ],
                "Acme funding": [
                    {
                        "url": "https://acme.example/funding",
                        "title": "Funding",
                        "content": "Acme raised $10M.",
                    }
                ],
                "Acme founders": [],
            }
        )
    )
    reply = json.dumps(
        {"topic": "Acme", "summary": "Acme makes widgets and raised $10M."}
    )
    anthropic_client = _FakeAnthropicClient([reply])

    state = run_research(
        "Acme",
        settings=_settings(),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        session_factory=session_factory,
    )

    assert state.run_id is not None
    assert state.brief == "Acme makes widgets and raised $10M."
    assert state.sources_used == 2
    assert state.steps_used == 3

    with session_factory() as session:
        record = load_run(session, state.run_id)
    assert record is not None
    assert record.brief == state.brief
    assert len(record.sources) == 2


def test_run_research_stops_at_max_steps(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    search_tool = SearchTool(client=_FakeTavilyClient({}))
    reply = json.dumps({"topic": "Acme", "summary": "No sources were found."})
    anthropic_client = _FakeAnthropicClient([reply])

    state = run_research(
        "Acme",
        settings=_settings(max_steps=1),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        session_factory=session_factory,
    )

    assert state.steps_used == 1
    assert state.sources_used == 0


def test_run_research_repairs_invalid_brief_json_once(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    search_tool = SearchTool(
        client=_FakeTavilyClient(
            {
                "Acme company overview": [
                    {
                        "url": "https://acme.example/about",
                        "title": "About Acme",
                        "content": "Acme makes widgets.",
                    }
                ]
            }
        )
    )
    bad_reply = "Sure, here's a summary: Acme makes widgets."
    good_reply = json.dumps({"topic": "Acme", "summary": "Acme makes widgets."})
    anthropic_client = _FakeAnthropicClient([bad_reply, good_reply])

    state = run_research(
        "Acme",
        settings=_settings(max_steps=1),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        session_factory=session_factory,
    )

    assert state.brief == "Acme makes widgets."


def test_run_research_gives_up_after_one_failed_repair(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    search_tool = SearchTool(
        client=_FakeTavilyClient(
            {
                "Acme company overview": [
                    {
                        "url": "https://acme.example/about",
                        "title": "About Acme",
                        "content": "Acme makes widgets.",
                    }
                ]
            }
        )
    )
    anthropic_client = _FakeAnthropicClient(["not json", "still not json"])

    state = run_research(
        "Acme",
        settings=_settings(max_steps=1),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        session_factory=session_factory,
    )

    assert state.brief is not None
    assert "could not synthesize" in state.brief.lower()
