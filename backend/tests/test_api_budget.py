"""HTTP-test för /budget-endpoints (anomalies + family + auto).

Använder FastAPI dependency-override för att skjuta in in-memory-sessionen.
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
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    # Patcha bort demo-bootstrap innan app skapas — det läser riktiga CSV.
    from hembudget import demo as demo_mod
    monkeypatch.setattr(demo_mod, "bootstrap_if_empty", lambda: {"skipped": True})

    from hembudget.api import deps as api_deps
    from hembudget.main import build_app

    app = build_app()

    # Den "riktiga" metoden: FastAPI dependency_overrides
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


def test_anomalies_endpoint(client):
    c, SessionLocal = client
    with SessionLocal() as s:
        from hembudget.db.models import Account, Category, Transaction
        acc = Account(name="X", bank="nordea", type="checking")
        cat = Category(name="Mat")
        s.add_all([acc, cat]); s.flush()
        months = [
            (date(2025, 1, 10), -500), (date(2025, 2, 10), -520),
            (date(2025, 3, 10), -490), (date(2025, 4, 10), -510),
            (date(2025, 5, 10), -480), (date(2025, 6, 10), -530),
            (date(2025, 7, 10), -3000),
        ]
        for d, amt in months:
            s.add(Transaction(
                account_id=acc.id, date=d, amount=Decimal(str(amt)),
                currency="SEK", raw_description="Mat",
                hash=f"{d}-{amt}", category_id=cat.id,
            ))
        s.commit()

    r = c.get("/budget/anomalies/2025-07")
    assert r.status_code == 200
    names = [a["category"] for a in r.json()["anomalies"]]
    assert "Mat" in names


def test_family_endpoint(client):
    c, SessionLocal = client
    with SessionLocal() as s:
        from hembudget.db.models import Account, Transaction
        a1 = Account(name="Robin", bank="nordea", type="checking", owner_id=1)
        a2 = Account(name="Gem", bank="nordea", type="shared")
        s.add_all([a1, a2]); s.flush()
        s.add(Transaction(
            account_id=a1.id, date=date(2026, 4, 25),
            amount=Decimal("30000"), currency="SEK",
            raw_description="Lön", hash="lon1",
        ))
        s.add(Transaction(
            account_id=a2.id, date=date(2026, 4, 28),
            amount=Decimal("-2000"), currency="SEK",
            raw_description="Mat", hash="mat1",
        ))
        s.commit()

    r = c.get("/budget/family/2026-04")
    assert r.status_code == 200
    body = r.json()
    assert "user_1" in body["by_owner"]
    assert body["by_owner"]["user_1"]["income"] == 30000.0
    assert body["by_owner"]["gemensamt"]["expenses"] == 2000.0


def test_auto_budget_endpoint(client):
    c, SessionLocal = client
    with SessionLocal() as s:
        from hembudget.db.models import Account, Category, Transaction
        acc = Account(name="X", bank="nordea", type="checking")
        cat = Category(name="Mat")
        s.add_all([acc, cat]); s.flush()
        for m in [1, 2, 3]:
            s.add(Transaction(
                account_id=acc.id, date=date(2025, m, 10),
                amount=Decimal("-1000"), currency="SEK",
                raw_description="Mat", hash=f"m{m}",
                category_id=cat.id,
            ))
        s.commit()

    r = c.post("/budget/auto?month=2025-04&lookback_months=3")
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == 1
    assert body["budgets"][0]["planned_amount"] == -1000.0
