"""Smoke-test forecast-endpointen över olika månader så SQL-generation inte
faller sönder över årsgränser och utanför januari."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from hembudget.api.deps import db as db_dep, require_auth
from hembudget.db.models import (
    Account, Base, Transaction, UpcomingTransaction,
)
from hembudget.main import app


@pytest.fixture()
def client():
    # StaticPool + shared cache så flera sessions delar samma :memory: DB
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def _override_db():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[db_dep] = _override_db
    app.dependency_overrides[require_auth] = lambda: "test-token"

    # Seed en del data — konto, transaktioner + kommande
    with Session(engine) as s:
        acc = Account(name="Gemensamt", bank="nordea", type="shared")
        s.add(acc); s.flush()
        for m, amt in [(12, -1000), (1, -2000), (2, -1500), (3, -1800)]:
            yr = 2025 if m == 12 else 2026
            s.add(Transaction(
                account_id=acc.id, date=date(yr, m, 15),
                amount=Decimal(str(amt)), currency="SEK",
                raw_description="mat",
                hash=f"h-{yr}-{m}",
            ))
        s.add(UpcomingTransaction(
            kind="bill", name="Vattenfall",
            amount=Decimal("1420"), expected_date=date(2026, 4, 30),
        ))
        s.add(UpcomingTransaction(
            kind="income", name="Lön Robin",
            amount=Decimal("42000"), expected_date=date(2026, 4, 25),
            owner="Robin",
        ))
        s.commit()

    yield TestClient(app)
    app.dependency_overrides.clear()


def test_forecast_april(client):
    """April ligger utanför jan-specialfallet som tidigare buggade."""
    r = client.get("/upcoming/forecast?month=2026-04")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["month"] == "2026-04"
    assert data["totals"]["expected_income"] == 42000
    assert data["totals"]["upcoming_bills"] == 1420
    # 3 månader tillbaka: jan, feb, mar → snitt av 2000, 1500, 1800 = 1766.67
    assert abs(data["totals"]["avg_fixed_expenses"] - 1766.67) < 0.02


def test_forecast_january_crosses_year_boundary(client):
    """Jan 2026 ska kolla okt-dec 2025."""
    r = client.get("/upcoming/forecast?month=2026-01")
    assert r.status_code == 200, r.text
    # Bara dec 2025 finns i vår seed → snitt = 1000
    assert abs(r.json()["totals"]["avg_fixed_expenses"] - 1000) < 0.02


def test_forecast_future_month_empty(client):
    """Långt i framtiden — ingen data → endpoint får inte krascha."""
    r = client.get("/upcoming/forecast?month=2027-06")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["totals"]["expected_income"] == 0
    assert data["totals"]["upcoming_bills"] == 0
