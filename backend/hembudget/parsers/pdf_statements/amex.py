"""Parser för SAS Amex Premium-fakturor (svenska).

Målformat: PDF med text-layer. Layout från kund Karl Robin:
- Header: "SAS Amex Premium Faktura"
- Kontoöversikt: Fakturans saldo, Förfallodag, Bankgiro, OCR
- Inbetalningar-tabell: 2 datumkolumner + beskrivning + belopp CR
- Nya köp-tabell(er): 2 datumkolumner + merchant + stad + belopp
- En tabell per kortinnehavare (huvudkort + extrakort)
"""
from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal

from . import ParsedStatement, StatementLine

log = logging.getLogger(__name__)


# --- Detection ---

AMEX_HEADER_PATTERNS = (
    "SAS Amex Premium",
    "American Express",
    "americanexpress.se",
)


def looks_like_amex(text: str) -> bool:
    return any(p in text for p in AMEX_HEADER_PATTERNS)


# --- Amount parsing ---

_AMOUNT_RE = re.compile(r"[\d\s .]+,\d{2}")


def _parse_amount(s: str) -> Decimal:
    """Svenska tal: '13.445,08' eller '1 053,00' → Decimal."""
    cleaned = s.replace(" ", "").replace(" ", "").replace(".", "")
    cleaned = cleaned.replace(",", ".")
    return Decimal(cleaned)


def _parse_date_amex(s: str) -> date | None:
    """Amex använder DD.MM.YY."""
    try:
        d, m, y = s.split(".")
        year = 2000 + int(y) if int(y) < 80 else 1900 + int(y)
        return date(year, int(m), int(d))
    except (ValueError, TypeError):
        return None


# --- Header block ---

