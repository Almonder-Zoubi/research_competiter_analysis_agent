"""Offline tests for verify/reconcile.py — pure functions, no LLM/network
calls at all, so there's nothing to fake here (see CLAUDE.md: no live calls
in the test suite, trivially true for this module).
"""

from __future__ import annotations

from agent.schemas import Fact
from verify.reconcile import reconcile_facts


def _fact(attribute: str, value: str, url: str, confidence: float = 1.0) -> Fact:
    return Fact(attribute=attribute, value=value, source_url=url, confidence=confidence)


def test_single_uncorroborated_fact_gets_baseline_confidence() -> None:
    facts = [_fact("founded_year", "2016", "https://a.example/page")]

    reconciled, conflicts = reconcile_facts(facts)

    assert conflicts == []
    assert len(reconciled) == 1
    assert reconciled[0].confidence == 0.6


def test_agreement_across_independent_domains_raises_confidence() -> None:
    facts = [
        _fact("founded_year", "2016", "https://a.example/page"),
        _fact("founded_year", "2016", "https://b.example/page"),
        _fact("Founded Year", "2016", "https://c.example/page"),
    ]

    reconciled, conflicts = reconcile_facts(facts)

    assert conflicts == []
    assert len(reconciled) == 3
    assert all(f.confidence == 1.0 for f in reconciled)  # 0.6 + 0.2*2 = 1.0


def test_two_pages_on_the_same_domain_count_as_one_source() -> None:
    facts = [
        _fact("founded_year", "2016", "https://a.example/about"),
        _fact("founded_year", "2016", "https://a.example/history"),
    ]

    reconciled, conflicts = reconcile_facts(facts)

    assert conflicts == []
    # still just 1 distinct domain -> baseline, not boosted as if 2 sources
    assert all(f.confidence == 0.6 for f in reconciled)


def test_attribute_names_are_normalized_before_grouping() -> None:
    facts = [
        _fact("founded_year", "2016", "https://a.example/page"),
        _fact("Founded_Year", "2016", "https://b.example/page"),
        _fact("  founded year  ", "2016", "https://c.example/page"),
    ]

    reconciled, conflicts = reconcile_facts(facts)

    assert conflicts == []
    assert len(reconciled) == 3
    assert all(f.confidence == 1.0 for f in reconciled)


def test_disagreement_produces_a_conflict_and_lowers_confidence() -> None:
    facts = [
        _fact("employee_count", "210", "https://a.example/page"),
        _fact("employee_count", "250", "https://b.example/page"),
    ]

    reconciled, conflicts = reconcile_facts(facts)

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.attribute == "employee_count"
    assert {v.value for v in conflict.values} == {"210", "250"}

    assert len(reconciled) == 2
    # 1 domain each -> baseline 0.6, halved by the conflict penalty
    assert all(f.confidence == 0.3 for f in reconciled)


def test_conflict_with_corroboration_on_one_side_still_penalized() -> None:
    facts = [
        _fact("valuation", "$10B", "https://a.example/page"),
        _fact("valuation", "$10B", "https://b.example/page"),
        _fact("valuation", "$11B", "https://c.example/page"),
    ]

    reconciled, conflicts = reconcile_facts(facts)

    assert len(conflicts) == 1
    by_value = {f.value: f.confidence for f in reconciled}
    # $10B: 2 domains -> 0.8 corroboration, halved -> 0.4
    assert by_value["$10B"] == 0.4
    # $11B: 1 domain -> 0.6 baseline, halved -> 0.3
    assert by_value["$11B"] == 0.3


def test_unrelated_attributes_do_not_interfere_with_each_other() -> None:
    facts = [
        _fact("founded_year", "2016", "https://a.example/page"),
        _fact("headquarters", "Austin, Texas", "https://a.example/page"),
    ]

    reconciled, conflicts = reconcile_facts(facts)

    assert conflicts == []
    assert len(reconciled) == 2
    assert all(f.confidence == 0.6 for f in reconciled)


def test_does_not_mutate_input_list() -> None:
    facts = [_fact("founded_year", "2016", "https://a.example/page")]
    original_confidence = facts[0].confidence

    reconcile_facts(facts)

    assert facts[0].confidence == original_confidence


def test_reconciliation_is_idempotent() -> None:
    facts = [
        _fact("employee_count", "210", "https://a.example/page"),
        _fact("employee_count", "250", "https://b.example/page"),
        _fact("founded_year", "2016", "https://a.example/page"),
        _fact("founded_year", "2016", "https://c.example/page"),
    ]

    once, conflicts_once = reconcile_facts(facts)
    twice, conflicts_twice = reconcile_facts(once)

    assert sorted((f.attribute, f.value, f.confidence) for f in once) == sorted(
        (f.attribute, f.value, f.confidence) for f in twice
    )
    assert len(conflicts_once) == len(conflicts_twice) == 1


def test_empty_input_returns_empty_output() -> None:
    reconciled, conflicts = reconcile_facts([])

    assert reconciled == []
    assert conflicts == []
