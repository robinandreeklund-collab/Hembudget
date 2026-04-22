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
    "kontoutdrag",
    "sas eurobonus mc",
    "seb kort bank",
    "saseurobonusmastercard",
    "eurobonus mastercard",
)


def looks_like_seb_kort(text: str) -> bool:
    """Case-insensitive — SEB Kort har alltid "KONTOUTDRAG" + någon form
    av SEB Kort/EuroBonus-märkning."""
    low = (text or "").lower()
    has_kontoutdrag = "kontoutdrag" in low
    has_seb = (
        "seb kort" in low
        or "saseurobonusmastercard" in low
        or "sas eurobonus mc" in low
        or "eurobonus mastercard" in low
    )
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

# Format A (e-faktura): "SKULD FRÅN 251201 6032,91"
# Format B (pappersfaktura): "SALDO FRÅN FÖREGÅENDE KONTOUTDRAG 6985,50"
_OPENING_RE = re.compile(
    r"SKULD\s+FRÅN\s+(\d{6})\s+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
_OPENING_ALT_RE = re.compile(
    r"SALDO\s+FRÅN\s+FÖREGÅENDE\s+KONTOUTDRAG\s+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
# Format A: "SKULD PER 251231 11344,02"
# Format B: "Totalt saldo 17324,23" (i header-block)
_CLOSING_RE = re.compile(
    r"SKULD\s+PER\s+(\d{6})\s+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
_TOTAL_SALDO_RE = re.compile(
    r"Totalt\s+saldo\s+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
# "Vill du betala hela månadens skuld ska du betala  11.344,02" (format A)
_TOTAL_RE = re.compile(
    r"hela\s+månadens\s+skuld\s+ska\s+du\s+betala[\s\n]+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
# Format A: "Vill du debitera är det lägsta beloppet att betala  345,00"
# Format B: "Lägsta belopp att betala** 519,72"
_MIN_RE = re.compile(
    r"lägsta\s+belopp(?:et)?\s+att\s+betala\*?\*?[\s\n]+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
# Kreditutrymme (format B): "Kreditutrymme 20000,00"
_CREDIT_LIMIT_RE = re.compile(
    r"Kreditutrymme\s+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
# "Betalning oss tillhanda senast  2026-01-30"
_DUE_RE = re.compile(
    r"oss\s+tillhanda\s+senast\s+(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
# OCR: båda format stöds: "OCR Nummer: 403538411614789" och "OCR-nummer 128495819"
_OCR_RE = re.compile(
    r"OCR[\s\-]*[Nn]ummer\s*[:：]?\s*(\d{8,})", re.IGNORECASE,
)
# Bankgiro: "Bankgiro 595-4300" OCH "Bankgironummer 595-4300"
_BANKGIRO_RE = re.compile(
    r"Bankgiro(?:t|nummer)?[:\s]*(\d+-?\d+)", re.IGNORECASE,
)
_ACCOUNT_NUM_RE = re.compile(
    r"Kontonummer\s*[:：]?\s*(\d{10,})", re.IGNORECASE,
)
_PERIOD_RE = re.compile(
    r"KONTOUTDRAG\s+(\w+)\s+(\d{4})", re.IGNORECASE,
)
_KOPGRANS_RE = re.compile(
    r"Köpgräns[\s\n]+([\d\s .]+,\d{2})", re.IGNORECASE,
)
_AMOUNT_ANY = re.compile(r"[\d .]+,\d{2}")

# Kortinnehavare: två format stöds
# Format A (e-faktura): "KORT NR **** **** **** 9506 EVELINA FRÖJD"
# Format B (pappersfaktura): "EVELINA FRÖJD **** **** **** 9506"
# Banken visar 3 grupper av asterisker + sista 4 siffror + namn
_CARDHOLDER_RE = re.compile(
    r"KORT\s+NR\s+(?:\*+\s+){2,4}(\d{4})\s+([A-ZÅÄÖ][A-ZÅÄÖ ]+?)(?=\s*\n)",
    re.MULTILINE,
)
_CARDHOLDER_ALT_RE = re.compile(
    r"^(?!KORT\s+NR)([A-ZÅÄÖ][A-ZÅÄÖ]+(?:\s+[A-ZÅÄÖ][A-ZÅÄÖ]+)*)\s+"
    r"(?:\*+\s+){2,4}(\d{4})",
    re.MULTILINE,
)

# Datum-mönster i SEB: YYMMDD som fristående 6-siffrigt tal
_DATE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
# Valuta: 3-letter code, bara stora bokstäver
_CURRENCY_RE = re.compile(r"\b(SEK|EUR|USD|GBP|NOK|DKK|CHF|JPY)\b")
# Amount: signed decimal, tusentalsavgränsare valfri
_AMOUNT_RE = re.compile(
    r"(?<![\d.,])(-?\d{1,3}(?:[.\s]?\d{3})*,\d{2})(?!\d)"
)

_SUMMARY_MARKERS = (
    "TOTALT DETTA KORT",
    "SKULD FRÅN",
    "SKULD PER",
    "SALDO FRÅN FÖREGÅENDE",
    "SALDO FRÅN FÖREGÅENDE KONTOUTDRAG",
    "OCR Nummer",
    "OCR-nummer",
    "Totalt saldo",
    "Kreditutrymme",
    # OBS: "Kostnad pappersfaktura" är en legitim transaktion (avgift) och
    # ska INTE skippas trots att den ser ut som rubriktext.
)


def parse_seb_kort(text: str) -> ParsedStatement:
    stmt = ParsedStatement(issuer="seb_kort")
    stmt.card_name = "SEB EuroBonus Mastercard Premium"

    # Format A: "Vill du betala hela månadens skuld ska du betala ..."
    # Format B: "Totalt saldo ..."
    if m := _TOTAL_RE.search(text):
        stmt.total_amount = _parse_amount(m.group(1))
    elif m := _TOTAL_SALDO_RE.search(text):
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

    # Opening balance: format A eller B
    if m := _OPENING_RE.search(text):
        stmt.statement_period_start = _parse_date_yymmdd(m.group(1))
        stmt.opening_balance = _parse_amount(m.group(2))
    elif m := _OPENING_ALT_RE.search(text):
        stmt.opening_balance = _parse_amount(m.group(1))
    # Closing balance: format A
    if m := _CLOSING_RE.search(text):
        stmt.statement_period_end = _parse_date_yymmdd(m.group(1))
        stmt.closing_balance = _parse_amount(m.group(2))
    elif stmt.total_amount:
        # Format B: closing = total_amount
        stmt.closing_balance = stmt.total_amount

    # Kortinnehavare-index: mappa rad-position → holder
    # Stöd båda formaten:
    # Format A: "KORT NR **** **** **** 9506 EVELINA FRÖJD" → (last4, name)
    # Format B: "EVELINA FRÖJD **** **** **** 9506" → (last4, name)
    cardholders: list[tuple[int, str, str]] = []
    for m in _CARDHOLDER_RE.finditer(text):
        cardholders.append((m.start(), m.group(1), m.group(2).strip()))
    for m in _CARDHOLDER_ALT_RE.finditer(text):
        # Format B: grupp 1 = namn, grupp 2 = last4
        cardholders.append((m.start(), m.group(2), m.group(1).strip()))
    # Sortera per text-position
    cardholders.sort(key=lambda t: t[0])

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

    # Transaktioner: processa rad för rad. På varje rad:
    # 1. Hitta alla 6-siffriga datum + amounts i ordning
    # 2. Första datum = transaktionsdatum, spec = text mellan datum och
    #    amount (eller efter sista datum), sista amount = transaktionens
    #    belopp, ev. 2:a datum = bokföringsdag.
    # 3. Skippa SKULD FRÅN/SKULD PER/TOTALT-rader
    cumulative_offset = 0
    for line in text.split("\n"):
        line_offset = cumulative_offset
        cumulative_offset += len(line) + 1  # +1 för \n

        low = line.lower()
        if "skuld från" in low or "skuld per" in low or "totalt detta kort" in low:
            continue

        dates = list(_DATE_RE.finditer(line))
        amounts = list(_AMOUNT_RE.finditer(line))
        if not dates or not amounts:
            continue

        tx_date = _parse_date_yymmdd(dates[0].group(1))
        if tx_date is None:
            continue

        # Sista amount på raden = transaktionens belopp
        amt_match = amounts[-1]
        amt_str = amt_match.group(1)

        # Description: text mellan första datumet och amountet, minus ev.
        # andra datum, valuta, kurs
        desc_region_start = dates[0].end()
        desc_region_end = amt_match.start()
        desc_region = line[desc_region_start:desc_region_end]
        # Ta bort 6-siffrigt bokföringsdatum + valutakod från beskrivningen
        desc_region = _DATE_RE.sub("", desc_region)
        desc_region = _CURRENCY_RE.sub("", desc_region)
        # Ta bort ev. kurs (decimal som inte är amount)
        spec = re.sub(r"\s+", " ", desc_region).strip()
        spec = spec.rstrip(",.- ")

        # Hoppa över om spec är tom eller är rubrik-text
        if not spec or len(spec) < 2:
            continue
        if any(marker.lower() in spec.lower() for marker in _SUMMARY_MARKERS):
            continue

        # Currency
        cm = _CURRENCY_RE.search(line)
        currency = cm.group(1) if cm else None

        amount_raw = _parse_amount(amt_str)
        # SEB visar köp som POSITIVT (skuld ökar) → utgift för oss = negativt
        # Inbetalning (BETALT BG) är NEGATIVT i källan → positiv för oss
        amount = -amount_raw

        merchant, city = _split_merchant_city(spec)
        holder, last4 = _current_holder_at(line_offset)
        if stmt.card_last_digits is None and last4 is not None:
            stmt.card_last_digits = last4

        # Bankavgifter (pappersfaktura, valutatillägg etc.) attribueras
        # INTE till en kortinnehavare — de är gemensamma fakturaavgifter
        # som hör till parent-kortkontot.
        low_spec = spec.lower()
        if any(m in low_spec for m in (
            "pappersfaktura", "valutatillägg", "årsavgift", "aviavgift",
            "överdragsavgift", "försenings",
        )):
            holder = None

        stmt.transactions.append(StatementLine(
            date=tx_date,
            description=spec,
            merchant=merchant,
            city=city,
            amount=amount,
            cardholder=holder,
            foreign_currency=(currency if currency and currency != "SEK" else None),
        ))

    # Format B har rader utan datum för "Faktureringsavgift 35,00" och
    # liknande metadata-rader. Lägg till dem som tx med period-slutdatum.
    _FEE_RE = re.compile(
        r"(Faktureringsavgift|Aviavgift|Årsavgift|Overdragsavgift)\s+"
        r"([\d\s .]+,\d{2})",
        re.IGNORECASE,
    )
    # Använd sista existerande tx som "period-slut" eller today
    from datetime import date as _date
    fallback_date = (
        max((t.date for t in stmt.transactions), default=_date.today())
        if stmt.transactions
        else (stmt.statement_period_end or _date.today())
    )
    seen_fees: set[str] = set()
    for m in _FEE_RE.finditer(text):
        fee_name = m.group(1)
        if fee_name.lower() in seen_fees:
            continue
        seen_fees.add(fee_name.lower())
        amt_str = m.group(2)
        try:
            val = _parse_amount(amt_str)
        except Exception:
            continue
        stmt.transactions.append(StatementLine(
            date=fallback_date,
            description=fee_name,
            merchant=fee_name,
            city=None,
            amount=-val,  # avgifter = utgift
            cardholder=None,  # gemensam avgift
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
