"""Tester för /upcoming/{id}/find-bank-tx — bredare sök efter
kandidat-transaktioner när auto-match missade dem."""
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


def test_find_bank_tx_finds_two_part_payment(client):
    """Amex 13 445 kr betalad som 13 000 + 445 på olika dagar.
    find-bank-tx ska hitta båda."""
    c, SL = client
    from hembudget.db.models import Account, Transaction, UpcomingTransaction
    with SL() as s:
        acc = Account(name="Mat", bank="nordea", type="shared")
        s.add(acc); s.flush()
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 2, 20),
            amount=Decimal("-445"), currency="SEK",
            raw_description="BG American Exp", hash="h1",
        ))
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 2, 27),
            amount=Decimal("-13000"), currency="SEK",
            raw_description="BG American Exp", hash="h2",
        ))
        up = UpcomingTransaction(
            kind="bill", name="Kreditkortsfaktura — Amex",
            amount=Decimal("13445"),
            expected_date=date(2026, 2, 27),
        )
        s.add(up); s.commit()
        up_id = up.id

    # Bredare tolerans för att hitta 445 och 13000 (diff mot 13445 är
    # 13000 resp 445, måste vara inom tolerance)
    r = c.get(
        f"/upcoming/{up_id}/find-bank-tx"
        f"?amount_tolerance=15000&date_tolerance_days=14"
    )
    body = r.json()
    cands = body["candidates"]
    assert len(cands) == 2
    amounts = sorted(c["amount"] for c in cands)
    assert amounts == [-13000.0, -445.0]


def test_find_bank_tx_excludes_already_matched(client):
    c, SL = client
    from hembudget.db.models import (
        Account, Transaction, UpcomingTransaction, UpcomingPayment,
    )
    with SL() as s:
        acc = Account(name="X", bank="nordea", type="checking")
        s.add(acc); s.flush()
        tx_used = Transaction(
            account_id=acc.id, date=date(2026, 2, 27),
            amount=Decimal("-1000"), currency="SEK",
            raw_description="Used", hash="h1",
        )
        tx_free = Transaction(
            account_id=acc.id, date=date(2026, 2, 27),
            amount=Decimal("-1000"), currency="SEK",
            raw_description="Free", hash="h2",
        )
        s.add_all([tx_used, tx_free]); s.flush()

        other_up = UpcomingTransaction(
            kind="bill", name="Annan", amount=Decimal("1000"),
            expected_date=date(2026, 2, 27),
        )
        s.add(other_up); s.flush()
        s.add(UpcomingPayment(
            upcoming_id=other_up.id, transaction_id=tx_used.id,
        ))

        target_up = UpcomingTransaction(
            kind="bill", name="Target", amount=Decimal("1000"),
            expected_date=date(2026, 2, 27),
        )
        s.add(target_up); s.commit()
        target_id = target_up.id
        free_id = tx_free.id

    r = c.get(f"/upcoming/{target_id}/find-bank-tx")
    cands = r.json()["candidates"]
    tx_ids = [c["transaction_id"] for c in cands]
    assert free_id in tx_ids
    # tx_used ska vara filtrerad bort
    assert all(c["transaction_id"] != cands[0].get("transaction_id") or
               c["transaction_id"] == free_id for c in cands)


def test_find_bank_tx_marks_exact_matches(client):
    c, SL = client
    from hembudget.db.models import Account, Transaction, UpcomingTransaction
    with SL() as s:
        acc = Account(name="X", bank="nordea", type="checking")
        s.add(acc); s.flush()
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 2, 27),
            amount=Decimal("-1000"), currency="SEK",
            raw_description="Exact", hash="h1",
        ))
        up = UpcomingTransaction(
            kind="bill", name="X", amount=Decimal("1000"),
            expected_date=date(2026, 2, 27),
        )
        s.add(up); s.commit()
        up_id = up.id

    r = c.get(f"/upcoming/{up_id}/find-bank-tx")
    c = r.json()["candidates"][0]
    assert c["exact_match"] is True
    assert c["amount_diff"] < 1


def test_find_bank_tx_404_for_unknown(client):
    c, _ = client
    r = c.get("/upcoming/99999/find-bank-tx")
    assert r.status_code == 404


def test_multi_match_via_match_upcoming_achieves_paid_status(client):
    """Simulera UI-flödet: användaren markerar 2 checkboxar i FindBankTxModal
    och klickar 'Matcha mot 2 rader' → sekventiella POST
    /transactions/{id}/match-upcoming → upcoming blir 'paid'."""
    c, SL = client
    from hembudget.db.models import Account, Transaction, UpcomingTransaction
    with SL() as s:
        acc = Account(name="Mat", bank="nordea", type="shared")
        s.add(acc); s.flush()
        tx1 = Transaction(
            account_id=acc.id, date=date(2026, 2, 20),
            amount=Decimal("-445"), currency="SEK",
            raw_description="d1", hash="h1",
        )
        tx2 = Transaction(
            account_id=acc.id, date=date(2026, 2, 27),
            amount=Decimal("-13000"), currency="SEK",
            raw_description="d2", hash="h2",
        )
        s.add_all([tx1, tx2]); s.flush()
        up = UpcomingTransaction(
            kind="bill", name="Amex",
            amount=Decimal("13445"),
            expected_date=date(2026, 2, 27),
        )
        s.add(up); s.commit()
        tx1_id, tx2_id, up_id = tx1.id, tx2.id, up.id

    c.post(f"/transactions/{tx1_id}/match-upcoming", json={"upcoming_id": up_id})
    r = c.post(
        f"/transactions/{tx2_id}/match-upcoming", json={"upcoming_id": up_id},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "paid"
    assert r.json()["paid_amount"] == pytest.approx(13445.0)
