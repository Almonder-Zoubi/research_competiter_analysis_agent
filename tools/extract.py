"""Extracts atomic, attributed facts from one source's text.

MODEL_FAST (Haiku) — extraction runs once per source, so this needs to stay a
cheap, high-volume call (see CLAUDE.md's model routing). Structured output goes
through the shared validate + one-repair-retry helper (agent/llm.py) like every
other structured call in this project — never trust raw model JSON.

The model is only asked for attribute/value pairs, never for source_url: we
already know which source we're extracting from, so filling it in ourselves
avoids trusting the model to echo back — and never mangle — a URL it was
already given (same reasoning as _drop_hallucinated_urls in deep_research.py).
"""

from __future__ import annotations

from anthropic import Anthropic, AnthropicError
from langfuse import observe
from pydantic import BaseModel, Field

from agent.llm import call_for_structured_output
from agent.schemas import Fact, Source
from tools.base import Tool, ToolErrorCategory, ToolResult

EXTRACT_SYSTEM_PROMPT = """\
You are a fact-extraction assistant. Given the text of one web page about a \
research subject, pull out a handful of atomic, factual claims explicitly \
stated in the text. Each fact is a short attribute/value pair grounded only \
in this text; never infer or add outside knowledge, and skip anything not \
clearly stated. If the text contains no extractable facts, return an empty \
list.

Use one of these attribute names whenever a fact matches it, so the same \
real-world fact is named consistently across different sources: \
founded_year, headquarters, founders, ceo, employee_count, funding_total, \
latest_funding_round, valuation, revenue, ownership, products, industry, \
controversies. If a fact doesn't fit any of these, use a short descriptive \
attribute name of your own.

Respond with ONLY valid JSON matching this schema, no other text:
{"facts": [{"attribute": "<attribute name>", "value": "<value>"}]}"""

_SCHEMA_HINT = '{"facts": [{"attribute": "...", "value": "..."}]}'
_SOURCE_CHARS = 4000


class ExtractInput(BaseModel):
    source: Source
    topic: str


class _ExtractedFact(BaseModel):
    attribute: str
    value: str


class _ExtractedFacts(BaseModel):
    facts: list[_ExtractedFact] = Field(default_factory=list)


class ExtractTool(Tool[list[Fact]]):
    name = "extract"

    def __init__(self, client: Anthropic, model: str) -> None:
        self._client = client
        self._model = model

    @observe(name="extract", as_type="tool")
    def run(self, input: ExtractInput) -> ToolResult[list[Fact]]:  # type: ignore[override]
        if not input.source.content.strip():
            return ToolResult.success([])

        user_prompt = (
            f"Research subject: {input.topic}\n"
            f"Source: {input.source.url}\n\n"
            f"{input.source.content[:_SOURCE_CHARS]}"
        )

        try:
            parsed = call_for_structured_output(
                self._client,
                self._model,
                system_prompt=EXTRACT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema=_ExtractedFacts,
                schema_hint=_SCHEMA_HINT,
                max_tokens=600,
            )
        except AnthropicError as e:
            return ToolResult.failure(ToolErrorCategory.TRANSIENT, str(e))

        if parsed is None:
            return ToolResult.failure(
                ToolErrorCategory.VALIDATION,
                f"could not extract facts from {input.source.url} "
                "(invalid model output after retry)",
            )

        facts = [
            Fact(attribute=f.attribute, value=f.value, source_url=input.source.url)
            for f in parsed.facts
        ]
        return ToolResult.success(facts)
