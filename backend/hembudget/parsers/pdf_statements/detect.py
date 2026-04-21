"""Autodetect: vilken kortutgivare är detta PDF-kontoutdrag?"""
from __future__ import annotations

from . import ParsedStatement, extract_pdf_text
from .amex import looks_like_amex, parse_amex
from .seb_kort import looks_like_seb_kort, parse_seb_kort


def parse_statement(pdf_bytes: bytes) -> ParsedStatement:
    """Läs en kreditkorts-PDF och returnera strukturerad data.

    Kastar ValueError om formatet inte känns igen.
    """
    text = extract_pdf_text(pdf_bytes)
    if looks_like_amex(text):
        return parse_amex(text)
    if looks_like_seb_kort(text):
        return parse_seb_kort(text)
    raise ValueError(
        "Okänt PDF-format. Hembudget känner igen SAS Amex Premium och "
        "SAS EuroBonus MC Premium (SEB Kort). Använd vision-flödet eller "
        "CSV-import för andra format."
    )


def parse_statement_text(text: str) -> ParsedStatement:
    """Samma som parse_statement men tar redan extraherad text (för tester)."""
    if looks_like_amex(text):
        return parse_amex(text)
    if looks_like_seb_kort(text):
        return parse_seb_kort(text)
    raise ValueError("Okänt format")
