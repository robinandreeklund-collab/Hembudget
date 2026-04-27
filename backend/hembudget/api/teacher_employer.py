"""Lärar-API för arbetsgivar-dynamik (idé 1, C4d i dev_v1.md).

Endpoints:
 - GET  /teacher/employer/class      — alla elever i klassen + score/trend
 - POST /teacher/employer/{student_id}/delta — manuell justering med
   motivering (kräver att läraren äger eleven)

Lärar-impersonation (x-as-student) är INTE rätt mönster här — det här
är lärar-vyer som visar tvärsnitt över klassen utan att gå in i
elevens scope.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..school import is_enabled as school_enabled
from ..school.engines import master_session
from ..school.employer_models import (
    CollectiveAgreement,
    EmployerSatisfaction,
    EmployerSatisfactionEvent,
)
from ..school.models import Student, StudentProfile
from .deps import TokenInfo, require_teacher
from .employer import (
    _apply_delta,
    _ensure_satisfaction,
    _resolve_agreement_for_profile,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["teacher-employer"])


def _require_school() -> None:
    if not school_enabled():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "School mode inaktivt",
        )


def _verify_teacher_owns_student(
    teacher_id: int, student_id: int,
) -> Student:
    """Hämta + validera. 404 om eleven inte finns, 403 om
    läraren inte äger hen."""
    with master_session() as s:
        st = s.get(Student, student_id)
        if not st:
            raise HTTPException(404, "Eleven finns inte")
        if st.teacher_id != teacher_id:
            raise HTTPException(403, "Inte din elev")
        return st


# ---------- Schemas ----------

class ClassRow(BaseModel):
    student_id: int
    display_name: str
    class_label: Optional[str] = None
    profession: Optional[str] = None
    employer: Optional[str] = None
    agreement_code: Optional[str] = None
    score: int
    trend: str
    last_event_at: Optional[str] = None
    flag: Optional[str] = None  # "low" om score<40, "critical" om <25


class ClassSummaryOut(BaseModel):
    rows: list[ClassRow]
    total_students: int
    avg_score: int


class ManualDeltaIn(BaseModel):
    delta: int = Field(ge=-30, le=30)
    reason_md: str = Field(min_length=5, max_length=400)


class ManualDeltaOut(BaseModel):
    event_id: int
    new_score: int
    new_trend: str


# ---------- Endpoints ----------

@router.get("/teacher/employer/class", response_model=ClassSummaryOut)
def teacher_class_employer(
    info: TokenInfo = Depends(require_teacher),
) -> ClassSummaryOut:
    """Lärar-vy: alla elever med satisfaction + avtal-kod + flagga.

    Pedagogiskt fokus: hjälpa läraren spotta elever vars score
    sjunkit och behöver samtal. Inte en spårning av varje rörelse —
    bara nuläget.
    """
    _require_school()
    teacher_id = info.teacher_id or 0

    with master_session() as s:
        students = (
            s.query(Student)
            .filter(Student.teacher_id == teacher_id)
            .order_by(Student.class_label, Student.display_name)
            .all()
        )
        rows: list[ClassRow] = []
        score_total = 0
        for st in students:
            sat = _ensure_satisfaction(s, st.id)
            score_total += sat.score
            profile = (
                s.query(StudentProfile)
                .filter(StudentProfile.student_id == st.id)
                .first()
            )
            agreement_code: Optional[str] = None
            profession = None
            employer = None
            if profile:
                profession = profile.profession
                employer = profile.employer
                _, agreement = _resolve_agreement_for_profile(s, profile)
                if agreement:
                    agreement_code = agreement.code
            flag: Optional[str] = None
            if sat.score < 25:
                flag = "critical"
            elif sat.score < 40:
                flag = "low"
            rows.append(ClassRow(
                student_id=st.id,
                display_name=st.display_name,
                class_label=st.class_label,
                profession=profession,
                employer=employer,
                agreement_code=agreement_code,
                score=sat.score,
                trend=sat.trend,
                last_event_at=(
                    sat.last_event_at.isoformat() if sat.last_event_at else None
                ),
                flag=flag,
            ))
        avg = (score_total // len(rows)) if rows else 0
        return ClassSummaryOut(
            rows=rows,
            total_students=len(rows),
            avg_score=avg,
        )


@router.post(
    "/teacher/employer/{student_id}/delta",
    response_model=ManualDeltaOut,
)
def teacher_manual_delta(
    student_id: int,
    payload: ManualDeltaIn,
    info: TokenInfo = Depends(require_teacher),
) -> ManualDeltaOut:
    """Lärare lägger till en manuell delta för en elev.

    Begränsningar:
    - Lärare måste äga eleven (404/403 annars)
    - delta ∈ [-30, +30] (hindrar att läraren krossar scoren med en
      enda klick — flera mindre deltas är pedagogiskt rätt)
    - reason_md krävs (5–400 tecken) — läraren MÅSTE motivera

    Use-case: en elev har gjort något offline som ska speglas i
    systemet (utebliven inlämning, exemplariskt teamarbete osv).
    """
    _require_school()
    teacher_id = info.teacher_id or 0
    _verify_teacher_owns_student(teacher_id, student_id)

    with master_session() as s:
        # Stoppa "manual_teacher" så reason_md tydligt markeras i
        # eventloggen som lärar-judgement, inte system-genererad.
        prefix = "**Manuell justering från läraren:**\n\n"
        event = _apply_delta(
            s, student_id,
            kind="manual_teacher",
            delta=int(payload.delta),
            reason_md=prefix + payload.reason_md,
            meta={"teacher_id": teacher_id},
        )
        sat = _ensure_satisfaction(s, student_id)
        return ManualDeltaOut(
            event_id=event.id,
            new_score=sat.score,
            new_trend=sat.trend,
        )
