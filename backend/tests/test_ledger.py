"""Tester för huvudbok-endpointen (/ledger/)."""
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


def test_ledger_empty_returns_structure(client):
    c, _ = client
    r = c.get("/ledger/?year=2026")
    assert r.status_code == 200
    body = r.json()
    assert body["period"]["start"] == "2026-01-01"
    assert body["period"]["end"] == "2027-01-01"
    assert body["accounts"] == []
    assert body["categories"] == []
    assert body["totals"]["income"] == 0
    assert body["totals"]["expenses"] == 0


def test_ledger_opening_balance_plus_movements_equals_closing(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(
            name="Löner", bank="nordea", type="checking",
            opening_balance=Decimal("10000"),
            opening_balance_date=date(2025, 12, 31),
        )
        s.add(acc); s.flush()
        # Inom perioden: +35 000 (lön) - 3 000 (el)
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 1, 25),
            amount=Decimal("35000"), currency="SEK",
            raw_description="Inkab", hash="h1",
        ))
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 1, 27),
            amount=Decimal("-3000"), currency="SEK",
            raw_description="Hjo Energi", hash="h2",
        ))
        s.commit()

    r = c.get("/ledger/?month=2026-01")
    body = r.json()
    assert len(body["accounts"]) == 1
    a = body["accounts"][0]
    assert a["opening_balance"] == pytest.approx(10000.0)
    assert a["income"] == pytest.approx(35000.0)
    assert a["expenses"] == pytest.approx(3000.0)
    # 10000 + 35000 - 3000 = 42000
    assert a["closing_balance"] == pytest.approx(42000.0)
    assert a["transaction_count"] == 2


def test_ledger_transfers_separate_from_income_expense(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc1 = Account(name="Lön", bank="nordea", type="checking")
        acc2 = Account(name="Spar", bank="nordea", type="savings")
        s.add_all([acc1, acc2]); s.flush()
        # Överföring 5000 från acc1 till acc2, markerad som transfer
        s.add(Transaction(
            account_id=acc1.id, date=date(2026, 2, 1),
            amount=Decimal("-5000"), currency="SEK",
            raw_description="Överföring till spar", hash="t1",
            is_transfer=True,
        ))
        s.add(Transaction(
            account_id=acc2.id, date=date(2026, 2, 1),
            amount=Decimal("5000"), currency="SEK",
            raw_description="Insättning från lön", hash="t2",
            is_transfer=True,
        ))
        s.commit()

    r = c.get("/ledger/?month=2026-02")
    body = r.json()
    accs = {a["name"]: a for a in body["accounts"]}
    # Acc1: transfer_out = 5000, expenses = 0
    assert accs["Lön"]["expenses"] == 0
    assert accs["Lön"]["transfer_out"] == pytest.approx(5000.0)
    # Acc2: transfer_in = 5000, income = 0
    assert accs["Spar"]["income"] == 0
    assert accs["Spar"]["transfer_in"] == pytest.approx(5000.0)

    # Transfer-check ska vara OK (båda sidor balanserar)
    transfer_check = next(
        c for c in body["checks"] if "verföringar" in c["name"]
    )
    assert transfer_check["passed"] is True
    assert abs(transfer_check["value"]) < 1.0


def test_ledger_categorization_check_flags_uncategorized(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        # En okategoriserad transaktion
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 3, 1),
            amount=Decimal("-100"), currency="SEK",
            raw_description="okänd", hash="h1",
        ))
        s.commit()

    r = c.get("/ledger/?month=2026-03")
    body = r.json()
    cat_check = next(
        c for c in body["checks"] if "ategorisera" in c["name"]
    )
    assert cat_check["passed"] is False
    assert cat_check["value"] == 1


