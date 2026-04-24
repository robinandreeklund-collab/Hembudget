"""Tester för many-to-one invoice matching + batch-counterpart."""
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


# ---------- Many-to-one matching ----------


def test_invoice_paid_in_two_parts_shows_partial_then_paid(client):
    """Amex-faktura 13 445 kr betalas i två delar: 5 000 + 8 445."""
    c, SL = client
    from hembudget.db.models import Account, Transaction, UpcomingTransaction

    with SL() as s:
        acc = Account(name="Lön", bank="nordea", type="checking")
        s.add(acc); s.flush()
        # Två bankrader som tillsammans utgör betalningen
        tx1 = Transaction(
            account_id=acc.id, date=date(2026, 2, 15),
            amount=Decimal("-5000"), currency="SEK",
            raw_description="Amex del 1", hash="h1",
        )
        tx2 = Transaction(
            account_id=acc.id, date=date(2026, 2, 27),
            amount=Decimal("-8445"), currency="SEK",
            raw_description="Amex del 2", hash="h2",
        )
        s.add_all([tx1, tx2]); s.flush()
        up = UpcomingTransaction(
            kind="bill", name="Amex-faktura",
            amount=Decimal("13445"),
            expected_date=date(2026, 2, 27),
            debit_account_id=acc.id, source="pdf_parser",
        )
        s.add(up); s.commit()
        tx1_id, tx2_id, up_id = tx1.id, tx2.id, up.id

    # Koppla första delbetalningen
    r = c.post(
        f"/transactions/{tx1_id}/match-upcoming",
        json={"upcoming_id": up_id},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "partial"
    assert body["paid_amount"] == pytest.approx(5000.0)
    assert body["remaining_amount"] == pytest.approx(8445.0)

    # Koppla andra delen — nu ska det vara fullt betalt
    r = c.post(
        f"/transactions/{tx2_id}/match-upcoming",
        json={"upcoming_id": up_id},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "paid"
    assert body["paid_amount"] == pytest.approx(13445.0)
    assert abs(body["remaining_amount"]) < 2.0

    # Verify via /upcoming list
    r = c.get("/upcoming/?only_future=false")
    ups = r.json()
    u = next(x for x in ups if x["id"] == up_id)
    assert u["payment_status"] == "paid"
    assert len(u["payment_tx_ids"]) == 2
    assert set(u["payment_tx_ids"]) == {tx1_id, tx2_id}


def test_unmatch_one_of_several_payments(client):
    """När man unmatch:ar en av två delbetalningar ska den andra vara kvar."""
    c, SL = client
    from hembudget.db.models import Account, Transaction, UpcomingTransaction

    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        tx1 = Transaction(
            account_id=acc.id, date=date(2026, 2, 1),
            amount=Decimal("-500"), currency="SEK",
            raw_description="d1", hash="h1",
        )
        tx2 = Transaction(
            account_id=acc.id, date=date(2026, 2, 15),
            amount=Decimal("-500"), currency="SEK",
            raw_description="d2", hash="h2",
        )
        s.add_all([tx1, tx2]); s.flush()
        up = UpcomingTransaction(
            kind="bill", name="X", amount=Decimal("1000"),
            expected_date=date(2026, 2, 15),
            debit_account_id=acc.id,
        )
        s.add(up); s.commit()
        tx1_id, tx2_id, up_id = tx1.id, tx2.id, up.id

    c.post(f"/transactions/{tx1_id}/match-upcoming", json={"upcoming_id": up_id})
    c.post(f"/transactions/{tx2_id}/match-upcoming", json={"upcoming_id": up_id})

    # Unmatch tx1 → kvarvarande payment = tx2
    r = c.post(f"/transactions/{tx1_id}/unmatch-upcoming")
    assert r.status_code == 200

    r = c.get("/upcoming/?only_future=false")
    u = next(x for x in r.json() if x["id"] == up_id)
    assert u["payment_tx_ids"] == [tx2_id]
    assert u["paid_amount"] == pytest.approx(500.0)
    assert u["payment_status"] == "partial"


def test_upcoming_out_includes_payment_fields_for_unmatched(client):
    c, SL = client
    from hembudget.db.models import UpcomingTransaction
    with SL() as s:
        s.add(UpcomingTransaction(
            kind="bill", name="Test",
            amount=Decimal("1000"),
            expected_date=date(2026, 3, 1),
        ))
        s.commit()

    r = c.get("/upcoming/?only_future=false")
    u = r.json()[0]
    assert u["payment_status"] == "unpaid"
    assert u["paid_amount"] == 0
    assert u["payment_tx_ids"] == []


# ---------- Batch counterparts ----------


def test_batch_create_counterparts_for_all_orphans(client):
    """Kör '/transfers/batch-create-counterparts' med partnerns inkognito
    som mål → alla orphans får motparter och paras."""
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        shared = Account(name="Gemensamt", bank="nordea", type="shared")
        incog = Account(
            name="Evelina priv", bank="nordea", type="checking",
            incognito=True,
        )
        s.add_all([shared, incog]); s.flush()
        shared_id, incog_id = shared.id, incog.id
        # Tre orphan-transfers på gemensamt
        for i, (d, amt) in enumerate([
            (date(2026, 1, 5), 5000),
            (date(2026, 2, 5), 8000),
            (date(2026, 3, 5), 12000),
        ]):
            s.add(Transaction(
                account_id=shared_id, date=d,
                amount=Decimal(str(amt)), currency="SEK",
                raw_description=f"Insättning {i}", hash=f"h{i}",
                is_transfer=True,
            ))
        s.commit()

    r = c.post("/transfers/batch-create-counterparts", json={
        "target_account_id": incog_id,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["orphans_processed"] == 3
    assert body["counterparts_created"] == 3

    # Verifiera via /transfers/unpaired — ska nu vara 0
    r = c.get("/transfers/unpaired")
    assert r.json()["count"] == 0

    # Parade ska nu vara 3
    r = c.get("/transfers/paired")
    assert r.json()["count"] == 3


def test_batch_skips_orphans_already_on_target(client):
    """Om en orphan redan ligger på target-kontot ska den INTE skapas
    som duplikat."""
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        incog = Account(name="Priv", bank="nordea", type="checking", incognito=True)
        s.add(incog); s.flush()
        incog_id = incog.id
        # En orphan direkt på target-kontot (skulle kunna bli självreferens)
        s.add(Transaction(
            account_id=incog_id, date=date(2026, 1, 1),
            amount=Decimal("1000"), currency="SEK",
            raw_description="X", hash="h1", is_transfer=True,
        ))
        s.commit()

    r = c.post("/transfers/batch-create-counterparts", json={
        "target_account_id": incog_id,
    })
    assert r.json()["orphans_processed"] == 0


def test_batch_400_without_target(client):
    c, _ = client
    r = c.post("/transfers/batch-create-counterparts", json={})
    assert r.status_code == 400


def test_batch_404_for_unknown_target(client):
    c, _ = client
    r = c.post("/transfers/batch-create-counterparts", json={
        "target_account_id": 99999,
    })
    assert r.status_code == 404
