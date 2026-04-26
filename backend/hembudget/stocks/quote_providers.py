"""Datakällor för aktiekurser.

Abstraktion `QuoteProvider` med tre implementationer:

- `MockQuoteProvider`: deterministisk seed:ad slumpgenerator. Används
  i tester och som fallback om ingen riktig källa svarar. Kan också
  användas i klassrum utan internet.
- `YFinanceProvider`: hämtar data från Yahoo Finance via `yfinance`-
  paketet. Gratis men inofficiellt — kan brytas. Ej en hård
  beroende — `yfinance` importeras lazy så systemet startar utan
  paketet installerat.
- `FinnhubProvider`: officiell källa, gratis nivå 60 anrop/min.
  Läser API-nyckel från (1) AppConfig-tabellen i master-DB
  (`finnhub_api_key`) eller (2) FINNHUB_API_KEY env-var. Super-
  admin sätter nyckeln via UI.

Provider väljs via env-var `HEMBUDGET_QUOTE_PROVIDER`. Auto-läge:
om ingen env-var är satt och Finnhub-nyckel finns → finnhub,
annars mock. Sätt explicit till `yfinance` om du vill ha det.
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


# --- FinnhubProvider — officiell, gratis 60 anrop/min ---

FINNHUB_KEY_CONFIG_KEY = "finnhub_api_key"


def _read_finnhub_key() -> str:
    """Läser API-nyckeln. DB-värdet (super-admin via UI) vinner över
    env-varen så nyckeln kan bytas utan redeploy."""
    try:
        from ..school.engines import master_session
        from ..school.models import AppConfig
        with master_session() as s:
            cfg = s.get(AppConfig, FINNHUB_KEY_CONFIG_KEY)
            if cfg and cfg.value and isinstance(cfg.value, dict):
                key = str(cfg.value.get("key", "")).strip()
                if key:
                    return key
    except Exception:
        log.exception("finnhub: kunde inte läsa nyckel från DB")
    return os.environ.get("FINNHUB_API_KEY", "").strip()


def finnhub_key_configured() -> bool:
    return bool(_read_finnhub_key())


def finnhub_key_source() -> str:
    """'db' om super-admin satt nyckeln via UI, 'env' om bara env-var,
    '' om ingen alls."""
    try:
        from ..school.engines import master_session
        from ..school.models import AppConfig
        with master_session() as s:
            cfg = s.get(AppConfig, FINNHUB_KEY_CONFIG_KEY)
            if cfg and cfg.value and isinstance(cfg.value, dict):
                key = str(cfg.value.get("key", "")).strip()
                if key:
                    return "db"
    except Exception:
        pass
    if os.environ.get("FINNHUB_API_KEY", "").strip():
        return "env"
    return ""


def finnhub_key_preview() -> str:
    k = _read_finnhub_key()
    if not k:
        return ""
    return f"…{k[-4:]}" if len(k) >= 4 else ""


class FinnhubProvider(QuoteProvider):
    """Hämtar realtidsquote från Finnhub.io.

    Endpoint: GET https://finnhub.io/api/v1/quote?symbol=X&token=KEY
    Svar: {c: current, h: high, l: low, o: open, pc: previous_close, t: ts}

    Rate limit på gratis: 60 anrop/min. För 30 OMXS30-tickers tar vi
    30 anrop per pollning — väl inom gränsen, ingen sleep behövs.
    Vi rate-limit:ar inte själva — om Finnhub returnerar 429 hoppar
    vi tickern och loggar.

    OMXS30-symboler: Yahoo använder t.ex. 'VOLV-B.ST'. Finnhub
    accepterar samma format på Stockholmsbörsen.
    """

    name = "finnhub"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or _read_finnhub_key()

    def fetch_quotes(self, tickers: list[str]) -> list[Quote]:
        if not self.api_key:
            log.warning("finnhub: ingen API-nyckel konfigurerad")
            return []
        try:
            import httpx  # type: ignore
        except ImportError:
            log.warning("finnhub: httpx saknas i miljön")
            return []

        out: list[Quote] = []
        ts = datetime.utcnow().replace(microsecond=0)
        # Använd context manager med timeout så en hängande request
        # inte blockerar pollings-jobbet.
        try:
            with httpx.Client(timeout=10.0) as client:
                for ticker in tickers:
                    try:
                        r = client.get(
                            "https://finnhub.io/api/v1/quote",
                            params={"symbol": ticker, "token": self.api_key},
                        )
                        if r.status_code == 429:
                            log.warning("finnhub: rate limit för %s", ticker)
                            continue
                        if r.status_code != 200:
                            log.warning(
                                "finnhub: status %d för %s",
                                r.status_code, ticker,
                            )
                            continue
                        data = r.json()
                        # Finnhub returnerar {c:0,...} för okända symboler
                        c = data.get("c")
                        if c is None or float(c) == 0:
                            continue
                        last = Decimal(str(c)).quantize(Decimal("0.01"))
                        prev = data.get("pc")
                        change_pct = None
                        if prev and float(prev) > 0:
                            change_pct = (
                                (float(c) - float(prev)) / float(prev) * 100
                            )
                        out.append(Quote(
                            ticker=ticker,
                            last=last,
                            bid=None,
                            ask=None,
                            volume=None,
                            change_pct=change_pct,
                            ts=ts,
                        ))
                    except Exception as exc:
                        log.warning(
                            "finnhub: fetch failed for %s: %s", ticker, exc,
                        )
                        continue
        except Exception as exc:
            log.warning("finnhub: client setup failed: %s", exc)
            return []
        return out


def get_provider(name: Optional[str] = None) -> QuoteProvider:
    """Faktorymetod.

    Auto-läge (env-var ej satt): finnhub om nyckel finns, annars mock.
    Explicit: 'finnhub' / 'yfinance' / 'mock'.
    """
    explicit = name or os.environ.get("HEMBUDGET_QUOTE_PROVIDER", "")
    explicit = (explicit or "").lower().strip()
    if explicit == "finnhub":
        return FinnhubProvider()
    if explicit == "yfinance":
        return YFinanceProvider()
    if explicit == "mock":
        return MockQuoteProvider()
    if explicit:
        log.warning("Okänd HEMBUDGET_QUOTE_PROVIDER=%s — auto-väljer", explicit)
    # Auto: finnhub om nyckel finns, annars mock
    if finnhub_key_configured():
        return FinnhubProvider()
    return MockQuoteProvider()
