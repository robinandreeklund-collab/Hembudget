"""Tester för manuell match av transaktioner + huvudbok-export."""
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


# ---------- Manual match ----------


def _setup_tx_and_upcomings(SL):
    from hembudget.db.models import Account, Transaction, UpcomingTransaction
    with SL() as s:
        acc = Account(name="Lönekonto", bank="nordea", type="checking")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 3, 25),
            amount=Decimal("35000"), currency="SEK",
            raw_description="Lön mars", hash="h1",
        )
        s.add(tx); s.flush()
        tx_id = tx.id
        # En matchande (income 35000 2026-03-25)
        u1 = UpcomingTransaction(
            kind="income", name="Arbetsgivare",
            amount=Decimal("35000"),
            expected_date=date(2026, 3, 25),
            owner="Robin",
        )
        # En med annan belopp men nära datum
        u2 = UpcomingTransaction(
            kind="income", name="Återbetalning",
            amount=Decimal("1200"),
            expected_date=date(2026, 3, 27),
            owner="Robin",
        )
        # En irrelevant bill
        u3 = UpcomingTransaction(
            kind="bill", name="Elräkning",
            amount=Decimal("3000"),
            expected_date=date(2026, 3, 28),
        )
        s.add_all([u1, u2, u3]); s.commit()
        return tx_id, u1.id, u2.id, u3.id


def test_match_candidates_sorts_exact_match_first(client):
    c, SL = client
    tx_id, u1_id, u2_id, u3_id = _setup_tx_and_upcomings(SL)

    r = c.get(f"/transactions/{tx_id}/match-candidates")
    assert r.status_code == 200
    body = r.json()
    # Default kind=income eftersom tx är positiv
    assert body["kind"] == "income"
    cands = body["candidates"]
    assert len(cands) >= 2
    # Första ska vara exakta matchen (u1 = 35 000 på samma datum)
    assert cands[0]["id"] == u1_id
    assert cands[0]["exact_match"] is True
    assert cands[0]["amount_diff"] == 0
    # u3 (bill) ska INTE vara med när kind=income
    ids = [c["id"] for c in cands]
    assert u3_id not in ids


def test_match_candidates_kind_bill_shows_only_bills(client):
    c, SL = client
    tx_id, _, _, u3_id = _setup_tx_and_upcomings(SL)

    r = c.get(f"/transactions/{tx_id}/match-candidates?kind=bill")
    body = r.json()
    ids = [c["id"] for c in body["candidates"]]
    assert u3_id in ids
    # Income-upcomings ska vara filtrerade bort
    assert all(c["kind"] == "bill" for c in body["candidates"])


def test_match_upcoming_links_and_copies_splits(client):
    c, SL = client
    tx_id, u1_id, _, _ = _setup_tx_and_upcomings(SL)

    r = c.post(
        f"/transactions/{tx_id}/match-upcoming",
        json={"upcoming_id": u1_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transaction_id"] == tx_id
    assert body["upcoming_id"] == u1_id

    # Verifiera i DB
    from hembudget.db.models import UpcomingTransaction
    with SL() as s:
        u = s.get(UpcomingTransaction, u1_id)
        assert u.matched_transaction_id == tx_id


def test_match_upcoming_supports_multiple_payments(client):
    """En faktura kan betalas i flera omgångar — t.ex. Amex 13 445 kr
    som betalas 5 000 + 8 445 på två bankdagar. Båda Transactions ska
    kunna kopplas till samma upcoming och bidra till paid_amount."""
    c, SL = client
    tx_id, u1_id, _, _ = _setup_tx_and_upcomings(SL)
    # Första delbetalningen
    r = c.post(f"/transactions/{tx_id}/match-upcoming", json={"upcoming_id": u1_id})
    assert r.status_code == 200
    assert r.json()["status"] == "paid"  # samma belopp → full

    # En andra tx — också 35 000
    from hembudget.db.models import Transaction, Account
    with SL() as s:
        acc = s.query(Account).first()
        tx2 = Transaction(
            account_id=acc.id, date=date(2026, 3, 26),
            amount=Decimal("35000"), currency="SEK",
            raw_description="Annan", hash="h2",
        )
        s.add(tx2); s.commit()
        tx2_id = tx2.id

    r = c.post(
        f"/transactions/{tx2_id}/match-upcoming",
        json={"upcoming_id": u1_id},
    )
    # Nu accepteras ett andra pair (som delbetalning) — blir "overpaid"
    assert r.status_code == 200
    body = r.json()
    assert body["paid_amount"] == pytest.approx(70000.0)  # 35k + 35k
    assert body["status"] == "overpaid"


def test_unmatch_upcoming_frees_it(client):
    c, SL = client
    tx_id, u1_id, _, _ = _setup_tx_and_upcomings(SL)
    c.post(f"/transactions/{tx_id}/match-upcoming", json={"upcoming_id": u1_id})

    r = c.post(f"/transactions/{tx_id}/unmatch-upcoming")
    assert r.status_code == 200
    assert u1_id in r.json()["unmatched"]

    from hembudget.db.models import UpcomingTransaction
    with SL() as s:
        u = s.get(UpcomingTransaction, u1_id)
        assert u.matched_transaction_id is None


def test_match_upcoming_404_for_missing_tx(client):
    c, _ = client
    r = c.post(
        "/transactions/99999/match-upcoming", json={"upcoming_id": 1},
    )
    assert r.status_code == 404


def test_match_upcoming_400_without_upcoming_id(client):
    c, SL = client
    tx_id, _, _, _ = _setup_tx_and_upcomings(SL)
    r = c.post(f"/transactions/{tx_id}/match-upcoming", json={})
    assert r.status_code == 400


# ---------- Ledger export ----------


def test_ledger_yaml_export_returns_valid_yaml(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(name="X", bank="nordea", type="checking")
        s.add(acc); s.flush()
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 1, 15),
            amount=Decimal("-500"), currency="SEK",
            raw_description="Test", hash="h1",
        ))
        s.commit()

    r = c.get("/ledger/export.yaml?year=2026")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-yaml")
    assert "attachment" in r.headers["content-disposition"]
    assert "huvudbok_2026.yaml" in r.headers["content-disposition"]
    # Ska vara giltig YAML
    import yaml
    body = yaml.safe_load(r.text)
    assert "accounts" in body
    assert "totals" in body
    assert body["period"]["label"] == "2026"


def test_ledger_pdf_export_returns_pdf(client):
    c, _ = client
    r = c.get("/ledger/export.pdf?year=2026")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    # PDF magic bytes
    assert r.content.startswith(b"%PDF")


def test_ledger_yaml_month_export(client):
    c, _ = client
    r = c.get("/ledger/export.yaml?month=2026-03")
    assert r.status_code == 200
    import yaml
    body = yaml.safe_load(r.text)
    assert body["period"]["label"] == "2026-03"
    assert body["period"]["start"] == "2026-03-01"
    assert body["period"]["end"] == "2026-04-01"
