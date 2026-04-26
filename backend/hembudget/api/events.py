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
