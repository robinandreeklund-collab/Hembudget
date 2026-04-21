"""Test av UpcomingMaterializer — automatisk materialisering av
kommande fakturor från lånescheman och prenumerationer."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.db.models import (
    Account,
    Base,
    Category,
    Loan,
    LoanScheduleEntry,
    Subscription,
    UpcomingTransaction,
)
from hembudget.upcoming_match.materializer import (
    LOAN_SOURCE,
    SUB_SOURCE,
    UpcomingMaterializer,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _loan(s, name="Bolån"):
    loan = Loan(
        name=name, lender="Nordea",
        principal_amount=Decimal("2000000"),
        start_date=date(2020, 1, 1), interest_rate=0.04,
    )
    s.add(loan); s.flush()
    return loan


def test_materializes_loan_schedule_future_only(session):
    loan = _loan(session)
    today = date.today()
    # En historisk + en framtida rad
    session.add_all([
        LoanScheduleEntry(
            loan_id=loan.id, due_date=today - timedelta(days=30),
            amount=Decimal("7000"), payment_type="interest",
        ),
        LoanScheduleEntry(
            loan_id=loan.id, due_date=today + timedelta(days=15),
            amount=Decimal("7000"), payment_type="interest",
        ),
    ])
    session.flush()

    result = UpcomingMaterializer(session, horizon_days=60).run()
    assert result.loan_upcoming_created == 1
    ups = session.query(UpcomingTransaction).all()
    assert len(ups) == 1
    assert ups[0].source == LOAN_SOURCE
    assert ups[0].expected_date == today + timedelta(days=15)
    assert ups[0].autogiro is True


def test_merges_interest_and_amortization_same_due_date(session):
    loan = _loan(session)
    today = date.today()
    due = today + timedelta(days=10)
    session.add_all([
        LoanScheduleEntry(
            loan_id=loan.id, due_date=due,
            amount=Decimal("7000"), payment_type="interest",
        ),
        LoanScheduleEntry(
            loan_id=loan.id, due_date=due,
            amount=Decimal("3000"), payment_type="amortization",
        ),
    ])
    session.flush()

    UpcomingMaterializer(session).run()
    ups = session.query(UpcomingTransaction).all()
    assert len(ups) == 1
    assert ups[0].amount == Decimal("10000")
    assert "interest + amortization" in ups[0].name or "amortization + interest" in ups[0].name


def test_skips_already_matched_schedule_entries(session):
    loan = _loan(session)
    today = date.today()
    session.add(LoanScheduleEntry(
        loan_id=loan.id, due_date=today + timedelta(days=10),
        amount=Decimal("7000"), payment_type="interest",
        matched_transaction_id=1,  # redan matchad
    ))
    session.flush()

    result = UpcomingMaterializer(session).run()
    assert result.loan_upcoming_created == 0


def test_loan_materialization_idempotent(session):
    loan = _loan(session)
    today = date.today()
    session.add(LoanScheduleEntry(
        loan_id=loan.id, due_date=today + timedelta(days=10),
        amount=Decimal("7000"), payment_type="interest",
    ))
    session.flush()

    r1 = UpcomingMaterializer(session).run()
    r2 = UpcomingMaterializer(session).run()
    assert r1.loan_upcoming_created == 1
    assert r2.loan_upcoming_created == 0
    assert r2.skipped_existing == 1
    assert session.query(UpcomingTransaction).count() == 1


def test_materializes_subscription_next_cycles(session):
    """Spotify som dras 15:e varje månad — 3 cycles inom horisonten."""
    today = date.today()
    acc = Account(name="Lön", bank="nordea", type="checking")
    cat = Category(name="Prenumerationer")
    session.add_all([acc, cat]); session.flush()

    sub = Subscription(
        merchant="Spotify", amount=Decimal("139"),
        interval_days=30, next_expected_date=today + timedelta(days=5),
        account_id=acc.id, category_id=cat.id,
    )
    session.add(sub); session.flush()

    # horizon_days=90 → borde rulla ut cirka 3 cycles
    result = UpcomingMaterializer(session, horizon_days=90).run()
    assert result.sub_upcoming_created >= 3
    ups = session.query(UpcomingTransaction).filter(
        UpcomingTransaction.source == SUB_SOURCE
    ).all()
    assert all(u.name == "Spotify" for u in ups)
    assert all(u.amount == Decimal("139") for u in ups)
    assert all(u.autogiro for u in ups)
    assert all(u.category_id == cat.id for u in ups)


def test_subscription_materialization_is_idempotent(session):
    today = date.today()
    sub = Subscription(
        merchant="Netflix", amount=Decimal("129"),
        interval_days=30, next_expected_date=today + timedelta(days=5),
    )
    session.add(sub); session.flush()

    r1 = UpcomingMaterializer(session, horizon_days=30).run()
    r2 = UpcomingMaterializer(session, horizon_days=30).run()
    assert r1.sub_upcoming_created == r2.skipped_existing
    assert r2.sub_upcoming_created == 0


def test_inactive_subscriptions_skipped(session):
    today = date.today()
    sub = Subscription(
        merchant="Gammal prenumeration", amount=Decimal("99"),
        interval_days=30, next_expected_date=today + timedelta(days=5),
        active=False,
    )
    session.add(sub); session.flush()

    result = UpcomingMaterializer(session, horizon_days=90).run()
    assert result.sub_upcoming_created == 0


def test_empty_sources_returns_zero(session):
    result = UpcomingMaterializer(session).run()
    assert result.loan_upcoming_created == 0
    assert result.sub_upcoming_created == 0
    assert result.skipped_existing == 0
