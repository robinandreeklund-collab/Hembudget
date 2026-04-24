"""Test per-kortinnehavar-fördelning vid PDF-import av Mastercard.

Kortinnehavar-info lagras som `cardholder`-fält på Transaction
(inte som separata sub-konton). Alla transaktioner tillhör parent-
kortkontot och fördelas dynamiskt via cardholder för rapportering.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

REPO_ROOT = Path(__file__).resolve().parents[2]
SEB_PDF = REPO_ROOT / "data" / "5b3d3093-538d-41c3-af6a-8a285d5ec9a1.pdf"


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
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    from hembudget import demo as demo_mod
    monkeypatch.setattr(demo_mod, "bootstrap_if_empty", lambda: {"skipped": True})

    from hembudget.api import deps as api_deps
    from hembudget.main import build_app

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


@pytest.mark.skipif(not SEB_PDF.exists(), reason="SEB PDF saknas")
def test_seb_pdf_cardholder_field_not_sub_accounts(client):
    c, SessionLocal = client
    with open(SEB_PDF, "rb") as f:
        content = f.read()

    r = c.post(
        "/upcoming/parse-credit-card-pdf",
        files={"file": ("seb.pdf", content, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parser"] == "pdf:seb_kort"
    # Cardholders-breakdown ska finnas i responsen
    assert "cardholders_breakdown" in body
    breakdown = body["cardholders_breakdown"]
    assert any("EVELINA" in k for k in breakdown)
    assert any("ROBIN" in k for k in breakdown)

    with SessionLocal() as s:
        from hembudget.db.models import Account, Transaction

        # BARA 1 credit-konto (parent). Inga sub-konton.
        credits = s.query(Account).filter(Account.type == "credit").all()
        assert len(credits) == 1
        parent = credits[0]

        # Alla transaktioner tillhör parent
        all_txs = s.query(Transaction).filter(
            Transaction.account_id == parent.id,
        ).all()
        assert len(all_txs) >= 45

        # Kortinnehavare är fördelade via cardholder-fält
        holders = {t.cardholder for t in all_txs if t.cardholder}
        assert any("EVELINA" in h for h in holders)
        assert any("ROBIN" in h for h in holders)

        # Betalningar och bankavgifter har cardholder=None (gemensamma)
        no_holder_txs = [t for t in all_txs if t.cardholder is None]
        descs = [t.raw_description.lower() for t in no_holder_txs]
        assert any("betalt" in d for d in descs)
        assert any("pappersfaktura" in d for d in descs)
