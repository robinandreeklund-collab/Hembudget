"""Tester för månads-lås på huvudboken."""
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


def test_lock_and_unlock_month(client):
    c, SL = client
    r1 = c.post("/ledger/locks/2026-01")
    assert r1.status_code == 200
    r2 = c.get("/ledger/locks")
    assert "2026-01" in [x["month"] for x in r2.json()["locks"]]
    r3 = c.delete("/ledger/locks/2026-01")
    assert r3.status_code == 200
    r4 = c.get("/ledger/locks")
    assert r4.json()["locks"] == []


def test_locked_month_blocks_tx_update(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(name="A", bank="n", type="checking")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 1, 15),
            amount=Decimal("-500"), currency="SEK",
            raw_description="Test", hash="h1",
        )
        s.add(tx); s.commit()
        tx_id = tx.id

    # Innan lås — PATCH funkar
    r_before = c.patch(f"/transactions/{tx_id}", json={"amount": -600})
    assert r_before.status_code == 200

    # Lås januari
    c.post("/ledger/locks/2026-01")

    # PATCH på tx i låst månad → 423
    r_locked = c.patch(f"/transactions/{tx_id}", json={"amount": -700})
    assert r_locked.status_code == 423
    assert "låst" in r_locked.json()["detail"].lower()

    # DELETE blockas också
    r_del = c.delete(f"/transactions/{tx_id}")
    assert r_del.status_code == 423

    # Lås upp — PATCH går igen
    c.delete("/ledger/locks/2026-01")
    r_after = c.patch(f"/transactions/{tx_id}", json={"amount": -800})
    assert r_after.status_code == 200


def test_ledger_returns_locked_months(client):
    c, SL = client
    c.post("/ledger/locks/2026-02")
    c.post("/ledger/locks/2026-03")

    # Month-scope: bara månader som matchar (2026-02)
    r = c.get("/ledger/?month=2026-02").json()
    assert r["locked_months"] == ["2026-02"]

    # Year-scope: alla låsta månader inom året
    r = c.get("/ledger/?year=2026").json()
    assert set(r["locked_months"]) == {"2026-02", "2026-03"}


def test_cant_move_tx_to_locked_month(client):
    """Om man försöker flytta en tx till en låst månad → 423."""
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(name="A", bank="n", type="checking")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 4, 15),
            amount=Decimal("-500"), currency="SEK",
            raw_description="Apr-tx", hash="h2",
        )
        s.add(tx); s.commit()
        tx_id = tx.id

    c.post("/ledger/locks/2026-01")

    # Försök flytta till januari (låst)
    r = c.patch(f"/transactions/{tx_id}", json={"date": "2026-01-10"})
    assert r.status_code == 423
