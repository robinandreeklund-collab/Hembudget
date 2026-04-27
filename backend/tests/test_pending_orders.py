"""Tester för PendingOrder-flödet: queue → execute → cancel."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def sessions():
    """Två SQLite-DB:er: master + scope. Mirror prod-strukturen."""
    from hembudget.db.models import Base as ScopeBase
    from hembudget.school.models import MasterBase

    master_engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    scope_engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    MasterBase.metadata.create_all(master_engine)
    ScopeBase.metadata.create_all(scope_engine)

    MS = sessionmaker(bind=master_engine, autoflush=False, expire_on_commit=False)
    SS = sessionmaker(bind=scope_engine, autoflush=False, expire_on_commit=False)
    ms = MS()
    ss = SS()

    # Seed: ett ISK-konto med saldo + en aktie med kurs
    from hembudget.db.models import Account, Transaction
    from hembudget.school.stock_models import (
        LatestStockQuote, MarketCalendar, StockMaster,
    )

    acc = Account(name="ISK", bank="nordea", type="isk", currency="SEK")
    ss.add(acc); ss.flush()
    # Sätt saldo via en deposit-tx
    ss.add(Transaction(
        account_id=acc.id, date=date.today(),
        amount=Decimal("50000"),
        currency="SEK", raw_description="Insättning", hash="seed-deposit",
    ))
    ss.commit()

    ms.add(StockMaster(
        ticker="VOLV-B.ST", name="Volvo B", sector="Industri",
        currency="SEK", exchange="XSTO", active=1,
    ))
    ms.add(LatestStockQuote(
        ticker="VOLV-B.ST", last=Decimal("324"),
        ts=datetime.utcnow(),
    ))
    # Sätt MarketCalendar — open today
    ms.add(MarketCalendar(
        calendar_date=date.today(), exchange="XSTO",
        status="open", open_time="09:00", close_time="17:30",
    ))
    ms.commit()

    yield ss, ms, acc.id
    ss.close(); ms.close()


def test_queue_buy_locks_cash(sessions):
    """Köp-order låser cash + buffer."""
    from hembudget.stocks.orders import _available_cash, queue_order

    ss, ms, acc_id = sessions
    cash_before = _available_cash(ss, acc_id)
    order = queue_order(
        scope_session=ss, master_session=ms,
        account_id=acc_id, ticker="VOLV-B.ST",
        side="buy", quantity=10,
    )
    assert order.status == "pending"
    assert order.quantity == 10
    # 324 * 10 + courtage + 5% buffer ≈ 3413
    assert order.locked_amount > Decimal("3000")
    assert order.locked_amount < Decimal("4000")

    cash_after = _available_cash(ss, acc_id)
    assert cash_after == cash_before - order.locked_amount


def test_queue_buy_blocks_when_insufficient_cash(sessions):
    """Köp som överstiger saldo blockeras."""
    from hembudget.stocks.orders import queue_order
    from hembudget.stocks.trading import TradeError

    ss, ms, acc_id = sessions
    with pytest.raises(TradeError) as exc:
        queue_order(
            scope_session=ss, master_session=ms,
            account_id=acc_id, ticker="VOLV-B.ST",
            side="buy", quantity=10000,  # 3.24 M kr
        )
    assert exc.value.code == "insufficient_funds"


def test_queue_sell_blocks_when_no_holding(sessions):
    """Sälj utan holding blockeras."""
    from hembudget.stocks.orders import queue_order
    from hembudget.stocks.trading import TradeError

    ss, ms, acc_id = sessions
    with pytest.raises(TradeError) as exc:
        queue_order(
            scope_session=ss, master_session=ms,
            account_id=acc_id, ticker="VOLV-B.ST",
            side="sell", quantity=10,
        )
    assert exc.value.code == "insufficient_shares"


def test_cancel_releases_lock(sessions):
    """Avbryt frigör cash-låsningen."""
    from hembudget.stocks.orders import (
        _available_cash, cancel_order, queue_order,
    )

    ss, ms, acc_id = sessions
    cash_before = _available_cash(ss, acc_id)
    order = queue_order(
        scope_session=ss, master_session=ms,
        account_id=acc_id, ticker="VOLV-B.ST",
        side="buy", quantity=5,
    )
    assert _available_cash(ss, acc_id) < cash_before
    cancelled = cancel_order(
        scope_session=ss, account_id=acc_id, order_id=order.id,
    )
    assert cancelled.status == "cancelled"
    assert cancelled.cancel_reason == "user_cancelled"
    # Cash ska vara samma som innan
    assert _available_cash(ss, acc_id) == cash_before


def test_execute_pending_runs_buy(sessions):
    """Pending buy-order utförs när marknaden är öppen."""
    from hembudget.db.models import StockHolding
    from hembudget.stocks.orders import execute_pending_orders, queue_order

    ss, ms, acc_id = sessions
    queue_order(
        scope_session=ss, master_session=ms,
        account_id=acc_id, ticker="VOLV-B.ST",
        side="buy", quantity=5,
    )
    # Mock is_market_open via tid (kalendern säger open 09:00-17:30)
    # Vi använder is_market_open som det är — fixturen seedar dagens
    # datum som 'open' så execution borde fungera om vi är i tids-
    # spannet. För test-stabilitet patcha is_market_open.
    from hembudget.stocks import orders as orders_mod
    orders_mod.is_market_open = lambda *a, **k: True  # type: ignore

    res = execute_pending_orders(scope_session=ss, master_session=ms)
    assert res["executed"] == 1
    assert res["cancelled"] == 0

    # Holding har skapats
    holding = (
        ss.query(StockHolding)
        .filter(StockHolding.ticker == "VOLV-B.ST")
        .first()
    )
    assert holding is not None
    assert holding.quantity == 5
