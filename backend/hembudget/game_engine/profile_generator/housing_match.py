"""Boende-matchning · väljer boendetyp och storlek matchat mot hushållets
nettolön och valda stad.

Regelverk (svenska 2026, dev/game-motor/02-profile-generator.md steg 4):
- Boendekostnad max 30-35 % av nettolön (singel)
- Max 25 % vid familj med barn
- Hyresrätt ~100-180 kr/kvm/mån (city-specifik)
- Bostadsrätt: köppris från stad × storlek; månadskostnad = avgift +
  ränta + amortering
- Villa: lite billigare per kvm men + 4-9k drift
"""
from __future__ import annotations

import random
from typing import Literal

from ..pools.stadspool import Stad
from .schema import FamilyStatus, HousingChoice


# === Konstanter ===

# Andel av köpeskilling som kontantinsats (svensk regel 15 %)
LTV_MAX = 0.85

# Schablonränta + amortering 2026 (förenklat)
INTEREST_RATE_ANNUAL = 0.039   # 3.9 % bolån-snitt
AMORTERING_RATE_ANNUAL = 0.02  # 2 % per år (LTV 70-85)

# Bostadsrätt månadsavgift per kvm (SEK/kvm/mån)
BRF_AVGIFT_PER_KVM_MONTH = (35, 75)

# Villa-driftkostnad per månad (SEK)
VILLA_DRIFT_MONTHLY = (4_000, 9_000)

# Kvm per person efter familjestatus
KVM_PER_PERSON_RANGE: dict[FamilyStatus, tuple[int, int]] = {
    "ensam": (28, 45),
    "sambo": (22, 38),
    "familj_med_barn": (20, 32),
}


# === Hjälpare ===


def _household_size(family_status: FamilyStatus, children: int) -> int:
    base = {"ensam": 1, "sambo": 2, "familj_med_barn": 2}[family_status]
    return base + (children if family_status == "familj_med_barn" else 0)


def _max_housing_share(family_status: FamilyStatus) -> float:
    """Övre gräns för boendekostnad som andel av nettolön."""
    return 0.25 if family_status == "familj_med_barn" else 0.32


def _pick_size_kvm(
    rng: random.Random,
    family_status: FamilyStatus,
    children: int,
) -> int:
    persons = _household_size(family_status, children)
    lo, hi = KVM_PER_PERSON_RANGE[family_status]
    per_person = rng.randint(lo, hi)
    # Säkerhetsklamp så små singel-lägenheter inte krymper under 22 kvm
    return max(22, per_person * persons)


def _monthly_loan_cost(
    purchase_price: int,
) -> tuple[int, int, int]:
    """Returnerar (lån, ränta_per_månad, amortering_per_månad)."""
    loan = int(purchase_price * LTV_MAX)
    interest_m = int(loan * INTEREST_RATE_ANNUAL / 12)
    amort_m = int(loan * AMORTERING_RATE_ANNUAL / 12)
    return loan, interest_m, amort_m


# === Per-typ-byggare ===


def _build_hyresratt(
    rng: random.Random, city: Stad, size_kvm: int,
) -> HousingChoice:
    cost = int(city.avg_rental_per_kvm_month * size_kvm)
    return HousingChoice(
        type="hyresratt",
        size_kvm=size_kvm,
        monthly_cost=cost,
    )


def _build_bostadsratt(
    rng: random.Random, city: Stad, size_kvm: int,
) -> HousingChoice:
    price = int(city.avg_brf_price_per_kvm * size_kvm)
    loan, interest_m, amort_m = _monthly_loan_cost(price)
    avgift_per_kvm = rng.uniform(*BRF_AVGIFT_PER_KVM_MONTH)
    avgift_m = int(avgift_per_kvm * size_kvm)
    monthly = interest_m + amort_m + avgift_m
    return HousingChoice(
        type="bostadsratt",
        size_kvm=size_kvm,
        monthly_cost=monthly,
        purchase_price=price,
        loan_amount=loan,
        monthly_amortering=amort_m,
        monthly_interest=interest_m,
        monthly_avgift=avgift_m,
    )


def _build_villa(
    rng: random.Random, city: Stad, size_kvm: int,
) -> HousingChoice:
    price = int(city.avg_villa_price_per_kvm * size_kvm)
    loan, interest_m, amort_m = _monthly_loan_cost(price)
    drift = rng.randint(*VILLA_DRIFT_MONTHLY)
    monthly = interest_m + amort_m + drift
    return HousingChoice(
        type="villa",
        size_kvm=size_kvm,
        monthly_cost=monthly,
        purchase_price=price,
        loan_amount=loan,
        monthly_amortering=amort_m,
        monthly_interest=interest_m,
        monthly_drift=drift,
    )


# === Huvudfunktion ===


def pick_housing(
    rng: random.Random,
    *,
    city: Stad,
    family_status: FamilyStatus,
    children: int,
    household_net_monthly: int,
) -> HousingChoice:
    """Väljer boendetyp och dimensioner matchat mot inkomst + stad.

    Algoritm:
      1. Räkna max-månadskostnad (= max-share × nettolön)
      2. Bygg kandidat per typ med stadens vikter, klampa storlek
      3. Filtrera bort kandidater över max-budget
      4. Slumpa en kandidat enligt stadens bostad_pct-vikter
      5. Om alla för dyra → välj billigaste hyresrätt med minimi-storlek
    """
    max_monthly = int(household_net_monthly * _max_housing_share(family_status))
    size_kvm = _pick_size_kvm(rng, family_status, children)

    candidates: list[tuple[HousingChoice, float]] = []

    # Hyresrätt
    hr = _build_hyresratt(rng, city, size_kvm)
    if hr.monthly_cost <= max_monthly:
        candidates.append((hr, city.bostad_pct_hyresratt))

    # Bostadsrätt
    br = _build_bostadsratt(rng, city, size_kvm)
    if br.monthly_cost <= max_monthly:
        candidates.append((br, city.bostad_pct_brf))

    # Villa (bara om staden överhuvudtaget har villor)
    if city.bostad_pct_villa > 0.03:
        v = _build_villa(rng, city, size_kvm)
        if v.monthly_cost <= max_monthly:
            candidates.append((v, city.bostad_pct_villa))

    if not candidates:
        # Fallback: krymp tills hyresrätt får plats
        min_size = max(22, int(max_monthly / city.avg_rental_per_kvm_month))
        return _build_hyresratt(rng, city, min_size)

    # Vikta-slumpa
    items, weights = zip(*candidates)
    return rng.choices(items, weights=weights, k=1)[0]
