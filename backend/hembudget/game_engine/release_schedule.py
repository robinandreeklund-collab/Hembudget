"""Realtid-projektion · spel-tid → real-tid mapping.

Mappar spel-månadens 30 dagar till ~4.3 real-timmar. Synkas medvetet
mot företagsdelens AUTO_TICK_INTERVAL_HOURS=1.0 (1 biz-vecka per
real-timme) så privat och företag rör sig genom samma kalender.

Spel-tiden börjar ALLTID på GAME_ANCHOR_DATE = 2026-01-01 oavsett
när eleven skapades. Real-tid sedan student.created_at mappas
framåt på den här tidslinjen — så två elever som skapats olika dagar
ändå spelar samma spel-kalender (men ligger på olika positioner).

NY TAKT: 1 spel-vecka = 1 real-timme  (matchar biz-tick)
       = 1 spel-dag = ~514 sek (~8.5 min)
       = 1 spel-månad ≈ 4.3 real-timmar
       = 1 spel-år ≈ 12 real-dagar

Pedagogiskt: eleven hinner till varje deklarationsfönster (2 mars
arrival, 17 mars start, 31 mars digital deadline, 4 maj sista dag),
ser flera år av karriär, kan jämföra ISK över flera år.

Användning av API:erna filtrerar `released_at IS NULL OR released_at
<= NOW()` så att events dyker upp gradvis när real-tiden går.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional


# 1 real-timme = 1 spel-vecka = 7 spel-dagar
# → 1 spel-dag = 3600/7 ≈ 514 sekunder
SECONDS_PER_GAME_DAY = 3600 // 7  # 514 sek (~8.5 min)
SECONDS_PER_GAME_MONTH = SECONDS_PER_GAME_DAY * 30  # ~4.28 h

# Spel-anchor · alla elever startar här i spel-tid (oavsett när de
# skapades i real-tid). Ändra ALDRIG efter att en kohort startat —
# det skulle hoppa fram alla elevers historik på ett brutalt sätt.
GAME_ANCHOR_DATE = date(2026, 1, 1)


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
    seed_anchor_ym: Optional[str] = None,  # bakåtkompat-arg, ignoreras
    now: Optional[datetime] = None,
) -> tuple[int, int, int]:
    """Beräkna nuvarande spel-datum (år, månad, dag) för en elev.

    Anchor: spel-tiden startar ALLTID på GAME_ANCHOR_DATE. Real-tid
    sedan student.created_at mappas framåt. 1 real-timme = 1 spel-
    vecka. Två elever skapade olika dagar ligger därför på olika
    spel-datum men spelar samma kalender.

    seed_anchor_ym ignoreras — kvar för bakåtkompat med gamla anrop.
    Tas bort i ett senare commit när alla call-sites uppdaterats.
    """
    n = now or datetime.utcnow()
    elapsed_real = max(0.0, (n - student_created_at).total_seconds())
    elapsed_game_days = int(elapsed_real // SECONDS_PER_GAME_DAY)
    y = GAME_ANCHOR_DATE.year
    m = GAME_ANCHOR_DATE.month
    # Räkna fram år/månad/dag (förenklad 30-dagars-månad)
    day = GAME_ANCHOR_DATE.day + elapsed_game_days
    while day > 30:
        day -= 30
        m += 1
        if m > 12:
            m = 1
            y += 1
    return y, m, day


def game_year_month(
    student_created_at: datetime,
    seed_anchor_ym: Optional[str] = None,  # bakåtkompat
    now: Optional[datetime] = None,
) -> str:
    """Returnera 'YYYY-MM' för elevens nuvarande spel-månad."""
    y, m, _d = game_date_for(student_created_at, seed_anchor_ym, now)
    return f"{y:04d}-{m:02d}"


def real_to_game_datetime(
    student_created_at: datetime,
    real_dt: datetime,
) -> datetime:
    """Konvertera ett real-datetime till motsvarande spel-datetime."""
    elapsed_real = max(0.0, (real_dt - student_created_at).total_seconds())
    elapsed_game_seconds = int(elapsed_real * (86400 / SECONDS_PER_GAME_DAY))
    return datetime(
        GAME_ANCHOR_DATE.year, GAME_ANCHOR_DATE.month,
        GAME_ANCHOR_DATE.day,
    ) + timedelta(seconds=elapsed_game_seconds)


def game_to_real_datetime(
    student_created_at: datetime,
    game_dt: datetime,
) -> datetime:
    """Konvertera ett spel-datetime till motsvarande real-datetime."""
    anchor_dt = datetime(
        GAME_ANCHOR_DATE.year, GAME_ANCHOR_DATE.month,
        GAME_ANCHOR_DATE.day,
    )
    elapsed_game = (game_dt - anchor_dt).total_seconds()
    elapsed_real = elapsed_game * (SECONDS_PER_GAME_DAY / 86400)
    return student_created_at + timedelta(seconds=elapsed_real)
