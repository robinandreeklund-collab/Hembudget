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


# === Familje-aware lookup (Sprint 7 budget+KV-integration) ============

class _Profile:
    """Lättviktigt mock-objekt med StudentProfile-liknande fält."""
    def __init__(
        self, *, age=25, family_status="ensam",
        children_ages=None, housing_type="hyresratt",
    ):
        self.age = age
        self.family_status = family_status
        self.children_ages = children_ages or []
        self.housing_type = housing_type


def test_kv_household_singel_mat_matches_kv_table():
    """Singel 25 år mat → 2 730 kr (KV 25-50)."""
    from hembudget.wellbeing.minimums import kv_minimum_for_household
    val = kv_minimum_for_household(
        "Mat & livsmedel", adult_age=25, children_ages=[],
    )
    assert val == 2_730


def test_kv_household_sambo_mat_doubles():
    """Sambo båda 25 år → mat ~ 2 × 2 730 = 5 460 kr."""
    from hembudget.wellbeing.minimums import kv_minimum_for_household
    val = kv_minimum_for_household(
        "Mat & livsmedel", adult_age=25, partner_age=25,
        children_ages=[],
    )
    assert val == 5_460


def test_kv_household_familj_med_barn_includes_kids():
    """Familj 30 + 30 + barn 5 år → mat = 2730 + 2730 + 1710."""
    from hembudget.wellbeing.minimums import kv_minimum_for_household
    val = kv_minimum_for_household(
        "Mat & livsmedel", adult_age=30, partner_age=30,
        children_ages=[5],
    )
    # 2730 (vuxen) + 2730 (vuxen) + 1710 (4-6 år) = 7170
    assert val == 7_170


def test_kv_for_student_uses_profile_fields():
    """kv_minimum_for_student plockar fält från profile-objektet."""
    from hembudget.wellbeing.minimums import kv_minimum_for_student
    profile = _Profile(
        age=30, family_status="familj_med_barn",
        children_ages=[5],
    )
    val = kv_minimum_for_student("Mat & livsmedel", profile)
    assert val == 7_170


def test_kv_for_student_none_profile_falls_back():
    """profile=None → använder hardcoded CATEGORY_MINIMUMS_SEK_MONTH."""
    from hembudget.wellbeing.minimums import kv_minimum_for_student
    val = kv_minimum_for_student("Mat", None)
    assert val == 2_840


def test_check_against_minimum_with_profile_uses_family_aware():
    """Check med profile → familje-aware minimum."""
    profile = _Profile(
        age=30, family_status="sambo",
    )
    # Sambo-matminimum är ~5 460 kr; budget 2 800 kr → ratio < 0.8
    r = check_against_minimum(
        "Mat & livsmedel", 2_800, profile=profile,
    )
    assert r.is_violation is True


def test_kv_household_vatten_zero_for_hyresratt():
    """Hyresrätt har ofta vatten i hyran → minimum=0."""
    from hembudget.wellbeing.minimums import kv_minimum_for_household
    val = kv_minimum_for_household(
        "Vatten", adult_age=30, housing_type="hyresratt",
    )
    assert val == 0
