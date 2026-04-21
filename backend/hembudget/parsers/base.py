from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class RawTransaction:
    date: date
    amount: Decimal
    description: str
    currency: str = "SEK"
    counterparty: str | None = None
    balance: Decimal | None = None
    reference: str | None = None
    row_index: int | None = None   # fallback-unikgörare när balance saknas
    meta: dict = field(default_factory=dict)

    def stable_hash(self, account_id: int | str) -> str:
        # Include balance when available so two identical same-day rows don't
        # dedupe each other (Nordea gives us this for free). Fall back to
        # row_index for sources without balance (credit-card CSVs).
        extra = ""
        if self.balance is not None:
            extra = f"|{self.balance}"
        elif self.row_index is not None:
            extra = f"|#{self.row_index}"
        key = (
            f"{account_id}|{self.date.isoformat()}|{self.amount}|"
            f"{self.description.strip().lower()}{extra}"
        )
        return hashlib.sha256(key.encode("utf-8")).hexdigest()


class BankParser:
    """Abstract base for bank CSV parsers."""

    bank: str = ""
    name: str = ""

    def detect(self, sample: bytes) -> bool:
        raise NotImplementedError

    def parse(self, content: bytes) -> list[RawTransaction]:
        raise NotImplementedError


def _sniff_decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "iso-8859-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def decode_csv(content: bytes) -> str:
    return _sniff_decode(content)
