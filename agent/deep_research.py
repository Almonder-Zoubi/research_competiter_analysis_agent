"""Deep-research mode: more targeted query planning and structured, multi-section
synthesis than the default light-mode brief. Opt-in via `--deep-research` (see
cli.py) — the default run_research() path in agent/loop.py is untouched.

Kept in its own module rather than folded into agent/planner.py / agent/loop.py
so this genuinely-additive, more-expensive path is easy to review, test, and (if
it doesn't pull its weight) delete as one unit.
"""

from __future__ import annotations

from anthropic import Anthropic

from agent.llm import call_for_structured_output
from agent.schemas import DeepResearchPlan, DeepResearchReport, ReportSection, Source

DEEP_RESEARCH_PLANNER_SYSTEM_PROMPT = """\
You are a research planning assistant preparing for an in-depth, multi-section \
report — more thorough than a quick overview. Given a research subject, first \
classify it as one of: "company" (a company or organization, including \
non-English names or legal suffixes like GmbH, AG, Ltd, S.A.), "field" (an \
engineering/technology/research field), or "initiative" (a specific \
initiative, product, or division inside a larger company). Then produce 5-6 \
short, keyword-style web search queries (not full sentences or questions) \
that together would surface enough material for a structured report covering \
several distinct angles — not just a general overview.

Guidance by subject type:
- company: queries covering what it does, ownership/corporate structure, \
financials (revenue, valuation, or funding), history/founding, scale \
(employees, offices, markets), and any controversies, lawsuits, or scandals \
(search for this even if you expect to find nothing — that is a normal, \
expected outcome, not a failure).
- field: queries covering a definition/overview, the key organizations or \
researchers active in it, the current state of the art, real-world \
applications, and known criticisms, risks, or open problems.
- initiative: queries covering what it is, its relationship to the parent \
company, key people or products involved, outcomes/reception, and any \
criticisms or controversies.

Respond with ONLY valid JSON matching this schema, no other text:
{"subject_type": "company" | "field" | "initiative", \
"queries": ["<query 1>", "<query 2>", "..."]}"""

_PLAN_SCHEMA_HINT = (
    '{"subject_type": "company", "queries": ["...", "...", "...", "...", "..."]}'
)

DEEP_RESEARCH_SYSTEM_PROMPT = """\
You are a research analyst producing an in-depth, multi-section report. You \
are given raw text pulled from several web pages about a research subject, \
plus its subject type. Write one entry per section listed below for that \
subject type, grounded only in the given text — do not add outside \
knowledge. Each section's content should be 3-6 sentences.

If a section asks about controversies, scandals, or criticisms and the \
sources contain nothing on that topic, write exactly: "No notable \
controversies were found in the available sources." Do not invent or imply \
one that isn't supported by the text.

Sections by subject type:
- company: Origin & History, Ownership & Corporate Structure, Financials, \
Products & Services, Scale, Controversies & Legal Issues.
- field: Overview & Definition, Key Organizations & Players, Current State \
of the Art, Applications & Real-World Impact, Criticisms & Open Problems, \
Recent Developments.
- initiative: Overview, Relationship to Parent Company, Key People & \
Products, Outcomes & Reception, Criticisms.
- general: Overview, Key Details, Notable People OR Organizations, Recent \
Developments, Notable Issues OR Criticisms.

For each section, list which of the given source URLs support its content \
in source_urls — only URLs that were actually given to you, never invent one.

Do not use literal double-quote characters inside any string value (heading \
or content) — if you want to quote a phrase from a source, rephrase it \
without quotation marks or use single quotes instead. An unescaped double \
quote inside a JSON string breaks the response.

Respond with ONLY valid JSON matching this schema, no other text:
{"topic": "<subject>", "subject_type": "<company|field|initiative|general>", \
"sections": [{"heading": "<heading>", "content": "<3-6 sentences>", \
"source_urls": ["<url>", "..."]}]}"""

