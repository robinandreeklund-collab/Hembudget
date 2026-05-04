"""Lärar-API för spelmotorn.

Spec: dev/game-motor/

Endpoints:
- GET    /v2/teacher/calendars                 — lista lärarens klasskalendrar
- POST   /v2/teacher/calendars                 — skapa eller uppdatera kalender
- POST   /v2/teacher/calendars/{id}/pause      — pausa till given datetime
- POST   /v2/teacher/calendars/{id}/resume     — ta bort paus
- DELETE /v2/teacher/calendars/{id}            — radera kalender

- POST   /v2/teacher/students/profile-preview  — förhandsvisa Profile Generator
                                                  (skapar ingen elev)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import random as _random

from ..game_engine.monte_carlo import SimConfig, run_simulations, summarize

from ..db.models import InsurancePolicy
from ..game_engine.event_engine import (
    EVENT_BY_KEY,
    apply_event,
    list_active_templates,
)
from ..game_engine.monthly_engine import tick_month
from ..game_engine.pentagon import pentagon_history_for_student
from ..game_engine.profile_generator import (
    GeneratedProfile,
    generate_profile,
)
from ..school.engines import (
    get_scope_session,
    master_session,
    scope_context,
    scope_for_student,
)
from ..school.game_engine_models import (
    ClassCalendar,
    SchoolClass,
    WeekTickRun,
    WellbeingEvent,
    compute_current_sim_year_month,
    shift_year_month,
)
from ..school.models import Student
from .deps import TokenInfo, require_teacher

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/teacher", tags=["game-engine"])


# === Schemas ===


class ClassCalendarOut(BaseModel):
    id: int
    teacher_id: int
    class_label: Optional[str]
    sim_start_year_month: str
    weeks_per_sim_month: int
    paused_until: Optional[datetime]
    last_tick_year_month: str
    last_tick_at: Optional[datetime]
    real_start_date: datetime
    current_sim_year_month: str = Field(
        description=(
            "Beräknad just-nu-spelmånad baserat på real_start_date + tempo. "
            "Cron tickar tills `last_tick_year_month == current_sim_year_month`."
        ),
    )
    is_paused: bool


class ClassCalendarUpsertIn(BaseModel):
    class_label: Optional[str] = Field(
        default=None, max_length=60,
        description="Klass-etikett (t.ex. '8A'). NULL = lärarens default-kalender.",
    )
    sim_start_year_month: str = Field(
        description="Spelets startmånad, format 'YYYY-MM'.",
        pattern=r"^\d{4}-\d{2}$",
    )
    weeks_per_sim_month: int = Field(
        default=1, ge=1, le=4,
        description="1=snabb (default), 2=normal, 4=långsam.",
    )


class PauseIn(BaseModel):
    paused_until: datetime = Field(
        description="Klassens tid pausas tills denna tidpunkt.",
    )


class AdvanceMonthIn(BaseModel):
    """Tick:a en spelmånad för en elev.

    `seed` styr Profile Generator (samma seed = samma karaktär över
    tid). `year_month` är "YYYY-MM" och måste vara nästa otickade
    månad för att inte hoppa över hål. `spend_profile` + `starting_level`
    matchar elevens lärar-inställning.
    """
    year_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    seed: int = Field(description="Slumpfröet för Profile Generator.")
    archetype: str = "random"
    starting_level: int = Field(default=1, ge=1, le=3)
    spend_profile: str = Field(default="balanserad")
    partner_model: str = Field(default="solo")


class TickResponse(BaseModel):
    student_id: int
    year_month: str
    skipped: bool
    summary: dict


class WeekTickRunOut(BaseModel):
    id: int
    student_id: int
    year_month: str
    status: str
    seed_used: Optional[int]
    started_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]


class ProfilePreviewIn(BaseModel):
    seed: Optional[int] = Field(
        default=None,
        description="Slumpfrö (seedas annars deterministiskt på timestamp).",
    )
    archetype: str = Field(
        default="random",
        description="'random' eller en specifik arketyp-key från yrkespoolen.",
    )
    starting_level: int = Field(default=1, ge=1, le=3)
    name: str = Field(default="Förhandsvisning", min_length=1, max_length=80)
    partner_model: str = Field(
        default="solo",
        description="'solo' / 'ai' / 'klasskompis' / 'auto'.",
    )


# === Helpers ===


def _to_out(c: ClassCalendar) -> ClassCalendarOut:
    now = datetime.utcnow()
    current = compute_current_sim_year_month(
        c.sim_start_year_month,
        c.real_start_date or now,
        now,
        c.weeks_per_sim_month,
    )
    is_paused = bool(c.paused_until and c.paused_until > now)
    return ClassCalendarOut(
        id=c.id,
        teacher_id=c.teacher_id,
        class_label=c.class_label,
        sim_start_year_month=c.sim_start_year_month,
        weeks_per_sim_month=c.weeks_per_sim_month,
        paused_until=c.paused_until,
        last_tick_year_month=c.last_tick_year_month,
        last_tick_at=c.last_tick_at,
        real_start_date=c.real_start_date,
        current_sim_year_month=current,
        is_paused=is_paused,
    )


# === Endpoints: ClassCalendar ===


@router.get("/calendars", response_model=list[ClassCalendarOut])
def list_calendars(info: TokenInfo = Depends(require_teacher)):
    """Returnerar alla klasskalendrar för inloggad lärare."""
    with master_session() as s:
        rows = (
            s.query(ClassCalendar)
            .filter(ClassCalendar.teacher_id == info.teacher_id)
            .order_by(ClassCalendar.created_at.desc())
            .all()
        )
        return [_to_out(c) for c in rows]


@router.post(
    "/calendars",
    response_model=ClassCalendarOut,
    status_code=status.HTTP_200_OK,
)
def upsert_calendar(
    body: ClassCalendarUpsertIn,
    info: TokenInfo = Depends(require_teacher),
):
    """Skapar eller uppdaterar en klasskalender (per teacher_id + class_label).

    Idempotent: samma `class_label` uppdaterar befintlig istället för att
    skapa duplikat. `last_tick_year_month` initieras till sim_start - 1
    så att första cron-ticken landar på sim_start.
    """
    with master_session() as s:
        existing = (
            s.query(ClassCalendar)
            .filter(
                ClassCalendar.teacher_id == info.teacher_id,
                ClassCalendar.class_label == body.class_label,
            )
            .one_or_none()
        )
        if existing is None:
            cal = ClassCalendar(
                teacher_id=info.teacher_id,
                class_label=body.class_label,
                sim_start_year_month=body.sim_start_year_month,
                weeks_per_sim_month=body.weeks_per_sim_month,
                # Backa ett steg så att första tick landar på sim_start
                last_tick_year_month=shift_year_month(
                    body.sim_start_year_month, -1,
                ),
            )
            s.add(cal)
            s.flush()
        else:
            existing.sim_start_year_month = body.sim_start_year_month
            existing.weeks_per_sim_month = body.weeks_per_sim_month
            cal = existing
        s.commit()
        s.refresh(cal)
        return _to_out(cal)


@router.post("/calendars/{cal_id}/pause", response_model=ClassCalendarOut)
def pause_calendar(
    cal_id: int,
    body: PauseIn,
    info: TokenInfo = Depends(require_teacher),
):
    with master_session() as s:
        cal = s.get(ClassCalendar, cal_id)
        if cal is None or cal.teacher_id != info.teacher_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Kalender saknas.")
        cal.paused_until = body.paused_until
        s.commit()
        s.refresh(cal)
        return _to_out(cal)


@router.post("/calendars/{cal_id}/resume", response_model=ClassCalendarOut)
def resume_calendar(
    cal_id: int,
    info: TokenInfo = Depends(require_teacher),
):
    with master_session() as s:
        cal = s.get(ClassCalendar, cal_id)
        if cal is None or cal.teacher_id != info.teacher_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Kalender saknas.")
        cal.paused_until = None
        s.commit()
        s.refresh(cal)
        return _to_out(cal)


@router.delete("/calendars/{cal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_calendar(
    cal_id: int,
    info: TokenInfo = Depends(require_teacher),
):
    with master_session() as s:
        cal = s.get(ClassCalendar, cal_id)
        if cal is None or cal.teacher_id != info.teacher_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Kalender saknas.")
        s.delete(cal)
        s.commit()
    return None


# === Endpoints: Profile Generator preview ===


@router.post(
    "/students/profile-preview",
    response_model=GeneratedProfile,
)
def profile_preview(
    body: ProfilePreviewIn,
    info: TokenInfo = Depends(require_teacher),
):
    """Förhandsvisar en Profile Generator-output utan att skapa en elev.

    Lärare kan reroll:a innan hen trycker "Skapa". Samma `seed` ger samma
    profil — perfekt för komparativ studie ("alla får IT-konsult, jämför
    val över tid").
    """
    return generate_profile(
        seed=body.seed,
        archetype=body.archetype,
        starting_level=body.starting_level,
        name=body.name,
        partner_model=body.partner_model,
    )


# === Endpoints: Monthly Engine ===


def _load_student_or_404(s, teacher_id: int, student_id: int) -> Student:
    student = s.get(Student, student_id)
    if student is None or student.teacher_id != teacher_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Elev saknas.")
    return student


@router.post(
    "/students/{student_id}/advance-month",
    response_model=TickResponse,
)
def advance_student_month(
    student_id: int,
    body: AdvanceMonthIn,
    info: TokenInfo = Depends(require_teacher),
):
    """Tick:a en spelmånad för en specifik elev.

    Idempotent: två anrop med samma `year_month` returnerar `skipped=True`
    den andra gången. Reroll = först radera WeekTickRun + scope-data
    (görs separat via /v2/teacher/students/{id}/rewind i Sprint 4).
    """
    with master_session() as s:
        student = _load_student_or_404(s, info.teacher_id, student_id)
        # Vi behöver bara plain attribut innan session stängs
        student_id_local = student.id
        student_obj = student
        # Detacha så vi kan använda objektet utanför sessionen
        s.expunge(student)

    profile = generate_profile(
        seed=body.seed,
        archetype=body.archetype,
        starting_level=body.starting_level,
        name=student_obj.display_name or "Elev",
        partner_model=body.partner_model,
    )

    result = tick_month(
        student_obj,
        profile,
        body.year_month,
        spend_profile=body.spend_profile,
        starting_level=body.starting_level,
    )

    return TickResponse(
        student_id=student_id_local,
        year_month=result.year_month,
        skipped=result.skipped,
        summary=result.summary,
    )


class EventTemplateOut(BaseModel):
    """Hur en EventTemplate exponeras via API:n."""
    key: str
    display: str
    description: str
    kind: str
    frequency_per_year: float
    age_range: tuple[int, int]
    family_status_filter: list[str]
    cost_range: tuple[int, int]
    pentagon_unmitigated: dict
    pentagon_mitigated: Optional[dict]
    mitigations: list[dict]
    actor_route: Optional[str]
    echo_trigger: Optional[str]


class InjectEventIn(BaseModel):
    """Lärar-injektion av ett specifikt event i en spelmånad."""
    template_key: str = Field(description="EVENT_BY_KEY-key.")
    year_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    seed: int = Field(description="Seed för Profile Generator.")
    archetype: str = "random"
    starting_level: int = Field(default=1, ge=1, le=3)
    partner_model: str = "solo"
    base_cost_override: Optional[int] = Field(
        default=None,
        description="Tvinga ett specifikt belopp (kr).",
    )


class InjectEventOut(BaseModel):
    student_id: int
    template_key: str
    template_display: str
    occurred_on: str
    base_cost: int
    effective_cost: int
    mitigation_used: bool
    mitigation_label: Optional[str]
    mail_id: int
    claim_id: Optional[int]


@router.get(
    "/students/{student_id}/tick-history",
    response_model=list[WeekTickRunOut],
)
def list_tick_history(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
):
    """Lista alla tick-runs för en elev (för historik + felsökning)."""
    with master_session() as s:
        _load_student_or_404(s, info.teacher_id, student_id)
        rows = (
            s.query(WeekTickRun)
            .filter(WeekTickRun.student_id == student_id)
            .order_by(WeekTickRun.year_month.desc())
            .all()
        )
        return [
            WeekTickRunOut(
                id=r.id,
                student_id=r.student_id,
                year_month=r.year_month,
                status=r.status,
                seed_used=r.seed_used,
                started_at=r.started_at,
                completed_at=r.completed_at,
                error_message=r.error_message,
            )
            for r in rows
        ]


# === Endpoints: Event Engine ===


@router.get("/event-templates", response_model=list[EventTemplateOut])
def list_event_templates(info: TokenInfo = Depends(require_teacher)):
    """Lista hela event-poolen så lärare kan välja template för injektion."""
    return [
        EventTemplateOut(
            key=t.key,
            display=t.display,
            description=t.description,
            kind=t.kind,
            frequency_per_year=t.frequency_per_year,
            age_range=t.age_range,
            family_status_filter=list(t.family_status_filter),
            cost_range=t.cost_range,
            pentagon_unmitigated=t.pentagon_unmitigated.as_dict(),
            pentagon_mitigated=(
                t.pentagon_mitigated.as_dict() if t.pentagon_mitigated else None
            ),
            mitigations=[
                {
                    "insurance_kind": m.insurance_kind,
                    "cost_multiplier": m.cost_multiplier,
                    "label": m.label,
                }
                for m in t.mitigations
            ],
            actor_route=t.actor_route,
            echo_trigger=t.echo_trigger,
        )
        for t in list_active_templates()
    ]


@router.post(
    "/students/{student_id}/inject-event",
    response_model=InjectEventOut,
)
def inject_event(
    student_id: int,
    body: InjectEventIn,
    info: TokenInfo = Depends(require_teacher),
):
    """Tvinga ett specifikt event för en elev i en specifik spelmånad.

    Idempotens: två anrop med samma (student, year_month, template) ger
    två separata MailItems — det är medvetet, läraren kan ha pedagogisk
    anledning att skicka samma event flera gånger.
    """
    template = EVENT_BY_KEY.get(body.template_key)
    if template is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Okänd template: {body.template_key}",
        )

    with master_session() as s:
        student = _load_student_or_404(s, info.teacher_id, student_id)
        student_obj = student
        s.expunge(student)

    profile = generate_profile(
        seed=body.seed,
        archetype=body.archetype,
        starting_level=body.starting_level,
        name=student_obj.display_name or "Elev",
        partner_model=body.partner_model,
    )

    scope_key = scope_for_student(student_obj)
    rng = _random.Random(
        f"{scope_key}|inject|{body.year_month}|{body.template_key}",
    )
    maker = get_scope_session(scope_key)
    with scope_context(scope_key):
        with maker() as s:
            occ = apply_event(
                s,
                template=template,
                profile=profile,
                year_month=body.year_month,
                student_scope=scope_key,
                rng=rng,
                base_cost_override=body.base_cost_override,
            )
            s.commit()

    return InjectEventOut(
        student_id=student_id,
        template_key=occ.template_key,
        template_display=occ.template_display,
        occurred_on=occ.occurred_on.isoformat(),
        base_cost=occ.mitigation.base_cost,
        effective_cost=occ.mitigation.effective_cost,
        mitigation_used=occ.mitigation.mitigation_used,
        mitigation_label=occ.mitigation.mitigation_label,
        mail_id=occ.mail_id,
        claim_id=occ.claim_id,
    )


# === Endpoints: Snabbspola (M6) + Pentagon-historik (P2) ===


class AdvanceMultipleIn(BaseModel):
    """Snabbspola flera spelmånader i sekvens för en elev."""
    start_year_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    n_months: int = Field(ge=1, le=12, description="1-12 månader åt gången")
    seed: int
    archetype: str = "random"
    starting_level: int = Field(default=1, ge=1, le=3)
    spend_profile: str = Field(default="balanserad")
    partner_model: str = "solo"


class AdvanceMultipleOut(BaseModel):
    student_id: int
    months_processed: int
    months_skipped: int
    last_year_month: str
    summaries: list[dict]


class AdvanceClassIn(BaseModel):
    """Snabbspola en hel klass en spelmånad framåt."""
    seed_strategy: Literal["per_student", "fixed"] = Field(
        default="per_student",
        description=(
            "per_student: använd hash(student_id) som seed för deterministisk "
            "men individuell profil. fixed: alla får samma seed (för "
            "komparativ studie)."
        ),
    )
    fixed_seed: Optional[int] = None
    archetype: str = "random"
    starting_level: int = Field(default=1, ge=1, le=3)
    spend_profile: str = "balanserad"
    partner_model: str = "solo"


class AdvanceClassOut(BaseModel):
    calendar_id: int
    sim_year_month_after: str
    students_advanced: int
    students_skipped: int
    students_failed: int
    failures: list[dict]


class WellbeingEventOut(BaseModel):
    id: int
    occurred_at: datetime
    axis: str
    requested_delta: int
    applied_delta: int
    new_value: int
    reason_kind: str
    explanation: Optional[str]
    year_month: Optional[str]


@router.post(
    "/students/{student_id}/advance-months",
    response_model=AdvanceMultipleOut,
)
def advance_multiple_months(
    student_id: int,
    body: AdvanceMultipleIn,
    info: TokenInfo = Depends(require_teacher),
):
    """Snabbspola flera spelmånader i sekvens. Idempotent — månader som
    redan tickats hoppas över."""
    with master_session() as s:
        student = _load_student_or_404(s, info.teacher_id, student_id)
        student_obj = student
        s.expunge(student)

    profile = generate_profile(
        seed=body.seed,
        archetype=body.archetype,
        starting_level=body.starting_level,
        name=student_obj.display_name or "Elev",
        partner_model=body.partner_model,
    )

    summaries: list[dict] = []
    processed = 0
    skipped = 0
    last_ym = body.start_year_month

    current_ym = body.start_year_month
    for _ in range(body.n_months):
        result = tick_month(
            student_obj,
            profile,
            current_ym,
            spend_profile=body.spend_profile,
            starting_level=body.starting_level,
        )
        summaries.append({
            "year_month": result.year_month,
            "skipped": result.skipped,
            "summary": result.summary,
        })
        if result.skipped:
            skipped += 1
        else:
            processed += 1
        last_ym = current_ym
        current_ym = shift_year_month(current_ym, 1)

    return AdvanceMultipleOut(
        student_id=student_id,
        months_processed=processed,
        months_skipped=skipped,
        last_year_month=last_ym,
        summaries=summaries,
    )


def _hash_seed(student_id: int, base: int = 0) -> int:
    """Stabil seed per elev så reroll inte ändrar deras karaktär."""
    return (student_id * 2654435761 + base) & 0x7FFFFFFF


@router.post(
    "/calendars/{cal_id}/advance",
    response_model=AdvanceClassOut,
)
def advance_class(
    cal_id: int,
    body: AdvanceClassIn,
    info: TokenInfo = Depends(require_teacher),
):
    """Tick:a alla elever i en klass-kalender en spelmånad framåt.

    Använder kalendrens `last_tick_year_month` + 1 som mål-månad. Efter
    ticken uppdateras `last_tick_year_month` och `last_tick_at`.
    """
    with master_session() as s:
        cal = s.get(ClassCalendar, cal_id)
        if cal is None or cal.teacher_id != info.teacher_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Kalender saknas.")
        # Pausad kalender → 400
        if cal.paused_until and cal.paused_until > datetime.utcnow():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Kalendern är pausad. Avsluta paus först.",
            )

        target_ym = shift_year_month(cal.last_tick_year_month, 1)

        # Hitta alla elever som tillhör denna kalender
        students_q = s.query(Student).filter(
            Student.teacher_id == info.teacher_id,
        )
        if cal.class_label is not None:
            students_q = students_q.filter(
                Student.class_label == cal.class_label,
            )
        students = students_q.all()

        # Detacha för att kunna använda utanför sessionen
        student_objs = []
        for stu in students:
            s.expunge(stu)
            student_objs.append(stu)

    advanced = 0
    skipped = 0
    failed = 0
    failures: list[dict] = []

    for stu in student_objs:
        try:
            seed = (
                body.fixed_seed
                if (body.seed_strategy == "fixed" and body.fixed_seed is not None)
                else _hash_seed(stu.id)
            )
            profile = generate_profile(
                seed=seed,
                archetype=body.archetype,
                starting_level=body.starting_level,
                name=stu.display_name or "Elev",
                partner_model=body.partner_model,
            )
            result = tick_month(
                stu, profile, target_ym,
                spend_profile=body.spend_profile,
                starting_level=body.starting_level,
            )
            if result.skipped:
                skipped += 1
            else:
                advanced += 1
        except Exception as exc:
            failed += 1
            failures.append({
                "student_id": stu.id,
                "display_name": stu.display_name,
                "error": str(exc),
            })

    # Uppdatera kalender efter ticken
    with master_session() as s:
        cal = s.get(ClassCalendar, cal_id)
        if cal is not None:
            cal.last_tick_year_month = target_ym
            cal.last_tick_at = datetime.utcnow()
            s.commit()

    return AdvanceClassOut(
        calendar_id=cal_id,
        sim_year_month_after=target_ym,
        students_advanced=advanced,
        students_skipped=skipped,
        students_failed=failed,
        failures=failures,
    )


@router.get(
    "/students/{student_id}/pentagon-history",
    response_model=list[WellbeingEventOut],
)
def list_pentagon_history(
    student_id: int,
    days: int = 30,
    axis: Optional[str] = None,
    info: TokenInfo = Depends(require_teacher),
):
    """Lista WellbeingEvent-rader för en elev senaste `days` dagarna.

    Visar varje pentagon-delta med requested vs applied (= tröghets-effekt
    synlig), reason_kind (drift/event/decision) och förklaring."""
    with master_session() as s:
        _load_student_or_404(s, info.teacher_id, student_id)

    rows = pentagon_history_for_student(student_id, days=days, axis=axis)
    return [
        WellbeingEventOut(
            id=r.id,
            occurred_at=r.occurred_at,
            axis=r.axis,
            requested_delta=r.requested_delta,
            applied_delta=r.applied_delta,
            new_value=r.new_value,
            reason_kind=r.reason_kind,
            explanation=r.explanation,
            year_month=r.year_month,
        )
        for r in rows
    ]


# === Fas 8 · Monte Carlo-endpoint ===


class MonteCarloIn(BaseModel):
    """Konfiguration för Monte Carlo-körning."""
    n_simulations: int = Field(default=500, ge=10, le=10000)
    n_months: int = Field(default=12, ge=1, le=36)
    starting_level: int = Field(default=1, ge=1, le=3)
    spend_profile: str = Field(default="balanserad")
    archetype: str = Field(default="random")
    partner_model: str = Field(default="auto")
    seed_base: int = Field(default=0)


@router.post("/monte-carlo", response_model=dict)
def monte_carlo(
    body: MonteCarloIn,
    info: TokenInfo = Depends(require_teacher),
):
    """Kör N Monte Carlo-simuleringar och returnera statistik.

    Verktyg för läraren att verifiera difficulty-balansen för en
    klass innan eleverna startar:
      - Nivå 1 (sparsam) bör ge ~90 % positiv balans efter 12 mån
      - Nivå 2 (balanserad) ~60-70 %
      - Nivå 3 (slösa) ~30-40 % (medvetet utmanande)

    Snabbt: ~1500 simuleringar/sekund. Begränsat till max 10k per anrop.
    """
    cfg = SimConfig(
        n_simulations=body.n_simulations,
        n_months=body.n_months,
        starting_level=body.starting_level,
        spend_profile=body.spend_profile,
        archetype=body.archetype,
        partner_model=body.partner_model,
        seed_base=body.seed_base,
    )
    res = run_simulations(cfg)
    return summarize(res)


# === Bug #1 · Lärar-klasser CRUD ===


class SchoolClassOut(BaseModel):
    id: int
    label: str
    display_name: Optional[str]
    description: Optional[str]
    is_archived: bool
    student_count: int
    created_at: datetime


class SchoolClassIn(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    display_name: Optional[str] = Field(default=None, max_length=160)
    description: Optional[str] = None


class SchoolClassPatchIn(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=60)
    display_name: Optional[str] = Field(default=None, max_length=160)
    description: Optional[str] = None
    is_archived: Optional[bool] = None


@router.get("/classes", response_model=list[SchoolClassOut])
def list_classes(info: TokenInfo = Depends(require_teacher)):
    """Lista lärarens alla klasser med elev-antal.

    Heal-pass: om läraren har EN klass och elever med class_label=NULL,
    backfill:a class_label på dem. Tidigare visade dropdown '1 elev'
    trots att läraren hade t.ex. 18 elever — eftersom de gamla elev-
    raderna saknade class_label och bara den nyaste matchade.
    """
    with master_session() as s:
        rows = (
            s.query(SchoolClass)
            .filter(SchoolClass.teacher_id == info.teacher_id)
            .filter(SchoolClass.is_archived.is_(False))
            .order_by(SchoolClass.is_archived, SchoolClass.label)
            .all()
        )

        # Heal: backfill class_label på elever utan label om läraren
        # bara har EN aktiv klass (entydigt vilken de tillhör).
        if len(rows) == 1:
            backfilled = (
                s.query(Student)
                .filter(
                    Student.teacher_id == info.teacher_id,
                    Student.active.is_(True),
                    (Student.class_label.is_(None))
                    | (Student.class_label == ""),
                )
                .update(
                    {Student.class_label: rows[0].label},
                    synchronize_session=False,
                )
            )
            if backfilled:
                s.commit()

        # Hämta alla klasser (inkl. arkiverade för räkning)
        all_rows = (
            s.query(SchoolClass)
            .filter(SchoolClass.teacher_id == info.teacher_id)
            .order_by(SchoolClass.is_archived, SchoolClass.label)
            .all()
        )
        out = []
        for r in all_rows:
            n = (
                s.query(Student)
                .filter(
                    Student.teacher_id == info.teacher_id,
                    Student.class_label == r.label,
                    Student.active.is_(True),
                )
                .count()
            )
            out.append(SchoolClassOut(
                id=r.id, label=r.label, display_name=r.display_name,
                description=r.description, is_archived=r.is_archived,
                student_count=n, created_at=r.created_at,
            ))
        return out


@router.post("/classes", response_model=SchoolClassOut)
def create_class(
    body: SchoolClassIn,
    info: TokenInfo = Depends(require_teacher),
):
    with master_session() as s:
        existing = (
            s.query(SchoolClass)
            .filter(
                SchoolClass.teacher_id == info.teacher_id,
                SchoolClass.label == body.label,
            )
            .one_or_none()
        )
        if existing is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Klass '{body.label}' finns redan.",
            )
        cls = SchoolClass(
            teacher_id=info.teacher_id,
            label=body.label,
            display_name=body.display_name,
            description=body.description,
        )
        s.add(cls)
        s.commit()
        s.refresh(cls)
        return SchoolClassOut(
            id=cls.id, label=cls.label, display_name=cls.display_name,
            description=cls.description, is_archived=cls.is_archived,
            student_count=0, created_at=cls.created_at,
        )


@router.patch("/classes/{class_id}", response_model=SchoolClassOut)
def patch_class(
    class_id: int,
    body: SchoolClassPatchIn,
    info: TokenInfo = Depends(require_teacher),
):
    with master_session() as s:
        cls = s.get(SchoolClass, class_id)
        if cls is None or cls.teacher_id != info.teacher_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Klass saknas.")

        if body.label is not None and body.label != cls.label:
            # Uppdatera även Student.class_label på alla elever som hade
            # gamla labeln så data inte tappas
            old = cls.label
            students = (
                s.query(Student)
                .filter(
                    Student.teacher_id == info.teacher_id,
                    Student.class_label == old,
                )
                .all()
            )
            for stu in students:
                stu.class_label = body.label
            cls.label = body.label

        if body.display_name is not None:
            cls.display_name = body.display_name
        if body.description is not None:
            cls.description = body.description
        if body.is_archived is not None:
            cls.is_archived = body.is_archived
        s.commit()
        s.refresh(cls)
        n = (
            s.query(Student)
            .filter(
                Student.teacher_id == info.teacher_id,
                Student.class_label == cls.label,
            )
            .count()
        )
        return SchoolClassOut(
            id=cls.id, label=cls.label, display_name=cls.display_name,
            description=cls.description, is_archived=cls.is_archived,
            student_count=n, created_at=cls.created_at,
        )


@router.delete("/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(
    class_id: int,
    info: TokenInfo = Depends(require_teacher),
):
    """Radera klass. Eleverna behåller class_label-strängen som
    text-historik (ingen FK), men klassen försvinner från dropdown."""
    with master_session() as s:
        cls = s.get(SchoolClass, class_id)
        if cls is None or cls.teacher_id != info.teacher_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Klass saknas.")
        s.delete(cls)
        s.commit()
    return None
