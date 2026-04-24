"""Parser för Ekonomilabbets fyra PDF-typer.

Vi äger formatet — alla genererade PDF:er börjar med en magisk header:
  EKONOMILABBET KONTOUTDRAG
  EKONOMILABBET LÖNESPEC
  EKONOMILABBET LÅNEBESKED
  EKONOMILABBET KREDITKORT

Detta gör formatet robust att läsa tillbaka, oberoende av hur teckensnitt
eller layout justeras i framtiden.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

import pypdfium2 as pdfium

from .base import RawTransaction


PdfKind = Literal[
    "kontoutdrag", "lonespec", "lan_besked", "kreditkort_faktura",
]


@dataclass
class EkonomilabbetParseResult:
    kind: PdfKind
    title: str
    period: str | None = None  # YYYY-MM
    account_no: str | None = None
    bank_name: str | None = None
    transactions: list[RawTransaction] = field(default_factory=list)
    total_amount: Decimal | None = None
    meta: dict = field(default_factory=dict)


def detect_ekonomilabbet(pdf_bytes: bytes) -> PdfKind | None:
    text = _extract_text(pdf_bytes)
    if not text:
        return None
    head = text[:200].upper()
    if "EKONOMILABBET KONTOUTDRAG" in head:
        return "kontoutdrag"
    if "EKONOMILABBET LÖNESPEC" in head or "EKONOMILABBET LONESPEC" in head:
        return "lonespec"
    if "EKONOMILABBET LÅNEBESKED" in head or "EKONOMILABBET LANBESKED" in head:
        return "lan_besked"
    if "EKONOMILABBET KREDITKORT" in head:
        return "kreditkort_faktura"
    return None


def parse_ekonomilabbet(pdf_bytes: bytes) -> EkonomilabbetParseResult | None:
    kind = detect_ekonomilabbet(pdf_bytes)
    if kind is None:
        return None
    text = _extract_text(pdf_bytes)
    if kind == "kontoutdrag":
        return _parse_kontoutdrag(text)
    if kind == "lonespec":
        return _parse_lonespec(text)
    if kind == "lan_besked":
        return _parse_lanbesked(text)
    if kind == "kreditkort_faktura":
        return _parse_kreditkort(text)
    return None


# ---------- Internals ----------

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
# Kräv ordgräns/start-of-string + tecken/siffra för att undvika att
# regexen plockar upp svans av ett tidigare ord (t.ex. "18/04250,00 kr"
# ska INTE matcha "4250,00").
_AMOUNT_RE = re.compile(r"(?:^|[\s\(])(-?\d{1,3}(?:[ \xa0]\d{3})*,\d{2})\s*kr")
_PERIOD_RE = re.compile(r"(\d{4}-\d{2})")
_ACCOUNT_RE = re.compile(r"Konto:\s*([^\n]+)")
_CARD_RE = re.compile(r"Kortnummer:\s*([^\n]+)")
_BANK_RE = re.compile(r"Bank:\s*([^\n]+)")


def _extract_text(pdf_bytes: bytes) -> str:
    """Extrahera all text från en PDF via pypdfium2."""
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        out: list[str] = []
        for i in range(len(pdf)):
            page = pdf[i]
            tp = page.get_textpage()
            out.append(tp.get_text_range())
            tp.close()
            page.close()
        pdf.close()
        return "\n".join(out)
    except Exception:
        return ""


def _parse_amount(s: str) -> Decimal:
    """'-1 234,56 kr' → Decimal('-1234.56')."""
    m = _AMOUNT_RE.search(s)
    if not m:
        return Decimal(0)
    raw = m.group(1).replace(" ", "").replace(",", ".")
    return Decimal(raw)


def _parse_kontoutdrag(text: str) -> EkonomilabbetParseResult:
    res = EkonomilabbetParseResult(kind="kontoutdrag", title="Kontoutdrag")

    if m := _BANK_RE.search(text):
        res.bank_name = m.group(1).strip()
    if m := _ACCOUNT_RE.search(text):
        res.account_no = m.group(1).strip()
    if m := _PERIOD_RE.search(text.split("Period:", 1)[-1] if "Period:" in text else text):
        res.period = m.group(1)

    # Tabell-rader: "YYYY-MM-DD <text> <belopp> kr <saldo> kr"
    # Vi parsear rad för rad efter "Datum"-rubriken
    lines = text.splitlines()
    in_table = False
    row_idx = 0
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("Datum") and "Belopp" in s:
            in_table = True
            continue
        if not in_table:
            continue
        m_date = _DATE_RE.search(s)
        if not m_date:
            continue
        # Hitta båda beloppen (belopp + saldo)
        amounts = list(_AMOUNT_RE.finditer(s))
        if len(amounts) < 2:
            continue
        d = date.fromisoformat(m_date.group(1))
        # Plocka ut text mellan datum och första beloppet
        date_end = m_date.end()
        amount_start = amounts[-2].start()
        desc = s[date_end:amount_start].strip()
        amount_str = amounts[-2].group(1).replace(" ", "").replace(",", ".")
        balance_str = amounts[-1].group(1).replace(" ", "").replace(",", ".")
        amount = Decimal(amount_str)
        balance = Decimal(balance_str)
        row_idx += 1
        res.transactions.append(RawTransaction(
            date=d, amount=amount, description=desc,
            balance=balance, row_index=row_idx,
        ))

    return res


def _parse_lonespec(text: str) -> EkonomilabbetParseResult:
    res = EkonomilabbetParseResult(kind="lonespec", title="Lönespec")
    if m := _PERIOD_RE.search(text):
        res.period = m.group(1)

    # Hitta nettolön
    for ln in text.splitlines():
        if "NETTOLÖN" in ln.upper():
            res.total_amount = _parse_amount(ln)
            break

    # Pay date
    if m := re.search(r"Utbetalningsdag:\s*(\d{4}-\d{2}-\d{2})", text):
        d = date.fromisoformat(m.group(1))
        if res.total_amount is not None:
            employer_match = re.search(r"Arbetsgivare:\s*([^\n]+)", text)
            employer = employer_match.group(1).strip() if employer_match else "OKÄND"
            res.transactions.append(RawTransaction(
                date=d,
                amount=res.total_amount,
                description=f"LÖN {employer.upper()}",
                row_index=1,
            ))

    if employer_match := re.search(r"Arbetsgivare:\s*([^\n]+)", text):
        res.meta["employer"] = employer_match.group(1).strip()
    if gross_match := re.search(r"Bruttolön\s+([\d ]+,\d{2})\s*kr", text):
        res.meta["gross"] = gross_match.group(1)

    return res


def _parse_lanbesked(text: str) -> EkonomilabbetParseResult:
    res = EkonomilabbetParseResult(kind="lan_besked", title="Lånebesked")
    if m := _PERIOD_RE.search(text):
        res.period = m.group(1)

    # Plocka ut räntekostnad, amortering, totalt
    for ln in text.splitlines():
        if "Räntekostnad denna månad" in ln:
            res.meta["interest"] = float(_parse_amount(ln))
        elif "Amortering denna månad" in ln:
            res.meta["amortization"] = float(_parse_amount(ln))
        elif "TOTALT ATT BETALA" in ln.upper():
            res.total_amount = _parse_amount(ln)
        elif "Återstående lån" in ln:
            res.meta["remaining"] = float(_parse_amount(ln))
        elif ln.strip().startswith("Långivare:"):
            res.meta["lender"] = ln.split(":", 1)[1].strip()
        elif ln.strip().startswith("Aktuell ränta"):
            rm = re.search(r"(\d+[.,]\d+)\s*%", ln)
            if rm:
                res.meta["rate_pct"] = float(rm.group(1).replace(",", "."))

    if m := re.search(r"Förfallodag:\s*(\d{4}-\d{2}-\d{2})", text):
        due = date.fromisoformat(m.group(1))
        if res.total_amount:
            lender = res.meta.get("lender", "BANK").upper()
            res.transactions.append(RawTransaction(
                date=due,
                amount=-res.total_amount,
                description=f"{lender} BOLÅN AUTOGIRO",
                row_index=1,
            ))
    return res


def _parse_kreditkort(text: str) -> EkonomilabbetParseResult:
    res = EkonomilabbetParseResult(kind="kreditkort_faktura", title="Kreditkort")
    if m := _PERIOD_RE.search(text):
        res.period = m.group(1)
    if m := _CARD_RE.search(text):
        res.account_no = m.group(1).strip()

    lines = text.splitlines()
    in_table = False
    row_idx = 0
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("Datum") and "Köp" in s:
            in_table = True
            continue
        if not in_table:
            continue
        if s.startswith("Att betala"):
            res.total_amount = _parse_amount(s)
            in_table = False
            continue
        m_date = _DATE_RE.search(s)
        if not m_date:
            continue
        amounts = list(_AMOUNT_RE.finditer(s))
        if not amounts:
            continue
        d = date.fromisoformat(m_date.group(1))
        date_end = m_date.end()
        amount_start = amounts[-1].start()
        desc = s[date_end:amount_start].strip()
        amount = Decimal(amounts[-1].group(1).replace(" ", "").replace(",", "."))
        row_idx += 1
        # Köp på kort lagras som NEGATIVA tx på kortets konto (= utgift)
        res.transactions.append(RawTransaction(
            date=d, amount=-amount, description=desc, row_index=row_idx,
        ))
    return res
