"""Tester for /utility-endpoints och PDF-parser."""
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


def _seed_two_years(SL):
    """Seeda el + vatten-transaktioner for 2025 (lagt) och 2026 (hogre)."""
    from hembudget.db.models import Account, Category, Transaction
    with SL() as s:
        acc = Account(name="A", bank="n", type="checking")
        el = Category(name="El")
        vatten = Category(name="Vatten/Avgift")
        s.add_all([acc, el, vatten]); s.flush()
        # 2025: 500 kr/mnad el, 200 kr/mnad vatten
        for m in range(1, 13):
            s.add(Transaction(
                account_id=acc.id, date=date(2025, m, 15),
                amount=Decimal("-500"), currency="SEK",
                raw_description="Hjo Energi", hash=f"e25_{m}",
                category_id=el.id,
            ))
            s.add(Transaction(
                account_id=acc.id, date=date(2025, m, 15),
                amount=Decimal("-200"), currency="SEK",
                raw_description="Hjo kommun", hash=f"v25_{m}",
                category_id=vatten.id,
            ))
        # 2026 Q1: 700 kr/mnad el (+40 % yoy)
        for m in range(1, 4):
            s.add(Transaction(
                account_id=acc.id, date=date(2026, m, 15),
                amount=Decimal("-700"), currency="SEK",
                raw_description="Hjo Energi", hash=f"e26_{m}",
                category_id=el.id,
            ))
        s.commit()


def test_history_yoy_comparison(client):
    c, SL = client
    _seed_two_years(SL)

    r = c.get("/utility/history?year=2026&compare_previous_year=true")
    assert r.status_code == 200, r.text
    body = r.json()

    # Current year: bara el Q1, 700 * 3 = 2100
    assert body["year"] == 2026
    assert body["category_totals"]["El"] == pytest.approx(2100.0)

    # Previous-year struktur
    assert "previous" in body
    prev = body["previous"]
    assert prev["year"] == 2025
    # 2025: el 500 * 12 = 6000, vatten 200 * 12 = 2400
    assert prev["category_totals"]["El"] == pytest.approx(6000.0)
    assert prev["category_totals"]["Vatten/Avgift"] == pytest.approx(2400.0)

    # YoY-diff per manad for El: januari 700 - 500 = +200
    assert body["yoy_diff"]["El"]["2026-01"] == pytest.approx(200.0)
    # April 0 - 500 = -500 (ingen tx 2026-04)
    assert body["yoy_diff"]["El"]["2026-04"] == pytest.approx(-500.0)


def test_history_without_yoy_has_no_previous(client):
    c, SL = client
    _seed_two_years(SL)
    r = c.get("/utility/history?year=2026")
    body = r.json()
    assert "previous" not in body
    assert "yoy_diff" not in body


def test_readings_crud(client):
    c, SL = client

    # Skapa en manuell reading
    r1 = c.post("/utility/readings", json={
        "supplier": "tibber",
        "meter_type": "electricity",
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
        "consumption": 450,
        "consumption_unit": "kWh",
        "cost_kr": 950,
    })
    assert r1.status_code == 200
    rid = r1.json()["id"]

    # Lista
    r2 = c.get("/utility/readings?year=2026")
    rows = r2.json()["readings"]
    assert len(rows) == 1
    assert rows[0]["consumption"] == 450
    assert rows[0]["consumption_unit"] == "kWh"
    assert rows[0]["supplier"] == "tibber"

    # Lista dyker upp i history.readings
    hist = c.get("/utility/history?year=2026").json()
    assert "electricity" in hist["readings"]
    assert hist["readings"]["electricity"]["2026-01"]["consumption"] == 450.0
    assert hist["readings"]["electricity"]["2026-01"]["cost_kr"] == 950.0

    # Ta bort
    r3 = c.delete(f"/utility/readings/{rid}")
    assert r3.status_code == 200
    r4 = c.get("/utility/readings?year=2026")
    assert r4.json()["readings"] == []


