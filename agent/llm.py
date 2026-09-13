"""Shared helper for validated, repair-retried structured LLM output.

Every call that must return structured data goes through here — see CLAUDE.md's
hard rule: validate against a Pydantic model, one repair retry on invalid output,
never trust raw model JSON. Used by agent/planner.py, agent/cited_brief.py,
agent/deep_research.py, and tools/extract.py; factored out once a second caller
needed it.

_call_once is also the single choke point for LLM-call tracing (Day 8, see
agent/tracing.py) — every one of those callers' Anthropic calls is traced here,
once, rather than instrumenting each call site separately.
"""

from __future__ import annotations

from typing import TypeVar

from anthropic import Anthropic
from langfuse import get_client, observe
from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


# Keep the repair prompt small — a full pydantic error message can be long.
_MAX_ERROR_CHARS = 300


def call_for_structured_output(
    client: Anthropic,
    model: str,
    *,
    system_prompt: str,
    user_prompt: str,
    schema: type[ModelT],
    schema_hint: str,
    max_tokens: int,
) -> ModelT | None:
    """Call once; on invalid output, ask once more — telling the model what
    specifically was wrong (not just "try again"), which matters a lot for
    freeform JSON output on rich topics (e.g. a model quoting a source's exact
    words without escaping the quotes breaks JSON well past the schema hint
    alone fixing it). None if both attempts fail — callers must have a safe
    fallback, never crash the loop on bad model output.
    """
    parsed, error = _call_once(
        client, model, system_prompt, user_prompt, schema, max_tokens
    )
    if parsed is not None:
        return parsed

    repair_prompt = (
        f"{user_prompt}\n\n"
        f"Your previous response was not valid JSON matching the schema "
        f"(error: {error}). Respond again with ONLY valid JSON: {schema_hint} "
        "Do not use literal double-quote characters inside any string value — "
        "rephrase or use single quotes instead, since an unescaped double "
        "quote breaks JSON."
    )
    parsed, _ = _call_once(
        client, model, system_prompt, repair_prompt, schema, max_tokens
    )
    return parsed


@observe(
    name="anthropic_call",
    as_type="generation",
    capture_input=False,
    capture_output=False,
)
def _call_once(
    client: Anthropic,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: type[ModelT],
    max_tokens: int,
) -> tuple[ModelT | None, str | None]:
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")

    # Recorded on the current @observe-created generation span, not returned —
    # a no-op when tracing is disabled (see agent/tracing.py; confirmed safe
    # to call unconditionally, no active-span check needed by callers).
    # getattr, not response.usage directly: test fakes across this project
    # return a bare SimpleNamespace(content=...) with no .usage, and this is
    # a secondary observability signal, not core behavior worth failing over.
    usage = getattr(response, "usage", None)
    usage_details = (
        {"input": usage.input_tokens, "output": usage.output_tokens}
        if usage is not None
        else None
    )
    get_client().update_current_generation(
        model=model, input=user_prompt, output=text, usage_details=usage_details
    )

    try:
        return schema.model_validate_json(_strip_code_fence(text)), None
    except ValidationError as e:
        return None, str(e)[:_MAX_ERROR_CHARS]


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
