"""Sjuk-/VAB-roller för Monthly Engine.

Spec: dev/game-motor/03-monthly-engine.md (Fas H · ny i denna patch)

Pipeline per spelmånad:
  1. Slumpa sjukperioder för eleven (sannolikhet baserat på fysiskt
     krävande yrke + säsong)
  2. Slumpa VAB-dagar (om eleven har barn under 12)
  3. Räkna lönepåverkan via apply_sick_pay_reduction
  4. Skapa MailItem (sjukanmälan från arbetsgivare / FK-utbetalning)
  5. Skapa Transaction (lön-justering för sjukperioden)
  6. Pentagon-delta: -health, -economy (mindre lön), -leisure (utmattning),
     +safety något om sambo hjälper, -safety vid längre sjuk
  7. Logga EmployerSatisfactionEvent (master-DB) så befintlig satisfaction-
     score speglar frånvaron
"""
from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ...db.models import Account, MailItem, Transaction
from ..difficulty import get_difficulty
from ..pentagon import apply_pentagon_delta
from ..profile_generator.schema import GeneratedProfile

log = logging.getLogger(__name__)


# === Konstanter (svenska 2026) ===

# Genomsnittlig sannolikhet att eleven är sjuk någon dag per månad,
# baserat på Arbetsgivarverkets 4.7 % sjukfrånvaro.
P_SICK_PER_MONTH_BASELINE = 0.30  # 30 % chans att månaden innehåller sjuk
SICK_DAYS_RANGE = (1, 14)  # min-max dagar per sjukperiod (kort=vanligast)

# Säsongsfaktorer · vinter (jan-mars + okt-dec) = mer sjuk
SEASON_MULT = {
    1: 1.6, 2: 1.7, 3: 1.4, 4: 1.0, 5: 0.8, 6: 0.6,
    7: 0.5, 8: 0.6, 9: 0.9, 10: 1.2, 11: 1.4, 12: 1.5,
}

# Fysisk-demand-faktor · högre demand = mer sjuk
def _physical_factor(physical_demand: int) -> float:
    return 0.7 + (physical_demand / 10) * 0.6  # 0.7 till 1.3

# Sannolikhet att en sjukperiod blir LÅNG (>14 dagar = sjukpenning från FK)
P_LONG_SICK = 0.04  # 4 % av sjukperioder

# VAB-statistik (FK 2023)
P_VAB_PER_CHILD_PER_MONTH = 0.45  # genomsnittlig sannolikhet
VAB_DAYS_RANGE = (1, 5)  # 1-5 dagar per VAB-tillfälle (norm)
VAB_SEASON_MULT = {
    1: 2.2, 2: 2.5, 3: 1.8, 4: 1.0, 5: 0.6, 6: 0.4,
    7: 0.4, 8: 0.5, 9: 1.3, 10: 1.4, 11: 1.6, 12: 1.7,
}

# Sjuklön
KARENSAVDRAG_FRAC_OF_WEEK = 0.20    # Karensavdrag = 20 % × snittveckans lön
SICK_PAY_DAY2_14_PCT = 0.80         # Arbetsgivare betalar 80 % dag 2-14
SICK_PENSION_PCT = 0.80              # FK sjukpenning = 80 % av SGI
SICK_PENSION_DAILY_MAX = 1209       # 2026-tak

# VAB-ersättning (samma som sjukpenning för anställda)
VAB_PAY_PCT = 0.80


@dataclass(frozen=True)
class HealthEvent:
    """En slumpbar mall för hälso-/VAB-händelse."""
    key: str
    display: str
    kind: str  # "sick_short" | "sick_long" | "vab"


SICK_EVENT_TEMPLATES = [
    HealthEvent(key="sick_short_cold", display="Förkylning · 2-5 dagar", kind="sick_short"),
    HealthEvent(key="sick_short_flu", display="Influensa · 5-10 dagar", kind="sick_short"),
    HealthEvent(key="sick_short_stomach", display="Magsjuka · 1-3 dagar", kind="sick_short"),
    HealthEvent(key="sick_short_headache", display="Migrän · 1-2 dagar", kind="sick_short"),
    HealthEvent(key="sick_long_burnout", display="Utmattnings-syndrom · 30+ dagar", kind="sick_long"),
    HealthEvent(key="sick_long_back", display="Ryggåkomma · 21-45 dagar", kind="sick_long"),
    HealthEvent(key="vab_kid_fever", display="VAB · barnet har feber", kind="vab"),
    HealthEvent(key="vab_kid_rs", display="VAB · RS-virus", kind="vab"),
    HealthEvent(key="vab_kid_stomach", display="VAB · vinterkräksjuka", kind="vab"),
]

