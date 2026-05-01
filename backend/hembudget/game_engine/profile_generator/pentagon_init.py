"""Initial pentagon-beräkning · ger varje karaktär en unik startposition.

Spec: dev/game-motor/02-profile-generator.md steg 6.

Baslinje 60 per axel, modifierare ±3 till ±8 per fakta. Klampas till
45-80 så ingen startar i ett "omöjligt" läge eller med orealistisk topp.
"""
from __future__ import annotations

from .schema import GeneratedProfile, PentagonInit


BASELINE = 60
FLOOR = 45
CEILING = 80


def compute_initial_pentagon(profile_facts: dict) -> PentagonInit:
    """Beräknar pentagon från fakta-dict (måste innehålla nycklar enligt
    listan i `_facts_for_pentagon` i generator.py)."""
    p = {
        "economy": BASELINE,
        "safety": BASELINE,
        "health": BASELINE,
        "social": BASELINE,
        "leisure": BASELINE,
    }
    explanations: dict[str, list[str]] = {k: [] for k in p}

    def adj(axis: str, delta: int, why: str) -> None:
        p[axis] += delta
        explanations[axis].append(f"{'+' if delta >= 0 else ''}{delta}: {why}")

    # === ECONOMY ===
    housing_pct = profile_facts.get("housing_pct", 0.0)
    if housing_pct > 0.40:
        adj("economy", -8, "boende > 40 % av nettolön")
    elif housing_pct > 0.35:
        adj("economy", -5, "boende > 35 % av nettolön")
    if profile_facts.get("has_student_loan"):
        adj("economy", -3, "CSN-lån att amortera")
    if profile_facts.get("has_high_cost_credit"):
        adj("economy", -5, "dyrt konsumtionslån / kreditkortsskuld")
    if profile_facts.get("has_savings_buffer"):
        adj("economy", +3, "buffert > 1 månadslön")

    # === SAFETY (karriärtrygghet) ===
    if profile_facts.get("competency_match_with_yrke"):
        adj("safety", +5, "kompetens matchar yrket")
    if profile_facts.get("collective_agreement"):
        adj("safety", +3, "kollektivavtal")
    if profile_facts.get("is_temporary_employment"):
        adj("safety", -5, "vikariat / tidsbegränsad anställning")
    if profile_facts.get("low_job_density_city"):
        adj("safety", -3, "tunn lokal arbetsmarknad")

    # === HEALTH ===
    if profile_facts.get("has_chronic_condition"):
        adj("health", -3, "kronisk åkomma")
    commute = profile_facts.get("commute_minutes", 0)
    if commute > 60:
        adj("health", -2, "lång pendling > 60 min")
    if profile_facts.get("has_health_insurance"):
        adj("health", +2, "sjukförsäkring via jobb")
    physical = profile_facts.get("physical_demand", 5)
    if physical >= 8:
        adj("health", -2, "fysiskt krävande yrke")

    # === SOCIAL (relationer) ===
    family_status = profile_facts.get("family_status", "ensam")
    age = profile_facts.get("age", 25)
    if family_status == "sambo":
        adj("social", +5, "sambo")
    if family_status == "familj_med_barn":
        adj("social", +8, "familj med barn")
    if family_status == "ensam" and age > 30:
        adj("social", -3, "singel över 30")
    schedule = profile_facts.get("schedule_irregularity", 5)
    if schedule >= 8:
        adj("social", -2, "OB / skift försvårar fasta umgängestider")

    # === LEISURE (fritid) ===
    if commute > 60:
        adj("leisure", -4, "pendling stjäl fritid")
    if profile_facts.get("has_children"):
        adj("leisure", -3, "barn = mindre egen tid")
    if profile_facts.get("budget_for_leisure", 0) < 1500:
        adj("leisure", -2, "tunn fritidsbudget")
    if profile_facts.get("budget_for_leisure", 0) > 3000:
        adj("leisure", +2, "rejäl fritidsbudget")

    # Klampa
    clamped = {k: max(FLOOR, min(CEILING, v)) for k, v in p.items()}

    return PentagonInit(
        economy=clamped["economy"],
        safety=clamped["safety"],
        health=clamped["health"],
        social=clamped["social"],
        leisure=clamped["leisure"],
        explanations=explanations,
    )
