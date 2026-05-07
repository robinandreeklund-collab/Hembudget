"""Centraliserad spel-tid för biz-domänen.

Privat och företag delar samma kalender · 1 real-timme = 1 spel-vecka,
anchor 2026-01-01 (se game_engine/release_schedule.py). När biz-koden
bokför transaktioner, skapar offerter, betalar fakturor osv. så MÅSTE
datumstämpeln komma från spel-tiden — annars hamnar företagskontot på
"7 maj" medan privat-bokföringen står på "2 januari".

Detta modul är den enda källan till `current_game_date()` för biz.
Endpoints som tidigare hämtade `date.today()` ska byta till hjälparen
nedan. Fail-soft: om scope-context saknas (t.ex. bakgrundsjobb utan
elev) faller vi tillbaka till `date.today()` så vi inte krashar tester
eller kickstart-skript.
"""
from __future__ import annotations

from datetime import date


def current_game_date() -> date:
    """Returnera elevens nuvarande spel-datum (synkat med privat-tid).

    Anropare: alla biz-endpoints som bokför affärshändelser. Fail-soft —
    returnerar `date.today()` om scope/elev inte kan hittas, men
    loggar inte (det är legitimt under tester och kickstart).
    """
    try:
        from ..school.engines import (
            get_current_actor_student, master_session,
        )
        from ..school.models import Student
        from ..game_engine.release_schedule import game_date_for
        sid = get_current_actor_student()
        if sid is None:
            return date.today()
        with master_session() as ms:
            stu = ms.get(Student, sid)
            if stu is None or stu.created_at is None:
                return date.today()
            gy, gm, gd = game_date_for(stu.created_at)
            gd = max(1, min(28, gd))
            return date(gy, gm, gd)
    except Exception:
        return date.today()


def current_game_date_for_student(student_id: int) -> date:
    """Variant där vi har student_id direkt (t.ex. tick-engine i
    bakgrunden). Samma fail-soft-mönster."""
    try:
        from ..school.engines import master_session
        from ..school.models import Student
        from ..game_engine.release_schedule import game_date_for
        with master_session() as ms:
            stu = ms.get(Student, student_id)
            if stu is None or stu.created_at is None:
                return date.today()
            gy, gm, gd = game_date_for(stu.created_at)
            gd = max(1, min(28, gd))
            return date(gy, gm, gd)
    except Exception:
        return date.today()
