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


# ---------- Klasskompis-bjudningar ----------

class ClassmateOut(BaseModel):
    student_id: int
    display_name: str
    class_label: Optional[str]


@router.get("/classmates")
def list_classmates() -> dict:
    """Lista klasskompisar för bjudningar. Kräver att läraren har slagit
    på invite_classmates_enabled. Visar bara student_id + display_name —
    inga ekonomiska detaljer.

    OBS: denna endpoint kräver student-token för att veta vilken klass
    eleven tillhör. Vi läser via master_session + ContextVar för att
    plocka rätt student.
    """
    from ..school.engines import get_current_actor_student
    from ..school.models import Student
    from ..school.social_models import ClassDisplaySettings

    actor_id = get_current_actor_student()
    if actor_id is None:
        raise HTTPException(403, "Saknar student-kontext")

    with master_session() as ms:
        me = ms.query(Student).filter(Student.id == actor_id).first()
        if me is None:
            raise HTTPException(404, "Student saknas")

        # Är klasskompis-bjudningar aktiverade för denna lärare?
        cfg = (
            ms.query(ClassDisplaySettings)
            .filter(ClassDisplaySettings.teacher_id == me.teacher_id)
            .first()
        )
        if cfg is not None and cfg.invite_classmates_enabled is False:
            return {"classmates": [], "invites_enabled": False}

        # Klasskamrater = samma teacher_id, inte mig själv. Filtrera
        # också på class_label om eleven har en sådan (annars alla i
        # lärarens klass).
        q = ms.query(Student).filter(
            Student.teacher_id == me.teacher_id,
            Student.id != me.id,
        )
        if me.class_label:
            q = q.filter(Student.class_label == me.class_label)
        rows = q.order_by(Student.display_name).all()

        return {
            "classmates": [
                ClassmateOut(
                    student_id=s.id,
                    display_name=s.display_name,
                    class_label=s.class_label,
                ).model_dump()
                for s in rows
            ],
            "invites_enabled": True,
            "cost_split_model": cfg.cost_split_model if cfg else "split",
            "max_invites_per_week": cfg.max_invites_per_week if cfg else 3,
        }


class InviteIn(BaseModel):
    event_id: int
    classmate_ids: list[int]
    message: Optional[str] = None


class InviteResultOut(BaseModel):
    invites_created: int
    invite_ids: list[int]
    cost_split_model: str
    swish_amount_per_recipient: float
    week_remaining: int  # Hur många bjudningar eleven har kvar denna vecka


def _count_invites_this_week(master_sess, from_student_id: int) -> int:
    """Räkna bjudningar denna ISO-vecka för anti-spam."""
    from datetime import date as _d, datetime as _dt
    from ..school.social_models import ClassEventInvite

    today = _d.today()
    iso_year, iso_week, _ = today.isocalendar()
    week_start = _d.fromisocalendar(iso_year, iso_week, 1)
    return (
        master_sess.query(ClassEventInvite)
        .filter(
            ClassEventInvite.from_student_id == from_student_id,
            ClassEventInvite.created_at >= _dt.combine(week_start, _dt.min.time()),
        )
        .count()
    )


