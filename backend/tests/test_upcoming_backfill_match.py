"""Tester för backfill_match — matcha upcoming mot redan befintliga
transaktioner (för när gamla fakturor läses in retroaktivt).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def session():
    from hembudget.db.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False,
    )
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _make_account(s, name="Lön"):
    from hembudget.db.models import Account
    a = Account(name=name, bank="nordea", type="checking")
    s.add(a); s.flush()
    return a


def _make_tx(s, account_id, d, amount, desc="bg-betalning"):
    from hembudget.db.models import Transaction
    t = Transaction(
        account_id=account_id, date=d, amount=Decimal(str(amount)),
        currency="SEK", raw_description=desc, hash=f"h-{d}-{amount}",
    )
    s.add(t); s.flush()
    return t


def test_backfill_match_pairs_existing_transaction(session):
    from hembudget.db.models import UpcomingTransaction
    from hembudget.upcoming_match import UpcomingMatcher

    acc = _make_account(session)
    # Befintlig bankrad: Amex-faktura redan betald 2026-02-27
    tx = _make_tx(session, acc.id, date(2026, 2, 27), -13445.08)
    session.commit()

    up = UpcomingTransaction(
        kind="bill", name="Kreditkortsfaktura — Amex",
        amount=Decimal("13445.08"),
        expected_date=date(2026, 2, 27),
        debit_date=date(2026, 2, 27),
        debit_account_id=acc.id,
        source="pdf_parser",
    )
    session.add(up); session.flush()

    matched = UpcomingMatcher(session).backfill_match([up])
    assert matched == 1
    assert up.matched_transaction_id == tx.id


def test_backfill_match_respects_date_tolerance(session):
    from hembudget.db.models import UpcomingTransaction
    from hembudget.upcoming_match import UpcomingMatcher

    acc = _make_account(session)
    # Bankrad 10 dagar FÖRE due_date → utanför default-tolerans (5 dagar)
    _make_tx(session, acc.id, date(2026, 2, 15), -13445.08)
    session.commit()

    up = UpcomingTransaction(
        kind="bill", name="Amex",
        amount=Decimal("13445.08"),
        expected_date=date(2026, 2, 27),
        debit_date=date(2026, 2, 27),
        debit_account_id=acc.id,
        source="pdf_parser",
    )
    session.add(up); session.flush()

    matched = UpcomingMatcher(session).backfill_match([up])
    assert matched == 0
    assert up.matched_transaction_id is None


def test_backfill_match_respects_amount_tolerance(session):
    from hembudget.db.models import UpcomingTransaction
    from hembudget.upcoming_match import UpcomingMatcher

    acc = _make_account(session)
    # 10 kr off → utanför tolerans (1 kr)
    _make_tx(session, acc.id, date(2026, 2, 27), -13455.00)
    session.commit()

    up = UpcomingTransaction(
        kind="bill", name="Amex",
        amount=Decimal("13445.08"),
        expected_date=date(2026, 2, 27),
        debit_account_id=acc.id,
        source="pdf_parser",
    )
    session.add(up); session.flush()

    matched = UpcomingMatcher(session).backfill_match([up])
    assert matched == 0


def test_backfill_picks_closest_date_when_multiple(session):
    from hembudget.db.models import UpcomingTransaction
    from hembudget.upcoming_match import UpcomingMatcher

    acc = _make_account(session)
    tx_early = _make_tx(session, acc.id, date(2026, 2, 24), -100)
    tx_exact = _make_tx(session, acc.id, date(2026, 2, 27), -100)
    session.commit()

    up = UpcomingTransaction(
        kind="bill", name="Räkning", amount=Decimal("100"),
        expected_date=date(2026, 2, 27),
        debit_account_id=acc.id,
        source="manual",
    )
    session.add(up); session.flush()

    UpcomingMatcher(session).backfill_match([up])
    assert up.matched_transaction_id == tx_exact.id
    # Bara för tydlighet
    assert tx_early.id != tx_exact.id


def test_backfill_doesnt_steal_already_matched_tx(session):
    """Om en Transaction redan är länkad till en annan Upcoming ska den
    inte kunna matchas igen."""
    from hembudget.db.models import UpcomingTransaction
    from hembudget.upcoming_match import UpcomingMatcher

    acc = _make_account(session)
    tx = _make_tx(session, acc.id, date(2026, 2, 27), -100)
    # Första upcoming äger tx:en
    up1 = UpcomingTransaction(
        kind="bill", name="A", amount=Decimal("100"),
        expected_date=date(2026, 2, 27),
        debit_account_id=acc.id, matched_transaction_id=tx.id,
        source="manual",
    )
    session.add(up1); session.flush()

    # Ny upcoming med identiska detaljer
    up2 = UpcomingTransaction(
        kind="bill", name="B", amount=Decimal("100"),
        expected_date=date(2026, 2, 27),
        debit_account_id=acc.id, source="manual",
    )
    session.add(up2); session.flush()

    matched = UpcomingMatcher(session).backfill_match([up2])
    assert matched == 0
    assert up2.matched_transaction_id is None


def test_backfill_without_arg_processes_all_open(session):
    from hembudget.db.models import UpcomingTransaction
    from hembudget.upcoming_match import UpcomingMatcher

    acc = _make_account(session)
    _make_tx(session, acc.id, date(2026, 2, 27), -100)
    _make_tx(session, acc.id, date(2026, 3, 27), -250)
    session.commit()

    for d, amt in [(date(2026, 2, 27), 100), (date(2026, 3, 27), 250)]:
        session.add(UpcomingTransaction(
            kind="bill", name=f"F {d}",
            amount=Decimal(str(amt)),
            expected_date=d,
            debit_account_id=acc.id,
            source="manual",
        ))
    session.flush()

    matched = UpcomingMatcher(session).backfill_match()
    assert matched == 2
