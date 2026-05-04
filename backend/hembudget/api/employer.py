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
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..school import is_enabled as school_enabled
from ..school.engines import master_session
from ..school.employer_models import (
    CollectiveAgreement,
    EmployerSatisfaction,
    EmployerSatisfactionEvent,
    NegotiationConfig,
    NegotiationRound,
    ProfessionAgreement,
    SalaryNegotiation,
    WorkplaceQuestion,
    WorkplaceQuestionAnswer,
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
    """Hämta vilken elev requesten gäller.

    - Elev-token: ``info.student_id`` är satt direkt vid token-skapande.
    - Lärare med ``x-as-student``-impersonation: middleware har redan
      verifierat att eleven tillhör läraren och satt
      ``current_actor_student`` i ContextVar:n. Vi läser den.
      OBS: Vi får INTE läsa ``info.student_id`` för lärare — det är
      alltid None på lärar-tokens. (Det var en bugg i tidigare
      versioner som fick alla impersonerade lärare att få 400 här.)

    Höjer 400 om ingen student-kontext finns."""
    if info.role == "student" and info.student_id:
        return info.student_id
    if info.role == "teacher":
        from ..school.engines import get_current_actor_student
        sid = get_current_actor_student()
        if sid is not None:
            return sid
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


# ---------- Workplace-frågor ----------

class QuestionOptionOut(BaseModel):
    """Skickas till eleven UTAN delta + explanation — skulle annars
    avslöja vad som är 'rätt' svar innan eleven valt.
    """
    index: int
    text: str


class QuestionOut(BaseModel):
    id: int
    code: str
    scenario_md: str
    options: list[QuestionOptionOut]
    difficulty: int
    tags: Optional[list] = None


class QuestionAnswerIn(BaseModel):
    question_id: int
    chosen_index: int


class QuestionAnswerOut(BaseModel):
    delta_applied: int
    chosen_explanation: str
    correct_path_md: str
    new_score: int
    new_trend: str


def _pick_next_question(
    s: Session, student_id: int,
) -> Optional[WorkplaceQuestion]:
    """Plocka en obesvarad fråga åt eleven.

    Strategi: lägsta `difficulty` först bland obesvarade, deterministiskt
    sortera på id efter det så samma elev får samma ordning vid samma
    DB-state. Detta gör testning förutsägbar.
    """
    answered_ids = {
        a.question_id for a in (
            s.query(WorkplaceQuestionAnswer.question_id)
            .filter(WorkplaceQuestionAnswer.student_id == student_id)
            .all()
        )
    }
    q = s.query(WorkplaceQuestion)
    if answered_ids:
        q = q.filter(~WorkplaceQuestion.id.in_(answered_ids))
    return (
        q.order_by(
            WorkplaceQuestion.difficulty.asc(),
            WorkplaceQuestion.id.asc(),
        )
        .first()
    )


@router.get("/questions/next", response_model=Optional[QuestionOut])
def next_question(
    info: TokenInfo = Depends(require_token),
) -> Optional[QuestionOut]:
    """Returnera nästa obesvarade arbetsplats-fråga för aktuell elev.

    Returnerar null om alla frågor besvarats — UI:n visar då 'inga
    fler frågor just nu'. Pedagogiskt: vi avslöjar inte deltas eller
    explanations innan eleven valt.
    """
    _require_school()
    student_id = _resolve_student_id(info)

    with master_session() as s:
        q = _pick_next_question(s, student_id)
        if q is None:
            return None
        opts_raw = q.options or []
        return QuestionOut(
            id=q.id,
            code=q.code,
            scenario_md=q.scenario_md,
            options=[
                QuestionOptionOut(index=i, text=str(o.get("text", "")))
                for i, o in enumerate(opts_raw)
            ],
            difficulty=q.difficulty,
            tags=q.tags,
        )


@router.post("/questions/answer", response_model=QuestionAnswerOut)
def answer_question(
    payload: QuestionAnswerIn,
    info: TokenInfo = Depends(require_token),
) -> QuestionAnswerOut:
    """Eleven svarar på en fråga. Vi:

    1. Validerar att frågan finns och eleven inte redan svarat
    2. Plockar valt alternativ + dess delta + explanation
    3. Skapar event via _apply_delta (justerar score + trend)
    4. Skapar WorkplaceQuestionAnswer-rad (länkad till event)
    5. Returnerar feedback (delta + explanation + correct_path)
    """
    _require_school()
    student_id = _resolve_student_id(info)

    with master_session() as s:
        q = s.get(WorkplaceQuestion, payload.question_id)
        if q is None:
            raise HTTPException(404, "Frågan finns inte")

        # Idempotens: om redan svarat, returnera tidigare resultat
        existing = (
            s.query(WorkplaceQuestionAnswer)
            .filter(
                WorkplaceQuestionAnswer.student_id == student_id,
                WorkplaceQuestionAnswer.question_id == q.id,
            )
            .first()
        )
        if existing:
            opts = q.options or []
            chosen_explanation = ""
            if 0 <= existing.chosen_index < len(opts):
                chosen_explanation = str(
                    opts[existing.chosen_index].get("explanation", "")
                )
            sat = _ensure_satisfaction(s, student_id)
            return QuestionAnswerOut(
                delta_applied=existing.delta_applied,
                chosen_explanation=chosen_explanation,
                correct_path_md=q.correct_path_md,
                new_score=sat.score,
                new_trend=sat.trend,
            )

        opts = q.options or []
        if not (0 <= payload.chosen_index < len(opts)):
            raise HTTPException(400, "Ogiltigt val (chosen_index)")
        chosen = opts[payload.chosen_index]
        delta = int(chosen.get("delta", 0))
        explanation = str(chosen.get("explanation", ""))

        # Pedagogisk reason_md = elevens val + kort förklaring + tagg
        reason_md = (
            f"**Du svarade**: {chosen.get('text', '')}\n\n"
            f"{explanation}"
        )
        event = _apply_delta(
            s, student_id,
            kind="question_answered",
            delta=delta,
            reason_md=reason_md,
            meta={
                "question_id": q.id,
                "question_code": q.code,
                "chosen_index": payload.chosen_index,
            },
        )
        s.add(WorkplaceQuestionAnswer(
            student_id=student_id,
            question_id=q.id,
            chosen_index=payload.chosen_index,
            delta_applied=delta,
            event_id=event.id,
        ))
        s.flush()

        sat = _ensure_satisfaction(s, student_id)
        return QuestionAnswerOut(
            delta_applied=delta,
            chosen_explanation=explanation,
            correct_path_md=q.correct_path_md,
            new_score=sat.score,
            new_trend=sat.trend,
        )


# ---------- Lönesamtal (idé 2) ----------

class NegotiationRoundOut(BaseModel):
    round_no: int
    student_message: str
    employer_response: str
    proposed_pct: Optional[float]
    created_at: str


class NegotiationOut(BaseModel):
    id: int
    student_id: int
    profession: str
    employer: str
    starting_salary: float
    avtal_norm_pct: Optional[float]
    avtal_code: Optional[str]
    status: str  # 'active' | 'completed' | 'abandoned'
    started_at: str
    completed_at: Optional[str]
    final_salary: Optional[float]
    final_pct: Optional[float]
    teacher_summary_md: Optional[str]
    rounds: list[NegotiationRoundOut]
    max_rounds: int


class StartNegotiationOut(BaseModel):
    negotiation: NegotiationOut
    briefing_md: str  # Pedagogisk text till eleven inför rond 1
    # Maria öppnar samtalet · dynamiskt AI-genererat hälsningsmeddelande
    # baserat på elevens karaktär + senaste arbetsplats-events.
    opening_message: Optional[str] = None


class SendMessageIn(BaseModel):
    message: str = Field(min_length=10, max_length=1500)


class SendMessageOut(BaseModel):
    round_no: int
    employer_response: str
    proposed_pct: Optional[float]
    is_final_round: bool
    negotiation_status: str
    # Tone-bedömning · Maria observerar elevens stil per rond.
    # -15..+15. None om AI inte är tillgängligt.
    tone_score: Optional[int] = None
    tone_reason: Optional[str] = None


class CompleteNegotiationIn(BaseModel):
    accept_offer: bool = True


class CompleteNegotiationOut(BaseModel):
    final_pct: Optional[float]
    final_salary: Optional[float]
    avtal_norm_pct: Optional[float]
    pending_effective_from: Optional[str]
    summary_md: str
    # Förhandlingsbetyg 0-100 + bryt-ned
    grade: int = 0
    grade_label: str = ""
    grade_strengths: list[str] = []
    grade_improvements: list[str] = []
    # Pentagon-deltar som applicerades vid avslut (för animation)
    pentagon_deltas: dict = {}
    # "Maria kommer ihåg" — påverkar framtida events. Polaritet:
    # "positive" | "negative" | "neutral"
    maria_memory_polarity: str = "neutral"
    maria_memory_md: Optional[str] = None
    # Total ton-summering (ackumulerat över alla ronder)
    tone_total: int = 0
    # Lönedelta · per månad + per år (för animation/UI)
    salary_delta_per_month: Optional[float] = None
    salary_delta_per_year: Optional[float] = None


def _get_or_create_config() -> NegotiationConfig:
    """Hämta singleton-config (skapa om saknas). Inte fastnyckel
    eftersom default-värdena är meningsfulla även orörda."""
    with master_session() as s:
        cfg = s.query(NegotiationConfig).first()
        if cfg is None:
            cfg = NegotiationConfig()
            s.add(cfg)
            s.flush()
        # Detacha så vi kan returnera en kopia utan session-bindning
        s.refresh(cfg)
        # Returnera primitiva fält som dict för att undvika
        # session-stängning / lazy load-problem
        return NegotiationConfig(
            id=cfg.id,
            max_rounds=cfg.max_rounds,
            max_input_tokens_per_round=cfg.max_input_tokens_per_round,
            max_output_tokens_per_round=cfg.max_output_tokens_per_round,
            model=cfg.model,
            disabled=cfg.disabled,
        )


def _negotiation_to_out(
    s: Session, n: SalaryNegotiation, max_rounds: int,
) -> NegotiationOut:
    rounds = (
        s.query(NegotiationRound)
        .filter(NegotiationRound.negotiation_id == n.id)
        .order_by(NegotiationRound.round_no.asc())
        .all()
    )
    return NegotiationOut(
        id=n.id,
        student_id=n.student_id,
        profession=n.profession,
        employer=n.employer,
        starting_salary=float(n.starting_salary),
        avtal_norm_pct=n.avtal_norm_pct,
        avtal_code=n.avtal_code,
        status=n.status,
        started_at=n.started_at.isoformat(),
        completed_at=(
            n.completed_at.isoformat() if n.completed_at else None
        ),
        final_salary=(
            float(n.final_salary) if n.final_salary is not None else None
        ),
        final_pct=n.final_pct,
        teacher_summary_md=n.teacher_summary_md,
        rounds=[
            NegotiationRoundOut(
                round_no=r.round_no,
                student_message=r.student_message,
                employer_response=r.employer_response,
                proposed_pct=r.proposed_pct,
                created_at=r.created_at.isoformat(),
            )
            for r in rounds
        ],
        max_rounds=max_rounds,
    )


def _build_briefing_md(
    profile: StudentProfile,
    agreement: Optional[CollectiveAgreement],
    avtal_norm_pct: Optional[float],
    sat_score: int,
) -> str:
    parts = [
        f"## Inför ditt lönesamtal\n",
        f"Du jobbar som **{profile.profession}** på **{profile.employer}** "
        f"och har {int(profile.gross_salary_monthly):,} kr/mån i "
        f"bruttolön.".replace(",", " "),
    ]
    if agreement and avtal_norm_pct is not None:
        parts.append(
            f"\nDitt avtal **{agreement.name}** ger en revision på "
            f"~{avtal_norm_pct} % i år. Det är ramen — du kan landa "
            "över eller under beroende på samtalet."
        )
    elif avtal_norm_pct is None:
        parts.append(
            "\nDu omfattas inte av kollektivavtal — det finns ingen "
            "central revisionsnorm. Höjningen är helt upp till "
            "förhandling."
        )
    parts.append(
        f"\n**Tips inför samtalet:**\n"
        f"- Förbered konkreta argument: vad har du levererat? Vilken "
        f"ny kompetens har du tagit på dig?\n"
        f"- Marknadsdata stärker dig — kolla SCB eller jobbportaler.\n"
        f"- Du har 5 ronder. AI-chefen ger ett bud i varje rond. "
        f"Du kan acceptera eller försöka pressa.\n"
        f"- Hot om uppsägning utan plan funkar inte — chefen håller "
        f"sitt bud."
    )
    if sat_score < 40:
        parts.append(
            "\n*Din arbetsgivar-nöjdhetsfaktor är låg just nu. Det "
            "påverkar förhandlingsutrymmet — chefen kommer hålla "
            "lägre bud än om du presterat starkt.*"
        )
    elif sat_score >= 75:
        parts.append(
            "\n*Din arbetsgivar-nöjdhetsfaktor är hög. Chefen ser "
            "dig som en värdefull medarbetare och har utrymme att "
            "ge mer än avtals-normen.*"
        )
    return "\n".join(parts)


@router.post("/negotiation/start", response_model=StartNegotiationOut)
def start_negotiation(
    info: TokenInfo = Depends(require_token),
) -> StartNegotiationOut:
    """Starta nytt lönesamtal — eller återuppta pågående.

    Endast EN aktiv session per elev åt gången. Om en redan finns
    återges den; annars skapas ny från elevens nuvarande profil.
    """
    _require_school()
    student_id = _resolve_student_id(info)
    cfg = _get_or_create_config()
    if cfg.disabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Lönesamtal är avstängt av super-admin",
        )

    with master_session() as s:
        # Pågående session?
        active = (
            s.query(SalaryNegotiation)
            .filter(
                SalaryNegotiation.student_id == student_id,
                SalaryNegotiation.status == "active",
            )
            .order_by(SalaryNegotiation.started_at.desc())
            .first()
        )
        if active is None:
            profile = (
                s.query(StudentProfile)
                .filter(StudentProfile.student_id == student_id)
                .first()
            )
            if profile is None:
                raise HTTPException(
                    404,
                    "Eleven har ingen profil — kör onboardingen först",
                )
            _, agreement = _resolve_agreement_for_profile(s, profile)
            # Plocka årets revisions-pct från meta
            year = str(__import__("datetime").datetime.utcnow().year)
            avtal_pct: Optional[float] = None
            if agreement and isinstance(agreement.meta, dict):
                rev = agreement.meta.get("revision_pct_year") or {}
                if isinstance(rev, dict) and year in rev:
                    avtal_pct = float(rev[year])
            active = SalaryNegotiation(
                student_id=student_id,
                profession=profile.profession,
                employer=profile.employer,
                starting_salary=profile.gross_salary_monthly,
                avtal_norm_pct=avtal_pct,
                avtal_code=agreement.code if agreement else None,
                status="active",
            )
            s.add(active)
            s.flush()

        # Bygg briefing
        profile = (
            s.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        agreement: Optional[CollectiveAgreement] = None
        if active.avtal_code:
            agreement = (
                s.query(CollectiveAgreement)
                .filter(CollectiveAgreement.code == active.avtal_code)
                .first()
            )
        sat = _ensure_satisfaction(s, student_id)
        briefing = _build_briefing_md(
            profile, agreement, active.avtal_norm_pct, sat.score,
        ) if profile else "Profil saknas."

        # Maria öppnar samtalet · genereras EN gång per session och
        # cachas på SalaryNegotiation.opening_message så återbesök
        # inte triggar nya AI-anrop.
        opening = active.opening_message
        if not opening and profile is not None:
            from ..school.models import Student as _Stu
            stu = s.get(_Stu, student_id)
            student_name = (
                stu.display_name if stu else "eleven"
            )
            recent_events = [
                e.kind for e in (
                    s.query(EmployerSatisfactionEvent)
                    .filter(
                        EmployerSatisfactionEvent.student_id == student_id,
                    )
                    .order_by(EmployerSatisfactionEvent.ts.desc())
                    .limit(3)
                    .all()
                )
            ]
            from ..school import ai as ai_core
            opening_res = ai_core.negotiate_salary_opening(
                student_name=student_name,
                profession=active.profession,
                employer=active.employer,
                salary=int(float(active.starting_salary)),
                years=2,
                satisfaction_score=sat.score,
                satisfaction_trend=sat.trend,
                recent_events=recent_events,
            )
            if opening_res is not None:
                opening = opening_res.text
                active.opening_message = opening
                s.flush()

        return StartNegotiationOut(
            negotiation=_negotiation_to_out(s, active, cfg.max_rounds),
            briefing_md=briefing,
            opening_message=opening,
        )


@router.post(
    "/negotiation/{negotiation_id}/message",
    response_model=SendMessageOut,
)
def send_negotiation_message(
    negotiation_id: int,
    payload: SendMessageIn,
    info: TokenInfo = Depends(require_token),
) -> SendMessageOut:
    """En rond i lönesamtalet — eleven skickar argument, AI svarar."""
    _require_school()
    student_id = _resolve_student_id(info)
    cfg = _get_or_create_config()
    if cfg.disabled:
        raise HTTPException(503, "Lönesamtal är avstängt av super-admin")

    # AI-gating sker via _gate_ai i ai_admin-modulen — inte detta lager.
    # Vi förlitar oss på require_token + att ai_core hanterar avstängd nyckel.

    with master_session() as s:
        n = s.get(SalaryNegotiation, negotiation_id)
        if n is None or n.student_id != student_id:
            raise HTTPException(404, "Samtalet finns inte")
        if n.status != "active":
            raise HTTPException(400, "Samtalet är redan avslutat")

        existing_rounds = (
            s.query(NegotiationRound)
            .filter(NegotiationRound.negotiation_id == n.id)
            .order_by(NegotiationRound.round_no.asc())
            .all()
        )
        if len(existing_rounds) >= cfg.max_rounds:
            raise HTTPException(
                400,
                f"Max {cfg.max_rounds} ronder uppnått — avsluta samtalet",
            )

        # Hämta kontext för AI
        profile = (
            s.query(StudentProfile)
            .filter(StudentProfile.student_id == n.student_id)
            .first()
        )
        agreement: Optional[CollectiveAgreement] = None
        if n.avtal_code:
            agreement = (
                s.query(CollectiveAgreement)
                .filter(CollectiveAgreement.code == n.avtal_code)
                .first()
            )
        sat = _ensure_satisfaction(s, n.student_id)
        recent_events = [
            e.kind for e in (
                s.query(EmployerSatisfactionEvent)
                .filter(
                    EmployerSatisfactionEvent.student_id == n.student_id,
                )
                .order_by(EmployerSatisfactionEvent.ts.desc())
                .limit(3)
                .all()
            )
        ]

        # Bygg history för Claude
        history: list[dict] = []
        for r in existing_rounds:
            history.append({"role": "user", "content": r.student_message})
            history.append({"role": "assistant", "content": r.employer_response})

        student_name = "eleven"
        if profile:
            from ..school.models import Student
            stu = s.get(Student, n.student_id)
            if stu:
                student_name = stu.display_name

        from ..school import ai as ai_core
        result = ai_core.negotiate_salary_round(
            history=history,
            new_message=payload.message,
            student_name=student_name,
            profession=n.profession,
            employer=n.employer,
            salary=int(float(n.starting_salary)),
            years=2,  # Vi har inte hire_date — antagande
            agreement_name=agreement.name if agreement else "(inget avtal)",
            avtal_pct=n.avtal_norm_pct or 3.0,
            satisfaction_score=sat.score,
            satisfaction_trend=sat.trend,
            recent_events=recent_events,
            round_no=len(existing_rounds) + 1,
            max_rounds=cfg.max_rounds,
            max_tokens=cfg.max_output_tokens_per_round,
        )
        if result is None:
            last = ai_core.get_last_error() or "okänt fel"
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                f"AI-anropet misslyckades: {last}",
            )

        proposed = ai_core.extract_proposed_pct(result.text)
        round_no = len(existing_rounds) + 1

        # Maria-AI bedömer ton/professionalism · -15..+15. Påverkar
        # pentagon (social/safety) och EmployerSatisfaction direkt.
        # Misslyckas tyst — då gör vi ingen pentagon-effekt.
        tone_score, tone_reason = ai_core.evaluate_negotiation_tone(
            student_name=student_name,
            student_message=payload.message,
        )
        if tone_score is not None:
            try:
                # Pentagon: ton påverkar social (samtalskänsla) och
                # safety (anställningsförhållande). Skala ned från
                # -15..+15 till -5..+5 (max-tröghet per event).
                from ..game_engine.pentagon import (
                    apply_pentagon_delta as _apd,
                )
                axis_delta = max(-5, min(5, round(tone_score / 3)))
                if axis_delta != 0:
                    _apd(
                        n.student_id,
                        axis="social",
                        requested_delta=axis_delta,
                        reason_kind="event",
                        explanation=(
                            f"Lönesamtal rond {round_no} · ton: "
                            f"{tone_reason or 'AI-bedömning'}"
                        ),
                    )
                    _apd(
                        n.student_id,
                        axis="safety",
                        requested_delta=axis_delta,
                        reason_kind="event",
                        explanation=(
                            f"Lönesamtal rond {round_no} · ton: "
                            f"{tone_reason or 'AI-bedömning'}"
                        ),
                    )
            except Exception:
                import logging as _logging
                _logging.getLogger(__name__).exception(
                    "tone-pentagon failed",
                )

            # EmployerSatisfaction: skala -15..+15 till -3..+3 så ett
            # otrevligt samtal sänker satisfaction märkbart men inte
            # förödande, och ett välhanterat höjer det.
            try:
                sat_delta = max(-3, min(3, round(tone_score / 5)))
                if sat_delta != 0:
                    sat.score = max(0, min(100, sat.score + sat_delta))
                    s.add(EmployerSatisfactionEvent(
                        student_id=n.student_id,
                        kind="negotiation_tone",
                        delta_score=sat_delta,
                        reason_md=(
                            f"Lönesamtal rond {round_no}: "
                            f"{tone_reason or 'AI-bedömning av ton'}"
                        ),
                        meta={
                            "negotiation_id": n.id,
                            "round_no": round_no,
                            "tone_score": tone_score,
                        },
                    ))
            except Exception:
                import logging as _logging
                _logging.getLogger(__name__).exception(
                    "tone-satisfaction failed",
                )

        s.add(NegotiationRound(
            negotiation_id=n.id,
            round_no=round_no,
            student_message=payload.message,
            employer_response=result.text,
            proposed_pct=proposed,
            tone_score=tone_score,
            tone_reason=tone_reason,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        ))
        s.flush()

        is_final = round_no >= cfg.max_rounds

        return SendMessageOut(
            round_no=round_no,
            employer_response=result.text,
            proposed_pct=proposed,
            is_final_round=is_final,
            negotiation_status=n.status,
            tone_score=tone_score,
            tone_reason=tone_reason,
        )


