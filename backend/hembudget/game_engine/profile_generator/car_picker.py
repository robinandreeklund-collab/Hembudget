"""Bil + pendling + bil-finansiering per genererad karaktär.

En del av profil-generatorn. Bestämmer:

- Om karaktären har bil (zon-baserad % + spend-profile + ålders-faktor)
- Drivmedelstyp (60 % bensin, 15 % diesel, 20 % el, 5 % hybrid)
- Bilmärke/-modell + årsmodell + marknadsvärde (spend-profile-tier)
- Finansiering (kontant < 80k, lån 80-280k, leasing eller lån > 280k)
- Försäkringsbolag + premie (baserat på värde + årsmodell + ålder)
- Pendlingsavstånd (om bil eller kollektivt)
- Månatliga drivmedels-/laddnings-kostnader

Determinism: använd `seed_for(student_id, "car")` så samma elev alltid
får samma bil. Vid familj-scope kopieras bilen från huvudföräldern.

Output: `CarChoice` (pydantic) som lagras både i GeneratedProfile (för
spårbarhet) och som kolumner på `StudentProfile` (för snabb access i
fixed_expenses + bil-events + skatteverket).
"""
from __future__ import annotations

import random
from typing import Literal, Optional

from pydantic import BaseModel, Field


# === Sannolikheter per zon ===

# Stadsstorlek → % bil för normal-profil. Justeras med spend-profile +
# ålder. Matchar verkligheten (SCB · bil per hushåll).
P_CAR_BY_CITY_TIER = {
    "large": 0.30,    # Stockholm/Göteborg/Malmö
    "medium": 0.60,   # Uppsala/Västerås m.fl.
    "small": 0.85,    # Småorter
}

# Pendlings-avstånd (km) per zon, (median, std-radie)
COMMUTE_KM_BY_CITY_TIER = {
    "large": (12, 7),
    "medium": (18, 10),
    "small": (25, 18),
}

# Kollektivtrafik-kort kr/mån för dem utan bil
PUBLIC_TRANSPORT_BY_TIER = {
    "large": 970,    # SL 30-dagar 2026
    "medium": 680,
    "small": 520,
}


# === Bilmärken/modeller per pris-tier ===

class CarModel(BaseModel):
    brand: str
    model: str
    fuel_options: list[str]   # vilka driftslag som finns
    base_price_new: int        # cirka nybilspris (för depreciation-räkning)


BUDGET_CARS: list[CarModel] = [
    CarModel(brand="Volvo", model="V40", fuel_options=["bensin", "diesel"], base_price_new=210_000),
    CarModel(brand="Toyota", model="Corolla", fuel_options=["bensin", "hybrid"], base_price_new=245_000),
    CarModel(brand="Renault", model="Mégane", fuel_options=["bensin", "diesel"], base_price_new=215_000),
    CarModel(brand="Skoda", model="Octavia", fuel_options=["bensin", "diesel"], base_price_new=265_000),
    CarModel(brand="Hyundai", model="i30", fuel_options=["bensin", "el"], base_price_new=220_000),
    CarModel(brand="Ford", model="Focus", fuel_options=["bensin", "diesel"], base_price_new=230_000),
    CarModel(brand="Renault", model="Zoe", fuel_options=["el"], base_price_new=260_000),
    CarModel(brand="MG", model="MG4", fuel_options=["el"], base_price_new=295_000),
]

MID_CARS: list[CarModel] = [
    CarModel(brand="Volvo", model="V60", fuel_options=["bensin", "diesel", "hybrid"], base_price_new=395_000),
    CarModel(brand="VW", model="Passat", fuel_options=["bensin", "diesel", "hybrid"], base_price_new=380_000),
    CarModel(brand="Toyota", model="RAV4", fuel_options=["bensin", "hybrid"], base_price_new=410_000),
    CarModel(brand="Skoda", model="Kodiaq", fuel_options=["bensin", "diesel"], base_price_new=425_000),
    CarModel(brand="Mazda", model="CX-5", fuel_options=["bensin", "diesel"], base_price_new=395_000),
    CarModel(brand="Audi", model="A4", fuel_options=["bensin", "diesel"], base_price_new=430_000),
    CarModel(brand="Tesla", model="Model 3", fuel_options=["el"], base_price_new=485_000),
    CarModel(brand="VW", model="ID.4", fuel_options=["el"], base_price_new=505_000),
]

