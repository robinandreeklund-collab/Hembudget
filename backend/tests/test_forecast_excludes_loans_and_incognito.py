"""Regressionstester för avg_expenses-exkluderingar i monthly_forecast.

Användaren såg 'snitt övriga utgifter 54 729 kr' som var uppblåst
av lånebetalningar och kortköp som egentligen täcks separat av
låneschemat och upcoming-fakturor.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("HEMBUDGET_DEMO_MODE", "1")
    from hembudget.db.models import Base

    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False,
    )
    from hembudget import demo as demo_mod
    monkeypatch.setattr(demo_mod, "bootstrap_if_empty", lambda: {"skipped": True})
    from hembudget.api import deps as api_deps
    from hembudget.main import build_app
    app = build_app()

    def _db():
        s = SessionLocal()
        try:
            yield s; s.commit()
        except Exception:
            s.rollback(); raise
        finally:
            s.close()

    app.dependency_overrides[api_deps.db] = _db
    with TestClient(app) as c:
        yield c, SessionLocal


def test_loan_payments_excluded_from_avg_expenses(client):
    """Låneamorteringar och räntebetalningar fångas via låneschemat,
    inte via avg_expenses. Om de räknas båda ställen dubbelräknas de."""
    c, SL = client
    from hembudget.db.models import (
        Account, Loan, LoanPayment, Transaction,
    )
    with SL() as s:
        acc = Account(name="Lön", bank="nordea", type="checking")
        s.add(acc); s.flush()
        loan = Loan(
            name="Bolån", lender="Nordea",
            principal_amount=Decimal("1000000"),
            start_date=date(2020, 1, 1), interest_rate=0.03,
        )
        s.add(loan); s.flush()
        # 3 månaders amorteringar + räntebetalningar + mat-utgifter
        for m in [1, 2, 3]:
            amort_tx = Transaction(
                account_id=acc.id, date=date(2026, m, 27),
                amount=Decimal("-5000"), currency="SEK",
                raw_description="Amortering", hash=f"amort-{m}",
            )
            interest_tx = Transaction(
                account_id=acc.id, date=date(2026, m, 27),
                amount=Decimal("-2500"), currency="SEK",
                raw_description="Ränta", hash=f"ranta-{m}",
            )
            mat_tx = Transaction(
                account_id=acc.id, date=date(2026, m, 10),
                amount=Decimal("-10000"), currency="SEK",
                raw_description="ICA", hash=f"ica-{m}",
            )
            s.add_all([amort_tx, interest_tx, mat_tx]); s.flush()
            # Lånebetalningar registreras via LoanPayment
            s.add(LoanPayment(
                loan_id=loan.id, transaction_id=amort_tx.id,
                date=amort_tx.date, amount=Decimal("5000"),
                payment_type="amortization",
            ))
            s.add(LoanPayment(
                loan_id=loan.id, transaction_id=interest_tx.id,
                date=interest_tx.date, amount=Decimal("2500"),
                payment_type="interest",
            ))
        s.commit()

    r = c.get("/upcoming/forecast?month=2026-04")
    totals = r.json()["totals"]
    # avg ska vara 10 000 (bara mat) — INTE 17 500 (mat + amort + ränta)
    assert totals["avg_fixed_expenses"] == pytest.approx(10000.0)


def test_forecast_includes_loan_scheduled_separately(client):
    """Lånebetalningar från schemat dras separat från 'kvar efter kända'
    — inte via avg_expenses."""
    c, SL = client
    from hembudget.db.models import (
        Account, Loan, LoanScheduleEntry, UpcomingTransaction,
    )
    with SL() as s:
        acc = Account(name="Lön", bank="nordea", type="checking")
        s.add(acc); s.flush()
        loan = Loan(
            name="X", lender="Nordea",
            principal_amount=Decimal("100000"),
            start_date=date(2024, 1, 1), interest_rate=0.03,
        )
        s.add(loan); s.flush()
        # April-schemat: 5000 amort + 2500 ränta
        s.add(LoanScheduleEntry(
            loan_id=loan.id, due_date=date(2026, 4, 27),
            amount=Decimal("5000"), payment_type="amortization",
        ))
        s.add(LoanScheduleEntry(
            loan_id=loan.id, due_date=date(2026, 4, 27),
            amount=Decimal("2500"), payment_type="interest",
        ))
        # Lön för april
        s.add(UpcomingTransaction(
            kind="income", name="Lön",
            amount=Decimal("30000"),
            expected_date=date(2026, 4, 25),
        ))
        s.commit()

    r = c.get("/upcoming/forecast?month=2026-04")
    totals = r.json()["totals"]
    assert totals["expected_income"] == pytest.approx(30000.0)
    assert totals["upcoming_bills"] == pytest.approx(0.0)
    # Nytt: loan_scheduled visas separat
    assert totals["loan_scheduled"] == pytest.approx(7500.0)  # 5000 + 2500
    # Kvar efter kända = 30000 - 0 - 7500 = 22500
    assert totals["after_known_bills"] == pytest.approx(22500.0)


def test_incognito_expenses_excluded_from_avg(client):
    """Partnerns privata utgifter (på inkognito-konto) ska inte påverka
    familjens snitt-utgifter."""
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        main = Account(name="Lön", bank="nordea", type="checking")
        incog = Account(
            name="Eve priv", bank="nordea", type="checking", incognito=True,
        )
        s.add_all([main, incog]); s.flush()
        for m in [1, 2, 3]:
            s.add(Transaction(
                account_id=main.id, date=date(2026, m, 10),
                amount=Decimal("-5000"), currency="SEK",
                raw_description="ICA", hash=f"ica-{m}",
            ))
            # Stora privata utgifter på inkognito — ska EJ räknas
            s.add(Transaction(
                account_id=incog.id, date=date(2026, m, 12),
                amount=Decimal("-20000"), currency="SEK",
                raw_description="Privat", hash=f"priv-{m}",
            ))
        s.commit()

    r = c.get("/upcoming/forecast?month=2026-04")
    # avg = 5000 (bara main-kontots ICA), inkognito ignoreras
    assert r.json()["totals"]["avg_fixed_expenses"] == pytest.approx(5000.0)
