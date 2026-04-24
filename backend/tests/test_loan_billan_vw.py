"""Tester för billån-importflödet (VW Financial Services m.fl.).

Billån-format skiljer sig från bolån på tre sätt:
- Inget 'Ursprungligt lånebelopp' (bara 'Kvar att betala')
- Ingen amorteringsplan visas — bara 'Nästa betalning' + 'Avtalets slut'
- Eget bankgiro för inbetalning (t.ex. '5078-3489' för VW Financial)

Därför måste parsern:
- Acceptera null för principal_amount och använda current_balance som bas
- Auto-generera schedule från today → contract_end med linjär amortering
- Lägga in bankgiro i match_pattern så CSV-betalningar matchar
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class FakeLoanLLM:
    def __init__(self, response: dict):
        self.response = response

    def is_alive(self) -> bool:
        return True

    def complete_json(self, messages, schema=None, **kw):
        return self.response


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
    from hembudget.main import build_app

    orig_llm = api_deps.llm_client
    # VW Financial Services-svar (från bilden i tasken)
    vw_response = {
        "name": "VW Financial Services billån",
        "lender": "Volkswagen Financial Services",
        "loan_number": "OSJ884",
        "principal_amount": None,
        "current_balance": 39081.0,
        "amortized_total": None,
        "start_date": None,
        "contract_end_date": "2027-10-31",
        "next_payment_date": "2026-05-12",
        "interest_rate": 0.0641,
        "binding_type": "rörlig",
        "amortization_monthly": None,
        "repayment_account_number": None,
        "payment_bankgiro": "5078-3489",
        "security": "VW personbil OSJ884",
        "schedule": [],
        "historical_transactions": [],
    }
    fake = FakeLoanLLM(vw_response)

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
    app.dependency_overrides[orig_llm] = lambda: fake

    with TestClient(app) as c:
        yield c, SessionLocal, fake


def _fake_png_bytes() -> bytes:
    """En minimal 1x1 PNG så UploadFile inte kraschar."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf"
        b"\xc0\x00\x00\x00\x03\x00\x01\\\xcd\xff\x69\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def test_vw_billan_creates_loan_with_contract_end_and_schedule(client):
    c, SL, _ = client

    png = _fake_png_bytes()
    r = c.post(
        "/loans/parse-from-images",
        files=[("files", ("vw.png", png, "image/png"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Kontrakt-slut mappat till binding_end_date
    assert body["binding_end_date"] == "2027-10-31"
    # Ränta korrekt
    assert body["interest_rate"] == pytest.approx(0.0641, abs=0.0001)
    # payment_bankgiro + loan_number + lender i match_pattern
    mp = body["match_pattern"]
    assert "5078-3489" in mp
    assert "OSJ884" in mp
    assert "Volkswagen Financial Services" in mp

    # Lånet är skapat — current_balance används som principal-fallback
    from hembudget.db.models import Loan, LoanScheduleEntry
    with SL() as s:
        loan = s.query(Loan).one()
        assert float(loan.current_balance_at_creation) == pytest.approx(39081.0)
        # principal_amount får current_balance som fallback (inget
        # Ursprungligt visas på VW)
        assert float(loan.principal_amount) == pytest.approx(39081.0)
        assert loan.binding_end_date.isoformat() == "2027-10-31"
        # Månadsamortering auto-härledd = 39 081 / ~17 månader
        assert loan.amortization_monthly is not None
        amort = float(loan.amortization_monthly)
        assert 2000 <= amort <= 2800  # 39081/17 ≈ 2299, 39081/14 ≈ 2791

        # Schedule auto-genererad med rätt dag-i-månaden (12 från next_payment)
        entries = (
            s.query(LoanScheduleEntry)
            .filter(LoanScheduleEntry.loan_id == loan.id)
            .order_by(LoanScheduleEntry.due_date)
            .all()
        )
        assert len(entries) > 0, "auto-schedule saknas helt"
        # Alla på dag 12
        assert all(e.due_date.day == 12 for e in entries)
        # Både ränta- och amortering-rader
        types = {e.payment_type for e in entries}
        assert types == {"interest", "amortization"}
        # Sista raden ska ligga runt contract_end (oktober 2027)
        last_amort = [
            e for e in entries if e.payment_type == "amortization"
        ][-1]
        assert last_amort.due_date.year == 2027


def test_vw_billan_schedule_not_generated_if_contract_end_in_past(
    client, monkeypatch,
):
    """Om 'Avtalets slut' redan har passerat ska INGEN schedule genereras
    (det finns ingen framtid att prognostisera)."""
    c, SL, fake = client
    fake.response = {
        **fake.response,
        "contract_end_date": "2020-01-01",  # Redan förbi
    }

    png = _fake_png_bytes()
    r = c.post(
        "/loans/parse-from-images",
        files=[("files", ("vw.png", png, "image/png"))],
    )
    assert r.status_code == 200

    from hembudget.db.models import Loan, LoanScheduleEntry
    with SL() as s:
        loan = s.query(Loan).one()
        entries = s.query(LoanScheduleEntry).filter(
            LoanScheduleEntry.loan_id == loan.id
        ).count()
        assert entries == 0
