"""Tester för att 'income_by_owner' i månadsprognosen resolverar
ägarnamn korrekt även när upcoming.owner är tomt."""
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


def test_owner_resolved_from_name_substring(client):
    """När upcoming.owner är None men namnet innehåller en User.name
    (t.ex. 'Evelinas Lön'), ska income_by_owner visa 'Evelina'."""
    c, SL = client
    from hembudget.db.models import UpcomingTransaction, User
    with SL() as s:
        eve = User(name="Evelina")
        s.add(eve); s.flush()
        # Unmatched upcoming utan owner men namn med "Evelina" i sig
        s.add(UpcomingTransaction(
            kind="income", name="Evelinas Lön",
            amount=Decimal("35604"),
            expected_date=date(2026, 4, 25),
        ))
        s.commit()

    r = c.get("/upcoming/forecast?month=2026-04")
    by_owner = r.json()["income_by_owner"]
    assert "Evelina" in by_owner
    assert "Okänd" not in by_owner
    assert by_owner["Evelina"] == pytest.approx(35604.0)


def test_materialize_to_account_sets_owner_from_account(client):
    """När användaren manuellt kopplar en upcoming(income) utan owner
    till ett konto med owner_id satt → upcoming.owner sätts till User.name
    så framtida vyer visar rätt namn."""
    c, SL = client
    from hembudget.db.models import (
        Account, UpcomingTransaction, User,
    )
    with SL() as s:
        eve = User(name="Evelina")
        s.add(eve); s.flush()
        acc = Account(
            name="Eve priv", bank="nordea", type="checking",
            owner_id=eve.id, incognito=True,
        )
        s.add(acc); s.commit()
        acc_id = acc.id

    r = c.post("/upcoming/", json={
        "kind": "income", "name": "Inkab",
        "amount": "30000", "expected_date": "2026-04-25",
    })
    up_id = r.json()["id"]
    assert r.json()["owner"] is None

    r = c.post(
        f"/upcoming/{up_id}/materialize-to-account",
        json={"account_id": acc_id},
    )
    assert r.status_code == 200

    # Verify upcoming nu har owner satt
    from hembudget.db.models import UpcomingTransaction as _UT
    with SL() as s:
        up = s.get(_UT, up_id)
        assert up.owner == "Evelina"


def test_owner_string_takes_priority_over_name_substring(client):
    """Om upcoming.owner är explicit satt ska det vinna över
    automatisk namn-substring-match."""
    c, SL = client
    from hembudget.db.models import UpcomingTransaction, User
    with SL() as s:
        eve = User(name="Evelina")
        s.add(eve); s.flush()
        # Owner explicit "Annan Person" trots att namnet säger "Evelina"
        s.add(UpcomingTransaction(
            kind="income", name="Evelinas lön",
            amount=Decimal("1000"),
            expected_date=date(2026, 4, 25),
            owner="Annan Person",
        ))
        s.commit()

    r = c.get("/upcoming/forecast?month=2026-04")
    by_owner = r.json()["income_by_owner"]
    assert "Annan Person" in by_owner
    assert "Evelina" not in by_owner
