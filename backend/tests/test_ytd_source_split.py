"""Tester för ytd-split per källa + monthly_summary inkluderar upcomings."""
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
    from hembudget.categorize.rules import seed_categories_and_rules

    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = S()
    seed_categories_and_rules(s)
    s.commit()
    try:
        yield s
    finally:
        s.close()


def test_ytd_splits_from_transactions_and_manual(session):
    """Både Transaction-lön OCH manuell upcoming-lön ska summeras, och
    uppdelningen per källa ska returneras så UI kan visa den."""
    from hembudget.db.models import (
        Account, Category, Transaction, UpcomingTransaction, User,
    )
    from hembudget.chat.tools import ytd_income_by_person

    robin = User(name="Robin")
    session.add(robin); session.flush()
    acc = Account(
        name="Robin lönekonto", bank="nordea", type="checking",
        owner_id=robin.id,
    )
    session.add(acc); session.flush()
    lon = session.query(Category).filter(Category.name == "Lön").one()
    session.add(Transaction(
        account_id=acc.id, date=date(2026, 2, 25),
        amount=Decimal("34500"), currency="SEK",
        raw_description="Inkab", hash="h1",
        category_id=lon.id,
    ))
    # Partner — manuell upcoming utan Transaction
    session.add(UpcomingTransaction(
        kind="income", name="Evelinas jobb",
        amount=Decimal("28000"),
        expected_date=date(2026, 2, 25),
        owner="Evelina",
    ))
    session.commit()

    r = ytd_income_by_person(session, year=2026)
    assert r["grand_total"] == pytest.approx(62500.0)
    assert r["total_from_transactions"] == pytest.approx(34500.0)
    assert r["total_from_manual"] == pytest.approx(28000.0)

    # Per owner
    robin_bucket = r["by_owner"][f"user_{robin.id}"]
    assert robin_bucket["from_transactions"] == pytest.approx(34500.0)
    assert robin_bucket["from_manual"] == pytest.approx(0.0)

    eve_bucket = r["by_owner"]["Evelina"]
    assert eve_bucket["from_manual"] == pytest.approx(28000.0)
    assert eve_bucket["from_transactions"] == pytest.approx(0.0)


def test_monthly_summary_includes_unmatched_income_upcomings(session):
    """Januari har 34 500 i Transaction-lön + 28 000 i omatchad upcoming
    (partnerns). Month summary ska visa income = 62 500."""
    from hembudget.db.models import (
        Account, Category, Transaction, UpcomingTransaction,
    )
    from hembudget.budget.monthly import MonthlyBudgetService

    acc = Account(name="A", bank="nordea", type="checking")
    session.add(acc); session.flush()
    lon = session.query(Category).filter(Category.name == "Lön").one()
    session.add(Transaction(
        account_id=acc.id, date=date(2026, 1, 25),
        amount=Decimal("34500"), currency="SEK",
        raw_description="Inkab", hash="h1",
        category_id=lon.id,
    ))
    session.add(UpcomingTransaction(
        kind="income", name="Partnerns lön",
        amount=Decimal("28000"),
        expected_date=date(2026, 1, 27),
        owner="Evelina",
    ))
    session.commit()

    svc = MonthlyBudgetService(session)
    summary = svc.summary("2026-01")
    assert float(summary.income) == pytest.approx(62500.0)


def test_monthly_summary_includes_unmatched_bill_upcomings(session):
    """Manuell bill med passerat datum ska räknas som utgift för
    månaden, även utan en matchad Transaction."""
    from hembudget.db.models import UpcomingTransaction
    from hembudget.budget.monthly import MonthlyBudgetService

    session.add(UpcomingTransaction(
        kind="bill", name="Manuell faktura",
        amount=Decimal("1500"),
        expected_date=date(2026, 3, 27),
    ))
    session.commit()

    svc = MonthlyBudgetService(session)
    summary = svc.summary("2026-03")
    assert float(summary.expenses) == pytest.approx(1500.0)


def test_monthly_summary_matched_upcoming_not_double_counted(session):
    """En matchad upcoming ska INTE dubbelräknas — Transaction är källan."""
    from hembudget.db.models import Account, Transaction, UpcomingTransaction
    from hembudget.budget.monthly import MonthlyBudgetService

    acc = Account(name="A", bank="nordea", type="checking")
    session.add(acc); session.flush()
    tx = Transaction(
        account_id=acc.id, date=date(2026, 1, 25),
        amount=Decimal("34500"), currency="SEK",
        raw_description="Inkab", hash="h1",
    )
    session.add(tx); session.flush()
    session.add(UpcomingTransaction(
        kind="income", name="Inkab",
        amount=Decimal("34500"),
        expected_date=date(2026, 1, 25),
        matched_transaction_id=tx.id,
    ))
    session.commit()

    svc = MonthlyBudgetService(session)
    summary = svc.summary("2026-01")
    # Bara EN räkning, från Transaction
    assert float(summary.income) == pytest.approx(34500.0)
