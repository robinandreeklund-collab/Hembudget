from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.categorize.rules import seed_categories_and_rules
from hembudget.db.models import Account, Base, Loan, Transaction
from hembudget.loans.matcher import LoanMatcher, classify_payment


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_categories_and_rules(s)
        yield s


def _acc(session, name="Lönekonto", type_="checking"):
    a = Account(name=name, bank="nordea", type=type_)
    session.add(a); session.flush()
    return a


def _tx(session, acc_id, d, amount, desc):
    t = Transaction(
        account_id=acc_id, date=d, amount=Decimal(str(amount)),
        currency="SEK", raw_description=desc, hash=f"{acc_id}-{d}-{amount}-{desc}",
    )
    session.add(t); session.flush()
    return t


def test_classify_payment_keywords():
    assert classify_payment("Bolåneränta SBAB") == "interest"
    assert classify_payment("Amortering SBAB") == "amortization"
    assert classify_payment("Räntebetalning") == "interest"
    assert classify_payment("Bolån SBAB") is None   # otydlig


def test_matcher_links_interest_and_amort(session):
    acc = _acc(session)
    loan = Loan(
        name="Bostadslån", lender="SBAB", principal_amount=Decimal("2500000"),
        start_date=date(2024, 1, 1), interest_rate=0.042,
        match_pattern="SBAB",
    )
    session.add(loan); session.flush()

    ranta = _tx(session, acc.id, date(2026, 3, 25), -8500, "Bolåneränta SBAB")
    amort = _tx(session, acc.id, date(2026, 3, 25), -5000, "Amortering SBAB")
    ica = _tx(session, acc.id, date(2026, 3, 25), -500, "ICA MAXI")

    r = LoanMatcher(session).match_and_classify([ranta, amort, ica])
    assert r.linked == 2
    assert r.unclassified == 0

    m = LoanMatcher(session)
    assert m.outstanding_balance(loan) == Decimal("2495000.00")
    assert m.total_interest_paid(loan) == Decimal("8500.00")


def test_matcher_unclassified_counts(session):
    acc = _acc(session)
    loan = Loan(
        name="Bolån", lender="SEB", principal_amount=Decimal("1000000"),
        start_date=date(2024, 1, 1), interest_rate=0.04,
        match_pattern="SEB BOLÅN",
    )
    session.add(loan); session.flush()

    tx = _tx(session, acc.id, date(2026, 3, 25), -12000, "SEB BOLÅN")
    r = LoanMatcher(session).match_and_classify([tx])
    assert r.linked == 0
    assert r.unclassified == 1
