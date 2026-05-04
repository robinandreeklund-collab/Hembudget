"""Tester för kreditscoring-motorn — verifierar att avslag/godkännande
hänger ihop med faktorerna och att förklaringarna är pedagogiska."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.credit.scoring import (
    annuity_monthly_payment,
    calculate_credit_score,
)
from hembudget.db.models import Account, Base, Loan, Transaction


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _add_salary(s, account_id, *, amount=25_000, months=3):
    """Lägg till N månaders lön på checking-konto."""
    today = date.today()
    for m in range(months):
        s.add(Transaction(
            account_id=account_id, date=today - timedelta(days=30 * m),
            amount=Decimal(str(amount)), currency="SEK",
            raw_description=f"Lön {m}", hash=f"sal-{account_id}-{m}",
        ))
    s.flush()


def test_no_income_means_low_score(session):
    s = session
    s.add(Account(name="Lön", bank="d", type="checking"))
    s.flush()
    r = calculate_credit_score(
        s, requested_amount=Decimal("10000"), requested_months=24,
    )
    assert r.score < 600
    inc = next(f for f in r.factors if f.name == "Inkomst")
    assert inc.points < 0
    assert "ingen lön" in inc.explanation.lower() or "regelbunden" in inc.explanation.lower()


def test_good_income_pushes_score_up(session):
    s = session
    a = Account(name="Lön", bank="d", type="checking")
    s.add(a); s.flush()
    _add_salary(s, a.id, amount=30_000, months=3)
    r = calculate_credit_score(
        s, requested_amount=Decimal("10000"), requested_months=24,
    )
    inc = next(f for f in r.factors if f.name == "Inkomst")
    assert inc.points >= 10


def test_high_debt_ratio_blocks_approval(session):
    s = session
    a = Account(name="Lön", bank="d", type="checking")
    s.add(a); s.flush()
    _add_salary(s, a.id, amount=20_000, months=3)
    # Stort befintligt lån — 6x årsinkomsten
    s.add(Loan(
        name="Bolån", lender="SBAB",
        principal_amount=Decimal("1_500_000"),
        start_date=date(2020, 1, 1), interest_rate=0.04,
        loan_kind="mortgage", active=True,
    ))
    s.flush()
    r = calculate_credit_score(
        s, requested_amount=Decimal("100_000"), requested_months=60,
    )
    debt = next(f for f in r.factors if f.name == "Skuldkvot")
    assert debt.points <= -30


def test_approved_score_offers_rate(session):
    s = session
    a = Account(name="Lön", bank="d", type="checking",
                opening_balance=Decimal("0"))
    sav = Account(name="Spar", bank="d", type="savings",
                  opening_balance=Decimal("30000"))
    s.add_all([a, sav]); s.flush()
    _add_salary(s, a.id, amount=35_000, months=3)
    r = calculate_credit_score(
        s, requested_amount=Decimal("20000"), requested_months=24,
    )
    assert r.approved is True
    assert r.offered_rate in (0.04, 0.065, 0.09)


def test_declined_has_pedagogical_reason(session):
    s = session
    a = Account(name="Lön", bank="d", type="checking")
    s.add(a); s.flush()
    # Ingen lön + stort lån
    s.add(Loan(
        name="Bolån", lender="SBAB",
        principal_amount=Decimal("3_000_000"),
        start_date=date(2020, 1, 1), interest_rate=0.04,
        loan_kind="mortgage", active=True,
    ))
    s.flush()
    r = calculate_credit_score(
        s, requested_amount=Decimal("50000"), requested_months=36,
    )
    assert r.approved is False
    assert r.decline_reason is not None
    # Bör innehålla "Inkomst" eller "Skuldkvot" som värsta faktor
    assert any(name in r.decline_reason for name in ["Inkomst", "Skuldkvot"])


def test_lender_is_deterministic_per_seed(session):
    s = session
    a = Account(name="Lön", bank="d", type="checking")
    s.add(a); s.flush()
    _add_salary(s, a.id, amount=25_000, months=3)
    r1 = calculate_credit_score(
        s, requested_amount=Decimal("10000"),
        requested_months=24, student_seed=42,
    )
    r2 = calculate_credit_score(
        s, requested_amount=Decimal("10000"),
        requested_months=24, student_seed=42,
    )
    assert r1.simulated_lender == r2.simulated_lender


def test_factors_include_explanations(session):
    s = session
    a = Account(name="Lön", bank="d", type="checking")
    s.add(a); s.flush()
    _add_salary(s, a.id, amount=25_000, months=3)
    r = calculate_credit_score(
        s, requested_amount=Decimal("10000"), requested_months=24,
    )
    # Alla synliga faktorer ska ha explanation
    for f in r.factors:
        assert len(f.explanation) > 20
        assert isinstance(f.points, int)


def test_annuity_payment_correct():
    """100 000 kr på 24 mån @ 6 % → ~4 432 kr/mån."""
    p = annuity_monthly_payment(Decimal("100000"), 0.06, 24)
    # Tolerera ±5 kr
    assert Decimal("4427") < p < Decimal("4437")


def test_annuity_zero_rate_is_division():
    """0 % ränta → bara division."""
    p = annuity_monthly_payment(Decimal("12000"), 0.0, 12)
    assert p == Decimal("1000.00")