@router.post("/invite-classmates", response_model=InviteResultOut)
def invite_classmates(
    payload: InviteIn,
    scope: Session = Depends(db),
) -> InviteResultOut:
    """Bjud N klasskompisar på ett event. Skapar ClassEventInvite per
    mottagare. Mottagarna ser invitationen via /events/invitations.

    Kostnadsmodell sätts från lärarens ClassDisplaySettings — låses i
    invitationen så ändringen i config inte påverkar pågående.
    """
    from datetime import date as _d
    from decimal import Decimal as _Dec

    from ..school.engines import get_current_actor_student
    from ..school.models import Student
    from ..school.social_models import (
        ClassDisplaySettings,
        ClassEventInvite,
    )

    if not payload.classmate_ids:
        raise HTTPException(400, "Inga klasskompisar valda")
    if len(payload.classmate_ids) > 20:
        raise HTTPException(400, "Max 20 mottagare per bjudning")

    # Hämta eventet i scope
    ev = scope.get(StudentEvent, payload.event_id)
    if ev is None:
        raise HTTPException(404, "Event saknas")
    if ev.status != "pending":
        raise HTTPException(400, "Event är inte längre pending")
    if not ev.social_invite_allowed:
        raise HTTPException(400, "Detta event tillåter inte klasskompis-bjudningar")

    actor_id = get_current_actor_student()
    if actor_id is None:
        raise HTTPException(403, "Saknar student-kontext")

    with master_session() as ms:
        me = ms.query(Student).filter(Student.id == actor_id).first()
        if me is None:
            raise HTTPException(404, "Student saknas")

        cfg = (
            ms.query(ClassDisplaySettings)
            .filter(ClassDisplaySettings.teacher_id == me.teacher_id)
            .first()
        )
        if cfg is not None and not cfg.invite_classmates_enabled:
            raise HTTPException(400, "Klasskompis-bjudningar är avstängda av läraren")

        cost_split_model = cfg.cost_split_model if cfg else "split"
        max_per_week = cfg.max_invites_per_week if cfg else 3

        # Anti-spam: räkna bjudningar denna ISO-vecka
        already_this_week = _count_invites_this_week(ms, actor_id)
        remaining = max_per_week - already_this_week
        if len(payload.classmate_ids) > remaining:
            raise HTTPException(
                400,
                f"Du kan bjuda max {remaining} fler denna vecka "
                f"({already_this_week}/{max_per_week} redan skickade).",
            )

        # Validera att alla mottagare är klasskompisar
        valid_ids = {
            s.id for s in ms.query(Student)
            .filter(
                Student.teacher_id == me.teacher_id,
                Student.id != me.id,
                Student.id.in_(payload.classmate_ids),
            )
            .all()
        }
        invalid = set(payload.classmate_ids) - valid_ids
        if invalid:
            raise HTTPException(
                400, f"Dessa elever finns inte i klassen: {sorted(invalid)}",
            )

        # Beräkna swish-belopp per mottagare
        cost = float(ev.cost)
        n_recipients = len(payload.classmate_ids)
        if cost_split_model == "split":
            # 50/50 mellan alla deltagare (bjudaren + N mottagare)
            swish_per = cost / (n_recipients + 1) if n_recipients > 0 else 0
        elif cost_split_model == "each_pays_own":
            swish_per = cost
        else:  # inviter_pays
            swish_per = 0.0

        # Skapa invitationer
        invite_ids = []
        for mate_id in payload.classmate_ids:
            inv = ClassEventInvite(
                from_student_id=actor_id,
                to_student_id=mate_id,
                event_code=ev.event_code,
                event_title=ev.title,
                proposed_date=ev.proposed_date,
                deadline=ev.deadline,
                cost=ev.cost,
                cost_split_model=cost_split_model,
                message=payload.message,
                status="pending",
                swish_amount=_Dec(str(round(swish_per, 2))) if swish_per > 0 else None,
            )
            ms.add(inv)
        ms.flush()
        # Hämta IDn
        for inv in ms.query(ClassEventInvite).filter(
            ClassEventInvite.from_student_id == actor_id,
            ClassEventInvite.event_code == ev.event_code,
        ).order_by(ClassEventInvite.id.desc()).limit(n_recipients).all():
            invite_ids.append(inv.id)

    return InviteResultOut(
        invites_created=n_recipients,
        invite_ids=invite_ids,
        cost_split_model=cost_split_model,
        swish_amount_per_recipient=round(swish_per, 2),
        week_remaining=remaining - n_recipients,
    )


class InvitationOut(BaseModel):
    id: int
    from_student_id: int
    from_display_name: Optional[str]
    event_code: str
    event_title: str
    proposed_date: Optional[str]
    deadline: str
    cost: float
    cost_split_model: str
    swish_amount: Optional[float]
    message: Optional[str]
    status: str
    created_at: str


@router.get("/invitations")
def list_invitations(scope: Session = Depends(db)) -> dict:
    """Lista invitationer som JAG fått (mottagit) — pending + recent.

    Pedagogiskt: 'inkorgen' där eleven ser vem som bjudit och kan
    svara. Visar vem (display_name) men inga ekonomiska detaljer
    om bjudaren.
    """
    from ..school.engines import get_current_actor_student
    from ..school.models import Student
    from ..school.social_models import ClassEventInvite

    actor_id = get_current_actor_student()
    if actor_id is None:
        raise HTTPException(403, "Saknar student-kontext")

    with master_session() as ms:
        rows = (
            ms.query(ClassEventInvite)
            .filter(ClassEventInvite.to_student_id == actor_id)
            .order_by(ClassEventInvite.created_at.desc())
            .limit(50)
            .all()
        )
        # Slå upp avsändarnamn
        sender_ids = list({r.from_student_id for r in rows})
        senders = {
            s.id: s.display_name
            for s in ms.query(Student).filter(Student.id.in_(sender_ids)).all()
        }

        return {
            "invitations": [
                InvitationOut(
                    id=r.id,
                    from_student_id=r.from_student_id,
                    from_display_name=senders.get(r.from_student_id),
                    event_code=r.event_code,
                    event_title=r.event_title,
                    proposed_date=r.proposed_date.isoformat() if r.proposed_date else None,
                    deadline=r.deadline.isoformat(),
                    cost=float(r.cost),
                    cost_split_model=r.cost_split_model,
                    swish_amount=float(r.swish_amount) if r.swish_amount else None,
                    message=r.message,
                    status=r.status,
                    created_at=r.created_at.isoformat() if r.created_at else "",
                ).model_dump()
                for r in rows
            ],
            "count": len(rows),
        }


class InvitationRespondIn(BaseModel):
    invite_id: int
    accept: bool


class InvitationRespondOut(BaseModel):
    invite_id: int
    status: str
    student_event_id: Optional[int]
    swish_upcoming_id: Optional[int]
    pedagogical_note: str


