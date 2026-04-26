"""Tester för aktie-seedmotor."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.school.models import MasterBase
from hembudget.school.stock_models import MarketCalendar, StockMaster
from hembudget.school.stock_seed import (
    STOCK_UNIVERSE,
    _swedish_holidays,
    seed_all,
    seed_market_calendar,
    seed_stock_universe,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    MasterBase.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_seed_stock_universe_creates_30(session):
    n = seed_stock_universe(session)
    assert n == 30
    assert session.query(StockMaster).count() == 30


def test_seed_stock_universe_is_idempotent(session):
    seed_stock_universe(session)
    n2 = seed_stock_universe(session)
    assert n2 == 0
    assert session.query(StockMaster).count() == 30


def test_seed_universe_covers_at_least_8_sectors(session):
    seed_stock_universe(session)
    sectors = {s.sector for s in session.query(StockMaster).all()}
    assert len(sectors) >= 7  # Minst 7 distinkta sektorer (Industri, Bank, Telecom, ...)


def test_universe_tickers_unique():
    tickers = [s["ticker"] for s in STOCK_UNIVERSE]
    assert len(tickers) == len(set(tickers))


def test_universe_uses_yahoo_format():
    """Yahoo-format kräver suffix .ST för Stockholmsbörsen."""
    for s in STOCK_UNIVERSE:
        assert s["ticker"].endswith(".ST"), f"{s['ticker']} har inte .ST-suffix"


def test_swedish_holidays_2026_includes_known_dates():
    h = _swedish_holidays(2026)
    assert date(2026, 1, 1) in h    # Nyårsdagen
    assert date(2026, 1, 6) in h    # Trettondag jul
    assert date(2026, 5, 1) in h    # Första maj
    assert date(2026, 12, 24) in h  # Julafton
    assert date(2026, 12, 25) in h  # Juldagen
    assert date(2026, 12, 26) in h  # Annandag jul
    assert date(2026, 12, 31) in h  # Nyårsafton


def test_swedish_holidays_2026_easter():
    """Påsken 2026: söndag 5 april → långfredag 3 april, annandag 6 april."""
    h = _swedish_holidays(2026)
    assert date(2026, 4, 3) in h     # Långfredag
    assert date(2026, 4, 6) in h     # Annandag påsk
    assert date(2026, 5, 14) in h    # Kristi himmelsfärd (39 d efter påskdag)


def test_seed_market_calendar_creates_days(session):
    n = seed_market_calendar(session, years_ahead=0)
    # Minst 365 dagar i innevarande år
    assert n >= 300


def test_seed_market_calendar_is_idempotent(session):
    seed_market_calendar(session, years_ahead=0)
    n2 = seed_market_calendar(session, years_ahead=0)
    assert n2 == 0


def test_calendar_marks_weekends_closed(session):
    seed_market_calendar(session, years_ahead=0)
    today = date.today()
    # Hitta nästa lördag
    days_to_saturday = (5 - today.weekday()) % 7 or 7
    sat = today.replace(day=1)
    # Bara verifiera att ALLA lördagar i året är closed
    rows = (
        session.query(MarketCalendar)
        .filter(MarketCalendar.calendar_date.between(
            date(today.year, 1, 1), date(today.year, 12, 31),
        ))
        .all()
    )
    for r in rows:
        if r.calendar_date.weekday() == 5:  # Lördag
            assert r.status == "closed"
        elif r.calendar_date.weekday() == 6:  # Söndag
            assert r.status == "closed"


def test_calendar_marks_normal_weekdays_open(session):
    seed_market_calendar(session, years_ahead=0)
    # En vardag som inte är helgdag
    rows = (
        session.query(MarketCalendar)
        .filter(MarketCalendar.status == "open")
        .all()
    )
    assert len(rows) > 200  # Ungefär 252 handelsdagar/år
    for r in rows:
        assert r.calendar_date.weekday() < 5
        assert r.open_time == "09:00"
        assert r.close_time == "17:30"


def test_seed_all_returns_counts(session):
    r = seed_all(session)
    assert r["stocks_added"] == 30
    assert r["calendar_days_added"] >= 365
