"""Tester för PATCH /transactions/{id} — amount/date/raw_description-edit."""
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


def test_patch_transaction_updates_amount_date_description(client):
    """Regression: TransactionUpdate.date fick 422 ("none_required") eftersom
    fältnamnet `date` kolliderade med `from datetime import date` när
    `from __future__ import annotations` var på. Pydantic trodde typen
    var None. Fixat med date_type-alias. Detta test ser till att vi INTE
    regresserar."""
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 4, 10),
            amount=Decimal("-2000"), currency="SEK",
            raw_description="Fel lön", hash="h1",
        )
        s.add(tx); s.commit()
        tx_id = tx.id

    r = c.patch(
        f"/transactions/{tx_id}",
        json={
            "amount": 34500,
            "date": "2026-04-25",
            "raw_description": "Lön Evelina (korrigerad)",
            "create_rule": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["amount"]) == 34500.0
    assert body["date"] == "2026-04-25"
    assert body["raw_description"] == "Lön Evelina (korrigerad)"


def test_patch_transaction_only_amount(client):
    """Partiell uppdatering — bara amount."""
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 3, 1),
            amount=Decimal("-500"), currency="SEK",
            raw_description="X", hash="h2",
        )
        s.add(tx); s.commit()
        tx_id = tx.id

    r = c.patch(f"/transactions/{tx_id}", json={"amount": -750})
    assert r.status_code == 200, r.text
    assert float(r.json()["amount"]) == -750.0
    # Datum och beskrivning oförändrade
    assert r.json()["date"] == "2026-03-01"
    assert r.json()["raw_description"] == "X"
