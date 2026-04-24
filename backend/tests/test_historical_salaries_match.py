"""Bekräftar att historiska löner som läggs in i efterhand auto-matchas
mot befintliga transaktioner i importerade kontoutdrag.
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

    def _db():
        s = SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[api_deps.db] = _db
    with TestClient(app) as c:
        yield c, SessionLocal


def test_multiple_historical_monthly_salaries_auto_match(client):
    """Robin lägger in sina 4 senaste månaders löner manuellt, i efterhand.
    Kontoutdragen har redan importerats. Varje upcoming ska matchas mot
    rätt månads löne-transaktion automatiskt — utan att man måste göra
    nåt extra.
    """
    c, SL = client

    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(
            name="Robin Lönekonto", bank="nordea", type="checking",
            account_number="1709 20 72840",
        )
        s.add(acc); s.flush()

        # 4 månaders historiska löne-transaktioner (från CSV-import)
        # Beloppen varierar lite (semesterersättning etc.) — varje
        # upcoming måste matcha rätt månads belopp.
        salary_tx_ids = {}
        salaries = [
            (date(2026, 1, 25), Decimal("34280.00")),
            (date(2026, 2, 25), Decimal("34430.00")),
            (date(2026, 3, 25), Decimal("34430.00")),
            (date(2026, 4, 25), Decimal("35120.00")),
        ]
        for d, amt in salaries:
            tx = Transaction(
                account_id=acc.id, date=d, amount=amt,
                currency="SEK", raw_description="Lön Inkab",
                hash=f"lon-{d}",
            )
            s.add(tx); s.flush()
            salary_tx_ids[d] = tx.id
        s.commit()

    # Användaren lägger in varje löne-upcoming i efterhand — EN API-request
    # per månad (som UI:t gör när man lägger till via /upcoming/)
    upcoming_ids = []
    for d, amt in [
        (date(2026, 1, 25), 34280),
        (date(2026, 2, 25), 34430),
        (date(2026, 3, 25), 34430),
        (date(2026, 4, 25), 35120),
    ]:
        r = c.post("/upcoming/", json={
            "kind": "income",
            "name": "Inkab",
            "amount": str(amt),
            "expected_date": d.isoformat(),
            "owner": "Robin",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        # Varje ska ha matchats mot rätt månads tx
        assert body["matched_transaction_id"] == salary_tx_ids[d], (
            f"upcoming för {d} matchade tx #{body['matched_transaction_id']} "
            f"istället för #{salary_tx_ids[d]}"
        )
        upcoming_ids.append(body["id"])

    # Alla 4 uppcomings är nu "paid" (matched) — visas inte som kommande
    r = c.get("/upcoming/?only_future=false")
    ups = r.json()
    assert all(u["matched_transaction_id"] is not None for u in ups)


def test_historical_salary_matches_despite_date_drift(client):
    """Löne-datumet varierar lite från månad till månad (löningsdag
    förskjuts om 25:e är lördag). Upcoming anger 25:e men tx är på
    23:e — ska fortfarande matcha (±5 dagars tolerans)."""
    c, SL = client

    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 1, 23),  # Fredag, flyttad fr 25e
            amount=Decimal("30000"), currency="SEK",
            raw_description="Lön", hash="h1",
        )
        s.add(tx); s.flush()
        tx_id = tx.id
        s.commit()

    r = c.post("/upcoming/", json={
        "kind": "income", "name": "Arbetsgivare",
        "amount": "30000", "expected_date": "2026-01-25",
    })
    assert r.status_code == 200
    assert r.json()["matched_transaction_id"] == tx_id


def test_historical_salary_no_match_when_no_matching_tx(client):
    """Om användaren lägger in en historisk lön MEN inga transaktioner
    finns importerade, blir den liggande som omatchad (men räknas ändå
    som inkomst i YTD/family-breakdown enligt föregående fix)."""
    c, _ = client
    r = c.post("/upcoming/", json={
        "kind": "income", "name": "X",
        "amount": "25000", "expected_date": "2026-02-25",
        "owner": "Evelina",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["matched_transaction_id"] is None

    # Den räknas ändå i YTD (manual income counts test från förra commiten)
    r = c.get("/budget/ytd-income")
    ytd = r.json()
    assert ytd["grand_total"] >= 25000.0