def test_history_no_split_double_count(client):
    """En tx med splits ska inte dubbelraknas: om tx har
    category_id=El OCH en split pa El, ska bara split:s belopp raknas.
    Summan ska bli split-beloppet, inte tx.amount + split."""
    c, SL = client
    from hembudget.db.models import (
        Account, Category, Transaction, TransactionSplit,
    )
    with SL() as s:
        acc = Account(name="A", bank="n", type="checking")
        el = Category(name="El")
        vatten = Category(name="Vatten/Avgift")
        s.add_all([acc, el, vatten]); s.flush()
        # Hjo Energi-faktura 3 797 kr: tx kategoriserad som El,
        # men med splits El 2000, Vatten 1797
        tx = Transaction(
            account_id=acc.id, date=date(2026, 3, 15),
            amount=Decimal("-3797"), currency="SEK",
            raw_description="Hjo Energi", hash="h1",
            category_id=el.id,
        )
        s.add(tx); s.flush()
        s.add(TransactionSplit(
            transaction_id=tx.id, description="El",
            amount=Decimal("2000"), category_id=el.id, sort_order=0,
            source="manual",
        ))
        s.add(TransactionSplit(
            transaction_id=tx.id, description="Vatten",
            amount=Decimal("1797"), category_id=vatten.id, sort_order=1,
            source="manual",
        ))
        s.commit()

    # /utility ska fordela splits korrekt
    r = c.get("/utility/history?year=2026")
    body = r.json()
    # El: bara split-belopp (2000), inte 3797 + 2000 = 5797
    assert body["by_category"]["El"]["2026-03"] == pytest.approx(2000.0)
    assert body["by_category"]["Vatten/Avgift"]["2026-03"] == pytest.approx(1797.0)

    # Totalt = 3797 (inte 3797 + 2000 + 1797 = 7594 som gammal bugg)
    assert body["summary"]["year_total"] == pytest.approx(3797.0)


def test_ledger_uses_splits_per_category(client):
    """Huvudbokens resultatrakning ska anvanda splits istallet for
    tx.category_id nar tx har splits. Annars gar Vatten- och Mobil-
    delarna av en Hjo Energi-faktura forlorade (kategoriserad som El)."""
    c, SL = client
    from hembudget.db.models import (
        Account, Category, Transaction, TransactionSplit,
    )
    with SL() as s:
        acc = Account(name="A", bank="n", type="checking")
        el = Category(name="El")
        vatten = Category(name="Vatten/Avgift")
        mobil = Category(name="Mobil")
        s.add_all([acc, el, vatten, mobil]); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 3, 15),
            amount=Decimal("-5000"), currency="SEK",
            raw_description="Hjo Energi kombinerad", hash="h1",
            category_id=el.id,
        )
        s.add(tx); s.flush()
        s.add(TransactionSplit(
            transaction_id=tx.id, description="El",
            amount=Decimal("2500"), category_id=el.id, sort_order=0,
            source="manual",
        ))
        s.add(TransactionSplit(
            transaction_id=tx.id, description="Vatten",
            amount=Decimal("1500"), category_id=vatten.id, sort_order=1,
            source="manual",
        ))
        s.add(TransactionSplit(
            transaction_id=tx.id, description="Mobil",
            amount=Decimal("1000"), category_id=mobil.id, sort_order=2,
            source="manual",
        ))
        s.commit()

    r = c.get("/ledger/?year=2026")
    body = r.json()
    cats = {c["category"]: c for c in body["categories"]}
    # Alla tre kategorier ska finnas representerade
    assert cats["El"]["expenses"] == pytest.approx(2500.0)
    assert cats["Vatten/Avgift"]["expenses"] == pytest.approx(1500.0)
    assert cats["Mobil"]["expenses"] == pytest.approx(1000.0)
    # Totala expenses = tx-amount (5000), inte bara El
    assert body["totals"]["expenses"] == pytest.approx(5000.0)


