"""Pure eval metrics — no LLM/network calls, same purity bar as verify/.

Both metrics score the actual persisted artifacts (the rendered brief text,
the stored Fact rows), not internal pipeline state — re-deriving from what
was actually saved is a real check, not a tautology confirming the pipeline
agrees with itself.
"""

from __future__ import annotations

import re

from agent.schemas import RunRecord

_CITATION_PATTERN = re.compile(r"\[(https?://[^\]\s]+)\]\s*$")


def citation_coverage(record: RunRecord) -> float:
    """Fraction of the brief's lines that end in a citation to a source
    actually fetched during that run. 0.0 if there's no brief, or if the
    brief is one un-cited paragraph (the pre-Days-6-7 format) — a real,
    meaningful score, not a placeholder.
    """
    if not record.brief:
        return 0.0
    lines = [line for line in record.brief.split("\n") if line.strip()]
    if not lines:
        return 0.0
    valid_urls = {source.url for source in record.sources}
    cited = sum(1 for line in lines if _is_cited(line, valid_urls))
    return cited / len(lines)


def _is_cited(line: str, valid_urls: set[str]) -> bool:
    match = _CITATION_PATTERN.search(line.strip())
    return match is not None and match.group(1) in valid_urls


def fact_recall(record: RunRecord, expected_facts: list[str]) -> float | None:
    """Fraction of expected_facts found (case-insensitive substring) across
    the run's extracted fact values. None ("not applicable") when no
    expected facts were given for this case — kept distinct from a real 0%,
    since e.g. pre-Days-4-5 runs have no facts to search at all.
    """
    if not expected_facts:
        return None
    haystack = " ".join(fact.value for fact in record.facts).lower()
    found = sum(1 for expected in expected_facts if expected.lower() in haystack)
    return found / len(expected_facts)
