"""Seed initial budget från Konsumentverkets schabloner.

Anropas vid student-skapande (`_seed_initial_student_data`) så eleven
får en fungerande startbudget redan vid första inloggningen — och
första onboarding-uppdraget "Skapa din budget" kan starta från KV-
referensen istället för en tom tabell.

Mappar `BudgetSuggestion`-fälten (från school.konsumentverket) till
elevens default-kategorinamn så Budget-rader skapas med rätt
category_id. Sparar budgets som NEGATIVA värden för utgifter
(konsistent med transaktionstecken).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from ..db.models import Budget, Category
from ..game_engine.profile_generator.schema import GeneratedProfile
from ..school.konsumentverket import BudgetSuggestion, suggest_budget


# Mappning från BudgetSuggestion-fält → elev-kategorinamn.
# Samma kategorier som variable_expenses.py + fixed_expenses.py
# använder, så onboarding-budgeten ligger i nivå med actuals direkt
# första månaden.
_FIELD_TO_CATEGORY: list[tuple[str, str]] = [
    ("mat",                "Mat & livsmedel"),
    ("forbrukningsvaror",  "Förbrukningsvaror"),
    ("hemutrustning",      "Hemutrustning"),
    ("el",                 "Hushållsel"),
    ("bredband_mobil",     "Internet & mobil"),
    ("medietjanster",      "Strömningstjänster"),
    ("vatten_avlopp",      "Vatten"),
    ("hemforsakring",      "Hemförsäkring"),
    ("transport",          "Transport (övrigt)"),
]


# `individuellt_ovrigt` är aggregerad — bryt ned i de tre viktigaste
# delposterna (kläder, hygien, fritid) enligt KV-PDF:s andelar.
_INDIV_SPLIT: list[tuple[float, str]] = [
    (0.27, "Kläder & skor"),
    (0.18, "Hälsa & hygien"),
    (0.32, "Nöje & fritid"),
    # Resterande ~23 % är försäkringar/sjukvård/övrigt, hamnar i
    # "Restaurang & café"-bufferten via nojen_marginal.
]


def _get_or_create_category(s: Session, name: str) -> Category:
    cat = s.query(Category).filter(Category.name == name).first()
    if cat is not None:
        return cat
    cat = Category(name=name)
    s.add(cat)
    s.flush()
    return cat


def _set_budget_if_missing(
    s: Session, year_month: str, category_id: int, planned: Decimal,
) -> bool:
    """Sätter Budget-rad om den saknas. Returnerar True om något
    skrevs. Idempotent — överskriver inte elevens egna val."""
    existing = (
        s.query(Budget)
        .filter(
            Budget.month == year_month,
            Budget.category_id == category_id,
        )
        .first()
    )
    if existing is not None:
        return False
    s.add(Budget(
        month=year_month,
        category_id=category_id,
        planned_amount=planned,
    ))
    s.flush()
    return True


def seed_initial_budget(
    s: Session,
    *,
    profile: GeneratedProfile,
    year_month: str,
) -> dict:
    """Skapa Budget-rader för en månad från KV-schabloner enligt
    elevens hushålls-profil.

    Idempotent — befintliga budget-rader rörs INTE (eleven kan ha
    justerat dem manuellt). Returnerar metadata om hur många rader
    som skapades.
    """
    # === Hämta KV-suggestion utifrån faktisk profil ===
    fam = profile.family
    children_ages = list(fam.children_ages or [])
    age = int(profile.facts.get("age", 30))
    partner_age = age if fam.partner_yrke_key else None

    has_mortgage = profile.housing.type in ("bostadsratt", "villa", "radhus")
    sug: BudgetSuggestion = suggest_budget(
        adult_age=age,
        partner_age=partner_age,
        children_ages=children_ages,
        housing_type=(
            "hyresratt" if profile.housing.type == "hyresratt"
            else "bostadsratt" if profile.housing.type == "bostadsratt"
            else "villa"
        ),
        housing_monthly=int(profile.housing.monthly_cost or 0),
        has_mortgage=has_mortgage,
        has_car_loan=False,
        has_student_loan=bool(
            profile.facts.get("has_student_loan", False),
        ),
        net_salary_monthly=int(profile.monthly_net or 0),
    )

    created = 0
    skipped = 0

    # === Direkta fält → en kategori ===
    for field, cat_name in _FIELD_TO_CATEGORY:
        amount = int(getattr(sug, field, 0) or 0)
        if amount <= 0:
            continue
        cat = _get_or_create_category(s, cat_name)
        # Budgetar för utgifter lagras NEGATIVA internt.
        if _set_budget_if_missing(
            s, year_month, cat.id, -Decimal(amount),
        ):
            created += 1
        else:
            skipped += 1

    # === Individuellt övrigt → split i tre delkategorier ===
    indiv_total = int(sug.individuellt_ovrigt or 0)
    if indiv_total > 0:
        for share, cat_name in _INDIV_SPLIT:
            amount = int(round(indiv_total * share))
            if amount <= 0:
                continue
            cat = _get_or_create_category(s, cat_name)
            if _set_budget_if_missing(
                s, year_month, cat.id, -Decimal(amount),
            ):
                created += 1
            else:
                skipped += 1

    # === Restaurang & café · KV-bufferten (nöjesmarginal) ===
    # Den rest som blir kvar efter fasta utgifter (= profile.facts'
    # nöjesutrymme). Visas pedagogiskt så eleven ser att restaurang/
    # nöje är det första som kapas vid bristande budget.
    rest_amount = max(0, int(sug.nojen_marginal or 0) // 3)
    if rest_amount > 0:
        cat = _get_or_create_category(s, "Restaurang & café")
        if _set_budget_if_missing(
            s, year_month, cat.id, -Decimal(rest_amount),
        ):
            created += 1
        else:
            skipped += 1

    # === Sparmål (Sparande som inkomst-stil mål) ===
    # Ej en utgiftskategori — vi skapar en Goal istället via separat
    # endpoint. Här bara registrera som budget-rad så elev ser i
    # /v2/budget vad KV rekommenderar att hen sätter undan.
    if sug.sparande and sug.sparande > 0:
        cat = _get_or_create_category(s, "Sparmål")
        if _set_budget_if_missing(
            s, year_month, cat.id, -Decimal(int(sug.sparande)),
        ):
            created += 1
        else:
            skipped += 1

    return {
        "created": created,
        "skipped_existing": skipped,
        "total_planned": (
            sug.total - sug.boende - sug.lan_amortering_ranta
        ),
    }


def seed_initial_budget_for_months(
    s: Session,
    *,
    profile: GeneratedProfile,
    year_months: Iterable[str],
) -> int:
    """Hjälpvariant — seeda budgeten för flera månader (t.ex. förra +
    innevarande) så eleven har realistiska KV-värden hela första
    historiken."""
    total_created = 0
    for ym in year_months:
        info = seed_initial_budget(s, profile=profile, year_month=ym)
        total_created += info["created"]
    return total_created
