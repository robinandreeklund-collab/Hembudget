"""Tester för Wellbeing-minimibelopp och budget-validering."""
from __future__ import annotations

import pytest

from hembudget.wellbeing.minimums import (
    CATEGORY_MINIMUMS_SEK_MONTH,
    check_against_minimum,
    lookup_minimum,
)


def test_lookup_known_category():
    assert lookup_minimum("Mat") == 2_840
    assert lookup_minimum("Hemförsäkring") == 200


def test_lookup_case_insensitive():
    assert lookup_minimum("mat") == 2_840
    assert lookup_minimum("MAT") == 2_840


def test_lookup_unknown_returns_none():
    assert lookup_minimum("Coola Saker") is None
    assert lookup_minimum("") is None


def test_check_above_minimum_is_ok():
    r = check_against_minimum("Mat", 3_500)
    assert r.severity == "ok"
    assert r.is_violation is False
    assert r.ratio > 1.0


def test_check_just_below_warns_but_no_violation():
    """Mat 2 400 kr (~85% av 2 840) → snålt, ej violation."""
    r = check_against_minimum("Mat", 2_400)
    assert r.severity == "snålt"
    assert r.is_violation is False


def test_check_under_80_pct_is_violation():
    """Mat 2 000 kr (~70 % av 2 840) → violation."""
    r = check_against_minimum("Mat", 2_000)
    assert r.severity == "snålt"
    assert r.is_violation is True


def test_check_under_50_pct_is_subexistens():
    """Mat 1 200 kr (~42 % av 2 840) → subexistens."""
    r = check_against_minimum("Mat", 1_200)
    assert r.severity == "subexistens"
    assert r.is_violation is True
    assert "subexistens" in r.severity or "hälften" in r.message.lower()


def test_unknown_category_returns_ok():
    r = check_against_minimum("Coola Saker", 50)
    assert r.severity == "ok"
    assert r.is_violation is False


def test_message_is_pedagogical():
    """Texten ska peka på Konsumentverket och Wellbeing."""
    r = check_against_minimum("Mat", 1_500)
    assert "konsumentverket" in r.message.lower()
    assert r.is_violation


def test_zero_budget_handled_gracefully():
    """Om eleven sätter 0 kr ska vi inte krascha på division."""
    r = check_against_minimum("Mat", 0)
    assert r.ratio == 0.0
    assert r.severity == "subexistens"


def test_minimums_dict_includes_essentials():
    """Sanity check — alla kärnkategorier finns."""
    essentials = ["Mat", "Hemförsäkring", "Bredband", "Hushållsel"]
    for cat in essentials:
        assert cat in CATEGORY_MINIMUMS_SEK_MONTH
