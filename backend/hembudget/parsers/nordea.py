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
        header = [h.strip().lower().lstrip("﻿") for h in rows[0]]
        out: list[RawTransaction] = []

        def col(name: str, row: list[str]) -> str:
            try:
                idx = header.index(name)
            except ValueError:
                return ""
            return row[idx].strip() if idx < len(row) else ""

        # Identify own account-number tokens so they can be stripped from
        # descriptions — Nordea fills the Avsändare/Mottagare columns with
        # the user's own number which is noise for categorization.
        own_accounts: set[str] = set()
        for row in rows[1:]:
            for name in ("avsändare", "mottagare"):
                val = col(name, row)
                if val:
                    own_accounts.add(val)

        for idx, row in enumerate(rows[1:]):
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
            description = self._build_description(
                rubrik=col("rubrik", row),
                mottagare=col("mottagare", row),
                avsandare=col("avsändare", row),
                namn=col("namn", row),
                transaktion=col("transaktion", row),
                own_accounts=own_accounts,
            )
            balance_str = col("saldo", row)
            balance = _parse_amount(balance_str) if balance_str else None
            currency = col("valuta", row) or "SEK"
            out.append(
                RawTransaction(
                    date=d,
                    amount=amount,
                    description=description,
                    currency=currency,
                    balance=balance,
                    row_index=idx,
                )
            )
        return out

    @staticmethod
    def _build_description(
        *,
        rubrik: str,
        mottagare: str,
        avsandare: str,
        namn: str,
        transaktion: str,
        own_accounts: set[str],
    ) -> str:
        """Prefer Rubrik; fall back to Namn/motpart. Drop own-account noise."""
        primary = rubrik or namn or transaktion
        counterparty = ""
        for candidate in (mottagare, avsandare, namn):
            if candidate and candidate not in own_accounts:
                counterparty = candidate
                break
        if primary and counterparty and counterparty.lower() not in primary.lower():
            return f"{primary} — {counterparty}"
        return primary or counterparty or ""
