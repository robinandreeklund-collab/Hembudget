"""Realtid-projektion · spel-tid → real-tid mapping.

Mappar spel-månadens 30 dagar till ~4.3 real-timmar. Synkas medvetet
mot företagsdelens AUTO_TICK_INTERVAL_HOURS=1.0 (1 biz-vecka per
real-timme) så privat och företag rör sig genom samma kalender.

Används av seed-flödet (fixed_expenses, salary_phase, health_engine,
event_engine, pension-transfer) för att sätta `released_at` på
MailItem + Transaction.

API:erna filtrerar `released_at IS NULL OR released_at <= NOW()` så
att events dyker upp gradvis när real-tiden går.

NY TAKT: 1 spel-vecka = 1 real-timme  (matchar biz-tick)
       = 1 spel-dag = ~514 sek (~8.5 min)
       = 1 spel-månad ≈ 4.3 real-timmar
       = 1 spel-år ≈ 12 real-dagar

Pedagogiskt: eleven hinner till deklaration (april) flera gånger per
termin, ser konsekvenser av sparval, kan ta sig genom 2-3 spel-år
inom en hemläxa.

- Dag 1 (hyra) → T0 + 0 min (direkt synlig)
- Dag 3 (el)  → T0 + 17 min
- Dag 7 (mobil) → T0 + 1 h
- Dag 22 (lönespec) → T0 + ~3 h
- Dag 25 (lön) → T0 + ~3.5 h
- Nästa månad börjar → T0 + ~4.3 h
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


# 1 real-timme = 1 spel-vecka = 7 spel-dagar
# → 1 spel-dag = 3600/7 ≈ 514 sekunder
SECONDS_PER_GAME_DAY = 3600 // 7  # 514 sek (~8.5 min)
SECONDS_PER_GAME_MONTH = SECONDS_PER_GAME_DAY * 30  # ~4.28 h


def release_at_for_day(
    base: datetime, day_in_month: int,
) -> datetime:
    """Räkna ut när ett event ska 'släppas' baserat på spel-dag.

    base: T0 (typiskt student.created_at eller current month start)
    day_in_month: 1-30, vilken dag i spelmånaden eventet hör till
    """
    day = max(1, min(30, int(day_in_month)))
    offset = timedelta(seconds=(day - 1) * SECONDS_PER_GAME_DAY)
    return base + offset


def release_at_for_date(
    base: datetime, event_date,
) -> datetime:
    """Wrappar release_at_for_day med ett date/datetime-objekt
    som har .day-attribut."""
    if event_date is None:
        return base
    try:
        day = int(getattr(event_date, "day", 1))
    except Exception:
        day = 1
    return release_at_for_day(base, day)


def is_released(release_at: Optional[datetime], now: Optional[datetime] = None) -> bool:
    """True om eventet är synligt nu."""
    if release_at is None:
        return True
    n = now or datetime.utcnow()
    return release_at <= n


def game_date_for(
    student_created_at: datetime,
    seed_anchor_ym: str,
    now: Optional[datetime] = None,
) -> tuple[int, int, int]:
    """Beräkna nuvarande spel-datum (år, månad, dag) för en elev.

    seed_anchor_ym: "YYYY-MM" som motsvarar 'current month' när eleven
    skapades (typiskt real-månad vid student-skapandet).

    1 real-timme = 1 spel-vecka. Spel-tiden börjar i seed_anchor_ym
    dag 1 vid student.created_at.
    """
    n = now or datetime.utcnow()
    elapsed_real = max(0.0, (n - student_created_at).total_seconds())
    elapsed_game_days = int(elapsed_real // SECONDS_PER_GAME_DAY)
    y, m = (int(p) for p in seed_anchor_ym.split("-"))
    # Räkna fram år/månad/dag
    day = 1 + elapsed_game_days
    while day > 30:  # förenklad 30-dagars-månad för spel-tiden
        day -= 30
        m += 1
        if m > 12:
            m = 1
            y += 1
    return y, m, day


def game_year_month(
    student_created_at: datetime,
    seed_anchor_ym: str,
    now: Optional[datetime] = None,
) -> str:
    """Returnera 'YYYY-MM' för elevens nuvarande spel-månad."""
    y, m, _d = game_date_for(student_created_at, seed_anchor_ym, now)
    return f"{y:04d}-{m:02d}"