@router.get(
    "/negotiation/{negotiation_id}",
    response_model=NegotiationOut,
)
def get_negotiation(
    negotiation_id: int,
    info: TokenInfo = Depends(require_token),
) -> NegotiationOut:
    """Hämta hela samtalet (alla ronder + status)."""
    _require_school()
    student_id = _resolve_student_id(info)
    cfg = _get_or_create_config()
    with master_session() as s:
        n = s.get(SalaryNegotiation, negotiation_id)
        if n is None or n.student_id != student_id:
            raise HTTPException(404, "Samtalet finns inte")
        return _negotiation_to_out(s, n, cfg.max_rounds)


class AcceptPreviewOut(BaseModel):
    """Förhandsvisning av konsekvenser INNAN eleven trycker Acceptera/Avsluta.

    Beräknar utifrån sista bud + avtals-norm + tone-historik så eleven
    ser exakt vad valet ger innan det sker. Helt deterministiskt — ingen
    AI-anrop. Endpoints är POST för att matcha REST-konventionen att
    sida-effektsfri preview kan ändå ha stor data, men implementation
    är read-only.
    """
    final_pct: Optional[float]
    avtal_norm_pct: Optional[float]
    starting_salary: float
    new_salary_if_accepted: Optional[float]
    salary_delta_per_month: Optional[float]
    salary_delta_per_year: Optional[float]
    # Pentagon-effekter om man accepterar / avslutar
    accept_ekonomi_delta: int
    accept_social_delta: int
    accept_safety_delta: int
    abandon_social_delta: int
    abandon_safety_delta: int
    # Arbetsgivar-nöjdhet
    accept_employer_sat_delta: int
    abandon_employer_sat_delta: int
    # Sammanfattning av tone-historiken (ackumulerad effekt redan
    # applicerad rond-för-rond, visas här som referens).
    tone_history_total: int
    # Pedagogisk text · risk-varning eller positiv signal
    warning_md: Optional[str] = None


