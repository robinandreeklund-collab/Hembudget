"""Regressionstest för user report:
'jag delbet. 13000 på amex. den 27. men sen kan jag inte hitta 445 som bankrad'."""
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


def test_find_bank_tx_after_partial_still_shows_remaining_candidate(client):
    """Amex 13 445 · första delbet 13 000 gjord ·
    find-bank-tx ska fortfarande hitta -445 som kandidat."""
    c, SL = client
    from hembudget.db.models import Account, Transaction, UpcomingTransaction
    with SL() as s:
        acc = Account(name="Mat", bank="nordea", type="shared")
        s.add(acc); s.flush()
        tx_partial = Transaction(
            account_id=acc.id, date=date(2026, 2, 27),
            amount=Decimal("-13000"), currency="SEK",
            raw_description="BG American Exp", hash="h1",
            is_transfer=True,
        )
        tx_rest = Transaction(
            account_id=acc.id, date=date(2026, 2, 20),
            amount=Decimal("-445"), currency="SEK",
            raw_description="BG American Exp", hash="h2",
            is_transfer=True,
        )
        s.add_all([tx_partial, tx_rest]); s.flush()
        up = UpcomingTransaction(
            kind="bill", name="Amex-faktura",
            amount=Decimal("13445"),
            expected_date=date(2026, 2, 27),
            source="pdf_parser",
        )
        s.add(up); s.commit()
        tx_partial_id, tx_rest_id, up_id = tx_partial.id, tx_rest.id, up.id

    # Steg 1: användaren klickar Link2 på -13000 tx, matchar mot Amex
    r = c.post(
        f"/transactions/{tx_partial_id}/match-upcoming",
        json={"upcoming_id": up_id},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "partial"
    assert r.json()["paid_amount"] == pytest.approx(13000.0)

    # Steg 2: användaren öppnar "hitta bankrad" på Amex upcoming
    # (frontend kallar find-bank-tx med amount_tolerance=13445)
    r = c.get(
        f"/upcoming/{up_id}/find-bank-tx"
        f"?amount_tolerance=13445&date_tolerance_days=14"
    )
    assert r.status_code == 200
    body = r.json()
    cands = body["candidates"]
    tx_ids = [c["transaction_id"] for c in cands]
    # -13000 ska vara EXKLUDERAD (redan i UpcomingPayment)
    assert tx_partial_id not in tx_ids
    # -445 SKA vara med (användarens bug-rapport: den saknas)
    assert tx_rest_id in tx_ids, (
        f"445-raden försvann! cands={cands}"
    )
