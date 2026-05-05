"""Arbetsförmedlingen-API · /v2/arbetsformedlingen/*

Spec: dev/game-motor/05-arbetsformedlingen.md (Endpoints)

Elev-endpoints:
  GET  /v2/arbetsformedlingen/jobs?ym=YYYY-MM
  POST /v2/arbetsformedlingen/apply
  GET  /v2/arbetsformedlingen/applications
  POST /v2/arbetsformedlingen/applications/{id}/round
  POST /v2/arbetsformedlingen/applications/{id}/accept
  POST /v2/arbetsformedlingen/applications/{id}/decline
  POST /v2/arbetsformedlingen/applications/{id}/abandon

Lärar-endpoints:
  GET  /v2/teacher/arbetsformedlingen/applications/{student_id}
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date as _date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..db.base import session_scope
from ..db.models import JobApplication
from ..game_engine.arbetsformedlingen import (
    JobOpening,
    MATS_OPENING_MESSAGE,
    abandon_application,
    accept_offer,
    apply_to_job,
    available_jobs_for_student,
    decline_offer,
    submit_round_response,
)
from ..game_engine.profile_generator.schema import (
    FamilyChoice,
    GeneratedProfile,
    HousingChoice,
    PentagonInit,
)
from ..game_engine.pools.stadspool import STAD_BY_KEY
from ..school.engines import master_session
from ..school.models import StudentProfile
from .deps import TokenInfo, require_token

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/arbetsformedlingen", tags=["arbetsformedlingen"])
teacher_router = APIRouter(
    prefix="/v2/teacher/arbetsformedlingen", tags=["teacher-arbetsformedlingen"],
)


# === Schemas ===

class JobOpeningOut(BaseModel):
    listing_id: str
    yrke_key: str
    yrke_display: str
    yrke_ssyk: str
    employer_name: str
    city_key: str
    city_display: str
    monthly_gross_min: int
    monthly_gross_median: int
    monthly_gross_max: int
    education_level: str
    match_score: int
    description: str
    # Sprint 7 · utökad annons-data
    company_blurb: str = ""
    job_description: list[str] = []
    requirements: list[str] = []
    meriter: list[str] = []
    benefits: list[str] = []
    employment_type: str = ""
    application_deadline: str = ""
    work_hours: str = ""
    start_date: str = ""


class JobsResponse(BaseModel):
    mats_message: str
    year_month: str
    jobs: list[JobOpeningOut]


class ApplyIn(BaseModel):
    listing_id: str
    yrke_key: str
    yrke_display: str
    yrke_ssyk: str
    employer_name: str
    city_key: str
    city_display: str
    monthly_gross_min: int
    monthly_gross_median: int
    monthly_gross_max: int
    education_level: str
    match_score: int
    description: str = ""
    # Sprint 7 · annonsdata bevaras vid apply så sparkad i job_ad_data
    company_blurb: str = ""
    job_description: list[str] = []
    requirements: list[str] = []
    meriter: list[str] = []
    benefits: list[str] = []
    employment_type: str = ""
    application_deadline: str = ""
    work_hours: str = ""
    start_date: str = ""


class JobApplicationOut(BaseModel):
    id: int
    yrke_key: str
    yrke_display: str
    employer_name: str
    city_key: str
    city_display: str
    status: str
    current_round: int
    match_score: int
    monthly_gross_offered: Optional[int]
    final_score: Optional[int]
    feedback_md: Optional[str]
    rounds_data: Optional[dict]
    started_on: str
    completed_on: Optional[str]
    # Sprint 7 · läses av lärar-vyn så hen kan se elevens texter
    cover_letter_text: Optional[str] = None
    case_answer_text: Optional[str] = None
    ai_feedback_md: Optional[str] = None
    job_ad_data: Optional[dict] = None


class RoundIn(BaseModel):
    payload: dict = Field(default_factory=dict)


class RoundOut(BaseModel):
    round_n: int
    score_delta: int
    feedback_md: str
    pentagon_delta: dict[str, int]
    advanced_to: int
    final_status: Optional[str]
    application: JobApplicationOut


# === Helpers ===


def _require_student(info: TokenInfo) -> int:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast elever kan använda Arbetsförmedlingen.",
        )
    return info.student_id


def _city_key_from_display(display: Optional[str]) -> Optional[str]:
    if not display:
        return None
    norm = display.strip().lower()
    for key, stad in STAD_BY_KEY.items():
        if stad.display.lower() == norm:
            return key
        if key == norm:
            return key
    return None


def _profile_from_studentprofile(sp: StudentProfile) -> GeneratedProfile:
    """Bygg minimal GeneratedProfile från lagrad StudentProfile."""
    city_key = _city_key_from_display(sp.city) or "medelstad"
    city = STAD_BY_KEY.get(city_key) or STAD_BY_KEY["medelstad"]
    return GeneratedProfile(
        seed=sp.student_id or 0,
        name="Eleven",
        yrke_key=getattr(sp, "profession_key", "okand") or "okand",
        yrke_display=sp.profession or "Okänd",
        yrke_ssyk="0000",
        monthly_gross=sp.gross_salary_monthly,
        monthly_net=sp.net_salary_monthly,
        city_key=city_key,
        city_display=city.display,
        region=city.region,
        housing=HousingChoice(
            type=sp.housing_type if sp.housing_type in (
                "hyresratt", "bostadsratt", "villa", "radhus",
            ) else "hyresratt",
            size_kvm=max(22, sp.housing_monthly // 100),
            monthly_cost=sp.housing_monthly,
        ),
        family=FamilyChoice(status=sp.family_status, partner_model="solo"),
        household_gross_monthly=sp.gross_salary_monthly,
        household_net_monthly=sp.net_salary_monthly,
        pentagon=PentagonInit(
            economy=60, safety=60, health=60, social=60, leisure=60,
        ),
        facts={
            "age": sp.age,
            "competency_match_with_yrke": True,
        },
    )


def _to_app_out(app: JobApplication) -> JobApplicationOut:
    return JobApplicationOut(
        id=app.id,
        yrke_key=app.yrke_key,
        yrke_display=app.yrke_display,
        employer_name=app.employer_name,
        city_key=app.city_key,
        city_display=app.city_display,
        status=app.status,
        current_round=app.current_round,
        match_score=app.match_score,
        monthly_gross_offered=app.monthly_gross_offered,
        final_score=app.final_score,
        feedback_md=app.feedback_md,
        rounds_data=app.rounds_data,
        started_on=app.started_on.isoformat() if app.started_on else "",
        completed_on=app.completed_on.isoformat() if app.completed_on else None,
        cover_letter_text=getattr(app, "cover_letter_text", None),
        case_answer_text=getattr(app, "case_answer_text", None),
        ai_feedback_md=getattr(app, "ai_feedback_md", None),
        job_ad_data=getattr(app, "job_ad_data", None),
    )


# === Elev-endpoints ===


@router.get("/jobs", response_model=JobsResponse)
def list_jobs(
    ym: str = "2026-01",
    n: int = 6,
    info: TokenInfo = Depends(require_token),
):
    """Lista relevanta jobb för eleven (sorterade på match_score)."""
    sid = _require_student(info)
    with master_session() as s:
        sp = (
            s.query(StudentProfile)
            .filter(StudentProfile.student_id == sid)
            .first()
        )
        if sp is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Elevens profil saknas.",
            )
    profile = _profile_from_studentprofile(sp)

    # Difficulty-progression · 3+ avslag på 30 dagar → -10p match-score
    # på alla jobb (verkligheten · arbetsgivare ser aktivitet men
    # något skickar varningssignaler).
    from datetime import date as _d_diff, timedelta as _td_diff
    cutoff = _d_diff.today() - _td_diff(days=30)
    with session_scope() as scope_s:
        recent_rejections = (
            scope_s.query(JobApplication)
            .filter(
                JobApplication.status.in_(("rejected", "abandoned")),
                JobApplication.completed_on.isnot(None),
                JobApplication.completed_on >= cutoff,
            )
            .count()
        )
    difficulty_modifier = -10 if recent_rejections >= 3 else 0

    jobs = available_jobs_for_student(
        profile, ym, n=max(1, min(n, 12)),
        difficulty_modifier=difficulty_modifier,
    )
    mats_msg = MATS_OPENING_MESSAGE
    if difficulty_modifier < 0:
        mats_msg += (
            f"\n\n⚠ Du har {recent_rejections} avslag/avbrott senaste "
            "30 dagarna — det syns i din profil. Match-score är något "
            "nedjusterad. Lägg mer tid per ansökan."
        )
    return JobsResponse(
        mats_message=mats_msg,
        year_month=ym,
        jobs=[JobOpeningOut(**asdict(j)) for j in jobs],
    )


@router.post("/apply", response_model=JobApplicationOut)
def apply(
    body: ApplyIn,
    info: TokenInfo = Depends(require_token),
):
    """Starta en ansökan från en JobOpening (skicka hela JobOpening-payload)."""
    sid = _require_student(info)
    opening = JobOpening(**body.model_dump())
    with session_scope() as s:
        # Kontrollera att eleven inte har för många pågående ansökningar
        active = (
            s.query(JobApplication)
            .filter(
                JobApplication.status.in_((
                    "round_1", "round_2", "round_3", "round_4",
                    "round_5", "offer_pending",
                ))
            )
            .count()
        )
        if active >= 2:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Du har redan 2 pågående ansökningar. Avsluta en innan du söker fler.",
            )
        app = apply_to_job(
            s, student_id=sid, opening=opening, today=_date.today(),
        )
        # Lärar-spårning
        try:
            from ..school.activity import log_activity
            log_activity(
                kind="job.applied",
                summary=f"Sökte jobb: {opening.yrke_display} hos {opening.employer_name}",
                payload={
                    "application_id": app.id,
                    "yrke_key": opening.yrke_key,
                    "employer": opening.employer_name,
                    "match_score": opening.match_score,
                    "monthly_gross_median": opening.monthly_gross_median,
                },
            )
        except Exception:
            pass
        return _to_app_out(app)


@router.get("/applications", response_model=list[JobApplicationOut])
def list_applications(info: TokenInfo = Depends(require_token)):
    sid = _require_student(info)
    with session_scope() as s:
        rows = (
            s.query(JobApplication)
            .order_by(JobApplication.started_on.desc())
            .all()
        )
        return [_to_app_out(a) for a in rows]


@router.post("/applications/{app_id}/round", response_model=RoundOut)
def submit_round(
    app_id: int,
    body: RoundIn,
    info: TokenInfo = Depends(require_token),
):
    sid = _require_student(info)
    with session_scope() as s:
        try:
            result = submit_round_response(
                s, student_id=sid, application_id=app_id,
                payload=body.payload,
            )
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
        s.flush()
        app = s.get(JobApplication, app_id)
        if app is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ansökan saknas.")
        return RoundOut(
            round_n=result.round_n,
            score_delta=result.score_delta,
            feedback_md=result.feedback_md,
            pentagon_delta=result.pentagon_delta,
            advanced_to=result.advanced_to,
            final_status=result.final_status,
            application=_to_app_out(app),
        )


@router.post("/applications/{app_id}/accept", response_model=JobApplicationOut)
def accept(
    app_id: int,
    info: TokenInfo = Depends(require_token),
):
    sid = _require_student(info)
    with session_scope() as s:
        try:
            app = accept_offer(s, student_id=sid, application_id=app_id)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
        try:
            from ..school.activity import log_activity
            log_activity(
                kind="job.accepted",
                summary=f"Tog jobbet: {app.yrke_display} hos {app.employer_name}",
                payload={
                    "application_id": app.id,
                    "yrke_key": app.yrke_key,
                    "employer": app.employer_name,
                    "monthly_gross_offered": app.monthly_gross_offered,
                    "final_score": app.final_score,
                },
            )
        except Exception:
            pass
        return _to_app_out(app)


@router.post("/applications/{app_id}/decline", response_model=JobApplicationOut)
def decline(
    app_id: int,
    info: TokenInfo = Depends(require_token),
):
    sid = _require_student(info)
    with session_scope() as s:
        try:
            app = decline_offer(s, student_id=sid, application_id=app_id)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
        try:
            from ..school.activity import log_activity
            log_activity(
                kind="job.declined",
                summary=f"Tackade nej till {app.yrke_display} hos {app.employer_name}",
                payload={
                    "application_id": app.id,
                    "yrke_key": app.yrke_key,
                    "final_score": app.final_score,
                },
            )
        except Exception:
            pass
        return _to_app_out(app)


@router.post("/applications/{app_id}/abandon", response_model=JobApplicationOut)
def abandon(
    app_id: int,
    info: TokenInfo = Depends(require_token),
):
    sid = _require_student(info)
    with session_scope() as s:
        try:
            app = abandon_application(s, student_id=sid, application_id=app_id)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
        try:
            from ..school.activity import log_activity
            log_activity(
                kind="job.abandoned",
                summary=f"Avbröt ansökan till {app.yrke_display}",
                payload={"application_id": app.id, "yrke_key": app.yrke_key},
            )
        except Exception:
            pass
        return _to_app_out(app)


# === Cover-letter-preview · AI-feedback INNAN submit ===

class CoverLetterPreviewIn(BaseModel):
    text: str
    yrke_display: str
    employer_name: str
    job_description: Optional[str] = None
    requirements: list[str] = []


class CoverLetterPreviewOut(BaseModel):
    score: int
    feedback_md: str
    highlights: list[str] = []


@router.post("/cover-letter-preview", response_model=CoverLetterPreviewOut)
def cover_letter_preview(
    body: CoverLetterPreviewIn,
    info: TokenInfo = Depends(require_token),
):
    """Eleven får AI-feedback på personliga brevet INNAN hen submittar
    rond 1. Hjälper hen iterera utan att förbruka rond-tillfället.
    """
    sid = _require_student(info)
    text = (body.text or "").strip()
    if len(text.split()) < 30:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Skriv minst 30 ord innan du ber om feedback.",
        )
    from ..school.ai import evaluate_cover_letter
    from ..school.engines import master_session
    from ..school.models import Student as _Stu_p
    with master_session() as ms:
        stu = ms.get(_Stu_p, sid)
        teacher_id = stu.teacher_id if stu else None
    try:
        res = evaluate_cover_letter(
            cover_letter_text=text,
            job_title=body.yrke_display,
            employer=body.employer_name,
            job_description=body.job_description or body.yrke_display,
            requirements=body.requirements,
            teacher_id=teacher_id,
        )
        if res is None:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "AI-tjänsten gick inte att nå.",
            )
        return CoverLetterPreviewOut(
            score=int(res.data.get("score", 12)),
            feedback_md=res.data.get("feedback_md", ""),
            highlights=res.data.get("highlights", []) or [],
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "AI-bedömning misslyckades.",
        )


# === Lärar-endpoint ===


@teacher_router.get(
    "/applications/{student_id}", response_model=list[JobApplicationOut],
)
def teacher_list_applications(
    student_id: int,
    info: TokenInfo = Depends(require_token),
):
    if info.role != "teacher" or info.teacher_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast lärare.")
    from ..school.engines import scope_for_student, scope_context, get_scope_session
    from ..school.models import Student

    with master_session() as s:
        stu = s.get(Student, student_id)
        if stu is None or stu.teacher_id != info.teacher_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Elev saknas.")
        s.expunge(stu)
    scope_key = scope_for_student(stu)
    maker = get_scope_session(scope_key)
    with scope_context(scope_key):
        with maker() as s:
            rows = (
                s.query(JobApplication)
                .order_by(JobApplication.started_on.desc())
                .all()
            )
            return [_to_app_out(a) for a in rows]


# === Lärar-overview · sammanställning över elevens AF-aktivitet ===


class TeacherAFOverviewOut(BaseModel):
    student_id: int
    student_name: str
    n_applications_total: int
    n_active: int  # status in (applied, in_review, offered)
    n_completed: int  # status == accepted
    n_declined: int  # status == declined
    n_abandoned: int  # status == abandoned
    avg_match_score: Optional[float]
    avg_final_score: Optional[float]
    last_application_date: Optional[str]
    summary_md: str


@teacher_router.get(
    "/overview/{student_id}", response_model=TeacherAFOverviewOut,
)
def teacher_af_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> TeacherAFOverviewOut:
    """Sammanställning av elevens AF-aktivitet.

    Räknar ansökningar per status, snitt match/final-score och senaste
    ansökningsdatum. Genererar en kort sammanfattning för läraren med
    pedagogisk indikator (är eleven aktiv? lyckas hen i intervjuerna?).
    """
    if info.role != "teacher" or info.teacher_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast lärare.")
    from ..school.engines import scope_for_student, scope_context, get_scope_session
    from ..school.models import Student

    with master_session() as s:
        stu = s.get(Student, student_id)
        if stu is None or stu.teacher_id != info.teacher_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Elev saknas.")
        student_name = stu.display_name
        s.expunge(stu)

    scope_key = scope_for_student(stu)
    maker = get_scope_session(scope_key)
    with scope_context(scope_key):
        with maker() as s:
            rows = (
                s.query(JobApplication)
                .order_by(JobApplication.started_on.desc())
                .all()
            )
            n_total = len(rows)
            n_active = sum(
                1 for r in rows if r.status in ("applied", "in_review", "offered")
            )
            n_completed = sum(1 for r in rows if r.status == "accepted")
            n_declined = sum(1 for r in rows if r.status == "declined")
            n_abandoned = sum(1 for r in rows if r.status == "abandoned")
            scores = [r.match_score for r in rows if r.match_score is not None]
            avg_match = sum(scores) / len(scores) if scores else None
            finals = [r.final_score for r in rows if r.final_score is not None]
            avg_final = sum(finals) / len(finals) if finals else None
            last_date = (
                rows[0].started_on.isoformat() if rows else None
            )

    if n_total == 0:
        summary = (
            f"## {student_name} har inte sökt något jobb än\n\n"
            "Eleven har inte interagerat med Arbetsförmedlingen. "
            "Tipsa eleven om att Mats listar lediga tjänster i kollet "
            "varje månad."
        )
    else:
        accept_rate_str = (
            f"{(n_completed / n_total * 100):.0f}%"
            if n_total > 0 else "—"
        )
        summary = (
            f"## {student_name} på Arbetsförmedlingen\n\n"
            f"- Totalt antal ansökningar: **{n_total}**\n"
            f"- Aktiva (pågående): {n_active}\n"
            f"- Accepterade: {n_completed} ({accept_rate_str})\n"
            f"- Avböjda av AG: {n_declined}\n"
            f"- Avbrutna av elev: {n_abandoned}\n"
            + (
                f"- Snitt match-score: {avg_match:.0f}/100\n"
                if avg_match is not None else ""
            )
            + (
                f"- Snitt final-score (intervju): {avg_final:.0f}/100\n"
                if avg_final is not None else ""
            )
            + (
                f"- Senaste ansökan: {last_date}\n"
                if last_date else ""
            )
        )

    return TeacherAFOverviewOut(
        student_id=student_id,
        student_name=student_name,
        n_applications_total=n_total,
        n_active=n_active,
        n_completed=n_completed,
        n_declined=n_declined,
        n_abandoned=n_abandoned,
        avg_match_score=avg_match,
        avg_final_score=avg_final,
        last_application_date=last_date,
        summary_md=summary,
    )
