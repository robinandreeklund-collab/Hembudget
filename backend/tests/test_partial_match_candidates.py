"""Tester för att match-candidates inkluderar partial-matches.

Scenario: Du klickar på en 445 kr-bankrad (del av Amex-faktura 13 445)
och "Matcha manuellt" → fakturan ska finnas med som kandidat med
'match_type=partial'."""
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


def test_small_tx_finds_large_invoice_as_partial(client):
    """Tx på 445 kr ska kunna vara delbetalning av en 13 445 kr faktura."""
    c, SL = client
    from hembudget.db.models import Account, Transaction, UpcomingTransaction
    with SL() as s:
        acc = Account(name="Mat", bank="nordea", type="shared")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 2, 20),
            amount=Decimal("-445"), currency="SEK",
            raw_description="BG American Exp", hash="h1",
        )
        s.add(tx); s.flush()
        up = UpcomingTransaction(
            kind="bill", name="Amex-faktura",
            amount=Decimal("13445"),
            expected_date=date(2026, 2, 27),
        )
        s.add(up); s.commit()
        tx_id, up_id = tx.id, up.id

    r = c.get(f"/transactions/{tx_id}/match-candidates")
    assert r.status_code == 200
    cands = r.json()["candidates"]
    amex = next((c for c in cands if c["id"] == up_id), None)
    assert amex is not None
    assert amex["match_type"] == "partial"
    assert amex["remaining_amount"] == pytest.approx(13445.0)
    assert amex["amount"] == pytest.approx(13445.0)


def test_partial_candidate_shows_remaining_after_first_payment(client):
    """Efter delbetalning 13 000 har upcomingen bara 445 kvar —
    remaining_amount ska reflektera det."""
    c, SL = client
    from hembudget.db.models import (
        Account, Transaction, UpcomingTransaction, UpcomingPayment,
    )
    with SL() as s:
        acc = Account(name="Mat", bank="nordea", type="shared")
        s.add(acc); s.flush()
        tx_first = Transaction(
            account_id=acc.id, date=date(2026, 2, 27),
            amount=Decimal("-13000"), currency="SEK",
            raw_description="BG Amex", hash="h1",
        )
        tx_second = Transaction(
            account_id=acc.id, date=date(2026, 2, 20),
            amount=Decimal("-445"), currency="SEK",
            raw_description="BG Amex", hash="h2",
        )
        s.add_all([tx_first, tx_second]); s.flush()
        up = UpcomingTransaction(
            kind="bill", name="Amex",
            amount=Decimal("13445"),
            expected_date=date(2026, 2, 27),
        )
        s.add(up); s.flush()
        # Första delbetalningen redan registrerad
        s.add(UpcomingPayment(upcoming_id=up.id, transaction_id=tx_first.id))
        s.commit()
        tx_second_id, up_id = tx_second.id, up.id

    r = c.get(f"/transactions/{tx_second_id}/match-candidates")
    cands = r.json()["candidates"]
    amex = next((c for c in cands if c["id"] == up_id), None)
    assert amex is not None
    assert amex["match_type"] == "partial"
    assert amex["paid_amount"] == pytest.approx(13000.0)
    assert amex["remaining_amount"] == pytest.approx(445.0)
    # Denna 445-tx matchar perfekt den återstående summan
    # (remaining 445, tx 445 → amount_diff inte relevant för partial)


def test_partial_only_same_sign(client):
    """En positiv tx (inkomst) ska INTE matchas som delbetalning av
    en bill (som är negativ)."""
    c, SL = client
    from hembudget.db.models import Account, Transaction, UpcomingTransaction
    with SL() as s:
        acc = Account(name="X", bank="nordea", type="checking")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 2, 27),
            amount=Decimal("500"),  # positiv
            currency="SEK",
            raw_description="Återbetalning", hash="h1",
        )
        s.add(tx); s.flush()
        up = UpcomingTransaction(
            kind="bill", name="Bill", amount=Decimal("1000"),
            expected_date=date(2026, 2, 27),
        )
        s.add(up); s.commit()
        tx_id, up_id = tx.id, up.id

    r = c.get(f"/transactions/{tx_id}/match-candidates")
    cands = r.json()["candidates"]
    # Upcomingen har kind=bill men tx har positiv amount — ska filtreras bort
    assert not any(c["id"] == up_id for c in cands)


def test_full_match_preferred_over_partial(client):
    """Om både fullmatch och partial-match finns, ska fullmatch rankas först."""
    c, SL = client
    from hembudget.db.models import Account, Transaction, UpcomingTransaction
    with SL() as s:
        acc = Account(name="X", bank="nordea", type="checking")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 2, 27),
            amount=Decimal("-1000"), currency="SEK",
            raw_description="X", hash="h1",
        )
        s.add(tx); s.flush()
        # Exakt match 1000 kr
        full = UpcomingTransaction(
            kind="bill", name="Exakt", amount=Decimal("1000"),
            expected_date=date(2026, 2, 27),
        )
        # Större faktura som 1000 skulle vara partial mot
        partial = UpcomingTransaction(
            kind="bill", name="Större", amount=Decimal("5000"),
            expected_date=date(2026, 2, 27),
        )
        s.add_all([full, partial]); s.commit()
        tx_id, full_id = tx.id, full.id

    r = c.get(f"/transactions/{tx_id}/match-candidates")
    cands = r.json()["candidates"]
    assert cands[0]["id"] == full_id  # fullmatch först
    assert cands[0]["match_type"] == "full"


def test_matching_partial_updates_paid_amount(client):
    """End-to-end: välj bill som partial-match, POST match-upcoming →
    upcoming.paid_amount växer, status partial."""
    c, SL = client
    from hembudget.db.models import Account, Transaction, UpcomingTransaction
    with SL() as s:
        acc = Account(name="Mat", bank="nordea", type="shared")
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 2, 20),
            amount=Decimal("-445"), currency="SEK",
            raw_description="BG Amex", hash="h1",
        )
        s.add(tx); s.flush()
        up = UpcomingTransaction(
            kind="bill", name="Amex",
            amount=Decimal("13445"),
            expected_date=date(2026, 2, 27),
        )
        s.add(up); s.commit()
        tx_id, up_id = tx.id, up.id

    # Matcha 445-tx mot 13445-upcoming som delbetalning
    r = c.post(
        f"/transactions/{tx_id}/match-upcoming",
        json={"upcoming_id": up_id},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["paid_amount"] == pytest.approx(445.0)
    assert body["remaining_amount"] == pytest.approx(13000.0)
    assert body["status"] == "partial"
