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
    # Bokföring + bank + mobil + ansvarsförsäkring · ALLA bolag har dessa
    monthly_fixed_cost: int = 1500
    seed_base: int = 0


# === Industry-specific kostnadsratio + overhead ===
#
# MATERIAL_COST_RATIO: hur stor del av revenue som går till material/inköp.
#   Eleven ser detta som "kost-of-goods-sold" (KGS).
# MONTHLY_OVERHEAD: extra fasta kostnader specifika för branschen
#   (lokal för cafe/hantverk, leasing-bil för hantverk, etc.).
#
# Hämtat från SCB-statistik + Skatteverkets bransch-snitt 2024.

INDUSTRY_COST_PROFILE: dict[str, dict] = {
    "hantverk": {
        "material_ratio": 0.35,
        "monthly_overhead": 7500,
        # Pipeline-multiplikator · branscher med många små jobb (cafe)
        # behöver mer pipeline för att fånga verkligheten.
        "pipeline_mult": 1.0,
    },
    "it": {
        "material_ratio": 0.18,
        "monthly_overhead": 2200,
        "pipeline_mult": 1.0,
    },
    "cafe": {
        # Cafe har VOLYM (catering-beställningar 1-3/v) + lite lokala jobb.
        # Verklig cafe omsätter på 100+ kunder/dag — vi modellerar bara
        # storjobb (catering, bröllopstårtor). Höjd pipeline kompenserar.
        "material_ratio": 0.40,
        "monthly_overhead": 4500,
        "pipeline_mult": 2.5,
    },
    "konsult": {
        "material_ratio": 0.22,
        "monthly_overhead": 2500,
        "pipeline_mult": 1.0,
    },
    "kreativ": {
        "material_ratio": 0.28,
        "monthly_overhead": 2500,
        "pipeline_mult": 1.1,
    },
    "ehandel": {
        # E-handel har också volym
        "material_ratio": 0.50,
        "monthly_overhead": 3500,
        "pipeline_mult": 2.0,
    },
}

DEFAULT_COST_PROFILE = {
    "material_ratio": 0.25, "monthly_overhead": 2500, "pipeline_mult": 1.0,
}


