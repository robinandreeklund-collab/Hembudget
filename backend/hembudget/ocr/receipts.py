from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class ReceiptResult:
    merchant: str | None
    amount: Decimal | None
    date: date | None
    raw_text: str


AMOUNT_RE = re.compile(r"(?i)(?:total|summa|att\s*betala|att\s*erl[aä]gga)[^\d\-]{0,20}(-?\d[\d\s]*[,\.]\d{2})")
FALLBACK_AMOUNT_RE = re.compile(r"(-?\d[\d\s]{0,8}[,\.]\d{2})\s*(?:kr|sek)?$", re.MULTILINE | re.IGNORECASE)
DATE_RE = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2})|(\d{2}[-/\.]\d{2}[-/\.]\d{2,4})")


def _parse_amount(s: str) -> Optional[Decimal]:
    s = s.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return None


def _parse_date(s: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


class ReceiptOCR:
    """Tunt Tesseract-wrapper. Kräver lokalt installerad tesseract + svenska (swe)."""

    def __init__(self, lang: str = "swe+eng"):
        self.lang = lang

    def extract(self, image_bytes: bytes) -> ReceiptResult:
        try:
            import pytesseract
            from PIL import Image
        except Exception as exc:
            log.warning("OCR unavailable: %s", exc)
            return ReceiptResult(None, None, None, "")

        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img, lang=self.lang)
        return self._parse(text)

    def _parse(self, text: str) -> ReceiptResult:
        amount = None
        m = AMOUNT_RE.search(text)
        if m:
            amount = _parse_amount(m.group(1))
        if amount is None:
            for m in FALLBACK_AMOUNT_RE.finditer(text):
                amt = _parse_amount(m.group(1))
                if amt is not None and amt != 0:
                    amount = amt  # use last one (often the total)

        receipt_date = None
        m = DATE_RE.search(text)
        if m:
            receipt_date = _parse_date(m.group(0))

        merchant = None
        for line in text.splitlines():
            line = line.strip()
            if line and any(c.isalpha() for c in line):
                merchant = line[:60]
                break

        return ReceiptResult(merchant=merchant, amount=amount, date=receipt_date, raw_text=text)
