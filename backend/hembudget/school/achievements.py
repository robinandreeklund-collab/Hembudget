"""Prestationssystem för skolläget.

Varje "achievement" är en symbolisk belöning eleven kan tjäna genom att
utföra handlingar (klara steg/moduler, träffa streaks, etc.). Används
för att göra lärflödet mer motiverande — systemet är helt additivt och
påverkar inte bedömning eller mastery.

Design:
- Stateless helpers — `evaluate_and_grant()` kollar kravet och skapar
  en StudentAchievement-rad om eleven är redo. Idempotent (UniqueConstraint
  hindrar dubbletter).
- Metadata (titel/beskrivning/emoji) ligger i Python, inte DB — byts
  utan migration och kan översättas.
- Streaks räknas från unika datum (UTC) där eleven har minst ett
  slutfört steg.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import distinct, func as sa_func
from sqlalchemy.orm import Session

from .models import (
    Competency,
    ModuleStep,
    StudentAchievement,
    StudentModule,
    StudentStepProgress,
)

log = logging.getLogger(__name__)


# ---------- Metadata ----------

ACHIEVEMENTS: dict[str, dict[str, str]] = {
    "first_step": {
        "title": "Första steget",
        "emoji": "🎯",
        "description": "Du har gjort ditt första steg.",
    },
    "first_module_done": {
        "title": "Första modulen klar",
        "emoji": "📚",
        "description": "En hel modul avklarad — snyggt!",
    },
    "ten_reflections": {
        "title": "Tio tankar tänkta",
        "emoji": "✍️",
        "description": "Tio reflektioner inskickade.",
    },
    "three_mastered_competencies": {
        "title": "Tre kompetenser mästrade",
        "emoji": "🏆",
        "description": "Tre kompetenser har nått 75 % mastery.",
    },
    "seven_day_streak": {
        "title": "Sjudagars serie",
        "emoji": "🔥",
        "description": "Sju dagar i rad med minst ett klart steg.",
    },
    "first_quiz_perfect": {
        "title": "Första quiz-fullpoäng",
        "emoji": "💯",
        "description": "Svarade rätt på ett quiz på första försöket.",
    },
}

# Tröskelvärde för "mastery" (samma som MasteryChart:s visning).
MASTERY_THRESHOLD = 0.75


def describe(key: str) -> dict[str, str] | None:
    meta = ACHIEVEMENTS.get(key)
    if not meta:
        return None
    return {"key": key, **meta}


# ---------- Streak ----------

def _completion_dates(session: Session, student_id: int) -> list[date]:
    """Unika UTC-datum där eleven har minst ett slutfört steg, sorterat
    fallande."""
    rows = (
        session.query(
            distinct(sa_func.date(StudentStepProgress.completed_at))
        )
        .filter(
            StudentStepProgress.student_id == student_id,
            StudentStepProgress.completed_at.isnot(None),
        )
        .all()
    )
    out: list[date] = []
    for (d,) in rows:
        if isinstance(d, date):
            out.append(d)
        elif isinstance(d, str):
            # SQLite kan returnera datum som str "YYYY-MM-DD"
            try:
                out.append(datetime.strptime(d, "%Y-%m-%d").date())
            except ValueError:
                continue
    out.sort(reverse=True)
    return out


def compute_streak(
    session: Session, student_id: int, today: Optional[date] = None,
) -> tuple[int, int]:
    """Returnera (current_streak, longest_streak). current = antal
    konsekutiva dagar fram till idag (eller gårdagen) där eleven var
    aktiv; longest = längsta passet historiskt.

    Om eleven varken var aktiv idag eller igår räknas current=0.
    """
    days = _completion_dates(session, student_id)
    if not days:
        return 0, 0

    today = today or datetime.utcnow().date()
    day_set = set(days)

    # Current streak: börja på idag, gå bakåt. Tillåt att start=går
    # om eleven inte varit aktiv idag än — annars slår streaken bort
    # direkt varje morgon.
    if today in day_set:
        cursor = today
    elif (today - timedelta(days=1)) in day_set:
        cursor = today - timedelta(days=1)
    else:
        cursor = None

    current = 0
    if cursor:
        while cursor in day_set:
            current += 1
            cursor -= timedelta(days=1)

    # Längsta streak: iterera alla dagar sorterat stigande
    longest = 0
    run = 0
    prev: Optional[date] = None
    for d in sorted(days):
        if prev is not None and (d - prev).days == 1:
            run += 1
        else:
            run = 1
        if run > longest:
            longest = run
        prev = d

    return current, longest


# ---------- Evaluation ----------

def _already_has(session: Session, student_id: int, key: str) -> bool:
    return (
        session.query(StudentAchievement)
        .filter(
            StudentAchievement.student_id == student_id,
            StudentAchievement.key == key,
        )
        .first()
        is not None
    )


def _grant(session: Session, student_id: int, key: str) -> None:
    session.add(StudentAchievement(student_id=student_id, key=key))


def _mastered_competency_count(
    session: Session, student_id: int,
) -> int:
    """Antal kompetenser där eleven har nått MASTERY_THRESHOLD. Använder
    samma formel som api/modules._compute_mastery_for_student men
    duplicerar logiken medvetet — achievements kallas ofta, och vi vill
    inte ha en cirkulär import med api-lagret."""
    from .models import ModuleStepCompetency
    rows = (
        session.query(ModuleStepCompetency, ModuleStep)
        .join(ModuleStep, ModuleStepCompetency.step_id == ModuleStep.id)
        .all()
    )
    progs = {
        p.step_id: p
        for p in session.query(StudentStepProgress)
        .filter(StudentStepProgress.student_id == student_id)
        .all()
    }
    by_comp: dict[int, dict] = {}
    for msc, step in rows:
        bucket = by_comp.setdefault(
            msc.competency_id, {"tot": 0.0, "earn": 0.0},
        )
        bucket["tot"] += msc.weight
        prog = progs.get(step.id)
        if prog and prog.completed_at:
            success = 1.0
            if step.kind == "quiz":
                d = prog.data or {}
                to = d.get("teacher_override")
                if isinstance(to, dict) and "correct" in to:
                    success = 1.0 if to.get("correct") else 0.0
                else:
                    success = 1.0 if d.get(
                        "first_correct", d.get("correct")
                    ) else 0.0
            bucket["earn"] += msc.weight * success
    mastered = 0
    for b in by_comp.values():
        if b["tot"] > 0 and (b["earn"] / b["tot"]) >= MASTERY_THRESHOLD:
            mastered += 1
    return mastered


def evaluate_and_grant(session: Session, student_id: int) -> list[str]:
    """Titta på elevens aktuella state och tilldela alla prestationer
    som eleven nu uppfyller men inte redan har. Returnerar listan av
    nya nycklar (kan användas av frontend för celebration-animation)."""
    granted: list[str] = []

    # Hur många steg har eleven slutfört någonsin?
    completed_steps = (
        session.query(StudentStepProgress)
        .filter(
            StudentStepProgress.student_id == student_id,
            StudentStepProgress.completed_at.isnot(None),
        )
        .count()
    )

    # first_step: minst ett slutfört steg
    if completed_steps >= 1 and not _already_has(
        session, student_id, "first_step",
    ):
        _grant(session, student_id, "first_step")
        granted.append("first_step")

    # first_module_done: minst en modul med completed_at
    finished_modules = (
        session.query(StudentModule)
        .filter(
            StudentModule.student_id == student_id,
            StudentModule.completed_at.isnot(None),
        )
        .count()
    )
    if finished_modules >= 1 and not _already_has(
        session, student_id, "first_module_done",
    ):
        _grant(session, student_id, "first_module_done")
        granted.append("first_module_done")

    # ten_reflections: minst 10 reflect-steg slutförda
    reflect_count = (
        session.query(StudentStepProgress)
        .join(ModuleStep, StudentStepProgress.step_id == ModuleStep.id)
        .filter(
            StudentStepProgress.student_id == student_id,
            StudentStepProgress.completed_at.isnot(None),
            ModuleStep.kind == "reflect",
        )
        .count()
    )
    if reflect_count >= 10 and not _already_has(
        session, student_id, "ten_reflections",
    ):
        _grant(session, student_id, "ten_reflections")
        granted.append("ten_reflections")

    # three_mastered_competencies
    if not _already_has(session, student_id, "three_mastered_competencies"):
        if _mastered_competency_count(session, student_id) >= 3:
            _grant(session, student_id, "three_mastered_competencies")
            granted.append("three_mastered_competencies")

    # seven_day_streak
    if not _already_has(session, student_id, "seven_day_streak"):
        current, longest = compute_streak(session, student_id)
        if max(current, longest) >= 7:
            _grant(session, student_id, "seven_day_streak")
            granted.append("seven_day_streak")

    # first_quiz_perfect: minst ett quiz med first_correct=True
    if not _already_has(session, student_id, "first_quiz_perfect"):
        has_perfect = (
            session.query(StudentStepProgress)
            .join(ModuleStep, StudentStepProgress.step_id == ModuleStep.id)
            .filter(
                StudentStepProgress.student_id == student_id,
                ModuleStep.kind == "quiz",
                StudentStepProgress.completed_at.isnot(None),
            )
            .all()
        )
        for p in has_perfect:
            d = p.data if isinstance(p.data, dict) else {}
            if d.get("first_correct") is True:
                _grant(session, student_id, "first_quiz_perfect")
                granted.append("first_quiz_perfect")
                break

    if granted:
        session.flush()
    return granted


# ---------- Enkel list-hjälpare för API ----------

def list_earned(
    session: Session, student_id: int,
) -> list[dict]:
    rows = (
        session.query(StudentAchievement)
        .filter(StudentAchievement.student_id == student_id)
        .order_by(StudentAchievement.earned_at.desc())
        .all()
    )
    out: list[dict] = []
    for r in rows:
        meta = ACHIEVEMENTS.get(r.key)
        if not meta:
            continue
        out.append({
            "key": r.key,
            "title": meta["title"],
            "emoji": meta["emoji"],
            "description": meta["description"],
            "earned_at": r.earned_at.isoformat() if r.earned_at else None,
        })
    return out
