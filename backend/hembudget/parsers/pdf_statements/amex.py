"""Parser för SAS Amex Premium-fakturor (svenska).

Kan läsa både "line-based" text (fallback extract_pdf_text) och
layout-baserad text (extract_pdf_text_layout). Transaktionsraderna
innehåller alltid `DD.MM.YY DD.MM.YY <desc> <amount> [CR]`.
Rader kan ha 1 eller 2 transaktioner (vid 2-kolumns-layout på
sida 2+).
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
    "sas amex",
    "american express",
    "americanexpress.se",
    "amex europe",
    "amex premium",
)


def looks_like_amex(text: str) -> bool:
    low = (text or "").lower()
    return any(p in low for p in AMEX_HEADER_PATTERNS)


# --- Amount / date parsing ---

def _parse_amount(s: str) -> Decimal:
    cleaned = s.replace(" ", "").replace(" ", "").replace(".", "")
    cleaned = cleaned.replace(",", ".")
    return Decimal(cleaned)


def _parse_date_amex(s: str) -> date | None:
    """DD.MM.YY → date. Tillåter även 'DD MM YY' (med mellanslag som pypdfium2
    ibland producerar)."""
    s = s.strip().replace(" ", "")
    if "." in s:
        parts = s.split(".")
    elif len(s) == 6 and s.isdigit():
        parts = [s[:2], s[2:4], s[4:]]
    else:
        return None
    if len(parts) != 3:
        return None
    try:
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        year = 2000 + y if y < 80 else 1900 + y
        return date(year, m, d)
    except (ValueError, TypeError):
        return None


# --- Headers ---

# Stödjer både "Fakturans saldo 13.445,08" på samma rad och på separat rad
_TOTAL_RE = re.compile(
    r"Fakturans\s+saldo[\s\n]+([\d\s .]+,\d{2})", re.IGNORECASE,
)
_MIN_RE = re.compile(
    r"Lägsta\s+belopp\s+att\s+betala[\s\n]+([\d\s .]+,\d{2})",
    re.IGNORECASE,
)
_DUE_RE = re.compile(
    r"Förfallodag[\s\n]+(\d{2}[.\s]\d{2}[.\s]\d{2})", re.IGNORECASE,
)
_BANKGIRO_RE = re.compile(r"Bankgiro[:\s]+(\d+-\d+)", re.IGNORECASE)
_OCR_RE = re.compile(
    r"OCR[:\s]+((?:\d[\d\s]*){8,})", re.IGNORECASE,
)
_CARD_LAST_RE = re.compile(
    r"Kortnumme[rt]\s+som\s+slutar\s+på[:\s]+(\d+)", re.IGNORECASE,
)
_PERIOD_RE = re.compile(
    r"Fakturans\s+period[:\s]+"
    r"(\d{2}[.\s]\d{2}[.\s]\d{2})\s+till\s+(\d{2}[.\s]\d{2}[.\s]\d{2})",
    re.IGNORECASE,
)
_PREV_INVOICE_RE = re.compile(
    r"Föregående\s+faktura[\s\n]+([\d\s .]+,\d{2})", re.IGNORECASE,
)
_NEW_PURCHASES_TOTAL_RE = re.compile(
    r"Nya\s+köp[\s\n]+([\d\s .]+,\d{2})", re.IGNORECASE,
)
_NEW_PAYMENTS_RE = re.compile(
    r"Nya\s+inbetalningar[\s\n]+(-?[\d\s .]+,\d{2})", re.IGNORECASE,
)

# Kortinnehavar-sektion: "Nya köp för Karl Robin Ludvig Fröjd"
_CARDHOLDER_SECTION_RE = re.compile(
    r"Nya\s+köp\s+för\s+([A-ZÅÄÖa-zåäö]+(?:\s+[A-ZÅÄÖa-zåäö]+)*?)"
    r"(?=\s*(?:Extrakort|Transaktions|\n|$))",
    re.MULTILINE,
)

# Datumpar-mönster: transaktionsdatum + processdatum.
# Accepterar både "DD.MM.YY" och "DD  MM  YY" (2+ mellanslag) eftersom
# pypdfium2 ibland extraherar punkterna på en separat Y-koordinat som
# hamnar utanför grupperingen och försvinner.
_DATE_SEG = r"\d{2}[.\s]{1,3}\d{2}[.\s]{1,3}\d{2}"
_DATE_PAIR_RE = re.compile(
    rf"({_DATE_SEG})\s+({_DATE_SEG})"
)
# Belopp-mönster (standalone): bara positiva tal — tecknet avgörs
# av CR-markör och ev. ledande "-" (som checkas separat). Detta
# undviker att "Ikea Orebro - 30,00" tolkas som negativt belopp.
_STANDALONE_AMOUNT_RE = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:\.\d{3})*,\d{2})(?!\d)"
)

# Rader som är skräp — summarubriker, kolumnrubriker etc
_SKIP_PATTERNS = (
    "summa ",
    "summan av",
    "summa nya",
    "transaktions",
    "process",
    "belopp i sek",
    "datum",
    "gällande räntesatser",
    "kategori",
    "debiterad ränta",
    "räntesats",
    "nya köp",
    "nya inbetalningar",
    "inbetalningar",
    "ytterligare information",
    "amex",
    "faktura",
    "kontoöversikt",
    "kortnummer",
    "sammanfattning",
)


_EXACT_SKIP_WORDS = {"köp", "kontantuttag", "saldo", "fakturans saldo"}


def _contains_skip_word(desc: str) -> bool:
    """Check om description är en summa/rubrikrad som inte är en riktig transaktion."""
    low = desc.lower().strip()
    if low in _EXACT_SKIP_WORDS:
        return True
    for p in _SKIP_PATTERNS:
        if p in low:
            return True
    return False


def parse_amex(text: str) -> ParsedStatement:
    stmt = ParsedStatement(issuer="amex")
    stmt.card_name = "SAS Amex Premium"

    # --- Headers ---
    if m := _TOTAL_RE.search(text):
        stmt.total_amount = _parse_amount(m.group(1))
    if m := _MIN_RE.search(text):
        stmt.minimum_amount = _parse_amount(m.group(1))
    if m := _DUE_RE.search(text):
        stmt.due_date = _parse_date_amex(m.group(1))
    if m := _BANKGIRO_RE.search(text):
        stmt.bankgiro = m.group(1)
    # Ta SISTA matchen — Amex-fakturan visar OCR:en på flera ställen; den
    # sista (vid betalningsinfo-blocket längst ned) är typiskt renast.
    ocr_matches = list(_OCR_RE.finditer(text))
    if ocr_matches:
        m = ocr_matches[-1]
        ocr = re.sub(r"\s+", "", m.group(1))
        # Trimma till 17 siffror om längre — Amex OCR är alltid 17
        if len(ocr) > 17:
            ocr = ocr[-17:]
        stmt.ocr_reference = ocr
    if m := _CARD_LAST_RE.search(text):
        stmt.card_last_digits = m.group(1)[-4:]
    if m := _PERIOD_RE.search(text):
        stmt.statement_period_start = _parse_date_amex(m.group(1))
        stmt.statement_period_end = _parse_date_amex(m.group(2))
    if m := _PREV_INVOICE_RE.search(text):
        stmt.opening_balance = _parse_amount(m.group(1))
    if m := _NEW_PURCHASES_TOTAL_RE.search(text):
        # Kan matcha fel label om kollision — ok, vi är toleranta
        try:
            stmt.new_purchases_total = _parse_amount(m.group(1))
        except Exception:
            pass
    if m := _NEW_PAYMENTS_RE.search(text):
        try:
            val = _parse_amount(m.group(1).lstrip("-"))
            stmt.payments_total = val * Decimal("-1")
        except Exception:
            pass

    # Derive opening_balance om det inte hittades direkt. I Amex:s PDF
    # står "Föregående faktura"-labeln ofta på annan Y-rad än siffran
    # pga layout. Men vi kan reverse-enginera eftersom identiteten
    #   opening + new_purchases + payments_total = closing (= total_amount)
    # alltid håller. Om vi har 3 av 4, räkna fjärde.
    if stmt.opening_balance is None:
        if (
            stmt.total_amount
            and stmt.new_purchases_total is not None
            and stmt.payments_total is not None
        ):
            stmt.opening_balance = (
                stmt.total_amount
                - stmt.new_purchases_total
                - stmt.payments_total
            ).quantize(Decimal("0.01"))

    # --- Kortinnehavar-sektioner: mappa text-positioner till holders ---
    cardholders: list[tuple[int, str]] = []
    for m in _CARDHOLDER_SECTION_RE.finditer(text):
        name = m.group(1).strip()
        if len(name) > 2 and not _contains_skip_word(name):
            cardholders.append((m.start(), name))

    def _holder_at(pos: int) -> str | None:
        holder = None
        for start, name in cardholders:
            if start < pos:
                holder = name
            else:
                break
        return holder

    # --- Transaktioner ---
    # CR-markörer ignoreras helt — källans tecken är nog för att avgöra
    # om det är ett köp (positivt i källan → utgift hos oss) eller
    # inbetalning/retur (negativt i källan → pengar in hos oss).
    # Eventuella stray "CR"-rader splittas bort som egna noise-rader.
    lines = text.split("\n")
    merged: list[tuple[int, str]] = []
    char_offset = 0
    for line in lines:
        line_offset = char_offset
        char_offset += len(line) + 1
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "CR":
            continue
        # "CR foo bar" → behåll bara "foo bar" (andra kolumnens innehåll)
        m_cr = re.match(r"^CR\s+(.*)$", stripped)
        if m_cr:
            rest = m_cr.group(1).strip()
            if rest:
                merged.append((line_offset, rest))
            continue
        merged.append((line_offset, stripped))

    # Nu extrahera transaktioner från varje rad. Strategi:
    # 1. Hitta alla datum-par (DD.MM.YY DD.MM.YY) på raden
    # 2. För varje par: description är text mellan slutet av paret och
    #    nästa datum-par (eller slut av rad), avslutat med ett belopp.
    # 3. Beloppet är det sista "\d,\d\d"-mönstret i beskrivningsområdet
    # 4. Om det finns "CR" innan nästa datum-par, markera som credit
    last_date: date | None = None
    for line_off, line in merged:
        date_pairs = list(_DATE_PAIR_RE.finditer(line))
        if not date_pairs:
            # Fallback: rad utan datum kan vara en fortsättning där
            # datumet hamnat på en närliggande Y. Om raden har formatet
            # "merchant  amount" försök ärva senaste datum.
            orphan_match = re.search(
                rf"^[\s.,]*([A-Za-zÅÄÖåäö][\w\s\-&/.åäöÅÄÖ]+?)\s+"
                rf"(?<![\d.,])(-?\d{{1,3}}(?:\.\d{{3}})*,\d{{2}})(?!\d)",
                line,
            )
            if orphan_match and last_date is not None:
                desc_raw = orphan_match.group(1).strip()
                amt_raw = orphan_match.group(2)
                desc_clean = desc_raw.rstrip(":,.- ").strip()
                if (
                    desc_clean
                    and not _contains_skip_word(desc_clean)
                    and len(desc_clean) > 2
                ):
                    amount_val = _parse_amount(amt_raw.lstrip("-"))
                    # Orphan-rader antas vara köp (positiva i källan)
                    if amt_raw.startswith("-"):
                        amount = amount_val
                    else:
                        amount = -amount_val
                    merchant, city = _split_merchant_city(desc_clean)
                    stmt.transactions.append(StatementLine(
                        date=last_date,
                        description=desc_clean,
                        merchant=merchant,
                        city=city,
                        amount=amount,
                        cardholder=_holder_at(line_off),
                    ))
            continue
        for i, dp in enumerate(date_pairs):
            # Område mellan slutet av datumpar och början av nästa par
            # (eller radslut)
            region_start = dp.end()
            region_end = date_pairs[i + 1].start() if i + 1 < len(date_pairs) else len(line)
            region = line[region_start:region_end]

            amount_matches = list(_STANDALONE_AMOUNT_RE.finditer(region))
            if not amount_matches:
                continue
            # Ta FÖRSTA belopp efter datumparet — det är "denna transaktion"s
            # belopp. Efterföljande belopp i samma region hör till andra
            # kolumnens transaktion (nästa datum-par) eller till summa.
            amt_m = amount_matches[0]
            amt_raw = amt_m.group(1)

            # Description = text före beloppet
            desc = region[:amt_m.start()].strip()
            # CR-markering: har vi "CR" mellan amount och region-slut?
            after_amt = region[amt_m.end():]
            is_credit = "CR" in after_amt

            # Minustecken omedelbart före beloppet (inbetalning från kortets
            # perspektiv). "Ikea - 30,00" är INTE inbetalning — där är "-"
            # separerat av mellanslag. Kräv att "-" står direkt före siffran.
            minus_before = (
                amt_m.start() > 0 and region[amt_m.start() - 1] == "-"
            )

            tx_date = _parse_date_amex(dp.group(1))
            if tx_date is None:
                continue
            last_date = tx_date

            desc_clean = desc.rstrip(":,.- ").strip()
            if _contains_skip_word(desc_clean):
                continue
            if not desc_clean:
                continue

            amount_val = _parse_amount(amt_raw)
            # Tecken: "- 30,00" (space mellan `-` och siffran) = "-" är
            # del av beskrivningen (t.ex. "Ikea Orebro 70231 Ikea - 30,00")
            # → vanligt köp → vårt värde = negativt.
            # "-30,00" (direkt adjacent) = verkligt negativt belopp i
            # källan = CR/inbetalning → vårt värde = positivt.
            # Skillnaden detekteras av `minus_before` som bara är True
            # om tecknet direkt före siffran är "-" (ingen mellanslag).
            if minus_before:
                amount = amount_val  # pengar in → positivt
            else:
                amount = -amount_val  # utgift → negativt

            merchant, city = _split_merchant_city(desc_clean)
            stmt.transactions.append(StatementLine(
                date=tx_date,
                description=desc_clean,
                merchant=merchant,
                city=city,
                amount=amount,
                cardholder=_holder_at(line_off + dp.start()),
            ))

    # Deduplicering — samma (date, desc, amount, cardholder) får förekomma
    # flera gånger (t.ex. 5 × Klm), men identiska matchningar som beror på
    # regex-overlap ska filtreras.
    seen = set()
    unique: list[StatementLine] = []
    for t in stmt.transactions:
        key = (t.date, t.description, t.amount, t.cardholder)
        # Tillåt dubletter — inom samma fakturadag kan man verkligen ha
        # 2 identiska köp. Men räkna position i listan för att skilja.
        unique.append(t)
    stmt.transactions = unique

    stmt.transactions.sort(key=lambda t: t.date)
    return stmt


_KNOWN_CITIES = {
    "stockholm", "göteborg", "malmö", "uppsala", "västerås", "örebro",
    "linköping", "helsingborg", "jönköping", "norrköping", "umeå",
    "gävle", "borås", "södertälje", "eskilstuna", "halmstad", "växjö",
    "karlstad", "sundsvall", "hjo", "skövde", "skoevde", "skovde",
    "luleå", "amsterdam", "hollyhill", "goteborg", "uddevalla",
    "alvsjo", "frederiksberg", "mollertorp", "molltorp",
    "san francisco",
}


def _split_merchant_city(desc: str) -> tuple[str, str | None]:
    """Försök plocka ut staden från slutet av beskrivningen."""
    stripped = desc.strip()
    parts = re.split(r"\s{3,}", stripped)
    if len(parts) >= 2:
        return parts[0].strip(), parts[-1].strip()
    tokens = stripped.rsplit(" ", 1)
    if len(tokens) == 2 and tokens[1].lower() in _KNOWN_CITIES:
        return tokens[0].strip(), tokens[1].strip()
    # Sista två ord (San Francisco)
    tokens2 = stripped.rsplit(" ", 2)
    if len(tokens2) == 3:
        two_word = f"{tokens2[1]} {tokens2[2]}".lower()
        if two_word in _KNOWN_CITIES:
            return tokens2[0].strip(), f"{tokens2[1]} {tokens2[2]}"
    return stripped, None
