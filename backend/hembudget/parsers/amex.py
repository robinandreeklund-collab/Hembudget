from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .base import BankParser, RawTransaction, decode_csv


def _parse_amount(s: str) -> Decimal:
    s = s.strip().replace("\xa0", "").replace(" ", "").replace("kr", "").replace("SEK", "")
    if not s:
        return Decimal("0")
    # Amex: credit = negative amount in "Belopp" column for purchases
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0")


def _parse_date(s: str):
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date: {s!r}")


class AmexParser(BankParser):
    """Amex Eurobonus CSV-export.

    Typical header: Datum;Beskrivning;Belopp;Utlandsbelopp;Kategori
    Amex reports purchases as negative amounts.
    """

    bank = "amex"
    name = "American Express (Eurobonus)"

    HEADER_KEYS = {"datum", "beskrivning", "belopp"}

    def detect(self, sample: bytes) -> bool:
        text = decode_csv(sample[:2000]).lower()
        if "american express" in text or "amex" in text:
            return True
        first = text.splitlines()[0] if text else ""
        fields = {f.strip().strip('"') for f in first.split(";")}
        return self.HEADER_KEYS.issubset(fields)

    def parse(self, content: bytes) -> list[RawTransaction]:
        text = decode_csv(content)
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        out: list[RawTransaction] = []
        for row in reader:
            norm = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if not norm.get("datum"):
                continue
            try:
                d = _parse_date(norm["datum"])
            except ValueError:
                continue
            amount = _parse_amount(norm.get("belopp", "0"))
            desc = norm.get("beskrivning", "")
            out.append(
                RawTransaction(
                    date=d,
                    amount=amount,
                    description=desc,
                    currency="SEK",
                    meta={"foreign_amount": norm.get("utlandsbelopp", "") or None,
                          "amex_category": norm.get("kategori") or None},
                )
            )
        return out
