"""Parser för SEB Kort Bank "KONTOUTDRAG" (SAS EuroBonus MC Premium m.fl.).

Målformat: PDF med text-layer. Layout:
- Header: "KONTOUTDRAG december 2025" + "SAS EuroBonus MC Premium"
- "Kontonummer: 403538411614789"
- Kolumner: Datum | Specifikation | Ort | Valuta | Kurs | Bokföringsdag | Belopp
- "SKULD FRÅN YYMMDD" → ingående skuld
- "BETALT BG DATUM YYMMDD" → inbetalning (negativt belopp)
- "KORT NR **** **** **** XXXX FIRSTNAME LASTNAME" → kortinnehavare-sektion
- "TOTALT DETTA KORT" per kort + "SKULD PER YYMMDD" i slutet
- Betalningsinfo-ruta: Köpgräns, OCR, betalningsvillkor
"""
from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal

from . import ParsedStatement, StatementLine

log = logging.getLogger(__name__)


SEB_HEADER_PATTERNS = (
    "KONTOUTDRAG",
    "SAS EuroBonus MC Premium",
    "SEB Kort Bank",
    "saseurobonusmastercard.se",
)


def looks_like_seb_kort(text: str) -> bool:
    # SEB Kort har "KONTOUTDRAG" i rubrik (inte "Faktura") + SEB Kort Bank
    has_kontoutdrag = "KONTOUTDRAG" in text
    has_seb = ("SEB Kort Bank" in text or "saseurobonusmastercard" in text)
    return has_kontoutdrag and has_seb


# --- Amount / date ---

def _parse_amount(s: str) -> Decimal:
    cleaned = s.replace(" ", "").replace(" ", "").replace(".", "")
    cleaned = cleaned.replace(",", ".")
    return Decimal(cleaned)


def _parse_date_yymmdd(s: str) -> date | None:
    """SEB Kort använder YYMMDD, t.ex. '251129' → 2025-11-29."""
    s = s.strip()
    if len(s) != 6 or not s.isdigit():
        return None
    y, m, d = int(s[:2]), int(s[2:4]), int(s[4:])
    year = 2000 + y if y < 80 else 1900 + y
    try:
        return date(year, m, d)
    except ValueError:
        return None


def _parse_iso_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# --- Regex-mönster ---

