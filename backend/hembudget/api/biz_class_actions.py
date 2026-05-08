"""Klass-actions · mentor + comeback + säsong-events.

Spec: Fas I + J · dev/feature-allabolag.md

* Mentor: framgångsrikt bolag adopterar svagare → båda får poäng,
  mentee:n får +5 rykte i 4 v
* Comeback: shared-opportunities-emit ger 1.5× viktning till bolag
  med <0 vinst 4 v rakt
* Säsong-events: lärare aktiverar Black Friday / rekryteringskris /
  hållbarhetsmånad / konkurs-kedja
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field


from .deps import TokenInfo, require_token


log = logging.getLogger(__name__)

mentor_router = APIRouter(
    prefix="/v2/foretag/mentor", tags=["allabolag"],
)
event_router = APIRouter(
    prefix="/v2/teacher/season-events", tags=["allabolag"],
)


def _require_student(info: TokenInfo) -> int:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(403, "Endast elever")
    return info.student_id


def _require_teacher(info: TokenInfo) -> int:
    if info.role != "teacher" or info.teacher_id is None:
        raise HTTPException(403, "Endast lärare")
    return info.teacher_id


# === Mentor ===

class MentorshipApplyIn(BaseModel):
    mentee_company_share_id: int
    note: Optional[str] = Field(default=None, max_length=500)


class MentorshipOut(BaseModel):
    id: int
    mentor_company_name: str
    mentee_company_name: str
    note: Optional[str]
    is_active: bool
    started_at: str


@mentor_router.get("/candidates", response_model=list[dict])
def list_candidates(info: TokenInfo = Depends(require_token)):
    """Lista bolag som behöver mentor (negativ vinst eller låg UC).
    Bara om jag själv är minst 'etablerat'."""
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import (
        ClassCompanyShare, CompanyMentorship, Student,
    )

    with master_session() as s:
        stu = s.get(Student, student_id)
        if stu is None:
            raise HTTPException(404, "Elev saknas")
        my_share = (
            s.query(ClassCompanyShare)
            .filter(ClassCompanyShare.owner_student_id == student_id)
            .first()
        )
        if my_share is None:
            return []
        if my_share.company_level not in ("etablerat", "marknadsledare"):
            return []

        # Hitta kandidater: negativ vinst ELLER UC < 40
        existing_mentee_ids = {
            m.mentee_share_id for m in
            s.query(CompanyMentorship)
            .filter(
                CompanyMentorship.mentor_share_id == my_share.id,
                CompanyMentorship.is_active.is_(True),
            ).all()
        }
        candidates = (
            s.query(ClassCompanyShare)
            .filter(
                ClassCompanyShare.teacher_id == stu.teacher_id,
                ClassCompanyShare.id != my_share.id,
                ClassCompanyShare.is_published.is_(True),
            )
            .all()
        )
        out = []
        for c in candidates:
            if c.id in existing_mentee_ids:
                continue
            if c.profit_4w < 0 or c.uc_score < 40:
                out.append({
                    "company_share_id": c.id,
                    "company_name": c.company_name,
                    "company_level": c.company_level,
                    "profit_4w": c.profit_4w,
                    "uc_score": c.uc_score,
                    "uc_rating": c.uc_rating,
                })
        return out


@mentor_router.post("/apply", response_model=MentorshipOut)
def apply_mentorship(
    body: MentorshipApplyIn,
    info: TokenInfo = Depends(require_token),
):
    """Adoptera ett svagare bolag. Båda får poäng, mentee:n får
    +5 rykte boost."""
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import (
        ClassCompanyShare, CompanyMentorship,
    )

    with master_session() as s:
        my_share = (
            s.query(ClassCompanyShare)
            .filter(ClassCompanyShare.owner_student_id == student_id)
            .first()
        )
        if my_share is None:
            raise HTTPException(400, "Du saknar företag")
        if my_share.company_level not in ("etablerat", "marknadsledare"):
            raise HTTPException(
                403,
                "Du måste vara minst nivå Etablerat för att vara mentor",
            )
        mentee = s.get(ClassCompanyShare, body.mentee_company_share_id)
        if mentee is None:
            raise HTTPException(404, "Mentee saknas")
        if mentee.teacher_id != my_share.teacher_id:
            raise HTTPException(403, "Annan klass")
        if mentee.id == my_share.id:
            raise HTTPException(400, "Kan inte mentora sig själv")

        existing = (
            s.query(CompanyMentorship)
            .filter(
                CompanyMentorship.mentor_share_id == my_share.id,
                CompanyMentorship.mentee_share_id == mentee.id,
                CompanyMentorship.is_active.is_(True),
            )
            .first()
        )
        if existing is not None:
            raise HTTPException(409, "Redan mentor till bolaget")

        m = CompanyMentorship(
            mentor_share_id=my_share.id,
            mentee_share_id=mentee.id,
            note=body.note,
        )
        s.add(m)

        # Tillfällig +5 rykte till mentee (lagras direkt på cache · läses
        # av nästa Allabolag-fetch)
        mentee.reputation = min(100, mentee.reputation + 5)
        s.commit()
        s.refresh(m)

        try:
            from ..school.activity import log_activity
            log_activity(
                kind="biz.mentor_started",
                summary=(
                    f"Mentor till {mentee.company_name} "
                    f"({mentee.uc_rating}-rating)"
                ),
                payload={"mentee_share_id": mentee.id},
            )
        except Exception:
            pass

        return MentorshipOut(
            id=m.id,
            mentor_company_name=my_share.company_name,
            mentee_company_name=mentee.company_name,
            note=m.note,
            is_active=m.is_active,
            started_at=m.started_at.isoformat(),
        )


@mentor_router.get("/mine", response_model=list[MentorshipOut])
def my_mentorships(info: TokenInfo = Depends(require_token)):
    """Lista mina mentorrelationer (jag som mentor)."""
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import ClassCompanyShare, CompanyMentorship

    with master_session() as s:
        my_share = (
            s.query(ClassCompanyShare)
            .filter(ClassCompanyShare.owner_student_id == student_id)
            .first()
        )
        if my_share is None:
            return []
        rows = (
            s.query(CompanyMentorship)
            .filter(CompanyMentorship.mentor_share_id == my_share.id)
            .order_by(CompanyMentorship.started_at.desc())
            .all()
        )
        share_ids = list({r.mentee_share_id for r in rows})
        mentees = (
            s.query(ClassCompanyShare)
            .filter(ClassCompanyShare.id.in_(share_ids))
            .all()
        )
        m_map = {m.id: m.company_name for m in mentees}
        return [
            MentorshipOut(
                id=r.id,
                mentor_company_name=my_share.company_name,
                mentee_company_name=m_map.get(r.mentee_share_id, "?"),
                note=r.note,
                is_active=r.is_active,
                started_at=r.started_at.isoformat(),
            )
            for r in rows
        ]


# === Säsong-events ===

EVENT_KINDS = {
    "black_friday": {
        "label": "Black Friday-vecka",
        "duration_days": 7,
        "desc": "Shared-opp-frekvens × 3, kort deadline. Konkurrens på max.",
    },
    "recruitment_crisis": {
        "label": "Rekryteringskris",
        "duration_days": 14,
        "desc": "MCP-priset × 1.5, klass-jobb-löner +20 %.",
    },
    "sustainability": {
        "label": "Hållbarhetsbonus-månad",
        "duration_days": 30,
        "desc": "Specialist-utrustning ger +10 % extra rykte.",
    },
    "bankruptcy_chain": {
        "label": "Konkurs-event",
        "duration_days": 7,
        "desc": "En stor kund går omkull · obetalda fakturor < 30d får 50 %.",
    },
}


class SeasonEventIn(BaseModel):
    event_kind: str = Field(..., pattern="^(black_friday|recruitment_crisis|sustainability|bankruptcy_chain)$")


class SeasonEventOut(BaseModel):
    id: int
    event_kind: str
    label: str
    desc: str
    started_at: str
    ends_at: str
    is_active: bool


@event_router.get("", response_model=list[SeasonEventOut])
def list_season_events(info: TokenInfo = Depends(require_token)):
    """Lärare ser alla event för sin klass; elev ser dom också (för status-rendering)."""
    from ..school.engines import master_session
    from ..school.models import ClassSeasonEvent, Student

    if info.role == "teacher" and info.teacher_id:
        teacher_id = info.teacher_id
    elif info.role == "student" and info.student_id:
        with master_session() as s:
            stu = s.get(Student, info.student_id)
            if stu is None:
                raise HTTPException(404, "Elev saknas")
            teacher_id = stu.teacher_id
    else:
        raise HTTPException(403, "Endast lärare/elev")

    with master_session() as s:
        rows = (
            s.query(ClassSeasonEvent)
            .filter(ClassSeasonEvent.teacher_id == teacher_id)
            .order_by(ClassSeasonEvent.started_at.desc())
            .limit(20)
            .all()
        )
        return [
            SeasonEventOut(
                id=r.id,
                event_kind=r.event_kind,
                label=EVENT_KINDS.get(r.event_kind, {}).get("label", r.event_kind),
                desc=EVENT_KINDS.get(r.event_kind, {}).get("desc", ""),
                started_at=r.started_at.isoformat(),
                ends_at=r.ends_at.isoformat(),
                is_active=r.is_active and r.ends_at > datetime.utcnow(),
            )
            for r in rows
        ]


@event_router.post("", response_model=SeasonEventOut)
def trigger_season_event(
    body: SeasonEventIn,
    info: TokenInfo = Depends(require_token),
):
    """Lärare aktiverar säsong-event för sin klass."""
    teacher_id = _require_teacher(info)
    if body.event_kind not in EVENT_KINDS:
        raise HTTPException(400, "Okänt event")
    meta = EVENT_KINDS[body.event_kind]
    from ..school.engines import master_session
    from ..school.models import ClassSeasonEvent
    now = datetime.utcnow()
    ends = now + timedelta(days=meta["duration_days"])
    with master_session() as s:
        ev = ClassSeasonEvent(
            teacher_id=teacher_id,
            event_kind=body.event_kind,
            started_at=now,
            ends_at=ends,
            is_active=True,
        )
        s.add(ev)
        s.commit()
        s.refresh(ev)
        return SeasonEventOut(
            id=ev.id,
            event_kind=ev.event_kind,
            label=meta["label"],
            desc=meta["desc"],
            started_at=ev.started_at.isoformat(),
            ends_at=ev.ends_at.isoformat(),
            is_active=True,
        )


@event_router.delete("/{event_id}")
def end_season_event(
    event_id: int,
    info: TokenInfo = Depends(require_token),
):
    """Avsluta event manuellt (innan ends_at)."""
    teacher_id = _require_teacher(info)
    from ..school.engines import master_session
    from ..school.models import ClassSeasonEvent
    with master_session() as s:
        ev = s.get(ClassSeasonEvent, event_id)
        if ev is None or ev.teacher_id != teacher_id:
            raise HTTPException(404, "Event saknas")
        ev.is_active = False
        ev.ends_at = datetime.utcnow()
        s.commit()
    return {"ok": True}


# === Helper · used by shared_opportunities + tick_engine ===

def is_event_active(teacher_id: int, event_kind: str) -> bool:
    """Kolla om ett specifikt event är aktivt just nu för en klass."""
    from ..school.engines import master_session
    from ..school.models import ClassSeasonEvent
    now = datetime.utcnow()
    with master_session() as s:
        ev = (
            s.query(ClassSeasonEvent)
            .filter(
                ClassSeasonEvent.teacher_id == teacher_id,
                ClassSeasonEvent.event_kind == event_kind,
                ClassSeasonEvent.is_active.is_(True),
                ClassSeasonEvent.ends_at > now,
            )
            .first()
        )
        return ev is not None
