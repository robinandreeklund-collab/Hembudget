"""Heuristisk parser för svenska energi- och bredbandsfakturor.

Stöd:
- **Hjo Energi** / kommunalt energibolag — el + vattenavgift + renhållning,
  ofta en gemensam faktura med olika poster
- **Telinet** — bredband + mobil, fast månadsavgift ofta
- **Tibber** — PDF-faktura backup (men Tibber API föredras)
- **Vattenfall / E.ON / Fortum** — el, tabell med förbrukning + pris

Extraherar:
- Period (from, to)
- Förbrukning (kWh för el, GB för bredband, m³ för vatten)
- Totalbelopp
- Mätare-typ (el / bredband / vatten / fjärrvärme)

Parsern är medvetet tolerant — olika bolag har olika layouter men
de flesta har samma nyckelord ("Förbrukning", "kWh", "Period", "Belopp").
Om ett fält saknas returnerar vi None och låter användaren komplettera
i UI:t.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

import pypdfium2 as pdfium


@dataclass
class UtilityPdfResult:
    supplier: str = "unknown"  # hjo_energi | telinet | vattenfall | ...
    meter_type: str = "electricity"  # electricity | broadband | water | heating

    period_start: Optional[date] = None
    period_end: Optional[date] = None

    consumption: Optional[Decimal] = None  # kWh / GB / m³
    consumption_unit: Optional[str] = None  # "kWh", "GB", "m3"

    cost_kr: Optional[Decimal] = None  # totalbelopp inkl. moms

    raw_text: str = ""
    parse_errors: list[str] = field(default_factory=list)


def _to_decimal(s: str) -> Optional[Decimal]:
    s = s.strip().replace(" ", " ").replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _to_date(s: str) -> Optional[date]:
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s.strip())
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    # YYYY-MM (månad utan dag → första dagen)
    m = re.match(r"(\d{4})-(\d{1,2})$", s.strip())
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            return None
    return None


def extract_text(pdf_bytes: bytes) -> str:
    pdf = pdfium.PdfDocument(pdf_bytes)
    return "\n".join(
        p.get_textpage().get_text_range() for p in pdf
    )


def detect_supplier_and_type(text: str) -> tuple[str, str]:
    """Returnera (supplier, meter_type) baserat på textinnehåll."""
    lower = text.lower()
    if "hjo energi" in lower:
        if "bredband" in lower or "internet" in lower:
            return ("hjo_energi", "broadband")
        return ("hjo_energi", "electricity")
    if "telinet" in lower:
        if "bredband" in lower or "fiber" in lower:
            return ("telinet", "broadband")
        return ("telinet", "broadband")  # Telinet är främst bredband
    if "tibber" in lower:
        return ("tibber", "electricity")
    if "vattenfall" in lower:
        if "vatten och avlopp" in lower or "va-avgift" in lower:
            return ("vattenfall", "water")
        return ("vattenfall", "electricity")
    if "fortum" in lower:
        return ("fortum", "electricity")
    if "e.on" in lower or "eon " in lower:
        return ("eon", "electricity")
    if "fjärrvärme" in lower:
        return ("fjärrvärme", "heating")
    if "hjo kommun" in lower and ("vatten" in lower or "avlopp" in lower):
        return ("hjo_kommun", "water")
    return ("unknown", "electricity")


def _extract_period(text: str) -> tuple[Optional[date], Optional[date]]:
    """Leta efter fakturaperiod i text."""
    # Format 1: "Period: 2026-01-01 - 2026-01-31"
    m = re.search(
        r"[Pp]eriod[:\s]*(\d{4}-\d{1,2}-\d{1,2})\s*[-–—]\s*(\d{4}-\d{1,2}-\d{1,2})",
        text,
    )
    if m:
        return _to_date(m.group(1)), _to_date(m.group(2))
    # Format 2: "Förbrukningsperiod 2026-01-01 till 2026-01-31"
    m = re.search(
        r"[Ff]örbrukningsperiod[:\s]*(\d{4}-\d{1,2}-\d{1,2})\s*(?:till|[-–—])\s*(\d{4}-\d{1,2}-\d{1,2})",
        text,
    )
    if m:
        return _to_date(m.group(1)), _to_date(m.group(2))
    # Format 3: "2026-01-01 – 2026-01-31" på egen rad
    m = re.search(
        r"\b(\d{4}-\d{1,2}-\d{1,2})\s*[-–—]\s*(\d{4}-\d{1,2}-\d{1,2})\b",
        text,
    )
    if m:
        return _to_date(m.group(1)), _to_date(m.group(2))
    # Format 4: "Januari 2026" → första-sista i månaden
    m = re.search(
        r"\b(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)\s+(\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if m:
        months = {
            "januari": 1, "februari": 2, "mars": 3, "april": 4,
            "maj": 5, "juni": 6, "juli": 7, "augusti": 8,
            "september": 9, "oktober": 10, "november": 11, "december": 12,
        }
        mon = months[m.group(1).lower()]
        year = int(m.group(2))
        from calendar import monthrange
        last_day = monthrange(year, mon)[1]
        return date(year, mon, 1), date(year, mon, last_day)
    return None, None


def _extract_kwh(text: str) -> Optional[Decimal]:
    """Leta efter 'XXXX kWh'-mönster. Välj största värdet om flera."""
    matches = re.findall(
        r"(\d{1,3}(?:[ \.]\d{3})*(?:[,\.]\d+)?)\s*kWh",
        text,
    )
    if not matches:
        return None
    # Oftast flera kWh-tal (period, ackumulerat, per månad…) — ta det
    # största som typiskt är periodens totala förbrukning
    vals = [_to_decimal(m) for m in matches]
    vals = [v for v in vals if v is not None and v > 0]
    if not vals:
        return None
    return max(vals)


def _extract_gb(text: str) -> Optional[Decimal]:
    """Telinet/Bredband: leta efter GB-förbrukning."""
    matches = re.findall(
        r"(\d{1,3}(?:[,\.]\d+)?)\s*GB",
        text,
    )
    if not matches:
        return None
    vals = [_to_decimal(m) for m in matches]
    vals = [v for v in vals if v is not None and v > 0]
    if not vals:
        return None
    return max(vals)


def _extract_total_cost(text: str) -> Optional[Decimal]:
    """Leta efter totalbelopp att betala."""
    # "Att betala: X XXX,XX kr"
    patterns = [
        r"[Aa]tt\s+betala[:\s]*([\d\s,.]+)\s*kr",
        r"[Tt]otalt?\s+(?:belopp|summa)?[:\s]*([\d\s,.]+)\s*kr",
        r"[Ss]umma\s+att\s+betala[:\s]*([\d\s,.]+)\s*kr",
        r"[Ss]lutsumma[:\s]*([\d\s,.]+)\s*kr",
        r"[Bb]elopp[:\s]*([\d\s,.]+)\s*SEK",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val = _to_decimal(m.group(1))
            if val and val > 0:
                return val
    return None


def parse_utility_pdf(pdf_bytes: bytes) -> UtilityPdfResult:
    """Parse en energifaktura → strukturerad data.

    Tolerant mot olika layouter. Om något fält inte hittas returneras
    det som None och användaren kan fylla i manuellt i UI:t.
    """
    res = UtilityPdfResult()
    try:
        text = extract_text(pdf_bytes)
    except Exception as exc:
        res.parse_errors.append(f"PDF-läsning misslyckades: {exc}")
        return res
    res.raw_text = text

    res.supplier, res.meter_type = detect_supplier_and_type(text)
    res.period_start, res.period_end = _extract_period(text)
    res.cost_kr = _extract_total_cost(text)

    if res.meter_type == "electricity" or res.meter_type == "heating":
        res.consumption = _extract_kwh(text)
        res.consumption_unit = "kWh" if res.consumption else None
    elif res.meter_type == "broadband":
        # Bredband har ofta fast avgift — förbrukning är GB (om mätbar)
        res.consumption = _extract_gb(text)
        res.consumption_unit = "GB" if res.consumption else None
    elif res.meter_type == "water":
        # Vatten i m³
        m = re.search(
            r"(\d{1,3}(?:[,\.]\d+)?)\s*m[³3]",
            text,
        )
        if m:
            res.consumption = _to_decimal(m.group(1))
            res.consumption_unit = "m³"

    # Sanity check — om vi inte hittat varken period eller kostnad är
    # det troligen fel format
    if res.period_start is None and res.cost_kr is None:
        res.parse_errors.append(
            "Varken period eller totalbelopp hittat — troligen ej en faktura."
        )

    return res
