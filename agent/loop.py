"""The thin walking-skeleton loop:

    plan -> search -> store sources -> synthesize one brief -> store -> return

Budget guards from RunState are checked at every step so a run can't run away
(see CLAUDE.md). Cross-checking facts across sources, and the fully-cited brief
that's the project's headline feature, are Days 4-7 — this is deliberately crude.
"""

from __future__ import annotations

import structlog
from anthropic import Anthropic
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from agent.config import Settings
from agent.planner import make_search_queries
from agent.schemas import Brief
from agent.state import RunState
from memory.repository import save_brief, save_run, save_sources
from tools.search import SearchInput, SearchTool

logger = structlog.get_logger()

BRIEF_SYSTEM_PROMPT = """\
You are a research analyst. You are given raw text pulled from a few web pages \
about a company. Write a short, factual brief grounded only in that text — do not \
add outside knowledge.

Respond with ONLY valid JSON matching this schema, no other text:
{"topic": "<company name>", "summary": "<3-6 sentence summary>"}"""

_SOURCE_CHARS_PER_ITEM = 2000


def run_research(
    topic: str,
    *,
    settings: Settings,
    anthropic_client: Anthropic,
    search_tool: SearchTool,
    session_factory: sessionmaker,
) -> RunState:
    state = RunState(topic=topic)

    with session_factory() as session:
        state.run_id = save_run(session, topic=topic)

    state.plan = make_search_queries(topic)

    for query in state.plan:
        if not state.can_take_step(settings.max_steps):
            logger.warning("budget.max_steps_reached", topic=topic, query=query)
            break
        if not state.can_fetch_source(settings.max_sources):
            logger.warning("budget.max_sources_reached", topic=topic, query=query)
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
            continue

        found = result.value or []
        state.sources.extend(found)
        state.sources_used += len(found)

    if state.sources:
        with session_factory() as session:
            save_sources(session, state.run_id, state.sources)

    state.brief = _synthesize_brief(anthropic_client, settings.model_smart, state)

    with session_factory() as session:
        save_brief(session, state.run_id, state.brief)

    return state


def _synthesize_brief(client: Anthropic, model: str, state: RunState) -> str:
    if not state.sources:
        return f"No sources were found for {state.topic!r} — nothing to summarize."

    user_prompt = _build_user_prompt(state)

    brief = _call_for_brief(client, model, user_prompt)
    if brief is None:
        # One repair retry on invalid structured output, per CLAUDE.md's hard rule.
        repair_prompt = (
            f"{user_prompt}\n\n"
            "Your previous response was not valid JSON matching the schema. "
            'Respond again with ONLY valid JSON: {"topic": "...", "summary": "..."}.'
        )
        brief = _call_for_brief(client, model, repair_prompt)

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


def _call_for_brief(client: Anthropic, model: str, user_prompt: str) -> Brief | None:
    response = client.messages.create(
        model=model,
        max_tokens=500,
        system=BRIEF_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    try:
        return Brief.model_validate_json(_strip_code_fence(text))
    except ValidationError:
        return None


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