def test_breakdown_lists_transactions_for_cell(client):
    """GET /utility/breakdown?category=El&month=2026-01 listar alla
    tx + splits som bidrar till cellen. Anvands for att felsoka
    'varfor ar mars-el 24 443 kr?'."""
    c, SL = client
    from hembudget.db.models import (
        Account, Category, Transaction, TransactionSplit,
    )
    with SL() as s:
        acc = Account(name="A", bank="n", type="checking")
        el = Category(name="El")
        s.add_all([acc, el]); s.flush()
        # Ren el-tx
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 1, 15),
            amount=Decimal("-900"), currency="SEK",
            raw_description="Hjo Energi januari", hash="e1",
            category_id=el.id,
        ))
        # Split-rad pa kombinerad faktura
        tx2 = Transaction(
            account_id=acc.id, date=date(2026, 1, 20),
            amount=Decimal("-1200"), currency="SEK",
            raw_description="Hjo Energi kombinerad", hash="e2",
        )
        s.add(tx2); s.flush()
        s.add(TransactionSplit(
            transaction_id=tx2.id, description="El-del",
            amount=Decimal("800"), category_id=el.id, sort_order=0,
            source="manual",
        ))
        s.commit()

    r = c.get("/utility/breakdown?category=El&month=2026-01")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["category"] == "El"
    assert body["month"] == "2026-01"
    # Total = 900 + 800 = 1700
    assert body["total"] == pytest.approx(1700.0)
    assert len(body["items"]) == 2
    # En tx, en split
    types = {i["type"] for i in body["items"]}
    assert types == {"transaction", "split"}
    # Splits kan inte flyttas via date-patch
    for item in body["items"]:
        if item["type"] == "split":
            assert item["can_move"] is False
        else:
            assert item["can_move"] is True


def test_rescan_existing_invoices_creates_readings(client, tmp_path):
    """Rescan ska gå igenom alla UpcomingTransaction med
    source_image_path satt och skapa UtilityReading-rader. Idempotent —
    andra körningen skippar dubletter via source_file-path."""
    c, SL = client
    from pathlib import Path
    from hembudget.db.models import UpcomingTransaction

    # Skapa en riktig Hjo Energi-lik PDF med pypdfium2? Det går inte —
    # vi kan inte skapa PDF:er i test. Istället: skapa en fil på disk
    # (bara bytes) som kommer faila att parsas → räknas som error, inte
    # created. Det är också ett användbart test för error-hanteringen.

    # Skapa en upcoming med pekare till fake PDF som inte existerar på disk
    fake_pdf = tmp_path / "fake_nonexistent.pdf"
    with SL() as s:
        up = UpcomingTransaction(
            kind="bill", name="Test faktura",
            amount=Decimal("100"),
            expected_date=date(2026, 1, 15),
            source="vision_ai",
            source_image_path=str(fake_pdf),
        )
        s.add(up); s.commit()

    r = c.post("/utility/rescan-existing")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scanned"] == 1
    # Filen saknas → error
    assert len(body["errors"]) == 1
    assert "saknas" in body["errors"][0]["error"]
    assert body["created"] == 0


def test_history_includes_unpaid_upcoming_bills(client):
    """Kommande fakturor (unpaid) ska racknas med i utility-historien
    sa vi ser upcoming april-fakturor som redan ar bestamda."""
    c, SL = client
    from hembudget.db.models import (
        Account, Category, UpcomingTransaction, UpcomingTransactionLine,
    )
    with SL() as s:
        acc = Account(name="A", bank="n", type="checking")
        el = Category(name="El")
        vatten = Category(name="Vatten/Avgift")
        s.add_all([acc, el, vatten]); s.flush()
        # Upcoming april-faktura: Hjo Energi 4 000 kr, kategori El
        s.add(UpcomingTransaction(
            kind="bill", name="Hjo Energi april",
            amount=Decimal("4000"),
            expected_date=date(2026, 4, 28),
            category_id=el.id,
        ))
        # Upcoming med lines (splits) — Hjo kombinerad faktura 2000 kr
        combo = UpcomingTransaction(
            kind="bill", name="Hjo kombinerad april",
            amount=Decimal("2000"),
            expected_date=date(2026, 4, 30),
        )
        s.add(combo); s.flush()
        s.add(UpcomingTransactionLine(
            upcoming_id=combo.id, description="El del",
            amount=Decimal("1200"), category_id=el.id, sort_order=0,
        ))
        s.add(UpcomingTransactionLine(
            upcoming_id=combo.id, description="Vatten del",
            amount=Decimal("800"), category_id=vatten.id, sort_order=1,
        ))
        s.commit()

    r = c.get("/utility/history?year=2026")
    body = r.json()
    # El i april: 4000 (Hjo Energi) + 1200 (Hjo kombinerad line) = 5200
    assert body["by_category"]["El"]["2026-04"] == pytest.approx(5200.0)
    # Vatten i april: 800 (combo line)
    assert body["by_category"]["Vatten/Avgift"]["2026-04"] == pytest.approx(800.0)


