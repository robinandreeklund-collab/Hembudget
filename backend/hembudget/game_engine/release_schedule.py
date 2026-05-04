"""Realtid-projektion · spel-tid → real-tid mapping.

Mappar spel-månadens 30 dagar till 5 real-dagar (en skolvecka).
Används av seed-flödet (fixed_expenses, salary_phase, health_engine,
event_engine, pension-transfer) för att sätta `released_at` på
MailItem + Transaction.

API:erna filtrerar `released_at IS NULL OR released_at <= NOW()` så
att events dyker upp gradvis när real-tiden går.

1 spel-dag = 4 real-timmar
- Dag 1 (hyra) → T0 + 0 h (direkt synlig)
- Dag 3 (el)  → T0 + 8 h (samma kväll)
- Dag 7 (mobil) → T0 + 24 h (måndag eftermiddag)
- Dag 25 (lön) → T0 + 96 h (fredag morgon)
- Dag 30 (slut) → T0 + 116 h (måndag morgon vecka 2)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


# 5 real-dagar = 30 spel-dagar → 1 spel-dag = 4 timmar
SECONDS_PER_GAME_DAY = int(86400 * 5 / 30)  # 14 400 = 4 h


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
