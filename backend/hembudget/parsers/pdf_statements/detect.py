"""Autodetect: vilken kortutgivare är detta PDF-kontoutdrag?"""
from __future__ import annotations

from . import ParsedStatement, extract_pdf_text_layout
from .amex import looks_like_amex, parse_amex, reattribute_holders_by_sum
from .seb_kort import looks_like_seb_kort, parse_seb_kort


class UnknownStatementFormat(ValueError):
    """Kastas när detektionen inte matchar. Bär med extracted text och
    en lista över signaturer som testades så endpointet kan returnera
    detaljer till frontend."""

    def __init__(self, text: str):
        super().__init__(
            "Okänt PDF-format — varken Amex eller SEB Kort detekterades."
        )
        self.extracted_text = text


def parse_statement(
    pdf_bytes: bytes, force: str | None = None
) -> ParsedStatement:
    """Läs en kreditkorts-PDF och returnera strukturerad data.

    `force` kan vara 'amex' eller 'seb_kort' för att tvinga en viss parser
    (användbart när auto-detekteringen missar men användaren vet formatet).

    Kastar UnknownStatementFormat om formatet inte känns igen.
    """
    text = extract_pdf_text_layout(pdf_bytes)
    is_amex = force == "amex" or (force is None and looks_like_amex(text))
    is_seb = force == "seb_kort" or (force is None and looks_like_seb_kort(text))

    if is_amex:
        stmt = parse_amex(text)
        # Re-attribute cardholders via PDF:ens egna "Summa nya köp för X"
        # rader — Amex text-layout ger fel cardholder för köp i slutet
        # av huvudkortssektionen (KLM-refunder m.fl.). Vi har sanningen
        # direkt i PDF:ens summa-rader och använder greedy assignment.
        try:
            reattribute_holders_by_sum(stmt, text)
        except Exception:
            pass
        return stmt
    if is_seb:
        return parse_seb_kort(text)
    raise UnknownStatementFormat(text)


def parse_statement_text(
    text: str, force: str | None = None
) -> ParsedStatement:
    """Samma som parse_statement men tar redan extraherad text (för tester
    utan riktig PDF-bytes). Ingen X-kolumn-re-attribution här."""
    if force == "amex":
        return parse_amex(text)
    if force == "seb_kort":
        return parse_seb_kort(text)
    if looks_like_amex(text):
        return parse_amex(text)
    if looks_like_seb_kort(text):
        return parse_seb_kort(text)
    raise UnknownStatementFormat(text)
