"""Test för klistra-in-kontoutdrag-importen.

Backend ska kunna ta emot text från användarens internetbank, tolka
datum + belopp + beskrivning per rad, varna för dubbletter och sen
importera de godkända raderna med proper hash + auto-kategorisering.
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


SAMPLE_NORDEA_PASTE = """\
2026-04-22\tBODIL RAPP\t6 400,00
2026-04-21\t(1) Importerade kontohändelser\t-1 076,16
2026-04-17\tOmsättning lån 3254 80 14029\t-28 215,00
2026-04-13\tSKATTEVERKET\t-4 221,00
2026-04-13\tSKATTEVERKET\t-7 977,00
2026-04-05\tHÄLSOCENTRALEN I HJO AB\t100 000,00
"""


def _setup_account(SL):
    from hembudget.db.models import Account
    with SL() as s:
        acc = Account(name="Företag", bank="nordea", type="checking")
        s.add(acc); s.commit()
        return acc.id


def test_parse_pasted_returns_candidates_with_no_duplicates(client):
    c, SL = client
    acc_id = _setup_account(SL)

    r = c.post(
        f"/accounts/{acc_id}/parse-pasted-statement",
        json={"text": SAMPLE_NORDEA_PASTE},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["candidates"]) == 6
    # Inga existerande tx → ingen dubblett
    assert all(not c["duplicate"] for c in body["candidates"])
    assert body["latest_existing_date"] is None
    # Stickprov: parsed amounts/desc
    bodil = next(c for c in body["candidates"] if "BODIL" in c["description"])
    assert bodil["amount"] == 6400.0
    assert bodil["date"] == "2026-04-22"
    skatte = [c for c in body["candidates"] if c["description"] == "SKATTEVERKET"]
    assert len(skatte) == 2
    assert {c["amount"] for c in skatte} == {-4221.0, -7977.0}


def test_parse_detects_duplicates_against_existing(client):
    """Om tx redan finns på samma datum + belopp markeras som dubblett."""
    c, SL = client
    acc_id = _setup_account(SL)

    # Importera först gången
    r1 = c.post(
        f"/accounts/{acc_id}/import-pasted-statement",
        json={
            "rows": [
                {"date": "2026-04-22", "amount": 6400.0, "description": "BODIL RAPP"},
            ],
        },
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["imported"] == 1

    # Klistra in samma sak igen — ska markeras som dubblett
    r2 = c.post(
        f"/accounts/{acc_id}/parse-pasted-statement",
        json={"text": "2026-04-22\tBODIL RAPP\t6 400,00"},
    )
    body = r2.json()
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["duplicate"]
    assert "exakt match" in body["candidates"][0]["dup_reason"]
    assert body["latest_existing_date"] == "2026-04-22"


def test_import_pasted_creates_transactions_with_dedup(client):
    """import-pasted skapar tx, hoppar över dubbletter, kör auto-cat."""
    c, SL = client
    acc_id = _setup_account(SL)

    r1 = c.post(
        f"/accounts/{acc_id}/import-pasted-statement",
        json={
            "rows": [
                {"date": "2026-04-22", "amount": 6400.0, "description": "BODIL RAPP"},
                {"date": "2026-04-21", "amount": -1076.16, "description": "Importerade"},
            ],
        },
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["imported"] == 2
    assert body1["skipped_duplicates"] == 0

    # Andra körningen — samma rader → båda dubbletter
    r2 = c.post(
        f"/accounts/{acc_id}/import-pasted-statement",
        json={
            "rows": [
                {"date": "2026-04-22", "amount": 6400.0, "description": "BODIL RAPP"},
                {"date": "2026-04-21", "amount": -1076.16, "description": "Importerade"},
                {"date": "2026-04-20", "amount": -50.0, "description": "Ny rad"},
            ],
        },
    )
    body2 = r2.json()
    assert body2["imported"] == 1
    assert body2["skipped_duplicates"] == 2

    # Verifiera att txs faktiskt skapats
    txs = c.get(f"/transactions?account_id={acc_id}").json()
    assert len(txs) == 3


def test_parse_handles_swedish_amount_formats(client):
    """1 234,56 / 1234,56 / -1 234,56 / +1234.56 — alla ska tolkas."""
    c, SL = client
    acc_id = _setup_account(SL)

    text = """\
2026-04-22\tA\t1 234,56
2026-04-21\tB\t1234,56
2026-04-20\tC\t-1 234,56
2026-04-19\tD\t+1234.56
2026-04-18\tE\t1 000,00 SEK
2026-04-17\tF\t-500 kr
"""
    r = c.post(
        f"/accounts/{acc_id}/parse-pasted-statement",
        json={"text": text},
    )
    body = r.json()
    by_desc = {c["description"]: c["amount"] for c in body["candidates"]}
    assert by_desc["A"] == 1234.56
    assert by_desc["B"] == 1234.56
    assert by_desc["C"] == -1234.56
    assert by_desc["D"] == 1234.56
    assert by_desc["E"] == 1000.0
    assert by_desc["F"] == -500.0


def test_parse_skips_header_and_empty_lines(client):
    c, SL = client
    acc_id = _setup_account(SL)

    text = """
Kontoutdrag privatkonto 1234 56 78900

Datum\tBeskrivning\tBelopp
2026-04-22\tBODIL RAPP\t6 400,00

Ingående saldo: 18 480,10
Utgående saldo: 24 964,17
"""
    r = c.post(
        f"/accounts/{acc_id}/parse-pasted-statement",
        json={"text": text},
    )
    body = r.json()
    # Bara BODIL ska räknas — header/saldo-rader skippas
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["description"] == "BODIL RAPP"
