"""Tester för Skatteverket-fönster + verdict-pipeline (SKV-2-flöde).

Täcker:
- compute_window faserna off_season / granska / inlamna / stangd
- setup_after_submit · besked_due_on, payout_wave, late_fee
- process_pending_besked · Rudolf-verdict + slutskattebesked-mail
- process_pending_payouts · återbäring → tx + mail; kvarskatt → mail
- Edge: deadline 4 maj, dubbel-process-skydd, sen inlämning
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.db.base import Base
from hembudget.db.models import (
    Account, MailItem, TaxDeduction, TaxYearReturn, Transaction,
)
from hembudget.api.skatten_window import compute_window
from hembudget.api.skatten_pipeline import (
    setup_after_submit, process_pending_besked,
    process_pending_payouts,
)


@pytest.fixture()
def session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


@pytest.fixture()
def lonekonto(session):
    acc = Account(
        name="Lönekonto",
        bank="Testbank",
        type="checking",
    )
    session.add(acc)
    session.flush()
    return acc


# === compute_window ===


def test_window_off_season_jan():
    """Jan = off_season · aktören låst."""
    state = compute_window(date(2027, 1, 15))
    assert state.phase == "off_season"
    assert state.can_read is False
    assert state.submit_open is False
    assert state.tax_year == 2026
    assert state.opens_on == date(2027, 3, 2)


def test_window_anchor_year_clamps_to_2026():
    """Spel börjar 2026-01-01 · eleven har ingen inkomst innan dess.
    Första deklarationen är för 2026 (inte 2025), öppnar mars 2027.

    Verkligheten skulle säga 'deklarera för 2025' i jan 2026 — men
    eleven har inte spelat 2025 så det vore tomt + förvirrande.
    """
    state = compute_window(date(2026, 1, 15))
    assert state.phase == "off_season"
    assert state.tax_year == 2026, (
        f"Förväntade 2026 (anchor-clamp), fick {state.tax_year}"
    )
    assert state.opens_on == date(2027, 3, 2)
    assert "2026" in state.description
    assert "2025" not in state.description


def test_window_anchor_july_still_2026():
    """Mitt i första spel-året (juli 2026) → fortfarande off_season
    för år 2026 (nästa fönster 2027-03)."""
    state = compute_window(date(2026, 7, 15))
    assert state.phase == "off_season"
    assert state.tax_year == 2026
    assert state.opens_on == date(2027, 3, 2)


def test_window_granska_mars_2():
    """2-16 mars = granska · läs-läge, ingen submit."""
    state = compute_window(date(2027, 3, 2))
    assert state.phase == "granska"
    assert state.can_read is True
    assert state.submit_open is False
    assert state.opens_on == date(2027, 3, 17)


def test_window_inlamna_mars_17():
    """17 mars - 4 maj = inlamna · submit aktiverat."""
    state = compute_window(date(2027, 3, 17))
    assert state.phase == "inlamna"
    assert state.submit_open is True
    assert state.closes_on == date(2027, 5, 4)


def test_window_inlamna_last_day():
    """4 maj exakt = inlamna fortfarande."""
    state = compute_window(date(2027, 5, 4))
    assert state.phase == "inlamna"
    assert state.submit_open is True


def test_window_stangd_after_may_4():
    """5 maj = stangd · förseningsavgift gäller."""
    state = compute_window(date(2027, 5, 5))
    assert state.phase == "stangd"
    assert state.submit_open is False
    # Nästa öppning = 2 mars NÄSTA år
    assert state.opens_on == date(2028, 3, 2)


# === setup_after_submit ===


def test_submit_in_time_wave_1(session):
    """Submit 20 mars → våg 1 (april), inga late_fee."""
    ret = TaxYearReturn(
        year=2026,
        gross_income=Decimal("300000"),
        prelim_tax_paid=Decimal("75000"),
        final_tax=Decimal("70000"),
        diff=Decimal("5000"),  # 5 000 kr återbäring
        locked=True,
    )
    session.add(ret)
    session.flush()
    today = date(2027, 3, 20)  # före 31 mars
    info = setup_after_submit(session, tax_return=ret, today_game=today)

    assert ret.status == "submitted"
    assert ret.besked_due_on == today + timedelta(days=3)
    assert ret.payout_wave == 1
    assert ret.payout_due_on == date(2027, 4, 7)
    assert ret.late_fee == Decimal("0")
    assert info["case_no"].startswith("SKV-2026-")
    # Mottagningsmail finns i postlådan
    mails = session.query(MailItem).filter(
        MailItem.subject.like("Mottagningskvitto%"),
    ).all()
    assert len(mails) == 1


def test_submit_after_digital_deadline_wave_2(session):
    """Submit 15 april → våg 2 (juni)."""
    ret = TaxYearReturn(
        year=2026,
        gross_income=Decimal("300000"),
        prelim_tax_paid=Decimal("75000"),
        final_tax=Decimal("70000"),
        diff=Decimal("5000"),
        locked=True,
    )
    session.add(ret); session.flush()
    today = date(2027, 4, 15)  # 1 apr - 4 maj
    setup_after_submit(session, tax_return=ret, today_game=today)
    assert ret.payout_wave == 2
    assert ret.payout_due_on == date(2027, 6, 9)
    assert ret.late_fee == Decimal("0")


def test_submit_after_may_4_late_fee(session):
    """Sen inlämning → 1 250 kr förseningsavgift + payout_wave=0."""
    ret = TaxYearReturn(
        year=2026,
        gross_income=Decimal("300000"),
        prelim_tax_paid=Decimal("75000"),
        final_tax=Decimal("70000"),
        diff=Decimal("5000"),
        locked=True,
    )
    session.add(ret); session.flush()
    today = date(2027, 5, 10)  # efter 4 maj
    info = setup_after_submit(session, tax_return=ret, today_game=today)
    assert ret.payout_wave == 0
    assert ret.payout_due_on is None
    assert ret.late_fee == Decimal("1250")
    assert "förseningsavgift" in info["wave_message"].lower()


# === process_pending_besked · Rudolf-verdict ===


def test_besked_godkand_simple(session):
    """Submit utan kontroversiella avdrag → godkand."""
    ret = TaxYearReturn(
        year=2026,
        gross_income=Decimal("300000"),
        prelim_tax_paid=Decimal("75000"),
        final_tax=Decimal("70000"),
        diff=Decimal("5000"),  # återbäring
        locked=True,
    )
    session.add(ret); session.flush()
    setup_after_submit(session, tax_return=ret, today_game=date(2027, 3, 20))

    # Tick fram 3 spel-dagar
    process_pending_besked(session, today_game=date(2027, 3, 23))
    session.refresh(ret)
    assert ret.verdict == "godkand"
    assert ret.status == "vantar_utbetalning"

    # Slutskattebesked-mail finns
    besked = session.query(MailItem).filter(
        MailItem.subject.like("Slutskattebesked%"),
    ).all()
    assert len(besked) == 1
    assert "GODKÄND" in besked[0].subject


def test_besked_kontroll_stora_reseavdrag(session):
    """Reseavdrag > 15 000 kr utan beskrivning → kontroll."""
    ret = TaxYearReturn(
        year=2026,
        gross_income=Decimal("300000"),
        prelim_tax_paid=Decimal("75000"),
        final_tax=Decimal("70000"),
        diff=Decimal("0"),
        locked=True,
    )
    session.add(ret)
    # Stor rese-avdrag utan beskrivning
    session.add(TaxDeduction(
        year=2026, kind="rese", name="Pendling",
        description=None,  # saknar info
        amount=Decimal("18000"),
        source="manual",
    ))
    session.flush()
    setup_after_submit(session, tax_return=ret, today_game=date(2027, 3, 20))
    process_pending_besked(session, today_game=date(2027, 3, 23))
    session.refresh(ret)
    assert ret.verdict == "kontroll"
    assert ret.locked is False  # eleven kan omarbeta


def test_besked_avslag_stora_reseavdrag(session):
    """Reseavdrag > 30 000 kr → avslag."""
    ret = TaxYearReturn(
        year=2026,
        gross_income=Decimal("300000"),
        prelim_tax_paid=Decimal("75000"),
        final_tax=Decimal("70000"),
        diff=Decimal("0"),
        locked=True,
    )
    session.add(ret)
    session.add(TaxDeduction(
        year=2026, kind="rese", name="Pendling",
        description="Bil Sthlm-Uppsala",
        amount=Decimal("35000"),
        source="manual",
    ))
    session.flush()
    setup_after_submit(session, tax_return=ret, today_game=date(2027, 3, 20))
    process_pending_besked(session, today_game=date(2027, 3, 23))
    session.refresh(ret)
    assert ret.verdict == "avslag"


def test_besked_idempotent(session):
    """Två process-anrop ska INTE skapa två slutskattebesked-mail."""
    ret = TaxYearReturn(
        year=2026,
        gross_income=Decimal("300000"),
        prelim_tax_paid=Decimal("75000"),
        final_tax=Decimal("70000"),
        diff=Decimal("5000"),
        locked=True,
    )
    session.add(ret); session.flush()
    setup_after_submit(session, tax_return=ret, today_game=date(2027, 3, 20))

    process_pending_besked(session, today_game=date(2027, 3, 23))
    process_pending_besked(session, today_game=date(2027, 3, 24))

    besked = session.query(MailItem).filter(
        MailItem.subject.like("Slutskattebesked%"),
    ).all()
    assert len(besked) == 1, (
        "Bara EN slutskattebesked-mail · idempotency-skydd via "
        "status=submitted-filter (process går bara på submitted-rader)"
    )


# === process_pending_payouts · återbäring/kvarskatt ===


def test_payout_aterbaring_creates_tx(session, lonekonto):
    """Återbäring vid våg-datum → income-tx på lönekonto + glatt mail."""
    ret = TaxYearReturn(
        year=2026,
        gross_income=Decimal("300000"),
        prelim_tax_paid=Decimal("75000"),
        final_tax=Decimal("70000"),
        diff=Decimal("5000"),  # 5k återbäring
        locked=True,
        status="vantar_utbetalning",
        verdict="godkand",
        payout_wave=1,
        payout_due_on=date(2027, 4, 7),
    )
    session.add(ret); session.flush()

    process_pending_payouts(session, today_game=date(2027, 4, 7))
    session.refresh(ret)
    assert ret.status == "klar"

    tx = session.query(Transaction).filter(
        Transaction.account_id == lonekonto.id,
        Transaction.amount == Decimal("5000"),
    ).all()
    assert len(tx) == 1
    assert "återbäring" in tx[0].raw_description.lower()


def test_payout_kvarskatt_creates_mail_no_tx(session, lonekonto):
    """Kvarskatt → INGEN tx direkt · bara faktura-mail med due_date."""
    ret = TaxYearReturn(
        year=2026,
        gross_income=Decimal("300000"),
        prelim_tax_paid=Decimal("60000"),
        final_tax=Decimal("70000"),
        diff=Decimal("-10000"),  # 10k kvarskatt
        locked=True,
        status="vantar_utbetalning",
        verdict="godkand",
        payout_wave=1,
        payout_due_on=date(2027, 4, 7),
    )
    session.add(ret); session.flush()

    process_pending_payouts(session, today_game=date(2027, 4, 7))

    # Ingen tx
    txs = session.query(Transaction).all()
    assert len(txs) == 0
    # Men faktura-mail med due_date 12 mars 2028
    mails = session.query(MailItem).filter(
        MailItem.subject.like("Kvarskatt%"),
    ).all()
    assert len(mails) == 1
    assert mails[0].due_date == date(2028, 3, 12)


def test_payout_too_early_no_action(session, lonekonto):
    """Payout-process FÖRE due-datum ska inte göra något."""
    ret = TaxYearReturn(
        year=2026,
        gross_income=Decimal("300000"),
        prelim_tax_paid=Decimal("75000"),
        final_tax=Decimal("70000"),
        diff=Decimal("5000"),
        locked=True,
        status="vantar_utbetalning",
        verdict="godkand",
        payout_wave=1,
        payout_due_on=date(2027, 4, 7),
    )
    session.add(ret); session.flush()

    process_pending_payouts(session, today_game=date(2027, 4, 1))  # för tidigt
    session.refresh(ret)
    assert ret.status == "vantar_utbetalning"  # oförändrad
    assert session.query(Transaction).count() == 0
