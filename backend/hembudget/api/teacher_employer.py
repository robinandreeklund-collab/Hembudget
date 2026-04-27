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
    NegotiationConfig,
    NegotiationRound,
    SalaryNegotiation,
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


# ---------- Lönesamtal — lärar-vyer ----------

class NegotiationListRow(BaseModel):
    id: int
    student_id: int
    display_name: str
    profession: str
    started_at: str
    completed_at: Optional[str] = None
    status: str
    final_pct: Optional[float] = None
    avtal_norm_pct: Optional[float] = None
    delta_vs_norm: Optional[float] = None
    flag: Optional[str] = None  # "below_norm" om eleven landade < norm-0.5pp


class NegotiationListOut(BaseModel):
    rows: list[NegotiationListRow]
    below_norm_count: int


@router.get(
    "/teacher/employer/negotiations",
    response_model=NegotiationListOut,
)
def teacher_negotiations(
    info: TokenInfo = Depends(require_teacher),
) -> NegotiationListOut:
    """Lista alla lönesamtal för lärarens elever — de senaste först.

    Pedagogisk varning: rad markeras 'below_norm' om eleven landade
    minst 0,5 pp under avtals-normen, så läraren kan följa upp.
    """
    _require_school()
    teacher_id = info.teacher_id or 0
    with master_session() as s:
        rows: list[NegotiationListRow] = []
        below = 0
        # Joina mot Student för att filtrera per lärare + display_name
        results = (
            s.query(SalaryNegotiation, Student)
            .join(Student, Student.id == SalaryNegotiation.student_id)
            .filter(Student.teacher_id == teacher_id)
            .order_by(SalaryNegotiation.started_at.desc())
            .all()
        )
        for n, st in results:
            delta_vs_norm: Optional[float] = None
            flag: Optional[str] = None
            if (
                n.final_pct is not None
                and n.avtal_norm_pct is not None
            ):
                delta_vs_norm = round(n.final_pct - n.avtal_norm_pct, 2)
                if delta_vs_norm <= -0.5:
                    flag = "below_norm"
                    below += 1
            rows.append(NegotiationListRow(
                id=n.id,
                student_id=n.student_id,
                display_name=st.display_name,
                profession=n.profession,
                started_at=n.started_at.isoformat(),
                completed_at=(
                    n.completed_at.isoformat() if n.completed_at else None
                ),
                status=n.status,
                final_pct=n.final_pct,
                avtal_norm_pct=n.avtal_norm_pct,
                delta_vs_norm=delta_vs_norm,
                flag=flag,
            ))
        return NegotiationListOut(rows=rows, below_norm_count=below)


class NegotiationDetailRoundOut(BaseModel):
    round_no: int
    student_message: str
    employer_response: str
    proposed_pct: Optional[float]
    created_at: str


class NegotiationDetailOut(BaseModel):
    id: int
    student_id: int
    display_name: str
    profession: str
    employer: str
    starting_salary: float
    avtal_norm_pct: Optional[float]
    final_pct: Optional[float]
    final_salary: Optional[float]
    status: str
    started_at: str
    completed_at: Optional[str]
    teacher_summary_md: Optional[str]
    rounds: list[NegotiationDetailRoundOut]


@router.get(
    "/teacher/employer/negotiations/{negotiation_id}",
    response_model=NegotiationDetailOut,
)
def teacher_negotiation_detail(
    negotiation_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> NegotiationDetailOut:
    """Full transkript av ett lönesamtal — för pedagogisk granskning."""
    _require_school()
    teacher_id = info.teacher_id or 0
    with master_session() as s:
        n = s.get(SalaryNegotiation, negotiation_id)
        if n is None:
            raise HTTPException(404, "Samtalet finns inte")
        st = s.get(Student, n.student_id)
        if st is None or st.teacher_id != teacher_id:
            raise HTTPException(403, "Inte din elev")
        rounds = (
            s.query(NegotiationRound)
            .filter(NegotiationRound.negotiation_id == n.id)
            .order_by(NegotiationRound.round_no.asc())
            .all()
        )
        return NegotiationDetailOut(
            id=n.id,
            student_id=n.student_id,
            display_name=st.display_name,
            profession=n.profession,
            employer=n.employer,
            starting_salary=float(n.starting_salary),
            avtal_norm_pct=n.avtal_norm_pct,
            final_pct=n.final_pct,
            final_salary=(
                float(n.final_salary) if n.final_salary is not None else None
            ),
            status=n.status,
            started_at=n.started_at.isoformat(),
            completed_at=(
                n.completed_at.isoformat() if n.completed_at else None
            ),
            teacher_summary_md=n.teacher_summary_md,
            rounds=[
                NegotiationDetailRoundOut(
                    round_no=r.round_no,
                    student_message=r.student_message,
                    employer_response=r.employer_response,
                    proposed_pct=r.proposed_pct,
                    created_at=r.created_at.isoformat(),
                )
                for r in rounds
            ],
        )


@router.post(
    "/teacher/employer/{student_id}/negotiation/reset",
)
def teacher_force_reset_negotiation(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    """Markera elevens aktiva lönesamtal som 'abandoned' så hen kan
    starta nytt. Använd för demo eller felaktigt påbörjade samtal.
    Påverkar inte pending_salary om den redan satts."""
    _require_school()
    teacher_id = info.teacher_id or 0
    _verify_teacher_owns_student(teacher_id, student_id)
    from datetime import datetime as _dt
    with master_session() as s:
        active = (
            s.query(SalaryNegotiation)
            .filter(
                SalaryNegotiation.student_id == student_id,
                SalaryNegotiation.status == "active",
            )
            .all()
        )
        n = 0
        for a in active:
            a.status = "abandoned"
            a.completed_at = _dt.utcnow()
            n += 1
        s.flush()
        return {"reset_count": n}
