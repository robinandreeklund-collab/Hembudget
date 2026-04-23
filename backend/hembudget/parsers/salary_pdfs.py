"""Heuristisk parser för svenska lönespec-PDF:er.

Stöder tre huvudformat i testdatat:
1. **INKAB** (Ingenjörsfirma Nybergs Konstruktion) — "INKAB" i header,
   löneart-tabell, Bruttolön/Skatt/Utbetalas i sidofält
2. **Vättaporten AB (VP)** — "Vättaporten AB" i header, har "Extra skatt"
   som egen rad = extra utdragen skatt per månad (skatteprognos)
3. **Försäkringskassan** — "Försäkringskassan" / FK i text, två varianter:
   3a. Barnbidrag — "Barnbidrag" + belopp direkt
   3b. Föräldrapenning — tabell med bruttobelopp, preliminär skatt, netto

För varje PDF extraheras:
- Arbetsgivare/utbetalare, mottagare
- Löneperiod (from-to)
- Utbetalningsdatum
- Brutto, skatt, förmån, netto
- Extra skatt (VP) för skatteprognos
- Semesterdagar (betalda/obetalda/sparade) där det finns
- Skattetabell och engångsskatt%

Används av /salaries/parse-pdf-endpointen för att automatiskt skapa
UpcomingTransaction-rader med fullständig metadata + kopplad källfil.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

import pypdfium2 as pdfium


@dataclass
class SalaryPdfResult:
    # Formatet vi känner igen — påverkar vilka fält vi förväntar oss
    detected_format: str = "unknown"  # inkab | vp | fk_barnbidrag | fk_foraldrapenning | unknown

    # Identitet
    employer: Optional[str] = None
    employee: Optional[str] = None

    # Datum
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    paid_out_date: Optional[date] = None

    # Belopp
    gross: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    extra_tax: Optional[Decimal] = None  # "Extra skatt"-raden på VP
    benefit: Optional[Decimal] = None     # "Förmån"
    net: Optional[Decimal] = None         # Utbetalas

    # Skatte-metadata
    tax_table: Optional[str] = None       # t.ex. "33", "34"
    one_time_tax_percent: Optional[float] = None  # engångsskatt %

    # Semester
    vacation_days_paid: Optional[int] = None
    vacation_days_unpaid: Optional[int] = None
    vacation_days_saved: Optional[int] = None

    # Rå text för debug + fallback i frontend
    raw_text: str = ""
    parse_errors: list[str] = field(default_factory=list)


def _to_decimal(s: str) -> Optional[Decimal]:
    """Tolka svenskt belopp '1 234,56' / '1234,56' / '-100,00'."""
    s = s.strip().replace(" ", " ").replace(" ", "")
    if not s:
        return None
    # Svensk decimal → punkt
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _to_int(s: str) -> Optional[int]:
    s = s.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _to_date(s: str) -> Optional[date]:
    """Tolka YYYY-MM-DD. Ex: '2026-01-23'."""
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s.strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def extract_text(pdf_bytes: bytes) -> str:
    """Extrahera all text från en PDF (alla sidor, blankrad mellan)."""
    pdf = pdfium.PdfDocument(pdf_bytes)
    parts = []
    for page in pdf:
        t = page.get_textpage().get_text_range()
        parts.append(t)
    return "\n".join(parts)


def detect_format(text: str) -> str:
    lower = text.lower()
    if "inkab" in lower or "nybergs konstruktion" in lower:
        return "inkab"
    if "vättaporten" in lower or "vattaporten" in lower:
        return "vp"
    if "försäkringskassan" in lower or "forsakringskassan" in lower or "kundcenter" in lower:
        if "barnbidrag" in lower:
            return "fk_barnbidrag"
        return "fk_foraldrapenning"
    return "unknown"


def _parse_inkab(text: str, res: SalaryPdfResult) -> None:
    """INKAB-layout: sidofält med Bruttolön/Skatt/Utbetalas."""
    res.employer = "INKAB"
    # Namn: "Anställningsnummer 003 Robin André" eller annan layout
    m = re.search(r"Anställningsnummer\s+\S+\s+([A-ZÅÄÖ][\wåäöÅÄÖ\- ]+?)(?=\n|Klarabergs|$)", text)
    if m:
        res.employee = m.group(1).strip()
    # Löneperiod
    m = re.search(r"Löneperiod\s+(\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})", text)
    if m:
        res.period_start = _to_date(m.group(1))
        res.period_end = _to_date(m.group(2))
    # Utbetalas — "Utbetalas 2026-01-23 6 197,00"
    m = re.search(r"Utbetalas\s+(\d{4}-\d{2}-\d{2})\s+([\d\s,.]+)", text)
    if m:
        res.paid_out_date = _to_date(m.group(1))
        res.net = _to_decimal(m.group(2))
    # "Totalt i år Bruttolön 6 764,60" / "Bruttolön 6 764,60" i "Utbetalning"-blocket
    # VI hittar specifikt Utbetalning-blockets värden:
    m = re.search(
        r"Utbetalning\s*\nBruttolön\s+([\d\s,.]+)\s*\nSkatt\s+([\d\s,.]+)",
        text,
    )
    if m:
        res.gross = _to_decimal(m.group(1))
        res.tax = _to_decimal(m.group(2))
    else:
        # Fallback: första Bruttolön + Skatt-raderna
        m = re.search(r"Bruttolön\s+([\d\s,.]+)", text)
        if m:
            res.gross = _to_decimal(m.group(1))
        m = re.search(r"Skatt\s+([\d\s,.]+)", text)
        if m:
            res.tax = _to_decimal(m.group(1))
    # Tabell
    m = re.search(r"Tabell\s+([\d,.]+)", text)
    if m:
        res.tax_table = m.group(1).replace(",00", "").strip()
    # Engångsskatt
    m = re.search(r"Engångsskatt\s*%?\s+([\d,.]+)", text)
    if m:
        try:
            res.one_time_tax_percent = float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    # Semesterdagar
    m = re.search(r"Semesterdagar\s*\n\s*Betalda\s+(\d+)\s*\n\s*Obetalda\s+(\d+)\s*\n\s*Sparade\s+(\d+)", text)
    if m:
        res.vacation_days_paid = _to_int(m.group(1))
        res.vacation_days_unpaid = _to_int(m.group(2))
        res.vacation_days_saved = _to_int(m.group(3))


def _parse_vp(text: str, res: SalaryPdfResult) -> None:
    """Vättaporten AB-layout: har Extra skatt-rad."""
    res.employer = "Vättaporten AB"
    m = re.search(r"Namn:\s*([^\n]+)", text)
    if m:
        res.employee = m.group(1).strip()
    m = re.search(r"Löneperiod:\s*(\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})", text)
    if m:
        res.period_start = _to_date(m.group(1))
        res.period_end = _to_date(m.group(2))
    # UTBETALAS 2026-01-23 23 072,00 kr
    m = re.search(r"UTBETALAS\s+(\d{4}-\d{2}-\d{2})\s+([\d\s,.]+?)\s*kr", text)
    if m:
        res.paid_out_date = _to_date(m.group(1))
        res.net = _to_decimal(m.group(2))
    # Period-block: Bruttolön + Förmån + Skatt
    m = re.search(
        r"Perioden\s*\nBruttolön\s+([\d\s,.]+)",
        text,
    )
    if m:
        res.gross = _to_decimal(m.group(1))
    else:
        m = re.search(r"Månadslön\s+\d{6}\s*-\s*\d{6}\s+([\d\s,.]+)", text)
        if m:
            res.gross = _to_decimal(m.group(1))
    # Förmån, totala raden på "Perioden"
    m = re.search(r"Perioden[\s\S]*?Förmån\s+([\d\s,.]+)", text)
    if m:
        res.benefit = _to_decimal(m.group(1))
    # Totala skatten i "Perioden"-blocket
    m = re.search(r"Perioden[\s\S]*?Skatt\s+([\d\s,.]+)", text)
    if m:
        res.tax = _to_decimal(m.group(1))
    # EXTRA SKATT (egen rad i löneart-tabellen)
    m = re.search(r"Extra\s+skatt\s+([\d\s,.]+)", text, re.IGNORECASE)
    if m:
        res.extra_tax = _to_decimal(m.group(1))
    # Tabell + engångsskatt
    m = re.search(r"Tabell\s+([\d]+)", text)
    if m:
        res.tax_table = m.group(1)
    m = re.search(r"Engångsskatt\s*%?\s+([\d,.]+)", text)
    if m:
        try:
            res.one_time_tax_percent = float(m.group(1).replace(",", "."))
        except ValueError:
            pass


def _parse_fk_barnbidrag(text: str, res: SalaryPdfResult) -> None:
    """Försäkringskassan barnbidrag: enkel utbetalning utan skatt."""
    res.employer = "Försäkringskassan"
    m = re.search(r"Utbetalningsdatum:\s*(\d{4}-\d{2}-\d{2})", text)
    if m:
        res.paid_out_date = _to_date(m.group(1))
    m = re.search(r"Belopp:\s*([\d\s,.]+?)\s*kr", text)
    if m:
        res.net = _to_decimal(m.group(1))
        # Barnbidrag är skattefritt
        res.gross = res.net
        res.tax = Decimal("0")


def _parse_fk_foraldrapenning(text: str, res: SalaryPdfResult) -> None:
    """Försäkringskassan föräldrapenning: tabell med brutto/skatt/netto."""
    res.employer = "Försäkringskassan"
    # Utbetalningsraden har format:
    #   "2026-03-25 1 719 2 490 -771"
    # Där första tal = netto, andra = brutto, tredje = negativ skatt.
    # Vi hittar raden via "YYYY-MM-DD" följt av minst 3 tal.
    m = re.search(
        r"(\d{4}-\d{2}-\d{2})\s+"
        r"(\d{1,3}(?:\s\d{3})*)\s+"
        r"(\d{1,3}(?:\s\d{3})*)\s+"
        r"(-\d{1,3}(?:\s\d{3})*)",
        text,
    )
    if m:
        res.paid_out_date = _to_date(m.group(1))
        res.net = _to_decimal(m.group(2))
        res.gross = _to_decimal(m.group(3))
        tax_val = _to_decimal(m.group(4))
        res.tax = abs(tax_val) if tax_val is not None else None
    if not res.paid_out_date:
        # Fallback: sista datumet som inte är "Fastställd YYYY-MM-DD"
        dates = re.findall(r"(\d{4}-\d{2}-\d{2})", text)
        if dates:
            # Hoppa över datum som följs av "Fastställd"
            for d in reversed(dates):
                if f"Fastställd {d}" not in text:
                    res.paid_out_date = _to_date(d)
                    break


def parse_salary_pdf(pdf_bytes: bytes) -> SalaryPdfResult:
    """Parse en svensk lönespec-PDF → strukturerad data.

    Detekterar format automatiskt baserat på header-text. Returnerar
    SalaryPdfResult med detected_format='unknown' om ingen regel matchar.
    """
    res = SalaryPdfResult()
    try:
        text = extract_text(pdf_bytes)
    except Exception as exc:
        res.parse_errors.append(f"PDF-läsning misslyckades: {exc}")
        return res
    res.raw_text = text
    res.detected_format = detect_format(text)

    if res.detected_format == "inkab":
        _parse_inkab(text, res)
    elif res.detected_format == "vp":
        _parse_vp(text, res)
    elif res.detected_format == "fk_barnbidrag":
        _parse_fk_barnbidrag(text, res)
    elif res.detected_format == "fk_foraldrapenning":
        _parse_fk_foraldrapenning(text, res)
    else:
        res.parse_errors.append(
            "Okänt format — varken INKAB, Vättaporten eller FK kändes igen."
        )
    return res
