"""Integrationstest för hela "Kommande / prognos / huvudbok"-flödet.

Användaren rapporterade att siffrorna i olika vyer inte stämde:
- Prognosen "Kommande fakturor 34 233 kr" men listans total 72 100 kr.
- Delbetalda upcomings försvann från Kommande.
- Lånebetalningar räknades dubbelt.
- Huvudbokens "Interna överföringar balanserar" hade stor summa
  utan synliga orphans.

Det här testet bygger ett komplett scenario (flera konton, lön,
fakturor, partiella betalningar, lån, transfer-pair, upcoming-match)
och verifierar att ALLA tre vyer — /upcoming/forecast, /upcoming/ och
/ledger/ — rapporterar samma siffror enligt reglerna:

- Fullt betald upcoming räknas inte i forecast/kommande total.
- Delbetald räknas med åTERSTÅENDE, inte ursprungsbelopp.
- Auto:loan_schedule upcoming räknas som lån, inte faktura.
- Upcoming-matchad tx (+ dess pair-partner) räknas inte som transfer.
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


def _seed_scenario(SL):
    """Sätter upp ett realistiskt hushåll:
    - Checking-konto + Amex-kreditkonto + sparkonto
    - Lön 35 000 kr (upcoming income, ej matchad)
    - Elräkning 1 500 kr (upcoming, ej matchad — hel)
    - Amex-faktura 27 000 kr med 2 000 kr partiell betalning
    - Fullt betald faktura 500 kr (paid_amount == amount)
    - Bolån 7 000 kr i schedule (materialiserad som auto:loan_schedule)
    - En internöverföring 5 000 kr mellan två konton (paired)
    """
    from hembudget.db.models import (
        Account, Loan, LoanScheduleEntry, Transaction,
        UpcomingPayment, UpcomingTransaction,
    )

    with SL() as s:
        chk = Account(name="Checking", bank="nordea", type="checking")
        amex = Account(name="SAS Amex", bank="amex", type="credit")
        spar = Account(name="Sparkonto", bank="nordea", type="savings",
                       opening_balance=Decimal("10000"),
                       opening_balance_date=date(2025, 12, 31))
        s.add_all([chk, amex, spar]); s.flush()

        loan = Loan(
            name="Bolån", lender="SBAB",
            principal_amount=Decimal("2000000"),
            start_date=date(2020, 1, 1), interest_rate=0.03,
        )
        s.add(loan); s.flush()

        # Lån-schedule (framtida rat i april)
        s.add(LoanScheduleEntry(
            loan_id=loan.id, due_date=date(2026, 4, 28),
            amount=Decimal("7000"), payment_type="interest",
        ))

        # Lön (upcoming income, unmatched)
        s.add(UpcomingTransaction(
            kind="income", name="Lön",
            amount=Decimal("35000"), expected_date=date(2026, 4, 25),
        ))

        # Elräkning (upcoming bill, unmatched, unpaid)
        s.add(UpcomingTransaction(
            kind="bill", name="Vattenfall el",
            amount=Decimal("1500"), expected_date=date(2026, 4, 15),
        ))

        # Amex-faktura — 27 000 kr, 2 000 kr delbetalning
        tx_partial = Transaction(
            account_id=chk.id, date=date(2026, 4, 10),
            amount=Decimal("-2000"), currency="SEK",
            raw_description="Amex delbet", hash="h_amex",
        )
        s.add(tx_partial); s.flush()
        amex_up = UpcomingTransaction(
            kind="bill", name="Amex april",
            amount=Decimal("27000"), expected_date=date(2026, 4, 25),
            matched_transaction_id=tx_partial.id,
        )
        s.add(amex_up); s.flush()
        s.add(UpcomingPayment(upcoming_id=amex_up.id, transaction_id=tx_partial.id))

        # Fullt betald faktura — 500 kr, betalat 500 kr
        tx_full = Transaction(
            account_id=chk.id, date=date(2026, 4, 5),
            amount=Decimal("-500"), currency="SEK",
            raw_description="Spotify", hash="h_spot",
        )
        s.add(tx_full); s.flush()
        paid_up = UpcomingTransaction(
            kind="bill", name="Spotify",
            amount=Decimal("500"), expected_date=date(2026, 4, 5),
            matched_transaction_id=tx_full.id,
        )
        s.add(paid_up); s.flush()
        s.add(UpcomingPayment(upcoming_id=paid_up.id, transaction_id=tx_full.id))

        # Materialiserad loan-schedule upcoming (ska INTE räknas i
        # forecast.bills_total eftersom den är en lån-rat)
        s.add(UpcomingTransaction(
            kind="bill", name="Bolån (interest)",
            amount=Decimal("7000"),
            expected_date=date(2026, 4, 28),
            source="auto:loan_schedule",
            notes=f"loan:{loan.id}:2026-04-28",
        ))

        # Internöverföring, paired — 5 000 kr från checking till spar
        tx_out = Transaction(
            account_id=chk.id, date=date(2026, 4, 12),
            amount=Decimal("-5000"), currency="SEK",
            raw_description="Överföring till sparkonto", hash="h_xfer_out",
            is_transfer=True,
        )
        tx_in = Transaction(
            account_id=spar.id, date=date(2026, 4, 12),
            amount=Decimal("5000"), currency="SEK",
            raw_description="Insättning från checking", hash="h_xfer_in",
            is_transfer=True,
        )
        s.add_all([tx_out, tx_in]); s.flush()
        tx_out.transfer_pair_id = tx_in.id
        tx_in.transfer_pair_id = tx_out.id

        s.commit()
        return {
            "chk_id": chk.id, "amex_id": amex.id, "spar_id": spar.id,
            "loan_id": loan.id,
            "amex_up_id": amex_up.id, "paid_up_id": paid_up.id,
            "tx_partial_id": tx_partial.id,
            "tx_full_id": tx_full.id,
            "tx_xfer_out_id": tx_out.id, "tx_xfer_in_id": tx_in.id,
        }


def test_forecast_matches_kommande_list(client):
    """Forecast.totals.upcoming_bills måste vara SAMMA summa som
    Kommande-listans remaining-total för samma månad (ej-betalda +
    delbetaldas åTERSTÅENDE, exkl. loan_schedule)."""
    c, SL = client
    ids = _seed_scenario(SL)

    # Forecast
    fc = c.get("/upcoming/forecast?month=2026-04").json()
    bills_total = fc["totals"]["upcoming_bills"]
    loan_total = fc["totals"]["loan_scheduled"]
    income_total = fc["totals"]["expected_income"]

    # Kommande-listan för samma månad — vi räknar själva efter samma regler
    ups = c.get("/upcoming/?only_future=false").json()
    april_bills = [
        u for u in ups
        if u["kind"] == "bill"
        and u["expected_date"].startswith("2026-04")
        and u["source"] != "auto:loan_schedule"
    ]
    april_income = [
        u for u in ups
        if u["kind"] == "income" and u["expected_date"].startswith("2026-04")
    ]
    expected_bills_remaining = sum(
        u["amount"] - u.get("paid_amount", 0)
        for u in april_bills
        if u["payment_status"] != "paid"
    )
    expected_income_remaining = sum(
        u["amount"] - u.get("paid_amount", 0)
        for u in april_income
        if u["payment_status"] != "paid"
    )

    # Vattenfall 1500 + Amex remaining 25000 = 26500
    assert bills_total == pytest.approx(26500.0)
    assert bills_total == pytest.approx(expected_bills_remaining)

    # Lön 35000 — ej matchad, hel summa räknas
    assert income_total == pytest.approx(35000.0)
    assert income_total == pytest.approx(expected_income_remaining)

    # Bolån 7000 — bara via loan_scheduled, inte i bills
    assert loan_total == pytest.approx(7000.0)


def test_fully_paid_bill_excluded_from_forecast(client):
    """Spotify 500 kr är fullt betald — ska INTE finnas i upcoming_bills."""
    c, SL = client
    _seed_scenario(SL)

    fc = c.get("/upcoming/forecast?month=2026-04").json()
    # bills_total = 26500 (se test ovan). Om Spotify 500 råkade
    # räknas igen skulle det bli 27000.
    assert fc["totals"]["upcoming_bills"] == pytest.approx(26500.0)


def test_loan_schedule_not_double_counted(client):
    """Bolånet ska räknas i loan_scheduled (7000), inte i bills_total."""
    c, SL = client
    _seed_scenario(SL)

    fc = c.get("/upcoming/forecast?month=2026-04").json()
    totals = fc["totals"]
    # Kvar efter kända = 35000 - 26500 - 7000 = 1500
    assert totals["after_known_bills"] == pytest.approx(1500.0)


def test_partial_bill_stays_in_kommande_with_remaining(client):
    """Amex-fakturan (27 000 med 2 000 betalat) ska ligga kvar i
    /upcoming/?status=open med payment_status='partial' och
    paid_amount=2000."""
    c, SL = client
    ids = _seed_scenario(SL)

    ups = c.get("/upcoming/?only_future=false&status=open").json()
    amex = next(u for u in ups if u["id"] == ids["amex_up_id"])
    assert amex["payment_status"] == "partial"
    assert amex["paid_amount"] == pytest.approx(2000.0)
    # Spotify är fullt betald — ska INTE synas när status=open
    assert all(u["id"] != ids["paid_up_id"] for u in ups)


def test_ledger_transfer_balance_is_zero_for_paired_transfer(client):
    """Ett balanserat transfer-par (-5000 checking / +5000 spar)
    ska ge transfer_sum = 0 i huvudboken (`Interna överföringar
    balanserar` = passed)."""
    c, SL = client
    _seed_scenario(SL)

    r = c.get("/ledger/?month=2026-04")
    checks = r.json()["checks"]
    transfer = next(
        c for c in checks if c["name"] == "Interna överföringar balanserar"
    )
    assert transfer["passed"], f"value={transfer['value']}"
    assert abs(transfer["value"]) <= 2.0


def test_upcoming_list_exposes_payment_transactions_for_unmatch_ui(client):
    """/upcoming/ ska returnera payment_transactions med full detalj per
    delbetalning (date, amount, description, account_name) så /upcoming-
    UI:t kan visa listan + 'Ångra'-knappar utan extra fetch."""
    c, SL = client
    ids = _seed_scenario(SL)

    ups = c.get("/upcoming/?only_future=false").json()
    amex = next(u for u in ups if u["id"] == ids["amex_up_id"])
    assert len(amex["payment_transactions"]) == 1
    p = amex["payment_transactions"][0]
    assert p["id"] == ids["tx_partial_id"]
    assert p["amount"] == pytest.approx(-2000.0)
    assert p["description"] == "Amex delbet"
    assert p["account_name"] == "Checking"


def test_unmatch_upcoming_removes_tx_from_payment_list(client):
    """Efter /transactions/{tx_id}/unmatch-upcoming ska tx:en ej längre
    räknas som delbetalning — upcomingens payment_status går tillbaka
    till 'unpaid' eller 'partial' beroende på om fler betalningar fanns."""
    c, SL = client
    ids = _seed_scenario(SL)

    # Ångra Amex-delbetalningen
    r = c.post(f"/transactions/{ids['tx_partial_id']}/unmatch-upcoming")
    assert r.status_code == 200, r.text

    ups = c.get("/upcoming/?only_future=false").json()
    amex = next(u for u in ups if u["id"] == ids["amex_up_id"])
    assert amex["payment_status"] == "unpaid"
    assert amex["paid_amount"] == pytest.approx(0.0)
    assert len(amex["payment_transactions"]) == 0


def test_ledger_upcoming_summary_uses_remaining_for_partial(client):
    """upcoming_summary.unmatched_sum ska vara 26 500 (1500 el +
    25 000 Amex-remaining) + 7000 bolån = 33 500. Bolånet räknas med
    eftersom det ligger i upcoming_transactions-tabellen. Spotify
    räknas som matched."""
    c, SL = client
    _seed_scenario(SL)

    r = c.get("/ledger/?month=2026-04")
    summary = r.json()["upcoming_summary"]
    # 5 upcomings totalt i april: lön + el + amex + spotify + bolån
    assert summary["total"] == 5
    # Spotify = matchad (fullt betald)
    assert summary["matched"] == 1
    # Övriga 4 = unmatched
    assert summary["unmatched"] == 4
    # Summan i kr: lön 35000 + el 1500 + amex-rem 25000 + bolån 7000 = 68500
    assert summary["unmatched_sum"] == pytest.approx(68500.0)
