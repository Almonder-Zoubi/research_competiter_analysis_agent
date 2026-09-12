"""The research loop:

    plan -> search -> [fetch full page if content is thin] -> extract facts
    -> store sources + facts -> synthesize one brief -> store -> return

Budget guards from RunState are checked at every step so a run can't run away
(see CLAUDE.md). A circuit breaker (RunState.record_tool_failure) stops a run
from pursuing further sources after too many consecutive tool failures — see
DAYS_4_5_harden_tools.md. Cross-checking facts across sources, and the fully-
cited brief that's the project's headline feature, are Days 6-7 — the brief
synthesized here is still one prose paragraph, deliberately crude.

run_deep_research() is the opt-in, more expensive sibling (see --deep-research
in cli.py): more targeted search queries and a structured multi-section report
rendered to PDF, instead of one prose paragraph. It shares the same
budget-guarded search execution as run_research() via _execute_search_plan().
"""

from __future__ import annotations

from pathlib import Path

import structlog
from anthropic import Anthropic
from sqlalchemy.orm import sessionmaker

from agent.config import Settings
from agent.deep_research import plan_deep_research_queries, synthesize_deep_report
from agent.llm import call_for_structured_output
from agent.planner import plan_search_queries
from agent.report import render_report_pdf, report_path_for
from agent.schemas import Brief
from agent.state import RunState
from memory.repository import (
    save_brief,
    save_facts,
    save_report_path,
    save_run,
    save_sources,
)
from tools.extract import ExtractInput, ExtractTool
from tools.fetch import FetchInput, FetchTool
from tools.search import SearchInput, SearchTool

logger = structlog.get_logger()

# Tavily's `content` field is sometimes truncated or empty; a source this thin
# is worth backfilling with a direct fetch before extraction.
_THIN_CONTENT_CHARS = 200

BRIEF_SYSTEM_PROMPT = """\
You are a research analyst. You are given raw text pulled from a few web pages \
about a company. Write a short, factual brief grounded only in that text — do not \
add outside knowledge.

Respond with ONLY valid JSON matching this schema, no other text:
{"topic": "<company name>", "summary": "<3-6 sentence summary>"}"""

_SOURCE_CHARS_PER_ITEM = 2000
_BRIEF_SCHEMA_HINT = '{"topic": "...", "summary": "..."}'


def run_research(
    topic: str,
    *,
    settings: Settings,
    anthropic_client: Anthropic,
    search_tool: SearchTool,
    fetch_tool: FetchTool,
    extract_tool: ExtractTool,
    session_factory: sessionmaker,
) -> RunState:
    state = RunState(topic=topic)

    with session_factory() as session:
        state.run_id = save_run(session, topic=topic)

    state.plan = plan_search_queries(
        topic, client=anthropic_client, model=settings.model_fast
    )
    _execute_search_plan(state, settings, search_tool)

    if state.sources:
        with session_factory() as session:
            save_sources(session, state.run_id, state.sources)

    _backfill_and_extract(state, settings, fetch_tool, extract_tool)

    if state.facts:
        with session_factory() as session:
            save_facts(session, state.run_id, state.facts)

    state.brief = _synthesize_brief(anthropic_client, settings.model_smart, state)

    with session_factory() as session:
        save_brief(session, state.run_id, state.brief)

    return state


def run_deep_research(
    topic: str,
    *,
    settings: Settings,
    anthropic_client: Anthropic,
    search_tool: SearchTool,
    session_factory: sessionmaker,
) -> RunState:
    """Opt-in, more expensive sibling of run_research(): 5-6 targeted search
    queries instead of 2-3 generic ones, and a structured multi-section report
    (agent/deep_research.py) rendered to PDF (agent/report.py) instead of one
    prose paragraph. See DAYS_4_5_harden_tools.md and PROGRESS.md for the cost
    delta versus the default run.
    """
    state = RunState(topic=topic)

    with session_factory() as session:
        state.run_id = save_run(session, topic=topic)

    plan = plan_deep_research_queries(
        topic, client=anthropic_client, model=settings.model_fast
    )
    state.plan = plan.queries
    state.subject_type = plan.subject_type
    _execute_search_plan(state, settings, search_tool)

    if state.sources:
        with session_factory() as session:
            save_sources(session, state.run_id, state.sources)

    state.deep_report = synthesize_deep_report(
        anthropic_client,
        settings.model_smart,
        topic=topic,
        subject_type=plan.subject_type,
        sources=state.sources,
    )

    output_path = report_path_for(
        state.run_id, topic, reports_dir=Path(settings.reports_dir)
    )
    rendered_path = render_report_pdf(
        state.deep_report, state.sources, output_path=output_path
    )
    state.report_path = str(rendered_path)

    with session_factory() as session:
        save_report_path(session, state.run_id, state.report_path)

    return state


