"""End-to-end-tester för aktiehandel — buy_stock, sell_stock, get_portfolio.

Använder två separata in-memory engines: en för master (StockMaster,
LatestStockQuote, MarketCalendar) och en för scope (Account, Transaction,
StockHolding, StockTransaction). Trading-funktionerna tar båda
sessions explicit så denna setup speglar produktionsläget.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.db.models import (
    Account,
    Base,
    StockHolding,
    StockTransaction,
    Transaction,
)
from hembudget.school.models import MasterBase
from hembudget.school.stock_models import (
    LatestStockQuote,
    MarketCalendar,
    StockMaster,
)
from hembudget.school.stock_seed import seed_all
from hembudget.stocks.trading import (
    TradeError,
    buy_stock,
    get_portfolio,
    sell_stock,
)


@pytest.fixture()
def master() -> Session:
    engine = create_engine("sqlite:///:memory:")
    MasterBase.metadata.create_all(engine)
    with Session(engine) as s:
        seed_all(s)
        # Force market open today
        today = date.today()
        row = (
            s.query(MarketCalendar).filter(MarketCalendar.calendar_date == today).first()
        )
        if row:
            row.status = "open"
            row.open_time = "00:00"
            row.close_time = "23:59"
            s.flush()
        # Seed quotes manuellt så vi inte beror på MockQuoteProvider
        from datetime import datetime as _dt
        latest_rows = [
            ("VOLV-B.ST", Decimal("250.00")),
            ("ERIC-B.ST", Decimal("75.00")),
            ("HM-B.ST", Decimal("150.00")),
        ]
        for ticker, price in latest_rows:
            s.add(LatestStockQuote(
                ticker=ticker, last=price, ts=_dt.utcnow(),
            ))
        s.flush()
        yield s


@pytest.fixture()
def scope() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _make_isk(scope: Session, *, opening: int = 100_000) -> Account:
    a = Account(
        name="ISK", bank="Demo", type="isk",
        opening_balance=Decimal(opening),
        opening_balance_date=date(2026, 1, 1),
    )
    scope.add(a); scope.flush()
    return a


# --- Köp ---

def test_buy_creates_holding_transaction_and_ledger(scope, master):
    isk = _make_isk(scope)
    r = buy_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="VOLV-B.ST", quantity=10,
    )
    # 10 * 250 = 2500, courtage = max(1, 6.25) = 6.25
    assert r.price == Decimal("250.00")
    assert r.courtage == Decimal("6.25")
    assert r.total_amount == Decimal("2506.25")
    assert r.holding_quantity_after == 10
    assert r.cash_balance_after == Decimal("97493.75")

    # Holding skapad
    h = scope.query(StockHolding).first()
    assert h.ticker == "VOLV-B.ST"
    assert h.quantity == 10
    # avg_cost = total/qty = 250.625
    assert h.avg_cost == Decimal("250.6250")

    # Ledger-rad finns
    st = scope.query(StockTransaction).first()
    assert st.side == "buy"
    assert st.quote_id is None  # Vi seedade utan quote_id i fixturen

    # Cash-transaction skapad
    txs = scope.query(Transaction).all()
    assert len(txs) == 1
    assert txs[0].amount == Decimal("-2506.25")


def test_buy_second_time_updates_avg_cost_weighted(scope, master):
    isk = _make_isk(scope)
    # Första: 10 st @ 250
    buy_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="VOLV-B.ST", quantity=10,
    )
    # Ändra kursen
    latest = master.query(LatestStockQuote).filter(
        LatestStockQuote.ticker == "VOLV-B.ST",
    ).first()
    latest.last = Decimal("300.00")
    master.flush()
    # Andra: 5 st @ 300
    r2 = buy_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="VOLV-B.ST", quantity=5,
    )
    # Total cost = 2506.25 + 1500 + 3.75 (courtage) = 4010.00 / 15 = 267.3333…
    assert r2.holding_quantity_after == 15
    h = scope.query(StockHolding).first()
    assert h.quantity == 15
    # Snittkursen viktad
    expected = Decimal("4010.00") / Decimal("15")
    assert abs(Decimal(h.avg_cost) - expected) < Decimal("0.01")


def test_buy_insufficient_funds_raises(scope, master):
    isk = _make_isk(scope, opening=100)  # bara 100 kr på kontot
    with pytest.raises(TradeError) as exc:
        buy_stock(
            scope_session=scope, master_session=master,
            account_id=isk.id, ticker="VOLV-B.ST", quantity=1,
        )
    assert exc.value.code == "insufficient_funds"


def test_buy_unknown_ticker_raises(scope, master):
    isk = _make_isk(scope)
    with pytest.raises(TradeError) as exc:
        buy_stock(
            scope_session=scope, master_session=master,
            account_id=isk.id, ticker="DOESNOTEXIST", quantity=1,
        )
    assert exc.value.code == "unknown_ticker"


def test_buy_non_isk_account_raises(scope, master):
    a = Account(
        name="Lön", bank="Demo", type="checking",
        opening_balance=Decimal("100000"),
        opening_balance_date=date(2026, 1, 1),
    )
    scope.add(a); scope.flush()
    with pytest.raises(TradeError) as exc:
        buy_stock(
            scope_session=scope, master_session=master,
            account_id=a.id, ticker="VOLV-B.ST", quantity=1,
        )
    assert exc.value.code == "account_wrong_type"


def test_buy_market_closed_raises(scope, master):
    # Stäng marknaden
    today = date.today()
    row = master.query(MarketCalendar).filter(
        MarketCalendar.calendar_date == today,
    ).first()
    row.status = "closed"
    master.flush()

    isk = _make_isk(scope)
    with pytest.raises(TradeError) as exc:
        buy_stock(
            scope_session=scope, master_session=master,
            account_id=isk.id, ticker="VOLV-B.ST", quantity=1,
        )
    assert exc.value.code == "market_closed"


def test_buy_zero_quantity_raises(scope, master):
    isk = _make_isk(scope)
    with pytest.raises(TradeError) as exc:
        buy_stock(
            scope_session=scope, master_session=master,
            account_id=isk.id, ticker="VOLV-B.ST", quantity=0,
        )
    assert exc.value.code == "invalid_quantity"


def test_buy_no_quote_raises(scope, master):
    isk = _make_isk(scope)
    # SAND.ST finns i StockMaster men har ingen LatestStockQuote
    with pytest.raises(TradeError) as exc:
        buy_stock(
            scope_session=scope, master_session=master,
            account_id=isk.id, ticker="SAND.ST", quantity=1,
        )
    assert exc.value.code == "no_quote"


# --- Sälj ---

def test_sell_full_position_removes_holding(scope, master):
    isk = _make_isk(scope)
    buy_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="VOLV-B.ST", quantity=10,
    )
    r = sell_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="VOLV-B.ST", quantity=10,
    )
    # Sålt till samma kurs som köp → vinst = -courtage*2
    assert r.holding_quantity_after == 0
    assert scope.query(StockHolding).count() == 0
    assert r.realized_pnl is not None
    # Köp courtage 6.25, sälj courtage 6.25, så total förlust = -12.50 men
    # realized_pnl räknar på sälj-sidan: (price - avg_cost) * qty - courtage
    # avg_cost = 250.625, sälj = 250.00 → (-0.625 * 10) - 6.25 = -12.50
    assert r.realized_pnl == Decimal("-12.50")


def test_sell_partial_position_keeps_avg_cost(scope, master):
    isk = _make_isk(scope)
    buy_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="VOLV-B.ST", quantity=10,
    )
    r = sell_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="VOLV-B.ST", quantity=4,
    )
    h = scope.query(StockHolding).first()
    assert h.quantity == 6
    # avg_cost ska vara oförändrat
    assert h.avg_cost == Decimal("250.6250")


def test_sell_more_than_held_raises(scope, master):
    isk = _make_isk(scope)
    buy_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="VOLV-B.ST", quantity=5,
    )
    with pytest.raises(TradeError) as exc:
        sell_stock(
            scope_session=scope, master_session=master,
            account_id=isk.id, ticker="VOLV-B.ST", quantity=10,
        )
    assert exc.value.code == "insufficient_holding"


def test_sell_realizes_profit_when_price_up(scope, master):
    isk = _make_isk(scope)
    buy_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="ERIC-B.ST", quantity=20,
    )
    # Kursen går upp till 100
    latest = master.query(LatestStockQuote).filter(
        LatestStockQuote.ticker == "ERIC-B.ST",
    ).first()
    latest.last = Decimal("100.00")
    master.flush()
    r = sell_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="ERIC-B.ST", quantity=20,
    )
    # avg_cost från köp = (1500+3.75)/20 = 75.1875
    # vinst per st = 100 - 75.1875 = 24.8125
    # totalt = 24.8125 * 20 - courtage_sell
    # courtage_sell = max(1, 0.0025*2000) = 5.00
    # realized = 496.25 - 5 = 491.25
    assert r.realized_pnl == Decimal("491.25")


# --- Portfölj ---

def test_portfolio_empty_returns_zero(scope, master):
    isk = _make_isk(scope, opening=10000)
    p = get_portfolio(
        scope_session=scope, master_session=master, account_id=isk.id,
    )
    assert p["holdings"] == []
    assert p["total_market_value"] == 0.0
    assert p["cash_balance"] == 10000.0
    assert p["total_value"] == 10000.0


def test_portfolio_includes_holdings_with_market_value(scope, master):
    isk = _make_isk(scope)
    buy_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="VOLV-B.ST", quantity=10,
    )
    p = get_portfolio(
        scope_session=scope, master_session=master, account_id=isk.id,
    )
    assert len(p["holdings"]) == 1
    h = p["holdings"][0]
    assert h["ticker"] == "VOLV-B.ST"
    assert h["quantity"] == 10
    assert h["market_value"] == 2500.0  # 10 * 250
    assert h["sector"] == "Industri"


def test_portfolio_sector_weights_sum_to_100(scope, master):
    isk = _make_isk(scope)
    buy_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="VOLV-B.ST", quantity=10,
    )
    buy_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="ERIC-B.ST", quantity=10,
    )
    p = get_portfolio(
        scope_session=scope, master_session=master, account_id=isk.id,
    )
    total_weight = sum(p["sector_weights"].values())
    assert abs(total_weight - 100.0) < 0.01


def test_ledger_is_append_only_through_normal_flow(scope, master):
    """Säkerhetstest: efter buy + sell ska 2 rader finnas i StockTransaction
    (ingen modifiering av befintliga rader)."""
    isk = _make_isk(scope)
    r1 = buy_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="VOLV-B.ST", quantity=10,
    )
    r2 = sell_stock(
        scope_session=scope, master_session=master,
        account_id=isk.id, ticker="VOLV-B.ST", quantity=5,
    )
    rows = scope.query(StockTransaction).order_by(StockTransaction.id).all()
    assert len(rows) == 2
    assert rows[0].id == r1.transaction_id
    assert rows[0].side == "buy"
    assert rows[1].id == r2.transaction_id
    assert rows[1].side == "sell"
