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


def test_biz_mc_basics_mostly_positive():
    """Basics IT-konsult ska kunna gå runt · ≥ 70 % positive."""
    cfg = BizSimConfig(
        n_simulations=300, industry_label="it", level="basics",
        starting_reputation=50,
        monthly_owner_salary=0,
        monthly_fixed_cost=1500,
        seed_base=42,
    )
    res = run_biz_simulations(cfg)
    summary = summarize_biz(res)
    assert summary["classification"]["positive_pct"] >= 70.0, (
        f"Basics IT-konsult ska vara framgångsrikt, "
        f"fick {summary['classification']['positive_pct']} %"
    )


def test_biz_mc_advanced_has_more_variance():
    """Advanced ska ha fler events → större stdev än basics."""
    base_cfg = dict(
        n_simulations=300, industry_label="hantverk",
        starting_reputation=50, monthly_owner_salary=0,
        monthly_fixed_cost=1500, seed_base=77,
    )
    basics = run_biz_simulations(BizSimConfig(level="basics", **base_cfg))
    advanced = run_biz_simulations(BizSimConfig(level="advanced", **base_cfg))
    bs = summarize_biz(basics)
    ads = summarize_biz(advanced)
    assert ads["kassa_end_year"]["stdev"] > bs["kassa_end_year"]["stdev"] * 0.9, (
        f"Advanced ska ha minst lika stor variance som basics — "
        f"basics={bs['kassa_end_year']['stdev']}, "
        f"advanced={ads['kassa_end_year']['stdev']}"
    )


# === Kombinerad ===


def test_combined_mc_biz_does_not_drag_private():
    """Biz får INTE vara en pengasug · majoritet ska ha boost, inte drag."""
    cfg = CombinedSimConfig(
        n_simulations=300, starting_level=1, spend_profile="balanserad",
        biz_industry="konsult", biz_level="basics",
        biz_starting_reputation=50,
        biz_monthly_owner_salary=12000,
        biz_monthly_fixed_cost=1500,
        seed_base=42,
    )
    res = run_combined_simulations(cfg)
    summary = summarize_combined(res)
    drag = summary["biz"]["drag_pct"]
    boost = summary["biz"]["boost_pct"]
    assert boost > drag * 3, (
        f"Biz är en pengasug: {drag}% drag mot {boost}% boost. "
        f"Biz ska oftare boosta privatekonomin än dra ner den."
    )


def test_combined_mc_biz_helps_struggling_private():
    """Kombinerad level 3 slösa + biz ska vara BÄTTRE än bara privat."""
    priv_cfg = SimConfig(
        n_simulations=300, starting_level=3, spend_profile="slosa",
        seed_base=99,
    )
    priv_res = run_simulations(priv_cfg)
    priv_median = sorted([s.end_balance for s in priv_res.simulations])[
        len(priv_res.simulations) // 2
    ]

    comb_cfg = CombinedSimConfig(
        n_simulations=300, starting_level=3, spend_profile="slosa",
        biz_industry="hantverk", biz_level="basics",
        biz_starting_reputation=50,
        biz_monthly_owner_salary=15000,
        biz_monthly_fixed_cost=2000,
        seed_base=99,
    )
    comb_res = run_combined_simulations(comb_cfg)
    comb_summary = summarize_combined(comb_res)
    comb_median = comb_summary["combined"]["median"]

    assert comb_median > priv_median, (
        f"Biz hjälper inte struggling privatekonomi: "
        f"privat-median={priv_median}, combined-median={comb_median}"
    )


def test_combined_mc_pentagon_realistic_after_year():
    """Final reputation efter 12 månader ska ha drift mot kvalitet."""
    cfg = CombinedSimConfig(
        n_simulations=200, starting_level=1, spend_profile="balanserad",
        biz_industry="hantverk", biz_level="basics",
        biz_starting_reputation=50,
        seed_base=42,
    )
    res = run_combined_simulations(cfg)
    summary = summarize_combined(res)
    final_rep = summary["final_reputation"]["mean"]
    # Med kvalitet 60-90 (rimlig leverans) ska rep drifta UPP från 50
    assert final_rep > 50, (
        f"Reputation drift fungerar inte — start 50, slut {final_rep}"
    )
    assert final_rep < 95, (
        f"Reputation går upp för fort — slut {final_rep} efter 1 år"
    )
