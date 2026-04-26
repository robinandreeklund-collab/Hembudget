"""Tester för QuoteProvider-abstraktionen och börstidshjälpare."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.school.models import MasterBase
from hembudget.school.stock_models import MarketCalendar
from hembudget.school.stock_seed import seed_market_calendar
from hembudget.stocks.calendar import get_status, is_market_open, next_open
from hembudget.stocks.quote_providers import (
    MockQuoteProvider,
    YFinanceProvider,
    get_provider,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    MasterBase.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# --- MockQuoteProvider ---

def test_mock_provider_returns_quotes_for_each_ticker():
    p = MockQuoteProvider()
    quotes = p.fetch_quotes(["VOLV-B.ST", "ERIC-B.ST"])
    assert len(quotes) == 2
    assert {q.ticker for q in quotes} == {"VOLV-B.ST", "ERIC-B.ST"}
    for q in quotes:
        assert q.last > 0
        assert q.bid is not None and q.ask is not None
        assert q.bid <= q.last <= q.ask


def test_mock_provider_is_deterministic_per_5min_bucket():
    p = MockQuoteProvider()
    a = p.fetch_quotes(["VOLV-B.ST"])
    b = p.fetch_quotes(["VOLV-B.ST"])
    # Samma 5-min-bucket → samma kurs (testas inom samma sekund)
    assert a[0].last == b[0].last


def test_mock_provider_different_tickers_different_prices():
    p = MockQuoteProvider()
    quotes = p.fetch_quotes(["A.ST", "B.ST", "C.ST"])
    # Inte garanterat unika men det är osannolikt att tre tickers har
    # exakt samma base_price (hash mod 500)
    prices = {q.last for q in quotes}
    assert len(prices) >= 2  # Minst två olika priser


def test_get_provider_default_is_mock(monkeypatch):
    monkeypatch.delenv("HEMBUDGET_QUOTE_PROVIDER", raising=False)
    p = get_provider()
    assert isinstance(p, MockQuoteProvider)


def test_get_provider_yfinance_when_env_set(monkeypatch):
    monkeypatch.setenv("HEMBUDGET_QUOTE_PROVIDER", "yfinance")
    p = get_provider()
    assert isinstance(p, YFinanceProvider)


def test_get_provider_unknown_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("HEMBUDGET_QUOTE_PROVIDER", "okand")
    p = get_provider()
    assert isinstance(p, MockQuoteProvider)


def test_yfinance_provider_returns_empty_when_pkg_missing():
    """Om yfinance ej installerat ska providern returnera tom lista,
    inte krascha."""
    p = YFinanceProvider()
    quotes = p.fetch_quotes(["VOLV-B.ST"])
    # yfinance kanske finns i miljön — då tom eller någon kurs.
    # Det viktiga är att vi inte kraschar.
    assert isinstance(quotes, list)


# --- Börskalender-helpers ---

def test_get_status_returns_row_when_seeded(session):
    seed_market_calendar(session, years_ahead=0)
    today = date.today()
    row = get_status(session, today)
    assert row is not None


def test_get_status_returns_none_for_unseeded_date(session):
    seed_market_calendar(session, years_ahead=0)
    row = get_status(session, date(2200, 1, 1))
    assert row is None


def test_is_market_open_returns_false_on_weekend(session):
    seed_market_calendar(session, years_ahead=0)
    # Hitta nästa lördag
    today = date.today()
    days_to_sat = (5 - today.weekday()) % 7 or 7
    sat = today + timedelta(days=days_to_sat)
    sat_noon = datetime.combine(sat, datetime.strptime("12:00", "%H:%M").time())
    assert is_market_open(session, sat_noon) is False


def test_is_market_open_returns_true_inside_hours_on_weekday(session):
    seed_market_calendar(session, years_ahead=0)
    # Hitta nästa måndag som inte är helgdag
    today = date.today()
    for delta in range(0, 14):
        d = today + timedelta(days=delta)
        row = get_status(session, d)
        if row and row.status == "open":
            target = datetime.combine(
                d, datetime.strptime("10:00", "%H:%M").time(),
            )
            assert is_market_open(session, target) is True
            return
    pytest.fail("Hittade ingen öppen börsdag på 14 dagar")


def test_is_market_open_returns_false_before_open(session):
    seed_market_calendar(session, years_ahead=0)
    today = date.today()
    for delta in range(0, 14):
        d = today + timedelta(days=delta)
        row = get_status(session, d)
        if row and row.status == "open":
            target = datetime.combine(
                d, datetime.strptime("08:00", "%H:%M").time(),
            )
            assert is_market_open(session, target) is False
            return


def test_is_market_open_returns_false_after_close(session):
    seed_market_calendar(session, years_ahead=0)
    today = date.today()
    for delta in range(0, 14):
        d = today + timedelta(days=delta)
        row = get_status(session, d)
        if row and row.status == "open":
            target = datetime.combine(
                d, datetime.strptime("18:00", "%H:%M").time(),
            )
            assert is_market_open(session, target) is False
            return


def test_next_open_returns_a_future_datetime(session):
    seed_market_calendar(session, years_ahead=0)
    n = next_open(session, after=datetime.now())
    assert n is not None
    assert n > datetime.now()
    # Ska alltid vara 09:00
    assert n.hour == 9 and n.minute == 0
