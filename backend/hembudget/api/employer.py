"""API-router för arbetsgivar-dynamik (idé 1 i dev_v1.md).

Endpoints:
 - GET  /employer/status            — översikt: satisfaction + avtal + pension
 - GET  /employer/events            — eventlogg för aktuell elev (C4b)
 - GET  /employer/questions/next    — slumpa nästa obesvarad fråga (C4c)
 - POST /employer/questions/answer  — svara på fråga, applicera delta (C4c)

Lärar-impersonations stöds: `x-as-student`-header gör att läraren ser
elevens vy. Eleven själv ser bara sina egna events. Manuell-delta från
lärare läggs till i C4d.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..school import is_enabled as school_enabled
from ..school.engines import master_session
from ..school.employer_models import (
    CollectiveAgreement,
    EmployerSatisfaction,
    EmployerSatisfactionEvent,
    ProfessionAgreement,
)
from ..school.models import Student, StudentProfile
from .deps import TokenInfo, require_token

log = logging.getLogger(__name__)

router = APIRouter(prefix="/employer", tags=["employer"])


def _require_school() -> None:
    if not school_enabled():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "School mode inaktivt",
        )


def _resolve_student_id(info: TokenInfo) -> int:
    """Hämta vilken elev requesten gäller. För elev → egna ID.
    För lärare → måste impersonera (x-as-student) vilket
    StudentScopeMiddleware redan plockat upp; vi tar
    info.student_id om det finns där."""
    if info.role == "student" and info.student_id:
        return info.student_id
    if info.role == "teacher" and info.student_id:
        # Impersonations-läge — middleware har satt student_id för
        # lärare som har x-as-student-header och äger eleven.
        return info.student_id
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "Ingen elev-context — eleven loggar in själv eller "
        "läraren skickar x-as-student-header",
    )


def _resolve_agreement_for_profile(
    s: Session, profile: StudentProfile,
) -> tuple[Optional[ProfessionAgreement], Optional[CollectiveAgreement]]:
    """Hitta avtalet för (profession, employer). Mer specifikt
    employer_pattern vinner — vi sorterar längsta först och tar
    första substring-match."""
    rows = (
        s.query(ProfessionAgreement)
        .filter(ProfessionAgreement.profession == profile.profession)
        .all()
    )
    # Sortera: längst employer_pattern först (mest specifik)
    rows.sort(key=lambda r: -len(r.employer_pattern or ""))
    chosen: Optional[ProfessionAgreement] = None
    for row in rows:
        pattern = row.employer_pattern or ""
        if not pattern:
            # Default-rad — använd om inget specifikt matchat ännu
            if chosen is None:
                chosen = row
            continue
        if pattern.lower() in (profile.employer or "").lower():
            chosen = row
            break
    if chosen is None:
        return None, None
    agreement: Optional[CollectiveAgreement] = None
    if chosen.agreement_id:
        agreement = s.get(CollectiveAgreement, chosen.agreement_id)
    return chosen, agreement


# ---------- Schemas ----------

class AgreementOut(BaseModel):
    code: str
    name: str
    union: str
    employer_org: str
    summary_md: str
    source_url: Optional[str] = None
    verified: bool  # True om verified_at är satt
    meta: dict


class SatisfactionOut(BaseModel):
    score: int
    trend: str  # "rising" | "falling" | "stable"
    last_event_at: Optional[str] = None


class EmployerStatusOut(BaseModel):
    student_id: int
    profession: str
    employer: str
    gross_salary_monthly: int
    pending_salary_monthly: Optional[int] = None
    pending_effective_from: Optional[str] = None  # ISO-date
    pension_pct: Optional[float] = None
    satisfaction: SatisfactionOut
    agreement: Optional[AgreementOut] = None
    has_agreement: bool


def _ensure_satisfaction(
    s: Session, student_id: int,
) -> EmployerSatisfaction:
    """Skapa EmployerSatisfaction-rad om den saknas (default 70).

    Görs lazy så seedningen inte behöver räkna ut alla elever
    proaktivt — eleven får en rad första gången hens
    satisfaction efterfrågas."""
    row = (
        s.query(EmployerSatisfaction)
        .filter(EmployerSatisfaction.student_id == student_id)
        .first()
    )
    if row:
        return row
    row = EmployerSatisfaction(student_id=student_id, score=70, trend="stable")
    s.add(row)
    s.flush()
    return row


def _compute_trend(s: Session, student_id: int) -> str:
    """Trend baserat på senaste 5 events delta-summa.

    > 0 → 'rising', < 0 → 'falling', annars 'stable'.
    """
    rows = (
        s.query(EmployerSatisfactionEvent.delta_score)
        .filter(EmployerSatisfactionEvent.student_id == student_id)
        .order_by(EmployerSatisfactionEvent.ts.desc())
        .limit(5)
        .all()
    )
    if not rows:
        return "stable"
    delta_sum = sum(r[0] for r in rows)
    if delta_sum > 1:
        return "rising"
    if delta_sum < -1:
        return "falling"
    return "stable"


def _apply_delta(
    s: Session,
    student_id: int,
    *,
    kind: str,
    delta: int,
    reason_md: str,
    meta: Optional[dict] = None,
) -> EmployerSatisfactionEvent:
    """Applicera ett delta på en elevs satisfaction.

    - Skapar EmployerSatisfactionEvent-rad
    - Justerar EmployerSatisfaction.score (klamp 0–100)
    - Räknar om trend
    - Sätter last_event_at

    Returnerar den nya event-raden så caller kan länka från
    annan tabell (t.ex. WorkplaceQuestionAnswer.event_id).
    """
    sat = _ensure_satisfaction(s, student_id)
    new_score = max(0, min(100, sat.score + delta))
    event = EmployerSatisfactionEvent(
        student_id=student_id,
        kind=kind,
        delta_score=delta,
        reason_md=reason_md,
        meta=meta,
    )
    s.add(event)
    s.flush()
    sat.score = new_score
    sat.last_event_at = event.ts
    sat.trend = _compute_trend(s, student_id)
    s.flush()
    return event


# ---------- Event-schemas ----------

class EventOut(BaseModel):
    id: int
    ts: str  # ISO datetime
    kind: str
    delta_score: int
    reason_md: str
    meta: Optional[dict] = None


class EventListOut(BaseModel):
    events: list[EventOut]
    total: int


# ---------- Endpoints ----------

@router.get("/status", response_model=EmployerStatusOut)
def get_status(info: TokenInfo = Depends(require_token)) -> EmployerStatusOut:
    """Aktuell arbetsgivar-status: lön, satisfaction, avtal, pension."""
    _require_school()
    student_id = _resolve_student_id(info)

    with master_session() as s:
        student = s.get(Student, student_id)
        if not student:
            raise HTTPException(404, "Eleven finns inte")
        profile = (
            s.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        if not profile:
            raise HTTPException(
                404,
                "Eleven har ingen profil ännu — kör onboardingen först",
            )

        sat = _ensure_satisfaction(s, student_id)
        prof_agr, agreement = _resolve_agreement_for_profile(s, profile)

        agreement_out: Optional[AgreementOut] = None
        if agreement:
            agreement_out = AgreementOut(
                code=agreement.code,
                name=agreement.name,
                union=agreement.union,
                employer_org=agreement.employer_org,
                summary_md=agreement.summary_md,
                source_url=agreement.source_url,
                verified=agreement.verified_at is not None,
                meta=agreement.meta or {},
            )

        pension_pct: Optional[float] = None
        if prof_agr and prof_agr.pension_rate_pct is not None:
            pension_pct = float(prof_agr.pension_rate_pct)

        return EmployerStatusOut(
            student_id=student_id,
            profession=profile.profession,
            employer=profile.employer,
            gross_salary_monthly=profile.gross_salary_monthly,
            pending_salary_monthly=profile.pending_salary_monthly,
            pending_effective_from=(
                profile.pending_effective_from.isoformat()
                if profile.pending_effective_from else None
            ),
            pension_pct=pension_pct,
            satisfaction=SatisfactionOut(
                score=sat.score,
                trend=sat.trend,
                last_event_at=(
                    sat.last_event_at.isoformat() if sat.last_event_at else None
                ),
            ),
            agreement=agreement_out,
            has_agreement=agreement is not None,
        )


@router.get("/events", response_model=EventListOut)
def list_events(
    limit: int = 50,
    info: TokenInfo = Depends(require_token),
) -> EventListOut:
    """Eventlogg för aktuell elev — senaste händelserna först.

    Pedagogisk transparens: varje delta har reason_md som förklarar
    varför scoren rörde sig. Lärar-impersonering tillåten via
    x-as-student.
    """
    _require_school()
    student_id = _resolve_student_id(info)
    limit = max(1, min(limit, 500))

    with master_session() as s:
        total = (
            s.query(EmployerSatisfactionEvent)
            .filter(EmployerSatisfactionEvent.student_id == student_id)
            .count()
        )
        rows = (
            s.query(EmployerSatisfactionEvent)
            .filter(EmployerSatisfactionEvent.student_id == student_id)
            .order_by(EmployerSatisfactionEvent.ts.desc())
            .limit(limit)
            .all()
        )
        return EventListOut(
            events=[
                EventOut(
                    id=r.id,
                    ts=r.ts.isoformat(),
                    kind=r.kind,
                    delta_score=r.delta_score,
                    reason_md=r.reason_md,
                    meta=r.meta,
                )
                for r in rows
            ],
            total=total,
        )
