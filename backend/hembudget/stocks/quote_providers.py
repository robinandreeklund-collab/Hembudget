"""Datakällor för aktiekurser.

Abstraktion `QuoteProvider` med två implementationer:

- `MockQuoteProvider`: deterministisk seed:ad slumpgenerator. Används
  i tester och som fallback om ingen riktig källa svarar. Kan också
  användas i klassrum utan internet.
- `YFinanceProvider`: hämtar data från Yahoo Finance via `yfinance`-
  paketet. Gratis men inofficiellt — kan brytas. Ej en hård
  beroende — `yfinance` importeras lazy så systemet startar utan
  paketet installerat.

Provider väljs via env-var `HEMBUDGET_QUOTE_PROVIDER` (default `mock`).
Sätt till `yfinance` i prod när paketet finns.
"""
from __future__ import annotations

import logging
import os
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class Quote:
    """En enskild kurs-observation från datakällan."""
    ticker: str
    last: Decimal
    bid: Optional[Decimal]
    ask: Optional[Decimal]
    volume: Optional[int]
    change_pct: Optional[float]
    ts: datetime


class QuoteProvider(ABC):
    """Hämtar kurser för en lista av tickers. Implementationer ska
    aldrig kasta — om en kurs saknas returneras inget värde för den
    tickern. Detta gör att en enstaka fail inte stoppar hela polltick:en.
    """

    name: str = "abstract"

    @abstractmethod
    def fetch_quotes(self, tickers: list[str]) -> list[Quote]:
        """Returnera kurser för så många tickers som möjligt."""


# --- Mock-provider för tester och offline-läge ---

class MockQuoteProvider(QuoteProvider):
    """Deterministisk slumpgenerator. Pris för en ticker drivs av
    `(ticker, ts)` så samma anrop alltid ger samma resultat —
    nödvändigt för reproducerbara tester och rättvisa mellan elever.

    Basprissätter en ticker baserat på dess hash modulo 500 + 50 (så
    aktier landar mellan 50 och 550 kr). Varje tick rör priset ±2 %
    enligt en seed:ad slumpgenerator.
    """

    name = "mock"

    def __init__(self, *, base_seed: int = 1) -> None:
        self.base_seed = base_seed

    def _base_price(self, ticker: str) -> Decimal:
        # Stabil "fundamental" — samma över tid för en ticker
        h = abs(hash(ticker)) % 500
        return Decimal(50 + h)

    def fetch_quotes(self, tickers: list[str]) -> list[Quote]:
        ts = datetime.utcnow().replace(microsecond=0)
        bucket = ts.replace(second=0, minute=(ts.minute // 5) * 5)
        out: list[Quote] = []
        for t in tickers:
            base = self._base_price(t)
            rng = random.Random(f"{self.base_seed}|{t}|{bucket.isoformat()}")
            drift = Decimal(str(round(rng.uniform(-0.02, 0.02), 4)))
            last = (base * (Decimal("1") + drift)).quantize(Decimal("0.01"))
            spread = Decimal("0.05")
            out.append(Quote(
                ticker=t,
                last=last,
                bid=last - spread,
                ask=last + spread,
                volume=rng.randint(100_000, 5_000_000),
                change_pct=float(drift) * 100,
                ts=ts,
            ))
        return out


# --- YFinanceProvider — gratis, inofficiell ---

class YFinanceProvider(QuoteProvider):
    """Yahoo Finance via `yfinance`-paketet. Försening ~15 min på
    gratisnivån — det är pedagogiskt OK men måste märkas i UI."""

    name = "yfinance"

    def fetch_quotes(self, tickers: list[str]) -> list[Quote]:
        try:
            import yfinance as yf  # type: ignore
        except ImportError:
            log.warning(
                "yfinance saknas — pip install yfinance för att aktivera",
            )
            return []

        out: list[Quote] = []
        ts = datetime.utcnow().replace(microsecond=0)
        try:
            data = yf.Tickers(" ".join(tickers))
        except Exception as exc:  # nätverk, parse-fel
            log.warning("yfinance fetch failed: %s", exc)
            return []

        for t in tickers:
            try:
                info = data.tickers[t].fast_info  # type: ignore[attr-defined]
                last_raw = info.get("last_price") if isinstance(info, dict) else getattr(info, "last_price", None)
                if last_raw is None:
                    continue
                last = Decimal(str(last_raw)).quantize(Decimal("0.01"))
                prev_raw = (
                    info.get("previous_close") if isinstance(info, dict)
                    else getattr(info, "previous_close", None)
                )
                change_pct = None
                if prev_raw:
                    prev = Decimal(str(prev_raw))
                    if prev > 0:
                        change_pct = float((last - prev) / prev) * 100
                out.append(Quote(
                    ticker=t,
                    last=last,
                    bid=None,
                    ask=None,
                    volume=None,
                    change_pct=change_pct,
                    ts=ts,
                ))
            except Exception as exc:
                log.warning("yfinance per-ticker fetch failed for %s: %s", t, exc)
                continue
        return out


def get_provider(name: Optional[str] = None) -> QuoteProvider:
    """Faktorymetod baserad på env-var."""
    name = name or os.environ.get("HEMBUDGET_QUOTE_PROVIDER", "mock")
    name = (name or "mock").lower().strip()
    if name == "yfinance":
        return YFinanceProvider()
    if name == "mock":
        return MockQuoteProvider()
    log.warning("Okänd HEMBUDGET_QUOTE_PROVIDER=%s — använder mock", name)
    return MockQuoteProvider()
