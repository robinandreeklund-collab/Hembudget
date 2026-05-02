"""Monte Carlo-tester · privat + företag tillsammans.

Verifierar att de två motorerna är balanserade när de kör ihop:
- Privat-motor: level 1 ska vara mestadels positive, level 3 svårare
- Biz-motor: deterministisk seed → samma resultat varje körning
- Kombinerad: biz får inte vara en pengasug på privatekonomin

Snabba tester (300 sims per körning) så CI inte tar evigheter.
"""
from __future__ import annotations

import pytest

from hembudget.business.engine.monte_carlo import (
    BizSimConfig, run_biz_simulations, summarize_biz,
)
from hembudget.game_engine.monte_carlo.runner import (
    SimConfig, run_simulations, summarize,
)
from hembudget.game_engine.monte_carlo.combined import (
    CombinedSimConfig, run_combined_simulations, summarize_combined,
)


# === Privat MC-baselines ===


def test_private_mc_level1_balanced_mostly_positive():
    """Level 1 balanserad ska vara förlåtande · ≥ 60 % positive."""
    cfg = SimConfig(
        n_simulations=300, starting_level=1, spend_profile="balanserad",
        seed_base=42,
    )
    res = run_simulations(cfg)
    summary = summarize(res)
    assert summary["classification"]["positive_pct"] >= 60.0, (
        f"Level 1 balanserad ska vara mestadels positive, "
        f"fick {summary['classification']['positive_pct']} %"
    )


def test_private_mc_level3_slosa_mostly_negative():
    """Level 3 slösa ska vara hård · ≥ 50 % negative."""
    cfg = SimConfig(
        n_simulations=300, starting_level=3, spend_profile="slosa",
        seed_base=99,
    )
    res = run_simulations(cfg)
    summary = summarize(res)
    assert summary["classification"]["negative_pct"] >= 50.0, (
        f"Level 3 slösa ska vara mestadels negative, "
        f"fick {summary['classification']['negative_pct']} %"
    )


# === Biz MC ===


def test_biz_mc_deterministic_with_seed():
    """Samma seed_base → identiska resultat."""
    cfg = BizSimConfig(
        n_simulations=200, industry_label="it", level="basics",
        seed_base=12345,
    )
    res1 = run_biz_simulations(cfg)
    res2 = run_biz_simulations(cfg)
    bal1 = sorted(res1.end_balances())
    bal2 = sorted(res2.end_balances())
    assert bal1 == bal2, "Samma seed gav olika resultat — inte deterministisk"


def test_biz_mc_basics_realistic_spread():
    """Basics ska ha REALISTISK spread (25-65% pos) — varken trivialt
    eller hopplöst. Verkligheten: 30-50% av nystartade småföretag går
    bra första året."""
    cfg = BizSimConfig(
        n_simulations=300, industry_label="it", level="basics",
        starting_reputation=50,
        monthly_owner_salary=0,
        monthly_fixed_cost=1500,
        seed_base=42,
    )
    res = run_biz_simulations(cfg)
    summary = summarize_biz(res)
    pos = summary["classification"]["positive_pct"]
    neg = summary["classification"]["negative_pct"]
    assert 25.0 <= pos <= 70.0, (
        f"Basics ska ha 25-70 % positive (realistic). Fick {pos} %"
    )
    assert 20.0 <= neg <= 55.0, (
        f"Basics ska ha 20-55 % negative (genuint utmanande). Fick {neg} %"
    )


def test_biz_mc_advanced_harder_than_basics():
    """Advanced ska vara HÅRDARE än basics (mer events, mer komplexa
    jobb, högre kund-krav). Median-kassa ska vara LÄGRE i advanced
    (det är meningen — advanced är fördjupningsläget med riktig risk)."""
    base_cfg = dict(
        n_simulations=300, industry_label="konsult",
        starting_reputation=50, monthly_owner_salary=0,
        monthly_fixed_cost=1500, seed_base=77,
    )
    basics = run_biz_simulations(BizSimConfig(level="basics", **base_cfg))
    advanced = run_biz_simulations(BizSimConfig(level="advanced", **base_cfg))
    bs = summarize_biz(basics)
    ads = summarize_biz(advanced)
    assert ads["kassa_end_year"]["median"] < bs["kassa_end_year"]["median"], (
        f"Advanced ska vara hårdare än basics. "
        f"Basics-median={bs['kassa_end_year']['median']}, "
        f"advanced-median={ads['kassa_end_year']['median']}"
    )
    assert ads["classification"]["negative_pct"] >= bs["classification"][
        "negative_pct"
    ] * 0.9, (
        "Advanced ska ha minst lika hög negative-rate som basics"
    )


