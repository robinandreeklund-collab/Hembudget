"""Tester för Nordea "Kontohändelser"-PDF-parser.

Mot riktig användardata (ISK-kontoutdrag 2026-01-01 – 2026-04-22).
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from hembudget.parsers.pdf_statements.nordea_account import (
    looks_like_nordea_statement,
    parse_nordea_statement,
    parse_nordea_statement_pdf,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ISK_PDF = REPO_ROOT / "data_for_test" / "ISK_TEST" / (
    "Kontohändelser-47178384944-SEK-20260101-20260422.pdf"
)


@pytest.mark.skipif(not ISK_PDF.exists(), reason="ISK sample PDF saknas")
def test_nordea_isk_statement_parses():
    stmt = parse_nordea_statement_pdf(ISK_PDF.read_bytes())

    assert "ISK" in stmt.account_name.upper()
    assert stmt.account_number.replace(" ", "") == "47178384944"
    assert stmt.currency == "SEK"
    assert str(stmt.period_start) == "2026-01-01"
    assert str(stmt.period_end) == "2026-04-22"
    assert stmt.opening_balance == Decimal("2000.99")
    assert stmt.closing_balance == Decimal("0.99")

    # Kontrollera att transaktioner extraherades
    assert len(stmt.transactions) >= 20

    # Opening + summa(amount) ska matcha closing (± avrundning)
    total = sum((t.amount for t in stmt.transactions), Decimal("0"))
    assert abs(stmt.opening_balance + total - stmt.closing_balance) <= Decimal("0.01")

    # Varje transaktion har datum inom perioden
    for t in stmt.transactions:
        assert stmt.period_start <= t.date <= stmt.period_end

    # Transaktioner ska vara stigande kronologiska
    for a, b in zip(stmt.transactions, stmt.transactions[1:]):
        assert a.date <= b.date


def test_looks_like_nordea_statement_detection():
    assert looks_like_nordea_statement("Summering kontoutdrag")
    assert looks_like_nordea_statement("KONTOHÄNDELSER & DETALJER")
    assert not looks_like_nordea_statement("SAS EuroBonus MC Premium kontoutdrag")
    assert not looks_like_nordea_statement("")


def test_parse_synthetic_nordea_text():
    """Minimalt test mot konstruerad text — skyddar regex mot regressioner
    även om riktiga PDF:en saknas."""
    text = """Summering kontoutdrag
Namn: ISK BAS    Clearingnummer: 4717
Kontonummer: 4717 83 84944    IBAN: SE1234567
Valuta: SEK    Från: 2026-01-01    Till: 2026-03-31
Ingående saldo: 1 000,00
Utgående saldo: 800,00

2026-03-15  Köp fondandelar Stratega 70  -100,00  800,00
2026-02-10  Köp fondandelar Stratega 50  -100,00  900,00
"""
    stmt = parse_nordea_statement(text)
    assert stmt.account_name == "ISK BAS"
    assert stmt.clearing_number == "4717"
    assert stmt.account_number == "4717 83 84944"
    assert stmt.currency == "SEK"
    assert stmt.opening_balance == Decimal("1000.00")
    assert stmt.closing_balance == Decimal("800.00")
    assert len(stmt.transactions) == 2
    # Sorterade kronologiskt
    assert stmt.transactions[0].date.isoformat() == "2026-02-10"
    assert stmt.transactions[1].date.isoformat() == "2026-03-15"
    assert stmt.transactions[0].amount == Decimal("-100.00")