SHORT_SICK_TEMPLATES = [t for t in SICK_EVENT_TEMPLATES if t.kind == "sick_short"]
LONG_SICK_TEMPLATES = [t for t in SICK_EVENT_TEMPLATES if t.kind == "sick_long"]
VAB_TEMPLATES = [t for t in SICK_EVENT_TEMPLATES if t.kind == "vab"]


@dataclass
class HealthOccurrence:
    """En genomförd hälso-händelse med all spårbar data."""
    template: HealthEvent
    n_days: int
    occurred_on: date
    gross_loss: int           # Bruttolön man förlorar (karens + ev. tak-cap)
    pentagon_delta: dict[str, int]
    mail_id: Optional[int]
    tx_id: Optional[int]


def _ym_to_date(year_month: str, day: int) -> date:
    y, m = map(int, year_month.split("-"))
    return date(y, m, min(day, 28))


def _ym_month(year_month: str) -> int:
    return int(year_month.split("-")[1])


def _stable_hash(scope: str, year_month: str, key: str, idx: int) -> str:
    raw = f"{scope}|{year_month}|health|{key}|{idx}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def apply_sick_pay_reduction(
    *,
    monthly_gross: int,
    sick_days: int,
    is_vab: bool = False,
) -> tuple[int, dict]:
    """Räkna förlust i bruttolön för en sjukperiod / VAB.

    Returnerar (gross_loss, breakdown).

    Sjuk:
      Dag 1: karensavdrag (~20 % av snittveckans lön)
      Dag 2-14: arbetsgivaren betalar 80 % → 20 % bortfall per dag
      Dag 15+: FK-sjukpenning 80 % av SGI (cap 1209 kr/dag),
               vilket motsvarar ~20 % förlust för normallöner
               och MER för höglönere (taket biter)

    VAB: ingen karens, 80 % från dag 1 → 20 % bortfall per dag
    """
    if sick_days <= 0:
        return 0, {"karens": 0, "dag2_14": 0, "dag15_plus": 0}

    daily_gross = monthly_gross / 21.5  # Genomsnittlig arbetsdag

    breakdown = {"karens": 0, "dag2_14": 0, "dag15_plus": 0}

    if is_vab:
        # VAB · ingen karens, 80 % från dag 1
        loss = int(daily_gross * (1 - VAB_PAY_PCT) * sick_days)
        breakdown["dag2_14"] = loss
        return loss, breakdown

    # SJUK
    # Dag 1: karens
    weekly_gross = monthly_gross / 4.33
    karens = int(weekly_gross * KARENSAVDRAG_FRAC_OF_WEEK)
    breakdown["karens"] = karens
    if sick_days == 1:
        return karens, breakdown

    # Dag 2-14: 20 % förlust
    days_2_14 = min(sick_days - 1, 13)
    dag2_14_loss = int(daily_gross * (1 - SICK_PAY_DAY2_14_PCT) * days_2_14)
    breakdown["dag2_14"] = dag2_14_loss

    # Dag 15+: SGI-cap kan bita
    dag15_plus = max(0, sick_days - 14)
    if dag15_plus > 0:
        # Vad arbetsgivaren skulle ha betalat (= daily_gross × 100%)
        full_daily = daily_gross
        # FK ger 80 % av SGI, dock max 1209 kr/dag
        sgi_daily = min(full_daily * SICK_PENSION_PCT, SICK_PENSION_DAILY_MAX)
        per_day_loss = full_daily - sgi_daily
        breakdown["dag15_plus"] = int(per_day_loss * dag15_plus)

    total = sum(breakdown.values())
    return total, breakdown


