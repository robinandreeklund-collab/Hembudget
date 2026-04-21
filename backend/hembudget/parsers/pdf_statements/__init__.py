"""Deterministiska PDF-parsers för svenska kreditkortsfakturor.

Ersätter vision-LLM-flödet för kända format (Amex Eurobonus, SEB Kort
Mastercard). PDF-text extraheras med pypdfium2 och matchas mot
regex-mönster specifika per utgivare.

Fördelar över vision:
- ~20× snabbare (ingen LLM-anrop)
- Stabilt — samma fält varje gång
- Exakta belopp (ingen OCR-drift)
- Funkar offline och utan LM Studio
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class StatementLine:
    """En rad på kreditkortsfakturan."""
    date: date                     # transaktionsdatum
    description: str               # merchant + ev. stad
    merchant: str                  # bara handlaren (utan stad)
    city: str | None               # stad om angivet
    amount: Decimal                # signerad: köp = negativt, inbetalning = positivt
    cardholder: str | None = None  # vilken kortinnehavare (extrakort)
    foreign_currency: str | None = None  # t.ex. "USD" för utlandsköp


@dataclass
class ParsedStatement:
    """Resultat från en parse:ad kreditkortsfaktura."""
    issuer: str                              # "amex" | "seb_kort"
    card_name: str | None = None
    card_last_digits: str | None = None
    statement_period_start: date | None = None
    statement_period_end: date | None = None
    total_amount: Decimal = Decimal("0")     # att betala
    minimum_amount: Decimal | None = None
    due_date: date | None = None
    opening_balance: Decimal | None = None   # föregående faktura / skuld från
    closing_balance: Decimal | None = None   # skuld per, ska ≈ total_amount
    bankgiro: str | None = None
    ocr_reference: str | None = None
    new_purchases_total: Decimal | None = None
    payments_total: Decimal | None = None
    transactions: list[StatementLine] = field(default_factory=list)


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extrahera all text från en PDF. Använder pypdfium2:s text-layer
    (inte OCR) — PDFer från banker är alltid text-baserade."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        pages_text: list[str] = []
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                tp = page.get_textpage()
                try:
                    pages_text.append(tp.get_text_bounded())
                finally:
                    tp.close()
            finally:
                page.close()
        return "\n".join(pages_text)
    finally:
        pdf.close()
