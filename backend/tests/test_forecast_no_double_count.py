"""Regressionstest för månadsprognos: matchade kommande fakturor ska
INTE räknas dubbelt (som både upcoming_bills NÄSTA månad OCH som del av
avg_fixed_expenses från de senaste 3 månaderna)."""
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
    app = build_app()

    def _db():
        s = SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[api_deps.db] = _db
    with TestClient(app) as c:
        yield c, SessionLocal


def test_matched_upcoming_not_double_counted_in_avg_expenses(client):
    """El-fakturan betalades i jan, feb, mars (3000 kr/mån) OCH är inlagd
    som upcoming för april (3000 kr). Den ska räknas EN gång — som april-
    fakturan — inte som en del av snittet också.
    """
    c, SL = client
    from hembudget.db.models import (
        Account, Transaction, UpcomingTransaction,
    )
    with SL() as s:
        acc = Account(name="Löner", bank="nordea", type="checking")
        s.add(acc); s.flush()

        # 3 månader historia: varje månad en el-räkning 3000 kr som
        # matchades mot en upcoming, PLUS 10 000 kr "variabla utgifter"
        # (mat, bensin etc.)
        for m, day in [(1, 15), (2, 15), (3, 15)]:
            el_tx = Transaction(
                account_id=acc.id, date=date(2026, m, day),
                amount=Decimal("-3000.00"), currency="SEK",
                raw_description="Hjo Energi", hash=f"el-{m}",
            )
            s.add(el_tx); s.flush()
            # Upcoming som matchades mot den
            past_up = UpcomingTransaction(
                kind="bill", name="Hjo Energi",
                amount=Decimal("3000.00"),
                expected_date=date(2026, m, 27),
                matched_transaction_id=el_tx.id,
                debit_account_id=acc.id, source="pdf_parser",
            )
            s.add(past_up)

            # Variabla utgifter (mat + bensin) — summan dessa bör visas
            # som "avg övriga utgifter" i prognosen
            s.add(Transaction(
                account_id=acc.id, date=date(2026, m, 20),
                amount=Decimal("-10000.00"), currency="SEK",
                raw_description="Matbutik", hash=f"mat-{m}",
            ))

        # April: kommande el-faktura 3000 kr (inte matchad än)
        s.add(UpcomingTransaction(
            kind="bill", name="Hjo Energi (april)",
            amount=Decimal("3000.00"),
            expected_date=date(2026, 4, 27),
            debit_account_id=acc.id, source="pdf_parser",
        ))
        # April: kommande lön
        s.add(UpcomingTransaction(
            kind="income", name="Inkab",
            amount=Decimal("35000.00"),
            expected_date=date(2026, 4, 25),
            owner="Robin",
        ))
        s.commit()

    r = c.get("/upcoming/forecast?month=2026-04")
    assert r.status_code == 200
    body = r.json()
    totals = body["totals"]

    # upcoming_bills = 3000 (bara april-elen)
    assert totals["upcoming_bills"] == pytest.approx(3000.0)

    # avg övriga utgifter = snitt av 10 000/mån (bara mat — el matchades
    # mot en upcoming och ska EXKLUDERAS så den inte dubbelräknas)
    assert totals["avg_fixed_expenses"] == pytest.approx(10000.0)

    # expected_income = 35 000
    assert totals["expected_income"] == pytest.approx(35000.0)

    # Kvar att dela = 35000 - 3000 - 10000 = 22 000
    assert totals["available_to_split"] == pytest.approx(22000.0)


def test_avg_expenses_when_no_matched_upcomings(client):
    """Fallback: om inga upcoming är matchade ska snittet bara vara alla
    utgifter (som förr)."""
    c, SL = client
    from hembudget.db.models import Account, Transaction, UpcomingTransaction
    with SL() as s:
        acc = Account(name="A", bank="nordea", type="checking")
        s.add(acc); s.flush()
        for m in [1, 2, 3]:
            s.add(Transaction(
                account_id=acc.id, date=date(2026, m, 15),
                amount=Decimal("-12000.00"), currency="SEK",
                raw_description=f"Månad {m}", hash=f"t{m}",
            ))
        s.add(UpcomingTransaction(
            kind="income", name="X", amount=Decimal("30000"),
            expected_date=date(2026, 4, 25),
        ))
        s.commit()

    r = c.get("/upcoming/forecast?month=2026-04")
    assert r.status_code == 200
    totals = r.json()["totals"]
    assert totals["avg_fixed_expenses"] == pytest.approx(12000.0)
    # 30000 - 0 - 12000 = 18 000
    assert totals["available_to_split"] == pytest.approx(18000.0)
