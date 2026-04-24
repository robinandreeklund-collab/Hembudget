"""Tester för inkognito-konton.

Verifierar att inkognito-konton:
- Har en boolean-flagga på Account
- Exkluderas från total_balance i /balances/
- Exkluderas från total_assets + net_worth i /ledger/
- Private utgifter räknas INTE i månads-summary, family-breakdown eller
  ledger resultaträkning
- MEN inkomster (lön) räknas fortfarande
- Överföringar fungerar som vanligt (transfer-detektorn kopplar dem)
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


def test_create_account_with_incognito_flag(client):
    c, SL = client
    r = c.post("/accounts", json={
        "name": "Evelinas privata", "bank": "nordea", "type": "checking",
        "incognito": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["incognito"] is True

    from hembudget.db.models import Account
    with SL() as s:
        a = s.get(Account, body["id"])
        assert a.incognito is True


def test_toggle_incognito_via_patch(client):
    c, SL = client
    acc = c.post("/accounts", json={
        "name": "X", "bank": "nordea", "type": "checking",
    }).json()
    assert acc["incognito"] is False

    r = c.patch(f"/accounts/{acc['id']}", json={"incognito": True})
    assert r.status_code == 200
    assert r.json()["incognito"] is True


def test_incognito_excluded_from_total_balance(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        regular = Account(
            name="Gemensamt", bank="nordea", type="checking",
            opening_balance=Decimal("10000"),
            opening_balance_date=date(2025, 12, 31),
        )
        incog = Account(
            name="Evelinas privata", bank="nordea", type="checking",
            opening_balance=Decimal("50000"),
            opening_balance_date=date(2025, 12, 31),
            incognito=True,
        )
        s.add_all([regular, incog]); s.commit()

    r = c.get("/balances/")
    body = r.json()
    # Båda listas
    assert len(body["accounts"]) == 2
    incog_row = next(a for a in body["accounts"] if a["incognito"])
    assert incog_row["current_balance"] == pytest.approx(50000.0)
    # MEN total räknar bara det vanliga kontot
    assert body["total_balance"] == pytest.approx(10000.0)


def test_incognito_income_counts_but_expenses_ignored_in_monthly_summary(client):
    """Partnerns lön (income) ska synas i månadsöversikten. Hennes privata
    utgifter ska INTE göra det."""
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        incog = Account(
            name="Evelina priv", bank="nordea", type="checking",
            incognito=True,
        )
        s.add(incog); s.flush()
        # Hennes lön (income) — 30 000
        s.add(Transaction(
            account_id=incog.id, date=date(2026, 3, 25),
            amount=Decimal("30000"), currency="SEK",
            raw_description="Lön", hash="h-lon",
        ))
        # Hennes privata kläder — 2 500 (ska IGNORERAS)
        s.add(Transaction(
            account_id=incog.id, date=date(2026, 3, 10),
            amount=Decimal("-2500"), currency="SEK",
            raw_description="H&M", hash="h-klader",
        ))
        s.commit()

    r = c.get("/budget/2026-03")
    body = r.json()
    # Income: 30k (lön, syns)
    assert float(body["income"]) == pytest.approx(30000.0)
    # Expenses: 0 (kläderna exkluderas)
    assert float(body["expenses"]) == pytest.approx(0.0)


def test_incognito_excluded_from_ledger_assets(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        regular = Account(
            name="Gemensamt", bank="nordea", type="checking",
            opening_balance=Decimal("10000"),
            opening_balance_date=date(2025, 12, 31),
        )
        incog = Account(
            name="Priv", bank="nordea", type="checking",
            opening_balance=Decimal("99999"),
            opening_balance_date=date(2025, 12, 31),
            incognito=True,
        )
        s.add_all([regular, incog]); s.commit()

    r = c.get("/ledger/?year=2026")
    body = r.json()
    # Assets = 10 000 (bara regular)
    assert body["totals"]["assets"] == pytest.approx(10000.0)
    # Båda accounts listas
    incog_row = next(a for a in body["accounts"] if a["name"] == "Priv")
    assert incog_row["incognito"] is True


def test_incognito_expenses_excluded_from_ledger_categories(client):
    c, SL = client
    from hembudget.db.models import Account, Category, Transaction
    with SL() as s:
        klader = Category(name="Kläder & Skor", parent_id=None)
        lon = Category(name="Lön", parent_id=None)
        s.add_all([klader, lon]); s.flush()
        incog = Account(
            name="Priv", bank="nordea", type="checking", incognito=True,
        )
        s.add(incog); s.flush()
        # Hennes lön
        s.add(Transaction(
            account_id=incog.id, date=date(2026, 3, 25),
            amount=Decimal("30000"), currency="SEK",
            raw_description="Lön", hash="h1", category_id=lon.id,
        ))
        # Hennes privata inköp — ska exkluderas
        s.add(Transaction(
            account_id=incog.id, date=date(2026, 3, 10),
            amount=Decimal("-2500"), currency="SEK",
            raw_description="H&M", hash="h2", category_id=klader.id,
        ))
        s.commit()

    r = c.get("/ledger/?year=2026")
    body = r.json()
    cats = {c["category"]: c for c in body["categories"]}
    # Lön-kategori syns
    assert "Lön" in cats
    assert cats["Lön"]["income"] == pytest.approx(30000.0)
    # Kläder-kategori syns INTE eftersom inköpet var på inkognito-konto
    assert "Kläder & Skor" not in cats


def test_incognito_expenses_excluded_from_family_breakdown(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction, User
    with SL() as s:
        eve = User(name="Evelina")
        s.add(eve); s.flush()
        incog = Account(
            name="Eve priv", bank="nordea", type="checking",
            owner_id=eve.id, incognito=True,
        )
        s.add(incog); s.flush()
        s.add(Transaction(
            account_id=incog.id, date=date(2026, 3, 25),
            amount=Decimal("30000"), currency="SEK",
            raw_description="Lön", hash="h1",
        ))
        s.add(Transaction(
            account_id=incog.id, date=date(2026, 3, 10),
            amount=Decimal("-5000"), currency="SEK",
            raw_description="Privat", hash="h2",
        ))
        s.commit()

    r = c.get("/budget/family/2026-03")
    body = r.json()
    eve_bucket = body["by_owner"].get(f"user_{eve.id}")
    assert eve_bucket is not None
    assert eve_bucket["income"] == pytest.approx(30000.0)
    # Expenses = 0 eftersom 5k var på inkognito-konto
    assert eve_bucket["expenses"] == pytest.approx(0.0)


def test_transfer_detection_works_across_incognito_accounts(client):
    """Partnerns överföring från hennes inkognito-konto till gemensamma
    ska paras ihop som transfer — båda sidor flaggas som transfer."""
    c, SL = client
    from hembudget.db.models import Account, Transaction
    from hembudget.transfers.detector import TransferDetector

    with SL() as s:
        shared = Account(name="Gemensamt", bank="nordea", type="shared")
        incog = Account(
            name="Eve priv", bank="nordea", type="checking", incognito=True,
        )
        s.add_all([shared, incog]); s.flush()
        # Hon överför -10 000 från sitt privata
        tx_out = Transaction(
            account_id=incog.id, date=date(2026, 4, 5),
            amount=Decimal("-10000"), currency="SEK",
            raw_description="Till gemensamt", hash="h1",
        )
        # Motsvarande +10 000 dyker upp på gemensamma
        tx_in = Transaction(
            account_id=shared.id, date=date(2026, 4, 5),
            amount=Decimal("10000"), currency="SEK",
            raw_description="Från Evelina", hash="h2",
        )
        s.add_all([tx_out, tx_in]); s.commit()

        # Kör transfer-detektorn
        d = TransferDetector(s)
        result = d.detect_internal_transfers()
        s.commit()

        # Både hennes utgående och gemensamma inkommande ska vara markerade
        s.refresh(tx_out)
        s.refresh(tx_in)
        assert tx_out.is_transfer is True
        assert tx_in.is_transfer is True
