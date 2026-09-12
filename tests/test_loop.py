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
from agent.loop import run_deep_research, run_research
from agent.planner import make_search_queries
from memory.db import make_engine, make_session_factory
from memory.repository import load_run
from tools.extract import ExtractTool
from tools.fetch import FetchTool
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
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        text = self._replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class _FakeAnthropicClient:
    def __init__(self, replies: list[str]) -> None:
        self.messages = _FakeMessages(replies)


class _FakeFetchHttpClient:
    """Stands in for FetchTool's httpx client: allows every robots.txt check and
    returns the same canned, extractable page for any URL — good enough for
    loop-level wiring tests. tests/test_fetch.py covers FetchTool's own edge
    cases (robots disallow, timeouts, 404s, ...) in detail.
    """

    def __init__(self, page_text: str | None = None) -> None:
        text = page_text or (
            "This is a much longer fetched paragraph describing the company in "
            "far more detail than the short snippet the search tool returned. "
        )
        self._page_html = f"<html><body><article><p>{text}</p></article></body></html>"

    def get(self, url: str, **kwargs: Any) -> Any:
        if url.endswith("/robots.txt"):
            return SimpleNamespace(status_code=200, text="User-agent: *\nAllow: /\n")
        return SimpleNamespace(status_code=200, text=self._page_html)


class _NeverCalledHttpClient:
    """Fails the test loudly if FetchTool ever calls .get() — used to prove the
    backfill step was correctly skipped for content that's already long enough.
    """

    def get(self, url: str, **kwargs: Any) -> Any:
        raise AssertionError(f"fetch should not have been called for {url}")


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


def _planner_reply(*queries: str) -> str:
    """The loop now asks the model to plan queries too (agent/planner.py), so
    every fake Anthropic client here needs one reply for that call before the
    brief-synthesis reply."""
    return json.dumps({"queries": list(queries)})


def _extract_reply(*facts: tuple[str, str]) -> str:
    """The loop now runs fact extraction per source too (tools/extract.py) — one
    reply per source is needed between the planner reply and the brief reply."""
    return json.dumps({"facts": [{"attribute": a, "value": v} for a, v in facts]})


def _deep_planner_reply(subject_type: str, *queries: str) -> str:
    return json.dumps({"subject_type": subject_type, "queries": list(queries)})


def _deep_report_reply(topic: str, *headings: str) -> str:
    return json.dumps(
        {
            "topic": topic,
            "subject_type": "company",
            "sections": [
                {"heading": h, "content": f"{h} content.", "source_urls": []}
                for h in headings
            ],
        }
    )


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
    anthropic_client = _FakeAnthropicClient(
        [
            _planner_reply("Acme company overview", "Acme funding", "Acme founders"),
            _extract_reply(("product", "widgets")),  # for the "about" source
            _extract_reply(("funding_total", "$10M")),  # for the "funding" source
            reply,
        ]
    )

    state = run_research(
        "Acme",
        settings=_settings(),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        fetch_tool=FetchTool(client=_FakeFetchHttpClient()),
        extract_tool=ExtractTool(client=anthropic_client, model="fake-model"),  # type: ignore[arg-type]
        session_factory=session_factory,
    )

    assert state.run_id is not None
    assert state.brief == "Acme makes widgets and raised $10M."
    assert state.sources_used == 2
    # 3 search steps + (1 backfill fetch + 1 extract) per thin source x2:
    assert state.steps_used == 7
    assert len(state.facts) == 2
    assert {f.attribute for f in state.facts} == {"product", "funding_total"}

    with session_factory() as session:
        record = load_run(session, state.run_id)
    assert record is not None
    assert record.brief == state.brief
    assert len(record.sources) == 2
    assert len(record.facts) == 2