def test_ledger_categories_aggregates_income_and_expenses(client):
    c, SL = client
    from hembudget.db.models import Account, Category, Transaction
    with SL() as s:
        lon = Category(name="Lön", parent_id=None)
        mat = Category(name="Livsmedel", parent_id=None)
        s.add_all([lon, mat]); s.flush()
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 1, 25),
            amount=Decimal("35000"), currency="SEK",
            raw_description="Inkab", hash="h1", category_id=lon.id,
        ))
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 1, 10),
            amount=Decimal("-2500"), currency="SEK",
            raw_description="ICA", hash="h2", category_id=mat.id,
        ))
        s.commit()

    r = c.get("/ledger/?year=2026")
    body = r.json()
    cats = {c["category"]: c for c in body["categories"]}
    assert cats["Lön"]["income"] == pytest.approx(35000.0)
    assert cats["Lön"]["expenses"] == 0
    assert cats["Livsmedel"]["expenses"] == pytest.approx(2500.0)
    assert cats["Livsmedel"]["income"] == 0

    # Totals
    assert body["totals"]["income"] == pytest.approx(35000.0)
    assert body["totals"]["expenses"] == pytest.approx(2500.0)
    assert body["totals"]["net_result"] == pytest.approx(32500.0)


def test_ledger_upcoming_summary_counts_matched_vs_unmatched(client):
    c, SL = client
    from hembudget.db.models import (
        Account, Transaction, UpcomingPayment, UpcomingTransaction,
    )
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 1, 27),
            amount=Decimal("-3000"), currency="SEK",
            raw_description="Elräkning", hash="h1",
        )
        s.add(tx); s.flush()
        # Matchad (fullt betald — UpcomingPayment räknas nu, inte bara
        # matched_transaction_id, så vi måste skapa junction-rad)
        up_paid = UpcomingTransaction(
            kind="bill", name="El", amount=Decimal("3000"),
            expected_date=date(2026, 1, 27),
            matched_transaction_id=tx.id,
        )
        s.add(up_paid); s.flush()
        s.add(UpcomingPayment(upcoming_id=up_paid.id, transaction_id=tx.id))
        # Omatchad
        s.add(UpcomingTransaction(
            kind="bill", name="Bredband", amount=Decimal("500"),
            expected_date=date(2026, 1, 15),
        ))
        s.commit()

    r = c.get("/ledger/?month=2026-01")
    body = r.json()
    up = body["upcoming_summary"]
    assert up["total"] == 2
    assert up["matched"] == 1
    assert up["unmatched"] == 1
    assert up["matched_sum"] == pytest.approx(3000.0)
    assert up["unmatched_sum"] == pytest.approx(500.0)


def test_ledger_partial_upcoming_counts_as_unmatched_with_remaining(client):
    """Regression: delbetalda fakturor ska räknas som unmatched (de är
    inte klara) och unmatched_sum ska använda ÅTERSTÅENDE belopp — inte
    ursprungsbeloppet — så översikten speglar vad som faktiskt är kvar
    att betala."""
    c, SL = client
    from hembudget.db.models import (
        Account, Transaction, UpcomingPayment, UpcomingTransaction,
    )
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        # Delbetalning 2 000 kr på Amex-faktura 27 000 kr
        tx = Transaction(
            account_id=acc.id, date=date(2026, 1, 10),
            amount=Decimal("-2000"), currency="SEK",
            raw_description="Amex delbet", hash="h_amex",
        )
        s.add(tx); s.flush()
        up = UpcomingTransaction(
            kind="bill", name="Amex januari", amount=Decimal("27000"),
            expected_date=date(2026, 1, 25),
            matched_transaction_id=tx.id,
        )
        s.add(up); s.flush()
        s.add(UpcomingPayment(upcoming_id=up.id, transaction_id=tx.id))
        s.commit()

    r = c.get("/ledger/?month=2026-01")
    body = r.json()
    summary = body["upcoming_summary"]
    # Delbetald räknas som unmatched eftersom fakturan ej är klar
    assert summary["matched"] == 0
    assert summary["unmatched"] == 1
    # unmatched_sum = ÅTERSTÅENDE, inte 27 000
    assert summary["unmatched_sum"] == pytest.approx(25000.0)
