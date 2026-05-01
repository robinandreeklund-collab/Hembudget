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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..game_engine.profile_generator import (
    GeneratedProfile,
    generate_profile,
)
from ..school.engines import master_session
from ..school.game_engine_models import (
    ClassCalendar,
    compute_current_sim_year_month,
    shift_year_month,
)
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
