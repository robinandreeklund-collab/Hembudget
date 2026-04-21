from __future__ import annotations

from .amex import AmexParser
from .base import BankParser
from .nordea import NordeaParser
from .seb_kort import SebKortParser
from .seb_kort_xlsx import SebKortXlsxParser

# Order matters: xlsx must come before csv-based seb_kort because
# detection for the csv variant only looks at text headers.
ALL_PARSERS: list[BankParser] = [
    SebKortXlsxParser(),
    AmexParser(),
    NordeaParser(),
    SebKortParser(),
]


def detect_parser(content: bytes) -> BankParser | None:
    sample = content[:4000]
    for parser in ALL_PARSERS:
        try:
            if parser.detect(sample):
                return parser
        except Exception:
            continue
    return None


def parser_for_bank(bank: str, sample: bytes | None = None) -> BankParser | None:
    """Return a parser matching the given bank id. When multiple variants
    exist (e.g. seb_kort CSV + XLSX), the sample bytes are used to pick."""
    matches = [p for p in ALL_PARSERS if p.bank == bank]
    if not matches:
        return None
    if sample is not None:
        for p in matches:
            try:
                if p.detect(sample[:4096]):
                    return p
            except Exception:
                continue
    return matches[0]
