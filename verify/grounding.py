"""Enforces the project's headline metric — % of brief claims grounded in a
cited source — at the code level rather than trusting the synthesis prompt
alone. Pure, no LLM/network calls. Same reasoning as
agent/deep_research.py's _drop_hallucinated_urls: a model can cite a source
it wasn't given, so the guarantee has to be checked, not just asked for.
"""

from __future__ import annotations

from agent.schemas import CitedClaim


def drop_ungrounded_claims(
    claims: list[CitedClaim], valid_urls: set[str]
) -> list[CitedClaim]:
    """Keeps only claims whose source_url is actually among the run's fetched
    sources. Returns [] if every claim was ungrounded — the caller decides
    the fallback, this function never raises."""
    return [claim for claim in claims if claim.source_url in valid_urls]