_TOTAL_RE = re.compile(
    r"Fakturans\s+saldo\s+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
_MIN_RE = re.compile(
    r"Lägsta\s+belopp\s+att\s+betala\s+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
_DUE_RE = re.compile(r"Förfallodag\s+(\d{2}\.\d{2}\.\d{2})", re.IGNORECASE)
_BANKGIRO_RE = re.compile(r"Bankgiro[:\s]*(\d+-\d+)", re.IGNORECASE)
_OCR_RE = re.compile(r"OCR[:\s]*(\d{8,})", re.IGNORECASE)
_CARD_LAST_RE = re.compile(r"Kortnumme[rt]\s+som\s+slutar\s+på[:\s]*(\d+)", re.IGNORECASE)
_PERIOD_RE = re.compile(
    r"Fakturans\s+period[:\s]+(\d{2}\.\d{2}\.\d{2})\s+till\s+(\d{2}\.\d{2}\.\d{2})",
    re.IGNORECASE,
)
_PREV_INVOICE_RE = re.compile(
    r"Föregående\s+faktura\s+([\d\s .]+,\d{2})", re.IGNORECASE
)
_NEW_PURCHASES_TOTAL_RE = re.compile(
    r"Nya\s+köp\s+([\d\s .]+,\d{2})", re.IGNORECASE
)
_NEW_PAYMENTS_RE = re.compile(
    r"Nya\s+inbetalningar\s+(-?[\d\s .]+,\d{2})", re.IGNORECASE
)


# --- Transaction rows ---

# En rad ser ut så här (två-kolumns-datum + merchant + valfri stad + belopp):
#   06.01.26  06.01.26  Max Burgers    Luleå           412,00
#   09.01.26  09.01.26  Betalning Mottagen, Tack   -16.400,00 CR
#   21.01.26  22.01.26  Klm            Stockholm    -495,00 CR
# Beloppet kan följas av "CR" på egen rad eller samma (CR = credit / inbetalning).
# Merchant kan ha mellanslag, stad sitter i slutet av raden före belopp.
# Vi använder en tolerant regex som fångar två datum + allt mellan + belopp + ev CR.
_TX_ROW_RE = re.compile(
    r"^\s*(\d{2}\.\d{2}\.\d{2})\s+(\d{2}\.\d{2}\.\d{2})\s+"
    r"(.+?)\s{2,}"                                        # beskrivning (minst 2 mellanslag före belopp)
    r"(-?[\d\s .]+,\d{2})"
    r"(?:\s*CR)?\s*$",
    re.MULTILINE,
)

# Kortinnehavare-markör: "Nya köp för Karl Robin Ludvig Fröjd"
_CARDHOLDER_SECTION_RE = re.compile(
    r"Nya\s+köp\s+för\s+([A-ZÅÄÖa-zåäö ]+?)(?:\s+Extrakort|\n|$)"
)


def parse_amex(text: str) -> ParsedStatement:
    stmt = ParsedStatement(issuer="amex")

    # Header-fält
    if m := _TOTAL_RE.search(text):
        stmt.total_amount = _parse_amount(m.group(1))
    if m := _MIN_RE.search(text):
        stmt.minimum_amount = _parse_amount(m.group(1))
    if m := _DUE_RE.search(text):
        stmt.due_date = _parse_date_amex(m.group(1))
    if m := _BANKGIRO_RE.search(text):
        stmt.bankgiro = m.group(1)
    if m := _OCR_RE.search(text):
        stmt.ocr_reference = m.group(1)
    if m := _CARD_LAST_RE.search(text):
        stmt.card_last_digits = m.group(1)[-4:]  # typiskt 5 siffror, ta sista 4
    if m := _PERIOD_RE.search(text):
        stmt.statement_period_start = _parse_date_amex(m.group(1))
        stmt.statement_period_end = _parse_date_amex(m.group(2))
    if m := _NEW_PURCHASES_TOTAL_RE.search(text):
        stmt.new_purchases_total = _parse_amount(m.group(1))
    if m := _NEW_PAYMENTS_RE.search(text):
        # Inbetalningar visas negativt (-42.656,78)
        stmt.payments_total = _parse_amount(m.group(1).lstrip("-")) * Decimal("-1")
    if m := _PREV_INVOICE_RE.search(text):
        stmt.opening_balance = _parse_amount(m.group(1))

    stmt.card_name = "SAS Amex Premium"

    # Transaktionsrader. Loopa över hela texten och fånga vilket
    # kortinnehavar-block vi är i.
    current_holder: str | None = None
    for match in re.finditer(
        r"(?P<holder_marker>Nya\s+köp\s+för\s+(?P<holder>[A-ZÅÄÖa-zåäö ]+?)(?:\s+Extrakort|\n))"
        r"|"
        r"(?P<tx>^\s*(?P<d1>\d{2}\.\d{2}\.\d{2})\s+(?P<d2>\d{2}\.\d{2}\.\d{2})\s+"
        r"(?P<desc>.+?)\s{2,}(?P<amt>-?[\d\s .]+,\d{2})(?P<cr>\s*CR)?\s*$)",
        text,
        flags=re.MULTILINE,
    ):
        if match.group("holder_marker"):
            current_holder = match.group("holder").strip()
            continue
        if match.group("tx"):
            d = _parse_date_amex(match.group("d1"))
            if d is None:
                continue
            desc = match.group("desc").strip()
            raw_amt = _parse_amount(match.group("amt"))
            is_credit = bool(match.group("cr"))
            # Inbetalningar (Betalning Mottagen): redan negativt tecken
            # i källan → vi visar som positivt på kontot (kredit = pengar in
            # till kortet). Vanliga köp: positiva i källan → vi lagrar som
            # negativa (utgift). Refunder/CR: positiva.
            if is_credit:
                amount = abs(raw_amt)  # pengar in = positivt
            else:
                amount = -abs(raw_amt)

            # Splittra "Merchant   City" om det finns två eller fler
            # mellanslag mellan delarna. Beskrivningar som "Amazon Prime
            # Www.Amazon.Se" bryts inte upp (ingen stad).
            merchant, city = _split_merchant_city(desc)
            stmt.transactions.append(StatementLine(
                date=d,
                description=desc,
                merchant=merchant,
                city=city,
                amount=amount,
                cardholder=current_holder,
            ))

    # Sortera transaktioner i datum-ordning
    stmt.transactions.sort(key=lambda t: t.date)
    return stmt


_KNOWN_CITIES = {
    "stockholm", "göteborg", "malmö", "uppsala", "västerås", "örebro",
    "linköping", "helsingborg", "jönköping", "norrköping", "umeå",
    "gävle", "borås", "södertälje", "eskilstuna", "halmstad", "växjö",
    "karlstad", "sundsvall", "hjo", "skövde", "skoevde", "luleå", "amsterdam",
    "hollyhill", "goteborg", "uddevalla", "alvsjo", "frederiksberg",
    "mollertorp", "mollerstorp", "mollerstoerp", "mollerstoerp",
}


def _split_merchant_city(desc: str) -> tuple[str, str | None]:
    """Försök plocka ut staden från slutet av beskrivningen.

    Amex lägger merchant + flera mellanslag + stad. Men har inte alltid
    stad, och ibland är merchant flerordig. Heuristik:
    1. Om sista ordet är en känd svensk stad → stad; resten = merchant.
    2. Om det finns minst 3 mellanslag före sista ordet → sista ordet = stad.
    3. Annars → hela desc = merchant.
    """
    stripped = desc.strip()
    # Gap med 3+ mellanslag delar ofta merchant från stad
    parts = re.split(r"\s{3,}", stripped)
    if len(parts) >= 2:
        return parts[0].strip(), parts[-1].strip()
    # Sista ordet som känd stad
    tokens = stripped.rsplit(" ", 1)
    if len(tokens) == 2 and tokens[1].lower() in _KNOWN_CITIES:
        return tokens[0].strip(), tokens[1].strip()
    return stripped, None