# SKULD FRÅN 251201   6032,91
_OPENING_RE = re.compile(
    r"SKULD\s+FRÅN\s+(\d{6})\s+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
# SKULD PER 251231   11344,02
_CLOSING_RE = re.compile(
    r"SKULD\s+PER\s+(\d{6})\s+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
# "Vill du betala hela månadens skuld ska du betala  11.344,02"
_TOTAL_RE = re.compile(
    r"hela\s+månadens\s+skuld\s+ska\s+du\s+betala[\s\n]+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
# "Vill du debitera är det lägsta beloppet att betala  345,00"
_MIN_RE = re.compile(
    r"lägsta\s+beloppet\s+att\s+betala[\s\n]+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
# "Betalning oss tillhanda senast  2026-01-30"
_DUE_RE = re.compile(
    r"oss\s+tillhanda\s+senast\s+(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_OCR_RE = re.compile(
    r"OCR\s*Nummer\s*[:：]?\s*(\d{8,})", re.IGNORECASE,
)
_BANKGIRO_RE = re.compile(
    r"Bankgiro(?:t)?[:\s]*(\d+-\d+)", re.IGNORECASE,
)
_ACCOUNT_NUM_RE = re.compile(
    r"Kontonummer\s*[:：]?\s*(\d{10,})", re.IGNORECASE,
)
_PERIOD_RE = re.compile(
    r"KONTOUTDRAG\s+(\w+)\s+(\d{4})", re.IGNORECASE,
)
_CREDIT_LIMIT_RE = re.compile(
    r"Köpgräns[\s\n]+([\d\s .]+,\d{2})", re.IGNORECASE,
)
_AMOUNT_ANY = re.compile(r"[\d .]+,\d{2}")

# Kortinnehavare: "KORT NR **** **** **** 9506 EVELINA FRÖJD"
# Banken visar 3 grupper av asterisker + sista 4 siffror + namn.
_CARDHOLDER_RE = re.compile(
    r"KORT\s+NR\s+(?:\*+\s+){2,4}(\d{4})\s+([A-ZÅÄÖ][A-ZÅÄÖ ]+?)(?=\s*\n)",
    re.MULTILINE,
)

# Transaktionsrad:
#   251128   COOP HJO          HJO         SEK              251201      70,90
#   251229   BETALT BG DATUM 251229                                    -6032,91
# Columns: Datum Specifikation Ort [Valuta] [Kurs] Bokföringsdag Belopp
# Belopp kan vara positiv (köp) eller negativ (inbetalning)
_TX_RE = re.compile(
    r"^\s*(\d{6})\s+"
    r"(.+?)"                          # specifikation + ort (fångar allt mittemellan)
    r"\s{2,}(SEK|EUR|USD|GBP|NOK|DKK|\w{3})?\s*"   # ev. valuta
    r"(?:([\d .]+,\d{1,4})\s*)?"      # ev. kurs
    r"(\d{6})?\s*"                    # ev. bokföringsdag
    r"(-?[\d\s .]+,\d{2})\s*$",
    re.MULTILINE,
)

_SUMMARY_MARKERS = (
    "TOTALT DETTA KORT",
    "SUMMA",
    "SKULD FRÅN",
    "SKULD PER",
    "OCR Nummer",
    "Kostnad pappersfaktura",
)


def parse_seb_kort(text: str) -> ParsedStatement:
    stmt = ParsedStatement(issuer="seb_kort")
    stmt.card_name = "SEB EuroBonus Mastercard Premium"

    if m := _TOTAL_RE.search(text):
        stmt.total_amount = _parse_amount(m.group(1))
    if m := _MIN_RE.search(text):
        stmt.minimum_amount = _parse_amount(m.group(1))
    # SEB:s PDF:er visar summorna i en tabulär layout där rader/kolumner
    # kan vara separerade långt från labeln. Fallback: "SKULD PER" är
    # alltid = totalbelopp att betala.
    if not stmt.total_amount:
        if m := _CLOSING_RE.search(text):
            stmt.total_amount = _parse_amount(m.group(2))
    # Försök hitta belopp från summaraden (Köpgräns, Kvar, Uttagen, Vill du
    # betala hela, Lägsta, Senast) genom att söka alla tal i rad efter
    # "Köpgräns"-sektionen
    if not stmt.minimum_amount:
        block = re.search(
            r"Köpgräns.*?(?=SEB\s+Kort|$)",
            text, flags=re.DOTALL | re.IGNORECASE,
        )
        if block:
            amounts = _AMOUNT_ANY.findall(block.group(0))
            # Förväntad ordning: Köpgräns, Kvar, Uttagen, TotalAttBetala,
            # Lägsta. Sista datumet är "senast". Sjätte-siste är lägsta.
            if len(amounts) >= 5:
                stmt.minimum_amount = _parse_amount(amounts[4])
    if m := _DUE_RE.search(text):
        stmt.due_date = _parse_iso_date(m.group(1))
    # Fallback: SEB:s tabelllayout separerar "senast"-labeln från själva
    # datumet. Ta sista ISO-datumet i dokumentet om inget hittats ännu —
    # det är alltid förfallodagen (den sista är längst fram i tiden).
    if stmt.due_date is None:
        iso_dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        parsed = [_parse_iso_date(d) for d in iso_dates]
        parsed = [d for d in parsed if d is not None]
        if parsed:
            stmt.due_date = max(parsed)
    if m := _OCR_RE.search(text):
        stmt.ocr_reference = m.group(1)
    if m := _BANKGIRO_RE.search(text):
        stmt.bankgiro = m.group(1)

    if m := _OPENING_RE.search(text):
        stmt.statement_period_start = _parse_date_yymmdd(m.group(1))
        stmt.opening_balance = _parse_amount(m.group(2))
    if m := _CLOSING_RE.search(text):
        stmt.statement_period_end = _parse_date_yymmdd(m.group(1))
        stmt.closing_balance = _parse_amount(m.group(2))

    # Kortinnehavare-index: mappa rad-position → holder
    cardholders = [(m.start(), m.group(1), m.group(2).strip())
                   for m in _CARDHOLDER_RE.finditer(text)]

    def _current_holder_at(pos: int) -> tuple[str | None, str | None]:
        """Senast nämnda kortinnehavare FÖRE given position i texten."""
        holder = None
        digits = None
        for start, last4, name in cardholders:
            if start < pos:
                digits = last4
                holder = name
            else:
                break
        return holder, digits

    # Transaktionsrader
    for m in _TX_RE.finditer(text):
        date_str = m.group(1)
        spec = (m.group(2) or "").strip()
        currency = m.group(3) or None
        booking_date = m.group(5)  # ev. används framgent
        amt_str = m.group(6)

        # Skippa summarader och rubriker
        if any(marker.lower() in spec.lower() for marker in _SUMMARY_MARKERS):
            continue
        if spec.upper().startswith("SKULD"):
            continue

        tx_date = _parse_date_yymmdd(date_str)
        if tx_date is None:
            continue
        amount_raw = _parse_amount(amt_str)

        # Tecken-logik: SEB:s layout visar belopp som POSITIVT för köp
        # (ökar skuld) och NEGATIVT för inbetalningar. Vi vill ha
        # motsatsen på kortkontot: köp = negativt (utgift), inbetalning
        # = positivt (pengar in).
        amount = -amount_raw

        # Specifikation = "COOP HJO   HJO" → merchant + city
        merchant, city = _split_merchant_city(spec)

        holder, last4 = _current_holder_at(m.start())
        if stmt.card_last_digits is None and last4 is not None:
            stmt.card_last_digits = last4

        stmt.transactions.append(StatementLine(
            date=tx_date,
            description=spec,
            merchant=merchant,
            city=city,
            amount=amount,
            cardholder=holder,
            foreign_currency=(currency if currency and currency != "SEK" else None),
        ))

    stmt.transactions.sort(key=lambda t: t.date)
    return stmt


def _split_merchant_city(desc: str) -> tuple[str, str | None]:
    """SEB-layouten: 'COOP HJO   HJO' eller 'ICA SUPERMARKET HJO   HJO'.
    3+ mellanslag delar vanligen merchant från stad."""
    parts = re.split(r"\s{3,}", desc.strip())
    if len(parts) >= 2:
        return parts[0].strip(), parts[-1].strip() or None
    # Annars: om sista ordet är versaler och finns som city också: dela
    tokens = desc.strip().rsplit(" ", 1)
    if len(tokens) == 2 and tokens[1].isupper() and len(tokens[1]) >= 3:
        # Heuristik: "COOP HJO HJO" → "COOP HJO" + "HJO"
        rest = tokens[0]
        if rest.upper().endswith(tokens[1]):
            return rest.strip(), tokens[1].strip()
    return desc.strip(), None
