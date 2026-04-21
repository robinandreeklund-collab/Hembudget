"""Test: lånevision deriverar amortering korrekt från remaining_balance-delta
när banken inte visar amortering separat per schemarad (t.ex. Nordeas
'Betalningsplan'-vy)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.api.loans import _derive_interest_rate, _split_schedule_row
from hembudget.db.models import (
    Base,
    Loan,
    LoanPayment,
    LoanScheduleEntry,
)
from hembudget.loans.matcher import LoanMatcher


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# --- _split_schedule_row unit tests ---

def test_split_uses_explicit_amort_if_present():
    amort, interest = _split_schedule_row(
        total=4459, amort_explicit=2700,
        prev_remaining=None, this_remaining=None,
    )
    assert amort == 2700
    assert interest == 1759  # 4459 - 2700


def test_split_derives_from_remaining_delta():
    """Nordeas Betalningsplan: total=4640, remaining går från 734600→731900."""
    amort, interest = _split_schedule_row(
        total=4640, amort_explicit=None,
        prev_remaining=734600, this_remaining=731900,
    )
    assert amort == 2700.0
    assert interest == 1940.0


def test_split_falls_back_to_all_interest():
    """Utan amort och utan remaining → antaganden: hela beloppet är ränta."""
    amort, interest = _split_schedule_row(4640, None, None, None)
    assert amort == 0.0
    assert interest == 4640.0


def test_split_handles_zero_amort_explicit():
    """amort=0 räknas som att amort-värdet inte är tillförlitligt, så
    delta-logiken tar över om den går."""
    amort, interest = _split_schedule_row(
        total=4640, amort_explicit=0,
        prev_remaining=734600, this_remaining=731900,
    )
    assert amort == 2700.0
    assert interest == 1940.0


# --- _derive_interest_rate ---

def test_derive_rate_from_realistic_nordea_schedule():
    """Data från Nordea-skärmdumpen:
    - current_balance = 734 600
    - 2026-04-27: 4640, remaining 731 900 → amort 2700, ränta 1940
    - 2026-05-27: 4571, remaining 729 200 → amort 2700, ränta 1871
    - 2026-06-27: 4626, remaining 726 500 → amort 2700, ränta 1926
    Snitt-ränta per månad ≈ 1912. Årsränta = 1912*12/734600 ≈ 3.12%."""
    schedule = [
        {"due_date": "2026-04-27", "total_amount": 4640, "remaining_balance_after": 731900},
        {"due_date": "2026-05-27", "total_amount": 4571, "remaining_balance_after": 729200},
        {"due_date": "2026-06-27", "total_amount": 4626, "remaining_balance_after": 726500},
    ]
    rate = _derive_interest_rate(schedule, current_balance=734600)
    # Godkänn 3.00%-3.20% (avrundningar)
    assert 0.030 <= rate <= 0.032


def test_derive_rate_without_remaining_falls_back_too_high():
    """Om banken inte visar remaining → hela beloppet räknas som ränta →
    räntan blir orealistiskt hög. Det här är dokumenterat beteende:
    systemet kan inte derivera rätt utan delta-data, men kraschar inte."""
    schedule = [
        {"due_date": "2026-04-27", "total_amount": 4640},
        {"due_date": "2026-05-27", "total_amount": 4571},
    ]
    rate = _derive_interest_rate(schedule, current_balance=734600)
    assert rate is not None  # finns men felaktig
    assert rate > 0.07       # ~7.5% — olyckligt men deterministiskt


# --- outstanding_balance med current_balance_at_creation ---

def test_outstanding_uses_current_balance_when_set(session):
    loan = Loan(
        name="Bolån", lender="Nordea",
        principal_amount=Decimal("875000"),
        current_balance_at_creation=Decimal("734600"),
        start_date=date(2021, 11, 16),
        interest_rate=0.0311,
    )
    session.add(loan)
    session.flush()

    m = LoanMatcher(session)
    # Inga betalningar → outstanding = current_balance, inte principal
    assert m.outstanding_balance(loan) == Decimal("734600.00")


def test_outstanding_falls_back_to_principal_if_no_current(session):
    loan = Loan(
        name="Bolån", lender="Nordea",
        principal_amount=Decimal("875000"),
        start_date=date(2021, 11, 16),
        interest_rate=0.0311,
    )
    session.add(loan); session.flush()
    m = LoanMatcher(session)
    assert m.outstanding_balance(loan) == Decimal("875000.00")


def test_outstanding_subtracts_future_amortizations(session):
    """Amorteringar STRIKT efter lånets created_at drar current_balance.
    Betalningar samma dag räknas som redan inbakade i bankens angivna
    current_balance — strikt > är säkrare än >=."""
    from datetime import timedelta
    from hembudget.db.models import Account, Transaction

    loan = Loan(
        name="Bolån", lender="Nordea",
        principal_amount=Decimal("875000"),
        current_balance_at_creation=Decimal("734600"),
        start_date=date(2021, 11, 16),
        interest_rate=0.0311,
    )
    session.add(loan); session.flush()

    acc = Account(name="Lön", bank="nordea", type="checking")
    session.add(acc); session.flush()
    # Betalning imorgon (framtida) — ska dras
    future = date.today() + timedelta(days=1)
    tx = Transaction(
        account_id=acc.id, date=future,
        amount=Decimal("-4640"), currency="SEK",
        raw_description="Nordea", hash="h1",
    )
    session.add(tx); session.flush()
    session.add(LoanPayment(
        loan_id=loan.id, transaction_id=tx.id,
        date=future, amount=Decimal("2700"),
        payment_type="amortization",
    ))
    session.flush()

    m = LoanMatcher(session)
    assert m.outstanding_balance(loan) == Decimal("731900.00")  # 734600 - 2700


# --- integrationstester av schedule-skapande via _add_schedule_row logik ---

def test_interest_paid_counts_unmatched_historical_schedule(session):
    """Vision-fångade historiska betalningar (Transaktioner-fliken) ska
    räknas som 'betald ränta' även om bank-CSV inte importerats ännu.
    När CSV:n senare matchas uppgraderas till LoanPayment utan
    dubbelräkning."""
    from datetime import timedelta

    loan = Loan(
        name="Bolån", lender="Nordea",
        principal_amount=Decimal("875000"),
        current_balance_at_creation=Decimal("734600"),
        start_date=date(2021, 11, 16),
        interest_rate=0.0311,
    )
    session.add(loan); session.flush()

    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    # Historiska ränta-rader (omatchade) — räknas
    session.add(LoanScheduleEntry(
        loan_id=loan.id, due_date=yesterday - timedelta(days=30),
        amount=Decimal("1962"), payment_type="interest",
    ))
    session.add(LoanScheduleEntry(
        loan_id=loan.id, due_date=yesterday,
        amount=Decimal("1955"), payment_type="interest",
    ))
    # Framtida ränta-rad — räknas INTE
    session.add(LoanScheduleEntry(
        loan_id=loan.id, due_date=tomorrow,
        amount=Decimal("1940"), payment_type="interest",
    ))
    # Amortering-rad i förflutet — räknas INTE (bara interest)
    session.add(LoanScheduleEntry(
        loan_id=loan.id, due_date=yesterday,
        amount=Decimal("2700"), payment_type="amortization",
    ))
    session.flush()

    m = LoanMatcher(session)
    assert m.total_interest_paid(loan) == Decimal("3917.00")  # 1962 + 1955


def test_interest_paid_matched_schedule_excluded(session):
    """När en schemarad matchats mot en bank-CSV (matched_transaction_id
    satt) ska den INTE räknas som unmatched längre — istället räknas
    motsvarande LoanPayment."""
    from hembudget.db.models import Account, Transaction
    from datetime import timedelta

    loan = Loan(
        name="Bolån", lender="Nordea",
        principal_amount=Decimal("875000"),
        current_balance_at_creation=Decimal("734600"),
        start_date=date(2021, 11, 16),
        interest_rate=0.0311,
    )
    session.add(loan); session.flush()

    yesterday = date.today() - timedelta(days=1)
    # Historisk schemarad som nu matchats
    acc = Account(name="X", bank="nordea", type="checking")
    session.add(acc); session.flush()
    tx = Transaction(
        account_id=acc.id, date=yesterday, amount=Decimal("-4459"),
        currency="SEK", raw_description="Nordea Hypotek",
        hash="h-matched",
    )
    session.add(tx); session.flush()
    session.add(LoanScheduleEntry(
        loan_id=loan.id, due_date=yesterday,
        amount=Decimal("1759"), payment_type="interest",
        matched_transaction_id=tx.id,
    ))
    # Och motsvarande LoanPayment
    session.add(LoanPayment(
        loan_id=loan.id, transaction_id=tx.id,
        date=yesterday, amount=Decimal("1759"),
        payment_type="interest",
    ))
    session.flush()

    m = LoanMatcher(session)
    # Bara LoanPayment-siffran ska räknas — inte schema-raden
    assert m.total_interest_paid(loan) == Decimal("1759.00")


def test_schedule_rows_derived_from_delta_match_reality(session):
    """Skapa ett lån + kör logiken som parse-from-images-endpointet gör
    på Nordea-datan för att verifiera att amortering + ränta hamnar rätt."""
    loan = Loan(
        name="Bolån", lender="Nordea",
        principal_amount=Decimal("875000"),
        current_balance_at_creation=Decimal("734600"),
        start_date=date(2021, 11, 16),
        interest_rate=0.0311,
    )
    session.add(loan); session.flush()

    schedule = [
        {"due_date": "2026-04-27", "total_amount": 4640, "remaining_balance_after": 731900},
        {"due_date": "2026-05-27", "total_amount": 4571, "remaining_balance_after": 729200},
        {"due_date": "2026-06-27", "total_amount": 4626, "remaining_balance_after": 726500},
    ]

    prev = 734600
    for row in schedule:
        this = row["remaining_balance_after"]
        amort, interest = _split_schedule_row(
            row["total_amount"], None, prev, this,
        )
        session.add(LoanScheduleEntry(
            loan_id=loan.id, due_date=date.fromisoformat(row["due_date"]),
            amount=Decimal(str(round(amort, 2))),
            payment_type="amortization",
        ))
        session.add(LoanScheduleEntry(
            loan_id=loan.id, due_date=date.fromisoformat(row["due_date"]),
            amount=Decimal(str(round(interest, 2))),
            payment_type="interest",
        ))
        prev = this
    session.flush()

    entries = session.query(LoanScheduleEntry).order_by(
        LoanScheduleEntry.due_date, LoanScheduleEntry.payment_type
    ).all()

    # 3 rader × 2 typer = 6 entries
    assert len(entries) == 6
    # Alla amort-rader = 2700
    amorts = [e for e in entries if e.payment_type == "amortization"]
    assert all(e.amount == Decimal("2700.00") for e in amorts)
    # Ränta-rader: 1940, 1871, 1926
    interests = sorted(
        (e.amount for e in entries if e.payment_type == "interest"),
        reverse=True,
    )
    assert interests == [Decimal("1940.00"), Decimal("1926.00"), Decimal("1871.00")]


def test_combined_row_matches_sum_of_schedule_entries(session):
    """Nordeas 'Omsättning lån': banken visar -4662 kr men schemat har
    amort 2700 + ränta 1962. Matchern ska para ihop bankraden mot BÅDA
    schemaraderna och skapa två LoanPayment (en per typ)."""
    from hembudget.db.models import Account, Category, Transaction
    from hembudget.loans.matcher import LoanMatcher

    cat_i = Category(name="Bolåneränta")
    cat_a = Category(name="Amortering")
    session.add_all([cat_i, cat_a]); session.flush()

    loan = Loan(
        name="Bolån", lender="Nordea",
        principal_amount=Decimal("875000"),
        current_balance_at_creation=Decimal("734600"),
        start_date=date(2021, 11, 16), interest_rate=0.0311,
    )
    session.add(loan); session.flush()
    session.add_all([
        LoanScheduleEntry(
            loan_id=loan.id, due_date=date(2026, 1, 27),
            amount=Decimal("2700"), payment_type="amortization",
        ),
        LoanScheduleEntry(
            loan_id=loan.id, due_date=date(2026, 1, 27),
            amount=Decimal("1962"), payment_type="interest",
        ),
    ])
    session.flush()

    acc = Account(name="Lönekonto", bank="nordea", type="checking")
    session.add(acc); session.flush()
    tx = Transaction(
        account_id=acc.id, date=date(2026, 1, 28),
        amount=Decimal("-4662"), currency="SEK",
        raw_description="Omsättning lån 3992 68 11531",
        hash="tx1",
    )
    session.add(tx); session.flush()

    result = LoanMatcher(session).match_and_classify([tx])
    assert result.linked == 1
    # Två LoanPayment ska ha skapats: en per typ
    payments = session.query(LoanPayment).filter(LoanPayment.transaction_id == tx.id).all()
    types = {p.payment_type: p.amount for p in payments}
    assert types == {
        "amortization": Decimal("2700"),
        "interest": Decimal("1962"),
    }
    # Båda schemaraderna markerade som matchade
    entries = session.query(LoanScheduleEntry).filter(
        LoanScheduleEntry.loan_id == loan.id
    ).all()
    assert all(e.matched_transaction_id == tx.id for e in entries)


def test_omsattning_lan_no_longer_marked_as_transfer(session):
    """Regression: 'Omsättning lån' skulle tidigare markeras som transfer
    via generiska mönstret och hindra LoanMatcher. Nu ska det INTE hända."""
    from hembudget.db.models import Account, Transaction
    from hembudget.transfers.detector import GENERIC_TRANSFER_PATTERNS

    assert "omsättning lån" not in GENERIC_TRANSFER_PATTERNS


def test_interest_paid_year_filters_by_date(session):
    """interest_paid_year ska bara räkna poster inom det specifika året."""
    from datetime import timedelta
    from hembudget.db.models import Account, Transaction
    loan = Loan(
        name="Bolån", lender="Nordea",
        principal_amount=Decimal("875000"),
        current_balance_at_creation=Decimal("734600"),
        start_date=date(2021, 11, 16),
        interest_rate=0.0311,
    )
    session.add(loan); session.flush()

    # Historiska räntor i 2025 och 2026
    session.add(LoanScheduleEntry(
        loan_id=loan.id, due_date=date(2025, 12, 27),
        amount=Decimal("1900"), payment_type="interest",
    ))
    session.add(LoanScheduleEntry(
        loan_id=loan.id, due_date=date.today() - timedelta(days=1),
        amount=Decimal("1800"), payment_type="interest",
    ))
    session.flush()

    m = LoanMatcher(session)
    this_year = date.today().year
    assert m.interest_paid_year(loan, 2025) == Decimal("1900.00")
    assert m.interest_paid_year(loan, this_year) == Decimal("1800.00")
    assert m.interest_paid_year(loan, 2023) == Decimal("0.00")
