"""Företagsläget · spelmotor-endpoints.

Spec: deb/README.md.

Egen fil för att hålla api/foretag.py läsbar — denna fil hanterar
spelmotorn (offerter, jobb, marknadsföring, beslut, leverantörsfakturor,
manuell tick). Mountas på samma `/v2/foretag` prefix som foretag.py.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

log = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..business.engine import auto_tick_if_due, run_business_week
from ..business.engine.tick_engine import deliver_job
from ..business.game_clock import current_game_date
from ..business.models import (
    BusinessDecision,
    BusinessTickJob,
    Company,
    CompanyInvoice,
    Job,
    JobOpportunity,
    MarketingCampaign,
    Quote,
    SupplierInvoice,
)
from ..db.base import session_scope
from .deps import TokenInfo, require_token

router = APIRouter(prefix="/v2/foretag", tags=["foretag-engine"])
teacher_router = APIRouter(
    prefix="/v2/teacher/foretag", tags=["teacher-foretag-engine"],
)


# === Helpers ===


def _require_student(info: TokenInfo) -> int:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast elev-konto kan använda Företagsläget.",
        )
    return info.student_id


def _get_active_company(s) -> Company:
    co = (
        s.query(Company)
        .filter(Company.active.is_(True))
        .order_by(Company.id.desc())
        .first()
    )
    if co is None:
        raise HTTPException(400, "Skapa bolag först")
    return co


def _require_teacher(info: TokenInfo) -> int:
    if info.role != "teacher" or info.teacher_id is None:
        raise HTTPException(403, "Endast lärare")
    return info.teacher_id


# === Schemas: Opportunity / Quote ===


class OpportunityOut(BaseModel):
    id: int
    title: str
    description: str
    customer_name: str
    customer_segment: str
    industry_tag: Optional[str]
    requires_car: bool = False
    market_price: int
    expected_delivery_days: int
    deadline_on: str
    received_on: str
    status: str
    week_no: int
    has_quote: bool
    # Pedagogiska detaljer som visas vid "förlorad/vunnen". Eleven ska
    # ALLTID kunna förstå varför kunden tackade ja/nej — inte bara se
    # ett rött FÖRLORAD-pill utan förklaring. quote_* är None tills
    # eleven lämnat offert; decision_* är None tills kunden bestämt.
    quote_offered_price: Optional[int] = None
    quote_offered_delivery_days: Optional[int] = None
    quote_pitch_text: Optional[str] = None
    quote_pitch_quality: Optional[float] = None
    quote_accept_probability: Optional[float] = None
    quote_accepted: Optional[bool] = None
    quote_decision_explanation: Optional[str] = None


class QuoteIn(BaseModel):
    offered_price: int = Field(ge=1)
    offered_delivery_days: int = Field(ge=1, le=120)
    pitch_text: Optional[str] = None


class QuoteOut(BaseModel):
    id: int
    opportunity_id: int
    offered_price: int
    offered_delivery_days: int
    pitch_text: Optional[str]
    pitch_quality: Optional[float]
    accept_probability: Optional[float]
    accepted: Optional[bool]
    decision_explanation: Optional[str]
    submitted_on: str
    decided_on: Optional[str]


def _to_opportunity_out(opp: JobOpportunity) -> OpportunityOut:
    q = opp.quote
    return OpportunityOut(
        id=opp.id,
        title=opp.title,
        description=opp.description,
        customer_name=opp.customer_name,
        customer_segment=opp.customer_segment,
        industry_tag=opp.industry_tag,
        requires_car=bool(opp.requires_car),
        market_price=opp.market_price,
        expected_delivery_days=opp.expected_delivery_days,
        deadline_on=opp.deadline_on.isoformat(),
        received_on=opp.received_on.isoformat(),
        status=opp.status,
        week_no=opp.week_no,
        has_quote=q is not None,
        quote_offered_price=q.offered_price if q else None,
        quote_offered_delivery_days=q.offered_delivery_days if q else None,
        quote_pitch_text=q.pitch_text if q else None,
        quote_pitch_quality=(
            float(q.pitch_quality) if q and q.pitch_quality is not None else None
        ),
        quote_accept_probability=(
            float(q.accept_probability)
            if q and q.accept_probability is not None else None
        ),
        quote_accepted=q.accepted if q else None,
        quote_decision_explanation=q.decision_explanation if q else None,
    )


def _to_quote_out(q: Quote) -> QuoteOut:
    return QuoteOut(
        id=q.id,
        opportunity_id=q.opportunity_id,
        offered_price=q.offered_price,
        offered_delivery_days=q.offered_delivery_days,
        pitch_text=q.pitch_text,
        pitch_quality=float(q.pitch_quality) if q.pitch_quality else None,
        accept_probability=(
            float(q.accept_probability)
            if q.accept_probability else None
        ),
        accepted=q.accepted,
        decision_explanation=q.decision_explanation,
        submitted_on=q.submitted_on.isoformat(),
        decided_on=q.decided_on.isoformat() if q.decided_on else None,
    )


# === Endpoints: Tick-status (för UI-countdown) ===


class TickStatusOut(BaseModel):
    """Realtid-status för spelarens biz-tick. Frontend pollar för
    att visa 'nästa tick om HH:MM' och 'svar förväntas' på offerter."""
    last_auto_tick_at: Optional[str]  # ISO · när senaste tick kördes
    next_tick_at: str  # ISO · när nästa tick körs (+ AUTO_TICK_INTERVAL_HOURS)
    interval_hours: float  # AUTO_TICK_INTERVAL_HOURS
    seconds_until_next_tick: int
    week_no: int
    open_quotes_count: int
    last_tick_status: Optional[str] = None  # "done" | "failed" | None
    last_tick_error: Optional[str] = None


@router.get("/tick-status", response_model=TickStatusOut)
def get_tick_status(info: TokenInfo = Depends(require_token)):
    """Realtid-status för biz-tick. Används av UI:t för countdown.

    1 real-timme = 1 biz-vecka. När eleven öppnar offerter-sidan
    triggas auto_tick_if_due som kör en tick om 1+ h passerat. Det
    här endpointet säger BARA när nästa tick kommer — kör inte ticken.
    """
    from ..business.engine.tick_engine import (
        AUTO_TICK_INTERVAL_HOURS,
    )
    _require_student(info)
    with session_scope() as s:
        co = _get_active_company(s)
        last_at = co.last_auto_tick_at
        if last_at is None:
            # Aldrig tickat (precis skapad) → nästa tick är NU
            next_at = datetime.utcnow()
        else:
            next_at = last_at + timedelta(hours=AUTO_TICK_INTERVAL_HOURS)
        seconds_until = max(
            0, int((next_at - datetime.utcnow()).total_seconds()),
        )
        open_quotes = (
            s.query(Quote)
            .join(JobOpportunity, JobOpportunity.id == Quote.opportunity_id)
            .filter(
                Quote.company_id == co.id,
                Quote.accepted.is_(None),
                JobOpportunity.status == "quoted",
            )
            .count()
        )
        # Senaste BusinessTickJob för debug — om den senaste failade
        # vet vi att alla auto-tick-försök kraschar och quotes inte
        # avgörs trots att timmar passerat.
        last_status = None
        last_error = None
        try:
            last_job = (
                s.query(BusinessTickJob)
                .filter(BusinessTickJob.company_id == co.id)
                .order_by(BusinessTickJob.id.desc())
                .first()
            )
            if last_job is not None:
                last_status = last_job.status
                last_error = last_job.error
        except Exception:
            pass

        return TickStatusOut(
            last_auto_tick_at=last_at.isoformat() if last_at else None,
            next_tick_at=next_at.isoformat(),
            interval_hours=AUTO_TICK_INTERVAL_HOURS,
            seconds_until_next_tick=seconds_until,
            week_no=int(co.week_no or 0),
            open_quotes_count=open_quotes,
            last_tick_status=last_status,
            last_tick_error=last_error,
        )


# === Endpoints: Opportunity ===


@router.get("/opportunities", response_model=list[OpportunityOut])
def list_opportunities(
    info: TokenInfo = Depends(require_token),
    status_filter: Optional[str] = None,
):
    """Lista offertförfrågningar. Default = alla. Vanliga filter:
    'open' (kan offereras), 'quoted' (väntar på svar), 'won' (vunnit)."""
    _require_student(info)
    with session_scope() as s:
        co = _get_active_company(s)
        if co is None:
            return []
        # Auto-tick · drar fram så många biz-veckor som passerat sedan
        # senaste lasning så att eleven ser nya offertförfrågningar +
        # accept-besked från tidigare offerter dyka upp över tid utan
        # att klicka "Stega vecka". 1 biz-vecka per real-timme.
        auto_tick_if_due(s, company=co)

        # Pipeline-kickstart · om bolaget har bas-utrustning och inga
        # opps någonsin genererats kör vi pipeline-only så eleven
        # inte fastnar i tomt-state. VIKTIGT: kickstart_pipeline_only
        # bokar INGA kostnader (veckoränta, amortering, avskrivning)
        # — bara phase_c (offert-generering). Annars dubbel-debiteras
        # samma vecka när auto-tick sen kör igen.
        if co.has_base_equipment:
            existing_count = (
                s.query(JobOpportunity)
                .filter(JobOpportunity.company_id == co.id)
                .count()
            )
            if existing_count == 0:
                from ..business.engine.tick_engine import (
                    kickstart_pipeline_only,
                )
                try:
                    kickstart_pipeline_only(s, company=co, weeks=2)
                except Exception:
                    log.exception(
                        "list_opportunities: pipeline-kickstart misslyckades"
                    )
        q = (
            s.query(JobOpportunity)
            .filter(JobOpportunity.company_id == co.id)
        )
        if status_filter:
            q = q.filter(JobOpportunity.status == status_filter)
        rows = q.order_by(JobOpportunity.received_on.desc()).all()
        return [_to_opportunity_out(o) for o in rows]


@router.post(
    "/opportunities/{opp_id}/quote", response_model=QuoteOut,
)
def submit_quote(
    opp_id: int, body: QuoteIn,
    info: TokenInfo = Depends(require_token),
):
    """Lämna offert på en öppen förfrågan."""
    _require_student(info)
    with session_scope() as s:
        co = _get_active_company(s)
        opp = (
            s.query(JobOpportunity)
            .filter(
                JobOpportunity.id == opp_id,
                JobOpportunity.company_id == co.id,
            )
            .first()
        )
        if opp is None:
            raise HTTPException(404, "Förfrågan saknas")
        if opp.status != "open":
            raise HTTPException(
                400, f"Förfrågan har status '{opp.status}', kan ej offerera",
            )
        # Spärr · bil + bas-utrustning krävs
        if not co.has_base_equipment:
            raise HTTPException(
                403,
                "Du måste köpa bas-utrustning innan du kan svara på "
                "kundförfrågningar (Tillväxt-vyn).",
            )
        if opp.requires_car and not co.has_car:
            raise HTTPException(
                403,
                "Detta uppdrag kräver bil. Köp en i Tillväxt-vyn först.",
            )
        if opp.quote is not None:
            raise HTTPException(400, "Offert redan lämnad")

        # AI-bedömning av pitch (best-effort, avser pitch_quality 0..1).
        pitch_quality: Optional[Decimal] = None
        if body.pitch_text and body.pitch_text.strip():
            from ..business.ai import evaluate_quote_pitch
            try:
                pq = evaluate_quote_pitch(
                    pitch=body.pitch_text,
                    job_title=opp.title,
                    job_description=opp.description,
                    teacher_id=_resolve_teacher_id_for_student(
                        info.student_id,
                    ),
                )
                if pq is not None:
                    pitch_quality = Decimal(str(round(pq, 3)))
            except Exception:
                pitch_quality = None

        q = Quote(
            opportunity_id=opp_id,
            company_id=co.id,
            offered_price=body.offered_price,
            offered_delivery_days=body.offered_delivery_days,
            pitch_text=body.pitch_text,
            pitch_quality=pitch_quality,
            submitted_on=current_game_date(),
        )
        s.add(q)
        opp.status = "quoted"
        s.flush()
        return _to_quote_out(q)


@router.get("/opportunities/{opp_id}/quote", response_model=Optional[QuoteOut])
def get_quote(
    opp_id: int,
    info: TokenInfo = Depends(require_token),
):
    """Hämta offert + dess utfall (om kunden hunnit svara)."""
    _require_student(info)
    with session_scope() as s:
        co = _get_active_company(s)
        opp = (
            s.query(JobOpportunity)
            .filter(
                JobOpportunity.id == opp_id,
                JobOpportunity.company_id == co.id,
            )
            .first()
        )
        if opp is None or opp.quote is None:
            return None
        return _to_quote_out(opp.quote)


# === Schemas: Job ===


class JobOut(BaseModel):
    id: int
    title: str
    customer_name: str
    agreed_price: int
    started_on: str
    expected_complete_on: str
    delivered_on: Optional[str]
    status: str
    quality_score: Optional[int]
    invoice_id: Optional[int]
    # Tids-tracking · för live-countdown i UI
    estimated_hours: int = 0
    hours_per_week: int = 0
    days_remaining: int = 0  # antal dagar tills expected_complete_on
    days_total: int = 0      # totalt antal dagar från start till deadline
    progress_pct: int = 0    # 0-100 baserat på elapsed/total tid
    is_overdue: bool = False
    is_klass_pool: bool = False  # ⭐ klass-pool-jobb · högre belöning


class DeliverIn(BaseModel):
    """Bakåtkompat · gamla klienter kunde slidra quality_score 0-100.

    Nya klienter ska istället göra POST /jobs/{id}/submit-delivery-quiz
    med svar på 3 quiz-frågor. Den endpointen räknar quality_score
    automatiskt från svaren och kan inte fuskas.
    """
    quality_score: int = Field(ge=0, le=100)
    create_invoice: bool = True


class QuizQuestionOut(BaseModel):
    id: int
    category: str
    text: str
    # Alternativ visas i randomiserad ordning (a/b/c) så eleven inte
    # kan gissa "a är alltid bra".
    options: list[dict]  # [{"key": "a", "text": "...", "level": "good"}]


class QuizOut(BaseModel):
    job_id: int
    questions: list[QuizQuestionOut]


class QuizSubmitIn(BaseModel):
    # Lista med 3 svar · varje svar är "good"/"mid"/"bad"
    answers: list[str] = Field(min_length=3, max_length=3)
    create_invoice: bool = True


class QuizFeedbackItem(BaseModel):
    question_id: int
    question_text: str
    your_answer_level: str  # "good"/"mid"/"bad"
    your_answer_text: str
    best_answer_text: str
    explanation: str


class QuizSubmitOut(BaseModel):
    job: JobOut
    invoice_id: Optional[int]
    invoice_number: Optional[str]
    quality_score: int
    feedback: list[QuizFeedbackItem]


class DeliverOut(BaseModel):
    job: JobOut
    invoice_id: Optional[int]
    invoice_number: Optional[str]


def _to_job_out(j: Job) -> JobOut:
    today = current_game_date()
    days_total = max(1, (j.expected_complete_on - j.started_on).days)
    elapsed = max(0, (today - j.started_on).days)
    days_remaining = (j.expected_complete_on - today).days
    progress = min(100, int(round(elapsed / days_total * 100)))
    return JobOut(
        id=j.id, title=j.title, customer_name=j.customer_name,
        agreed_price=j.agreed_price,
        started_on=j.started_on.isoformat(),
        expected_complete_on=j.expected_complete_on.isoformat(),
        delivered_on=j.delivered_on.isoformat() if j.delivered_on else None,
        status=j.status,
        quality_score=j.quality_score,
        invoice_id=j.invoice_id,
        estimated_hours=int(j.estimated_hours or 0),
        hours_per_week=int(j.hours_per_week or 0),
        days_remaining=days_remaining,
        days_total=days_total,
        progress_pct=progress,
        is_overdue=(
            j.status == "in_progress" and days_remaining < 0
        ),
        is_klass_pool=(j.title or "").startswith("⭐ Klass-pool"),
    )


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    info: TokenInfo = Depends(require_token),
    status_filter: Optional[str] = None,
):
    _require_student(info)
    with session_scope() as s:
        co = _get_active_company(s)
        q = s.query(Job).filter(Job.company_id == co.id)
        if status_filter:
            q = q.filter(Job.status == status_filter)
        rows = q.order_by(Job.started_on.desc()).all()
        return [_to_job_out(j) for j in rows]


@router.post("/jobs/{job_id}/deliver", response_model=DeliverOut)
def deliver(
    job_id: int, body: DeliverIn,
    info: TokenInfo = Depends(require_token),
):
    """Eleven levererar ett jobb · sätter quality + skapar faktura."""
    sid = _require_student(info)
    with session_scope() as s:
        co = _get_active_company(s)
        job = (
            s.query(Job)
            .filter(Job.id == job_id, Job.company_id == co.id)
            .first()
        )
        if job is None:
            raise HTTPException(404, "Jobbet saknas")
        if job.status != "in_progress":
            raise HTTPException(
                400, f"Jobbet har status '{job.status}'",
            )

        delivered_job, invoice = deliver_job(
            s,
            company=co,
            job=job,
            quality_score=body.quality_score,
            create_invoice=body.create_invoice,
        )
        s.flush()

        # Pentagon-koppling: lyckad leverans höjer privat economy + leisure;
        # låg kvalitet sänker.
        try:
            from ..game_engine.pentagon import apply_pentagon_delta
            if body.quality_score >= 80:
                apply_pentagon_delta(
                    sid, axis="economy", requested_delta=2,
                    reason_kind="decision",
                    reason_id=job.id, reason_table="biz_jobs",
                    explanation=(
                        f"företag · levererat jobb {job.title} "
                        f"med kvalitet {body.quality_score}"
                    ),
                )
                apply_pentagon_delta(
                    sid, axis="leisure", requested_delta=1,
                    reason_kind="decision",
                    reason_id=job.id, reason_table="biz_jobs",
                    explanation="företag · framgångsrik leverans",
                )
            elif body.quality_score < 50:
                apply_pentagon_delta(
                    sid, axis="social", requested_delta=-2,
                    reason_kind="decision",
                    reason_id=job.id, reason_table="biz_jobs",
                    explanation=(
                        f"företag · låg kvalitet ({body.quality_score}) "
                        f"på leverans"
                    ),
                )
        except Exception:
            pass

        return DeliverOut(
            job=_to_job_out(delivered_job),
            invoice_id=invoice.id if invoice else None,
            invoice_number=(
                invoice.invoice_number if invoice else None
            ),
        )


# === Endpoints: Leverans-quiz =====================================
#
# Ersätter den fuskvänliga slidern (eleven valde själv 0-100). Nu
# svarar eleven på 3 situationsfrågor (kvalitet/kommunikation/tid/
# etik/teknik) med 3 alternativ vardera. Backend räknar quality_score
# från svaren · kan inte fuskas.


def _shuffle_options(
    q,  # business.delivery_quiz.QuizQuestion
    seed_int: int,
) -> list[dict]:
    """Randomisera ordningen så eleven inte kan gissa 'alternativ a är
    alltid bästa'. Seedat på (job_id + question_id) så samma elev
    får samma ordning vid omladdning av sidan = stabilt."""
    import random as _r
    rng = _r.Random(seed_int)
    items = [
        {"key": "good", "text": q.option_good, "level": "good"},
        {"key": "mid",  "text": q.option_mid,  "level": "mid"},
        {"key": "bad",  "text": q.option_bad,  "level": "bad"},
    ]
    rng.shuffle(items)
    # Ge dem stabila a/b/c-keys efter shuffle (frontend visar
    # 'a' / 'b' / 'c' så eleven inte ser level i UI).
    for i, item in enumerate(items):
        item["key"] = ["a", "b", "c"][i]
    return items


@router.get(
    "/jobs/{job_id}/quality-quiz",
    response_model=QuizOut,
)
def get_quality_quiz(
    job_id: int, info: TokenInfo = Depends(require_token),
):
    """Hämta 3 quiz-frågor för leveransen. Anti-repetition via
    Company.recent_quiz_question_ids så eleven inte ser samma fråga
    två leveranser i rad. Stabilt seedat på job_id så omladdning
    av sidan ger samma frågor."""
    _require_student(info)
    from ..business.delivery_quiz import pick_questions
    import random as _rnd_q
    with session_scope() as s:
        co = _get_active_company(s)
        job = (
            s.query(Job)
            .filter(Job.id == job_id, Job.company_id == co.id)
            .first()
        )
        if job is None:
            raise HTTPException(404, "Jobbet saknas")
        if job.status != "in_progress":
            raise HTTPException(
                400, f"Jobbet har status '{job.status}'",
            )
        # Stabil RNG: samma job ger samma frågor om eleven laddar om
        rng = _rnd_q.Random(f"quiz-{job.id}-{co.id}")
        recent = list(co.recent_quiz_question_ids or [])
        questions = pick_questions(
            industry_key=co.industry_key,
            recent_ids=recent,
            rng=rng,
        )
        out_qs = []
        for q in questions:
            opts = _shuffle_options(q, seed_int=q.id * 1000 + job.id)
            out_qs.append(QuizQuestionOut(
                id=q.id,
                category=q.category,
                text=q.text,
                options=opts,
            ))
        return QuizOut(job_id=job.id, questions=out_qs)


@router.post(
    "/jobs/{job_id}/submit-delivery-quiz",
    response_model=QuizSubmitOut,
)
def submit_delivery_quiz(
    job_id: int, body: QuizSubmitIn,
    info: TokenInfo = Depends(require_token),
):
    """Eleven har svarat på 3 quiz-frågor · backend räknar quality_score
    deterministiskt och levererar jobbet. Eleven kan INTE fuska."""
    sid = _require_student(info)
    from ..business.delivery_quiz import (
        get_question, pick_questions, score_answers, update_recent_ids,
    )
    import random as _rnd_q2
    with session_scope() as s:
        co = _get_active_company(s)
        job = (
            s.query(Job)
            .filter(Job.id == job_id, Job.company_id == co.id)
            .first()
        )
        if job is None:
            raise HTTPException(404, "Jobbet saknas")
        if job.status != "in_progress":
            raise HTTPException(
                400, f"Jobbet har status '{job.status}'",
            )

        # Återgenerera SAMMA frågor som vi gav i GET (samma seed)
        rng = _rnd_q2.Random(f"quiz-{job.id}-{co.id}")
        recent = list(co.recent_quiz_question_ids or [])
        questions = pick_questions(
            industry_key=co.industry_key,
            recent_ids=recent,
            rng=rng,
        )
        if len(questions) != 3:
            raise HTTPException(
                500, "Quiz-databasen är för liten",
            )

        # Validera svar
        for ans in body.answers:
            if ans not in ("good", "mid", "bad"):
                raise HTTPException(
                    422,
                    f"Ogiltigt svar '{ans}' · måste vara good/mid/bad",
                )

        quality_score = score_answers(body.answers)

        # Leverera jobbet med beräknad score
        delivered_job, invoice = deliver_job(
            s,
            company=co,
            job=job,
            quality_score=quality_score,
            create_invoice=body.create_invoice,
        )

        # Uppdatera anti-repetition · senaste 10 frågor
        new_ids = [q.id for q in questions]
        co.recent_quiz_question_ids = update_recent_ids(
            recent, new_ids, keep_n=10,
        )

        s.flush()

        # Pedagogisk feedback · vad var bäst-svaret + förklaring
        feedback: list[QuizFeedbackItem] = []
        for q, your_level in zip(questions, body.answers):
            your_text = {
                "good": q.option_good,
                "mid":  q.option_mid,
                "bad":  q.option_bad,
            }[your_level]
            feedback.append(QuizFeedbackItem(
                question_id=q.id,
                question_text=q.text,
                your_answer_level=your_level,
                your_answer_text=your_text,
                best_answer_text=q.option_good,
                explanation=q.explanation,
            ))

        # Pentagon-koppling (samma logik som gamla deliver-endpointen)
        try:
            from ..game_engine.pentagon import apply_pentagon_delta
            if quality_score >= 80:
                apply_pentagon_delta(
                    sid, axis="economy", requested_delta=2,
                    reason_kind="decision",
                    reason_id=job.id, reason_table="biz_jobs",
                    explanation=(
                        f"företag · levererat {job.title} med kvalitet "
                        f"{quality_score} (quiz)"
                    ),
                )
            elif quality_score < 50:
                apply_pentagon_delta(
                    sid, axis="social", requested_delta=-2,
                    reason_kind="decision",
                    reason_id=job.id, reason_table="biz_jobs",
                    explanation=(
                        f"företag · låg kvalitet {quality_score} på "
                        f"leverans (quiz)"
                    ),
                )
        except Exception:
            pass

        return QuizSubmitOut(
            job=_to_job_out(delivered_job),
            invoice_id=invoice.id if invoice else None,
            invoice_number=(
                invoice.invoice_number if invoice else None
            ),
            quality_score=quality_score,
            feedback=feedback,
        )


# === Schemas: Marketing ===


class MarketingIn(BaseModel):
    kind: str = Field(pattern="^(social|flygblad|google|sponsring|event)$")
    title: str = Field(min_length=2, max_length=200)
    copy_text: Optional[str] = None
    cost: int = Field(ge=1)
    duration_weeks: int = Field(ge=1, le=12, default=4)


class MarketingOut(BaseModel):
    id: int
    kind: str
    title: str
    copy_text: Optional[str]
    cost: int
    duration_weeks: int
    ai_quality_factor: Optional[float]
    ai_feedback: Optional[str]
    started_on: str
    ends_on: str
    active: bool


def _to_marketing_out(m: MarketingCampaign) -> MarketingOut:
    return MarketingOut(
        id=m.id, kind=m.kind, title=m.title, copy_text=m.copy_text,
        cost=m.cost, duration_weeks=m.duration_weeks,
        ai_quality_factor=(
            float(m.ai_quality_factor) if m.ai_quality_factor else None
        ),
        ai_feedback=m.ai_feedback,
        started_on=m.started_on.isoformat(),
        ends_on=m.ends_on.isoformat(),
        active=m.active,
    )


@router.get("/marketing", response_model=list[MarketingOut])
def list_marketing(
    info: TokenInfo = Depends(require_token),
    only_active: bool = False,
):
    _require_student(info)
    with session_scope() as s:
        co = _get_active_company(s)
        q = s.query(MarketingCampaign).filter(
            MarketingCampaign.company_id == co.id,
        )
        if only_active:
            q = q.filter(MarketingCampaign.active.is_(True))
        rows = q.order_by(MarketingCampaign.started_on.desc()).all()
        return [_to_marketing_out(m) for m in rows]


@router.post("/marketing", response_model=MarketingOut)
def create_marketing(
    body: MarketingIn,
    info: TokenInfo = Depends(require_token),
):
    """Skapa kampanj. Bokför kostnaden direkt + AI-bedöm copy om text finns."""
    _require_student(info)
    today = current_game_date()
    with session_scope() as s:
        co = _get_active_company(s)

        # Kassa-spärr · marknadsförings-kampanjer får inte ta saldo
        # minus. Returnera 402 så frontend kan föreslå tillväxtlån.
        from ..business.cash import compute_company_cash as _ccc
        bal = _ccc(s, co)
        if bal < body.cost:
            raise HTTPException(
                402,
                f"Otillräcklig kassa · {body.cost - bal} kr saknas. "
                f"Kassan är {bal} kr · kampanjen kostar {body.cost} kr. "
                "Ta ett tillväxtlån (Tillväxt → Lån) först.",
            )

        ai_factor = None
        ai_feedback = None
        if body.copy_text and body.copy_text.strip():
            from ..business.ai import evaluate_marketing_copy
            try:
                r = evaluate_marketing_copy(
                    copy_text=body.copy_text,
                    kind=body.kind,
                    teacher_id=_resolve_teacher_id_for_student(
                        info.student_id,
                    ),
                )
                if r is not None:
                    ai_factor = Decimal(str(round(r["factor"], 3)))
                    ai_feedback = r["feedback"]
            except Exception:
                pass

        m = MarketingCampaign(
            company_id=co.id,
            kind=body.kind,
            title=body.title,
            copy_text=body.copy_text,
            cost=body.cost,
            duration_weeks=body.duration_weeks,
            ai_quality_factor=ai_factor,
            ai_feedback=ai_feedback,
            base_pipeline_boost=Decimal("1.0"),
            started_on=today,
            ends_on=today + timedelta(weeks=body.duration_weeks),
            active=True,
        )
        s.add(m)

        # Bokför kostnaden direkt
        from ..business.models import CompanyTransaction as _Tx
        s.add(_Tx(
            company_id=co.id,
            occurred_on=today,
            kind="expense",
            category="marknadsforing",
            description=f"Kampanj · {body.title}",
            amount_excl_vat=Decimal(str(body.cost)),
            vat_rate=Decimal("0.25"),
            vat_amount=Decimal(str(int(round(body.cost * 0.25)))),
        ))

        # Marknadsföring kan ge en liten reputation-bump om AI gillar copy
        if ai_factor is not None and float(ai_factor) >= 1.2:
            from ..business.engine.reputation import (
                update_reputation_from_marketing,
            )
            co.reputation = update_reputation_from_marketing(
                co.reputation, float(ai_factor),
            )

        s.flush()
        return _to_marketing_out(m)


# === Marknadsförings-paket (10 nivåer · lokaltidning → TV) ===
#
# Pedagogisk koppling: eleven ser DIREKT hur högre rykte ökar chansen
# i kundförfrågningar (acceptance_model.py · reputation_term + marketing
# _term). Realistiska svenska annonspriser så jämförelsen mot omsättning
# ger en konkret känsla för marknadsförings-ROI.

MARKETING_PACKAGES: list[dict] = [
    {
        "key": "lokaltidning",
        "level": 1,
        "title": "Lokaltidning · annons",
        "channel": "Print · lokal",
        "cost": 3500,
        "duration_weeks": 2,
        "pipeline_boost": 1.05,
        "reputation_bump": 1,
        "description": (
            "Helsida i lokaltidningen (t.ex. Mariestads-Tidningen). "
            "Bas-paketet · liten räckvidd, men målgruppen läser noggrant."
        ),
    },
    {
        "key": "stads_facebook",
        "level": 2,
        "title": "Stadens Facebook-grupp",
        "channel": "Social · lokal",
        "cost": 1500,
        "duration_weeks": 2,
        "pipeline_boost": 1.04,
        "reputation_bump": 1,
        "description": (
            "Sponsrat inlägg i ortens Facebook-grupp. Billigt + virtuellt "
            "när folk taggar grannar."
        ),
    },
    {
        "key": "flygblad",
        "level": 3,
        "title": "Flygblad · 1 000 hushåll",
        "channel": "Print · direktreklam",
        "cost": 6500,
        "duration_weeks": 1,
        "pipeline_boost": 1.08,
        "reputation_bump": 1,
        "description": (
            "Distribution till 1 000 hushåll i ditt postnummer. "
            "Hög träffsäkerhet på lokal kundbas."
        ),
    },
    {
        "key": "google_lokal",
        "level": 4,
        "title": "Google Ads · lokala sökningar",
        "channel": "Sök · lokal",
        "cost": 12000,
        "duration_weeks": 4,
        "pipeline_boost": 1.15,
        "reputation_bump": 2,
        "description": (
            "Sökord som \"snickare Mariestad\" + Google Maps-pin. "
            "Folk som söker har KÖPINTRESSE — bästa ROI för småföretag."
        ),
    },
    {
        "key": "veckotidning",
        "level": 5,
        "title": "Veckotidning · regional helsida",
        "channel": "Print · regional",
        "cost": 18000,
        "duration_weeks": 3,
        "pipeline_boost": 1.18,
        "reputation_bump": 2,
        "description": (
            "Helsida i regional veckotidning (t.ex. Land, Hemmets Journal). "
            "Bredare målgrupp, mer status."
        ),
    },
    {
        "key": "radio_regional",
        "level": 6,
        "title": "Radio · regional reklam",
        "channel": "Radio · regional",
        "cost": 35000,
        "duration_weeks": 4,
        "pipeline_boost": 1.25,
        "reputation_bump": 4,
        "description": (
            "30-sekundersspots på regional radiostation. Hörs i bilen "
            "morgon + kväll · höjer top-of-mind."
        ),
    },
    {
        "key": "sponsring_idrott",
        "level": 7,
        "title": "Sponsring · idrottsförening",
        "channel": "Brand · sponsring",
        "cost": 50000,
        "duration_weeks": 12,
        "pipeline_boost": 1.20,
        "reputation_bump": 6,
        "description": (
            "Logo på matchtröjor + skylt på arena. Lägre direkt-ROI men "
            "STARK rykteseffekt — bygger varumärke och lokal goodwill."
        ),
    },
    {
        "key": "storstadstidning",
        "level": 8,
        "title": "Storstadstidning · halvsida",
        "channel": "Print · riks",
        "cost": 120000,
        "duration_weeks": 4,
        "pipeline_boost": 1.40,
        "reputation_bump": 5,
        "description": (
            "Halvsida i Aftonbladet eller Dagens Nyheter. Räckvidd över "
            "hela Sverige · seriöst varumärke."
        ),
    },
    {
        "key": "radio_riks",
        "level": 9,
        "title": "Radio · riksspelning",
        "channel": "Radio · riks",
        "cost": 250000,
        "duration_weeks": 6,
        "pipeline_boost": 1.55,
        "reputation_bump": 8,
        "description": (
            "Kampanj i P3 + P4 nationellt. Massiv räckvidd · folk känner "
            "igen ditt företag i hela landet."
        ),
    },
    {
        "key": "tv_reklam",
        "level": 10,
        "title": "TV-reklam · TV4 / Kanal 5 primetime",
        "channel": "TV · riks",
        "cost": 750000,
        "duration_weeks": 4,
        "pipeline_boost": 1.80,
        "reputation_bump": 12,
        "description": (
            "30-sekundersspots primetime. Det dyraste men starkaste "
            "marknadsverktyget. Förvandlar lokalt företag till nationellt."
        ),
    },
]


class MarketingPackageOut(BaseModel):
    key: str
    level: int
    title: str
    channel: str
    cost: int
    duration_weeks: int
    pipeline_boost: float
    reputation_bump: int
    description: str


class BuyPackageIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=40)


@router.get(
    "/marketing/packages", response_model=list[MarketingPackageOut],
)
def list_marketing_packages(info: TokenInfo = Depends(require_token)):
    """10-nivåers paketkatalog · lokaltidning → TV."""
    _require_student(info)
    return [MarketingPackageOut(**p) for p in MARKETING_PACKAGES]


@router.post("/marketing/packages/buy", response_model=MarketingOut)
def buy_marketing_package(
    body: BuyPackageIn,
    info: TokenInfo = Depends(require_token),
):
    """Köp ett marknadsförings-paket. Bokför kostnaden, skapar
    MarketingCampaign med tier-baserad pipeline_boost, och bumpar rykte
    omedelbart med paketets reputation_bump."""
    _require_student(info)
    pkg = next((p for p in MARKETING_PACKAGES if p["key"] == body.key), None)
    if pkg is None:
        raise HTTPException(404, "Paketet finns inte")

    today = current_game_date()
    with session_scope() as s:
        co = _get_active_company(s)

        # Hård spärr · paketet får inte ta kassan minus. Pedagogiskt:
        # 750 000 kr TV-reklam när kassan är 50k är inte feedback-i-
        # bokföringen, det är en katastrof. Returnera 402 så frontend
        # kan föreslå att ta tillväxtlån eller välja billigare paket.
        from .foretag_growth import _kassa
        bal = _kassa(s, co)
        if bal < pkg["cost"]:
            raise HTTPException(
                402,
                f"Otillräcklig kassa · {pkg['cost'] - bal} kr saknas. "
                f"Kassan är {bal} kr · paketet kostar {pkg['cost']} kr. "
                "Ta ett tillväxtlån (Tillväxt → Lån) eller välj ett "
                "billigare paket.",
            )

        m = MarketingCampaign(
            company_id=co.id,
            kind="paket",  # nytt kind-värde · tier-paket
            title=pkg["title"],
            copy_text=None,
            cost=pkg["cost"],
            duration_weeks=pkg["duration_weeks"],
            ai_quality_factor=None,
            ai_feedback=(
                f"Paketköp · {pkg['channel']}. "
                f"Pipeline-boost {pkg['pipeline_boost']:.2f}x · "
                f"rykte +{pkg['reputation_bump']}."
            ),
            base_pipeline_boost=Decimal(str(pkg["pipeline_boost"])),
            started_on=today,
            ends_on=today + timedelta(weeks=pkg["duration_weeks"]),
            active=True,
        )
        s.add(m)

        # Bokför hela paket-kostnaden direkt (engångsutlägg)
        from ..business.models import CompanyTransaction as _Tx
        s.add(_Tx(
            company_id=co.id,
            occurred_on=today,
            kind="expense",
            category="marknadsforing",
            description=f"Marknadsföringspaket · {pkg['title']}",
            amount_excl_vat=Decimal(str(pkg["cost"])),
            vat_rate=Decimal("0.25"),
            vat_amount=Decimal(str(int(round(pkg["cost"] * 0.25)))),
        ))

        # Bumpa rykte omedelbart · klamras till 0..100
        new_rep = min(100, max(0, int(co.reputation or 50) + int(pkg["reputation_bump"])))
        co.reputation = new_rep

        s.flush()
        return _to_marketing_out(m)


# === Schemas: Decision ===


class DecisionIn(BaseModel):
    # Alias-vänligt mönster · både UI-naturliga ('employee', 'leasing')
    # och tekniska ('hire_part_time', 'car_lease') accepteras. Frontend-
    # presetet skickar 'employee'/'leasing' men gamla tester kan
    # fortfarande använda de tekniska namnen.
    kind: str = Field(
        pattern=(
            "^(employee|hire_full_time|hire_part_time|wellness|"
            "leasing|car_lease|insurance|new_office)$"
        )
    )
    title: str = Field(min_length=2, max_length=200)
    monthly_cost: int = Field(ge=0, default=0)
    one_time_cost: int = Field(ge=0, default=0)
    capacity_delta: int = Field(default=0)
    reputation_delta: int = Field(default=0)
    insurance_kind: Optional[str] = None
    notes: Optional[str] = None


class DecisionOut(BaseModel):
    id: int
    kind: str
    title: str
    monthly_cost: int
    one_time_cost: int
    capacity_delta: int
    reputation_delta: int
    insurance_kind: Optional[str]
    started_on: str
    ends_on: Optional[str]
    active: bool


def _to_decision_out(d: BusinessDecision) -> DecisionOut:
    return DecisionOut(
        id=d.id, kind=d.kind, title=d.title,
        monthly_cost=d.monthly_cost, one_time_cost=d.one_time_cost,
        capacity_delta=d.capacity_delta,
        reputation_delta=d.reputation_delta,
        insurance_kind=d.insurance_kind,
        started_on=d.started_on.isoformat(),
        ends_on=d.ends_on.isoformat() if d.ends_on else None,
        active=d.active,
    )


@router.get("/decisions", response_model=list[DecisionOut])
def list_decisions(
    info: TokenInfo = Depends(require_token),
    only_active: bool = False,
):
    _require_student(info)
    with session_scope() as s:
        co = _get_active_company(s)
        q = s.query(BusinessDecision).filter(
            BusinessDecision.company_id == co.id,
        )
        if only_active:
            q = q.filter(BusinessDecision.active.is_(True))
        rows = q.order_by(BusinessDecision.started_on.desc()).all()
        return [_to_decision_out(d) for d in rows]


@router.post("/decisions", response_model=DecisionOut)
def create_decision(
    body: DecisionIn,
    info: TokenInfo = Depends(require_token),
):
    """Skapa beslut. Tillämpar capacity/reputation-delta direkt + bokför
    eventuell engångskostnad."""
    _require_student(info)
    today = current_game_date()
    with session_scope() as s:
        co = _get_active_company(s)
        # Kassa-spärr · engångskostnad + första veckans löpande kost
        # ska få plats. Pedagogiskt: aktivera inte ett 35 000 kr/mån-
        # beslut om kassan är 5 000 kr.
        from .foretag_growth import _kassa
        bal = _kassa(s, co)
        weekly = int(round((body.monthly_cost or 0) / 4))
        first_hit = (body.one_time_cost or 0) + weekly
        if bal < first_hit:
            raise HTTPException(
                402,
                f"Otillräcklig kassa · {first_hit - bal} kr saknas. "
                f"Kassan är {bal} kr men beslutet kostar "
                f"{body.one_time_cost} kr nu + {weekly} kr första veckan. "
                "Ta ett tillväxtlån (Tillväxt → Lån) först.",
            )
        d = BusinessDecision(
            company_id=co.id,
            kind=body.kind,
            title=body.title,
            monthly_cost=body.monthly_cost,
            one_time_cost=body.one_time_cost,
            capacity_delta=body.capacity_delta,
            reputation_delta=body.reputation_delta,
            insurance_kind=body.insurance_kind,
            started_on=today,
            active=True,
            notes=body.notes,
        )
        s.add(d)

        # Tillämpa effekter på Company direkt
        if body.capacity_delta:
            co.delivery_capacity = max(
                1, co.delivery_capacity + body.capacity_delta,
            )
        if body.reputation_delta:
            co.reputation = max(
                0, min(100, co.reputation + body.reputation_delta),
            )

        # Bokför engångskostnad
        if body.one_time_cost > 0:
            from ..business.models import CompanyTransaction as _Tx
            s.add(_Tx(
                company_id=co.id,
                occurred_on=today,
                kind="expense",
                category=f"decision:{body.kind}",
                description=f"Engångs · {body.title}",
                amount_excl_vat=Decimal(str(body.one_time_cost)),
                vat_rate=Decimal("0.25"),
                vat_amount=Decimal(
                    str(int(round(body.one_time_cost * 0.25))),
                ),
            ))

        s.flush()
        return _to_decision_out(d)


@router.delete("/decisions/{decision_id}", status_code=204)
def end_decision(
    decision_id: int,
    info: TokenInfo = Depends(require_token),
):
    """Avsluta ett beslut (anställning slut, försäkring sägs upp)."""
    _require_student(info)
    with session_scope() as s:
        co = _get_active_company(s)
        d = (
            s.query(BusinessDecision)
            .filter(
                BusinessDecision.id == decision_id,
                BusinessDecision.company_id == co.id,
            )
            .first()
        )
        if d is None:
            raise HTTPException(404, "Beslut saknas")
        if not d.active:
            return
        d.active = False
        d.ends_on = current_game_date()
        # Reverse capacity-delta
        if d.capacity_delta:
            co.delivery_capacity = max(
                1, co.delivery_capacity - d.capacity_delta,
            )
        s.flush()


# === Schemas: SupplierInvoice ===


class SupplierInvoiceOut(BaseModel):
    id: int
    sender_name: str
    invoice_number: str
    issued_on: str
    due_on: str
    description: str
    amount_excl_vat: int
    vat_rate: float
    source: str
    status: str
    paid_on: Optional[str]
    notes: Optional[str]


def _to_supplier_out(si: SupplierInvoice) -> SupplierInvoiceOut:
    return SupplierInvoiceOut(
        id=si.id,
        sender_name=si.sender_name,
        invoice_number=si.invoice_number,
        issued_on=si.issued_on.isoformat(),
        due_on=si.due_on.isoformat(),
        description=si.description,
        amount_excl_vat=si.amount_excl_vat,
        vat_rate=float(si.vat_rate),
        source=si.source,
        status=si.status,
        paid_on=si.paid_on.isoformat() if si.paid_on else None,
        notes=si.notes,
    )


@router.get("/supplier-invoices", response_model=list[SupplierInvoiceOut])
def list_supplier_invoices(
    info: TokenInfo = Depends(require_token),
    status_filter: Optional[str] = None,
):
    _require_student(info)
    with session_scope() as s:
        co = _get_active_company(s)
        q = s.query(SupplierInvoice).filter(
            SupplierInvoice.company_id == co.id,
        )
        if status_filter:
            q = q.filter(SupplierInvoice.status == status_filter)
        rows = q.order_by(SupplierInvoice.due_on.asc()).all()
        return [_to_supplier_out(si) for si in rows]


@router.post(
    "/supplier-invoices/{si_id}/pay", response_model=SupplierInvoiceOut,
)
def pay_supplier_invoice(
    si_id: int,
    info: TokenInfo = Depends(require_token),
):
    """Betala leverantörsfaktura · skapar CompanyTransaction expense."""
    _require_student(info)
    today = current_game_date()
    with session_scope() as s:
        co = _get_active_company(s)
        si = (
            s.query(SupplierInvoice)
            .filter(
                SupplierInvoice.id == si_id,
                SupplierInvoice.company_id == co.id,
            )
            .first()
        )
        if si is None:
            raise HTTPException(404, "Faktura saknas")
        if si.status == "paid":
            raise HTTPException(400, "Redan betald")

        # Kassa-spärr · att betala leverantörsfaktura får inte sänka
        # bolaget under noll. Frivilliga betalningar ska antingen ha
        # täckning eller skjutas upp / hanteras med tillväxtlån.
        from ..business.cash import compute_company_cash as _ccc
        total_due = int(si.amount_excl_vat) + int(si.vat_amount or 0)
        bal = _ccc(s, co)
        if bal < total_due:
            raise HTTPException(
                402,
                f"Otillräcklig kassa · {total_due - bal} kr saknas. "
                f"Kassan är {bal} kr · fakturan är {total_due} kr. "
                "Ta ett tillväxtlån (Tillväxt → Lån) först.",
            )

        si.status = "paid"
        si.paid_on = today

        # Bokför som expense (med moms)
        from ..business.models import CompanyTransaction as _Tx
        amt = Decimal(str(si.amount_excl_vat))
        vat = (amt * Decimal(str(si.vat_rate))).quantize(Decimal("0.01"))
        s.add(_Tx(
            company_id=co.id,
            occurred_on=today,
            kind="expense",
            category="leverantor",
            description=f"{si.sender_name} · {si.description}",
            amount_excl_vat=amt,
            vat_rate=Decimal(str(si.vat_rate)),
            vat_amount=vat,
        ))
        s.flush()
        return _to_supplier_out(si)


# === Tick-endpoint ===


class TickOut(BaseModel):
    week_no: int
    new_opportunities: int
    quotes_decided: int
    quotes_accepted: int
    quotes_rejected: int
    invoices_paid_now: int
    events_triggered: int
    reputation_after: int
    notes: list[str]


@router.post("/tick", response_model=TickOut)
def manual_tick(
    info: TokenInfo = Depends(require_token),
):
    """Manuell stega-vecka-knapp för eleven (bara om läraren tillåter
    solo-stega utan auto-cron). Tillgänglig i basics-läget."""
    _require_student(info)
    with session_scope() as s:
        co = _get_active_company(s)
        summary = run_business_week(s, company=co)
        s.flush()
        return TickOut(
            week_no=summary.week_no,
            new_opportunities=summary.new_opportunities,
            quotes_decided=summary.quotes_decided,
            quotes_accepted=summary.quotes_accepted,
            quotes_rejected=summary.quotes_rejected,
            invoices_paid_now=summary.invoices_paid_now,
            events_triggered=summary.events_triggered,
            reputation_after=summary.reputation_after,
            notes=summary.notes,
        )


# === Lärar-aggregat ===


class TeacherClassRow(BaseModel):
    student_id: int
    student_name: str
    has_company: bool
    company_name: Optional[str]
    company_form: Optional[str]
    reputation: Optional[int]
    week_no: Optional[int]
    revenue_4w: Optional[int]
    profit_4w: Optional[int]
    n_invoices_unpaid: Optional[int]
    n_open_opportunities: Optional[int]
    biz_mode_enabled: bool


class TeacherClassOverviewOut(BaseModel):
    teacher_id: int
    n_students: int
    n_with_active_company: int
    avg_reputation: Optional[int]
    avg_revenue_4w: Optional[int]
    rows: list[TeacherClassRow]


@teacher_router.get(
    "/class-overview", response_model=TeacherClassOverviewOut,
)
def class_overview(
    info: TokenInfo = Depends(require_token),
):
    """Klass-aggregerad bild över elevers företag.

    Spec: deb/README.md avsnitt 8 ("Klassöversikt: tabell över alla
    elever — företagsnamn, omsättning, vinst, antal kundfakturor,
    antal förfallna fakturor").
    """
    teacher_id = _require_teacher(info)
    from ..school.engines import (
        master_session, scope_context, scope_for_student,
    )
    from ..school.models import Student

    with master_session() as ms:
        students = (
            ms.query(Student)
            .filter(Student.teacher_id == teacher_id, Student.active.is_(True))
            .all()
        )
        for stu in students:
            ms.expunge(stu)

    rows: list[TeacherClassRow] = []
    n_with_company = 0
    rep_total = 0
    rep_count = 0
    revenue_total = 0
    revenue_count = 0

    for stu in students:
        biz_on = bool(getattr(stu, "business_mode_enabled", False))
        scope_key = scope_for_student(stu)

        co_data: dict = {
            "has_company": False,
            "company_name": None,
            "company_form": None,
            "reputation": None,
            "week_no": None,
            "revenue_4w": None,
            "profit_4w": None,
            "n_invoices_unpaid": None,
            "n_open_opportunities": None,
        }

        if biz_on:
            try:
                with scope_context(scope_key):
                    with session_scope() as s:
                        co = (
                            s.query(Company)
                            .filter(Company.active.is_(True))
                            .first()
                        )
                        if co is not None:
                            n_with_company += 1
                            rep_total += co.reputation
                            rep_count += 1
                            from ..business.game_clock import (
                                current_game_date_for_student,
                            )
                            today = current_game_date_for_student(stu.id)
                            cutoff = today - timedelta(weeks=4)

                            # Omsättning + vinst senaste 4 v
                            from ..business.models import (
                                CompanyTransaction as _Tx,
                            )
                            txs = (
                                s.query(_Tx)
                                .filter(
                                    _Tx.company_id == co.id,
                                    _Tx.occurred_on >= cutoff,
                                )
                                .all()
                            )
                            inc = sum(
                                int(t.amount_excl_vat) for t in txs
                                if t.kind == "income"
                            )
                            exp = sum(
                                int(t.amount_excl_vat) for t in txs
                                if t.kind in ("expense", "salary")
                            )
                            revenue_total += inc
                            revenue_count += 1

                            n_unpaid = (
                                s.query(CompanyInvoice)
                                .filter(
                                    CompanyInvoice.company_id == co.id,
                                    CompanyInvoice.status == "sent",
                                    CompanyInvoice.paid_on.is_(None),
                                )
                                .count()
                            )
                            n_open_opps = (
                                s.query(JobOpportunity)
                                .filter(
                                    JobOpportunity.company_id == co.id,
                                    JobOpportunity.status == "open",
                                )
                                .count()
                            )

                            co_data.update({
                                "has_company": True,
                                "company_name": co.name,
                                "company_form": co.form,
                                "reputation": co.reputation,
                                "week_no": co.week_no,
                                "revenue_4w": inc,
                                "profit_4w": inc - exp,
                                "n_invoices_unpaid": n_unpaid,
                                "n_open_opportunities": n_open_opps,
                            })
            except Exception:
                # Scope-DB inte initierad än; eleven har inte loggat in
                pass

        rows.append(TeacherClassRow(
            student_id=stu.id,
            student_name=stu.display_name,
            biz_mode_enabled=biz_on,
            **co_data,
        ))

    return TeacherClassOverviewOut(
        teacher_id=teacher_id,
        n_students=len(students),
        n_with_active_company=n_with_company,
        avg_reputation=(
            int(round(rep_total / rep_count)) if rep_count else None
        ),
        avg_revenue_4w=(
            int(round(revenue_total / revenue_count))
            if revenue_count else None
        ),
        rows=rows,
    )


# === Lärar-mass-skick av leverantörsfaktura ===


class TeacherSupplierInvoiceIn(BaseModel):
    target_student_ids: list[int] = Field(min_length=1)
    sender_name: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=2, max_length=240)
    amount_excl_vat: int = Field(ge=1)
    vat_rate: float = 0.25
    due_in_days: int = Field(ge=1, le=180, default=30)
    notes: Optional[str] = None


class TeacherSupplierInvoiceOut(BaseModel):
    n_created: int
    n_skipped_no_company: int
    n_skipped_not_my_student: int


@teacher_router.post(
    "/supplier-invoices", response_model=TeacherSupplierInvoiceOut,
)
def teacher_send_supplier_invoice(
    body: TeacherSupplierInvoiceIn,
    info: TokenInfo = Depends(require_token),
):
    """Lärare mass-skickar leverantörsfaktura till valda elever.

    Spec: deb/README.md avsnitt 8 ('Skicka leverantörsfaktura').
    """
    teacher_id = _require_teacher(info)
    from ..school.engines import (
        master_session, scope_context, scope_for_student,
    )
    from ..school.models import Student
    from ..business.game_clock import current_game_date_for_student

    n_created = 0
    n_skipped_no_co = 0
    n_skipped_not_mine = 0

    with master_session() as ms:
        for sid in body.target_student_ids:
            stu = ms.get(Student, sid)
            if stu is None or stu.teacher_id != teacher_id:
                n_skipped_not_mine += 1
                continue
            scope_key = scope_for_student(stu)

            try:
                with scope_context(scope_key):
                    with session_scope() as s:
                        co = (
                            s.query(Company)
                            .filter(Company.active.is_(True))
                            .first()
                        )
                        if co is None:
                            n_skipped_no_co += 1
                            continue

                        today = current_game_date_for_student(sid)
                        si = SupplierInvoice(
                            company_id=co.id,
                            sender_name=body.sender_name,
                            invoice_number=(
                                f"L-{teacher_id}-{today.isoformat()}"
                                f"-{sid}"
                            ),
                            issued_on=today,
                            due_on=today + timedelta(days=body.due_in_days),
                            description=body.description,
                            amount_excl_vat=body.amount_excl_vat,
                            vat_rate=Decimal(str(body.vat_rate)),
                            source="teacher",
                            teacher_id=teacher_id,
                            status="open",
                            notes=body.notes,
                        )
                        s.add(si)
                        s.flush()
                        n_created += 1
            except Exception:
                n_skipped_no_co += 1

    return TeacherSupplierInvoiceOut(
        n_created=n_created,
        n_skipped_no_company=n_skipped_no_co,
        n_skipped_not_my_student=n_skipped_not_mine,
    )


# === Lärar-kundfaktura-granskning ===


class TeacherInvoiceReviewIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: Optional[str] = None


class TeacherInvoiceReviewOut(BaseModel):
    invoice_id: int
    new_status: str
    teacher_comment: Optional[str]


@teacher_router.patch(
    "/invoices/{student_id}/{invoice_id}/review",
    response_model=TeacherInvoiceReviewOut,
)
def teacher_review_invoice(
    student_id: int, invoice_id: int,
    body: TeacherInvoiceReviewIn,
    info: TokenInfo = Depends(require_token),
):
    """Lärare granskar elevens kundfaktura. Avslag → tvingar elev korrigera.

    Spec: deb/README.md avsnitt 8 ('Granska kundfakturor').
    """
    teacher_id = _require_teacher(info)
    from ..school.engines import (
        master_session, scope_context, scope_for_student,
    )
    from ..school.models import Student

    with master_session() as ms:
        stu = ms.get(Student, student_id)
        if stu is None or stu.teacher_id != teacher_id:
            raise HTTPException(404, "Elev saknas")
        scope_key = scope_for_student(stu)

    with scope_context(scope_key):
        with session_scope() as s:
            inv = s.get(CompanyInvoice, invoice_id)
            if inv is None:
                raise HTTPException(404, "Faktura saknas")

            new_status = (
                "sent" if body.decision == "approved" else "draft"
            )
            inv.status = new_status

            # Lägg lärar-kommentar i description-fältet (separat tabell skulle
            # vara renare, men vi prioriterar enkelhet i fas 1)
            if body.comment:
                appended = f"\n[Lärare]: {body.comment}"
                if inv.description and len(inv.description) + len(appended) <= 240:
                    inv.description = inv.description + appended

            s.flush()
            return TeacherInvoiceReviewOut(
                invoice_id=inv.id,
                new_status=inv.status,
                teacher_comment=body.comment,
            )


# === Helper · resolve teacher_id för en elev (för AI-token-räkning) ===


def _resolve_teacher_id_for_student(student_id: int | None) -> int | None:
    if student_id is None:
        return None
    try:
        from ..school.engines import master_session
        from ..school.models import Student
        with master_session() as ms:
            stu = ms.get(Student, student_id)
            return stu.teacher_id if stu else None
    except Exception:
        return None
