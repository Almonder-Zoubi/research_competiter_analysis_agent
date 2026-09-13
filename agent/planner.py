"""Turns a research subject into a handful of targeted search queries.

LLM-driven (MODEL_FAST) so query strategy adapts to what kind of subject this
is — a company, an engineering/research field, a product, or a specific
initiative inside a larger company — rather than assuming every topic is a
funded startup (the old template's "funding"/"founders" queries make no sense
for e.g. "harness engineering"). Falls back to a fixed, subject-agnostic
template if the model call fails or returns invalid output, so planning can
never break the run (see CLAUDE.md: never leave the loop able to crash on
model output).
"""

from __future__ import annotations

from anthropic import Anthropic
from langfuse import observe

from agent.llm import call_for_structured_output
from agent.schemas import SearchPlan

PLANNER_SYSTEM_PROMPT = """\
You are a research planning assistant. Given a research subject, first decide \
what kind of subject it is — a company or organization (including non-English \
names or legal suffixes like GmbH, AG, Ltd, S.A.), an engineering/technology/ \
research field, a product, or a specific initiative or division inside a \
larger company — then produce 2-3 short, keyword-style web search queries \
(not full sentences or questions) that together would surface a well-rounded, \
factual overview of it.

Guidance by subject type:
- Company or organization: queries covering what it does, ownership/financials \
(funding, revenue, or parent company), and history or leadership.
- Engineering/technology/research field: queries covering a definition or \
overview, the companies or institutions active in it, and recent developments \
or applications.
- A specific initiative, product, or division inside a larger company: \
queries covering what it is, its relationship to the parent company, and any \
notable projects or outcomes.

Respond with ONLY valid JSON matching this schema, no other text:
{"queries": ["<query 1>", "<query 2>", "<query 3>"]}"""

_SCHEMA_HINT = '{"queries": ["...", "...", "..."]}'


def make_search_queries(topic: str) -> list[str]:
    """Deterministic, subject-agnostic fallback used if the LLM planner fails."""
    return [
        f"{topic} overview",
        f"{topic} key companies OR organizations",
        f"{topic} recent news OR developments",
    ]


@observe(name="plan_search_queries")
def plan_search_queries(topic: str, *, client: Anthropic, model: str) -> list[str]:
    plan = call_for_structured_output(
        client,
        model,
        system_prompt=PLANNER_SYSTEM_PROMPT,
        user_prompt=f"Research subject: {topic}",
        schema=SearchPlan,
        schema_hint=_SCHEMA_HINT,
        max_tokens=200,
    )
    if plan is None or not plan.queries:
        return make_search_queries(topic)
    return plan.queries
