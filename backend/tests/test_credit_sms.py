"""Tester för SMS-lån-flödet."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.api.credit import (
    SmsAcceptIn,
    SmsApplyIn,
    sms_accept,
    sms_apply,
)
from hembudget.db.models import (
    Account,
    Base,
    CreditApplication,
    Loan,
    Transaction,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed_with_income(s: Session, *, amount: int = 25_000):
    a = Account(name="Lön", bank="d", type="checking",
                opening_balance=Decimal("0"),
                opening_balance_date=date(2026, 1, 1))
    s.add(a); s.flush()
    today = date.today()
    s.add(Transaction(
        account_id=a.id, date=today - timedelta(days=10),
        amount=Decimal(str(amount)), currency="SEK",
        raw_description="Lön", hash="sal1",
    ))
    s.flush()
    return a.id


def test_sms_apply_approves_when_income_exists(session):
    _seed_with_income(session)
    r = sms_apply(SmsApplyIn(
        requested_amount=Decimal("5000"), requested_months=1,
    ), session)
    assert r.approved is True
    assert r.simulated_lender in {"Klarna Quick", "Bynk", "Cashbuddy", "GF Money"}
    assert r.effective_rate > 0.5  # Mycket högre än privatlån


def test_sms_apply_declines_without_income(session):
    a = Account(name="Lön", bank="d", type="checking")
    session.add(a); session.flush()
    r = sms_apply(SmsApplyIn(
        requested_amount=Decimal("5000"), requested_months=1,
    ), session)
    assert r.approved is False


def test_sms_total_cost_includes_fees(session):
    """5000 kr på 1 mån: ränta + 500 setup + 50 avi = ~5675."""
    _seed_with_income(session)
    r = sms_apply(SmsApplyIn(
        requested_amount=Decimal("5000"), requested_months=1,
    ), session)
    assert r.setup_fee == 500
    assert r.avi_fee_per_month == 50
    # Ränta 30 % årlig × 1/12 × 5000 = 125 kr
    # Total ≈ 5000 + 125 + 500 + 50 = 5675 kr
    assert 5600 < r.total_to_pay < 5700


def test_sms_warning_mentions_effective_rate(session):
    _seed_with_income(session)
    r = sms_apply(SmsApplyIn(
        requested_amount=Decimal("10000"), requested_months=2,
    ), session)
    assert "DYR KREDIT" in r.pedagogical_warning
    assert "Effektiv ränta" in r.pedagogical_warning


def test_sms_accept_creates_loan_with_high_cost_flag(session):
    acc_id = _seed_with_income(session)
    apply_r = sms_apply(SmsApplyIn(
        requested_amount=Decimal("5000"), requested_months=1,
    ), session)
    accept_r = sms_accept(SmsAcceptIn(
        application_id=apply_r.application_id,
        deposit_account_id=acc_id,
    ), session)
    loan = session.get(Loan, accept_r.loan_id)
    assert loan is not None
    assert loan.loan_kind == "sms"
    assert loan.is_high_cost_credit is True
    assert "SMS-lån" in loan.name
    # Pedagogiskt: noten innehåller reflektionsfråga
    assert "Reflektion" in accept_r.pedagogical_note
    assert "buffert" in accept_r.pedagogical_note.lower()


def test_sms_accept_creates_transaction(session):
    acc_id = _seed_with_income(session)
    apply_r = sms_apply(SmsApplyIn(
        requested_amount=Decimal("5000"), requested_months=1,
    ), session)
    accept_r = sms_accept(SmsAcceptIn(
        application_id=apply_r.application_id,
        deposit_account_id=acc_id,
    ), session)
    tx = session.get(Transaction, accept_r.transaction_id)
    assert tx is not None
    assert tx.amount == Decimal("5000")
    assert "SMS-lån" in tx.raw_description


def test_sms_application_audited(session):
    _seed_with_income(session)
    sms_apply(SmsApplyIn(
        requested_amount=Decimal("3000"), requested_months=2,
    ), session)
    apps = session.query(CreditApplication).all()
    assert len(apps) == 1
    assert apps[0].kind == "sms"


def test_sms_double_accept_blocked(session):
    acc_id = _seed_with_income(session)
    apply_r = sms_apply(SmsApplyIn(
        requested_amount=Decimal("5000"), requested_months=1,
    ), session)
    sms_accept(SmsAcceptIn(
        application_id=apply_r.application_id,
        deposit_account_id=acc_id,
    ), session)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        sms_accept(SmsAcceptIn(
            application_id=apply_r.application_id,
            deposit_account_id=acc_id,
        ), session)
    assert exc.value.status_code == 400
