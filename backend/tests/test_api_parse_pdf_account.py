"""HTTP-test för POST /accounts/parse-pdf — Nordea Kontohändelser auto-import."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

REPO_ROOT = Path(__file__).resolve().parents[2]
ISK_PDF = REPO_ROOT / "data_for_test" / "ISK_TEST" / (
    "Kontohändelser-47178384944-SEK-20260101-20260422.pdf"
)


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

    from hembudget.api import deps as api_deps
    from hembudget.categorize.rules import seed_categories_and_rules
    from hembudget.main import build_app

    with SessionLocal() as s:
        seed_categories_and_rules(s)
        s.commit()

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

    with TestClient(app) as c:
        yield c, SessionLocal


@pytest.mark.skipif(not ISK_PDF.exists(), reason="ISK sample PDF saknas")
def test_parse_pdf_creates_isk_account_and_imports_transactions(client):
    c, SessionLocal = client

    with open(ISK_PDF, "rb") as f:
        payload = f.read()

    r = c.post(
        "/accounts/parse-pdf",
        files={"file": ("isk.pdf", payload, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["created"] is True
    assert body["account_name"].upper().startswith("ISK")
    assert body["account_number"].replace(" ", "") == "47178384944"
    assert body["transactions_created"] >= 20
    assert body["transactions_skipped_duplicates"] == 0
    assert body["opening_balance"] == pytest.approx(2000.99)
    assert body["closing_balance"] == pytest.approx(0.99)
    assert body["period_start"] == "2026-01-01"
    assert body["period_end"] == "2026-04-22"

    from hembudget.db.models import Account, Transaction
    with SessionLocal() as s:
        acc = s.query(Account).filter(
            Account.id == body["account_id"]
        ).one()
        assert acc.type == "isk"
        assert acc.bank == "nordea"
        txs = s.query(Transaction).filter(
            Transaction.account_id == acc.id
        ).count()
        assert txs == body["transactions_created"]

    # Andra gången: idempotent — alla transaktioner skippas som duplicates
    r2 = c.post(
        "/accounts/parse-pdf",
        files={"file": ("isk.pdf", payload, "application/pdf")},
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["created"] is False
    assert body2["account_id"] == body["account_id"]
    assert body2["transactions_created"] == 0
    assert body2["transactions_skipped_duplicates"] == body["transactions_created"]


def test_parse_pdf_rejects_non_pdf(client):
    c, _ = client
    r = c.post(
        "/accounts/parse-pdf",
        files={"file": ("x.txt", b"not a pdf at all", "text/plain")},
    )
    assert r.status_code == 400
    assert "PDF" in r.json()["detail"]


def test_parse_pdf_rejects_empty(client):
    c, _ = client
    r = c.post(
        "/accounts/parse-pdf",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert r.status_code == 400
