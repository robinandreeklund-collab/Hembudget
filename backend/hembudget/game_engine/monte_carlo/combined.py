"""Monte Carlo · kombinerad privat + företag.

Verifierar att de två motorerna är balanserade när de kör tillsammans.
Specifikt:
- AB-elev: lön från bolaget ramlar in på privat-kontot. Privat-balansen
  ska vara hyfsad EVEN OM eleven inte vinner några jobb (lön från bolaget
  är "garanterad" om bolaget har kassa).
- Enskild firma: ingen lön, men eget uttag. Privat = vinst från biz
  flödar direkt till privat (inget lager).
- Båda: pentagon-balans ska vara realistisk när biz aktiv.

Vi kör N simuleringar och kontrollerar:
1. Privat-balansen är fortfarande inom rimligt spann
2. Biz-balansen är inom rimligt spann
3. KOMBINERAD ekonomi (privat + biz · netto) är inte fundamentalt
   sämre än bara privat (annars är biz en pengasug, inte motivation).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, median, stdev
from typing import Optional

from ...business.engine.monte_carlo import (
    BizMCSimulation, BizSimConfig, _simulate_one_biz,
)
from .runner import (
    MCSimulation, SimConfig, _simulate_one,
)


@dataclass
class CombinedSimConfig:
    """Kör BÅDE privat + biz för samma seed."""
    n_simulations: int = 1000
    n_months: int = 12
    starting_level: int = 1
    spend_profile: str = "balanserad"
    archetype: str = "random"
    partner_model: str = "solo"
    seed_base: int = 0

    # Biz-config
    biz_industry: str = "konsult"
    biz_level: str = "basics"
    biz_starting_reputation: int = 50
    biz_monthly_owner_salary: int = 12000  # AB · 12 000 kr/mån brutto
    biz_monthly_fixed_cost: int = 1500


@dataclass
class CombinedSim:
    """En enskild kombinerad simulering."""
    seed: int
    private: MCSimulation
    biz: BizMCSimulation

    @property
    def combined_balance(self) -> int:
        """Total nettobehållning · privat + biz-kassa + ev. uttag.

        För AB:
        - private.end_balance redan inkluderar lönen (om profile har den)
          MEN! Vår privat-MC genererar lön från PROFILE.salary, inte från
          biz. Så vi LÄGGER TILL biz.owner_salary_total som extra inkomst
          (eftersom privat antar att den fortfarande får lönen).

        Förenklad modell: combined = private_balance + biz_kassa, eftersom
        owner_salary redan flödar internt mellan biz och privat och vi
        räknar "total formuegen" som summan.
        """
        return self.private.end_balance + self.biz.end_kassa


@dataclass
class CombinedResult:
    config: CombinedSimConfig
    simulations: list[CombinedSim] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.simulations)

    def private_balances(self) -> list[int]:
        return [s.private.end_balance for s in self.simulations]

    def biz_balances(self) -> list[int]:
        return [s.biz.end_kassa for s in self.simulations]

    def combined_balances(self) -> list[int]:
        return [s.combined_balance for s in self.simulations]


def run_combined_simulations(
    config: CombinedSimConfig,
) -> CombinedResult:
    """Kör N kombinerade simuleringar (privat + biz för samma seed)."""
    result = CombinedResult(config=config)

    priv_cfg = SimConfig(
        n_simulations=config.n_simulations,
        n_months=config.n_months,
        starting_level=config.starting_level,
        spend_profile=config.spend_profile,
        archetype=config.archetype,
        partner_model=config.partner_model,
        seed_base=config.seed_base,
    )
    biz_cfg = BizSimConfig(
        n_simulations=config.n_simulations,
        n_months=config.n_months,
        industry_label=config.biz_industry,
        level=config.biz_level,
        starting_reputation=config.biz_starting_reputation,
        monthly_owner_salary=config.biz_monthly_owner_salary,
        monthly_fixed_cost=config.biz_monthly_fixed_cost,
        seed_base=config.seed_base,
    )

    for i in range(config.n_simulations):
        seed = config.seed_base + i * 7919
        priv_sim = _simulate_one(priv_cfg, seed)
        biz_sim = _simulate_one_biz(biz_cfg, seed)
        if priv_sim is None or biz_sim is None:
            continue
        result.simulations.append(CombinedSim(
            seed=seed, private=priv_sim, biz=biz_sim,
        ))
    return result


def summarize_combined(result: CombinedResult) -> dict:
    if not result.simulations:
        return {"error": "Inga simuleringar"}
    priv_bal = result.private_balances()
    biz_bal = result.biz_balances()
    comb_bal = result.combined_balances()
    total = result.n

    # Räkna ut hur många simulationer där biz HELT NEUTRALISERAR (eller
    # förvärrar) den privata ekonomin → en VARNING om det är för många
    biz_drag = sum(
        1 for s in result.simulations
        if s.biz.end_kassa < 0
    )
    biz_boost = sum(
        1 for s in result.simulations
        if s.biz.end_kassa > 10_000
    )

    return {
        "config": {
            "n_simulations": result.config.n_simulations,
            "n_months": result.config.n_months,
            "starting_level": result.config.starting_level,
            "spend_profile": result.config.spend_profile,
            "biz_industry": result.config.biz_industry,
            "biz_level": result.config.biz_level,
            "biz_monthly_owner_salary":
                result.config.biz_monthly_owner_salary,
        },
        "n_completed": total,
        "private": {
            "mean_balance": int(mean(priv_bal)),
            "median_balance": int(median(priv_bal)),
            "p10": sorted(priv_bal)[int(len(priv_bal) * 0.10)],
            "p90": sorted(priv_bal)[int(len(priv_bal) * 0.90)],
        },
        "biz": {
            "mean_kassa": int(mean(biz_bal)),
            "median_kassa": int(median(biz_bal)),
            "p10": sorted(biz_bal)[int(len(biz_bal) * 0.10)],
            "p90": sorted(biz_bal)[int(len(biz_bal) * 0.90)],
            "n_with_drag": biz_drag,
            "n_with_boost": biz_boost,
            "drag_pct": round(biz_drag / total * 100, 1),
            "boost_pct": round(biz_boost / total * 100, 1),
        },
        "combined": {
            "mean": int(mean(comb_bal)),
            "median": int(median(comb_bal)),
            "stdev": int(stdev(comb_bal)) if total > 1 else 0,
            "p10": sorted(comb_bal)[int(len(comb_bal) * 0.10)],
            "p25": sorted(comb_bal)[int(len(comb_bal) * 0.25)],
            "p50": sorted(comb_bal)[int(len(comb_bal) * 0.50)],
            "p75": sorted(comb_bal)[int(len(comb_bal) * 0.75)],
            "p90": sorted(comb_bal)[int(len(comb_bal) * 0.90)],
        },
        "biz_revenue": {
            "mean": int(
                mean(s.biz.revenue_total for s in result.simulations),
            ),
            "median": int(
                median(s.biz.revenue_total for s in result.simulations),
            ),
        },
        "biz_won_jobs": {
            "mean": round(
                mean(s.biz.n_quotes_won for s in result.simulations), 1,
            ),
            "median": median(
                [s.biz.n_quotes_won for s in result.simulations],
            ),
        },
        "final_reputation": {
            "mean": int(
                mean(s.biz.final_reputation for s in result.simulations),
            ),
            "median": median(
                [s.biz.final_reputation for s in result.simulations],
            ),
        },
    }
