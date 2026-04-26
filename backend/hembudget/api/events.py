"""Events-API: lista pending, tick-trigger, expire-städning, seed-bootstrap.

Accept/decline-flöden + klasskompis-bjudningar kommer i fas 3 av game.md.
Här bygger vi infrastrukturen.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.models import StudentEvent
from ..events.engine import expire_old_events, tick_for_student
from ..school.engines import master_session
from ..school.event_seed import seed_event_templates
from .deps import db, require_auth


router = APIRouter(
    prefix="/events",
    tags=["events"],
    dependencies=[Depends(require_auth)],
)


class StudentEventOut(BaseModel):
    id: int
    event_code: str
    title: str
    description: str
    category: str
    cost: float
    proposed_date: Optional[str]
    deadline: str
    source: str
    status: str
    social_invite_allowed: bool
    declinable: bool
    created_at: str


def _to_out(e: StudentEvent) -> StudentEventOut:
    return StudentEventOut(
        id=e.id,
        event_code=e.event_code,
        title=e.title,
        description=e.description,
        category=e.category,
        cost=float(e.cost),
        proposed_date=e.proposed_date.isoformat() if e.proposed_date else None,
        deadline=e.deadline.isoformat(),
        source=e.source,
        status=e.status,
        social_invite_allowed=e.social_invite_allowed,
        declinable=e.declinable,
        created_at=e.created_at.isoformat() if e.created_at else "",
    )


@router.get("/pending")
def list_pending(scope: Session = Depends(db)) -> dict:
    """Lista alla events med status='pending' inom deadline.
    Frontend visar i notifikations-bubblan."""
    rows = (
        scope.query(StudentEvent)
        .filter(StudentEvent.status == "pending")
        .order_by(StudentEvent.deadline.asc())
        .all()
    )
    return {
        "events": [_to_out(e).model_dump() for e in rows],
        "count": len(rows),
    }


@router.get("/history")
def list_history(
    limit: int = 50,
    scope: Session = Depends(db),
) -> dict:
    """Tidigare events oavsett status — för audit/reflektion."""
    rows = (
        scope.query(StudentEvent)
        .order_by(StudentEvent.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )
    return {
        "events": [_to_out(e).model_dump() for e in rows],
        "count": len(rows),
    }


class TickIn(BaseModel):
    student_seed: Optional[int] = None
    today: Optional[str] = None
    max_events: int = 3


@router.post("/internal/tick")
def trigger_tick(
    payload: Optional[TickIn] = None,
    scope: Session = Depends(db),
) -> dict:
    """Kör trigger-engine för aktiv elev. Idempotent per ISO-vecka.

    student_seed default: 0 (alla elever delar baseline-RNG;
    rekommendation är att tick:en kallas av en bakgrundsjobb som
    sätter seed = student_id för deterministisk variation per elev).
    """
    payload = payload or TickIn()
    today = None
    if payload.today:
        try:
            today = date.fromisoformat(payload.today)
        except ValueError:
            raise HTTPException(400, "Felaktigt datum")

    # Säkerställ att master har templates
    with master_session() as ms:
        if seed_event_templates(ms) > 0:
            # Logga bara — inte ett fel
            pass

        result = tick_for_student(
            scope_session=scope,
            master_session=ms,
            student_seed=payload.student_seed or 0,
            today=today,
            max_events_per_tick=payload.max_events,
        )

    # Expire gamla events i samma sväng
    expired = expire_old_events(scope, today=today)

    return {
        "events_created": result.events_created,
        "candidates_evaluated": result.candidates_evaluated,
        "skipped": result.skipped_reason_counts,
        "expired_old": expired,
        "week_seed": result.week_seed,
    }


@router.post("/internal/expire")
def trigger_expire(scope: Session = Depends(db)) -> dict:
    """Markera passade pending-events som expired."""
    n = expire_old_events(scope)
    return {"expired": n}


# ---------- Accept / decline ----------

class AcceptIn(BaseModel):
    account_id: Optional[int] = None  # Vart kostnaden bokförs (default: lönekonto)
    classmate_invite_ids: list[int] = []  # V2: bjuda kompisar


class AcceptResultOut(BaseModel):
    event_id: int
    status: str
    transaction_id: Optional[int]
    cost_applied: float
    income_applied: float
    impact_applied: dict
    pedagogical_note: str


def _resolve_default_account(scope: Session) -> Optional[int]:
    """Hitta elevens checking-konto — där kostnader/inkomster bokförs."""
    from ..db.models import Account
    acc = (
        scope.query(Account)
        .filter(Account.type == "checking")
        .order_by(Account.id.asc())
        .first()
    )
    return acc.id if acc else None


def _get_or_create_streak(scope: Session):
    """Hämta eller skapa elevens DeclineStreak-rad."""
    from ..db.models import DeclineStreak
    row = scope.query(DeclineStreak).first()
    if row is None:
        row = DeclineStreak(current_streak=0)
        scope.add(row); scope.flush()
    return row


def _bump_decline_streak(scope: Session, *, social_event: bool, justified: bool) -> dict:
    """Uppdaterar streak vid en decline. Returnerar info för frontend.

    Bara onödiga nej (sociala events utan sparande-skäl) räknas i
    streak — eleven straffas inte för att neka tandläkaren eller
    aktivt välja sparande."""
    from datetime import datetime as _dt
    streak = _get_or_create_streak(scope)
    if social_event and not justified:
        streak.current_streak += 1
        streak.last_decline_at = _dt.utcnow()
    scope.flush()
    return {
        "current_streak": streak.current_streak,
        "should_show_nudge": (
            streak.current_streak >= 3
            and streak.current_streak > streak.nudge_shown_for_streak
        ),
    }


def _reset_decline_streak(scope: Session) -> None:
    """Vid accept — nollställ streak."""
    from datetime import datetime as _dt
    streak = _get_or_create_streak(scope)
    streak.current_streak = 0
    streak.last_accept_at = _dt.utcnow()
    scope.flush()


def _is_income_event(template_or_event) -> bool:
    """Inkomst-event = cost=0 men positivt impact_economy. Eleven får
    alltså pengar för att accepterat (julmarknadsjobb, bonus, blod)."""
    cost = getattr(template_or_event, "cost", None) or getattr(
        template_or_event, "cost_min", 0
    )
    impact_economy = getattr(template_or_event, "impact_economy", 0)
    if isinstance(cost, (int, float)):
        return cost == 0 and impact_economy > 0
    # Decimal
    return float(cost) == 0 and impact_economy > 0


def _income_for_event(event: StudentEvent, impact_economy: int) -> float:
    """Härledd inkomst-formel för cost=0-events. Ungefärligt rimlig
    skala — pedagogiskt men inte exakt. Kan ersättas med ett dedikerat
    income_amount-fält senare."""
    return max(50.0, abs(impact_economy) * 400.0)


@router.post("/{event_id}/accept", response_model=AcceptResultOut)
def accept_event(
    event_id: int,
    payload: Optional[AcceptIn] = None,
    scope: Session = Depends(db),
) -> AcceptResultOut:
    """Eleven accepterar ett event. Skapar Transaction (utgift eller
    inkomst), uppdaterar status, returnerar Wellbeing-impact + pedagogisk
    notis."""
    import hashlib as _hashlib
    from datetime import datetime as _dt
    from decimal import Decimal as _Dec

    from ..db.models import Transaction
    from ..school.event_models import EventTemplate

    payload = payload or AcceptIn()
    ev = scope.get(StudentEvent, event_id)
    if ev is None:
        raise HTTPException(404, "Event saknas")
    if ev.status != "pending":
        raise HTTPException(400, f"Event har redan status '{ev.status}'")

    # Hämta master-templaten för impact-värden
    with master_session() as ms:
        tpl = (
            ms.query(EventTemplate)
            .filter(EventTemplate.code == ev.event_code)
            .first()
        )
        if tpl is None:
            raise HTTPException(404, "Event-mall saknas i master")
        impacts = {
            "economy": tpl.impact_economy,
            "health": tpl.impact_health,
            "social": tpl.impact_social,
            "leisure": tpl.impact_leisure,
            "safety": tpl.impact_safety,
        }

    account_id = payload.account_id or _resolve_default_account(scope)
    if account_id is None:
        raise HTTPException(
            400, "Inget konto hittades — skapa ett checking-konto först.",
        )

    # Bestäm transaktionsbelopp
    is_income = float(ev.cost) == 0 and impacts["economy"] > 0
    if is_income:
        amount = _income_for_event(ev, impacts["economy"])
        signed_amount = _Dec(str(amount))  # positivt = inkomst
        cost_applied = 0.0
        income_applied = amount
        desc = f"Event: {ev.title}"
    else:
        cost_applied = float(ev.cost)
        income_applied = 0.0
        signed_amount = -_Dec(str(cost_applied))  # negativt = utgift
        desc = f"Event: {ev.title}"

    # Skapa Transaction
    tx = None
    if signed_amount != 0:
        h = _hashlib.sha256(
            f"event-{ev.id}-{_dt.utcnow().isoformat()}".encode()
        ).hexdigest()
        tx = Transaction(
            account_id=account_id,
            date=_dt.utcnow().date(),
            amount=signed_amount,
            currency="SEK",
            raw_description=desc,
            is_transfer=False,
            hash=h,
        )
        scope.add(tx)
        scope.flush()

    # Uppdatera event
    ev.status = "accepted"
    ev.decided_at = _dt.utcnow()
    ev.resulting_transaction_id = tx.id if tx else None
    ev.impact_applied = impacts
    scope.flush()

    # Nollställ decline-streak — eleven har sagt ja
    _reset_decline_streak(scope)

    # Pedagogisk note
    if is_income:
        note = (
            f"Du tog uppdraget och tjänade {amount:.0f} kr. "
            f"Wellbeing-effekt: ekonomi +{impacts['economy']}"
        )
    else:
        note_parts = []
        for k, v in impacts.items():
            if v != 0:
                sign = "+" if v > 0 else ""
                note_parts.append(f"{k} {sign}{v}")
        impact_str = ", ".join(note_parts) if note_parts else "ingen Wellbeing-impact"
        note = (
            f"Du betalade {cost_applied:.0f} kr för {ev.title}. "
            f"Wellbeing-effekt: {impact_str}."
        )

    return AcceptResultOut(
        event_id=ev.id,
        status=ev.status,
        transaction_id=tx.id if tx else None,
        cost_applied=cost_applied,
        income_applied=income_applied,
        impact_applied=impacts,
        pedagogical_note=note,
    )


class DeclineIn(BaseModel):
    decision_reason: Optional[str] = None  # T.ex. "valde sparande"


class DeclineResultOut(BaseModel):
    event_id: int
    status: str
    impact_applied: dict
    pedagogical_note: str
    current_decline_streak: int = 0
    show_streak_nudge: bool = False


@router.post("/{event_id}/decline", response_model=DeclineResultOut)
def decline_event(
    event_id: int,
    payload: Optional[DeclineIn] = None,
    scope: Session = Depends(db),
) -> DeclineResultOut:
    """Eleven nekar ett event. Negativ social-impact appliceras om
    eleven HADE råd (annars ekonomiskt skäl, ingen impact).

    decline_reason='valde sparande' eller liknande → vi flaggar att
    valet var medvetet, ingen straff-impact.
    """
    from datetime import datetime as _dt

    from ..school.event_models import EventTemplate

    payload = payload or DeclineIn()
    ev = scope.get(StudentEvent, event_id)
    if ev is None:
        raise HTTPException(404, "Event saknas")
    if ev.status != "pending":
        raise HTTPException(400, f"Event har redan status '{ev.status}'")
    if not ev.declinable:
        raise HTTPException(
            400, "Detta event går inte att neka (oförutsedd kostnad)",
        )

    # Endast sociala kategorier ger negativ impact vid neka — du straffas
    # inte för att neka tandläkaren eller en lifestyle-prenumeration.
    decline_impact = {
        "economy": 0, "health": 0, "social": 0,
        "leisure": 0, "safety": 0,
    }
    if ev.category in {"social", "family", "culture", "sport"}:
        # Om eleven uttryckligen valt att spara → ingen straff-impact
        reason_lower = (payload.decision_reason or "").lower()
        if "sparande" in reason_lower or "sparmål" in reason_lower:
            note = (
                f"Du nekade {ev.title} för att prioritera sparande. "
                "Det är ett medvetet val — Wellbeing påverkas inte."
            )
        else:
            decline_impact["social"] = -1
            note = (
                f"Du nekade {ev.title}. Sociala band sänks med 1 p — "
                "att alltid säga nej har en kostnad."
            )
    else:
        note = f"Du nekade {ev.title}. Ingen Wellbeing-impact."

    ev.status = "declined"
    ev.decision_reason = payload.decision_reason
    ev.decided_at = _dt.utcnow()
    ev.impact_applied = decline_impact
    scope.flush()

    # Underhåll decline-streak. social-kategori utan 'sparande'-skäl
    # räknas som onödigt nej.
    is_social = ev.category in {"social", "family", "culture", "sport"}
    reason_lower = (payload.decision_reason or "").lower()
    justified = "sparande" in reason_lower or "sparmål" in reason_lower
    streak_info = _bump_decline_streak(
        scope, social_event=is_social, justified=justified,
    )

    if streak_info["should_show_nudge"]:
        # Markera att vi visat nudge för denna streak-nivå
        from ..db.models import DeclineStreak
        s = scope.query(DeclineStreak).first()
        if s:
            s.nudge_shown_for_streak = streak_info["current_streak"]
            scope.flush()

    return DeclineResultOut(
        event_id=ev.id,
        status=ev.status,
        impact_applied=decline_impact,
        pedagogical_note=note,
        current_decline_streak=streak_info["current_streak"],
        show_streak_nudge=streak_info["should_show_nudge"],
    )


@router.get("/decline-streak")
def get_decline_streak(scope: Session = Depends(db)) -> dict:
    """Aktuell streak — för Dashboard-banner och pedagogisk feedback."""
    from ..db.models import DeclineStreak
    row = scope.query(DeclineStreak).first()
    if row is None:
        return {
            "current_streak": 0,
            "last_decline_at": None,
            "last_accept_at": None,
        }
    return {
        "current_streak": row.current_streak,
        "last_decline_at": (
            row.last_decline_at.isoformat() if row.last_decline_at else None
        ),
        "last_accept_at": (
            row.last_accept_at.isoformat() if row.last_accept_at else None
        ),
    }