def _industry_costs(industry_label: str) -> dict:
    if industry_label is None:
        return DEFAULT_COST_PROFILE
    key = industry_label.lower().replace(" ", "-").replace(
        "ä", "a",
    ).replace("ö", "o").replace("å", "a")
    if key in INDUSTRY_COST_PROFILE:
        return INDUSTRY_COST_PROFILE[key]
    head = key.split("-")[0]
    return INDUSTRY_COST_PROFILE.get(head, DEFAULT_COST_PROFILE)


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
    industry_costs = _industry_costs(config.industry_label)

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

    # Engångs-startkostnader · realistiska för småföretag år 1
    # Bolagsregistrering, bokföringsprogram-uppsättning, verktyg,
    # hemsida, visitkort, första försäkring m.m.
    if config.level == "basics":
        # Lärling — ofta missar man hidden costs. Slumpmässig 25-50k.
        startup_cost = rng.randint(25_000, 50_000)
    else:
        # Advanced har mer erfarenhet → effektivare uppstart.
        startup_cost = rng.randint(15_000, 35_000)
    cost += startup_cost

    n_weeks = config.n_months * 4

    # Lärlings-effekt · första 8 veckorna har eleven sämre offerter
    # (mindre erfarenhet av prissättning + leverans-uppskattning).
    LEARNING_WEEKS = 8

    # Pipeline-throttle för MC-realism. Verkligheten: en småföretagare
    # får ca 12-30 offerter/år (1-3/månad), inte 100+.
    # Basics (skol-grundnivå) får MINDRE pipeline (svårt att etablera).
    # Advanced får MER pipeline (eleven har lärt sig + mer komplexa jobb).
    if config.level == "basics":
        PIPELINE_REALISM_FACTOR = 0.40
    else:
        PIPELINE_REALISM_FACTOR = 0.60
    # Bransch-multiplikator (cafe + ehandel har volym)
    PIPELINE_REALISM_FACTOR *= industry_costs.get("pipeline_mult", 1.0)

    for week_no in range(1, n_weeks + 1):
        is_learning = week_no <= LEARNING_WEEKS
        # --- Pipeline · antal nya offerter denna vecka ---
        # KALIBRERAT: under learning är pipelinen halverad,
        # och vi multiplicerar med realism-faktor.
        base_raw = profile.base_opportunities_per_week
        if is_learning:
            base_raw = max(1, base_raw - 1)
        base = max(0, int(round(base_raw * PIPELINE_REALISM_FACTOR + 0.001)))
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

            # Eleven lämnar offert · realistisk fördelning kring riktpris.
            # Verkligheten: nybörjare överprisar oftare än underprisar
            # (svårt att veta sitt värde). Snittet är ~1.05-1.10 av riktpris.
            # Under learning-fasen är spreaden bredare (mer fel-prissättning).
            if is_learning:
                offered_price = int(mp * rng.gauss(1.10, 0.15))
                offered_days = int(tmpl.delivery_days * rng.gauss(1.25, 0.20))
                pitch_quality = max(0.15, min(0.7, rng.gauss(0.40, 0.15)))
            else:
                offered_price = int(mp * rng.gauss(1.05, 0.10))
                offered_days = int(tmpl.delivery_days * rng.gauss(1.15, 0.15))
                pitch_quality = max(0.2, min(0.85, rng.gauss(0.55, 0.15)))
            offered_price = max(int(mp * 0.7), offered_price)
            offered_days = max(1, offered_days)

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
                # Eleven levererar (90% chans inom denna 12-mån sim).
                # Nybörjare missar oftare deadline → 80% under learning.
                deliver_chance = 0.8 if is_learning else 0.92
                if rng.random() < deliver_chance:
                    # Kvalitet · nybörjare har lägre snitt + bredare spread
                    if is_learning:
                        quality = max(30, min(95, int(rng.gauss(58, 18))))
                    else:
                        quality = max(40, min(95, int(rng.gauss(72, 12))))
                    avg_quality = (
                        quality if avg_quality is None
                        else int(round(
                            avg_quality + (quality - avg_quality) * 0.3,
                        ))
                    )
                    # Reputation drift mot kvalitet (15% per leverans).
                    # Låg kvalitet skapar klagomål → ytterligare drag.
                    reputation = max(
                        0, min(100,
                               reputation + int((quality - reputation) * 0.15)),
                    )
                    if quality < 50:
                        open_complaints += 1
                        reputation = max(0, reputation - 5)
                    # Kunden betalar enligt payment_morality.
                    # Nybörjare har sämre kund-screening → reducerad rate.
                    effective_morality = (
                        float(cust.payment_morality)
                        * (0.75 if is_learning else 0.92)
                    )
                    if rng.random() < effective_morality:
                        revenue += offered_price
                # else: levererat sent → inga pengar (eller halva)
            else:
                n_lost += 1

        # --- Månadsvis · löpande kostnader + lön (varje 4:e vecka) ---
        if week_no % 4 == 0:
            cost += config.monthly_fixed_cost
            # Bransch-specifik overhead (lokal, leasing, etc.)
            cost += industry_costs["monthly_overhead"]
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

        # --- Slumpevents · realistiskt antal per år ---
        # Verklighet: ett småföretag har 4-12 oväntade händelser/år
        # (sjuk, datorhaveri, miljöskatt, kundklagomål etc.).
        # Difficulty-profilen säger 0.4 prob × 2 max → 38 events/år
        # vilket är ALLTFÖR mycket. Kalibrerar i MC:
        if profile.event_probability_per_week > 0:
            # Advanced: ~10 events/år (1 var 5:e vecka)
            mc_event_prob = 0.20
            if rng.random() < mc_event_prob:
                cost += rng.choice([2500, 4500, 8500, 12000])
        else:
            # Basics: ~5 events/år (mildare)
            basics_event_prob = 0.10
            if rng.random() < basics_event_prob:
                cost += rng.choice([800, 1500, 2500, 4000])

    # === Material-kostnad (KGS) ===
    # Bransch-specifik andel av revenue. Advanced har MER komplexa jobb
    # → större material-andel + längre lead-times.
    material_ratio = industry_costs["material_ratio"]
    if config.level == "advanced":
        material_ratio = min(0.65, material_ratio + 0.07)
    material_cost = int(revenue * material_ratio)
    cost += material_cost
    # Ingående moms (drag av) på material — 25% av material-kostnaden
    input_vat_credit = int(material_cost * 0.25)

    # === Skatt + moms-justering ===
    # Utgående moms 25% på revenue, ingående moms-avdrag på material.
    output_vat = int(revenue * 0.25)
    vat_owed = max(0, output_vat - input_vat_credit)
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
