"""Profile Generator · huvudfunktion `generate_profile()`.

Spec: dev/game-motor/02-profile-generator.md

Pipeline:
  1. Slumpa yrke (viktat efter arketyp + startnivå)
  2. Slumpa stad (viktat efter städernas weight)
  3. Slumpa familj (ensam/sambo/barn) + ev. partner-yrke
  4. Räkna individ-netto + hushålls-netto via skola/tax.py
  5. Matcha boende mot hushålls-netto + stad
  6. Härled profil-fakta (housing_pct, age, has_chronic, etc.)
  7. Räkna initial pentagon från fakta
  8. Returnera GeneratedProfile (Pydantic)
"""
from __future__ import annotations

import random
import time
from typing import Optional

from ...school.tax import compute_net_salary
from ..pools.stadspool import pick_city_weighted
from ..pools.yrkespool import (
    YRKE_BY_KEY,
    pick_yrke_by_archetype,
)
from .family_picker import pick_family
from .housing_match import pick_housing
from .pentagon_init import compute_initial_pentagon
from .schema import GeneratedProfile, PartnerModel


# Sannolikhet för olika livsfakta (slumpas oberoende)
P_CHRONIC_CONDITION = 0.10
P_TEMPORARY_EMPLOYMENT = 0.15
P_HEALTH_INSURANCE = 0.45
P_HIGH_COST_CREDIT = 0.12
P_SAVINGS_BUFFER = 0.40
P_STUDENT_LOAN_BY_EDU = {
    "ingen": 0.00,
    "gymnasium": 0.05,
    "yh": 0.55,
    "hogskola": 0.85,
    "doktor": 0.95,
}


def _resolve_seed(seed: Optional[int]) -> int:
    if seed is None:
        return int(time.time_ns() & 0x7FFFFFFF)
    return int(seed)


def _commute_minutes(rng: random.Random, city_job_density: float) -> int:
    """Större städer = längre pendling i snitt."""
    if city_job_density >= 1.3:
        return rng.randint(15, 75)
    if city_job_density >= 1.0:
        return rng.randint(10, 55)
    return rng.randint(5, 35)


def _age_for_level(rng: random.Random, level: int, edu: str) -> int:
    """Lägg startålder mellan 22-55 baserat på nivå + utbildning."""
    base = {1: 24, 2: 32, 3: 42}.get(level, 28)
    edu_bonus = {"hogskola": 2, "doktor": 6, "yh": 1}.get(edu, 0)
    return base + edu_bonus + rng.randint(-3, 5)


def generate_profile(
    *,
    seed: Optional[int] = None,
    archetype: str = "random",
    starting_level: int = 1,
    name: str = "Förhandsvisning",
    partner_model: PartnerModel = "solo",
) -> GeneratedProfile:
    """Generera en komplett karaktär.

    Determinism: samma `seed` + samma argument = samma profil. Det
    gäller även när poolerna ändras — men nya yrken/städer kan ändra
    fördelningen. Säkraste är att låsa både seed OCH pool-version.
    """
    actual_seed = _resolve_seed(seed)
    rng = random.Random(actual_seed)

    # 1. Yrke
    yrke = pick_yrke_by_archetype(rng, archetype, starting_level)  # type: ignore[arg-type]
    gross = rng.randint(yrke.monthly_gross_min, yrke.monthly_gross_max)
    net = compute_net_salary(gross).net_monthly

    # 2. Stad — yrkespoolen har inte längre city_preference, så enkel vikt-pick
    city = pick_city_weighted(rng)

    # 3. Familj
    family = pick_family(
        rng,
        partner_model=partner_model,
        starting_level=starting_level,
    )

    # 4. Hushållets ekonomi
    household_gross = gross + (family.partner_gross_monthly or 0)
    if family.partner_gross_monthly:
        partner_net = compute_net_salary(family.partner_gross_monthly).net_monthly
    else:
        partner_net = 0
    household_net = net + partner_net

    # 5. Boende
    housing = pick_housing(
        rng,
        city=city,
        family_status=family.status,
        children=family.children_count,
        household_net_monthly=household_net,
    )

    # 6. Profil-fakta
    age = _age_for_level(rng, starting_level, yrke.education_level)
    commute = _commute_minutes(rng, city.job_density)
    p_csn = P_STUDENT_LOAN_BY_EDU.get(yrke.education_level, 0.0)
    has_csn = rng.random() < p_csn
    has_credit = rng.random() < P_HIGH_COST_CREDIT
    has_savings = rng.random() < P_SAVINGS_BUFFER
    has_chronic = rng.random() < P_CHRONIC_CONDITION
    is_temp = (
        starting_level == 1
        and rng.random() < P_TEMPORARY_EMPLOYMENT
        and yrke.collective_agreement is not None
    )
    has_health_ins = (
        yrke.collective_agreement is not None
        and rng.random() < P_HEALTH_INSURANCE
    )

    # Fritidsbudget = grovt 8 % av nettolön (svensk genomsnitt ~6-10 %)
    leisure_budget = int(household_net * 0.08)

    facts = {
        "age": age,
        "commute_minutes": commute,
        "housing_pct": (
            housing.monthly_cost / household_net if household_net else 0.0
        ),
        "has_student_loan": has_csn,
        "has_high_cost_credit": has_credit,
        "has_savings_buffer": has_savings,
        "has_chronic_condition": has_chronic,
        "competency_match_with_yrke": bool(yrke.competency_match),
        "collective_agreement": yrke.collective_agreement is not None,
        "is_temporary_employment": is_temp,
        "low_job_density_city": city.job_density < 0.8,
        "has_health_insurance": has_health_ins,
        "physical_demand": yrke.physical_demand,
        "schedule_irregularity": yrke.schedule_irregularity,
        "family_status": family.status,
        "has_children": family.children_count > 0,
        "budget_for_leisure": leisure_budget,
    }

    pentagon = compute_initial_pentagon(facts)

    return GeneratedProfile(
        seed=actual_seed,
        name=name,
        yrke_key=yrke.key,
        yrke_display=yrke.display,
        yrke_ssyk=yrke.ssyk,
        monthly_gross=gross,
        monthly_net=net,
        city_key=city.key,
        city_display=city.display,
        region=city.region,
        housing=housing,
        family=family,
        household_gross_monthly=household_gross,
        household_net_monthly=household_net,
        pentagon=pentagon,
        facts=facts,
    )


__all__ = ["generate_profile"]