def _roll_sick_episodes(
    rng: random.Random,
    *,
    profile: GeneratedProfile,
    year_month: str,
    difficulty_level: int = 2,
) -> list[tuple[HealthEvent, int]]:
    """Slumpa sjukperioder för månaden. Returnerar lista av (template, n_days).

    `difficulty_level` skalar både sannolikheten för sjuk och chansen att
    sjukperioden blir lång (utbrändhet/rygg).
    """
    diff = get_difficulty(difficulty_level)
    month = _ym_month(year_month)
    base_p = P_SICK_PER_MONTH_BASELINE * SEASON_MULT.get(month, 1.0)
    base_p *= _physical_factor(profile.facts.get("physical_demand", 5))
    base_p *= diff.sick_probability_mult

    episodes: list[tuple[HealthEvent, int]] = []
    if rng.random() < base_p:
        long_p = P_LONG_SICK * diff.long_sick_probability_mult
        if rng.random() < long_p:
            tpl = rng.choice(LONG_SICK_TEMPLATES)
            n_days = rng.randint(21, 45)
        else:
            tpl = rng.choice(SHORT_SICK_TEMPLATES)
            n_days = rng.randint(*SICK_DAYS_RANGE)
        episodes.append((tpl, n_days))
    return episodes


def _roll_vab_episodes(
    rng: random.Random,
    *,
    profile: GeneratedProfile,
    year_month: str,
    difficulty_level: int = 2,
) -> list[tuple[HealthEvent, int]]:
    """Slumpa VAB-tillfällen för månaden om eleven har barn under 12."""
    if profile.family.children_count == 0:
        return []
    young_kids = [
        a for a in profile.family.children_ages if a < 12
    ]
    if not young_kids:
        return []

    diff = get_difficulty(difficulty_level)
    month = _ym_month(year_month)
    season = VAB_SEASON_MULT.get(month, 1.0)

    episodes: list[tuple[HealthEvent, int]] = []
    for _ in young_kids:
        p = P_VAB_PER_CHILD_PER_MONTH * season * diff.vab_probability_mult
        if rng.random() < p:
            tpl = rng.choice(VAB_TEMPLATES)
            n_days = rng.randint(*VAB_DAYS_RANGE)
            episodes.append((tpl, n_days))
    return episodes


def _create_mail_for_episode(
    *,
    template: HealthEvent,
    n_days: int,
    gross_loss: int,
    occurred_on: date,
) -> MailItem:
    is_vab = template.kind == "vab"
    sender = "Försäkringskassan" if is_vab else "Arbetsgivaren"
    sender_short = "FK" if is_vab else "WORK"
    sender_kind = "skv" if is_vab else "work"

    body = (
        f"{template.display}\n\n"
        f"Antal dagar: {n_days}\n"
        f"Bortfall i lön: {gross_loss:,} kr brutto\n".replace(",", " ")
    )
    if is_vab:
        body += (
            "Tillfällig föräldrapenning ~80 % av SGI utbetalas. "
            "Ingen karensdag.\n"
        )
    elif n_days <= 1:
        body += "Karensavdrag dag 1.\n"
    elif n_days <= 14:
        body += "Karens dag 1 + 80 % sjuklön dag 2-14.\n"
    else:
        body += (
            "Karens dag 1 + sjuklön dag 2-14 + sjukpenning från "
            "Försäkringskassan dag 15 framåt.\n"
        )

    return MailItem(
        sender=sender,
        sender_short=sender_short,
        sender_kind=sender_kind,
        sender_meta=f"frånvaro · {occurred_on.isoformat()}",
        mail_type="info",
        subject=template.display,
        body_meta=f"Bortfall {gross_loss:,} kr brutto".replace(",", " "),
        body=body,
        amount=Decimal(-gross_loss) if gross_loss > 0 else None,
        due_date=None,
        status="unhandled",
    )


