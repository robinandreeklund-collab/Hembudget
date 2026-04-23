"""Test för /transfers/link-bulk — bulk-pairing av "säkra" förslag.

Användsfall: kreditkortsbetalningar som auto-detektorn missade — typiskt
en negativ rad på checking och en positiv rad på kreditkortet med
exakt samma belopp och samma dag. Användaren får en knapp "Para alla
säkra" som ringer denna endpoint i ett svep istället för att klicka
"Para ihop" 20+ gånger.
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


def _seed_credit_card_payments(SL):
    """Tre kreditkort-betalningar: en på checking, motsvarighet på Amex.
    Inget av detta är markerat som transfer ännu — auto-detektorn missade."""
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        chk = Account(name="Checking", bank="nordea", type="checking")
        amex = Account(name="Amex", bank="amex", type="credit")
        s.add_all([chk, amex]); s.flush()

        tx_pairs: list[tuple[int, int]] = []
        for i, (d, amt) in enumerate([
            (date(2026, 1, 25), Decimal("5000")),
            (date(2026, 2, 25), Decimal("7500")),
            (date(2026, 3, 25), Decimal("3200")),
        ]):
            chk_tx = Transaction(
                account_id=chk.id, date=d, amount=-amt, currency="SEK",
                raw_description=f"Betalning Amex {i}", hash=f"chk{i}",
            )
            amex_tx = Transaction(
                account_id=amex.id, date=d, amount=amt, currency="SEK",
                raw_description=f"Inbetalning {i}", hash=f"amex{i}",
            )
            s.add_all([chk_tx, amex_tx]); s.flush()
            tx_pairs.append((chk_tx.id, amex_tx.id))
        s.commit()
        return tx_pairs


def test_bulk_link_pairs_all_safe_suggestions(client):
    c, SL = client
    pairs = _seed_credit_card_payments(SL)

    r = c.post("/transfers/link-bulk", json={
        "pairs": [{"tx_a_id": a, "tx_b_id": b} for a, b in pairs],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["linked"] == 3
    assert body["skipped"] == 0
    assert body["errors"] == []

    # Verifiera att alla nu är parade och flaggade som transfer
    paired = c.get("/transfers/paired").json()
    assert paired["count"] == 3


def test_bulk_link_skips_already_paired(client):
    """Idempotent: körs två gånger ska andra körningen skip:a allt."""
    c, SL = client
    pairs = _seed_credit_card_payments(SL)
    payload = {"pairs": [{"tx_a_id": a, "tx_b_id": b} for a, b in pairs]}

    r1 = c.post("/transfers/link-bulk", json=payload)
    assert r1.json()["linked"] == 3
    r2 = c.post("/transfers/link-bulk", json=payload)
    assert r2.json()["linked"] == 0
    assert r2.json()["skipped"] == 3


def test_bulk_link_returns_errors_for_invalid_ids(client):
    """Saknade tx_id rapporteras per par utan att hela bulken kraschar."""
    c, SL = client
    pairs = _seed_credit_card_payments(SL)

    payload = {
        "pairs": [
            {"tx_a_id": pairs[0][0], "tx_b_id": pairs[0][1]},  # OK
            {"tx_a_id": 99999, "tx_b_id": 88888},  # finns inte
        ],
    }
    r = c.post("/transfers/link-bulk", json=payload)
    body = r.json()
    assert body["linked"] == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["error"] == "not_found"
