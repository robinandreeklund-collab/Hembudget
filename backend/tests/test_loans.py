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


def test_schedule_matches_exact_amount_and_close_date(session):
    """Schema-raden ska para ihop en transaktion vars belopp är exakt
    och datum nära (±5 dagar), oavsett om match_pattern saknas."""
    from hembudget.db.models import LoanScheduleEntry, LoanPayment

    acc = _acc(session)
    loan = Loan(
        name="Bolån", lender="SBAB", principal_amount=Decimal("2500000"),
        start_date=date(2024, 1, 1), interest_rate=0.042,
        # INGEN match_pattern — bevisar att schemat räcker
    )
    session.add(loan); session.flush()
    entry = LoanScheduleEntry(
        loan_id=loan.id, due_date=date(2026, 3, 25),
        amount=Decimal("8750.00"), payment_type="interest",
    )
    session.add(entry); session.flush()

    # Transaktion kommer 3 dagar senare, exakt belopp (±1 kr)
    tx = _tx(session, acc.id, date(2026, 3, 28), -8750.50, "Obskyr bank-text")

    r = LoanMatcher(session).match_and_classify([tx])
    assert r.matched_via_schedule == 1
    assert r.matched_via_pattern == 0
    session.refresh(entry)
    assert entry.matched_transaction_id == tx.id

    # Ett LoanPayment har skapats
    payments = session.query(LoanPayment).filter_by(loan_id=loan.id).all()
    assert len(payments) == 1
    assert payments[0].payment_type == "interest"


def test_schedule_beats_pattern_when_both_match(session):
    """När både schema OCH pattern matchar samma transaktion ska
    schema-raden vinna (mer pålitligt) och inte dubbelräkna."""
    from hembudget.db.models import LoanScheduleEntry, LoanPayment

    acc = _acc(session)
    loan = Loan(
        name="Bolån", lender="SBAB", principal_amount=Decimal("2500000"),
        start_date=date(2024, 1, 1), interest_rate=0.042,
        match_pattern="SBAB",
    )
    session.add(loan); session.flush()
    session.add(LoanScheduleEntry(
        loan_id=loan.id, due_date=date(2026, 3, 25),
        amount=Decimal("5000"), payment_type="amortization",
    ))
    session.flush()

    tx = _tx(session, acc.id, date(2026, 3, 25), -5000, "Amortering SBAB")
    r = LoanMatcher(session).match_and_classify([tx])

    assert r.linked == 1
    assert r.matched_via_schedule == 1
    assert r.matched_via_pattern == 0
    assert session.query(LoanPayment).count() == 1


def test_schedule_rejects_wrong_amount_or_far_date(session):
    from hembudget.db.models import LoanScheduleEntry

    acc = _acc(session)
    loan = Loan(
        name="Bolån", lender="SBAB", principal_amount=Decimal("2500000"),
        start_date=date(2024, 1, 1), interest_rate=0.042,
    )
    session.add(loan); session.flush()
    session.add(LoanScheduleEntry(
        loan_id=loan.id, due_date=date(2026, 3, 25),
        amount=Decimal("8750"), payment_type="interest",
    ))
    session.flush()

    # Fel belopp
    tx1 = _tx(session, acc.id, date(2026, 3, 25), -9000, "x")
    # För långt bort i tid
    tx2 = _tx(session, acc.id, date(2026, 4, 15), -8750, "x")

    r = LoanMatcher(session).match_and_classify([tx1, tx2])
    assert r.matched_via_schedule == 0


def test_generate_schedule_creates_entries(session):
    acc = _acc(session)
    loan = Loan(
        name="Bolån", lender="SBAB", principal_amount=Decimal("2500000"),
        start_date=date(2024, 1, 1), interest_rate=0.042,
        amortization_monthly=Decimal("5000"),
    )
    session.add(loan); session.flush()

    entries = LoanMatcher(session).generate_schedule(loan, months=3, day_of_month=25)

    # 3 månader × 2 typer = 6 rader (ränta + amortering per månad)
    assert len(entries) == 6
    amort_entries = [e for e in entries if e.payment_type == "amortization"]
    interest_entries = [e for e in entries if e.payment_type == "interest"]
    assert len(amort_entries) == 3
    assert len(interest_entries) == 3
    # Amorteringsbeloppet ska vara exakt det användaren angivit
    assert all(e.amount == Decimal("5000") for e in amort_entries)
    # Räntan ska minska över tid (eftersom amort drar ner saldot)
    interest_amounts = [e.amount for e in sorted(interest_entries, key=lambda e: e.due_date)]
    assert interest_amounts[0] > interest_amounts[1] > interest_amounts[2]


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