PREMIUM_CARS: list[CarModel] = [
    CarModel(brand="Volvo", model="XC60", fuel_options=["bensin", "diesel", "hybrid"], base_price_new=545_000),
    CarModel(brand="Volvo", model="XC90", fuel_options=["bensin", "hybrid"], base_price_new=720_000),
    CarModel(brand="BMW", model="3-serie", fuel_options=["bensin", "diesel", "hybrid"], base_price_new=560_000),
    CarModel(brand="Audi", model="A6", fuel_options=["bensin", "diesel", "hybrid"], base_price_new=625_000),
    CarModel(brand="Mercedes", model="C-Klass", fuel_options=["bensin", "diesel", "hybrid"], base_price_new=595_000),
    CarModel(brand="Tesla", model="Model Y", fuel_options=["el"], base_price_new=585_000),
    CarModel(brand="Volvo", model="EX30", fuel_options=["el"], base_price_new=495_000),
    CarModel(brand="Polestar", model="2", fuel_options=["el"], base_price_new=545_000),
]


# === Drivmedelskostnader · per km ===
# Bensin 16 kr/L · 0.55 L/mil ≈ 0.88 kr/km
# Diesel 17 kr/L · 0.45 L/mil ≈ 0.77 kr/km
# El: 1.50 kr/kWh × 0.18 kWh/km ≈ 0.27 kr/km (hemladdning)
# Hybrid: ~0.55 kr/km (snitt city/highway)

KR_PER_KM = {
    "bensin": 0.88,
    "diesel": 0.77,
    "hybrid": 0.55,
    "el": 0.27,
}


# === Försäkringsbolag ===

INSURANCE_PROVIDERS = ["Folksam", "If", "Trygg-Hansa", "Länsförsäkringar"]


# === Slumpalgoritm ===


def _city_tier(city_key: str) -> Literal["large", "medium", "small"]:
    """Mappa city-key till tier · matchar industries.LARGE_CITIES m.fl."""
    try:
        from ...business.industries import LARGE_CITIES, MEDIUM_CITIES
        ck = (city_key or "").lower()
        if ck in LARGE_CITIES:
            return "large"
        if ck in MEDIUM_CITIES:
            return "medium"
        return "small"
    except Exception:
        return "medium"


def _spend_profile_modifier(spend_profile: str) -> dict:
    """Hur spend-profile påverkar bil-chans + pris-tier.

    sparsam → -15 % bil-chans · välj BUDGET-tier
    balanserad → standard
    extravagant → +15 % bil-chans · välj PREMIUM-tier oftare
    """
    sp = (spend_profile or "balanserad").lower()
    if sp == "sparsam":
        return {"car_chance_delta": -0.15, "tier_bias": "budget"}
    if sp == "extravagant":
        return {"car_chance_delta": 0.15, "tier_bias": "premium"}
    return {"car_chance_delta": 0.0, "tier_bias": "balanced"}


def _age_modifier(age: int) -> float:
    """Bil-chans-justering per ålder.
    Unga (18-25): -10 % (har inte hunnit ha råd)
    Mid (26-59): standard
    Äldre (60+): +5 % (bilberoende)
    """
    if age <= 25:
        return -0.10
    if age >= 60:
        return 0.05
    return 0.0


def _pick_tier(
    rng: random.Random,
    tier_bias: str,
) -> tuple[list[CarModel], int, int]:
    """Returnerar (cars-pool, min_year, max_year-back).
    Sparsam: BUDGET, 6-15 år gammal
    Balanserad: MID, 2-8 år gammal
    Extravagant: PREMIUM (50 %), MID (50 %), 0-4 år gammal
    """
    if tier_bias == "budget":
        return BUDGET_CARS, 6, 15
    if tier_bias == "premium":
        if rng.random() < 0.5:
            return PREMIUM_CARS, 0, 4
        return MID_CARS, 0, 4
    # balanced
    return MID_CARS, 2, 8


def _market_value(model: CarModel, age_years: int) -> int:
    """Beräkna marknadsvärde · linjär depreciation 15 %/år första 3 år,
    sen 8 %/år. Min 30 % av nybilspriset."""
    val = float(model.base_price_new)
    for y in range(age_years):
        depr = 0.15 if y < 3 else 0.08
        val *= (1 - depr)
    return max(int(val), int(model.base_price_new * 0.30))


