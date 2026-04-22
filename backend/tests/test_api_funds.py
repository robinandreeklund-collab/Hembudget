"""HTTP-test för /funds — fondinnehav per ISK/fondkonto.

Vision-endpointen testas inte här (kräver LM Studio); vi testar istället
det deterministiska värdet av upsert-logiken via /funds/{acc}/update.
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


def _make_isk_account(SessionLocal) -> int:
    from hembudget.db.models import Account
    with SessionLocal() as s:
        acc = Account(name="ISK BAS", bank="nordea", type="isk", currency="SEK")
        s.add(acc); s.commit(); s.refresh(acc)
        return acc.id


def test_update_holding_creates_and_snapshots(client):
    c, SessionLocal = client
    acc_id = _make_isk_account(SessionLocal)

    r = c.post(f"/funds/{acc_id}/update", json={
        "fund_name": "Nordea Stratega 70",
        "units": "17.97",
        "market_value": "8415.70",
        "last_price": "468.39",
        "change_pct": 20.22,
        "change_value": "1415.70",
        "day_change_pct": -0.05,
        "snapshot_date": "2026-04-22",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fund_name"] == "Nordea Stratega 70"
    assert float(body["market_value"]) == pytest.approx(8415.70)
    assert float(body["last_price"]) == pytest.approx(468.39)

    # Andra uppdatering samma datum → upsert på både aktuell rad och snapshot
    r2 = c.post(f"/funds/{acc_id}/update", json={
        "fund_name": "Nordea Stratega 70",
        "units": "17.97",
        "market_value": "8500.00",
        "snapshot_date": "2026-04-22",
    })
    assert r2.status_code == 200

    # Summary ska visa ett innehav med uppdaterat värde
    r = c.get(f"/funds/{acc_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["fund_count"] == 1
    assert float(body["total_value"]) == pytest.approx(8500.00)
    assert body["last_update_date"] == "2026-04-22"

    # Två datum → två snapshots
    c.post(f"/funds/{acc_id}/update", json={
        "fund_name": "Nordea Stratega 70",
        "market_value": "8600.00",
        "snapshot_date": "2026-05-15",
    })
    r = c.get(
        f"/funds/{acc_id}/history",
        params={"fund_name": "Nordea Stratega 70"},
    )
    assert r.status_code == 200
    points = r.json()["points"]
    assert len(points) == 2
    assert points[0]["date"] == "2026-04-22"
    assert points[1]["date"] == "2026-05-15"
    assert float(points[1]["market_value"]) == pytest.approx(8600.00)


def test_summary_aggregates_multiple_funds(client):
    c, SessionLocal = client
    acc_id = _make_isk_account(SessionLocal)

    funds = [
        ("Nordea Framtidsfond", "5674.16"),
        ("Nordea Kinafond", "17653.48"),
        ("Nordea Stratega 70", "8415.70"),
    ]
    for name, value in funds:
        c.post(f"/funds/{acc_id}/update", json={
            "fund_name": name,
            "market_value": value,
            "snapshot_date": "2026-04-22",
        })

    r = c.get(f"/funds/{acc_id}")
    body = r.json()
    assert body["fund_count"] == 3
    expected_total = Decimal("5674.16") + Decimal("17653.48") + Decimal("8415.70")
    assert float(body["total_value"]) == pytest.approx(float(expected_total))

    # Största innehav först
    assert body["holdings"][0]["fund_name"] == "Nordea Kinafond"

    # Aggregerad historik per datum
    r = c.get(f"/funds/{acc_id}/history")
    points = r.json()["points"]
    assert len(points) == 1
    assert points[0]["date"] == "2026-04-22"
    assert float(points[0]["market_value"]) == pytest.approx(float(expected_total))


def test_unknown_account_returns_404(client):
    c, _ = client
    r = c.get("/funds/9999")
    assert r.status_code == 404

    r = c.post("/funds/9999/update", json={
        "fund_name": "Test", "market_value": "100",
    })
    assert r.status_code == 404