def _execute_search_plan(
    state: RunState, settings: Settings, search_tool: SearchTool
) -> None:
    """Runs state.plan's queries under budget guards, accumulating sources.
    Shared by run_research and run_deep_research so the guard logic
    (max_steps, max_sources) can't drift between the two paths.
    """
    for query in state.plan:
        if not state.can_take_step(settings.max_steps):
            logger.warning("budget.max_steps_reached", topic=state.topic, query=query)
            break
        if not state.can_fetch_source(settings.max_sources):
            logger.warning("budget.max_sources_reached", topic=state.topic, query=query)
            break
        state.steps_used += 1

        remaining_sources = settings.max_sources - state.sources_used
        result = search_tool.run(
            SearchInput(query=query, max_results=min(3, remaining_sources))
        )
        if not result.ok:
            logger.warning(
                "search.failed",
                query=query,
                category=result.error_category,
                error=result.error_message,
            )
            if state.record_tool_failure():
                logger.warning(
                    "circuit_breaker.tripped", topic=state.topic, stage="search"
                )
                break
            continue
        state.record_tool_success()

        found = result.value or []
        state.sources.extend(found)
        state.sources_used += len(found)


def _backfill_and_extract(
    state: RunState,
    settings: Settings,
    fetch_tool: FetchTool,
    extract_tool: ExtractTool,
) -> None:
    """For each source: backfill thin content with a direct fetch (budget- and
    circuit-breaker-guarded), then extract Facts from whatever content ends up
    available. A tripped circuit breaker stops the whole pass — the run falls
    through to synthesis with whatever facts/sources were gathered so far,
    same "always have something to persist" guarantee as brief synthesis.
    """
    for source in state.sources:
        if (
            len(source.content) < _THIN_CONTENT_CHARS
            and state.can_take_step(settings.max_steps)
            and state.can_fetch_source(settings.max_sources)
        ):
            state.steps_used += 1
            fetch_result = fetch_tool.run(FetchInput(url=source.url))
            if fetch_result.ok and fetch_result.value is not None:
                source.content = fetch_result.value.content or source.content
                source.title = source.title or fetch_result.value.title
                state.record_tool_success()
            else:
                logger.warning(
                    "fetch.failed",
                    url=source.url,
                    category=fetch_result.error_category,
                    error=fetch_result.error_message,
                )
                if state.record_tool_failure():
                    logger.warning(
                        "circuit_breaker.tripped", topic=state.topic, stage="fetch"
                    )
                    return

        if not state.can_take_step(settings.max_steps):
            logger.warning(
                "budget.max_steps_reached", topic=state.topic, stage="extract"
            )
            return
        state.steps_used += 1

        extract_result = extract_tool.run(
            ExtractInput(source=source, topic=state.topic)
        )
        if extract_result.ok and extract_result.value is not None:
            state.facts.extend(extract_result.value)
            state.record_tool_success()
        else:
            logger.warning(
                "extract.failed",
                url=source.url,
                category=extract_result.error_category,
                error=extract_result.error_message,
            )
            if state.record_tool_failure():
                logger.warning(
                    "circuit_breaker.tripped", topic=state.topic, stage="extract"
                )
                return


def _synthesize_brief(client: Anthropic, model: str, state: RunState) -> str:
    if not state.sources:
        return f"No sources were found for {state.topic!r} — nothing to summarize."

    user_prompt = _build_user_prompt(state)
    brief = call_for_structured_output(
        client,
        model,
        system_prompt=BRIEF_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=Brief,
        schema_hint=_BRIEF_SCHEMA_HINT,
        max_tokens=500,
    )

    if brief is None:
        logger.warning("brief.invalid_after_repair", topic=state.topic)
        return f"Could not synthesize a brief for {state.topic} (model output invalid after retry)."

    return brief.summary


def _build_user_prompt(state: RunState) -> str:
    sources_text = "\n\n".join(
        f"Source: {source.url}\nTitle: {source.title}\n"
        f"{source.content[:_SOURCE_CHARS_PER_ITEM]}"
        for source in state.sources
    )
    return f"Company: {state.topic}\n\nSources:\n{sources_text}"