@router.get(
    "/negotiation/{negotiation_id}/accept-preview",
    response_model=AcceptPreviewOut,
)
def accept_negotiation_preview(
    negotiation_id: int,
    info: TokenInfo = Depends(require_token),
) -> AcceptPreviewOut:
    """Visa konsekvenser av Acceptera/Avsluta innan eleven trycker."""
    _require_school()
    student_id = _resolve_student_id(info)
    cfg = _get_or_create_config()
    with master_session() as s:
        n = s.get(SalaryNegotiation, negotiation_id)
        if n is None or n.student_id != student_id:
            raise HTTPException(404, "Samtalet finns inte")

        rounds = (
            s.query(NegotiationRound)
            .filter(NegotiationRound.negotiation_id == n.id)
            .order_by(NegotiationRound.round_no.desc())
            .all()
        )
        final_pct: Optional[float] = None
        for r in rounds:
            if r.proposed_pct is not None:
                final_pct = r.proposed_pct
                break

        starting = float(n.starting_salary or 0)
        new_salary: Optional[float] = None
        delta_m: Optional[float] = None
        delta_y: Optional[float] = None
        if final_pct is not None and starting > 0:
            new_salary = round(starting * (1 + final_pct / 100), 2)
            delta_m = round(new_salary - starting, 2)
            delta_y = round(delta_m * 12, 2)

        # Ekonomi-pentagon: skalar löneökningen mot inkomst-schablonen
        # 0,5 % av brutto = +1 ekonomi-poäng (klampat -10..+10).
        accept_ekonomi = 0
        if delta_m is not None and starting > 0:
            pct = (delta_m / starting) * 100
            accept_ekonomi = max(-10, min(10, round(pct * 2)))

        # Avtals-jämförelse · ger pedagogisk varning om bud är under
        # avtals-norm
        warning: Optional[str] = None
        avtal = n.avtal_norm_pct
        if final_pct is None:
            warning = (
                "AI har inte lagt något konkret bud än — om du avslutar nu "
                "är lönen oförändrad."
            )
        elif avtal is not None and final_pct < avtal - 0.3:
            warning = (
                f"Budet ({final_pct:.1f} %) ligger UNDER avtals-norm "
                f"({avtal:.1f} %). Du kan be om mer eller avbryta och "
                "förhandla igen senare."
            )
        elif avtal is not None and final_pct > avtal + 0.5:
            warning = (
                f"Budet ({final_pct:.1f} %) ligger ÖVER avtals-norm "
                f"({avtal:.1f} %). Bra prestation — Maria är nöjd."
            )

        # Pentagon-deltar för accept/abandon
        accept_social = 3 if final_pct is not None else 0
        accept_safety = 2 if final_pct is not None else 0
        abandon_social = -2
        abandon_safety = -1
        accept_emp_sat = (
            3 if (avtal is not None and final_pct is not None and final_pct >= avtal)
            else (1 if final_pct is not None else 0)
        )
        abandon_emp_sat = -2

        tone_total = sum(
            (r.tone_score or 0) for r in rounds
        )

        return AcceptPreviewOut(
            final_pct=final_pct,
            avtal_norm_pct=avtal,
            starting_salary=starting,
            new_salary_if_accepted=new_salary,
            salary_delta_per_month=delta_m,
            salary_delta_per_year=delta_y,
            accept_ekonomi_delta=accept_ekonomi,
            accept_social_delta=accept_social,
            accept_safety_delta=accept_safety,
            abandon_social_delta=abandon_social,
            abandon_safety_delta=abandon_safety,
            accept_employer_sat_delta=accept_emp_sat,
            abandon_employer_sat_delta=abandon_emp_sat,
            tone_history_total=tone_total,
            warning_md=warning,
        )