def test_breakdown_includes_pdf_and_reading_info(client):
    """Breakdown-responsen ska inkludera upcoming_id, has_invoice_pdf,
    reading_id per item sa frontend kan visa 'Oppna faktura' och
    'Parsa om' direkt i modalen."""
    c, SL = client
    from hembudget.db.models import (
        Account, Category, Transaction, UpcomingTransaction, UtilityReading,
    )
    with SL() as s:
        acc = Account(name="A", bank="n", type="checking")
        el = Category(name="El")
        s.add_all([acc, el]); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 3, 15),
            amount=Decimal("-1000"), currency="SEK",
            raw_description="Hjo Energi", hash="h1",
            category_id=el.id,
        )
        s.add(tx); s.flush()
        # Kopplad upcoming med PDF
        up = UpcomingTransaction(
            kind="bill", name="Hjo Energi mars",
            amount=Decimal("1000"),
            expected_date=date(2026, 3, 15),
            source="pdf",
            source_image_path="/tmp/hjo-mars.pdf",
            matched_transaction_id=tx.id,
        )
        s.add(up); s.flush()
        # Tidigare skapad reading
        reading = UtilityReading(
            supplier="hjo_energi",
            meter_type="electricity",
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            cost_kr=Decimal("1000"),
            source="pdf",
            source_file="/tmp/hjo-mars.pdf",
            upcoming_id=up.id,
        )
        s.add(reading); s.commit()
        reading_id = reading.id

    r = c.get("/utility/breakdown?category=El&month=2026-03")
    body = r.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["upcoming_id"] is not None
    assert item["has_invoice_pdf"] is True
    assert item["reading_id"] == reading_id


def test_reparse_reading_updates_fields_without_touching_source(client, tmp_path):
    """POST /utility/readings/{id}/reparse laser om PDF:en och
    uppdaterar reading:s falt. Skall inte krascha om filen saknas."""
    c, SL = client
    from hembudget.db.models import UtilityReading

    with SL() as s:
        r = UtilityReading(
            supplier="manual",
            meter_type="electricity",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            consumption=Decimal("100"),
            consumption_unit="kWh",
            cost_kr=Decimal("500"),
            source="manual",
            source_file=None,
        )
        s.add(r); s.commit()
        rid = r.id

    # Ingen source_file → 400
    r1 = c.post(f"/utility/readings/{rid}/reparse")
    assert r1.status_code == 400

    # Satt en icke-existerande fil → 404
    with SL() as s:
        row = s.get(UtilityReading, rid)
        row.source_file = str(tmp_path / "missing.pdf")
        s.commit()
    r2 = c.post(f"/utility/readings/{rid}/reparse")
    assert r2.status_code == 404


def test_tibber_endpoints_require_token(client):
    """Utan token ska alla tibber-endpoints returnera 400, inte krascha."""
    c, _ = client
    r1 = c.post("/utility/tibber/test")
    assert r1.status_code == 400
    r2 = c.post("/utility/tibber/sync")
    assert r2.status_code == 400
    r3 = c.get("/utility/tibber/realtime")
    assert r3.status_code == 400