_REPORT_SCHEMA_HINT = (
    '{"topic": "...", "subject_type": "...", '
    '"sections": [{"heading": "...", "content": "...", "source_urls": ["..."]}]}'
)

# More context per source than light mode's 2000 chars — deep sections need
# more raw material to draw from, especially for niche categories like scale
# or controversies that a short excerpt might not even mention.
_DEEP_SOURCE_CHARS_PER_ITEM = 3000


def make_deep_research_queries(topic: str) -> DeepResearchPlan:
    """Deterministic, subject-agnostic fallback used if the LLM planner fails.

    subject_type="general" maps to a generic section set in
    synthesize_deep_report — never guesses "company" for a subject we
    couldn't even classify.
    """
    return DeepResearchPlan(
        subject_type="general",
        queries=[
            f"{topic} overview",
            f"{topic} history OR background",
            f"{topic} key people OR organizations",
            f"{topic} controversies OR criticisms OR issues",
            f"{topic} recent developments",
        ],
    )


def plan_deep_research_queries(
    topic: str, *, client: Anthropic, model: str
) -> DeepResearchPlan:
    plan = call_for_structured_output(
        client,
        model,
        system_prompt=DEEP_RESEARCH_PLANNER_SYSTEM_PROMPT,
        user_prompt=f"Research subject: {topic}",
        schema=DeepResearchPlan,
        schema_hint=_PLAN_SCHEMA_HINT,
        max_tokens=350,
    )
    if plan is None or not plan.queries:
        return make_deep_research_queries(topic)
    return plan


def synthesize_deep_report(
    client: Anthropic,
    model: str,
    *,
    topic: str,
    subject_type: str,
    sources: list[Source],
) -> DeepResearchReport:
    """Never returns None — like loop.py's _synthesize_brief, always produces
    something to persist and render, substituting a one-section explanatory
    report on total failure so a run can never end with nothing to show.
    """
    if not sources:
        return _fallback_report(
            topic,
            subject_type,
            f"No sources were found for {topic!r} — nothing to summarize.",
        )

    user_prompt = _build_user_prompt(topic, subject_type, sources)
    report = call_for_structured_output(
        client,
        model,
        system_prompt=DEEP_RESEARCH_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=DeepResearchReport,
        schema_hint=_REPORT_SCHEMA_HINT,
        # Confirmed via a real run (Wirecard, 15 sources) that 2500 truncates
        # mid-JSON on a data-rich topic (stop_reason: "max_tokens"); 4000 gave
        # the model room to finish (stop_reason: "end_turn").
        max_tokens=4000,
    )
    if report is None:
        return _fallback_report(
            topic,
            subject_type,
            f"Could not synthesize a deep research report for {topic} "
            "(model output invalid after retry).",
        )
    return _drop_hallucinated_urls(report, known_urls={s.url for s in sources})


def _fallback_report(topic: str, subject_type: str, message: str) -> DeepResearchReport:
    return DeepResearchReport(
        topic=topic,
        subject_type=subject_type,
        sections=[ReportSection(heading="Note", content=message, source_urls=[])],
    )


def _drop_hallucinated_urls(
    report: DeepResearchReport, known_urls: set[str]
) -> DeepResearchReport:
    """Cheap guard, ahead of the full verify/ pipeline (Days 6-7): a section's
    source_urls must be a subset of URLs we actually fetched this run — drop
    anything the model cited that we never gave it.
    """
    sections = [
        section.model_copy(
            update={"source_urls": [u for u in section.source_urls if u in known_urls]}
        )
        for section in report.sections
    ]
    return report.model_copy(update={"sections": sections})


def _build_user_prompt(topic: str, subject_type: str, sources: list[Source]) -> str:
    sources_text = "\n\n".join(
        f"Source: {source.url}\nTitle: {source.title}\n"
        f"{source.content[:_DEEP_SOURCE_CHARS_PER_ITEM]}"
        for source in sources
    )
    return f"Subject: {topic}\nSubject type: {subject_type}\n\nSources:\n{sources_text}"
