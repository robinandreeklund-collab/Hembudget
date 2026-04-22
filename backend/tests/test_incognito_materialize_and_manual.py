"""Tester för inkognito auto-materialize + manual tx endpoint."""
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


def _setup_user_and_incognito(SL, user_name="Evelina", acc_number="1711 20 07348"):
    from hembudget.db.models import User, Account
    with SL() as s:
        u = User(name=user_name)
        s.add(u); s.flush()
        acc = Account(
            name=f"{user_name} priv", bank="nordea", type="checking",
            account_number=acc_number, owner_id=u.id, incognito=True,
        )
        s.add(acc); s.commit()
        return u.id, acc.id


def test_upcoming_income_auto_materializes_on_incognito_account(client):
    c, SL = client
    user_id, acc_id = _setup_user_and_incognito(SL)

    # Lägg en lön via /upcoming/ med owner="Evelina"
    r = c.post("/upcoming/", json={
        "kind": "income",
        "name": "Inkab",
        "amount": "30000",
        "expected_date": "2026-03-25",
        "owner": "Evelina",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    # Ska vara auto-matchad mot en ny Transaction
    assert body["matched_transaction_id"] is not None

    # Verifiera att Transaction skapades på inkognito-kontot
    from hembudget.db.models import Transaction
    with SL() as s:
        tx = s.get(Transaction, body["matched_transaction_id"])
        assert tx is not None
        assert tx.account_id == acc_id
        assert float(tx.amount) == pytest.approx(30000.0)
        assert tx.date.isoformat() == "2026-03-25"
        assert "Inkab" in tx.raw_description


def test_upcoming_income_owner_case_insensitive(client):
    c, SL = client
    user_id, acc_id = _setup_user_and_incognito(SL, user_name="Evelina")

    r = c.post("/upcoming/", json={
        "kind": "income",
        "name": "VP Capital",
        "amount": "23072",
        "expected_date": "2026-02-25",
        "owner": "EVELINA",  # versaler
    })
    body = r.json()
    assert body["matched_transaction_id"] is not None

    from hembudget.db.models import Transaction
    with SL() as s:
        tx = s.get(Transaction, body["matched_transaction_id"])
        assert tx.account_id == acc_id


def test_upcoming_income_no_incognito_no_materialize(client):
    """Utan inkognito-konto för ägaren ska ingen Transaction skapas."""
    c, SL = client
    # Skapa user men INGET inkognito-konto för hen
    from hembudget.db.models import User
    with SL() as s:
        s.add(User(name="Solo"))
        s.commit()

    r = c.post("/upcoming/", json={
        "kind": "income", "name": "X",
        "amount": "5000", "expected_date": "2026-01-15",
        "owner": "Solo",
    })
    body = r.json()
    # Ingen match (ingen Transaction finns)
    assert body["matched_transaction_id"] is None


def test_upcoming_income_bill_kind_no_auto_materialize(client):
    """Bills ska INTE auto-materialize på inkognito — bara income."""
    c, SL = client
    _setup_user_and_incognito(SL)
    r = c.post("/upcoming/", json={
        "kind": "bill", "name": "Räkning",
        "amount": "1000", "expected_date": "2026-02-01",
        "owner": "Evelina",
    })
    body = r.json()
    assert body["matched_transaction_id"] is None


def test_upcoming_income_already_matched_doesnt_create_duplicate(client):
    """Om upcoming redan matchats (mot befintlig tx) ska vi inte skapa
    en till Transaction på inkognito-kontot."""
    c, SL = client
    user_id, acc_id = _setup_user_and_incognito(SL)

    # Pre-existerande Transaction som matchar
    from hembudget.db.models import Transaction, Account
    with SL() as s:
        # Skapa ett annat konto och lägg en matchande tx där
        other = Account(name="Annat", bank="nordea", type="checking")
        s.add(other); s.flush()
        s.add(Transaction(
            account_id=other.id, date=date(2026, 3, 25),
            amount=Decimal("30000"), currency="SEK",
            raw_description="Lön", hash="pre1",
        ))
        s.commit()

    r = c.post("/upcoming/", json={
        "kind": "income", "name": "Inkab",
        "amount": "30000", "expected_date": "2026-03-25",
        "owner": "Evelina",
    })
    body = r.json()
    # Backfill-match hittade pre-existing tx först
    assert body["matched_transaction_id"] is not None

    # INGEN ny tx ska ha skapats på inkognito-kontot
    from hembudget.db.models import Transaction as _Tx
    with SL() as s:
        count = s.query(_Tx).filter(_Tx.account_id == acc_id).count()
        assert count == 0


# ---------- Manual transaction endpoint ----------


def test_manual_transaction_creates_tx_on_account(client):
    c, SL = client
    _, acc_id = _setup_user_and_incognito(SL)

    r = c.post(f"/accounts/{acc_id}/manual-transaction", json={
        "date": "2026-04-05",
        "amount": -10000,
        "description": "Överföring till gemensamt",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account_id"] == acc_id
    assert float(body["amount"]) == -10000
    assert body["date"] == "2026-04-05"


def test_manual_transaction_paired_as_transfer_with_matching_counterpart(client):
    """När en manuell -10k på inkognito och en +10k på gemensamt finns,
    parar transfer-detektorn dem automatiskt."""
    c, SL = client
    _, incog_id = _setup_user_and_incognito(SL)
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        shared = Account(name="Gemensamt", bank="nordea", type="shared")
        s.add(shared); s.flush()
        shared_id = shared.id
        # Gemensamt fick insättning från Evelina (importerad från CSV)
        s.add(Transaction(
            account_id=shared_id, date=date(2026, 4, 5),
            amount=Decimal("10000"), currency="SEK",
            raw_description="Insättning från Evelina", hash="sh1",
        ))
        s.commit()

    # Användaren lägger -10000 manuellt på inkognito för att spegla
    # överföringen ut från hennes sida
    c.post(f"/accounts/{incog_id}/manual-transaction", json={
        "date": "2026-04-05",
        "amount": -10000,
        "description": "Till gemensamt",
    })

    # Båda sidor ska nu vara markerade is_transfer=True
    from hembudget.db.models import Transaction as _Tx
    with SL() as s:
        shared_tx = s.query(_Tx).filter(
            _Tx.account_id == shared_id,
        ).first()
        incog_tx = s.query(_Tx).filter(
            _Tx.account_id == incog_id,
        ).first()
        assert shared_tx.is_transfer is True
        assert incog_tx.is_transfer is True


def test_manual_transaction_400_for_invalid_input(client):
    c, SL = client
    _, acc_id = _setup_user_and_incognito(SL)
    r = c.post(f"/accounts/{acc_id}/manual-transaction", json={})
    assert r.status_code == 400


def test_manual_transaction_404_unknown_account(client):
    c, _ = client
    r = c.post("/accounts/9999/manual-transaction", json={
        "date": "2026-04-05", "amount": 100, "description": "test",
    })
    assert r.status_code == 404
