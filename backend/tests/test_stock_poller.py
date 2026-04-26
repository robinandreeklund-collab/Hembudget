"""Tester för poll_quotes-funktionen."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.school.models import MasterBase
from hembudget.school.stock_models import (
    LatestStockQuote,
    MarketCalendar,
    StockMaster,
    StockQuote,
)
from hembudget.school.stock_seed import seed_all
from hembudget.stocks.poller import downsample_old_history, poll_quotes
from hembudget.stocks.quote_providers import MockQuoteProvider


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    MasterBase.metadata.create_all(engine)
    with Session(engine) as s:
        seed_all(s)
        yield s


def _force_market_open(session: Session) -> None:
    """Sätt dagens kalender-rad till open så poll_quotes inte skippar."""
    today = date.today()
    row = (
        session.query(MarketCalendar)
        .filter(MarketCalendar.calendar_date == today)
        .first()
    )
    if row is None:
        row = MarketCalendar(
            calendar_date=today, exchange="XSTO",
            status="open", open_time="00:00", close_time="23:59",
        )
        session.add(row)
    else:
        row.status = "open"
        row.open_time = "00:00"
        row.close_time = "23:59"
    session.flush()


def test_poll_quotes_skips_when_market_closed(session):
    # Force closed
    today = date.today()
    row = (
        session.query(MarketCalendar)
        .filter(MarketCalendar.calendar_date == today)
        .first()
    )
    if row:
        row.status = "closed"
        session.flush()
    result = poll_quotes(session, provider=MockQuoteProvider())
    assert result["skipped_market_closed"] is True
    assert result["fetched"] == 0


def test_poll_quotes_force_overrides_closed(session):
    result = poll_quotes(session, provider=MockQuoteProvider(), force=True)
    assert result["skipped_market_closed"] is False
    assert result["fetched"] == 30
    assert session.query(StockQuote).count() == 30
    assert session.query(LatestStockQuote).count() == 30


def test_poll_quotes_writes_history(session):
    _force_market_open(session)
    poll_quotes(session, provider=MockQuoteProvider())
    rows = session.query(StockQuote).all()
    assert len(rows) == 30
    for r in rows:
        assert r.last > 0
        assert r.source == "mock"


def test_poll_quotes_upserts_latest(session):
    _force_market_open(session)
    # Första pollen
    poll_quotes(session, provider=MockQuoteProvider(base_seed=1))
    first_count = session.query(LatestStockQuote).count()
    # Andra pollen — ingen ny rad, bara update
    poll_quotes(session, provider=MockQuoteProvider(base_seed=2))
    second_count = session.query(LatestStockQuote).count()
    assert first_count == 30
    assert second_count == 30  # Ingen dubblering


def test_poll_quotes_handles_empty_universe(session):
    # Töm universum
    session.query(StockMaster).delete()
    session.flush()
    _force_market_open(session)
    result = poll_quotes(session, provider=MockQuoteProvider())
    assert result["fetched"] == 0


def test_downsample_old_history_keeps_last_per_day(session):
    _force_market_open(session)
    # Skapa flera kursrader för en ticker, alla för 100 dagar sedan
    old_date = date.today() - timedelta(days=100)
    base_dt = datetime.combine(old_date, datetime.min.time())
    for h in range(0, 24, 2):
        session.add(StockQuote(
            ticker="VOLV-B.ST",
            ts=base_dt + timedelta(hours=h),
            last=Decimal("100"),
            source="mock",
        ))
    session.flush()
    assert session.query(StockQuote).count() == 12

    deleted = downsample_old_history(session, keep_full_days=90)
    # 11 raderade (en behålls per dag/ticker)
    assert deleted == 11
    assert session.query(StockQuote).count() == 1


def test_downsample_does_not_touch_recent(session):
    _force_market_open(session)
    poll_quotes(session, provider=MockQuoteProvider())
    before = session.query(StockQuote).count()
    deleted = downsample_old_history(session, keep_full_days=90)
    assert deleted == 0
    assert session.query(StockQuote).count() == before


def test_latest_quote_has_link_to_history_id(session):
    _force_market_open(session)
    poll_quotes(session, provider=MockQuoteProvider())
    latest = session.query(LatestStockQuote).first()
    assert latest is not None
    assert latest.quote_id is not None
    history_row = session.get(StockQuote, latest.quote_id)
    assert history_row is not None
    assert history_row.ticker == latest.ticker
