"""Offline tests for verify/grounding.py — pure, no LLM/network calls."""

from __future__ import annotations

from agent.schemas import CitedClaim
from verify.grounding import drop_ungrounded_claims


def test_claim_citing_a_known_source_survives() -> None:
    claims = [CitedClaim(claim="Founded in 2016.", source_url="https://a.example/page")]

    kept = drop_ungrounded_claims(claims, valid_urls={"https://a.example/page"})

    assert kept == claims


def test_claim_citing_an_unknown_url_is_dropped() -> None:
    claims = [
        CitedClaim(claim="Founded in 2016.", source_url="https://a.example/page"),
        CitedClaim(claim="Raised $10M.", source_url="https://hallucinated.example/x"),
    ]

    kept = drop_ungrounded_claims(claims, valid_urls={"https://a.example/page"})

    assert len(kept) == 1
    assert kept[0].source_url == "https://a.example/page"


def test_all_ungrounded_returns_empty_list_without_raising() -> None:
    claims = [CitedClaim(claim="Made up.", source_url="https://hallucinated.example/x")]

    kept = drop_ungrounded_claims(claims, valid_urls={"https://a.example/page"})

    assert kept == []


def test_empty_claims_returns_empty_list() -> None:
    assert drop_ungrounded_claims([], valid_urls={"https://a.example/page"}) == []
