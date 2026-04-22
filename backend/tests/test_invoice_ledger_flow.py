"""E2e-tester för fakturahantering med mockad LLM.

Täcker:
- POST /upcoming/bulk-parse-invoices mot riktiga Jan-PDF:er
- POST /transactions/{id}/attach-invoice från transaktionsvyn
- GET /upcoming/{id}/source + /transactions/{id}/invoice (ledger-vy)
- Backfill_match så gamla fakturor flyttas direkt till 'Betalda'
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[2]
JAN_DIR = REPO_ROOT / "data_for_test" / "Jan"


class FakeLLM:
    """Mock som alltid är alive och svarar enligt en vy (text → parsed).

    Istället för att faktiskt anropa LM Studio returnerar den en
    förinställd struktur. Perfekt för att verifiera pipeline utan
    beroende på lokal modell."""

    def __init__(self, responses: dict[str, dict[str, Any]] | None = None):
        self.responses = responses or {}
        self.calls: list[dict] = []

    def is_alive(self) -> bool:
        return True

    def complete_json(self, messages, schema=None, **kw):
        self.calls.append({"messages": messages, "schema": schema})
        # Hitta en "key" genom att söka efter kända ord i user-msg
        user_msg = next(
            (m.get("content") for m in messages if m.get("role") == "user"),
            "",
        )
        if isinstance(user_msg, list):
            text = " ".join(
                part.get("text", "") for part in user_msg if isinstance(part, dict)
            )
        else:
            text = str(user_msg)

        low = text.lower()
        # Hjo Energi: kombinerad el/vatten/bredband
        if "hjo energi" in low or ("elnät" in low and "vatten" in low):
            return {
                "name": "Hjo Energi",
                "amount": 3793.0,
                "expected_date": "2026-01-30",
                "debit_date": "2026-01-30",
                "invoice_number": "1121097",
                "ocr_reference": None,
                "bankgiro": "5087-0120",
                "plusgiro": None,
                "iban": None,
                "from_account": None,
                "payment_type": "Bankgiro",
                "autogiro": False,
                "notes": "Period dec 2025",
                "lines": [
                    {"description": "Elnät", "amount": 2019.23, "category": None},
                    {"description": "Vatten", "amount": 875.30, "category": None},
                    {"description": "Internet/KabelTV", "amount": 898.00, "category": None},
                ],
            }
        # If Skadeförsäkring (varje variant)
        if "if skadeförsäkring" in low:
            return {
                "name": "If Skadeförsäkring",
                "amount": 335.0,
                "expected_date": "2026-01-02",
                "debit_date": None,
                "invoice_number": "86451644065",
                "ocr_reference": "864516440650059",
                "bankgiro": None,
                "plusgiro": "822700-1",
                "iban": None,
                "from_account": None,
                "payment_type": "Plusgiro",
                "autogiro": False,
                "notes": None,
                "lines": [],
            }
        # Default för övriga
        return {
            "name": "Faktura",
            "amount": 500.0,
            "expected_date": "2026-01-30",
            "debit_date": None,
            "invoice_number": None,
            "ocr_reference": None,
            "bankgiro": None,
            "plusgiro": None,
            "iban": None,
            "from_account": None,
            "payment_type": None,
            "autogiro": False,
            "notes": None,
            "lines": [],
        }


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("HEMBUDGET_DEMO_MODE", "1")

    from hembudget.db.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False,
    )

    from hembudget import demo as demo_mod
    monkeypatch.setattr(demo_mod, "bootstrap_if_empty", lambda: {"skipped": True})

    # Seeda några kategorier så line-items-schema inte blir tomt
    from hembudget.categorize.rules import seed_categories_and_rules
    with SessionLocal() as s:
        seed_categories_and_rules(s)
        s.commit()

    from hembudget.api import deps as api_deps
    from hembudget.main import build_app

    # Spara original-referensen INNAN build_app laddar endpoints — den
    # är vad FastAPI:s dependency-cache använder som nyckel.
    orig_llm_dep = api_deps.llm_client
    fake = FakeLLM()

    app = build_app()

    def _fake_db():
        s = SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[api_deps.db] = _fake_db
    app.dependency_overrides[orig_llm_dep] = lambda: fake

    with TestClient(app) as c:
        yield c, SessionLocal, fake


@pytest.mark.skipif(not JAN_DIR.exists(), reason="Jan-faktura-katalog saknas")
def test_bulk_parse_creates_upcomings_with_lines(client):
    c, SL, _fake = client

    pdfs = sorted(JAN_DIR.glob("*.pdf"))
    assert len(pdfs) >= 5, f"förväntar flera PDF:er, fick {len(pdfs)}"

    files = [
        ("files", (p.name, p.read_bytes(), "application/pdf"))
        for p in pdfs
    ]
    r = c.post("/upcoming/bulk-parse-invoices", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["processed"] == len(pdfs)
    assert body["created"] >= 5

    # Hjo Energi-fakturan ska ha 3 lines (el, vatten, bredband)
    from hembudget.db.models import UpcomingTransaction
    with SL() as s:
        hjo = (
            s.query(UpcomingTransaction)
            .filter(UpcomingTransaction.name == "Hjo Energi")
            .first()
        )
        assert hjo is not None
        assert len(hjo.lines) == 3
        line_descs = {ln.description for ln in hjo.lines}
        assert line_descs == {"Elnät", "Vatten", "Internet/KabelTV"}
        # Summan av lines ≈ fakturans totalbelopp (1 kr tolerans för
        # öresavrundning som är standard på svenska fakturor)
        total_lines = sum(float(ln.amount) for ln in hjo.lines)
        assert abs(total_lines - float(hjo.amount)) < 1.0

    # Alla upcomings ska ha sparad källfil (ledger)
    with SL() as s:
        ups = s.query(UpcomingTransaction).all()
        assert all(u.source_image_path for u in ups)


@pytest.mark.skipif(not JAN_DIR.exists(), reason="Jan-faktura-katalog saknas")
def test_bulk_parse_backfill_matches_existing_tx(client):
    """Om en Transaction redan finns på ett konto som matchar fakturans
    summa + datum ska den automatiskt markeras som betald."""
    c, SL, _fake = client

    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(
            name="Mat 1722 20 34439", bank="nordea", type="shared",
            account_number="1722 20 34439",
        )
        s.add(acc); s.flush()
        # Debit för Hjo Energi (3 793 kr) på förfallodagen 2026-01-30
        s.add(Transaction(
            account_id=acc.id, date=date(2026, 1, 30),
            amount=Decimal("-3793.00"), currency="SEK",
            raw_description="Hjo Energi BG 5087-0120", hash="h-hjo",
        ))
        s.commit()

    hjo_pdf = next(
        (p for p in JAN_DIR.glob("*.pdf")
         if "efa_1776848229114" in p.name),
        None,
    )
    assert hjo_pdf is not None, "Hjo Energi-PDF saknas i Jan-katalogen"

    files = [("files", (hjo_pdf.name, hjo_pdf.read_bytes(), "application/pdf"))]
    r = c.post("/upcoming/bulk-parse-invoices", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    # Fakturan ska ha matchats mot den befintliga bankraden
    assert body["matched_to_existing"] == 1
    assert body["results"][0]["status"] == "ok"


@pytest.mark.skipif(not JAN_DIR.exists(), reason="Jan-faktura-katalog saknas")
def test_attach_invoice_from_transaction_view(client):
    """Användaren klickar på en tx och bifogar en faktura → AI extraherar
    + splits skapas + ledger-vyn visar filen."""
    c, SL, _fake = client

    from hembudget.db.models import Account, Transaction
    with SL() as s:
        acc = Account(
            name="Mat 1722 20 34439", bank="nordea", type="shared",
            account_number="1722 20 34439",
        )
        s.add(acc); s.flush()
        tx = Transaction(
            account_id=acc.id, date=date(2026, 1, 30),
            amount=Decimal("-3793.00"), currency="SEK",
            raw_description="Hjo Energi", hash="h-tx",
        )
        s.add(tx); s.commit()
        tx_id = tx.id

    hjo_pdf = next(
        (p for p in JAN_DIR.glob("*.pdf")
         if "efa_1776848229114" in p.name),
        None,
    )
    assert hjo_pdf is not None

    files = {"file": (hjo_pdf.name, hjo_pdf.read_bytes(), "application/pdf")}
    r = c.post(f"/transactions/{tx_id}/attach-invoice", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transaction_id"] == tx_id
    assert body["name"] == "Hjo Energi"
    assert body["line_count"] == 3

    # Splits ska ha skapats (el + vatten + bredband)
    from hembudget.db.models import TransactionSplit
    with SL() as s:
        splits = (
            s.query(TransactionSplit)
            .filter(TransactionSplit.transaction_id == tx_id)
            .all()
        )
        assert len(splits) == 3
        # Summan av splits = transaktionens belopp (med bevarade tecken)
        total = sum(float(sp.amount) for sp in splits)
        assert abs(total - (-3793.00)) < 0.01

    # invoiced-ids ska nu inkludera denna tx
    r = c.get("/transactions/invoiced-ids")
    assert tx_id in r.json()["ids"]

    # Ledger-endpoint: hämta fakturan för transaktionen
    r = c.get(f"/transactions/{tx_id}/invoice")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"


def test_source_file_404_when_missing(client):
    c, SL, _ = client
    # Upcoming utan source_image_path
    from hembudget.db.models import UpcomingTransaction
    with SL() as s:
        u = UpcomingTransaction(
            kind="bill", name="Test", amount=Decimal("100"),
            expected_date=date(2026, 3, 1),
            source="manual",
        )
        s.add(u); s.commit()
        uid = u.id

    r = c.get(f"/upcoming/{uid}/source")
    assert r.status_code == 404


def test_attach_invoice_404_for_unknown_tx(client):
    c, _, _ = client
    r = c.post(
        "/transactions/99999/attach-invoice",
        files={"file": ("x.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert r.status_code == 404
