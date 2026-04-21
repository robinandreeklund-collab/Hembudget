from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .base import BankParser, RawTransaction, decode_csv


def _parse_amount(s: str) -> Decimal:
    s = s.strip().replace("\xa0", "").replace(" ", "").replace("SEK", "").replace("kr", "")
    if not s:
        return Decimal("0")
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0")


def _parse_date(s: str):
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date: {s!r}")


class SebKortParser(BankParser):
    """SEB Kort (Mastercard Eurobonus) CSV.

    Export format: "Datum;Specifikation;Ort;Valuta;Utl.belopp/moms;Belopp"
    Purchases are negative.
    """

    bank = "seb_kort"
    name = "SEB Kort (Mastercard Eurobonus)"

    def detect(self, sample: bytes) -> bool:
        text = decode_csv(sample[:2000]).lower()
        if "seb kort" in text or "sebkort" in text:
            return True
        first = text.splitlines()[0] if text else ""
        fields = {f.strip().strip('"').lower() for f in first.split(";")}
        return "specifikation" in fields and "belopp" in fields and ("ort" in fields or "utl.belopp" in fields)

    def parse(self, content: bytes) -> list[RawTransaction]:
        text = decode_csv(content)
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        out: list[RawTransaction] = []
        for row in reader:
            norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if not norm.get("datum"):
                continue
            try:
                d = _parse_date(norm["datum"])
            except ValueError:
                continue
            amount = _parse_amount(norm.get("belopp", "0"))
            description = norm.get("specifikation", "")
            city = norm.get("ort", "")
            if city:
                description = f"{description} [{city}]" if description else city
            out.append(
                RawTransaction(
                    date=d,
                    amount=amount,
                    description=description,
                    currency=norm.get("valuta", "SEK") or "SEK",
                    meta={"foreign_amount": norm.get("utl.belopp/moms") or norm.get("utl.belopp") or None},
                )
            )
        return out
