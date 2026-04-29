"""Trigger-engine för Wellbeing-events.

Pickar 0-3 events per vecka per elev från EventTemplate-biblioteket
baserat på:
- Slumpvikt (random_weight på mallen)
- Veckodag-trigger (weekday-villkor)
- Månadsdag-trigger (month_day_min/max)
- Säsong-trigger (season)
- Reaktiva trigger (low_savings_buffer, high_balance) — läses från
  scope-DB
- Personlighet (Personality.introvert_score påverkar antal sociala events)

Determinism: random.Random seedas på (student_seed, year_month, week_n)
så två tickar i samma vecka ger samma resultat → idempotent.

Funktionerna är rena (tar Session + master_session) — endpoint-lagret
i api/events.py wrappar dem.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..db.models import (
    Account,
    PersonalityProfile,
    StudentEvent,
    Transaction,
)
from ..school.event_models import EventTemplate


SEASON_FOR_MONTH = {
    1: "winter", 2: "winter", 12: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn",
}


@dataclass
class EventTickResult:
    week_seed: int
    candidates_evaluated: int
    events_created: int
    skipped_reason_counts: dict


def _balance_for(session: Session, account_id: int) -> Decimal:
    acc = session.get(Account, account_id)
    if acc is None:
        return Decimal("0")
    base = acc.opening_balance or Decimal("0")
    q = session.query(
        sa_func.coalesce(sa_func.sum(Transaction.amount), 0),
    ).filter(Transaction.account_id == account_id)
    if acc.opening_balance_date is not None:
        q = q.filter(Transaction.date >= acc.opening_balance_date)
    total = q.scalar() or Decimal("0")
    if not isinstance(total, Decimal):
        total = Decimal(str(total))
    return base + total


def _checking_balance(session: Session) -> Decimal:
    accs = session.query(Account).filter(Account.type == "checking").all()
    return sum((_balance_for(session, a.id) for a in accs), Decimal("0"))


def _savings_balance(session: Session) -> Decimal:
    accs = (
        session.query(Account)
        .filter(Account.type.in_({"savings", "isk"}))
        .all()
    )
    return sum((_balance_for(session, a.id) for a in accs), Decimal("0"))


def _passes_triggers(
    template: EventTemplate,
    *,
    today: date,
    rng: random.Random,
    checking: Decimal,
    savings: Decimal,
) -> tuple[bool, str]:
    """Kollar om ett template passerar sina trigger-villkor.
    Returnerar (passes, skip_reason)."""
    triggers = template.triggers or {}

    weekday_filter = triggers.get("weekday")
    if weekday_filter and today.weekday() not in weekday_filter:
        return False, "weekday_mismatch"

    md_min = triggers.get("month_day_min")
    md_max = triggers.get("month_day_max")
    if md_min is not None and today.day < md_min:
        return False, "before_month_day"
    if md_max is not None and today.day > md_max:
        return False, "after_month_day"

    season = triggers.get("season")
    if season and SEASON_FOR_MONTH.get(today.month) != season:
        # Tillåt också specifik månad ('december', 'november' etc)
        month_names = ["january", "february", "march", "april", "may",
                       "june", "july", "august", "september", "october",
                       "november", "december"]
        if season != month_names[today.month - 1]:
            return False, "wrong_season"

    reactive = triggers.get("reactive")
    if reactive == "low_savings_buffer" and savings >= Decimal("5000"):
        return False, "savings_too_high"
    if reactive == "high_balance" and checking < Decimal("20000"):
        return False, "balance_too_low"

    # Slumpvikt
    weight = float(triggers.get("random_weight", 1.0))
    if rng.random() > weight:
        return False, "random_skip"

    return True, ""


def _resolve_cost(template: EventTemplate, rng: random.Random) -> Decimal:
    """Slumpa kostnad mellan cost_min och cost_max för deterministisk
    men varierad upplevelse."""
    if template.cost_min == template.cost_max:
        return Decimal(template.cost_min)
    cost = rng.randint(template.cost_min, template.cost_max)
    # Avrunda till närmaste 10 kr för pedagogisk klarhet
    cost = round(cost / 10) * 10
    return Decimal(cost)


def tick_for_student(
    *,
    scope_session: Session,
    master_session: Session,
    student_seed: int,
    today: Optional[date] = None,
    max_events_per_tick: int = 3,
) -> EventTickResult:
    """Skapa 0-N nya events för en elev. Idempotent per vecka:
    samma student + samma vecka → samma events.

    Hoppar över events där eleven redan har en pågående eller färsk
    samma-code-event (under 14 dagar) — undviker dubletter.
    """
    today = today or date.today()
    week_n = today.isocalendar()[1]
    week_seed_str = f"events-{student_seed}-{today.year}-W{week_n}"
    week_seed = int(hashlib.sha256(week_seed_str.encode()).hexdigest()[:8], 16)
    rng = random.Random(week_seed)

    # Idempotency: om tick redan körts denna ISO-vecka för denna scope,
    # gör inget. Pickar samma vecka är meningslöst — eleven har redan
    # sina förslag.
    week_start = date.fromisocalendar(today.year, week_n, 1)
    already_ticked = (
        scope_session.query(StudentEvent)
        .filter(
            StudentEvent.created_at >= datetime.combine(
                week_start, datetime.min.time(),
            ),
            StudentEvent.source == "system",
        )
        .first()
    )
    if already_ticked is not None:
        return EventTickResult(
            week_seed=week_seed,
            candidates_evaluated=0,
            events_created=0,
            skipped_reason_counts={"already_ticked_this_week": 1},
        )

    # Personlighet-justering: introvert sänker antal social-events,
    # extrovert höjer
    pers = scope_session.query(PersonalityProfile).first()
    intr = pers.introvert_score if pers else 50
    # 0-100 → 0.5x till 1.5x för social-vikt
    social_multiplier = 1.5 - (intr / 100)

    # Aktuella balanser för reaktiva villkor
    checking = _checking_balance(scope_session)
    savings = _savings_balance(scope_session)

    # Hämta alla aktiva templates
    templates = (
        master_session.query(EventTemplate)
        .filter(EventTemplate.active.is_(True))
        .all()
    )

    # Existerande pågående/nyligen skapade events — undvik dubblar
    cutoff = today - timedelta(days=14)
    recent_codes = {
        e.event_code
        for e in scope_session.query(StudentEvent)
        .filter(StudentEvent.created_at >= datetime.combine(cutoff, datetime.min.time()))
        .all()
    }

    candidates: list[tuple[EventTemplate, float]] = []
    skip_counts: dict = {}

    for tpl in templates:
        if tpl.code in recent_codes:
            skip_counts["dupe"] = skip_counts.get("dupe", 0) + 1
            continue

        passes, reason = _passes_triggers(
            tpl, today=today, rng=rng,
            checking=checking, savings=savings,
        )
        if not passes:
            skip_counts[reason] = skip_counts.get(reason, 0) + 1
            continue

        weight = (tpl.triggers or {}).get("random_weight", 1.0)
        if tpl.category == "social":
            weight *= social_multiplier
        candidates.append((tpl, float(weight)))

    # Plocka upp till N events viktat
    events_created = 0
    for _ in range(max_events_per_tick):
        if not candidates:
            break
        weights = [c[1] for c in candidates]
        total = sum(weights)
        if total <= 0:
            break
        pick_val = rng.random() * total
        running = 0.0
        picked_idx = 0
        for i, (_, w) in enumerate(candidates):
            running += w
            if pick_val <= running:
                picked_idx = i
                break

        tpl, _w = candidates.pop(picked_idx)
        cost = _resolve_cost(tpl, rng)
        proposed = today + timedelta(days=rng.randint(1, max(2, tpl.duration_days // 2)))
        deadline = today + timedelta(days=tpl.duration_days)

        ev = StudentEvent(
            event_code=tpl.code,
            title=tpl.title,
            description=tpl.description,
            category=tpl.category,
            cost=cost,
            proposed_date=proposed,
            deadline=deadline,
            source="system",
            status="pending",
            social_invite_allowed=tpl.social_invite_allowed,
            declinable=tpl.declinable,
        )
        scope_session.add(ev)
        events_created += 1

    if events_created:
        scope_session.flush()

    return EventTickResult(
        week_seed=week_seed,
        candidates_evaluated=len(templates),
        events_created=events_created,
        skipped_reason_counts=skip_counts,
    )


def expire_old_events(
    scope_session: Session,
    *,
    today: Optional[date] = None,
) -> int:
    """Markera pending-events som expired om deadline passerat.
    Returnerar antalet uppdaterade rader."""
    today = today or date.today()
    rows = (
        scope_session.query(StudentEvent)
        .filter(
            StudentEvent.status == "pending",
            StudentEvent.deadline < today,
        )
        .all()
    )
    for r in rows:
        r.status = "expired"
        r.decided_at = datetime.utcnow()
    if rows:
        scope_session.flush()
    return len(rows)