def _insurance_premium(
    market_value: int, car_age: int, owner_age: int,
) -> int:
    """Försäkringspremie kr/mån.

    Baseline 350 kr.
    + 200 kr per 100k bilvärde över 100k.
    + 30 kr per år bilen är äldre än 5 år (mer servicebehov).
    + 100 kr om förare < 25 (riskklass).
    Max 1 200 kr/mån.
    """
    base = 350.0
    base += max(0, (market_value - 100_000) / 100_000) * 200.0
    if car_age > 5:
        base += (car_age - 5) * 30.0
    if owner_age < 25:
        base += 100.0
    return min(1200, int(base))


def _financing(
    rng: random.Random, market_value: int,
) -> dict:
    """Avgör hur bilen är finansierad.

    < 80 000 kr · alltid kontant
    80 000 - 280 000 · 30 % kontant, 70 % lån (5 år, 6 %)
    >= 280 000 · 60 % leasing (3 år), 40 % lån (5 år, 6 %)
    """
    if market_value < 80_000:
        return {"financing": "cash", "loan_principal": 0,
                "loan_monthly_payment": 0, "leasing_monthly": 0}
    if market_value < 280_000:
        if rng.random() < 0.3:
            return {"financing": "cash", "loan_principal": 0,
                    "loan_monthly_payment": 0, "leasing_monthly": 0}
        principal = int(market_value * 0.8)  # 20 % kontant-insats
        monthly = _annuity(principal, 0.06, 60)
        return {"financing": "loan", "loan_principal": principal,
                "loan_monthly_payment": monthly, "leasing_monthly": 0}
    # >= 280k
    if rng.random() < 0.6:
        # Leasing 3 år · ca 1.2 % av nybilspris/mån är typisk
        leasing = int(market_value * 0.013)
        return {"financing": "leasing", "loan_principal": 0,
                "loan_monthly_payment": 0, "leasing_monthly": leasing}
    principal = int(market_value * 0.85)  # mindre insats vid dyrare
    monthly = _annuity(principal, 0.06, 60)
    return {"financing": "loan", "loan_principal": principal,
            "loan_monthly_payment": monthly, "leasing_monthly": 0}


def _annuity(principal: int, annual_rate: float, months: int) -> int:
    """Annuitetsbetalning · standardformel."""
    r = annual_rate / 12.0
    if r == 0:
        return principal // months
    payment = principal * r / (1 - (1 + r) ** -months)
    return int(round(payment))


# === Pydantic-output ===


class CarChoice(BaseModel):
    """Lagras både i GeneratedProfile.car och som kolumner i StudentProfile."""
    has_car: bool
    commute_transport: Literal["car", "public", "bike", "remote"]
    commute_km: int = Field(ge=0, le=200)

    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    fuel_type: Optional[Literal["bensin", "diesel", "el", "hybrid"]] = None
    market_value_sek: Optional[int] = None
    license_plate: Optional[str] = None  # synthetic, t.ex. "ABC 123"

    insurance_provider: Optional[str] = None
    insurance_premium_monthly: Optional[int] = None

    financing: Optional[Literal["cash", "loan", "leasing"]] = None
    loan_principal: Optional[int] = None
    loan_monthly_payment: Optional[int] = None
    leasing_monthly: Optional[int] = None

    monthly_fuel_cost: int = 0      # bensin/diesel/hybrid-bränsle
    monthly_electric_extra: int = 0  # el-bil hemladdning · på utility
    monthly_public_transport: int = 0  # kollektivtrafik om INTE bil


# === Huvudfunktion ===