@router.post("/invitations/respond", response_model=InvitationRespondOut)
def respond_to_invitation(
    payload: InvitationRespondIn,
    scope: Session = Depends(db),
) -> InvitationRespondOut:
    """Mottagaren svarar på en bjudning.

    Vid accept:
    - Skapas en StudentEvent i mottagarens scope (status pending så
      hen kan acceptera/neka som vanligt — ELLER så accepterar vi
      direkt? V1: vi skapar pending event så mottagaren ser samma
      flöde som systemgenererade events)
    - Om swish_amount > 0: skapas en UpcomingTransaction (Swish-skuld
      till bjudaren) i mottagarens scope

    Vid decline:
    - Bara invitationens status uppdateras
    """
    from datetime import datetime as _dt
    from decimal import Decimal as _Dec

    from ..db.models import UpcomingTransaction
    from ..school.engines import get_current_actor_student
    from ..school.models import Student
    from ..school.social_models import ClassEventInvite

    actor_id = get_current_actor_student()
    if actor_id is None:
        raise HTTPException(403, "Saknar student-kontext")

    with master_session() as ms:
        inv = ms.get(ClassEventInvite, payload.invite_id)
        if inv is None:
            raise HTTPException(404, "Invitation saknas")
        if inv.to_student_id != actor_id:
            raise HTTPException(403, "Du är inte mottagare av denna invitation")
        if inv.status != "pending":
            raise HTTPException(400, f"Redan svarat ({inv.status})")

        sender = ms.query(Student).filter(Student.id == inv.from_student_id).first()
        sender_name = sender.display_name if sender else "okänd"

        if not payload.accept:
            inv.status = "declined"
            inv.responded_at = _dt.utcnow()
            ms.flush()
            return InvitationRespondOut(
                invite_id=inv.id,
                status=inv.status,
                student_event_id=None,
                swish_upcoming_id=None,
                pedagogical_note=(
                    f"Du tackade nej till {sender_name}s bjudning. Inget "
                    "betalningskrav. {inv.event_title} är borta från din inbox."
                ),
            )

        # ACCEPT — skapa StudentEvent + ev. Swish-skuld
        inv.status = "accepted"
        inv.responded_at = _dt.utcnow()
        ms.flush()

        invite_data = {
            "title": inv.event_title,
            "code": inv.event_code,
            "proposed_date": inv.proposed_date,
            "deadline": inv.deadline,
            "cost": _Dec(inv.cost),
            "swish_amount": _Dec(inv.swish_amount) if inv.swish_amount else None,
            "from_student_id": inv.from_student_id,
        }
        sender_id = invite_data["from_student_id"]

    # Skapa pending StudentEvent i mottagarens scope
    new_event = StudentEvent(
        event_code=invite_data["code"],
        title=invite_data["title"],
        description=(
            f"Bjuden av {sender_name}. {invite_data['title']}"
            + (f"\n\nMeddelande: {inv.message}" if inv.message else "")
        ),
        category="social",
        cost=invite_data["cost"],
        proposed_date=invite_data["proposed_date"],
        deadline=invite_data["deadline"],
        source="classmate_invite",
        source_classmate_id=sender_id,
        status="pending",
        social_invite_allowed=False,  # Mottagaren bjuder inte vidare
        declinable=True,
    )
    scope.add(new_event)
    scope.flush()

    swish_upcoming_id = None
    if invite_data["swish_amount"] and invite_data["swish_amount"] > 0:
        # Skapa Swish-skuld som UpcomingTransaction (bill, betalas inom
        # 14 dagar). Mottagaren ser den i Kommande-listan och kan
        # markera betald när hen swishar bjudaren.
        from datetime import timedelta as _td
        swish_due = _dt.utcnow().date() + _td(days=14)
        upcoming = UpcomingTransaction(
            kind="bill",
            name=f"Swish till {sender_name} ({invite_data['title']})",
            amount=invite_data["swish_amount"],
            expected_date=swish_due,
            owner=None,
            recurring_monthly=False,
            source="classmate_invite",
            notes=f"Återbetalning för bjudning till {invite_data['title']}",
        )
        scope.add(upcoming)
        scope.flush()
        swish_upcoming_id = upcoming.id

    note_parts = [
        f"Du tackade ja till {sender_name}s bjudning till {invite_data['title']}.",
    ]
    if invite_data["swish_amount"] and invite_data["swish_amount"] > 0:
        note_parts.append(
            f"Swish-skuld: {invite_data['swish_amount']} kr — ligger som "
            f"kommande räkning, betalas senast om 14 dagar."
        )
    else:
        note_parts.append("Bjudaren betalar — inga pengar från ditt konto.")

    return InvitationRespondOut(
        invite_id=payload.invite_id,
        status="accepted",
        student_event_id=new_event.id,
        swish_upcoming_id=swish_upcoming_id,
        pedagogical_note=" ".join(note_parts),
    )
