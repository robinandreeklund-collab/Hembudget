"""Tester för per-kategori-elasticitet i variable_expenses.

Pedagogiken: elevens budget-val styr genererade transaktioner via
ELASTICITY-floor. Mat 70 % floor (kropp behöver mat); nöje 0 %
(kan klippas helt). Spec: Sprint 7 budget-KV-integration.
"""
from __future__ import annotations

from hembudget.game_engine.monthly_engine.variable_expenses import (
    ELASTICITY,
    _apply_elasticity,
)


def test_no_student_budget_uses_kv_baseline():
    """Utan budget-val → KV-baseline rakt av."""
    assert _apply_elasticity("Mat & livsmedel", 3000, None) == 3000


def test_student_budget_above_floor_wins():
    """Elev sätter mat 4000 (över KV) → 4000 genereras."""
    assert _apply_elasticity("Mat & livsmedel", 3000, 4000) == 4000


def test_student_budget_below_mat_floor_clamped():
    """Mat-floor 70 % → kan inte gå under 0.7 × KV."""
    # KV=3000, floor=0.7 → 2100. Elev sätter 1500 → effective=2100
    assert _apply_elasticity("Mat & livsmedel", 3000, 1500) == 2100


def test_noje_zero_floor_follows_student():
    """Nöje 0 % floor → eleven kan stänga av helt."""
    assert _apply_elasticity("Nöje & fritid", 1500, 0) == 0
    assert _apply_elasticity("Nöje & fritid", 1500, 200) == 200


def test_restaurang_zero_floor_follows_student():
    """Restaurang 0 % floor → eleven styr helt."""
    assert _apply_elasticity("Restaurang & café", 900, 0) == 0


def test_klader_low_floor():
    """Kläder & skor 20 % floor."""
    # KV=600, floor=0.2 → 120. Elev sätter 50 → 120.
    assert _apply_elasticity("Kläder & skor", 600, 50) == 120


def test_unknown_category_default_floor():
    """Okänd kategori → 50 % floor (defensiv default)."""
    # KV=1000, floor=0.5 → 500
    assert _apply_elasticity("Okänd kategori XYZ", 1000, 100) == 500


def test_elasticity_table_covers_required_categories():
    """Sanity check — alla rörlig-utgift-kategorier från canonical-listan
    har en floor. "Transport (övrigt)" och "Barn & familj" konsoliderades
    bort i SKV-6 (kanonisk kategorilista) och ingår nu i "Transport"
    respektive "Övrigt"."""
    required = [
        "Mat & livsmedel", "Hälsa & hygien", "Transport",
        "Övrigt", "Förbrukningsvaror", "Kläder & skor",
        "Nöje & fritid", "Restaurang & café",
    ]
    for cat in required:
        assert cat in ELASTICITY, f"missing {cat}"


def test_mat_and_hygien_share_floor():
    """Mat och hygien är båda hälso-kritiska → 70 % floor."""
    assert ELASTICITY["Mat & livsmedel"] == 0.70
    assert ELASTICITY["Hälsa & hygien"] == 0.70
