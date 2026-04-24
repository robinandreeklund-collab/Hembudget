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
    (inte OCR) — PDFer från banker är alltid text-baserade.

    OBS: Enkel radvis extraktion, läsordning. Fungerar bra för rubrik/
    header-fält men misslyckas för tabulära layouter där belopp är i egen
    textkolumn. För dem, använd extract_pdf_text_layout().
    """
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


def extract_pdf_fragments(
    pdf_bytes: bytes,
) -> list[list[tuple[float, float, float, str]]]:
    """Returnera per-sida lista av text-fragment med positionsinformation.

    Varje fragment = (x_left, y_center, page_height, text). Används av
    kolumn-medvetna parsers (Amex och SEB Kort) som behöver veta vilken
    kolumn texten kom från.
    """
    import ctypes
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c

    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        pages_fragments: list[list[tuple[float, float, float, str]]] = []
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                page_height = page.get_height()
                tp = page.get_textpage()
                try:
                    rect_count = pdfium_c.FPDFText_CountRects(tp.raw, 0, -1)
                    fragments: list[tuple[float, float, float, str]] = []
                    for rect_idx in range(rect_count):
                        left = ctypes.c_double()
                        top = ctypes.c_double()
                        right = ctypes.c_double()
                        bottom = ctypes.c_double()
                        if not pdfium_c.FPDFText_GetRect(
                            tp.raw, rect_idx,
                            ctypes.byref(left), ctypes.byref(top),
                            ctypes.byref(right), ctypes.byref(bottom),
                        ):
                            continue
                        try:
                            frag = tp.get_text_bounded(
                                left.value, bottom.value,
                                right.value, top.value,
                            )
                        except Exception:
                            frag = ""
                        frag = frag.replace("\r", "").replace("\n", " ").strip()
                        if not frag:
                            continue
                        y_center = (top.value + bottom.value) / 2.0
                        fragments.append(
                            (left.value, y_center, page_height, frag)
                        )
                    pages_fragments.append(fragments)
                finally:
                    tp.close()
            finally:
                page.close()
        return pages_fragments
    finally:
        pdf.close()


def extract_pdf_text_layout(
    pdf_bytes: bytes, y_tolerance: float = 5.0
) -> str:
    """Layout-medveten extraktion — grupperar text-fragment per Y-
    koordinat så tabulära layouter (där belopp ligger i höger kolumn)
    bevaras som "description ... amount" på samma rad i utdata.

    Post-processar för att:
    - Städa upp datum med mellanslag ("30 . 01 . 26" → "30.01.26")
    - Slå ihop "punkt-rader" (rader med bara '.  .  .  .') med
      föregående rad — händer när datumpunkter renderas på lite annan
      Y än siffrorna.
    """
    import re
    pages_fragments = extract_pdf_fragments(pdf_bytes)
    all_rows: list[str] = []
    for fragments in pages_fragments:
        if not fragments:
            continue
        fragments_sorted = sorted(fragments, key=lambda t: (-t[1], t[0]))
        rows: list[list[tuple[float, str]]] = []
        current_y: float | None = None
        current_row: list[tuple[float, str]] = []
        for x, y, _ph, frag in fragments_sorted:
            if current_y is None or abs(y - current_y) > y_tolerance:
                if current_row:
                    rows.append(current_row)
                current_row = []
                current_y = y
            current_row.append((x, frag))
        if current_row:
            rows.append(current_row)

        merged_rows: list[str] = []
        for row in rows:
            row.sort(key=lambda t: t[0])
            s = "  ".join(frag for _, frag in row)
            merged_rows.append(s)

        # Pre-pass: slå ihop rader vars innehåll är bara punkter/mellanslag
        # med föregående rad. Reconstruct digits-separated-by-dots.
        dots_only = re.compile(r"^[\s\.,]+$")
        cleaned: list[str] = []
        for s in merged_rows:
            if dots_only.match(s) and cleaned:
                # Innehåller bara punkter/kommatecken → merge med prev
                cleaned[-1] = cleaned[-1] + " " + s
            else:
                cleaned.append(s)

        # Städa upp tal i varje rad
        for s in cleaned:
            # "30  01  26  .  .  ." → först ta bort alla mellanslag kring
            # punkter/kommatecken mellan siffror
            prev = None
            while prev != s:
                prev = s
                s = re.sub(r"(\d)\s+([.,])\s+(\d)", r"\1\2\3", s)
                s = re.sub(r"(\d)\s+([.,])\s+", r"\1\2", s)
                s = re.sub(r"\s+([.,])\s+(\d)", r"\1\2", s)
            # OBS: Vi joinar INTE "- 30" → "-30" eftersom `-` kan vara
            # en del av merchant-beskrivningen ("Ikea Orebro - 30,00").
            # Amounts som verkligen är negativa har sin "-" direkt adjacent
            # i källan eller indikeras av CR-markör på samma rad.
            # Städa bort kvarlämnade trailing "." "." "." sekvenser
            s = re.sub(r"\s{2,}\.(?:\s+\.)+(?=\s|$)", "", s)
            all_rows.append(s)
    return "\n".join(all_rows)
