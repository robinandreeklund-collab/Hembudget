"""Monte Carlo · in-memory simulator.

Kör N simuleringar utan DB-overhead för att verifiera att spelmotorns
ekonomi balanserar realistiskt över olika konfigurationer.

Per simulering:
1. Generera profil med deterministisk seed
2. Simulera 12 spelmånader genom att RÄKNA (inte skriva till DB):
   - Inkomst: nettolön × 12
   - Fast: profile.housing.monthly_cost × 12
   - Variabel: Konsumentverket-baseline × spend_profile-multiplikator × 12
   - Sjuk/VAB: förväntat lönebortfall (statistiskt)
   - Events: sample från event_engine för att få kostnadsfördelning
3. Räkna ut end-of-year-balans + förväntat pentagon-totalt
4. Klassa som positive / marginal / negative

Returnerar MCResult med statistik (median, mean, percentiler).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from statistics import mean, median, stdev
from typing import Optional

from ..difficulty import get_difficulty
from ..event_engine.templates import EVENT_TEMPLATES
from ..health_engine.roller import (
    P_LONG_SICK,
    P_SICK_PER_MONTH_BASELINE,
    P_VAB_PER_CHILD_PER_MONTH,
    SEASON_MULT,
    SICK_DAYS_RANGE,
    VAB_DAYS_RANGE,
    VAB_SEASON_MULT,
    apply_sick_pay_reduction,
)
from ..pools.stadspool import STAD_BY_KEY
from ..profile_generator import generate_profile
from ..profile_generator.schema import GeneratedProfile


SPEND_MULTIPLIER = {
    "sparsam": 0.85,
    "balanserad": 1.00,
    "slosa": 1.25,
}


@dataclass
class SimConfig:
    """Konfiguration för en Monte Carlo-körning."""
    n_simulations: int = 1000
    n_months: int = 12
    starting_level: int = 1
    spend_profile: str = "sparsam"
    archetype: str = "random"
    partner_model: str = "solo"
    seed_base: int = 0


@dataclass
class MCSimulation:
    """En enskild simulering."""
    seed: int
    yrke_key: str
    city_key: str
    family_status: str
    annual_gross: int
    annual_net: int
    annual_housing_cost: int
    annual_variable_cost: int
    annual_sick_loss: int
    annual_event_cost: int
    annual_event_income: int
    end_balance: int           # netto - alla utgifter + bonus
    pentagon_initial_total: int
    classification: str        # "positive" | "marginal" | "negative"


@dataclass
class MCResult:
    """Aggregerade resultat från en MC-körning."""
    config: SimConfig
    simulations: list[MCSimulation] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.simulations)

    def end_balances(self) -> list[int]:
        return [s.end_balance for s in self.simulations]

    def by_classification(self) -> dict[str, int]:
        out: dict[str, int] = {"positive": 0, "marginal": 0, "negative": 0}
        for s in self.simulations:
            out[s.classification] = out.get(s.classification, 0) + 1
        return out

    def percentile(self, pct: int) -> int:
        if not self.simulations:
            return 0
        vals = sorted(self.end_balances())
        idx = max(0, min(len(vals) - 1, int(len(vals) * pct / 100)))
        return vals[idx]


def _expected_sick_and_vab_loss_for_year(
    profile: GeneratedProfile,
    rng: random.Random,
    *,
    difficulty_level: int = 2,
    n_months: int = 12,
) -> int:
    """Sample sjuk + VAB-bortfall över n månader."""
    diff = get_difficulty(difficulty_level)
    physical = profile.facts.get("physical_demand", 5)
    physical_mult = 0.7 + (physical / 10) * 0.6
    total_loss = 0

    young_kids = [a for a in profile.family.children_ages if a < 12]

    for month in range(1, n_months + 1):
        # Sjuk
        season = SEASON_MULT.get(month, 1.0)
        p = (P_SICK_PER_MONTH_BASELINE * season * physical_mult
             * diff.sick_probability_mult)
        if rng.random() < p:
            long_p = P_LONG_SICK * diff.long_sick_probability_mult
            if rng.random() < long_p:
                n_days = rng.randint(21, 45)
            else:
                n_days = rng.randint(*SICK_DAYS_RANGE)
            loss, _ = apply_sick_pay_reduction(
                monthly_gross=profile.monthly_gross, sick_days=n_days,
            )
            total_loss += loss

        # VAB
        vab_season = VAB_SEASON_MULT.get(month, 1.0)
        for _ in young_kids:
            p_vab = (P_VAB_PER_CHILD_PER_MONTH * vab_season
                     * diff.vab_probability_mult)
            if rng.random() < p_vab:
                n_days = rng.randint(*VAB_DAYS_RANGE)
                loss, _ = apply_sick_pay_reduction(
                    monthly_gross=profile.monthly_gross,
                    sick_days=n_days, is_vab=True,
                )
                total_loss += loss
    return total_loss


def _expected_event_impact_for_year(
    profile: GeneratedProfile,
    rng: random.Random,
    *,
    difficulty_level: int = 2,
    n_months: int = 12,
) -> tuple[int, int]:
    """Sample (cost, income) från event-engine över n månader."""
    diff = get_difficulty(difficulty_level)
    cost = 0
    income = 0
    age = profile.facts.get("age", 30)
    family_status = profile.family.status
    max_per_month = diff.max_events_per_month

    for _ in range(n_months):
        n_triggered = 0
        for tpl in EVENT_TEMPLATES:
            if not tpl.active:
                continue
            if not (tpl.age_range[0] <= age <= tpl.age_range[1]):
                continue
            if tpl.family_status_filter and family_status not in tpl.family_status_filter:
                continue
            chance = (tpl.frequency_per_year / 12.0) * diff.event_frequency_mult
            if rng.random() < chance:
                lo, hi = tpl.cost_range
                if lo == hi == 0:
                    continue
                if lo > hi:
                    lo, hi = hi, lo
                base = rng.randint(lo, hi)
                if base < 0:
                    income += -base
                else:
                    cost += int(base * diff.event_cost_mult)
                n_triggered += 1
                if n_triggered >= max_per_month:
                    break
    return cost, income


def _classify(end_balance: int) -> str:
    if end_balance >= 5_000:
        return "positive"
    if end_balance >= -10_000:
        return "marginal"
    return "negative"


def _simulate_one(config: SimConfig, sim_seed: int) -> Optional[MCSimulation]:
    """Kör en simulering. Returnerar None om profile_generator failar."""
    try:
        profile = generate_profile(
            seed=sim_seed,
            archetype=config.archetype,
            starting_level=config.starting_level,
            partner_model=config.partner_model,
            name="MC",
        )
    except Exception:
        return None

    rng = random.Random(sim_seed * 31)
    diff = get_difficulty(config.starting_level)

    # Inkomst
    annual_net = profile.household_net_monthly * config.n_months
    annual_gross = profile.household_gross_monthly * config.n_months

    # Boende
    annual_housing = profile.housing.monthly_cost * config.n_months

    # Variabel (Konsumentverket × spend_profile × difficulty-extra)
    base_var = (
        2_840 +  # mat
        2_140 +  # individuellt övrigt
        300 +    # förbrukning
        950      # transport
    )
    if profile.family.partner_yrke_key:
        base_var = int(base_var * 1.5)
    base_var += profile.family.children_count * 2_500
    base_spend_mult = SPEND_MULTIPLIER.get(config.spend_profile, 1.0)
    # Amplifiera spreaden runt 1.0 (balanserad)
    if diff.spend_profile_amplifier != 1.0:
        spend_mult = 1.0 + (base_spend_mult - 1.0) * diff.spend_profile_amplifier
    else:
        spend_mult = base_spend_mult
    annual_variable = int(
        base_var * spend_mult * diff.variable_spend_extra_mult
        * config.n_months
    )

    # Sjuk + VAB
    sick_loss = _expected_sick_and_vab_loss_for_year(
        profile, rng,
        difficulty_level=config.starting_level,
        n_months=config.n_months,
    )

    # Events
    event_cost, event_income = _expected_event_impact_for_year(
        profile, rng,
        difficulty_level=config.starting_level,
        n_months=config.n_months,
    )

    # End balance
    end = (
        annual_net
        - annual_housing
        - annual_variable
        - sick_loss
        - event_cost
        + event_income
    )

    pentagon_total = (
        profile.pentagon.economy + profile.pentagon.safety
        + profile.pentagon.health + profile.pentagon.social
        + profile.pentagon.leisure
    )

    return MCSimulation(
        seed=sim_seed,
        yrke_key=profile.yrke_key,
        city_key=profile.city_key,
        family_status=profile.family.status,
        annual_gross=annual_gross,
        annual_net=annual_net,
        annual_housing_cost=annual_housing,
        annual_variable_cost=annual_variable,
        annual_sick_loss=sick_loss,
        annual_event_cost=event_cost,
        annual_event_income=event_income,
        end_balance=end,
        pentagon_initial_total=pentagon_total,
        classification=_classify(end),
    )


def run_simulations(config: SimConfig) -> MCResult:
    """Huvudfunktion · kör N simuleringar och returnerar aggregerat
    resultat."""
    result = MCResult(config=config)
    for i in range(config.n_simulations):
        seed = config.seed_base + i * 7919  # primtals-spridning
        sim = _simulate_one(config, seed)
        if sim is not None:
            result.simulations.append(sim)
    return result


def summarize(result: MCResult) -> dict:
    """Mänsklig sammanfattning av MC-körning."""
    if not result.simulations:
        return {"error": "Inga simuleringar genomförda"}

    balances = result.end_balances()
    cls = result.by_classification()
    total = result.n

    return {
        "config": {
            "n_simulations": result.config.n_simulations,
            "n_months": result.config.n_months,
            "starting_level": result.config.starting_level,
            "spend_profile": result.config.spend_profile,
            "archetype": result.config.archetype,
            "partner_model": result.config.partner_model,
        },
        "n_completed": total,
        "end_balance": {
            "mean": int(mean(balances)),
            "median": int(median(balances)),
            "stdev": int(stdev(balances)) if total > 1 else 0,
            "p10": result.percentile(10),
            "p25": result.percentile(25),
            "p50": result.percentile(50),
            "p75": result.percentile(75),
            "p90": result.percentile(90),
        },
        "classification": {
            "positive": cls.get("positive", 0),
            "marginal": cls.get("marginal", 0),
            "negative": cls.get("negative", 0),
            "positive_pct": round(cls.get("positive", 0) / total * 100, 1),
            "marginal_pct": round(cls.get("marginal", 0) / total * 100, 1),
            "negative_pct": round(cls.get("negative", 0) / total * 100, 1),
        },
    }
