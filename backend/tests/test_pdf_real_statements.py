"""Integrationstest mot RIKTIGA kreditkortsfakturor i data/.

Dessa PDFer är anonymiserade kopior av faktiska Amex/SEB Kort-fakturor
från en användare. De säkrar att parsern fungerar end-to-end mot
bankens verkliga layout — inte bara syntetisk test-text.

Om parserlogiken ändras och bryter dessa tester, PDF-parsningen fungerar
INTE längre i produktion även om de syntetiska testerna fortfarande
passerar.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from hembudget.parsers.pdf_statements.detect import parse_statement

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

AMEX_PDF = DATA_DIR / "2026-02-02 (1).pdf"
SEB_PDF = DATA_DIR / "5b3d3093-538d-41c3-af6a-8a285d5ec9a1.pdf"


@pytest.mark.skipif(not AMEX_PDF.exists(), reason="Amex sample PDF saknas")
def test_amex_real_pdf_extraction():
    """Full parse av en riktig SAS Amex Premium-faktura från feb 2026."""
    s = parse_statement(AMEX_PDF.read_bytes())

    # Headerfält
    assert s.issuer == "amex"
    assert s.total_amount == Decimal("13445.08")
    assert s.minimum_amount == Decimal("403.35")
    assert str(s.due_date) == "2026-02-27"
    assert s.bankgiro == "5127-5477"
    assert s.ocr_reference == "37939513843100975"

    # Alla 42 transaktioner extraherade (2 inbet + 35 köp Karl + 5 extrakort Rut)
    assert len(s.transactions) == 42

    # Pengar in till kortkontot (inbetalningar + refunder) = 42 656,78 kr
    pos = sum(t.amount for t in s.transactions if t.amount > 0)
    assert pos == Decimal("42656.78")

    # Utgifter (riktiga köp) = 16 418,08 kr
    neg = sum(-t.amount for t in s.transactions if t.amount < 0)
    assert neg == Decimal("16418.08")

    # Kortinnehavar-attribuering
    holders = {t.cardholder for t in s.transactions if t.cardholder}
    assert any("Karl Robin" in h for h in holders)
    assert any("Rut Elin" in h for h in holders)

    # Specifika nyckeltransaktioner
    max_burgers = [t for t in s.transactions if "Max Burgers" in t.description]
    assert len(max_burgers) == 1
    assert max_burgers[0].amount == Decimal("-412.00")

    # KLM-refunder (5 st, alla positiva)
    klm_refunds = [t for t in s.transactions if "Klm" in t.description and t.amount > 0]
    assert len(klm_refunds) == 5

    # Stor inbetalning
    big_payment = [t for t in s.transactions if "Betalning Mottagen" in t.description and t.amount > 20000]
    assert len(big_payment) == 1
    assert big_payment[0].amount == Decimal("23283.78")


@pytest.mark.skipif(not SEB_PDF.exists(), reason="SEB Kort sample PDF saknas")
def test_seb_kort_real_pdf_extraction():
    """Full parse av ett riktigt SAS EuroBonus MC Premium kontoutdrag
    (december 2025)."""
    s = parse_statement(SEB_PDF.read_bytes())

    assert s.issuer == "seb_kort"
    assert s.total_amount == Decimal("11344.02")
    assert str(s.due_date) == "2026-01-30"
    assert s.opening_balance == Decimal("6032.91")
    assert s.closing_balance == Decimal("11344.02")
    assert s.bankgiro == "595-4300"
    assert s.ocr_reference == "403538411614789"

    # Pengar in (BETALT BG) = 6 032,91 kr (= opening som betalades)
    pos = sum(t.amount for t in s.transactions if t.amount > 0)
    assert pos == Decimal("6032.91")

    # Köp totalt = 11 344,02 kr (= closing, matchar "SKULD PER")
    neg = sum(-t.amount for t in s.transactions if t.amount < 0)
    assert neg == Decimal("11344.02")

    # Minst 45 transaktioner (34 Evelina + 11 Robin + BETALT + pappers)
    assert len(s.transactions) >= 45

    # Per-kort-attribuering
    holders = {t.cardholder for t in s.transactions if t.cardholder}
    assert any("EVELINA" in h for h in holders)
    assert any("ROBIN" in h for h in holders)

    # BETALT BG
    paid = [t for t in s.transactions if "BETALT" in t.description]
    assert len(paid) == 1
    assert paid[0].amount == Decimal("6032.91")

    # Kostnad pappersfaktura
    paper = [t for t in s.transactions if "pappersfaktura" in t.description.lower()]
    assert len(paper) == 1
    assert paper[0].amount == Decimal("-35.00")


@pytest.mark.skipif(not AMEX_PDF.exists(), reason="Amex sample PDF saknas")
def test_amex_net_balance_matches_header():
    """Invariants: summan av transaktioner ska stämma med header-nyckeltal.

    Nya köp (header) - Nya inbetalningar (header) = saldo-förändring under
    perioden = slutsaldo - ingående saldo.
    """
    s = parse_statement(AMEX_PDF.read_bytes())
    # sum(transactions) ur vår perspektiv = (inbet) - (köp) = 42656.78 - 16418.08
    net = sum(t.amount for t in s.transactions)
    # Från header: nya köp 16418.08, nya inbetalningar -42656.78
    # (Föregående 39683.78 - 42656.78 + 16418.08 = 13445.08 ✓ )
    assert net == Decimal("26238.70")
