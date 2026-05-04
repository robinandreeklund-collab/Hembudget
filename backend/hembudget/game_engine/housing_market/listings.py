"""B2 · Listings-pool per stad.

Spec: dev/game-motor/06-boendemarknaden.md (Köp-flödet · "Föreslagna
bostäder i staden")

Listings genereras on-demand som en Python-pool — ingen DB-tabell
behövs. Deterministiskt seedad på (city_key, year_month) så samma
elev som öppnar marknaden samma sim-månad ser samma listings.

Storlek + adress slumpas inom realistiska intervall för stadens
bebyggelse-mönster. Pris baseras på `market_price_for` × storlek
× lägenhets-bonus (charm, läge, balkong osv).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

from ..pools.stadspool import STAD_BY_KEY
from .market_data import market_price_for


HousingType = Literal["bostadsratt", "villa", "radhus"]


@dataclass(frozen=True)
class HousingListing:
    """En tillgänglig bostad på marknaden i en specifik stad/månad."""

    listing_id: str  # Stabil id: "{city}-{ym}-{idx:02d}"
    city_key: str
    city_display: str
    type: HousingType
    address: str
    size_kvm: int
    rooms: int
    asking_price: int
    monthly_avgift: int        # BRF-avgift eller villa-drift
    description: str
    quality_score: int         # 1-10, för att förklara prisskillnader


# Stockholmsdistrikt
_DISTRICTS = {
    "stockholm": [
        "Södermalm", "Vasastan", "Kungsholmen", "Östermalm",
        "Bromma", "Hägersten", "Hammarby Sjöstad", "Liljeholmen",
    ],
    "goteborg": [
        "Linnéstaden", "Majorna", "Haga", "Östra Göteborg",
        "Lundby", "Kungsladugård", "Annedal",
    ],
    "malmo": [
        "Västra Hamnen", "Möllevången", "Limhamn",
        "Slottstaden", "Kirseberg", "Hyllie",
    ],
}


def _district_for(rng: random.Random, city_key: str) -> str:
    pool = _DISTRICTS.get(city_key)
    if pool:
        return rng.choice(pool)
    return "Centrum"


def _street_for(rng: random.Random, district: str) -> str:
    streets = [
        "Storgatan", "Nygatan", "Strandvägen", "Skolgatan",
        "Hagagatan", "Parkvägen", "Linnégatan", "Östra Allén",
    ]
    return f"{rng.choice(streets)} {rng.randint(1, 99)}"


def _quality_text(quality: int) -> str:
    if quality >= 9:
        return "Toppskick · nyrenoverat kök & badrum"
    if quality >= 7:
        return "Välhållet · ljust med god planlösning"
    if quality >= 5:
        return "Renoveringsbehov · slitet kök, original-badrum"
    return "Stort renoveringsbehov · bara skalet i bra skick"


def listings_for_city(
    city_key: str,
    year_month: str,
    *,
    n: int = 6,
    min_size_kvm: int = 0,
    types: tuple[str, ...] | None = None,
) -> list[HousingListing]:
    """Generera n listings för en stad i en specifik spelmånad.

    Deterministisk: samma (city, year_month) → samma listings.

    `min_size_kvm`: filtrera bort listings som är för små för hushållet
    (Konsumentverkets norm: ensam ≥28 kvm, sambo ≥44 kvm, familj ≥60+).
    `types`: begränsa till specifika typer ("hyresratt", "bostadsratt"...).
    Notera: hyresrätt-listings genereras INTE av den generella poolen
    (den är optimerad för köp); separat hyresrätts-pool kommer i Sprint 6.
    """
    city = STAD_BY_KEY.get(city_key)
    if city is None:
        return []

    rng = random.Random(f"listings|{city_key}|{year_month}")
    base_price = market_price_for(city_key, year_month)

    # Generera dubbelt så många kandidater när vi filtrerar — så vi
    # inte hamnar med tom lista pga storlek/typ-filter.
    target_n = n
    candidates_to_try = n if (min_size_kvm == 0 and not types) else n * 3

    listings: list[HousingListing] = []
    for idx in range(candidates_to_try):
        # Slumpa typ baserat på stadens fördelning
        type_pool = []
        type_weights = []
        if city.bostad_pct_brf > 0.05:
            type_pool.append("bostadsratt"); type_weights.append(city.bostad_pct_brf)
        if city.bostad_pct_villa > 0.05:
            type_pool.append("villa"); type_weights.append(city.bostad_pct_villa)
        # radhus = liten andel där villa finns
        if city.bostad_pct_villa > 0.10:
            type_pool.append("radhus"); type_weights.append(city.bostad_pct_villa * 0.4)
        if not type_pool:
            type_pool.append("bostadsratt")
            type_weights.append(1.0)
        h_type: HousingType = rng.choices(type_pool, weights=type_weights, k=1)[0]

        # Storlek per typ
        if h_type == "bostadsratt":
            size = rng.randint(28, 95)
            rooms = max(1, size // 30)
        elif h_type == "villa":
            size = rng.randint(85, 180)
            rooms = max(3, size // 35)
        else:  # radhus
            size = rng.randint(75, 130)
            rooms = max(2, size // 35)

        # Kvalitet 1-10 påverkar pris ±25 %
        quality = rng.randint(3, 10)
        quality_factor = 0.85 + (quality - 3) * (0.30 / 7)

        # Pris per kvm: BRF = base, villa lägre per kvm men större totalt
        price_per_kvm = base_price
        if h_type == "villa":
            price_per_kvm = int(city.avg_villa_price_per_kvm)
        elif h_type == "radhus":
            price_per_kvm = int((base_price + city.avg_villa_price_per_kvm) / 2)

        asking_price = int(price_per_kvm * size * quality_factor)

        # Månadsavgift: BRF 35-75 kr/kvm/mån, villa drift 4-9k flat
        if h_type == "villa":
            monthly_avgift = rng.randint(4_000, 9_000)
        elif h_type == "radhus":
            monthly_avgift = rng.randint(2_500, 6_000)
        else:
            monthly_avgift = int(rng.uniform(35, 75) * size)

        district = _district_for(rng, city_key)
        address = f"{_street_for(rng, district)}, {district}"

        # Filtrering
        if min_size_kvm and size < min_size_kvm:
            continue
        if types and h_type not in types:
            continue

        listings.append(HousingListing(
            listing_id=f"{city_key}-{year_month}-{idx:02d}",
            city_key=city_key,
            city_display=city.display,
            type=h_type,
            address=address,
            size_kvm=size,
            rooms=rooms,
            asking_price=asking_price,
            monthly_avgift=monthly_avgift,
            description=_quality_text(quality),
            quality_score=quality,
        ))

        if len(listings) >= target_n:
            break

    return listings
