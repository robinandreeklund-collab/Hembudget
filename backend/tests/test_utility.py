"""Tester for /utility-endpoints och PDF-parser."""
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


def _seed_two_years(SL):
    """Seeda el + vatten-transaktioner for 2025 (lagt) och 2026 (hogre)."""
    from hembudget.db.models import Account, Category, Transaction
    with SL() as s:
        acc = Account(name="A", bank="n", type="checking")
        el = Category(name="El")
        vatten = Category(name="Vatten/Avgift")
        s.add_all([acc, el, vatten]); s.flush()
        # 2025: 500 kr/mnad el, 200 kr/mnad vatten
        for m in range(1, 13):
            s.add(Transaction(
                account_id=acc.id, date=date(2025, m, 15),
                amount=Decimal("-500"), currency="SEK",
                raw_description="Hjo Energi", hash=f"e25_{m}",
                category_id=el.id,
            ))
            s.add(Transaction(
                account_id=acc.id, date=date(2025, m, 15),
                amount=Decimal("-200"), currency="SEK",
                raw_description="Hjo kommun", hash=f"v25_{m}",
                category_id=vatten.id,
            ))
        # 2026 Q1: 700 kr/mnad el (+40 % yoy)
        for m in range(1, 4):
            s.add(Transaction(
                account_id=acc.id, date=date(2026, m, 15),
                amount=Decimal("-700"), currency="SEK",
                raw_description="Hjo Energi", hash=f"e26_{m}",
                category_id=el.id,
            ))
        s.commit()


def test_history_yoy_comparison(client):
    c, SL = client
    _seed_two_years(SL)

    r = c.get("/utility/history?year=2026&compare_previous_year=true")
    assert r.status_code == 200, r.text
    body = r.json()

    # Current year: bara el Q1, 700 * 3 = 2100
    assert body["year"] == 2026
    assert body["category_totals"]["El"] == pytest.approx(2100.0)

    # Previous-year struktur
    assert "previous" in body
    prev = body["previous"]
    assert prev["year"] == 2025
    # 2025: el 500 * 12 = 6000, vatten 200 * 12 = 2400
    assert prev["category_totals"]["El"] == pytest.approx(6000.0)
    assert prev["category_totals"]["Vatten/Avgift"] == pytest.approx(2400.0)

    # YoY-diff per manad for El: januari 700 - 500 = +200
    assert body["yoy_diff"]["El"]["2026-01"] == pytest.approx(200.0)
    # April 0 - 500 = -500 (ingen tx 2026-04)
    assert body["yoy_diff"]["El"]["2026-04"] == pytest.approx(-500.0)


def test_history_without_yoy_has_no_previous(client):
    c, SL = client
    _seed_two_years(SL)
    r = c.get("/utility/history?year=2026")
    body = r.json()
    assert "previous" not in body
    assert "yoy_diff" not in body


def test_readings_crud(client):
    c, SL = client

    # Skapa en manuell reading
    r1 = c.post("/utility/readings", json={
        "supplier": "tibber",
        "meter_type": "electricity",
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
        "consumption": 450,
        "consumption_unit": "kWh",
        "cost_kr": 950,
    })
    assert r1.status_code == 200
    rid = r1.json()["id"]

    # Lista
    r2 = c.get("/utility/readings?year=2026")
    rows = r2.json()["readings"]
    assert len(rows) == 1
    assert rows[0]["consumption"] == 450
    assert rows[0]["consumption_unit"] == "kWh"
    assert rows[0]["supplier"] == "tibber"

    # Lista dyker upp i history.readings
    hist = c.get("/utility/history?year=2026").json()
    assert "electricity" in hist["readings"]
    assert hist["readings"]["electricity"]["2026-01"]["consumption"] == 450.0
    assert hist["readings"]["electricity"]["2026-01"]["cost_kr"] == 950.0

    # Ta bort
    r3 = c.delete(f"/utility/readings/{rid}")
    assert r3.status_code == 200
    r4 = c.get("/utility/readings?year=2026")
    assert r4.json()["readings"] == []


def test_breakdown_lists_transactions_for_cell(client):
    """GET /utility/breakdown?category=El&month=2026-01 listar alla
    tx + splits som bidrar till cellen. Anvands for att felsoka
    'varfor ar mars-el 24 443 kr?'."""
    c, SL = client
    from hembudget.db.models import (
        Account, Category, Transaction, TransactionSplit,
    )
    with SL() as s:
        acc = Account(name="A", bank="n", type="checking")
        el = Category(name="El")
        s.add_all([acc, el]); s.flush()
        # Ren el-tx
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 1, 15),
            amount=Decimal("-900"), currency="SEK",
            raw_description="Hjo Energi januari", hash="e1",
            category_id=el.id,
        ))
        # Split-rad pa kombinerad faktura
        tx2 = Transaction(
            account_id=acc.id, date=date(2026, 1, 20),
            amount=Decimal("-1200"), currency="SEK",
            raw_description="Hjo Energi kombinerad", hash="e2",
        )
        s.add(tx2); s.flush()
        s.add(TransactionSplit(
            transaction_id=tx2.id, description="El-del",
            amount=Decimal("800"), category_id=el.id, sort_order=0,
            source="manual",
        ))
        s.commit()

    r = c.get("/utility/breakdown?category=El&month=2026-01")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["category"] == "El"
    assert body["month"] == "2026-01"
    # Total = 900 + 800 = 1700
    assert body["total"] == pytest.approx(1700.0)
    assert len(body["items"]) == 2
    # En tx, en split
    types = {i["type"] for i in body["items"]}
    assert types == {"transaction", "split"}
    # Splits kan inte flyttas via date-patch
    for item in body["items"]:
        if item["type"] == "split":
            assert item["can_move"] is False
        else:
            assert item["can_move"] is True


def test_tibber_endpoints_require_token(client):
    """Utan token ska alla tibber-endpoints returnera 400, inte krascha."""
    c, _ = client
    r1 = c.post("/utility/tibber/test")
    assert r1.status_code == 400
    r2 = c.post("/utility/tibber/sync")
    assert r2.status_code == 400
    r3 = c.get("/utility/tibber/realtime")
    assert r3.status_code == 400