def pick_car(
    rng: random.Random,
    *,
    city_key: str,
    age: int,
    spend_profile: str,
    student_id: int = 0,
) -> CarChoice:
    """Generera bil-data för en karaktär.

    `student_id` används bara för plåt-generering så samma elev får
    samma regnr. Lämna 0 vid teori-/preview-anrop.
    """
    tier = _city_tier(city_key)
    sp_mod = _spend_profile_modifier(spend_profile)
    age_mod = _age_modifier(age)
    car_chance = P_CAR_BY_CITY_TIER[tier] + sp_mod["car_chance_delta"] + age_mod
    car_chance = max(0.05, min(0.95, car_chance))

    has_car = rng.random() < car_chance

    # 10 % remote-andel oavsett bil — pandemi-effekt kvarstår
    is_remote = rng.random() < 0.10

    # Pendling-avstånd · slumpa från zon-median
    median_km, radius_km = COMMUTE_KM_BY_CITY_TIER[tier]
    if is_remote:
        commute_km = 0
        transport: Literal["car", "public", "bike", "remote"] = "remote"
    elif has_car:
        commute_km = max(2, int(rng.gauss(median_km, radius_km)))
        transport = "car"
    else:
        # Cykel om kort, annars kollektivt
        commute_km = max(2, int(rng.gauss(median_km, radius_km)))
        transport = "bike" if commute_km <= 6 else "public"

    if not has_car:
        # Ingen bil · returnera tom CarChoice med ev. kollektivt-kostnad
        pub_cost = (
            PUBLIC_TRANSPORT_BY_TIER[tier] if transport == "public" else 0
        )
        return CarChoice(
            has_car=False,
            commute_transport=transport,
            commute_km=commute_km,
            monthly_public_transport=pub_cost,
        )

    # Plocka bil · pool baserat på spend-profile-tier
    pool, min_age, max_age = _pick_tier(rng, sp_mod["tier_bias"])
    model = rng.choice(pool)
    car_age = rng.randint(min_age, max_age)
    car_year = 2026 - car_age

    # 20 % el oavsett (om modellen stödjer det) · annars 65 % bensin,
    # 12 % diesel, 3 % hybrid (om modell stödjer).
    fuel_pool = list(model.fuel_options)
    if "el" in fuel_pool and rng.random() < 0.20:
        fuel = "el"
    else:
        # Vikta bland övriga
        non_el = [f for f in fuel_pool if f != "el"]
        if not non_el:
            fuel = fuel_pool[0]
        else:
            # bensin > diesel > hybrid om alla finns
            weights = [
                3 if f == "bensin" else (1 if f == "diesel" else 0.5)
                for f in non_el
            ]
            tot = sum(weights)
            r = rng.random() * tot
            acc = 0.0
            fuel = non_el[0]
            for f, w in zip(non_el, weights):
                acc += w
                if r <= acc:
                    fuel = f
                    break

    market_value = _market_value(model, car_age)
    insurance = _insurance_premium(market_value, car_age, age)
    financing = _financing(rng, market_value)

    # Drivmedelskostnad / mån
    kr_per_km = KR_PER_KM.get(fuel, 0.85)
    # ENA väg × 2 (return) × 22 arbetsdagar
    monthly_km = commute_km * 2 * 22
    raw_fuel = int(monthly_km * kr_per_km)
    monthly_fuel = raw_fuel if fuel != "el" else 0
    monthly_electric = raw_fuel if fuel == "el" else 0
    # Bonus laddning hemma för el · alla el-bilar +150 kr/mån oavsett
    if fuel == "el":
        monthly_electric += 150

    # Synthetic regnr · 3 bokstäver + 3 siffror, deterministiskt
    rng_plate = random.Random(student_id * 7 + 13 if student_id else rng.random())
    letters = "".join(rng_plate.choice("ABCDEFGHJKLMNOPRSTUWXYZ") for _ in range(3))
    digits = f"{rng_plate.randint(100, 999):03d}"
    plate = f"{letters} {digits}"

    return CarChoice(
        has_car=True,
        commute_transport="car",
        commute_km=commute_km,
        brand=model.brand,
        model=model.model,
        year=car_year,
        fuel_type=fuel,  # type: ignore[arg-type]
        market_value_sek=market_value,
        license_plate=plate,
        insurance_provider=rng.choice(INSURANCE_PROVIDERS),
        insurance_premium_monthly=insurance,
        financing=financing["financing"],  # type: ignore[arg-type]
        loan_principal=financing["loan_principal"] or None,
        loan_monthly_payment=financing["loan_monthly_payment"] or None,
        leasing_monthly=financing["leasing_monthly"] or None,
        monthly_fuel_cost=monthly_fuel,
        monthly_electric_extra=monthly_electric,
    )
