"""CLI entrypoint: `research-agent run --company "<name>"` or
`research-agent run --subject "<title>"`.

--company and --subject are the same underlying parameter (run_research()/
run_deep_research() already take a subject-agnostic `topic: str` — the
planner itself classifies it as a company, a research field, or an
initiative; see agent/planner.py and the "harness engineering" proof run in
PROGRESS.md). Two flags exist only so the command reads naturally for either
case: a company/organization, or a research subject, field, or scientific/
technical area (e.g. "quantum computing", "IT infrastructure").

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
from agent.loop import run_deep_research, run_research
from agent.schemas import Conflict
from agent.tracing import flush_tracing, init_tracing
from evals.run_eval import render_eval_report, run_evals
from memory.db import make_engine, make_session_factory
from memory.repository import list_runs, load_run
from tools.extract import ExtractTool
from tools.fetch import FetchTool
from tools.search import SearchTool
from verify.reconcile import reconcile_facts

logger = structlog.get_logger()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="research-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help=(
            "Research a company, subject, or research field and print a sourced brief."
        ),
    )
    topic_group = run_parser.add_mutually_exclusive_group(required=True)
    topic_group.add_argument("--company", help="Company or organization to research.")
    topic_group.add_argument(
        "--subject",
        help=(
            "A research subject, field, or scientific/technical area to "
            'research (e.g. "quantum computing", "IT infrastructure", '
            '"harness engineering"). Same as --company under the hood — '
            "whichever flag reads naturally for your topic."
        ),
    )
    run_parser.add_argument(
        "--deep-research",
        action="store_true",
        help=(
            "Run a comprehensive, multi-section report (origin, ownership, "
            "financials, scale, controversies, etc.) and render it to PDF "
            "under reports/. Slower and more expensive (~4-9x) than the "
            "default brief — see PROGRESS.md for the cost breakdown."
        ),
    )

    subparsers.add_parser("list", help="List all past runs stored in the database.")

    show_parser = subparsers.add_parser(
        "show", help="Show one past run in full: brief, sources, facts."
    )
    show_parser.add_argument(
        "--run-id", required=True, type=int, help="Run id, from `research-agent list`."
    )

    eval_parser = subparsers.add_parser(
        "eval",
        help=(
            "Score the golden-case eval suite against runs already in the "
            "database (see DAYS_9_10_evals_and_polish.md). $0 by default."
        ),
    )
    eval_parser.add_argument(
        "--judge",
        action="store_true",
        help=(
            "Also ask Claude (MODEL_SMART) to rate each scored case's brief "
            "for clarity and groundedness — one extra call per case, a few "
            "cents total. Off by default."
        ),
    )

    args = parser.parse_args(argv)

    if args.command == "run":
        topic = args.company or args.subject
        return _run_command(topic, deep_research=args.deep_research)
    if args.command == "list":
        return _list_command()
    if args.command == "show":
        return _show_command(args.run_id)
    if args.command == "eval":
        return _eval_command(use_judge=args.judge)

    parser.print_help()
    return 1


def _run_command(topic: str, *, deep_research: bool) -> int:
    settings = get_settings()
    init_tracing(settings)
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
    search_tool = SearchTool(client=TavilyClient(api_key=settings.tavily_api_key))
    fetch_tool = FetchTool()
    extract_tool = ExtractTool(client=anthropic_client, model=settings.model_fast)

    try:
        if deep_research:
            state = run_deep_research(
                topic,
                settings=settings,
                anthropic_client=anthropic_client,
                search_tool=search_tool,
                session_factory=session_factory,
            )
        else:
            state = run_research(
                topic,
                settings=settings,
                anthropic_client=anthropic_client,
                search_tool=search_tool,
                fetch_tool=fetch_tool,
                extract_tool=extract_tool,
                session_factory=session_factory,
            )
    except AnthropicError as e:
        print(f"Anthropic API call failed: {e}", file=sys.stderr)
        print(
            "(check your API key and billing/credits at console.anthropic.com)",
            file=sys.stderr,
        )
        return 1
    finally:
        flush_tracing()

    if deep_research and state.deep_report is not None:
        print(f"\n=== Deep Research Report: {state.topic} ===\n")
        for section in state.deep_report.sections:
            print(f"--- {section.heading} ---")
            print(section.content)
            print()
        print(f"Full PDF report: {state.report_path}")
    else:
        print(f"\n=== Brief: {state.topic} ===\n")
        print(state.brief)
        _print_conflicts(state.conflicts)

    print(
        f"\n(run #{state.run_id} stored in {settings.database_url} — "
        f"{state.sources_used} source(s), {state.steps_used} step(s) used)"
    )
    return 0


def _list_command() -> int:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        summaries = list_runs(session)

    if not summaries:
        print(
            'No runs stored yet — try `research-agent run --company "<name>"` or '
            '`research-agent run --subject "<title>"`.'
        )
        return 0

    print(
        f"{'ID':<5}{'TOPIC':<30}{'CREATED':<22}{'SOURCES':<9}{'FACTS':<7}{'BRIEF':<7}REPORT"
    )
    for s in summaries:
        created = s.created_at.strftime("%Y-%m-%d %H:%M")
        brief_flag = "yes" if s.has_brief else "no"
        report_flag = "yes" if s.has_report else "no"
        print(
            f"{s.id:<5}{s.topic:<30}{created:<22}{s.source_count:<9}"
            f"{s.fact_count:<7}{brief_flag:<7}{report_flag}"
        )
    return 0


def _show_command(run_id: int) -> int:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        record = load_run(session, run_id)

    if record is None:
        print(f"No run with id {run_id}.", file=sys.stderr)
        return 1

    print(
        f"=== Run #{record.id}: {record.topic} ({record.created_at:%Y-%m-%d %H:%M}) ===\n"
    )
    print("--- Brief ---")
    print(record.brief or "(no brief stored for this run)")

    if record.report_path:
        print(f"\n--- Deep Research Report ---\n{record.report_path}")

    print(f"\n--- Sources ({len(record.sources)}) ---")
    for source in record.sources:
        print(f"- {source.url}")
        if source.title:
            print(f"  {source.title}")

    print(f"\n--- Facts ({len(record.facts)}) ---")
    if not record.facts:
        print("(none extracted for this run)")
    for fact in record.facts:
        print(
            f"- {fact.attribute}: {fact.value} "
            f"(source: {fact.source_url}, confidence: {fact.confidence})"
        )

    # Recomputed on the fly rather than persisted — reconcile_facts is pure
    # and idempotent, so this reproduces the same conflicts the run itself
    # found, without a DB migration to store them separately.
    _, conflicts = reconcile_facts(record.facts)
    _print_conflicts(conflicts)
    return 0


def _print_conflicts(conflicts: list[Conflict]) -> None:
    if not conflicts:
        return
    print(f"\n⚠ {len(conflicts)} conflicting fact(s) found:")
    for conflict in conflicts:
        values = "; ".join(f"{v.value} ({v.source_url})" for v in conflict.values)
        print(f"  - {conflict.attribute}: {values}")


def _eval_command(*, use_judge: bool) -> int:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    anthropic_client = None
    if use_judge:
        init_tracing(settings)
        anthropic_client = Anthropic(api_key=settings.anthropic_api_key)

    try:
        results = run_evals(
            session_factory=session_factory,
            anthropic_client=anthropic_client,
            judge_model=settings.model_smart,
            use_judge=use_judge,
        )
    except AnthropicError as e:
        print(f"Anthropic API call failed: {e}", file=sys.stderr)
        print(
            "(check your API key and billing/credits at console.anthropic.com)",
            file=sys.stderr,
        )
        return 1
    finally:
        if use_judge:
            flush_tracing()

    print(f"=== Eval results ({len(results)} golden cases) ===\n")
    print(render_eval_report(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
