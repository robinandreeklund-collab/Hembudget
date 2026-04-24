"""Tester för de nya fixarna på låne-import:
- _reconcile_loan_amounts: härled principal/current_balance från amorterat
- /loans/{id}/schedule/prune-history: rensa pre-tracking rader
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def test_reconcile_amounts_derives_principal_from_current_plus_amortized():
    from hembudget.api.loans import _reconcile_loan_amounts

    # Nordea-fallet: principal saknas men current + amorterat ger oss det
    p, c = _reconcile_loan_amounts(None, 31633, 168367)
    assert p == 200000.0
    assert c == 31633.0


def test_reconcile_amounts_derives_current_from_principal_minus_amortized():
    from hembudget.api.loans import _reconcile_loan_amounts

    p, c = _reconcile_loan_amounts(200000, None, 168367)
    assert p == 200000.0
    assert c == 31633.0


def test_reconcile_amounts_when_principal_is_zero_explicitly():
    """LLM returnerar 0 istället för null → behandla som saknat."""
    from hembudget.api.loans import _reconcile_loan_amounts

    p, c = _reconcile_loan_amounts(0, 31633, 168367)
    assert p == 200000.0
    assert c == 31633.0


def test_reconcile_amounts_fallback_to_each_other_if_only_one():
    from hembudget.api.loans import _reconcile_loan_amounts

    p, c = _reconcile_loan_amounts(200000, None, None)
    assert p == 200000.0
    assert c == 200000.0

    p, c = _reconcile_loan_amounts(None, 50000, None)
    assert p == 50000.0
    assert c == 50000.0


def test_reconcile_amounts_trusts_explicit_input():
    from hembudget.api.loans import _reconcile_loan_amounts

    # Båda givna → inget härleds
    p, c = _reconcile_loan_amounts(200000, 31633, 168367)
    assert p == 200000.0
    assert c == 31633.0


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("HEMBUDGET_DEMO_MODE", "1")

    from hembudget.db.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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

    def _fake_db():
        s = SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[api_deps.db] = _fake_db
    with TestClient(app) as c:
        yield c, SessionLocal


def test_prune_history_removes_entries_before_earliest_transaction(client):
    c, SessionLocal = client

    from hembudget.db.models import (
        Account, Loan, LoanScheduleEntry, Transaction,
    )

    with SessionLocal() as s:
        acc = Account(name="Lönekonto", bank="nordea", type="checking")
        s.add(acc); s.flush()
        # Äldsta importerade transaktion är 2026-01-15
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 1, 15),
            amount=Decimal("-100"), currency="SEK",
            raw_description="x", hash="h1",
        ))
        loan = Loan(
            name="Nordea Hypotek", lender="Nordea Hypotek AB",
            principal_amount=Decimal("200000"), start_date=date(2017, 10, 16),
            interest_rate=0.0311,
        )
        s.add(loan); s.flush()
        loan_id = loan.id
        # 3 gamla schema-rader (före 2026-01-15) + 2 framtida
        for d in [date(2025, 8, 27), date(2025, 9, 27), date(2025, 12, 27)]:
            s.add(LoanScheduleEntry(
                loan_id=loan_id, due_date=d,
                amount=Decimal("1750"), payment_type="interest",
            ))
        for d in [date(2026, 2, 27), date(2026, 3, 27)]:
            s.add(LoanScheduleEntry(
                loan_id=loan_id, due_date=d,
                amount=Decimal("1700"), payment_type="interest",
            ))
        # En redan matchad pre-cutoff rad → ska INTE raderas
        s.add(LoanScheduleEntry(
            loan_id=loan_id, due_date=date(2025, 10, 27),
            amount=Decimal("1750"), payment_type="interest",
            matched_transaction_id=1,
        ))
        s.commit()

    r = c.post(f"/loans/{loan_id}/schedule/prune-history")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] == 3          # bara de tre omatchade pre-cutoff
    assert body["cutoff"] == "2026-01-15"

    # Kvar: 2 framtida + 1 matchad pre-cutoff = 3
    r = c.get(f"/loans/{loan_id}/schedule")
    remaining = r.json()
    assert len(remaining) == 3


def test_prune_history_uses_loan_start_date_when_no_transactions(client):
    c, SessionLocal = client

    from hembudget.db.models import Loan, LoanScheduleEntry

    with SessionLocal() as s:
        loan = Loan(
            name="Bolån", lender="Nordea",
            principal_amount=Decimal("100000"),
            start_date=date(2026, 2, 1),
            interest_rate=0.03,
        )
        s.add(loan); s.flush()
        loan_id = loan.id
        # En pre-start-rad och en post-start-rad
        s.add(LoanScheduleEntry(
            loan_id=loan_id, due_date=date(2025, 12, 1),
            amount=Decimal("500"), payment_type="interest",
        ))
        s.add(LoanScheduleEntry(
            loan_id=loan_id, due_date=date(2026, 3, 1),
            amount=Decimal("500"), payment_type="interest",
        ))
        s.commit()

    r = c.post(f"/loans/{loan_id}/schedule/prune-history")
    assert r.status_code == 200
    assert r.json()["deleted"] == 1
    assert r.json()["cutoff"] == "2026-02-01"


def test_prune_history_404_for_unknown_loan(client):
    c, _ = client
    r = c.post("/loans/9999/schedule/prune-history")
    assert r.status_code == 404