def test_run_research_stops_at_max_steps(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    search_tool = SearchTool(client=_FakeTavilyClient({}))
    reply = json.dumps({"topic": "Acme", "summary": "No sources were found."})
    anthropic_client = _FakeAnthropicClient(
        [_planner_reply("Acme company overview"), reply]
    )

    state = run_research(
        "Acme",
        settings=_settings(max_steps=1),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        fetch_tool=FetchTool(client=_NeverCalledHttpClient()),
        extract_tool=ExtractTool(client=anthropic_client, model="fake-model"),  # type: ignore[arg-type]
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
    anthropic_client = _FakeAnthropicClient(
        [_planner_reply("Acme company overview"), bad_reply, good_reply]
    )

    state = run_research(
        "Acme",
        settings=_settings(max_steps=1),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        fetch_tool=FetchTool(client=_NeverCalledHttpClient()),
        extract_tool=ExtractTool(client=anthropic_client, model="fake-model"),  # type: ignore[arg-type]
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
    anthropic_client = _FakeAnthropicClient(
        [_planner_reply("Acme company overview"), "not json", "still not json"]
    )

    state = run_research(
        "Acme",
        settings=_settings(max_steps=1),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        fetch_tool=FetchTool(client=_NeverCalledHttpClient()),
        extract_tool=ExtractTool(client=anthropic_client, model="fake-model"),  # type: ignore[arg-type]
        session_factory=session_factory,
    )

    assert state.brief is not None
    assert "could not synthesize" in state.brief.lower()


def test_run_research_falls_back_to_template_plan_if_planner_fails(
    tmp_path: Path,
) -> None:
    session_factory = _session_factory(tmp_path)
    search_tool = SearchTool(
        client=_FakeTavilyClient(
            {
                "Acme overview": [
                    {
                        "url": "https://acme.example/about",
                        "title": "About Acme",
                        "content": "Acme makes widgets.",
                    }
                ]
            }
        )
    )
    brief_reply = json.dumps({"topic": "Acme", "summary": "Acme makes widgets."})
    # Both planner attempts return invalid JSON; the loop must still complete
    # using the deterministic fallback template, not crash.
    anthropic_client = _FakeAnthropicClient(
        ["not json", "still not json", _extract_reply(), brief_reply]
    )

    state = run_research(
        "Acme",
        settings=_settings(),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        fetch_tool=FetchTool(client=_FakeFetchHttpClient()),
        extract_tool=ExtractTool(client=anthropic_client, model="fake-model"),  # type: ignore[arg-type]
        session_factory=session_factory,
    )

    assert state.plan == make_search_queries("Acme")
    assert state.brief == "Acme makes widgets."


def test_run_research_skips_backfill_when_content_is_already_long_enough(
    tmp_path: Path,
) -> None:
    session_factory = _session_factory(tmp_path)
    long_content = "Acme makes enterprise widgets. " * 10  # well over the threshold
    search_tool = SearchTool(
        client=_FakeTavilyClient(
            {
                "Acme company overview": [
                    {
                        "url": "https://acme.example/about",
                        "title": "About Acme",
                        "content": long_content,
                    }
                ]
            }
        )
    )
    brief_reply = json.dumps({"topic": "Acme", "summary": "Acme makes widgets."})
    anthropic_client = _FakeAnthropicClient(
        [
            _planner_reply("Acme company overview"),
            _extract_reply(("product", "widgets")),
            brief_reply,
        ]
    )
    never_called_fetch = _NeverCalledHttpClient()

    state = run_research(
        "Acme",
        settings=_settings(),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        fetch_tool=FetchTool(client=never_called_fetch),
        extract_tool=ExtractTool(client=anthropic_client, model="fake-model"),  # type: ignore[arg-type]
        session_factory=session_factory,
    )

    # No AssertionError from _NeverCalledHttpClient means backfill never ran;
    # extraction still happened directly against the already-long content.
    assert state.sources[0].content == long_content
    assert len(state.facts) == 1


def test_run_research_circuit_breaker_stops_extraction_after_repeated_failures(
    tmp_path: Path,
) -> None:
    long_content = "Acme has a long history of making enterprise widgets. " * 5
    queries = [f"Acme query {i}" for i in range(4)]
    session_factory = _session_factory(tmp_path)
    search_tool = SearchTool(
        client=_FakeTavilyClient(
            {
                q: [
                    {
                        "url": f"https://acme.example/page-{i}",
                        "title": f"Page {i}",
                        "content": long_content,
                    }
                ]
                for i, q in enumerate(queries)
            }
        )
    )
    brief_reply = json.dumps({"topic": "Acme", "summary": "Acme makes widgets."})
    # Every extraction attempt returns invalid JSON — 2 replies consumed per
    # source (initial + one repair retry, see agent/llm.py) — but the circuit
    # breaker should trip after 3 consecutive failed sources and skip the 4th
    # entirely, so only 3 sources' worth of bad replies are ever needed.
    anthropic_client = _FakeAnthropicClient(
        [_planner_reply(*queries)] + ["not json", "still not json"] * 3 + [brief_reply]
    )

    state = run_research(
        "Acme",
        settings=_settings(),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        fetch_tool=FetchTool(client=_NeverCalledHttpClient()),
        extract_tool=ExtractTool(client=anthropic_client, model="fake-model"),  # type: ignore[arg-type]
        session_factory=session_factory,
    )

    assert state.facts == []
    assert state.brief == "Acme makes widgets."
    # planner(1) + 3 sources x 2 extraction attempts + brief(1) = 8 — the 4th
    # source's extraction was never attempted once the breaker tripped.
    assert len(anthropic_client.messages.calls) == 8


def test_run_deep_research_end_to_end_offline(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    search_tool = SearchTool(
        client=_FakeTavilyClient(
            {
                "Acme overview": [
                    {
                        "url": "https://acme.example/about",
                        "title": "About Acme",
                        "content": "Acme makes widgets.",
                    }
                ],
                "Acme ownership": [
                    {
                        "url": "https://acme.example/ownership",
                        "title": "Ownership",
                        "content": "Acme is privately held.",
                    }
                ],
                "Acme controversies": [],
            }
        )
    )
    anthropic_client = _FakeAnthropicClient(
        [
            _deep_planner_reply(
                "company", "Acme overview", "Acme ownership", "Acme controversies"
            ),
            _deep_report_reply(
                "Acme", "Origin & History", "Controversies & Legal Issues"
            ),
        ]
    )

    state = run_deep_research(
        "Acme",
        settings=_settings(reports_dir=str(tmp_path / "reports")),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        session_factory=session_factory,
    )

    assert state.run_id is not None
    assert state.subject_type == "company"
    assert state.deep_report is not None
    assert len(state.deep_report.sections) == 2
    assert state.sources_used == 2

    assert state.report_path is not None
    report_file = Path(state.report_path)
    assert report_file.exists()
    assert report_file.read_bytes()[:4] == b"%PDF"

    with session_factory() as session:
        record = load_run(session, state.run_id)
    assert record is not None
    assert record.report_path == state.report_path


def test_run_deep_research_stops_at_max_steps(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    search_tool = SearchTool(client=_FakeTavilyClient({}))
    anthropic_client = _FakeAnthropicClient(
        [
            _deep_planner_reply(
                "general", "Acme overview", "Acme history", "Acme people"
            ),
            _deep_report_reply("Acme", "Note"),
        ]
    )

    state = run_deep_research(
        "Acme",
        settings=_settings(max_steps=1, reports_dir=str(tmp_path / "reports")),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        session_factory=session_factory,
    )

    assert state.steps_used == 1
    assert state.sources_used == 0


def test_run_deep_research_falls_back_when_synthesis_fails(tmp_path: Path) -> None:
    session_factory = _session_factory(tmp_path)
    search_tool = SearchTool(
        client=_FakeTavilyClient(
            {
                "Acme overview": [
                    {
                        "url": "https://acme.example/about",
                        "title": "About Acme",
                        "content": "Acme makes widgets.",
                    }
                ]
            }
        )
    )
    anthropic_client = _FakeAnthropicClient(
        [
            _deep_planner_reply(
                "company", "Acme overview", "Acme ownership", "Acme controversies"
            ),
            "not json",
            "still not json",
        ]
    )

    state = run_deep_research(
        "Acme",
        settings=_settings(reports_dir=str(tmp_path / "reports")),
        anthropic_client=anthropic_client,  # type: ignore[arg-type]
        search_tool=search_tool,
        session_factory=session_factory,
    )

    assert state.deep_report is not None
    assert state.deep_report.sections[0].heading == "Note"
    assert state.report_path is not None
    assert Path(state.report_path).exists()
