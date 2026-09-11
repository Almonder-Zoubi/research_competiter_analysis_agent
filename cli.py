"""CLI entrypoint: `research-agent run --company "<name>"`.

Runs the loop once against real Tavily + Anthropic calls — this is the one place
in the project where live network calls are expected (see CLAUDE.md: the test
suite itself never calls out).
"""

from __future__ import annotations

import argparse
import sys

import structlog
from anthropic import Anthropic, AnthropicError
from tavily import TavilyClient

from agent.config import get_settings
from agent.loop import run_research
from memory.db import make_engine, make_session_factory
from tools.search import SearchTool

logger = structlog.get_logger()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="research-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Research a company and print a sourced brief."
    )
    run_parser.add_argument(
        "--company", required=True, help="Company or topic to research."
    )

    args = parser.parse_args(argv)

    if args.command == "run":
        return _run_command(args.company)

    parser.print_help()
    return 1


def _run_command(company: str) -> int:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    try:
        state = run_research(
            company,
            settings=settings,
            anthropic_client=Anthropic(api_key=settings.anthropic_api_key),
            search_tool=SearchTool(
                client=TavilyClient(api_key=settings.tavily_api_key)
            ),
            session_factory=session_factory,
        )
    except AnthropicError as e:
        print(f"Anthropic API call failed: {e}", file=sys.stderr)
        print(
            "(check your API key and billing/credits at console.anthropic.com)",
            file=sys.stderr,
        )
        return 1

    print(f"\n=== Brief: {state.topic} ===\n")
    print(state.brief)
    print(
        f"\n(run #{state.run_id} stored in {settings.database_url} — "
        f"{state.sources_used} source(s), {state.steps_used} step(s) used)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
