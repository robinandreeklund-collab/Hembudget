"""Slumpa familjekonfiguration · ensam / sambo / familj_med_barn.

Spec: dev/game-motor/02-profile-generator.md steg 5.
"""
from __future__ import annotations

import random

from ..pools.yrkespool import pick_yrke_by_archetype
from .schema import FamilyChoice, FamilyStatus, PartnerModel


# Sannolikheter (spec)
FAMILY_WEIGHTS: dict[FamilyStatus, float] = {
    "ensam": 0.70,
    "sambo": 0.20,
    "familj_med_barn": 0.10,
}

# Antal barn vid familj_med_barn
CHILDREN_COUNT_WEIGHTS: dict[int, float] = {1: 0.60, 2: 0.30, 3: 0.10}


def _resolve_partner_model(rng: random.Random, requested: PartnerModel) -> PartnerModel:
    if requested != "auto":
        return requested
    # 80 % AI-partner när "auto", 20 % klasskompis-läge.
    return rng.choices(["ai", "klasskompis"], weights=[0.8, 0.2], k=1)[0]


def pick_family(
    rng: random.Random,
    *,
    partner_model: PartnerModel = "solo",
    starting_level: int = 1,
) -> FamilyChoice:
    """Slumpa familjestatus + ev. partner + ev. barn.

    Om `partner_model == "solo"` tvingar vi `ensam` (singel-spel).
    """
    if partner_model == "solo":
        status: FamilyStatus = "ensam"
    else:
        status = rng.choices(
            list(FAMILY_WEIGHTS.keys()),
            weights=list(FAMILY_WEIGHTS.values()),
            k=1,
        )[0]

    children_count = 0
    children_ages: list[int] = []
    if status == "familj_med_barn":
        children_count = rng.choices(
            list(CHILDREN_COUNT_WEIGHTS.keys()),
            weights=list(CHILDREN_COUNT_WEIGHTS.values()),
            k=1,
        )[0]
        children_ages = [rng.randint(0, 18) for _ in range(children_count)]

    partner_yrke_key: str | None = None
    partner_gross: int | None = None
    resolved_partner_model: PartnerModel = "solo"
    if status in ("sambo", "familj_med_barn"):
        resolved_partner_model = _resolve_partner_model(rng, partner_model)
        partner = pick_yrke_by_archetype(rng, "random", starting_level)
        partner_yrke_key = partner.key
        partner_gross = rng.randint(
            partner.monthly_gross_min, partner.monthly_gross_max,
        )

    return FamilyChoice(
        status=status,
        partner_model=resolved_partner_model,
        partner_yrke_key=partner_yrke_key,
        partner_gross_monthly=partner_gross,
        children_count=children_count,
        children_ages=children_ages,
    )
