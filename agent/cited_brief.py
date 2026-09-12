"""Synthesizes a brief as one cited claim per reconciled fact, instead of one
ungrounded paragraph over raw source text — the project's headline feature
(see CLAUDE.md, DAYS_6_7_verification.md).

None-on-failure, like agent/planner.py's plan_search_queries — agent/loop.py
owns the fallback text rather than this module hiding it internally (unlike
agent/deep_research.py's always-non-None convention), because loop.py also
has to fold in the grounding-filter step (verify/grounding.py) in between a
failed/successful call and the final text, and that composition is easier to
follow with one owner.
"""

from __future__ import annotations

from anthropic import Anthropic

from agent.llm import call_for_structured_output
from agent.schemas import Fact, VerifiedBrief

CITED_BRIEF_SYSTEM_PROMPT = """\
You are a research analyst. You are given a list of reconciled facts about a \
research subject, each with a confidence score and the exact source URL it \
came from. Write one short claim per fact worth including in a brief \
overview (skip facts too minor or redundant to mention) — each claim must \
cite the source_url of the fact it's based on, copied exactly. Do not add \
outside knowledge, and do not write anything that isn't backed by one of the \
given facts.

Do not use literal double-quote characters inside any string value — \
rephrase or use single quotes instead, since an unescaped double quote \
breaks JSON.

Respond with ONLY valid JSON matching this schema, no other text:
{"topic": "<subject>", "claims": [{"claim": "<one sentence>", \
"source_url": "<the fact's source_url, verbatim>"}]}"""

_SCHEMA_HINT = '{"topic": "...", "claims": [{"claim": "...", "source_url": "..."}]}'

# Keeps the prompt (and expected output) bounded on a fact-rich run — the
# Notion proof run (Days 4-5) produced 60 facts from 9 sources, and Figma
# (Days 6-7's own live proof run) produced 57. 40 facts each needing their own
# claim + full source URL in the output is a lot to ask for; 25 is still
# generous for a brief overview and cuts the expected output size.
_MAX_FACTS = 25


def synthesize_cited_brief(
    client: Anthropic, model: str, *, topic: str, facts: list[Fact]
) -> VerifiedBrief | None:
    user_prompt = _build_user_prompt(topic, facts)
    return call_for_structured_output(
        client,
        model,
        system_prompt=CITED_BRIEF_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=VerifiedBrief,
        schema_hint=_SCHEMA_HINT,
        # Confirmed via a real run (Figma, 57 facts -> 40 used under the old
        # cap): the first attempt at this milestone's live proof run failed
        # synthesis. Same root cause already confirmed once for deep-research
        # (see PROGRESS.md's Wirecard finding) — max_tokens=1200 was too low
        # once every claim also carries a full source URL in the output.
        # Raised to match deep_research.py's confirmed-working value.
        max_tokens=4000,
    )


def render_brief_text(brief: VerifiedBrief) -> str:
    """Pure: turns claims into the plain-text string persisted as
    RunRecord.brief — one cited sentence per line."""
    return "\n".join(f"{claim.claim} [{claim.source_url}]" for claim in brief.claims)


def _build_user_prompt(topic: str, facts: list[Fact]) -> str:
    facts_text = "\n".join(
        f"- {f.attribute}: {f.value} "
        f"(confidence: {f.confidence}, source_url: {f.source_url})"
        for f in facts[:_MAX_FACTS]
    )
    return f"Subject: {topic}\n\nFacts:\n{facts_text}"
