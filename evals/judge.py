"""LLM-as-judge for brief quality — opt-in, costs money (see
DAYS_9_10_evals_and_polish.md). Never called by default; only when
`research-agent eval --judge` is passed. Uses MODEL_SMART: this is a
one-call-per-golden-case qualitative judgment, not a high-volume call like
extraction, so the cost stays small even with the stronger model — and a
qualitative judgment benefits more from a stronger model than a cheap one.
"""

from __future__ import annotations

from anthropic import Anthropic
from pydantic import BaseModel, Field

from agent.llm import call_for_structured_output

JUDGE_SYSTEM_PROMPT = """\
You are evaluating the quality of a research brief written by another AI system. \
You are given the research subject and the brief text (each line is a claim, \
optionally ending in a bracketed source URL). Score it on two dimensions, each \
1 (poor) to 5 (excellent):

- clarity_score: is the brief well-organized, specific, and easy to understand?
- groundedness_score: do the claims read as genuinely grounded in cited sources \
(citations present, sensible, and relevant to their claims) rather than vague or \
unsupported assertions? A brief with no citations at all should score low here.

Respond with ONLY valid JSON matching this schema, no other text:
{"clarity_score": <1-5>, "groundedness_score": <1-5>, "reasoning": "<1-2 sentences>"}"""

_SCHEMA_HINT = '{"clarity_score": 1-5, "groundedness_score": 1-5, "reasoning": "..."}'


class BriefQualityJudgment(BaseModel):
    clarity_score: int = Field(ge=1, le=5)
    groundedness_score: int = Field(ge=1, le=5)
    reasoning: str


def judge_brief_quality(
    client: Anthropic, model: str, *, topic: str, brief_text: str
) -> BriefQualityJudgment | None:
    user_prompt = f"Research subject: {topic}\n\nBrief:\n{brief_text}"
    return call_for_structured_output(
        client,
        model,
        system_prompt=JUDGE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=BriefQualityJudgment,
        schema_hint=_SCHEMA_HINT,
        max_tokens=300,
    )
