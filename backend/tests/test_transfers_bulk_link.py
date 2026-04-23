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


def test_auto_pair_uncategorized_pairs_obvious_matches(client):
    """auto-pair-uncategorized scannar uncategorized + oparade rader och
    parar de som har EXAKT en motpart med samma datum + belopp på annat
    konto. Användsfall: kreditkortsbetalningar som detect_internal_transfers
    missade men som är solklara från åtgärda-listan i huvudboken."""
    c, SL = client
    pairs = _seed_credit_card_payments(SL)

    # Skicka uncategorized tx_ids — alla 6 ska finnas där
    all_ids = [tid for pair in pairs for tid in pair]
    r = c.post(
        "/transfers/auto-pair-uncategorized",
        json={"tx_ids": all_ids},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["linked"] == 3  # 3 par = 6 tx
    assert body["ambiguous_count"] == 0

    # Verifiera att alla 6 nu är parade som transfer
    paired = c.get("/transfers/paired").json()
    assert paired["count"] == 3


def test_auto_pair_handles_date_tolerance_and_amount_eps(client):
    """Real-world: kreditkortsdraget bokförs ofta 1-2 dagar efter checking-
    sidan, och Decimal-precision i SQLite kan göra exakt == miss. Auto-
    pair ska hantera båda."""
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        chk = Account(name="Mat", bank="nordea", type="shared")
        amex = Account(name="Amex", bank="amex", type="credit",
                       bankgiro="5127-5477")
        s.add_all([chk, amex]); s.flush()
        # Mat -13500 på 27 mars, Amex +13500 på 28 mars (1 dag senare)
        s.add(Transaction(account_id=chk.id, date=date(2026,3,27),
                          amount=Decimal("-13500.00"), currency="SEK",
                          raw_description="BG 5127-5477", hash="h_chk"))
        s.add(Transaction(account_id=amex.id, date=date(2026,3,28),
                          amount=Decimal("13500"), currency="SEK",
                          raw_description="Mottagen", hash="h_amex"))
        s.commit()

    r = c.post("/transfers/auto-pair-uncategorized",
               json={"month": "2026-03"})
    body = r.json()
    assert body["linked"] == 1, body


def test_auto_pair_skips_ambiguous_when_multiple_partners(client):
    """Om EN negativ rad har FLERA matchande positiva (samma dag, samma
    belopp) på olika konton → ambiguous, hoppa över istället för att
    gissa fel."""
    c, SL = client
    from hembudget.db.models import Account, Transaction
    with SL() as s:
        chk = Account(name="Chk", bank="nordea", type="checking")
        a1 = Account(name="A1", bank="amex", type="credit")
        a2 = Account(name="A2", bank="seb_kort", type="credit")
        s.add_all([chk, a1, a2]); s.flush()
        # En negativ men TVÅ positiva på samma datum + belopp
        s.add(Transaction(account_id=chk.id, date=date(2026,4,1),
                          amount=Decimal("-500"), currency="SEK",
                          raw_description="X", hash="h_chk"))
        s.add(Transaction(account_id=a1.id, date=date(2026,4,1),
                          amount=Decimal("500"), currency="SEK",
                          raw_description="A", hash="h_a1"))
        s.add(Transaction(account_id=a2.id, date=date(2026,4,1),
                          amount=Decimal("500"), currency="SEK",
                          raw_description="B", hash="h_a2"))
        s.commit()

    r = c.post(
        "/transfers/auto-pair-uncategorized",
        json={"month": "2026-04"},
    )
    body = r.json()
    assert body["linked"] == 0
    assert body["ambiguous_count"] == 1
