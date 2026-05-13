"""Stadspool · 14 svenska städer/orter med 2026-data.

Källor:
- SCB befolkningsstatistik 2024
- Hyresgästföreningen Bostadsbarometern 2024 (uppjusterad ~3 % för 2026)
- Svensk Mäklarstatistik / Booli BRF-snitt 2024 (uppjusterad)
- Konsumentverkets prisstatistik per region 2024
- SCB Regionala räkenskaper (sysselsättning per region)

Multiplikatorerna är relativa till **rikssnitt = 1.00**. Genom att
multiplicera en bas-kostnad (t.ex. matkonto 4 200 kr för singel) med
`cost_multiplier_food` får vi den stad-justerade kostnaden.

`bostad_pct_*` är hushållssnitt och summerar till ~1.0 (avvikelser kan
finnas pga andelar bo i andrahand etc).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal


City = Literal[
    "stockholm", "goteborg", "malmo", "uppsala", "linkoping", "orebro",
    "vasteras", "norrkoping", "gavle", "sundsvall", "umea", "lulea",
    "medelstad", "smaort",
]

Region = Literal[
    "Stockholm", "Västsverige", "Sydsverige",
    "Östra Mellansverige", "Norra Mellansverige",
    "Mellersta Norrland", "Övre Norrland",
]


@dataclass
class Stad:
    """En svensk stad/ort med boende- och kostnadsdata för 2026."""

    key: City
    display: str
    region: Region
    population: int

    # === KOSTNADSMULTIPLIKATORER (rikssnitt = 1.00) ===
    cost_multiplier_housing: float    # hyra + driftkostnad
    cost_multiplier_food: float       # mat & livsmedel
    cost_multiplier_transport: float  # SL-kort, bensin, parkering

    # === ARBETSMARKNAD ===
    job_density: float                # 1.0 = riksgenomsnitt jobbtillgång

    # === BOENDEFÖRDELNING (andel hushåll, summerar till ~1.0) ===
    bostad_pct_brf: float
    bostad_pct_villa: float
    bostad_pct_hyresratt: float

    # === PRISDATA 2026 ===
    avg_brf_price_per_kvm: int        # SEK/kvm köp
    avg_villa_price_per_kvm: int      # SEK/kvm köp
    avg_rental_per_kvm_month: int     # SEK/kvm/mån hyresrätt

    # === VAL-VIKT ===
    weight: float                     # sannolikhet att profil hamnar här


# === POOL ===

STADSPOOL: list[Stad] = [
    # --- STORSTÄDER ---
    Stad(
        key="stockholm",
        display="Stockholm",
        region="Stockholm",
        population=990_000,
        cost_multiplier_housing=1.30,
        cost_multiplier_food=1.05,
        cost_multiplier_transport=1.15,
        job_density=1.5,
        bostad_pct_brf=0.55,
        bostad_pct_villa=0.05,
        bostad_pct_hyresratt=0.40,
        avg_brf_price_per_kvm=100_000,
        avg_villa_price_per_kvm=82_000,
        avg_rental_per_kvm_month=155,
        weight=1.5,
    ),
    Stad(
        key="goteborg",
        display="Göteborg",
        region="Västsverige",
        population=600_000,
        cost_multiplier_housing=1.15,
        cost_multiplier_food=1.02,
        cost_multiplier_transport=1.08,
        job_density=1.3,
        bostad_pct_brf=0.40,
        bostad_pct_villa=0.15,
        bostad_pct_hyresratt=0.45,
        avg_brf_price_per_kvm=65_000,
        avg_villa_price_per_kvm=58_000,
        avg_rental_per_kvm_month=135,
        weight=1.2,
    ),
    Stad(
        key="malmo",
        display="Malmö",
        region="Sydsverige",
        population=360_000,
        cost_multiplier_housing=1.05,
        cost_multiplier_food=1.00,
        cost_multiplier_transport=1.05,
        job_density=1.2,
        bostad_pct_brf=0.35,
        bostad_pct_villa=0.10,
        bostad_pct_hyresratt=0.55,
        avg_brf_price_per_kvm=48_000,
        avg_villa_price_per_kvm=50_000,
        avg_rental_per_kvm_month=130,
        weight=1.0,
    ),

    # --- STÖRRE STÄDER ---
    Stad(
        key="uppsala",
        display="Uppsala",
        region="Östra Mellansverige",
        population=240_000,
        cost_multiplier_housing=1.10,
        cost_multiplier_food=1.00,
        cost_multiplier_transport=1.00,
        job_density=1.1,
        bostad_pct_brf=0.35,
        bostad_pct_villa=0.15,
        bostad_pct_hyresratt=0.50,
        avg_brf_price_per_kvm=58_000,
        avg_villa_price_per_kvm=52_000,
        avg_rental_per_kvm_month=140,
        weight=0.8,
    ),
    Stad(
        key="linkoping",
        display="Linköping",
        region="Östra Mellansverige",
        population=165_000,
        cost_multiplier_housing=0.95,
        cost_multiplier_food=0.98,
        cost_multiplier_transport=0.95,
        job_density=1.0,
        bostad_pct_brf=0.25,
        bostad_pct_villa=0.25,
        bostad_pct_hyresratt=0.50,
        avg_brf_price_per_kvm=40_000,
        avg_villa_price_per_kvm=36_000,
        avg_rental_per_kvm_month=120,
        weight=0.7,
    ),
    Stad(
        key="orebro",
        display="Örebro",
        region="Östra Mellansverige",
        population=160_000,
        cost_multiplier_housing=0.92,
        cost_multiplier_food=0.97,
        cost_multiplier_transport=0.95,
        job_density=0.95,
        bostad_pct_brf=0.25,
        bostad_pct_villa=0.25,
        bostad_pct_hyresratt=0.50,
        avg_brf_price_per_kvm=35_000,
        avg_villa_price_per_kvm=31_000,
        avg_rental_per_kvm_month=115,
        weight=0.7,
    ),
    Stad(
        key="vasteras",
        display="Västerås",
        region="Östra Mellansverige",
        population=160_000,
        cost_multiplier_housing=0.93,
        cost_multiplier_food=0.97,
        cost_multiplier_transport=0.95,
        job_density=0.95,
        bostad_pct_brf=0.25,
        bostad_pct_villa=0.25,
        bostad_pct_hyresratt=0.50,
        avg_brf_price_per_kvm=33_000,
        avg_villa_price_per_kvm=30_000,
        avg_rental_per_kvm_month=115,
        weight=0.7,
    ),
    Stad(
        key="norrkoping",
        display="Norrköping",
        region="Östra Mellansverige",
        population=145_000,
        cost_multiplier_housing=0.90,
        cost_multiplier_food=0.97,
        cost_multiplier_transport=0.93,
        job_density=0.90,
        bostad_pct_brf=0.20,
        bostad_pct_villa=0.25,
        bostad_pct_hyresratt=0.55,
        avg_brf_price_per_kvm=30_000,
        avg_villa_price_per_kvm=27_000,
        avg_rental_per_kvm_month=110,
        weight=0.6,
    ),

    # --- MEDELSTORA STÄDER ---
    Stad(
        key="gavle",
        display="Gävle",
        region="Norra Mellansverige",
        population=105_000,
        cost_multiplier_housing=0.88,
        cost_multiplier_food=0.96,
        cost_multiplier_transport=0.92,
        job_density=0.85,
        bostad_pct_brf=0.20,
        bostad_pct_villa=0.30,
        bostad_pct_hyresratt=0.50,
        avg_brf_price_per_kvm=28_000,
        avg_villa_price_per_kvm=24_000,
        avg_rental_per_kvm_month=105,
        weight=0.5,
    ),
    Stad(
        key="sundsvall",
        display="Sundsvall",
        region="Mellersta Norrland",
        population=100_000,
        cost_multiplier_housing=0.87,
        cost_multiplier_food=0.97,
        cost_multiplier_transport=0.93,
        job_density=0.85,
        bostad_pct_brf=0.20,
        bostad_pct_villa=0.30,
        bostad_pct_hyresratt=0.50,
        avg_brf_price_per_kvm=26_000,
        avg_villa_price_per_kvm=23_000,
        avg_rental_per_kvm_month=105,
        weight=0.4,
    ),
    Stad(
        key="umea",
        display="Umeå",
        region="Övre Norrland",
        population=130_000,
        cost_multiplier_housing=0.95,
        cost_multiplier_food=1.00,
        cost_multiplier_transport=0.95,
        job_density=0.95,
        bostad_pct_brf=0.30,
        bostad_pct_villa=0.20,
        bostad_pct_hyresratt=0.50,
        avg_brf_price_per_kvm=36_000,
        avg_villa_price_per_kvm=28_000,
        avg_rental_per_kvm_month=120,
        weight=0.5,
    ),
    Stad(
        key="lulea",
        display="Luleå",
        region="Övre Norrland",
        population=80_000,
        cost_multiplier_housing=0.88,
        cost_multiplier_food=1.00,
        cost_multiplier_transport=0.95,
        job_density=0.85,
        bostad_pct_brf=0.25,
        bostad_pct_villa=0.30,
        bostad_pct_hyresratt=0.45,
        avg_brf_price_per_kvm=28_000,
        avg_villa_price_per_kvm=24_000,
        avg_rental_per_kvm_month=110,
        weight=0.4,
    ),

    # --- GENERISK MEDELSTAD ---
    # Representerar svenska kommuncentra ~30-70k inv. utan storstadspendel.
    Stad(
        key="medelstad",
        display="Medelstor stad",
        region="Östra Mellansverige",
        population=50_000,
        cost_multiplier_housing=0.80,
        cost_multiplier_food=0.95,
        cost_multiplier_transport=0.90,
        job_density=0.75,
        bostad_pct_brf=0.15,
        bostad_pct_villa=0.40,
        bostad_pct_hyresratt=0.45,
        avg_brf_price_per_kvm=25_000,
        avg_villa_price_per_kvm=20_000,
        avg_rental_per_kvm_month=100,
        weight=1.0,
    ),

    # --- GENERISK SMÅORT ---
    # Representerar mindre orter <15k inv. där villa dominerar.
    Stad(
        key="smaort",
        display="Mindre ort",
        region="Norra Mellansverige",
        population=8_000,
        cost_multiplier_housing=0.65,
        cost_multiplier_food=0.95,
        cost_multiplier_transport=1.10,  # bil oftast nödvändig
        job_density=0.55,
        bostad_pct_brf=0.05,
        bostad_pct_villa=0.65,
        bostad_pct_hyresratt=0.30,
        avg_brf_price_per_kvm=18_000,
        avg_villa_price_per_kvm=15_000,
        avg_rental_per_kvm_month=85,
        weight=0.5,
    ),
]


# === LOOKUP-INDEX ===

STAD_BY_KEY: dict[str, Stad] = {s.key: s for s in STADSPOOL}


# === HJÄLPFUNKTIONER ===


def pick_city_weighted(
    rng: random.Random,
    city_preference: list[str] | None = None,
) -> Stad:
    """Returnerar en stad viktad efter `weight` (+ ev. preference-filter).

    - Om `city_preference` ges: filtrera till matchande städer först.
      Om filtret blir tomt, fallback till hela poolen.
    - Vikt: städernas `weight` × 1.0, eller × 1.5 om staden finns i
      `city_preference` (mjuk preferens snarare än hård).
    """
    if not city_preference:
        return rng.choices(
            STADSPOOL,
            weights=[s.weight for s in STADSPOOL],
            k=1,
        )[0]

    pref_set = set(city_preference)
    weights = [
        s.weight * (1.5 if s.key in pref_set else 1.0)
        for s in STADSPOOL
    ]
    return rng.choices(STADSPOOL, weights=weights, k=1)[0]


def pick_city_by_region(
    rng: random.Random,
    region: Region,
) -> Stad:
    """Slumpar en stad inom en specifik region (vägt efter `weight`)."""
    matching = [s for s in STADSPOOL if s.region == region]
    if not matching:
        return pick_city_weighted(rng)
    return rng.choices(
        matching,
        weights=[s.weight for s in matching],
        k=1,
    )[0]