def _pentagon_for_episode(
    template: HealthEvent,
    n_days: int,
) -> dict[str, int]:
    """Per-axel-effekt baserat på typ + längd."""
    if template.kind == "vab":
        return {
            "health": 0,                # Föräldern är inte sjuk
            "economy": -1 * max(1, n_days // 2),
            "social": +1,               # Hand med barnet
            "leisure": -2,              # Mindre egen tid
        }
    if template.kind == "sick_long":
        return {
            "health": -6,
            "economy": -4,
            "safety": -3,               # Karriär-osäkerhet
            "leisure": -3,              # Inte energi
            "social": -2,               # Isolering
        }
    # Kort sjukperiod
    return {
        "health": -2,
        "economy": -1,
        "leisure": -1,
    }


def apply_health_episode(
    s: Session,
    *,
    student_id: int,
    student_scope: str,
    profile: GeneratedProfile,
    template: HealthEvent,
    n_days: int,
    year_month: str,
    rng: random.Random,
    salary_account: Optional[Account] = None,
    idx: int = 0,
) -> HealthOccurrence:
    """Applicera en hälso-/VAB-händelse: lön-justering, mail, pentagon, log."""
    is_vab = template.kind == "vab"
    gross_loss, breakdown = apply_sick_pay_reduction(
        monthly_gross=profile.monthly_gross,
        sick_days=n_days,
        is_vab=is_vab,
    )

    day = rng.randint(2, 25)
    occurred = _ym_to_date(year_month, day)

    # Sjuk/VAB skapar INTE separat MailItem längre — det visas som rad
    # på lönespec-mailen istället (matchar verkligheten där löneavdrag
    # är en specifikationsrad, inte ett separat brev). Eleven ser ändå
    # händelsen via löneavdrags-Transaction i banken/bokföringen.
    tx_id: Optional[int] = None
    if salary_account is not None and gross_loss > 0:
        tx = Transaction(
            account_id=salary_account.id,
            date=occurred,
            amount=Decimal(-gross_loss),
            currency="SEK",
            raw_description=(
                f"Löneavdrag · {template.display} ({n_days} dagar)"
            ),
            normalized_merchant=(
                "Försäkringskassan" if is_vab else "Arbetsgivaren"
            ),
            hash=_stable_hash(student_scope, year_month, template.key, idx),
            user_verified=True,
        )
        s.add(tx)
        s.flush()
        tx_id = tx.id

    # Pentagon-delta · använd transaction som reason om vi har en,
    # annars logga utan reason_id (event-loggen visar ändå texten).
    pentagon_delta = _pentagon_for_episode(template, n_days)
    for axis, delta in pentagon_delta.items():
        if delta == 0:
            continue
        try:
            apply_pentagon_delta(
                student_id,
                axis=axis,
                requested_delta=delta,
                reason_kind="event",
                reason_id=tx_id or 0,
                reason_table="transactions" if tx_id else "health",
                explanation=f"{template.display} ({n_days} dagar)",
                year_month=year_month,
            )
        except Exception:
            log.exception("pentagon delta failed for health episode")

    # Logga i EmployerSatisfaction (om eleven har en rad)
    _log_employer_satisfaction(
        student_id=student_id,
        kind="vab" if is_vab else "sick",
        n_days=n_days,
        template_display=template.display,
    )

    return HealthOccurrence(
        template=template,
        n_days=n_days,
        occurred_on=occurred,
        gross_loss=gross_loss,
        pentagon_delta=pentagon_delta,
        mail_id=None,  # ingen separat MailItem längre · syns på lönespec
        tx_id=tx_id,
    )


def _log_employer_satisfaction(
    *,
    student_id: int,
    kind: str,
    n_days: int,
    template_display: str,
) -> None:
    """Logga frånvaro-event i master::employer_satisfaction_events.

    Score-effekt: korta sjukperioder ger mild dipp (-2 per tillfälle),
    långa ger större (-8). VAB är NEUTRAL för satisfaction (svensk norm).
    """
    try:
        from ...school.engines import master_session
        from ...school.employer_models import (
            EmployerSatisfaction,
            EmployerSatisfactionEvent,
        )

        if kind == "vab":
            delta = 0
            reason = (
                f"VAB ({n_days} dagar) — neutralt för satisfaction · "
                "förälder utövar lagstadgad rätt."
            )
        elif n_days >= 15:
            delta = -8
            reason = (
                f"Långtidssjukskrivning ({n_days} dagar) — tydlig påverkan "
                "på satisfaction. Arbetsgivaren saknar dig."
            )
        else:
            delta = -2
            reason = (
                f"Korttidssjukfrånvaro ({n_days} dagar) — mild påverkan "
                "på satisfaction."
            )

        with master_session() as s:
            sat = (
                s.query(EmployerSatisfaction)
                .filter(EmployerSatisfaction.student_id == student_id)
                .one_or_none()
            )
            if sat is None:
                # Skapa default-rad så framtida events har något att uppdatera
                sat = EmployerSatisfaction(student_id=student_id, score=70)
                s.add(sat)
                s.flush()

            sat.score = max(0, min(100, sat.score + delta))
            ev = EmployerSatisfactionEvent(
                student_id=student_id,
                kind=kind,
                delta_score=delta,
                reason_md=reason,
                meta={"days": n_days, "template": template_display},
            )
            s.add(ev)
            s.commit()
    except Exception:
        log.exception("logging EmployerSatisfaction failed")


def roll_monthly_health_events(
    s: Session,
    *,
    student_id: int,
    student_scope: str,
    profile: GeneratedProfile,
    year_month: str,
    rng: Optional[random.Random] = None,
    salary_account: Optional[Account] = None,
    difficulty_level: int = 2,
) -> list[HealthOccurrence]:
    """Huvudfunktion · slumpa sjuk + VAB för månaden, applicera allt."""
    rng = rng or random.Random(f"{student_scope}|{year_month}|health")
    occurrences: list[HealthOccurrence] = []

    sick = _roll_sick_episodes(
        rng, profile=profile, year_month=year_month,
        difficulty_level=difficulty_level,
    )
    vab = _roll_vab_episodes(
        rng, profile=profile, year_month=year_month,
        difficulty_level=difficulty_level,
    )

    for idx, (tpl, n_days) in enumerate(sick + vab):
        try:
            occ = apply_health_episode(
                s,
                student_id=student_id,
                student_scope=student_scope,
                profile=profile,
                template=tpl,
                n_days=n_days,
                year_month=year_month,
                rng=rng,
                salary_account=salary_account,
                idx=idx,
            )
            occurrences.append(occ)
        except Exception:
            log.exception("health episode failed")

    # Annotera lönespec-mailen för månaden med en frånvaro-sektion.
    # Då syns VAB/sjuk där (matchar verkligheten) istället för som
    # separata mail i postlådan.
    if occurrences:
        try:
            _annotate_salary_slip(s, year_month=year_month, occs=occurrences)
        except Exception:
            log.exception("salary-slip annotation failed")

    return occurrences


def _annotate_salary_slip(
    s: Session, *, year_month: str, occs: list[HealthOccurrence],
) -> None:
    """Lägg till en 'Frånvaro denna månad'-sektion i lönespec-mailen."""
    # Hitta huvudpersonens lönespec för månaden (inte partner)
    slip = (
        s.query(MailItem)
        .filter(
            MailItem.mail_type == "salary_slip",
            MailItem.subject == f"Lönespec {year_month}",
            MailItem.sender == "Arbetsgivaren",
        )
        .first()
    )
    if slip is None or not slip.body:
        return

    sick_total = sum(
        o.gross_loss for o in occs if o.template.kind != "vab"
    )
    sick_days = sum(
        o.n_days for o in occs if o.template.kind != "vab"
    )
    vab_total = sum(
        o.gross_loss for o in occs if o.template.kind == "vab"
    )
    vab_days = sum(
        o.n_days for o in occs if o.template.kind == "vab"
    )

    lines: list[str] = ["", "Frånvaro denna månad"]
    if sick_days > 0:
        lines.append(
            f"Sjukdom ({sick_days} dgr)         "
            f"{-sick_total:>10,} kr".replace(",", " ")
        )
    if vab_days > 0:
        lines.append(
            f"VAB ({vab_days} dgr)              "
            f"{-vab_total:>10,} kr".replace(",", " ")
        )
    total_loss = sick_total + vab_total
    lines.append("")
    lines.append(
        f"Justerad nettolön efter avdrag "
        f"{int(slip.amount or 0) - total_loss:>8,} kr".replace(",", " ")
    )

    slip.body = (slip.body or "") + "\n" + "\n".join(lines)
    s.flush()
