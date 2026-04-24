"""Tester för manuell koppling av upcoming till konto + skapa motsvarande
för orphan-transfers.
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


def test_materialize_upcoming_to_account(client):
    """Lön utan auto-match → användaren trycker 'Koppla till konto',
    väljer hennes inkognito-konto → Transaction skapas där och binds."""
    c, SL = client
    from hembudget.db.models import Account

    # Skapa ett konto utan owner-relation (så auto-materialize inte triggar)
    with SL() as s:
        acc = Account(
            name="Evelinas priv", bank="nordea", type="checking",
            incognito=True,
        )
        s.add(acc); s.commit()
        acc_id = acc.id

    # Skapa upcoming utan owner så auto-materialize definitivt inte triggar
    r = c.post("/upcoming/", json={
        "kind": "income", "name": "Arbetsgivare",
        "amount": "30000", "expected_date": "2026-03-25",
    })
    up = r.json()
    assert up["matched_transaction_id"] is None

    # Manuell koppling
    r = c.post(
        f"/upcoming/{up['id']}/materialize-to-account",
        json={"account_id": acc_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account_id"] == acc_id
    assert body["amount"] == pytest.approx(30000.0)

    # Verify Transaction skapades och upcoming är matchad
    from hembudget.db.models import Transaction, UpcomingTransaction
    with SL() as s:
        tx = s.get(Transaction, body["transaction_id"])
        assert tx.account_id == acc_id
        assert float(tx.amount) == pytest.approx(30000.0)
        u = s.get(UpcomingTransaction, up["id"])
        assert u.matched_transaction_id == tx.id


def test_materialize_bill_creates_negative_tx(client):
    c, SL = client
    from hembudget.db.models import Account
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.commit()
        acc_id = acc.id

    r = c.post("/upcoming/", json={
        "kind": "bill", "name": "Räkning",
        "amount": "1500", "expected_date": "2026-03-10",
    })
    up_id = r.json()["id"]

    r = c.post(
        f"/upcoming/{up_id}/materialize-to-account",
        json={"account_id": acc_id},
    )
    body = r.json()
    # Bill → negativt tecken
    assert body["amount"] == pytest.approx(-1500.0)


def test_materialize_already_matched_returns_409(client):
    c, SL = client
    from hembudget.db.models import Account
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.commit()
        acc_id = acc.id

    r = c.post("/upcoming/", json={
        "kind": "income", "name": "X",
        "amount": "5000", "expected_date": "2026-01-15",
    })
    up_id = r.json()["id"]
    c.post(
        f"/upcoming/{up_id}/materialize-to-account",
        json={"account_id": acc_id},
    )
    # Andra försök — redan matchad
    r = c.post(
        f"/upcoming/{up_id}/materialize-to-account",
        json={"account_id": acc_id},
    )
    assert r.status_code == 409


def test_materialize_404_for_missing_upcoming_or_account(client):
    c, _ = client
    r = c.post("/upcoming/99999/materialize-to-account", json={"account_id": 1})
    assert r.status_code == 404

    r = c.post("/upcoming/1/materialize-to-account", json={})
    assert r.status_code in (400, 404)


# ---------- create-counterpart ----------


def test_create_counterpart_pairs_transfer(client):
    """Orphan +10k på gemensamt → skapa motsvarande -10k på inkognito →
    båda paras som transfer."""
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        shared = Account(name="Gemensamt", bank="nordea", type="shared")
        incog = Account(
            name="Eve priv", bank="nordea", type="checking", incognito=True,
        )
        s.add_all([shared, incog]); s.flush()
        shared_id, incog_id = shared.id, incog.id
        tx = Transaction(
            account_id=shared_id, date=date(2026, 4, 5),
            amount=Decimal("10000"), currency="SEK",
            raw_description="Från Evelina", hash="h1",
            is_transfer=True,
        )
        s.add(tx); s.commit()
        tx_id = tx.id

    # Skapa motsvarande på inkognito
    r = c.post(
        f"/transfers/{tx_id}/create-counterpart",
        json={"account_id": incog_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["paired_as_transfer"] is True
    assert body["amount"] == pytest.approx(-10000.0)

    # Båda är paired
    from hembudget.db.models import Transaction as _Tx
    with SL() as s:
        src = s.get(_Tx, tx_id)
        counter = s.get(_Tx, body["counterpart_tx_id"])
        assert src.transfer_pair_id == counter.id
        assert counter.transfer_pair_id == src.id
        assert src.is_transfer is True
        assert counter.is_transfer is True
        assert counter.account_id == incog_id


def test_create_counterpart_rejects_same_account(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(name="X", bank="nordea", type="checking")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 4, 5),
            amount=Decimal("100"), currency="SEK",
            raw_description="Y", hash="h1", is_transfer=True,
        )
        s.add(tx); s.commit()
        tx_id, acc_id = tx.id, acc.id

    r = c.post(
        f"/transfers/{tx_id}/create-counterpart",
        json={"account_id": acc_id},
    )
    assert r.status_code == 400


def test_create_counterpart_404_for_missing(client):
    c, _ = client
    r = c.post("/transfers/99999/create-counterpart", json={"account_id": 1})
    assert r.status_code == 404


def test_create_counterpart_custom_description_and_date(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        a = Account(name="A", bank="nordea", type="checking")
        b = Account(name="B", bank="nordea", type="checking")
        s.add_all([a, b]); s.flush()
        tx = Transaction(
            account_id=a.id, date=date(2026, 4, 5),
            amount=Decimal("500"), currency="SEK",
            raw_description="X", hash="h1", is_transfer=True,
        )
        s.add(tx); s.commit()
        tx_id = tx.id
        b_id = b.id

    r = c.post(
        f"/transfers/{tx_id}/create-counterpart",
        json={
            "account_id": b_id,
            "description": "Min motpart",
            "date": "2026-04-07",
        },
    )
    body = r.json()
    from hembudget.db.models import Transaction as _Tx
    with SL() as s:
        counter = s.get(_Tx, body["counterpart_tx_id"])
        assert counter.raw_description == "Min motpart"
        assert counter.date.isoformat() == "2026-04-07"