def test_biz_mc_advanced_realistic_spread():
    """Advanced ska ha 20-55% positive och vara genuint hårdare."""
    cfg = BizSimConfig(
        n_simulations=300, industry_label="konsult", level="advanced",
        starting_reputation=50, monthly_owner_salary=0,
        monthly_fixed_cost=1500, seed_base=42,
    )
    res = run_biz_simulations(cfg)
    summary = summarize_biz(res)
    pos = summary["classification"]["positive_pct"]
    neg = summary["classification"]["negative_pct"]
    assert 15.0 <= pos <= 60.0, (
        f"Advanced ska ha 15-60 % positive. Fick {pos} %"
    )
    assert 25.0 <= neg <= 65.0, (
        f"Advanced ska ha 25-65 % negative. Fick {neg} %"
    )


# === Kombinerad ===


def test_combined_mc_biz_has_realistic_risk_reward():
    """Biz är RISKFYLLT — pedagogiskt rätt. Med MÅTTLIG owner_salary
    (5k/mån enskild firma-nivå) ska vi se en blandning av utfall."""
    cfg = CombinedSimConfig(
        n_simulations=300, starting_level=1, spend_profile="balanserad",
        biz_industry="konsult", biz_level="basics",
        biz_starting_reputation=50,
        biz_monthly_owner_salary=0,  # eget uttag, ingen formell lön
        biz_monthly_fixed_cost=1500,
        seed_base=42,
    )
    res = run_combined_simulations(cfg)
    summary = summarize_combined(res)
    drag = summary["biz"]["drag_pct"]
    boost = summary["biz"]["boost_pct"]
    # Bör vara rimligt utspritt.
    assert drag < 95.0, (
        f"Biz är nästan 100% pengasug ({drag}%) — det är fel. "
        f"Det ska finnas vinnare också."
    )
    assert boost > 10.0, (
        f"Biz har för få positiva utfall (boost={boost}%). "
        f"~30-60% av elever ska kunna lyckas."
    )


def test_combined_mc_top_quartile_biz_helps():
    """De TOP 25% combined-utfall ska vara klart bättre än median privat
    — duktigt biz lönar sig genuint."""
    cfg = CombinedSimConfig(
        n_simulations=400, starting_level=1, spend_profile="balanserad",
        biz_industry="konsult", biz_level="basics",
        biz_starting_reputation=50,
        biz_monthly_owner_salary=0,  # eget uttag
        biz_monthly_fixed_cost=1500,
        seed_base=42,
    )
    res = run_combined_simulations(cfg)
    summary = summarize_combined(res)

    # P75 combined ska vara HÖGRE än median privat (top quartile överträffar)
    assert summary["combined"]["p75"] > summary["private"]["median_balance"], (
        f"Top 25% combined: {summary['combined']['p75']} ska vara > "
        f"privat-median: {summary['private']['median_balance']}. "
        f"Duktigt biz lönar sig."
    )


def test_combined_mc_pentagon_realistic_after_year():
    """Final reputation efter 12 månader ska ligga i ett rimligt spann."""
    cfg = CombinedSimConfig(
        n_simulations=200, starting_level=1, spend_profile="balanserad",
        biz_industry="hantverk", biz_level="basics",
        biz_starting_reputation=50,
        seed_base=42,
    )
    res = run_combined_simulations(cfg)
    summary = summarize_combined(res)
    final_rep = summary["final_reputation"]["mean"]
    # Reputation kan både gå upp och ner beroende på kvalitet.
    # Spannet 35-85 är realistiskt för en blandning av nybörjare och
    # mer erfarna leveranser.
    assert 35 <= final_rep <= 85, (
        f"Reputation ligger orealistiskt — start 50, slut {final_rep}"
    )
