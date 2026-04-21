"""Verifiera att /balances räknar korrekt med och utan ingående saldo."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from hembudget.api.deps import db as db_dep, require_auth
from hembudget.db.models import Account, Base, Transaction
from hembudget.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def _override_db():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[db_dep] = _override_db
    app.dependency_overrides[require_auth] = lambda: "test-token"

    with Session(engine) as s:
        # Konto med öppningsbalans 2026-01-31
        nordea = Account(
            name="Nordea lönekonto", bank="nordea", type="checking",
            opening_balance=Decimal("10000"),
            opening_balance_date=date(2026, 1, 31),
        )
        # Konto utan öppningsbalans (räknar alla transaktioner)
        amex = Account(name="Amex", bank="amex", type="credit")
        s.add_all([nordea, amex])
        s.flush()

        # Transaktioner på Nordea efter 2026-01-31 = inkluderas
        s.add(Transaction(
            account_id=nordea.id, date=date(2026, 2, 15),
            amount=Decimal("-2000"), currency="SEK",
            raw_description="ICA", hash="n1",
        ))
        s.add(Transaction(
            account_id=nordea.id, date=date(2026, 2, 20),
            amount=Decimal("5000"), currency="SEK",
            raw_description="Lön", hash="n2",
        ))
        # En transaktion PÅ öppningsdagen — ska INTE inkluderas (date > start)
        s.add(Transaction(
            account_id=nordea.id, date=date(2026, 1, 31),
            amount=Decimal("-100"), currency="SEK",
            raw_description="Gammal rad", hash="n3",
        ))
        # Transaktion FÖRE öppningsdagen — ska INTE inkluderas
        s.add(Transaction(
            account_id=nordea.id, date=date(2025, 12, 1),
            amount=Decimal("-50000"), currency="SEK",
            raw_description="Fjol", hash="n4",
        ))

        # Amex: alla transaktioner summeras (ingen startdag)
        s.add(Transaction(
            account_id=amex.id, date=date(2026, 2, 1),
            amount=Decimal("-500"), currency="SEK",
            raw_description="Spotify", hash="a1",
        ))
        s.commit()

    yield TestClient(app)
    app.dependency_overrides.clear()


def test_balances_respect_opening_date(client):
    r = client.get("/balances/?as_of=2026-03-01")
    assert r.status_code == 200, r.text
    data = r.json()
    by_name = {a["name"]: a for a in data["accounts"]}

    # Nordea: 10 000 + (-2 000 + 5 000) = 13 000
    # Fjol-raden (-50k) och öppningsdag-raden (-100) räknas INTE
    assert by_name["Nordea lönekonto"]["current_balance"] == 13000
    assert by_name["Nordea lönekonto"]["movement_since_opening"] == 3000

    # Amex: 0 + -500 = -500 (ingen öppningsbalans)
    assert by_name["Amex"]["current_balance"] == -500
    assert by_name["Amex"]["opening_balance_date"] is None

    assert data["total_balance"] == 12500


def test_balances_as_of_cut_off(client):
    """as_of i förflutet ska inte inkludera senare transaktioner."""
    r = client.get("/balances/?as_of=2026-02-14")
    data = r.json()
    nordea = next(a for a in data["accounts"] if a["name"] == "Nordea lönekonto")
    # Inga transaktioner mellan 2026-02-01 och 2026-02-14 → bara öppningsbalansen
    assert nordea["current_balance"] == 10000
    assert nordea["movement_since_opening"] == 0
