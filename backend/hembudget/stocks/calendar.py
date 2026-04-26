"""Helpers för att avgöra om börsen är öppen vid ett givet tillfälle.

Läser från `MarketCalendar`-tabellen som är seedad via
`school/stock_seed.py::seed_market_calendar`.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy.orm import Session

from ..school.stock_models import MarketCalendar


def get_status(session: Session, d: date, exchange: str = "XSTO") -> Optional[MarketCalendar]:
    """Returnera kalenderraden för datumet (eller None om ej seedad)."""
    return (
        session.query(MarketCalendar)
        .filter(
            MarketCalendar.calendar_date == d,
            MarketCalendar.exchange == exchange,
        )
        .first()
    )


def is_market_open(
    session: Session,
    at: Optional[datetime] = None,
    exchange: str = "XSTO",
) -> bool:
    """True om börsen är öppen just nu (eller vid `at`).

    Försiktig default — om kalendern saknar dagen returnerar vi False
    eftersom vi inte vet säkert. Det skyddar mot att tillåta order när
    seed-jobbet inte kört.
    """
    at = at or datetime.now()
    row = get_status(session, at.date(), exchange)
    if row is None or row.status != "open":
        return False
    if not row.open_time or not row.close_time:
        return False
    open_t = time(*[int(x) for x in row.open_time.split(":")])
    close_t = time(*[int(x) for x in row.close_time.split(":")])
    now_t = at.time()
    return open_t <= now_t <= close_t


def next_open(
    session: Session,
    after: Optional[datetime] = None,
    exchange: str = "XSTO",
) -> Optional[datetime]:
    """Returnera tidpunkt då börsen nästa gång öppnar (eller None om
    inget hittas inom 30 dagar)."""
    from datetime import timedelta

    after = after or datetime.now()
    cutoff = after.date() + timedelta(days=30)
    rows = (
        session.query(MarketCalendar)
        .filter(
            MarketCalendar.calendar_date >= after.date(),
            MarketCalendar.calendar_date <= cutoff,
            MarketCalendar.exchange == exchange,
            MarketCalendar.status == "open",
        )
        .order_by(MarketCalendar.calendar_date.asc())
        .all()
    )
    for row in rows:
        if not row.open_time:
            continue
        h, m = (int(x) for x in row.open_time.split(":"))
        candidate = datetime.combine(row.calendar_date, time(h, m))
        if candidate > after:
            return candidate
    return None
