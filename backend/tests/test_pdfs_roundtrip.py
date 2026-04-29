"""Roundtrip: rendera de tre Ekonomilabbet-PDF:erna och parse:a dem
tillbaka — verifiera att parser-anchors fortfarande finns trots ny
visuell layout (Skatteverket-stil lönespec, Nordea-stil kontoutdrag,
SEB Kort-stil kreditkortsfaktura).

Bakgrund: 2026-04 fick PDF:erna en seriös redesign för att se ut som
riktiga svenska bankdokument. Magic-headers (EKONOMILABBET LÖNESPEC
etc.) MÅSTE finnas i första 200 tecken, och parser-anchors (Datum +
Belopp/Köp, NETTOLÖN, Period:, Utbetalningsdag:, Arbetsgivare:,
Att betala) måste finnas kvar i texten.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from hembudget.parsers.ekonomilabbet import (
    detect_ekonomilabbet, parse_ekonomilabbet,
)
from hembudget.teacher.pdfs import (
    render_kontoutdrag, render_kreditkort, render_lonespec,
)
from hembudget.teacher.scenario import (
    CardEvent, MonthScenario, SalaryEvent, TxEvent,
)


def _make_scenario():
    sal = SalaryEvent(
        employer="Elajo Eltjänst",
        profession="Elektriker",
        gross=Decimal("33000"),
        grundavdrag=Decimal("1700"),
        kommunal_tax=Decimal("7500"),
        statlig_tax=Decimal("0"),
        net=Decimal("24200"),
        pay_date=date(2026, 4, 25),
    )
    sc = MonthScenario(
        year_month="2026-04",
        student_id=1,
        bank_account_no="1234 56 78901",
        card_account_no="4571 **** **** 9876",
        bank_name="Nordea",
        card_name="SEB Kort",
        salary=sal,
        opening_balance=Decimal("25000"),
        transactions=[
            TxEvent(date=date(2026, 4, 25), description="LÖN ELAJO",
                    amount=Decimal("24200"), category_hint="Lön"),
            TxEvent(date=date(2026, 4, 28), description="HYRA HALMSTAD",
                    amount=Decimal("-6500"), category_hint="Boende"),
            TxEvent(date=date(2026, 4, 30), description="ÖVERFÖRING SPARKONTO",
                    amount=Decimal("-2000"), category_hint="Sparande"),
        ],
        card_events=[
            CardEvent(date=date(2026, 4, 5), description="LIDL",
                      amount=Decimal("450"), category_hint="Mat"),
            CardEvent(date=date(2026, 4, 12), description="SPOTIFY",
                      amount=Decimal("119"), category_hint="Streaming"),
        ],
    )
    return sc


def test_lonespec_roundtrip():
    sc = _make_scenario()
    pdf = render_lonespec(sc.salary, sc)
    kind = detect_ekonomilabbet(pdf)
    assert kind == "lonespec"
    parsed = parse_ekonomilabbet(pdf)
    assert parsed is not None
    assert parsed.kind == "lonespec"
    # NETTOLÖN ska ge total_amount
    assert parsed.total_amount == Decimal("24200.00")
    # Utbetalningsdag + Arbetsgivare + Bruttolön-meta
    assert len(parsed.transactions) == 1
    tx = parsed.transactions[0]
    assert tx.date == date(2026, 4, 25)
    assert "ELAJO" in tx.description.upper()
    assert "employer" in parsed.meta


def test_kontoutdrag_roundtrip():
    sc = _make_scenario()
    pdf = render_kontoutdrag(sc)
    kind = detect_ekonomilabbet(pdf)
    assert kind == "kontoutdrag"
    parsed = parse_ekonomilabbet(pdf)
    assert parsed is not None
    assert parsed.kind == "kontoutdrag"
    # Tre transaktioner
    assert len(parsed.transactions) == 3
    descs = [t.description for t in parsed.transactions]
    assert any("LÖN" in d for d in descs)
    assert any("HYRA" in d for d in descs)
    assert any("ÖVERFÖRING SPARKONTO" in d for d in descs)
    # Period parsas
    assert parsed.period == "2026-04"


def test_kreditkort_roundtrip():
    sc = _make_scenario()
    pdf = render_kreditkort(sc.card_events, sc)
    kind = detect_ekonomilabbet(pdf)
    assert kind == "kreditkort_faktura"
    parsed = parse_ekonomilabbet(pdf)
    assert parsed is not None
    assert parsed.kind == "kreditkort_faktura"
    # Två köp + total_amount
    assert len(parsed.transactions) == 2
    assert parsed.total_amount == Decimal("569.00")  # 450 + 119
    descs = [t.description for t in parsed.transactions]
    assert any("LIDL" in d for d in descs)
    assert any("SPOTIFY" in d for d in descs)


def test_kreditkort_empty_does_not_crash():
    sc = _make_scenario()
    sc.card_events = []
    pdf = render_kreditkort([], sc)
    kind = detect_ekonomilabbet(pdf)
    assert kind == "kreditkort_faktura"
