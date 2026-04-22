"""Tester för DELETE /transactions/{id} med korrekt cleanup."""
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


def test_delete_simple_transaction(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 3, 1),
            amount=Decimal("-500"), currency="SEK",
            raw_description="Test", hash="h1",
        )
        s.add(tx); s.commit()
        tx_id = tx.id

    r = c.delete(f"/transactions/{tx_id}")
    assert r.status_code == 200
    assert r.json()["deleted"] == tx_id

    # Tx ska vara borta
    from hembudget.db.models import Transaction as _Tx
    with SL() as s:
        assert s.get(_Tx, tx_id) is None


def test_delete_transaction_cleans_upcoming_payment(client):
    """När vi raderar en tx som är delbetalning av en upcoming, ska
    UpcomingPayment-junction-raden också rensas, och paid_amount räknas
    om för upcoming."""
    c, SL = client
    from hembudget.db.models import (
        Account, Transaction, UpcomingTransaction, UpcomingPayment,
    )
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        tx1 = Transaction(
            account_id=acc.id, date=date(2026, 2, 1),
            amount=Decimal("-500"), currency="SEK",
            raw_description="d1", hash="h1",
        )
        tx2 = Transaction(
            account_id=acc.id, date=date(2026, 2, 15),
            amount=Decimal("-500"), currency="SEK",
            raw_description="d2", hash="h2",
        )
        s.add_all([tx1, tx2]); s.flush()
        up = UpcomingTransaction(
            kind="bill", name="X", amount=Decimal("1000"),
            expected_date=date(2026, 2, 15),
            matched_transaction_id=tx1.id,
        )
        s.add(up); s.flush()
        s.add(UpcomingPayment(upcoming_id=up.id, transaction_id=tx1.id))
        s.add(UpcomingPayment(upcoming_id=up.id, transaction_id=tx2.id))
        s.commit()
        tx1_id, tx2_id, up_id = tx1.id, tx2.id, up.id

    # Radera tx1
    r = c.delete(f"/transactions/{tx1_id}")
    assert r.json()["upcoming_payments_removed"] == 1

    # Verify: bara tx2 kvar i payments, matched_transaction_id flyttad
    with SL() as s:
        remaining = s.query(UpcomingPayment).filter(
            UpcomingPayment.upcoming_id == up_id
        ).all()
        assert len(remaining) == 1
        assert remaining[0].transaction_id == tx2_id
        up = s.get(UpcomingTransaction, up_id)
        assert up.matched_transaction_id == tx2_id


def test_delete_transaction_cleans_loan_payment(client):
    c, SL = client
    from hembudget.db.models import Account, Loan, LoanPayment, Transaction
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        loan = Loan(
            name="X", lender="Nordea",
            principal_amount=Decimal("100000"),
            start_date=date(2024, 1, 1), interest_rate=0.03,
        )
        s.add(loan); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 2, 27),
            amount=Decimal("-5000"), currency="SEK",
            raw_description="Amort", hash="h1",
        )
        s.add(tx); s.flush()
        s.add(LoanPayment(
            loan_id=loan.id, transaction_id=tx.id,
            date=tx.date, amount=Decimal("5000"),
            payment_type="amortization",
        ))
        s.commit()
        tx_id = tx.id

    r = c.delete(f"/transactions/{tx_id}")
    assert r.json()["loan_payments_removed"] == 1

    with SL() as s:
        assert s.query(LoanPayment).count() == 0


def test_delete_transaction_unlinks_transfer_partner(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc1 = Account(name="A", bank="nordea", type="checking")
        acc2 = Account(name="B", bank="nordea", type="checking")
        s.add_all([acc1, acc2]); s.flush()
        tx1 = Transaction(
            account_id=acc1.id, date=date(2026, 4, 5),
            amount=Decimal("-1000"), currency="SEK",
            raw_description="Out", hash="h1", is_transfer=True,
        )
        tx2 = Transaction(
            account_id=acc2.id, date=date(2026, 4, 5),
            amount=Decimal("1000"), currency="SEK",
            raw_description="In", hash="h2", is_transfer=True,
        )
        s.add_all([tx1, tx2]); s.flush()
        tx1.transfer_pair_id = tx2.id
        tx2.transfer_pair_id = tx1.id
        s.commit()
        tx1_id, tx2_id = tx1.id, tx2.id

    r = c.delete(f"/transactions/{tx1_id}")
    assert r.json()["partner_unlinked"] == tx2_id

    with SL() as s:
        partner = s.get(Transaction, tx2_id)
        assert partner is not None  # finns kvar
        assert partner.transfer_pair_id is None  # men inte länkad


def test_delete_transaction_404_for_unknown(client):
    c, _ = client
    r = c.delete("/transactions/99999")
    assert r.status_code == 404
