"""Heuristisk parser för text-klistrade kontoutdrag.

Banker visar transaktioner i många olika format på sina hemsidor — det
finns ingen standard. När användaren markerar + kopierar texten direkt
från webbsidan blir det tab-separerat, mellanslag-separerat, eller
multi-line beroende på bank.

Den här parsern är medvetet TOLERANT: hittar datum + belopp på varje
rad och tar resten som beskrivning. Skipper rader som inte har båda.
Användaren får sedan en preview innan import så fel kan ångras.

Stöder svenska bank-format:
- Nordea Internetbank: 'YYYY-MM-DD\\tBeskrivning\\t-1 234,56'
- Swedbank: 'YYYY-MM-DD  Beskrivning  +1 234,56 SEK'
- SEB: 'DD.MM.YYYY Beskrivning -1 234,56'
- Kortköp via banken: 'DD/MM Beskrivning belopp saldo'

Returnerar list[ParsedRow] som backend sen kan dedupera + spara.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as _date
from decimal import Decimal, InvalidOperation
from typing import Optional


@dataclass
class ParsedRow:
    date: _date
    amount: Decimal
    description: str
    raw_line: str


# YYYY-MM-DD eller YYYY/MM/DD eller YYYY.MM.DD
_DATE_ISO = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
# DD-MM-YYYY eller DD/MM/YYYY eller DD.MM.YYYY (svenskt format)
_DATE_DMY = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b")
# DD/MM eller DD-MM (utan år, antas vara aktuellt år)
_DATE_DM = re.compile(r"\b(\d{1,2})[-/](\d{1,2})\b")

# Svenska belopp: "1 234,56" eller "1234,56" eller "−1 234,56" eller
# "+1234.56" eller "1234". Plus/minus/svensk minus-tecken (−). Tillåter
# valfritt SEK eller kr efter beloppet.
_AMOUNT = re.compile(
    r"(?P<sign>[-−+])?\s*"
    r"(?P<num>\d{1,3}(?:[  ]\d{3})*(?:[,.]\d{1,2})?|\d+(?:[,.]\d{1,2})?)"
    r"\s*(?:SEK|kr|KR)?\s*$"
)


def _parse_amount(s: str) -> Optional[Decimal]:
    """Tolka svenskt belopp '1 234,56' eller engelskt '1234.56'."""
    s = s.strip().replace(" ", " ").replace("−", "-")
    # Hitta sign + nummer
    m = _AMOUNT.search(s)
    if not m:
        return None
    sign = m.group("sign") or "+"
    num = m.group("num").replace(" ", "")
    # Svensk decimal: komma → punkt. Om komma finns, tusentalsavskiljare
    # är punkt; annars är punkt decimaltecken.
    if "," in num:
        num = num.replace(".", "").replace(",", ".")
    try:
        d = Decimal(num)
    except InvalidOperation:
        return None
    if sign == "-":
        d = -d
    return d


def _parse_date(s: str, default_year: int) -> Optional[_date]:
    """Tolka datum från valfri position i strängen."""
    m = _DATE_ISO.search(s)
    if m:
        try:
            return _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _DATE_DMY.search(s)
    if m:
        try:
            return _date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = _DATE_DM.search(s)
    if m:
        try:
            return _date(default_year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _strip_date_amount(line: str, dt: _date, amt: Decimal) -> str:
    """Ta bort datum + belopp från raden så bara beskrivningen blir kvar."""
    out = line
    # Ta bort alla datum-matchningar
    for pat in (_DATE_ISO, _DATE_DMY, _DATE_DM):
        out = pat.sub(" ", out)
    # Ta bort sista belopp-matchningen (kan finnas flera om saldo också
    # står med — vi tar det som ligger sist på raden, vilket _AMOUNT med
    # $-anchor gör)
    out = _AMOUNT.sub("", out)
    # Komprimera whitespace + ta bort tab/dubbla mellanslag
    out = re.sub(r"\s+", " ", out).strip()
    # Trimma gemensamma "skräp"-tecken som vissa banker har
    out = out.strip(" \t-—:|")
    return out


def parse_pasted(text: str, default_year: Optional[int] = None) -> list[ParsedRow]:
    """Tolka klistrad bank-text rad för rad.

    `default_year` används för datum utan år (t.ex. "DD/MM"). Om None,
    används aktuellt år.
    """
    if default_year is None:
        default_year = _date.today().year
    rows: list[ParsedRow] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Hoppa över uppenbara header/footer-rader
        low = line.lower()
        if any(skip in low for skip in (
            "ingående saldo", "utgående saldo", "summa",
            "kontoutdrag", "konto:", "period:", "datum belopp",
            "datum referens", "datum beskrivning",
        )):
            continue
        dt = _parse_date(line, default_year)
        if dt is None:
            continue
        amt = _parse_amount(line)
        if amt is None or amt == 0:
            continue
        desc = _strip_date_amount(line, dt, amt)
        if not desc:
            continue
        rows.append(ParsedRow(date=dt, amount=amt, description=desc, raw_line=raw_line))
    return rows
