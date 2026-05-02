"""Monte Carlo · företagsmotorn (in-memory).

Spec: deb/README.md avsnitt 12 ("Determinism för rättvisa") +
analog med game_engine/monte_carlo för privatmotorn.

Kör N simuleringar utan DB-overhead för att verifiera att biz-
spelmotorn ger realistiska utfall över olika konfigurationer.

Per simulering (12 spelmånader = 48 biz-veckor):
1. Generera profil → biz-bransch + svårighetsnivå
2. För varje vecka:
   - Pipeline-engine: hur många nya offerter dyker upp
   - Acceptance-model: P(accept) för veckans offerter
   - För accepterade: revenue (agreed_price * vat_factor)
   - Subtrahera: löpande kostnader (decisions × monthly), random events
3. Räkna ut end-of-year-balans (biz-kassan + uttagen lön)
4. Klassa som positive / marginal / negative

Determinism: seed = (config.seed_base + i * 7919). Samma seed → samma
utfall (kan re-spelas av läraren).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from statistics import mean, median, stdev
from typing import Optional

from ..engine.difficulty import get_biz_difficulty
from ..engine.seed_data import industry_pool
from ..engine.pricing import market_price_for


# === Vikter (matchar engine/acceptance_model.py) ===
W_PRICE = 4.5
W_REPUTATION = 0.025
W_PITCH = 1.5
W_DELAY = 1.2


@dataclass
class BizSimConfig:
    n_simulations: int = 1000
    n_months: int = 12  # 12 spelmånader = 48 biz-veckor
    industry_label: str = "hantverk"
    level: str = "basics"  # basics | advanced
    starting_reputation: int = 50
    monthly_owner_salary: int = 0  # AB · 0 = inget uttag
    monthly_fixed_cost: int = 1500  # licens, lokal-del, försäkring
    seed_base: int = 0


@dataclass
class BizMCSimulation:
    seed: int
    industry: str
    level: str
    n_opportunities_total: int
    n_quotes_won: int
    n_quotes_lost: int
    revenue_total: int
    cost_total: int
    owner_salary_total: int
    end_kassa: int            # bolagets kassa efter 12 mån
    final_reputation: int
    classification: str       # positive | marginal | negative


@dataclass
class BizMCResult:
    config: BizSimConfig
    simulations: list[BizMCSimulation] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.simulations)

    def end_balances(self) -> list[int]:
        return [s.end_kassa for s in self.simulations]

    def by_classification(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.simulations:
            out[s.classification] = out.get(s.classification, 0) + 1
        return out

    def percentile(self, p: int) -> int:
        if not self.simulations:
            return 0
        sorted_b = sorted(self.end_balances())
        idx = int(len(sorted_b) * p / 100)
        idx = max(0, min(len(sorted_b) - 1, idx))
        return sorted_b[idx]


def _sigmoid(x: float) -> float:
    if x > 50:
        return 1.0
    if x < -50:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def _simulate_quote_decision(
    *, market_price: int, offered_price: int,
    reputation: int, pitch_quality: float,
    expected_days: int, offered_days: int,
    customer_price_sensitivity: float,
    customer_quality_sensitivity: float,
    rng: random.Random,
) -> bool:
    """Återimplementation av acceptance_model i in-memory-form."""
    price_diff_ratio = (
        (market_price - offered_price) / max(market_price, 1)
    )
    price_term = (
        W_PRICE * price_diff_ratio
        * (0.5 + customer_price_sensitivity)
    )
    rep_term = W_REPUTATION * (reputation - 50)
    pitch_term = (
        W_PITCH * (pitch_quality - 0.5)
        * (0.5 + customer_quality_sensitivity)
    )
    delay_ratio = max(
        0.0,
        (offered_days - expected_days) / max(expected_days, 1),
    )
    delay_term = -W_DELAY * delay_ratio
    p = _sigmoid(price_term + rep_term + pitch_term + delay_term)
    return rng.random() < p


def _classify_biz(end_kassa: int, n_won: int) -> str:
    """Företaget gick bra, hyfsat eller dåligt över 12 månader."""
    # En bolag som inte vunnit ett enda jobb är "negative" oavsett kassa
    if n_won == 0:
        return "negative"
    if end_kassa >= 20_000:
        return "positive"
    if end_kassa >= 0:
        return "marginal"
    return "negative"


def _simulate_one_biz(
    config: BizSimConfig, sim_seed: int,
) -> BizMCSimulation:
    """Kör 1 simulering (12 månader = 48 veckor)."""
    rng = random.Random(sim_seed * 31)
    profile = get_biz_difficulty(config.level)
    customers, jobs = industry_pool(config.industry_label)

    reputation = config.starting_reputation
    avg_quality: Optional[int] = None
    open_complaints = 0
    in_progress = 0
    delivery_capacity = 1

    n_opps_total = 0
    n_won = 0
    n_lost = 0
    revenue = 0
    cost = 0
    owner_salary_paid = 0

    n_weeks = config.n_months * 4

    for week_no in range(1, n_weeks + 1):
        # --- Pipeline · antal nya offerter denna vecka ---
        base = profile.base_opportunities_per_week
        rep_bonus = (
            2 if reputation >= 80
            else 1 if reputation >= 60
            else -1 if reputation <= 30
            else 0
        )
        quality_bonus = (
            1 if avg_quality and avg_quality >= 80
            else -1 if avg_quality and avg_quality <= 40
            else 0
        )
        complaint_penalty = min(2, open_complaints)
        free_slots = max(0, delivery_capacity - in_progress)
        capacity_factor = (
            0.4 if free_slots == 0
            else 0.7 if free_slots == 1
            else 1.0
        )
        raw = base + rep_bonus + quality_bonus - complaint_penalty
        raw = max(0, int(round(raw * capacity_factor)))
        variance = rng.choice([-1, 0, 0, 1])
        n_new = max(0, raw + variance)
        n_opps_total += n_new

        # --- För varje offert: simulera offerten + acceptans ---
        for _ in range(n_new):
            cust = rng.choice(customers)
            tmpl = rng.choice(jobs)
            mp = market_price_for(tmpl, cust)
            # Slumpa volatilitet ±X% av mp
            vol = profile.market_price_volatility
            adj = 1.0 + rng.uniform(-vol, vol)
            mp = max(500, int(round(mp * adj / 100) * 100))

            # Eleven lämnar offer · realistisk spread runt riktpriset.
            # Många offerter blir för dyra (eleven optimerar inte alltid).
            offered_price = int(mp * rng.uniform(0.92, 1.18))
            offered_days = int(tmpl.delivery_days * rng.uniform(0.95, 1.4))
            # Pitch-kvalitet · normalt-fördelad runt 0.5 (medel)
            pitch_quality = max(0.2, min(0.85, rng.gauss(0.5, 0.15)))

            accepted = _simulate_quote_decision(
                market_price=mp,
                offered_price=offered_price,
                reputation=reputation,
                pitch_quality=pitch_quality,
                expected_days=tmpl.delivery_days,
                offered_days=offered_days,
                customer_price_sensitivity=(
                    cust.price_sensitivity
                    * profile.customer_price_pressure_mult
                ),
                customer_quality_sensitivity=cust.quality_sensitivity,
                rng=rng,
            )

            if accepted:
                n_won += 1
                # Eleven levererar (90% chans inom denna 12-mån sim)
                if rng.random() < 0.9:
                    # Kvalitet 60-90 (rimligt simulering-spann)
                    quality = rng.randint(60, 90)
                    avg_quality = (
                        quality if avg_quality is None
                        else int(round(
                            avg_quality + (quality - avg_quality) * 0.3,
                        ))
                    )
                    # Reputation drift mot kvalitet (15% per leverans)
                    reputation = max(
                        0, min(100,
                               reputation + int((quality - reputation) * 0.15)),
                    )
                    # Kunden betalar enligt payment_morality
                    if rng.random() < float(cust.payment_morality):
                        revenue += offered_price
            else:
                n_lost += 1

        # --- Månadsvis · löpande kostnader + lön (varje 4:e vecka) ---
        if week_no % 4 == 0:
            cost += config.monthly_fixed_cost
            if config.monthly_owner_salary > 0:
                # Inkl. arbetsgivaravgift 31.42% (förenklad)
                total_payroll = int(
                    config.monthly_owner_salary * 1.3142,
                )
                cost += total_payroll
                # Ägaren får net ~ gross × 0.7 (efter A-skatt 30%)
                owner_salary_paid += int(
                    config.monthly_owner_salary * 0.7,
                )

        # --- Slumpevents · advanced mode bara ---
        if profile.event_probability_per_week > 0:
            for _ in range(profile.max_events_per_week):
                if rng.random() < profile.event_probability_per_week:
                    cost += rng.choice([2500, 4500, 8500, 12000, 18000])

    # === Skatt + moms-justering ===
    # Eleven offererar pris EXKL moms och får INTE momsen — den är
    # skuld till SKV (25 % på revenue).
    vat_owed = int(revenue * 0.20)  # ~20 % netto efter ingående-moms-avdrag
    cost += vat_owed

    # Bolagsskatt 20.6 % på vinsten (förenklat — bara om vinst > 0)
    profit_before_tax = revenue - cost - owner_salary_paid
    if profit_before_tax > 0:
        corporate_tax = int(profit_before_tax * 0.206)
        cost += corporate_tax

    end_kassa = revenue - cost - owner_salary_paid
    return BizMCSimulation(
        seed=sim_seed,
        industry=config.industry_label,
        level=config.level,
        n_opportunities_total=n_opps_total,
        n_quotes_won=n_won,
        n_quotes_lost=n_lost,
        revenue_total=revenue,
        cost_total=cost,
        owner_salary_total=owner_salary_paid,
        end_kassa=end_kassa,
        final_reputation=reputation,
        classification=_classify_biz(end_kassa, n_won),
    )


def run_biz_simulations(config: BizSimConfig) -> BizMCResult:
    """Huvudfunktion · kör N biz-simuleringar."""
    result = BizMCResult(config=config)
    for i in range(config.n_simulations):
        seed = config.seed_base + i * 7919
        sim = _simulate_one_biz(config, seed)
        result.simulations.append(sim)
    return result


def summarize_biz(result: BizMCResult) -> dict:
    if not result.simulations:
        return {"error": "Inga simuleringar"}
    bal = result.end_balances()
    cls = result.by_classification()
    total = result.n
    return {
        "config": {
            "n_simulations": result.config.n_simulations,
            "n_months": result.config.n_months,
            "industry": result.config.industry_label,
            "level": result.config.level,
            "starting_reputation": result.config.starting_reputation,
            "monthly_owner_salary": result.config.monthly_owner_salary,
            "monthly_fixed_cost": result.config.monthly_fixed_cost,
        },
        "n_completed": total,
        "kassa_end_year": {
            "mean": int(mean(bal)),
            "median": int(median(bal)),
            "stdev": int(stdev(bal)) if total > 1 else 0,
            "p10": result.percentile(10),
            "p25": result.percentile(25),
            "p50": result.percentile(50),
            "p75": result.percentile(75),
            "p90": result.percentile(90),
        },
        "quotes": {
            "avg_won_per_sim": round(
                mean(s.n_quotes_won for s in result.simulations), 1,
            ),
            "avg_lost_per_sim": round(
                mean(s.n_quotes_lost for s in result.simulations), 1,
            ),
            "avg_revenue": int(
                mean(s.revenue_total for s in result.simulations),
            ),
        },
        "reputation_end": {
            "mean": int(
                mean(s.final_reputation for s in result.simulations),
            ),
            "median": int(
                median(s.final_reputation for s in result.simulations),
            ),
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
