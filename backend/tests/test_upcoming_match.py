"""Test av UpcomingMatcher: när riktiga transaktioner dyker upp i CSV-import
ska redan planerade UpcomingTransaction-rader markeras som bokförda."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.db.models import Account, Base, Transaction, UpcomingTransaction
from hembudget.upcoming_match import UpcomingMatcher


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _acc(session, name="Gemensamt", bank="nordea", type_="shared"):
    a = Account(name=name, bank=bank, type=type_)
    session.add(a); session.flush()
    return a


def _tx(session, account_id, d, amount, desc):
    t = Transaction(
        account_id=account_id, date=d,
        amount=Decimal(str(amount)), currency="SEK",
        raw_description=desc,
        hash=f"{account_id}-{d}-{amount}-{desc}",
    )
    session.add(t); session.flush()
    return t


def test_matches_bill_by_amount_date_account(session):
    gem = _acc(session)
    up = UpcomingTransaction(
        kind="bill", name="Vattenfall",
        amount=Decimal("1420"), expected_date=date(2026, 4, 30),
        debit_account_id=gem.id,
    )
    session.add(up); session.flush()

    # Riktig transaktion inom fönstret
    tx = _tx(session, gem.id, date(2026, 4, 30), -1420, "Autogiro Vattenfall")

    matched = UpcomingMatcher(session).match([tx])
    assert matched == 1
    session.refresh(up)
    assert up.matched_transaction_id == tx.id


def test_bill_not_matched_on_wrong_account(session):
    gem = _acc(session, "Gemensamt", type_="shared")
    other = _acc(session, "Lönekonto", type_="checking")
    up = UpcomingTransaction(
        kind="bill", name="Vattenfall",
        amount=Decimal("1420"), expected_date=date(2026, 4, 30),
        debit_account_id=gem.id,
    )
    session.add(up); session.flush()

    # Rätt belopp + datum men FEL konto
    tx = _tx(session, other.id, date(2026, 4, 30), -1420, "Autogiro Vattenfall")

    matched = UpcomingMatcher(session).match([tx])
    assert matched == 0


def test_matches_income(session):
    lonekonto = _acc(session, "Lönekonto", type_="checking")
    up = UpcomingTransaction(
        kind="income", name="Inkab",
        amount=Decimal("11357"), expected_date=date(2026, 4, 25),
        debit_account_id=lonekonto.id, owner="Robin",
    )
    session.add(up); session.flush()

    tx = _tx(session, lonekonto.id, date(2026, 4, 25), 11357, "Lön Inkab")
    matched = UpcomingMatcher(session).match([tx])
    assert matched == 1


def test_amount_tolerance(session):
    gem = _acc(session)
    up = UpcomingTransaction(
        kind="bill", name="Vattenfall",
        amount=Decimal("1420"), expected_date=date(2026, 4, 30),
        debit_account_id=gem.id,
    )
    session.add(up); session.flush()
    # 1 kr diff — inom tolerans
    tx = _tx(session, gem.id, date(2026, 4, 30), -1419, "Autogiro")
    matched = UpcomingMatcher(session).match([tx])
    assert matched == 1


def test_already_matched_not_repaired(session):
    gem = _acc(session)
    tx1 = _tx(session, gem.id, date(2026, 4, 30), -1420, "Autogiro 1")
    up = UpcomingTransaction(
        kind="bill", name="Vattenfall",
        amount=Decimal("1420"), expected_date=date(2026, 4, 30),
        debit_account_id=gem.id,
        matched_transaction_id=tx1.id,
    )
    session.add(up); session.flush()

    # En annan kandidat dyker upp — ska ignoreras
    tx2 = _tx(session, gem.id, date(2026, 4, 29), -1420, "Autogiro 2")
    matched = UpcomingMatcher(session).match([tx2])
    assert matched == 0
