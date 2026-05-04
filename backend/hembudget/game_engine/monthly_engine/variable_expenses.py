"""Fas C · Variabla utgifter.

Spec: dev/game-motor/03-monthly-engine.md (Fas C).

Genererar transaktioner sprida över hela spelmånaden, baserat på:
- Konsumentverkets baseline per kategori (mat, kläder, fritid, nöjen)
- Elevens spend_profile (sparsam=0.85x, balanserad=1.00x, slosa=1.25x)
- Stadens kostnadsmultiplikator (food/transport)
- Slumpmässig variation per kategori (5/12/20 % beroende på nivå)

Varje kategori bryts ned i 3-10 delkostnader (= transaktioner) så
postlådan + kontoutdraget speglar ett realistiskt månadsmönster.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ...db.models import Account, Transaction
from ...school.konsumentverket import (
    GEMENSAMT_PER_PERSONER,
    INDIVID_OVRIGT_PER_AGE,
    MAT_HEMMA_PER_AGE,
)
from ..difficulty import get_difficulty
from ..pools.stadspool import STAD_BY_KEY
from ..profile_generator.schema import GeneratedProfile
from ..release_schedule import release_at_for_day
from .scope_seed import get_or_create_category


SPEND_MULTIPLIER = {
    "sparsam": 0.85,
    "balanserad": 1.00,
    "slosa": 1.25,
}

VARIATION_PER_LEVEL = {1: 0.05, 2: 0.12, 3: 0.20}


@dataclass(frozen=True)
class CategoryPlan:
    """Hur en kategoris månadsbelopp ska splittras till transaktioner."""

    name: str                    # Visningsnamn + DB-kategori
    monthly_amount: int          # Totalsumma (efter mult/variation)
    n_transactions: tuple[int, int]  # (min, max) antal txns
    merchants: list[str]
    cost_mult_kind: str = "food"  # vilken stad-multiplikator som gäller


def _lookup_age_value(age: int, table: list[tuple[range, int]]) -> int:
    for r, v in table:
        if age in r:
            return v
    return table[-1][1]


def _persons_in_household(profile: GeneratedProfile) -> int:
    n = 1
    if profile.family.partner_yrke_key:
        n += 1
    n += profile.family.children_count
    return n


def _baseline_for_household(profile: GeneratedProfile) -> dict[str, int]:
    """Konsumentverket-baseline för (mat, individ-övrigt, mediter, nöje)."""
    age = profile.facts.get("age", 30)
    persons = _persons_in_household(profile)

    mat = _lookup_age_value(age, MAT_HEMMA_PER_AGE)
    if profile.family.partner_yrke_key:
        # Antar partnern är samma åldersgrupp ±5 år
        mat += _lookup_age_value(age, MAT_HEMMA_PER_AGE)
    for c_age in profile.family.children_ages:
        mat += _lookup_age_value(c_age, MAT_HEMMA_PER_AGE)

    individ = _lookup_age_value(age, INDIVID_OVRIGT_PER_AGE)
    if profile.family.partner_yrke_key:
        individ += _lookup_age_value(age, INDIVID_OVRIGT_PER_AGE)
    for c_age in profile.family.children_ages:
        individ += _lookup_age_value(c_age, INDIVID_OVRIGT_PER_AGE)

    forbruk_arr = GEMENSAMT_PER_PERSONER["förbrukningsvaror"]
    idx = max(0, min(len(forbruk_arr) - 1, persons - 1))
    forbruk = forbruk_arr[idx]

    return {"mat": mat, "individ": individ, "forbruk": forbruk}


def _plans_for(
    rng: random.Random,
    profile: GeneratedProfile,
    spend_profile: str,
    starting_level: int,
) -> list[CategoryPlan]:
    """Bygger CategoryPlan-lista för månaden."""
    from ..difficulty import get_difficulty
    base = _baseline_for_household(profile)
    base_mult = SPEND_MULTIPLIER.get(spend_profile, 1.0)
    # Difficulty-amplifiering av spend-profile-spread
    diff = get_difficulty(starting_level)
    if diff.spend_profile_amplifier != 1.0:
        mult = 1.0 + (base_mult - 1.0) * diff.spend_profile_amplifier
    else:
        mult = base_mult
    variation = VARIATION_PER_LEVEL.get(starting_level, 0.10)
    city = STAD_BY_KEY.get(profile.city_key)
    food_mult = city.cost_multiplier_food if city else 1.0
    transport_mult = city.cost_multiplier_transport if city else 1.0

    def _vary(amount: int) -> int:
        return max(0, int(amount * mult * (1 + rng.uniform(-variation, variation))))

    persons = _persons_in_household(profile)

    plans = [
        CategoryPlan(
            name="Mat & livsmedel",
            monthly_amount=_vary(int(base["mat"] * food_mult)),
            n_transactions=(4, 8),
            merchants=["ICA", "Coop", "Willys", "Hemköp", "Lidl"],
            cost_mult_kind="food",
        ),
        CategoryPlan(
            name="Restaurang & café",
            monthly_amount=_vary(int(900 * food_mult * persons * 0.7)),
            n_transactions=(2, 6),
            merchants=[
                "Espresso House", "Wayne's Coffee", "Joe & The Juice",
                "Max", "MAX Burgers", "Sushi Yama", "Pizzeria",
            ],
            cost_mult_kind="food",
        ),
        CategoryPlan(
            name="Kläder & skor",
            monthly_amount=_vary(int(base["individ"] * 0.20)),
            n_transactions=(1, 3),
            merchants=["H&M", "Lindex", "Zalando", "Stadium", "Åhléns"],
        ),
        CategoryPlan(
            name="Hälsa & hygien",
            monthly_amount=_vary(int(base["individ"] * 0.15)),
            n_transactions=(1, 3),
            merchants=["Apoteket", "Lyko", "Apotek Hjärtat"],
        ),
        CategoryPlan(
            name="Förbrukningsvaror",
            monthly_amount=_vary(base["forbruk"]),
            n_transactions=(1, 3),
            merchants=["Rusta", "Jula", "Clas Ohlson"],
        ),
        CategoryPlan(
            name="Nöje & fritid",
            monthly_amount=_vary(int(profile.facts.get("budget_for_leisure", 1500))),
            n_transactions=(2, 5),
            merchants=[
                "Spotify", "Netflix", "Bio Rio", "SF Bio",
                "Konsert", "Streaming", "Padelbana",
            ],
        ),
        CategoryPlan(
            name="Transport (övrigt)",
            monthly_amount=_vary(int(350 * transport_mult)),
            n_transactions=(1, 4),
            merchants=["Uber", "Bolt", "Voi", "SJ", "Taxi Stockholm"],
            cost_mult_kind="transport",
        ),
    ]

    if profile.family.children_count > 0:
        plans.append(CategoryPlan(
            name="Barn & familj",
            monthly_amount=_vary(700 + 300 * profile.family.children_count),
            n_transactions=(2, 5),
            merchants=["Babyland", "Lekia", "BR Leksaker"],
        ))

    return plans


def _split_amount(
    rng: random.Random, total: int, n: int,
) -> list[int]:
    """Dela `total` i `n` poster där varje post >= 1."""
    if n <= 1 or total <= n:
        return [total]
    # Slumpa n cut-points i (0, total)
    cuts = sorted(rng.sample(range(1, total), min(n - 1, total - 1)))
    parts: list[int] = []
    prev = 0
    for c in cuts:
        parts.append(c - prev)
        prev = c
    parts.append(total - prev)
    return parts


def _hash_for_tx(scope: str, year_month: str, plan_name: str, idx: int) -> str:
    raw = f"{scope}|{year_month}|var|{plan_name}|{idx}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def generate_variable_expenses(
    s: Session,
    *,
    profile: GeneratedProfile,
    year_month: str,
    salary_account: Account,
    student_scope: str,
    spend_profile: str = "balanserad",
    starting_level: int = 1,
    rng: Optional[random.Random] = None,
    release_base: Optional[datetime] = None,
) -> dict:
    """Skapa variabla transaktioner sprida över spelmånaden.

    Lika seed → lika månadsmönster (rng-deterministiskt). Använder
    `student_scope` + `year_month` som rng-seed-källa om ingen rng ges.
    """
    rng = rng or random.Random(f"{student_scope}|{year_month}|var")

    plans = _plans_for(rng, profile, spend_profile, starting_level)
    # Difficulty-extra-multiplikator (Fas 8b): nivå 3 har högre
    # impulsköp + småutgifter eleven inte planerar för
    diff = get_difficulty(starting_level)
    if diff.variable_spend_extra_mult != 1.0:
        plans = [
            type(p)(
                name=p.name,
                monthly_amount=int(p.monthly_amount * diff.variable_spend_extra_mult),
                n_transactions=p.n_transactions,
                merchants=p.merchants,
                cost_mult_kind=p.cost_mult_kind,
            )
            for p in plans
        ]

    y, m = map(int, year_month.split("-"))
    # Beräkna antal dagar i månaden (förenklat: sista dag i ms_to_date)
    if m == 12:
        next_first = date(y + 1, 1, 1)
    else:
        next_first = date(y, m + 1, 1)
    days_in_month = (next_first - date(y, m, 1)).days

    created_tx: list[int] = []
    by_category: dict[str, dict] = {}
    grand_total = 0

    for plan in plans:
        if plan.monthly_amount <= 0:
            continue
        n = rng.randint(*plan.n_transactions)
        amounts = _split_amount(rng, plan.monthly_amount, n)
        # Säkerställ att kategorin EXISTERAR i scope-DB:n så eleven
        # senare kan välja den vid manuell klassning. Men vi sätter
        # INTE category_id på tx — pedagogiken är att eleven ska
        # själv klassificera sina variabla utgifter (mat, kläder,
        # nöje etc.) via Bokföring-vyn.
        get_or_create_category(s, plan.name)
        cat_total = 0

        for idx, amt in enumerate(amounts):
            day = rng.randint(1, days_in_month)
            tx_date = date(y, m, day)
            merchant = rng.choice(plan.merchants)
            released_at = (
                release_at_for_day(release_base, day)
                if release_base is not None
                else None
            )
            tx = Transaction(
                account_id=salary_account.id,
                date=tx_date,
                amount=Decimal(-amt),  # Utgift = negativ
                currency="SEK",
                raw_description=f"{merchant} {tx_date.isoformat()}",
                normalized_merchant=merchant,
                category_id=None,  # Eleven klassar själv
                hash=_hash_for_tx(student_scope, year_month, plan.name, idx),
                user_verified=False,
                released_at=released_at,
            )
            s.add(tx)
            s.flush()
            created_tx.append(tx.id)
            cat_total += amt

        by_category[plan.name] = {
            "total": cat_total,
            "n_transactions": len(amounts),
        }
        grand_total += cat_total

    return {
        "transactions_created": len(created_tx),
        "tx_ids": created_tx,
        "total_amount": grand_total,
        "by_category": by_category,
    }
