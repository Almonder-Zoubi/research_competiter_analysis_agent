"""Turns a topic into a handful of search queries.

Template-based for the walking skeleton, not an LLM call — this keeps the first
end-to-end run cheap while the rest of the loop gets proven out. An LLM-driven
planner (MODEL_FAST) is a natural swap-in later, behind the same signature.
"""

from __future__ import annotations


def make_search_queries(topic: str) -> list[str]:
    return [
        f"{topic} company overview",
        f"{topic} funding",
        f"{topic} founders",
    ]
