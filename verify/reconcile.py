"""Reconciles atomic facts extracted from multiple sources — the project's
headline feature (see CLAUDE.md). Pure and deterministic: no LLM/network
calls, so it costs nothing and is exhaustively testable offline.

Agreement across independent sources raises confidence; disagreement is
recorded as a Conflict rather than silently picked between. "Independent"
means distinct domains, not distinct URLs — two pages on the same site aren't
corroborating each other (see ROADMAP.md's "corroborating independent
sources").

Known limitations (both confirmed against real extraction output — a `show`
of run #7's 60 real Notion facts — not hypothetical):
- Values are compared by exact normalized-string match, not semantic
  equivalence — "$343.2 million" and "343.2M" won't be recognized as
  agreeing. A real fix needs an LLM call or embedding similarity; both cost
  money and are deferred (see DAYS_6_7_verification.md).
- Naturally multi-valued attributes (e.g. "founders" or "products", where a
  company legitimately has more than one) get misread as a conflict when a
  source lists them across separate facts with the same attribute name —
  confirmed live: two "co-founder" facts (Ivan Zhao, Akshay Kothari) from the
  same source were flagged as disagreeing, when both are true. Distinguishing
  "these sources disagree" from "this attribute holds several values" needs
  either a fixed multi-valued-attribute list (attribute-specific
  special-casing this module deliberately avoids) or a smarter extraction
  step; deferred rather than special-cased for one example.
"""

from __future__ import annotations

import re
from collections import defaultdict
from urllib.parse import urlsplit

from agent.schemas import Conflict, ConflictingValue, Fact

_BASE_CONFIDENCE = 0.6
_CONFIDENCE_PER_EXTRA_DOMAIN = 0.2
_CONFLICT_PENALTY = 0.5


def reconcile_facts(facts: list[Fact]) -> tuple[list[Fact], list[Conflict]]:
    """Groups facts by attribute, corroborates or flags conflicts within each
    group, and returns new Fact objects with adjusted confidence alongside any
    Conflicts found. Pure and idempotent: confidence is recomputed from
    attribute/value/source_url only, never read from the input, so calling
    this again on an already-reconciled list reproduces the same result.
    Never mutates its input.
    """
    groups: dict[str, list[Fact]] = defaultdict(list)
    display_attribute: dict[str, str] = {}
    for fact in facts:
        key = _normalize(fact.attribute)
        groups[key].append(fact)
        display_attribute.setdefault(key, fact.attribute)

    reconciled: list[Fact] = []
    conflicts: list[Conflict] = []

    for key, group in groups.items():
        by_value: dict[str, list[Fact]] = defaultdict(list)
        for fact in group:
            by_value[_normalize(fact.value)].append(fact)

        if len(by_value) == 1:
            confidence = _corroboration_confidence(_distinct_domains(group))
            reconciled.extend(_with_confidence(f, confidence) for f in group)
            continue

        conflicts.append(
            Conflict(
                attribute=display_attribute[key],
                values=[
                    ConflictingValue(
                        value=same_value[0].value, source_url=same_value[0].source_url
                    )
                    for same_value in by_value.values()
                ],
            )
        )
        for same_value in by_value.values():
            confidence = (
                _corroboration_confidence(_distinct_domains(same_value))
                * _CONFLICT_PENALTY
            )
            reconciled.extend(_with_confidence(f, confidence) for f in same_value)

    return reconciled, conflicts


def _corroboration_confidence(distinct_domains: int) -> float:
    return min(
        1.0, _BASE_CONFIDENCE + _CONFIDENCE_PER_EXTRA_DOMAIN * (distinct_domains - 1)
    )


def _distinct_domains(facts: list[Fact]) -> int:
    return len({_domain(f.source_url) for f in facts})


def _with_confidence(fact: Fact, confidence: float) -> Fact:
    return Fact(
        attribute=fact.attribute,
        value=fact.value,
        source_url=fact.source_url,
        confidence=round(confidence, 4),
    )


def _normalize(text: str) -> str:
    return re.sub(r"[\s_]+", " ", text.strip().lower())


def _domain(url: str) -> str:
    netloc = urlsplit(url).netloc.lower()
    return netloc.removeprefix("www.")
