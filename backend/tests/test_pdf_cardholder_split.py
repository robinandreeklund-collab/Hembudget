"""Test per-kortinnehavar-split vid PDF-import av Mastercard."""
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
def test_seb_pdf_splits_per_cardholder(client):
    c, SessionLocal = client
    with open(SEB_PDF, "rb") as f:
        content = f.read()

    r = c.post(
        "/upcoming/parse-credit-card-pdf",
        files={"file": ("seb.pdf", content, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Parent-konto + 2 sub-konton för EVELINA och ROBIN
    assert body["parser"] == "pdf:seb_kort"
    assert len(body["sub_accounts"]) == 2
    sub_names = [s["name"] for s in body["sub_accounts"]]
    assert any("EVELINA" in n for n in sub_names)
    assert any("ROBIN" in n for n in sub_names)

    with SessionLocal() as s:
        from hembudget.db.models import Account, Transaction
        accounts = s.query(Account).all()
        # 1 parent + 2 sub = 3 credit-accounts
        credits = [a for a in accounts if a.type == "credit"]
        assert len(credits) == 3

        parent = next(a for a in credits if a.parent_account_id is None)
        subs = [a for a in credits if a.parent_account_id == parent.id]
        assert len(subs) == 2

        # Parent har BETALT BG + pappersfaktura (2 transaktioner utan cardholder)
        parent_txs = s.query(Transaction).filter(
            Transaction.account_id == parent.id,
        ).all()
        descs = [t.raw_description.lower() for t in parent_txs]
        assert any("betalt" in d for d in descs)
        assert any("pappersfaktura" in d for d in descs)

        # Sub-konton har köpen uppdelade
        total_sub_txs = sum(
            s.query(Transaction).filter(
                Transaction.account_id == sub.id,
            ).count() for sub in subs
        )
        # SEB-testen visade 45+ transaktioner totalt; parent ~2 + subs resten
        assert total_sub_txs >= 40
