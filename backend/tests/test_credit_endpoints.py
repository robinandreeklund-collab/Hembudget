"""End-to-end-tester för /credit/private/* endpoints."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.api.credit import (
    DeclineIn,
    PrivateLoanAcceptIn,
    PrivateLoanApplyIn,
    list_applications,
    private_accept,
    private_apply,
    private_decline,
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


def _seed_good_economy(s: Session) -> int:
    """Bra-ekonomi-elev → ska godkännas."""
    a = Account(
        name="Lön", bank="d", type="checking",
        opening_balance=Decimal("5000"),
        opening_balance_date=date(2026, 1, 1),
    )
    sav = Account(
        name="Spar", bank="d", type="savings",
        opening_balance=Decimal("30000"),
        opening_balance_date=date(2026, 1, 1),
    )
    s.add_all([a, sav]); s.flush()
    today = date.today()
    for m in range(3):
        s.add(Transaction(
            account_id=a.id, date=today - timedelta(days=30 * m),
            amount=Decimal("32000"), currency="SEK",
            raw_description=f"Lön {m}", hash=f"sal-{m}",
        ))
    s.flush()
    return a.id


def _seed_bad_economy(s: Session) -> int:
    """Dålig ekonomi → ska avslås."""
    a = Account(name="Lön", bank="d", type="checking")
    s.add(a); s.flush()
    s.add(Loan(
        name="Bolån", lender="SBAB",
        principal_amount=Decimal("3_500_000"),
        start_date=date(2020, 1, 1), interest_rate=0.04,
        loan_kind="mortgage", active=True,
    ))
    s.flush()
    return a.id


def test_apply_approved_returns_offer(session):
    _seed_good_economy(session)
    payload = PrivateLoanApplyIn(
        requested_amount=Decimal("20000"),
        requested_months=24,
        purpose="Oförutsedda utgifter",
    )
    r = private_apply(payload, session)
    assert r.approved is True
    assert r.offered_rate is not None
    assert r.offered_monthly_payment is not None
    assert r.offered_total_cost is not None
    assert "godkänt" in r.pedagogical_summary.lower() or "godkänd" in r.pedagogical_summary.lower()


def test_apply_creates_audit_row(session):
    _seed_good_economy(session)
    payload = PrivateLoanApplyIn(
        requested_amount=Decimal("10000"), requested_months=12,
    )
    private_apply(payload, session)
    rows = session.query(CreditApplication).all()
    assert len(rows) == 1
    assert rows[0].kind == "private"
    assert rows[0].requested_amount == Decimal("10000")


def test_apply_declined_has_reason(session):
    _seed_bad_economy(session)
    payload = PrivateLoanApplyIn(
        requested_amount=Decimal("100000"), requested_months=60,
    )
    r = private_apply(payload, session)
    assert r.approved is False
    assert r.decline_reason is not None
    assert r.offered_rate is None


def test_apply_factors_have_explanations(session):
    _seed_good_economy(session)
    payload = PrivateLoanApplyIn(
        requested_amount=Decimal("20000"), requested_months=24,
    )
    r = private_apply(payload, session)
    assert len(r.factors) >= 4
    for f in r.factors:
        assert len(f.explanation) > 20


def test_accept_creates_loan_and_transaction(session):
    acc_id = _seed_good_economy(session)
    apply_payload = PrivateLoanApplyIn(
        requested_amount=Decimal("20000"), requested_months=24,
    )
    apply_result = private_apply(apply_payload, session)
    assert apply_result.approved is True

    accept = PrivateLoanAcceptIn(
        application_id=apply_result.application_id,
        deposit_account_id=acc_id,
    )
    r = private_accept(accept, session)
    # Loan finns
    loan = session.get(Loan, r.loan_id)
    assert loan is not None
    assert loan.loan_kind == "private"
    assert loan.is_high_cost_credit is False
    assert loan.principal_amount == Decimal("20000")
    # Transaction skapad
    tx = session.get(Transaction, r.transaction_id)
    assert tx is not None
    assert tx.amount == Decimal("20000")
    # Application uppdaterad
    app = session.query(CreditApplication).first()
    assert app.result == "accepted"
    assert app.resulting_loan_id == loan.id
    # Pedagogisk note finns
    assert "ränta" in r.pedagogical_note.lower()


def test_accept_rejects_unapproved(session):
    _seed_bad_economy(session)
    apply_payload = PrivateLoanApplyIn(
        requested_amount=Decimal("100000"), requested_months=60,
    )
    apply_result = private_apply(apply_payload, session)
    assert apply_result.approved is False

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        private_accept(
            PrivateLoanAcceptIn(
                application_id=apply_result.application_id,
                deposit_account_id=1,
            ),
            session,
        )
    assert exc.value.status_code == 400


def test_accept_rejects_double_accept(session):
    acc_id = _seed_good_economy(session)
    apply_result = private_apply(
        PrivateLoanApplyIn(requested_amount=Decimal("10000"), requested_months=12),
        session,
    )
    private_accept(
        PrivateLoanAcceptIn(
            application_id=apply_result.application_id,
            deposit_account_id=acc_id,
        ),
        session,
    )
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        private_accept(
            PrivateLoanAcceptIn(
                application_id=apply_result.application_id,
                deposit_account_id=acc_id,
            ),
            session,
        )
    assert exc.value.status_code == 400


def test_decline_marks_rejected(session):
    _seed_good_economy(session)
    apply_result = private_apply(
        PrivateLoanApplyIn(requested_amount=Decimal("10000"), requested_months=12),
        session,
    )
    r = private_decline(DeclineIn(application_id=apply_result.application_id), session)
    assert r["result"] == "rejected"


def test_list_applications(session):
    _seed_good_economy(session)
    private_apply(
        PrivateLoanApplyIn(requested_amount=Decimal("10000"), requested_months=12),
        session,
    )
    private_apply(
        PrivateLoanApplyIn(requested_amount=Decimal("50000"), requested_months=36),
        session,
    )
    r = list_applications(session)
    assert r["count"] == 2
    assert all(a["kind"] == "private" for a in r["applications"])
