"""Parser för Nordeas "Kontohändelser"-PDF-utdrag.

Format från Nordea internetbanken (Ekonomi > Konton > Kontohändelser & detaljer):
- Header: "Summering kontoutdrag"
- Konto-info: Namn, Clearingnummer, Kontonummer, IBAN, Valuta
- Period: Från/Till, Dagar, Kontohändelser
- Transaktioner grupperade per månad
  (månadshuvud på egen rad, t.ex. "Mars 2026")
- Saldon: Ingående saldo, Utbetalningar, Inbetalningar, Utgående saldo

Exempeltransaktion:
    2026-03-30  Köp fondandelar Nordea Stratega 70  -200,00  0,99
    (datum, namn/beskrivning, belopp, löpande saldo)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from . import extract_pdf_text_layout

log = logging.getLogger(__name__)


@dataclass
class StatementTx:
    date: date
    description: str
    amount: Decimal          # signerat: negativt = utgift
    running_balance: Decimal  # saldo EFTER denna transaktion


@dataclass
class NordeaAccountStatement:
    account_name: str              # "ISK BAS", "Privatkonto" osv.
    account_number: str            # normaliserad "4717 83 84944"
    clearing_number: str | None = None
    iban: str | None = None
    currency: str = "SEK"
    period_start: date | None = None
    period_end: date | None = None
    opening_balance: Decimal = Decimal("0")
    closing_balance: Decimal = Decimal("0")
    transactions: list[StatementTx] = field(default_factory=list)


HEADER_PATTERNS = (
    "summering kontoutdrag",
    "kontohändelser & detaljer",
    "kontohändelser och detaljer",
)


def looks_like_nordea_statement(text: str) -> bool:
    low = (text or "").lower()
    return any(p in low for p in HEADER_PATTERNS)


_MONTH_NAMES = {
    "januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6,
    "juli": 7, "augusti": 8, "september": 9, "oktober": 10,
    "november": 11, "december": 12,
}

# Header-fält
_NAMN_RE = re.compile(r"Namn:\s*([^\n]+?)(?:\s{2,}|$)", re.IGNORECASE)
_CLEARING_RE = re.compile(r"Clearingnummer:\s*(\d+)", re.IGNORECASE)
_KONTO_RE = re.compile(
    r"Kontonummer:\s*([\d\s]+?)(?=\s{2,}|$|\n|IBAN)",
    re.IGNORECASE,
)
_IBAN_RE = re.compile(r"IBAN:\s*([A-Z]{2}\d+)", re.IGNORECASE)
_VALUTA_RE = re.compile(r"Valuta:\s*([A-Z]{3})", re.IGNORECASE)
_FROM_RE = re.compile(r"Från:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_TILL_RE = re.compile(r"Till:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_OPENING_RE = re.compile(
    r"Ingående\s+saldo:\s*(-?[\d\s .]+,\d{2})", re.IGNORECASE,
)
_CLOSING_RE = re.compile(
    r"Utgående\s+saldo:\s*(-?[\d\s .]+,\d{2})", re.IGNORECASE,
)


# Transaktionsrad: "YYYY-MM-DD  description  amount  saldo"
# Amount kan ha mellanslag som tusental ("-1 234,56")
_TX_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+(.+?)\s+"
    r"(-?\d{1,3}(?:[.\s]?\d{3})*,\d{2})\s+"
    r"(-?\d{1,3}(?:[.\s]?\d{3})*,\d{2})\s*$",
    re.MULTILINE,
)


def _parse_amount(s: str) -> Decimal:
    cleaned = s.replace(" ", "").replace(" ", "").replace(" ", "")
    cleaned = cleaned.replace(".", "").replace(",", ".")
    return Decimal(cleaned)


def _parse_iso_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def parse_nordea_statement(text: str) -> NordeaAccountStatement:
    """Parse:a utdragstexten från en Nordea Kontohändelser-PDF."""
    stmt = NordeaAccountStatement(
        account_name="",
        account_number="",
    )

    if m := _NAMN_RE.search(text):
        stmt.account_name = m.group(1).strip()
    if m := _CLEARING_RE.search(text):
        stmt.clearing_number = m.group(1).strip()
    if m := _KONTO_RE.search(text):
        stmt.account_number = re.sub(r"\s+", " ", m.group(1)).strip()
    if m := _IBAN_RE.search(text):
        stmt.iban = m.group(1).strip()
    if m := _VALUTA_RE.search(text):
        stmt.currency = m.group(1).strip()
    if m := _FROM_RE.search(text):
        stmt.period_start = _parse_iso_date(m.group(1))
    if m := _TILL_RE.search(text):
        stmt.period_end = _parse_iso_date(m.group(1))
    if m := _OPENING_RE.search(text):
        stmt.opening_balance = _parse_amount(m.group(1))
    if m := _CLOSING_RE.search(text):
        stmt.closing_balance = _parse_amount(m.group(1))

    # Transaktioner
    for m in _TX_RE.finditer(text):
        tx_date = _parse_iso_date(m.group(1))
        if tx_date is None:
            continue
        desc = m.group(2).strip()
        try:
            amount = _parse_amount(m.group(3))
            saldo = _parse_amount(m.group(4))
        except Exception:
            continue
        # Skippa summeringsrader ("Utbetalningar (24): -8 000,00")
        if any(marker in desc.lower() for marker in (
            "utbetalningar (", "inbetalningar (",
            "ingående saldo", "utgående saldo",
        )):
            continue
        stmt.transactions.append(StatementTx(
            date=tx_date,
            description=desc,
            amount=amount,
            running_balance=saldo,
        ))

    # Nordea listar transaktioner i OMVÄND kronologisk ordning (senaste först).
    # Vi sorterar stigande för konsistens.
    stmt.transactions.sort(key=lambda t: (t.date, -float(t.amount)))
    return stmt


def parse_nordea_statement_pdf(pdf_bytes: bytes) -> NordeaAccountStatement:
    """Hela pipeline: extrahera text från PDF och parsa."""
    text = extract_pdf_text_layout(pdf_bytes)
    return parse_nordea_statement(text)