@router.post(
    "/negotiation/{negotiation_id}/complete",
    response_model=CompleteNegotiationOut,
)
def complete_negotiation(
    negotiation_id: int,
    payload: CompleteNegotiationIn,
    info: TokenInfo = Depends(require_token),
) -> CompleteNegotiationOut:
    """Avsluta lönesamtalet.

    accept_offer=True → ta sista bud-pct, sätt pending_salary på
    profilen så lönespec-generatorn applicerar nästa månad.
    accept_offer=False → ingen ändring (status=abandoned).
    """
    _require_school()
    student_id = _resolve_student_id(info)
    cfg = _get_or_create_config()

    with master_session() as s:
        n = s.get(SalaryNegotiation, negotiation_id)
        if n is None or n.student_id != student_id:
            raise HTTPException(404, "Samtalet finns inte")
        if n.status != "active":
            raise HTTPException(400, "Samtalet är redan avslutat")

        rounds = (
            s.query(NegotiationRound)
            .filter(NegotiationRound.negotiation_id == n.id)
            .order_by(NegotiationRound.round_no.desc())
            .all()
        )
        # Sista föreslagna pct vinner
        final_pct: Optional[float] = None
        for r in rounds:
            if r.proposed_pct is not None:
                final_pct = r.proposed_pct
                break

        from datetime import datetime as _dt, date as _date
        n.completed_at = _dt.utcnow()

        pending_effective_from: Optional[_date] = None
        new_salary: Optional[float] = None

        if not payload.accept_offer or final_pct is None:
            n.status = "abandoned"
            summary = (
                "## Lönesamtal avbrutet\n\n"
                "Du valde att inte acceptera budet — eller AI lämnade "
                "inget tydligt bud i ronderna. Din lön är oförändrad."
            )
            # Pentagon · avbrutet samtal är en mild social-signal
            try:
                from ..game_engine.pentagon import apply_pentagon_delta
                apply_pentagon_delta(
                    student_id,
                    axis="social",
                    requested_delta=-1,
                    reason_kind="decision",
                    reason_id=n.id,
                    reason_table="salary_negotiations",
                    explanation="lönesamtal avbrutet utan beslut",
                )
            except Exception:
                pass
        else:
            n.status = "completed"
            new_salary_dec = float(n.starting_salary) * (1 + final_pct / 100)
            new_salary = round(new_salary_dec)
            n.final_salary = Decimal(str(new_salary))
            n.final_pct = final_pct

            # Skriv DIREKT till profilens gross_salary_monthly +
            # net_salary_monthly. pending_salary fanns tidigare men
            # ingen läste den någonstans (dead data) — lönen höjdes
            # aldrig i tick_month nästa månad.
            #
            # Behåller pending_effective_from som info till lärare,
            # men lönen är aktiv från och med direkt.
            from ..school.tax import compute_net_salary as _maria_net
            profile = (
                s.query(StudentProfile)
                .filter(StudentProfile.student_id == student_id)
                .first()
            )
            if profile:
                profile.pending_salary_monthly = new_salary
                today = _date.today()
                if today.month == 12:
                    pending_effective_from = _date(today.year + 1, 1, 1)
                else:
                    pending_effective_from = _date(
                        today.year, today.month + 1, 1,
                    )
                profile.pending_effective_from = pending_effective_from
                # KRITISKT · realisera lönen direkt så monthly_engine
                # nästa tick använder den nya nivån.
                profile.gross_salary_monthly = new_salary
                tax_after = _maria_net(new_salary)
                profile.net_salary_monthly = tax_after.net_monthly
                profile.tax_rate_effective = tax_after.effective_rate

            # Auto-genererad lärar-sammanfattning
            avtal_diff = (
                final_pct - n.avtal_norm_pct
                if n.avtal_norm_pct is not None else None
            )
            assess = ""
            if avtal_diff is not None:
                if avtal_diff > 0.5:
                    assess = (
                        f"Eleven landade {avtal_diff:.1f} pp över "
                        "avtals-norm — bra förhandling."
                    )
                elif avtal_diff < -0.5:
                    assess = (
                        f"Eleven landade {abs(avtal_diff):.1f} pp under "
                        "avtals-norm — accepterade lågt bud. "
                        "**Pedagogisk varning** — diskutera vid behov."
                    )
                else:
                    assess = "Eleven landade i nivå med avtals-normen."
            summary = (
                f"## Lönesamtal avslutat\n\n"
                f"**Slutbud:** {final_pct:.1f} % "
                f"({int(float(n.starting_salary)):,} → {new_salary:,} kr)\n\n"
                f"**Avtals-norm i år:** "
                f"{n.avtal_norm_pct:.1f} %\n\n"
                f"{assess}"
            ).replace(",", " ")
            n.teacher_summary_md = summary

            # Logga som event på satisfaction-ledger för spårbarhet
            _apply_delta(
                s, student_id,
                kind="salary_negotiation_completed",
                delta=0,
                reason_md=(
                    f"Lönesamtal avslutat: {final_pct:.1f} % höjning "
                    f"(avtal: {n.avtal_norm_pct or 0:.1f} %). Ny lön "
                    f"{new_salary:,} kr gäller från ".replace(",", " ")
                    + (
                        pending_effective_from.isoformat()
                        if pending_effective_from else "nästa månad"
                    )
                ),
                meta={"negotiation_id": n.id, "final_pct": final_pct},
            )

            # Pentagon-koppling · framgång i lönesamtal höjer economy + social.
            # Skala efter hur långt över avtals-normen eleven landade.
            try:
                from ..game_engine.pentagon import apply_pentagon_delta
                norm = n.avtal_norm_pct or 3.0
                diff = final_pct - norm
                if diff >= 1.5:
                    eco_d, soc_d = 4, 2
                elif diff >= 0.5:
                    eco_d, soc_d = 2, 1
                elif diff >= -0.5:
                    eco_d, soc_d = 1, 0
                elif diff >= -1.5:
                    eco_d, soc_d = -1, -1
                else:
                    eco_d, soc_d = -2, -2
                if eco_d != 0:
                    apply_pentagon_delta(
                        student_id,
                        axis="economy",
                        requested_delta=eco_d,
                        reason_kind="decision",
                        reason_id=n.id,
                        reason_table="salary_negotiations",
                        explanation=(
                            f"lönesamtal: {final_pct:.1f}% (avtal {norm:.1f}%)"
                        ),
                    )
                if soc_d != 0:
                    apply_pentagon_delta(
                        student_id,
                        axis="social",
                        requested_delta=soc_d,
                        reason_kind="decision",
                        reason_id=n.id,
                        reason_table="salary_negotiations",
                        explanation=(
                            f"lönesamtal-resultat: "
                            f"{'över' if diff > 0 else 'under'} avtals-norm"
                        ),
                    )
            except Exception:
                pass

        # === Förhandlingsbetyg + minne (Maria kommer ihåg) ===
        # Räkna ihop totalt och bryt ned till strengths/improvements
        # som visas i slutskärmen.
        tone_total = sum((r.tone_score or 0) for r in rounds)
        n_rounds = len(rounds)
        avtal_norm = n.avtal_norm_pct or 3.0
        diff_to_norm = (
            (final_pct - avtal_norm) if final_pct is not None else None
        )

        # Bas-betyg 50 + bonus för bra ton + bonus för bud över avtal
        grade = 50
        if tone_total > 0:
            grade += min(25, tone_total)  # +1 per +1 ton, cap 25
        else:
            grade += max(-25, tone_total)  # -1 per -1 ton, floor -25
        if diff_to_norm is not None:
            if diff_to_norm > 0:
                grade += min(20, int(diff_to_norm * 8))
            else:
                grade += max(-15, int(diff_to_norm * 6))
        # Engagemang · 3+ ronder ger små bonusar
        if n_rounds >= 3:
            grade += 5
        if n_rounds >= 5:
            grade += 5
        grade = max(0, min(100, grade))

        if grade >= 85:
            grade_label = "Mästerlig förhandling"
        elif grade >= 70:
            grade_label = "Stark förhandling"
        elif grade >= 50:
            grade_label = "Solid förhandling"
        elif grade >= 30:
            grade_label = "Mer förberedelse nästa gång"
        else:
            grade_label = "Tuff lärdom"

        strengths: list[str] = []
        improvements: list[str] = []
        if tone_total >= 5:
            strengths.append(
                "Du höll en saklig och respektfull ton genom samtalet — "
                "Maria uppfattade dig som professionell."
            )
        elif tone_total <= -5:
            improvements.append(
                "Tonen blev tidvis konfliktdriven. Sakliga argument och "
                "lugn röst öppnar fler bud än press."
            )
        if diff_to_norm is not None and diff_to_norm > 0.5:
            strengths.append(
                f"Slutbudet ({final_pct:.1f} %) ligger över avtals-norm "
                f"({avtal_norm:.1f} %) — det är resultatet av god "
                "argumentation."
            )
        elif diff_to_norm is not None and diff_to_norm < -0.5:
            improvements.append(
                f"Slutbudet hamnade under avtals-norm "
                f"({avtal_norm:.1f} %). Hänvisa explicit till avtalet "
                "i nästa samtal — det är din rätt."
            )
        if n_rounds <= 2 and n.status == "completed":
            improvements.append(
                "Samtalet avslutades efter få ronder. Att ankra om och "
                "be om mer brukar ge 0,5–1 procentenhet extra."
            )
        if not strengths:
            strengths.append(
                "Du tog steget och förhandlade — många gör aldrig det."
            )
        if not improvements:
            improvements.append(
                "Förbered konkret marknadsdata och din BATNA till nästa "
                "samtal — det stärker varje argument."
            )

        # Pentagon-deltar för animation (de faktiska deltarna applicerades
        # ovan men vi vill kunna visa dem i slutskärmen).
        pentagon_deltas: dict = {}
        if n.status == "completed" and final_pct is not None:
            norm = n.avtal_norm_pct or 3.0
            diff = final_pct - norm
            if diff >= 1.5:
                pentagon_deltas = {"economy": 4, "social": 2}
            elif diff >= 0.5:
                pentagon_deltas = {"economy": 2, "social": 1}
            elif diff >= -0.5:
                pentagon_deltas = {"economy": 1, "social": 0}
            elif diff >= -1.5:
                pentagon_deltas = {"economy": -1, "social": -1}
            else:
                pentagon_deltas = {"economy": -2, "social": -2}
        elif n.status == "abandoned":
            pentagon_deltas = {"social": -1}

        # "Maria kommer ihåg" · läggs som EmployerSatisfactionEvent
        # med kind="maria_memory" så framtida arbetsplats-events kan
        # peka tillbaka. Polariteten avgör om Maria är välvilligt
        # inställd nästa gång.
        if n.status == "completed" and tone_total >= 5 and (
            diff_to_norm is None or diff_to_norm >= -0.5
        ):
            memory_polarity = "positive"
            memory_md = (
                f"Maria minns dig som välförberedd och saklig. "
                f"Det öppnar dörrar för bättre projekt och nästa "
                f"lönesamtal."
            )
            sat_delta = +5
        elif tone_total <= -5 or (
            diff_to_norm is not None and diff_to_norm < -1.5
        ) or n.status == "abandoned":
            memory_polarity = "negative"
            memory_md = (
                "Maria minns samtalet som ansträngt. Räkna med att "
                "hon håller en hårdare linje vid nästa tillfälle."
            )
            sat_delta = -4
        else:
            memory_polarity = "neutral"
            memory_md = (
                "Maria minns samtalet som professionellt och OK. "
                "Inget som påverkar framtida bud nämnvärt."
            )
            sat_delta = 0

        try:
            sat = _ensure_satisfaction(s, student_id)
            sat.score = max(0, min(100, sat.score + sat_delta))
            s.add(EmployerSatisfactionEvent(
                student_id=student_id,
                kind="maria_memory",
                delta_score=sat_delta,
                reason_md=memory_md,
                meta={
                    "negotiation_id": n.id,
                    "polarity": memory_polarity,
                    "final_pct": final_pct,
                    "tone_total": tone_total,
                    "grade": grade,
                },
            ))
        except Exception:
            pass

        # Lönedeltar för slutskärmen
        delta_m: Optional[float] = None
        delta_y: Optional[float] = None
        if new_salary is not None and float(n.starting_salary) > 0:
            delta_m = round(
                float(new_salary) - float(n.starting_salary), 2,
            )
            delta_y = round(delta_m * 12, 2)

        s.flush()

        return CompleteNegotiationOut(
            final_pct=final_pct,
            final_salary=new_salary,
            avtal_norm_pct=n.avtal_norm_pct,
            pending_effective_from=(
                pending_effective_from.isoformat()
                if pending_effective_from else None
            ),
            summary_md=summary,
            grade=grade,
            grade_label=grade_label,
            grade_strengths=strengths,
            grade_improvements=improvements,
            pentagon_deltas=pentagon_deltas,
            maria_memory_polarity=memory_polarity,
            maria_memory_md=memory_md,
            tone_total=tone_total,
            salary_delta_per_month=delta_m,
            salary_delta_per_year=delta_y,
        )
