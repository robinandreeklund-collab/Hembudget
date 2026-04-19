from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .base import BankParser, RawTransaction, decode_csv


def _parse_amount(s: str) -> Decimal:
    s = s.strip().replace("\xa0", "").replace(" ", "")
    if not s:
        return Decimal("0")
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0")


def _parse_date(s: str):
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date: {s!r}")


class NordeaParser(BankParser):
    """Nordea privatkonto CSV.

    Header varies: "Bokföringsdag;Belopp;Avsändare;Mottagare;Namn;Rubrik;Saldo;Valuta"
    or older: "Datum;Transaktion;Kategori;Belopp;Saldo"
    """

    bank = "nordea"
    name = "Nordea"

    def detect(self, sample: bytes) -> bool:
        text = decode_csv(sample[:2000]).lower()
        if "nordea" in text:
            return True
        first = text.splitlines()[0] if text else ""
        fields = {f.strip().strip('"') for f in first.split(";")}
        return ("bokföringsdag" in fields and "belopp" in fields) or (
            "datum" in fields and "transaktion" in fields and "saldo" in fields
        )

    def parse(self, content: bytes) -> list[RawTransaction]:
        text = decode_csv(content)
        reader = csv.reader(io.StringIO(text), delimiter=";")
        rows = list(reader)
        if not rows:
            return []
        header = [h.strip().lower() for h in rows[0]]
        out: list[RawTransaction] = []

        def col(name: str, row: list[str]) -> str:
            try:
                idx = header.index(name)
            except ValueError:
                return ""
            return row[idx].strip() if idx < len(row) else ""

        for row in rows[1:]:
            if not row or not any(row):
                continue
            date_str = col("bokföringsdag", row) or col("datum", row)
            if not date_str:
                continue
            try:
                d = _parse_date(date_str)
            except ValueError:
                continue
            amount = _parse_amount(col("belopp", row))
            description_parts = [
                col("rubrik", row),
                col("mottagare", row),
                col("avsändare", row),
                col("namn", row),
                col("transaktion", row),
            ]
            description = " | ".join(p for p in description_parts if p)
            balance_str = col("saldo", row)
            balance = _parse_amount(balance_str) if balance_str else None
            currency = col("valuta", row) or "SEK"
            out.append(
                RawTransaction(
                    date=d,
                    amount=amount,
                    description=description or col("transaktion", row),
                    currency=currency,
                    balance=balance,
                )
            )
        return out
