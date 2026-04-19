from __future__ import annotations

from .amex import AmexParser
from .base import BankParser
from .nordea import NordeaParser
from .seb_kort import SebKortParser

ALL_PARSERS: list[BankParser] = [AmexParser(), NordeaParser(), SebKortParser()]


def detect_parser(content: bytes) -> BankParser | None:
    sample = content[:4000]
    for parser in ALL_PARSERS:
        try:
            if parser.detect(sample):
                return parser
        except Exception:
            continue
    return None


def parser_for_bank(bank: str) -> BankParser | None:
    for p in ALL_PARSERS:
        if p.bank == bank:
            return p
    return None
