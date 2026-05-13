"""Rental listings · 4 tiers från korridorrum till lyx-lägenhet.

Spec: Boendemarknad-utbyggnad (Fas 3 · klasskompis-anställning &
ekonomi-progression). Speglar `listings.py`-mönstret men för
hyresrätter istället för köp.

Listings genereras on-demand som en Python-pool — deterministisk
seed på (city_key, year_month) så samma elev som öppnar marknaden
samma sim-månad ser samma utbud. Inga DB-rader behövs eftersom
listings inte är persistent state — när eleven flyttar in
uppdateras `ActiveHome` direkt.

4 tiers:
  Tier 1 · korridor/akut       12-18 kvm, 1 rok, 3500-5000 kr/mån
  Tier 2 · liten lägenhet      25-45 kvm, 1-2 rok, 5500-8500 kr/mån
  Tier 3 · familjelägenhet     50-85 kvm, 2-3 rok, 9000-13000 kr/mån
  Tier 4 · lyx                 90-130 kvm, 3-4 rok, 14000-22000 kr/mån

Wellbeing-koppling (i `wellbeing/drift_calculator.py`):
  Hemlös     -8 safety / spelmånad
  Tier 1     -2 safety / spelmånad (trångt, instabilt)
  Tier 2      0 (baseline)
  Tier 3     +1 safety / spelmånad
  Tier 4     +2 safety / spelmånad (komfort)

Pentagon-event vid byte (i boendemarknad-endpoint):
  Tier 1 →  -2 safety
  Tier 2 →  +1 safety
  Tier 3 →  +3 safety, +1 social
  Tier 4 →  +5 safety, +2 social, -1 leisure
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

from ..pools.stadspool import STAD_BY_KEY


RentalTier = Literal[1, 2, 3, 4]


@dataclass(frozen=True)
class RentalListing:
    """En tillgänglig hyresrätt på marknaden."""

    listing_id: str           # "{city}-{ym}-r{idx:02d}"
    city_key: str
    city_display: str
    tier: RentalTier
    tier_label: str           # "korridor" | "liten" | "familj" | "lyx"
    address: str
    size_kvm: int
    rooms: int
    monthly_rent: int
    deposit: int              # Vanligen 1-3 månadshyror
    first_hand: bool          # True = förstahandskontrakt, False = andrahand
    queue_months: int         # Förväntad väntetid (0 = direkt, >0 spel-månader)
    quality_score: int        # 1-10 (för wellbeing-drift)
    description: str


# === Tier-tabeller ===
# Tuple: (size_range, rooms, rent_range, deposit_months,
#         first_hand_share, queue_months_range, quality_range)
_TIER_SPECS = {
    1: {
        "label": "korridor",
        "size_range": (12, 18),
        "rooms": 1,
        "rent_range": (3500, 5000),
        "deposit_months": 1,
        "first_hand_share": 0.20,
        "queue_months_range": (0, 2),
        "quality_range": (1, 3),
        "description_pool": [
            "Korridorrum · delad köks- och badrum",
            "Studentkorridor · trångt men billigt",
            "Akutboende · kort uppsägningstid",
            "Möblerat litet rum · gemensamhetsutrymmen",
        ],
    },
    2: {
        "label": "liten",
        "size_range": (25, 45),
        "rooms": (1, 2),
        "rent_range": (5500, 8500),
        "deposit_months": 2,
        "first_hand_share": 0.40,
        "queue_months_range": (1, 6),
        "quality_range": (3, 6),
        "description_pool": [
            "Liten etta · funkar för en person",
            "Kompakt 1:a · kök i hallen",
            "Lugn 2:a · perfekt för par eller singel",
            "Renoverat kök · slitet golv",
        ],
    },
    3: {
        "label": "familj",
        "size_range": (50, 85),
        "rooms": (2, 3),
        "rent_range": (9000, 13000),
        "deposit_months": 2,
        "first_hand_share": 0.60,
        "queue_months_range": (2, 9),
        "quality_range": (5, 8),
        "description_pool": [
            "Familjelägenhet · plats för barn",
            "Stor 3:a · balkong + förråd",
            "Centralt 2:a · välhållet med ekparkett",
            "Modernt kök · ljust och rymligt",
        ],
    },
    4: {
        "label": "lyx",
        "size_range": (90, 130),
        "rooms": (3, 4),
        "rent_range": (14000, 22000),
        "deposit_months": 3,
        "first_hand_share": 0.75,
        "queue_months_range": (3, 12),
        "quality_range": (8, 10),
        "description_pool": [
            "Lyxlägenhet · marmor i hallen",
            "Penthouse · takterrass med utsikt",
            "Sekelskifte · stuckatur + kakelugn",
            "Designat kök · högsta standard",
        ],
    },
}


_DISTRICTS = {
    "stockholm": [
        "Södermalm", "Vasastan", "Kungsholmen", "Östermalm",
        "Bromma", "Hägersten", "Hammarby Sjöstad", "Liljeholmen",
    ],
    "goteborg": [
        "Linné", "Vasastaden", "Majorna", "Hisingen", "Centrum",
        "Lundby", "Härlanda",
    ],
    "malmo": [
        "Möllevången", "Limhamn", "Västra Hamnen", "Centrum",
        "Rosengård", "Hyllie",
    ],
    "norrkoping": [
        "Centrum", "Lindö", "Hageby", "Berga", "Klockaretorpet",
    ],
}


_STREETS = [
    "Storgatan", "Parkvägen", "Skolgatan", "Linnégatan",
    "Birger Jarlsgatan", "Kungsgatan", "Drottninggatan",
    "Slottsgatan", "Strömgatan", "Bergsgatan",
]


def _district_for(rng: random.Random, city_key: str) -> str:
    districts = _DISTRICTS.get(
        city_key, _DISTRICTS.get("norrkoping"),
    )
    return rng.choice(districts)


def _street_for(rng: random.Random) -> str:
    return f"{rng.choice(_STREETS)} {rng.randint(1, 250)}"


def list_rentals_for_city(
    city_key: str,
    year_month: str,
    *,
    n: int = 12,
    min_tier: int = 1,
    max_tier: int = 4,
) -> list[RentalListing]:
    """Generera deterministisk pool av rental-listings för en stad/månad.

    n: total antal listings (default 12, 3 per tier)
    min_tier/max_tier: filtrera till specifika tier-spann
    """
    rng = random.Random(f"rentals-{city_key}-{year_month}")
    city = STAD_BY_KEY.get(city_key)
    if city is None:
        return []
    city_display = city.display

    listings: list[RentalListing] = []
    # Distribuera n över tier 1-4 (3 av varje)
    per_tier = max(1, n // 4)
    for tier in range(1, 5):
        if tier < min_tier or tier > max_tier:
            continue
        spec = _TIER_SPECS[tier]
        for idx in range(per_tier):
            size_min, size_max = spec["size_range"]
            size = rng.randint(size_min, size_max)
            rooms_spec = spec["rooms"]
            if isinstance(rooms_spec, tuple):
                rooms = rng.randint(rooms_spec[0], rooms_spec[1])
            else:
                rooms = rooms_spec
            rent_min, rent_max = spec["rent_range"]
            monthly_rent = rng.randint(rent_min, rent_max)
            # Justera rent ±10 % baserat på kvalitet inom tier
            q_min, q_max = spec["quality_range"]
            quality = rng.randint(q_min, q_max)
            q_factor = 0.95 + (quality - q_min) * 0.10 / max(1, q_max - q_min)
            monthly_rent = int(monthly_rent * q_factor)
            deposit = monthly_rent * spec["deposit_months"]
            first_hand = rng.random() < spec["first_hand_share"]
            qm_min, qm_max = spec["queue_months_range"]
            queue_months = rng.randint(qm_min, qm_max)
            # Andrahandskontrakt har kortare väntetid
            if not first_hand:
                queue_months = max(0, queue_months // 3)
            description = rng.choice(spec["description_pool"])
            district = _district_for(rng, city_key)
            address = f"{_street_for(rng)}, {district}"
            listings.append(RentalListing(
                listing_id=f"{city_key}-{year_month}-r{tier}{idx:02d}",
                city_key=city_key,
                city_display=city_display,
                tier=tier,  # type: ignore[arg-type]
                tier_label=spec["label"],
                address=address,
                size_kvm=size,
                rooms=rooms,
                monthly_rent=monthly_rent,
                deposit=deposit,
                first_hand=first_hand,
                queue_months=queue_months,
                quality_score=quality,
                description=description,
            ))
    return listings


def find_rental(
    listing_id: str,
) -> RentalListing | None:
    """Slå upp en specifik listing från dess id (format
    `{city}-{ym}-r{tier}{idx:02d}`). Re-genererar poolen för den
    stadsmånaden och plockar matchande id.
    """
    try:
        parts = listing_id.rsplit("-r", 1)
        city_ym = parts[0]
        # city-ym kan innehålla bindestreck (year-month), så splitta
        # från höger på en separator vi vet
        if "-" not in city_ym:
            return None
        # ym = sista "YYYY-MM"
        # city_key = allt innan sista "-YYYY"
        tokens = city_ym.split("-")
        if len(tokens) < 3:
            return None
        ym = f"{tokens[-2]}-{tokens[-1]}"
        city_key = "-".join(tokens[:-2])
    except Exception:
        return None
    for listing in list_rentals_for_city(city_key, ym, n=12):
        if listing.listing_id == listing_id:
            return listing
    return None


def tier_pentagon_deltas(tier: RentalTier) -> dict:
    """Pentagon-event-deltas vid inflyttning per tier."""
    return {
        1: {"safety": -2, "economy": +1},
        2: {"safety": +1, "economy": 0},
        3: {"safety": +3, "social": +1, "economy": -1},
        4: {"safety": +5, "social": +2, "leisure": -1, "economy": -2},
    }[tier]


def tier_monthly_safety_drift(tier: RentalTier) -> int:
    """Månatlig safety-drift för en bostad i en given tier."""
    return {
        1: -2,
        2: 0,
        3: +1,
        4: +2,
    }[tier]
