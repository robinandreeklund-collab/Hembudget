"""Tester för /ledger/check/{check_type} — snabb-åtgärds-preview för
avstämningscheckarna i huvudboken."""
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


def test_check_uncategorized_returns_uncategorized_txs(client):
    c, SL = client
    from hembudget.db.models import Account, Category, Transaction
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        mat = Category(name="Mat")
        s.add_all([acc, mat]); s.flush()
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 3, 1),
            amount=Decimal("-500"), currency="SEK",
            raw_description="okänd", hash="h1",
        ))
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 3, 5),
            amount=Decimal("-200"), currency="SEK",
            raw_description="ICA", hash="h2", category_id=mat.id,
        ))
        s.commit()

    r = c.get("/ledger/check/uncategorized?year=2026")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["transactions"][0]["description"] == "okänd"


def test_check_transfers_imbalance_returns_orphans(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        # Orphan transfer
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 3, 1),
            amount=Decimal("-1000"), currency="SEK",
            raw_description="Överföring ut", hash="h1",
            is_transfer=True,
        ))
        # Paired transfer (ska inte räknas)
        tx2 = Transaction(
            account_id=acc.id, date=date(2026, 3, 2),
            amount=Decimal("-500"), currency="SEK",
            raw_description="Parad", hash="h2",
            is_transfer=True, transfer_pair_id=999,
        )
        s.add(tx2); s.commit()

    r = c.get("/ledger/check/transfers_imbalance?year=2026")
    body = r.json()
    assert body["count"] == 1
    assert body["transactions"][0]["amount"] == -1000
    assert body["net_diff"] == pytest.approx(-1000.0)


def test_check_unmatched_past_upcomings(client):
    c, SL = client
    from hembudget.db.models import UpcomingTransaction
    with SL() as s:
        # Passerat + omatchat → ska med
        s.add(UpcomingTransaction(
            kind="bill", name="Gammal", amount=Decimal("500"),
            expected_date=date(2025, 12, 1),
        ))
        # Framtida → ska EJ med
        s.add(UpcomingTransaction(
            kind="bill", name="Framtida", amount=Decimal("300"),
            expected_date=date(2099, 12, 1),
        ))
        s.commit()

    r = c.get("/ledger/check/unmatched_past_upcomings?year=2025")
    body = r.json()
    assert body["count"] == 1
    assert body["upcomings"][0]["name"] == "Gammal"


def test_check_unknown_type_returns_400(client):
    c, _ = client
    r = c.get("/ledger/check/unknown_check?year=2026")
    assert r.status_code == 400


def test_ledger_returns_check_type_on_failing_checks(client):
    """Varje failed check i huvudbok ska ha 'check_type'-fält för
    frontendens expandera-funktion."""
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 3, 1),
            amount=Decimal("-100"), currency="SEK",
            raw_description="okänd", hash="h1",
        ))
        s.commit()

    r = c.get("/ledger/?year=2026")
    body = r.json()
    uncat = next(
        (c for c in body["checks"] if "ategoriserade" in c["name"]), None,
    )
    assert uncat is not None
    assert uncat["check_type"] == "uncategorized"


def test_upcoming_matched_tx_excluded_from_orphan_transfers(client):
    """Regression: en tx med is_transfer=True men matchad till en
    UpcomingTransaction ska EJ synas som orphan — användaren har
    redan redovisat den som bill-betalning."""
    c, SL = client
    from hembudget.db.models import (
        Account, Transaction, UpcomingPayment, UpcomingTransaction,
    )
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        # Orphan som är matchad mot upcoming → ska filtreras bort
        tx_matched = Transaction(
            account_id=acc.id, date=date(2026, 4, 17),
            amount=Decimal("-2922"), currency="SEK",
            raw_description="Betalning BG 5127-5477 American Exp",
            hash="h_amex", is_transfer=True,
        )
        # Orphan utan match → ska finnas kvar
        tx_bare = Transaction(
            account_id=acc.id, date=date(2026, 4, 1),
            amount=Decimal("-166"), currency="SEK",
            raw_description="Nordea LIV", hash="h_liv",
            is_transfer=True,
        )
        s.add_all([tx_matched, tx_bare]); s.flush()
        up = UpcomingTransaction(
            kind="bill", name="Amex-faktura",
            amount=Decimal("2922"), expected_date=date(2026, 4, 25),
        )
        s.add(up); s.flush()
        s.add(UpcomingPayment(upcoming_id=up.id, transaction_id=tx_matched.id))
        s.commit()

    r = c.get("/ledger/check/transfers_imbalance?month=2026-04")
    body = r.json()
    # Bara den omatchade kvar i orphan-listan
    assert body["count"] == 1
    assert body["transactions"][0]["description"] == "Nordea LIV"

    # Och huvudbokens transfer-sum ska inte längre räkna med Amex-raden
    r2 = c.get("/ledger/?month=2026-04")
    body2 = r2.json()
    transfer_check = next(
        (c for c in body2["checks"]
         if c["name"] == "Interna överföringar balanserar"), None,
    )
    assert transfer_check is not None
    # -166 är ensam orphan kvar; -2922 ska ha reklassificerats till expense
    assert transfer_check["value"] == pytest.approx(-166.0)


def test_transactions_list_exposes_upcoming_matches(client):
    """/transactions ska returnera upcoming_matches så UI kan visa
    bekräftelse-badge på matchade rader."""
    c, SL = client
    from hembudget.db.models import (
        Account, Transaction, UpcomingPayment, UpcomingTransaction,
    )
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 4, 17),
            amount=Decimal("-2922"), currency="SEK",
            raw_description="Amex-betalning", hash="h1",
        )
        s.add(tx); s.flush()
        up = UpcomingTransaction(
            kind="bill", name="Amex april",
            amount=Decimal("5000"), expected_date=date(2026, 4, 25),
        )
        s.add(up); s.flush()
        s.add(UpcomingPayment(upcoming_id=up.id, transaction_id=tx.id))
        s.commit()

    r = c.get("/transactions?account_id=1")
    body = r.json()
    assert len(body) == 1
    assert body[0]["upcoming_matches"] == [
        {
            "upcoming_id": 1,
            "name": "Amex april",
            "kind": "bill",
            "amount": "5000.00",
        },
    ]
