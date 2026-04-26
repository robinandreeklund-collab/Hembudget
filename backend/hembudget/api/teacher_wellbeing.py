"""Lärarintegration för Wellbeing — klassöversikt med rödflaggor +
elevens leaderboard (anonymiserad).

Två endpoints med olika synvinklar:
- /class/leaderboard (eleven får anonym rangordning)
- /teacher/class/wellbeing (läraren får full vy med namn + rödflagg-trösklar)
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.base import session_scope
from ..db.models import WellbeingScore
from ..school.engines import (
    get_current_actor_student,
    master_session,
    scope_context,
    scope_for_student,
)
from ..school.models import Student
from ..school.social_models import ClassDisplaySettings
from ..wellbeing.calculator import calculate_wellbeing
from .deps import TokenInfo, require_auth, require_teacher


router = APIRouter(tags=["teacher-wellbeing"])


# ---------- Lärarens fulla vy ----------

class WellbeingClassRow(BaseModel):
    student_id: int
    display_name: str
    class_label: Optional[str]
    total_score: int
    economy: int
    health: int
    social: int
    leisure: int
    safety: int
    events_accepted: int
    events_declined: int
    budget_violations: int
    decline_streak: int
    # Rödflaggor — sätts av servern baserat på trösklar
    flags: list[str]


def _wellbeing_for_student(student) -> dict:
    """Beräkna live Wellbeing för en elev. Sammansatt resultat."""
    from ..db.models import DeclineStreak
    scope_key = scope_for_student(student)
    today = date.today()
    ym = f"{today.year:04d}-{today.month:02d}"
    with scope_context(scope_key):
        with session_scope() as s:
            r = calculate_wellbeing(s, ym)
            streak_row = s.query(DeclineStreak).first()
            streak = streak_row.current_streak if streak_row else 0

    flags: list[str] = []
    if r.social < 30:
        flags.append("social_low")
    if r.health < 50 and r.budget_violations >= 2:
        flags.append("budget_underfed")
    if r.economy < 30:
        flags.append("economy_critical")
    if r.safety < 30:
        flags.append("buffer_low")
    if streak >= 5:
        flags.append("decline_streak_high")
    if r.total_score < 40:
        flags.append("overall_low")

    return {
        "total_score": r.total_score,
        "economy": r.economy,
        "health": r.health,
        "social": r.social,
        "leisure": r.leisure,
        "safety": r.safety,
        "events_accepted": r.events_accepted,
        "events_declined": r.events_declined,
        "budget_violations": r.budget_violations,
        "decline_streak": streak,
        "flags": flags,
    }


@router.get("/teacher/class/wellbeing")
def teacher_class_wellbeing(
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    """Lärar-vy: alla elever med fullständigt namn + Wellbeing per
    dimension + rödflaggor.

    Detta är inte anonymiserat — läraren ska kunna identifiera elever
    som mår sämre och prata med dem. Rödflaggor:
      - social_low: social < 30
      - budget_underfed: health < 50 OCH budget_violations >= 2
      - economy_critical: economy < 30
      - buffer_low: safety < 30
      - decline_streak_high: 5+ nej i rad
      - overall_low: total < 40
    """
    with master_session() as ms:
        students = (
            ms.query(Student)
            .filter(Student.teacher_id == info.teacher_id)
            .order_by(Student.class_label, Student.display_name)
            .all()
        )
        rows: list[WellbeingClassRow] = []
        for st in students:
            try:
                wb = _wellbeing_for_student(st)
            except Exception:
                # Fail-soft: om en elev har trasigt scope, visa nollor
                # och tom flag-lista. Lärar-UI:t indikerar 'data error'.
                wb = {
                    "total_score": 0, "economy": 0, "health": 0,
                    "social": 0, "leisure": 0, "safety": 0,
                    "events_accepted": 0, "events_declined": 0,
                    "budget_violations": 0, "decline_streak": 0,
                    "flags": ["data_error"],
                }
            rows.append(WellbeingClassRow(
                student_id=st.id,
                display_name=st.display_name,
                class_label=st.class_label,
                **wb,
            ))

        # Klass-aggregat
        if rows:
            avg_total = sum(r.total_score for r in rows) / len(rows)
            avg_economy = sum(r.economy for r in rows) / len(rows)
            avg_social = sum(r.social for r in rows) / len(rows)
            students_with_flags = sum(
                1 for r in rows if r.flags and "data_error" not in r.flags
            )
        else:
            avg_total = avg_economy = avg_social = 0
            students_with_flags = 0

        return {
            "rows": [r.model_dump() for r in rows],
            "aggregate": {
                "students": len(rows),
                "avg_total_score": round(avg_total, 1),
                "avg_economy": round(avg_economy, 1),
                "avg_social": round(avg_social, 1),
                "students_with_flags": students_with_flags,
            },
        }


# ---------- Elev-leaderboard (anonymiserad) ----------

class LeaderboardEntry(BaseModel):
    rank: int
    is_me: bool
    display_label: str  # "Du själv" eller "Anonym A/B/..."
    total_score: int
    social: int
    events_accepted: int


@router.get(
    "/class/leaderboard",
    dependencies=[Depends(require_auth)],
)
def class_leaderboard() -> dict:
    """Anonymiserad rangordning för eleven. Visar elevens egen position
    + topp och bottenscore + klassgenomsnitt.

    Endast aktiverad om läraren slagit på class_list_enabled. Annars
    returnerar tomt + enabled=False så frontend kan dölja sektionen.

    show_full_names = True kräver i V2 även elev-opt-in (PersonalityProfile-
    flagga). I V1 förblir alla anonymiserade förutom 'Du själv'.
    """
    actor_id = get_current_actor_student()
    if actor_id is None:
        raise HTTPException(403, "Saknar student-kontext")

    with master_session() as ms:
        me = ms.query(Student).filter(Student.id == actor_id).first()
        if me is None:
            raise HTTPException(404, "Student saknas")

        cfg = (
            ms.query(ClassDisplaySettings)
            .filter(ClassDisplaySettings.teacher_id == me.teacher_id)
            .first()
        )
        if cfg is None or not cfg.class_list_enabled:
            return {"enabled": False, "entries": [], "aggregate": None}

        classmates = (
            ms.query(Student)
            .filter(Student.teacher_id == me.teacher_id)
            .order_by(Student.id)
            .all()
        )

    # Beräkna Wellbeing per elev (live)
    scored: list[tuple[Student, dict]] = []
    for st in classmates:
        try:
            wb = _wellbeing_for_student(st)
        except Exception:
            wb = {
                "total_score": 0, "social": 0, "events_accepted": 0,
            }
        scored.append((st, wb))

    # Sortera: högsta total_score först
    scored.sort(key=lambda x: -x[1]["total_score"])

    entries: list[LeaderboardEntry] = []
    for rank, (st, wb) in enumerate(scored, start=1):
        is_me = st.id == actor_id
        if is_me:
            label = "Du själv"
        else:
            # Anonymisera: bokstav baserat på rank-position
            label = f"Anonym {chr(64 + rank) if rank <= 26 else '?'}"
        entries.append(LeaderboardEntry(
            rank=rank,
            is_me=is_me,
            display_label=label,
            total_score=wb["total_score"],
            social=wb["social"],
            events_accepted=wb["events_accepted"],
        ))

    # Aggregat: snitt + min/max + min position
    if scored:
        avg = sum(s[1]["total_score"] for s in scored) / len(scored)
        my_entry = next((e for e in entries if e.is_me), None)
    else:
        avg = 0
        my_entry = None

    return {
        "enabled": True,
        "entries": [e.model_dump() for e in entries],
        "aggregate": {
            "class_avg": round(avg, 1),
            "my_rank": my_entry.rank if my_entry else None,
            "my_total": my_entry.total_score if my_entry else None,
            "diff_from_avg": (
                round(my_entry.total_score - avg, 1) if my_entry else 0
            ),
            "total_students": len(scored),
        },
    }
