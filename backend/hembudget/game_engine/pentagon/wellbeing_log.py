"""P2 · WellbeingEvent-loggen.

Spec: dev/game-motor/07-pentagon-mekanik.md (Wellbeing-event-loggen)

`apply_pentagon_delta(student_id, axis, requested_delta, reason)`:
  1. Slår upp senaste 30 d historik från WellbeingEvent
  2. Klampar via `apply_momentum`
  3. Skriver en ny WellbeingEvent-rad
  4. Returnerar (applied_delta, new_value)

`pentagon_history_for_student(student_id, days=30)`:
  Lista WellbeingEvent-rader för en elev, senaste N dagarna,
  sorterad fallande på occurred_at.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ...school.engines import master_session
from ...school.game_engine_models import WellbeingEvent
from .momentum import apply_momentum

log = logging.getLogger(__name__)


def _current_value_for_axis(
    s: Session, student_id: int, axis: str,
) -> int:
    """Slå upp senaste new_value för en axel; default 60 om ingen tidigare event."""
    last = (
        s.query(WellbeingEvent)
        .filter(
            WellbeingEvent.student_id == student_id,
            WellbeingEvent.axis == axis,
        )
        .order_by(WellbeingEvent.occurred_at.desc())
        .first()
    )
    if last is None:
        return 60
    return int(last.new_value)


def log_wellbeing_event(
    s: Session,
    *,
    student_id: int,
    axis: str,
    requested_delta: int,
    applied_delta: int,
    new_value: int,
    reason_kind: str,
    reason_id: Optional[int] = None,
    reason_table: Optional[str] = None,
    explanation: Optional[str] = None,
    year_month: Optional[str] = None,
) -> WellbeingEvent:
    """Skriv en WellbeingEvent-rad. Ger objektet som ResultaT."""
    row = WellbeingEvent(
        student_id=student_id,
        axis=axis,
        requested_delta=requested_delta,
        applied_delta=applied_delta,
        new_value=new_value,
        reason_kind=reason_kind,
        reason_id=reason_id,
        reason_table=reason_table,
        explanation=explanation,
        year_month=year_month,
    )
    s.add(row)
    s.flush()
    return row


def apply_pentagon_delta(
    student_id: int,
    *,
    axis: str,
    requested_delta: int,
    reason_kind: str,
    reason_id: Optional[int] = None,
    reason_table: Optional[str] = None,
    explanation: Optional[str] = None,
    year_month: Optional[str] = None,
    floor: int = 0,
    ceiling: int = 100,
    now: Optional[datetime] = None,
) -> tuple[int, int]:
    """Applicera en pentagon-förändring med tröghet + audit-logg.

    Returnerar (applied_delta, new_value).
    """
    now = now or datetime.utcnow()
    with master_session() as s:
        # Hämta senaste 30 d för momentum-beräkning
        history = (
            s.query(WellbeingEvent)
            .filter(
                WellbeingEvent.student_id == student_id,
                WellbeingEvent.axis == axis,
                WellbeingEvent.occurred_at >= now - timedelta(days=30),
            )
            .all()
        )
        # Vi använder applied_delta-fältet som "delta" för momentum
        proxies = [
            type("EventProxy", (), {
                "axis": h.axis,
                "occurred_at": h.occurred_at,
                "delta": h.applied_delta,
            })()
            for h in history
        ]
        applied = apply_momentum(axis, requested_delta, proxies, now=now)

        current = _current_value_for_axis(s, student_id, axis)
        new_value = max(floor, min(ceiling, current + applied))

        log_wellbeing_event(
            s,
            student_id=student_id,
            axis=axis,
            requested_delta=requested_delta,
            applied_delta=applied,
            new_value=new_value,
            reason_kind=reason_kind,
            reason_id=reason_id,
            reason_table=reason_table,
            explanation=explanation,
            year_month=year_month,
        )
        s.commit()
        return applied, new_value


def pentagon_history_for_student(
    student_id: int,
    *,
    days: int = 30,
    axis: Optional[str] = None,
) -> list[WellbeingEvent]:
    """Hämta WellbeingEvent-rader för en elev senaste `days` dagarna."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    with master_session() as s:
        q = (
            s.query(WellbeingEvent)
            .filter(
                WellbeingEvent.student_id == student_id,
                WellbeingEvent.occurred_at >= cutoff,
            )
        )
        if axis:
            q = q.filter(WellbeingEvent.axis == axis)
        rows = q.order_by(WellbeingEvent.occurred_at.desc()).all()
        for r in rows:
            s.expunge(r)
        return rows
