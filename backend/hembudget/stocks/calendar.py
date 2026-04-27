"""Helpers för att avgöra om börsen är öppen vid ett givet tillfälle.

Läser från `MarketCalendar`-tabellen som är seedad via
`school/stock_seed.py::seed_market_calendar`.

VIKTIGT: alla tider lagras som lokal Stockholm-tid (XSTO). Cloud Run
kör i UTC så vi måste konvertera datetime.now() till Stockholm-tid
INNAN vi jämför mot open_time/close_time. Annars är börsen 'stängd'
första 1-2 timmar varje dag (UTC ligger 1-2 h efter Stockholm).
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..school.stock_models import MarketCalendar

_STHLM = ZoneInfo("Europe/Stockholm")


def _now_stockholm(at: Optional[datetime] = None) -> datetime:
    """Returnera tiden i Stockholm-zon.

    Konventioner:
    - at=None: hämta server-tid och konvertera till Stockholm
      (datetime.now(tz=...) ger korrekt resultat oavsett om servern
      kör i UTC, lokal tid eller annat).
    - at är timezone-aware: konvertera till Stockholm.
    - at är naiv: TOLKA SOM Stockholm-naiv (tester och callers förväntar
      sig att 'naive 09:30' betyder 09:30 svensk tid). På Cloud Run
      där datetime.now() är UTC går vi via at=None-branchen och
      undviker problemet helt.
    """
    if at is None:
        return datetime.now(_STHLM)
    if at.tzinfo is None:
        return at.replace(tzinfo=_STHLM)
    return at.astimezone(_STHLM)


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
    sthlm_now = _now_stockholm(at)
    row = get_status(session, sthlm_now.date(), exchange)
    if row is None or row.status != "open":
        return False
    if not row.open_time or not row.close_time:
        return False
    open_t = time(*[int(x) for x in row.open_time.split(":")])
    close_t = time(*[int(x) for x in row.close_time.split(":")])
    now_t = sthlm_now.time()
    return open_t <= now_t <= close_t


def next_open(
    session: Session,
    after: Optional[datetime] = None,
    exchange: str = "XSTO",
) -> Optional[datetime]:
    """Returnera tidpunkt då börsen nästa gång öppnar (eller None om
    inget hittas inom 30 dagar). Returnerar Stockholm-zonad datetime."""
    from datetime import timedelta

    sthlm_after = _now_stockholm(after)
    cutoff = sthlm_after.date() + timedelta(days=30)
    rows = (
        session.query(MarketCalendar)
        .filter(
            MarketCalendar.calendar_date >= sthlm_after.date(),
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
        # Returnera naiv datetime (Stockholm-naiv) — samma konvention
        # som tester och callers förväntar sig.
        candidate = datetime.combine(row.calendar_date, time(h, m))
        # Jämför som naiv Stockholm-tid mot sthlm_after stripped
        sthlm_after_naive = sthlm_after.replace(tzinfo=None)
        if candidate > sthlm_after_naive:
            return candidate
    return None
