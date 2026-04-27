"""Bakgrundsjobb som pollar kurser var 5:e min under börstid.

I V1 körs detta från en internal endpoint som kan triggas av:
- En förenklad scheduler i main.py::lifespan (om Cloud Run min-instances=1)
- Cloud Scheduler som pingar /internal/poll-quotes (rekommenderat — gratis)
- Manuellt vid utveckling och i tester

Modulen är ren från FastAPI-beroende så den kan testas isolerat.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..school.stock_models import LatestStockQuote, StockMaster, StockQuote
from .calendar import is_market_open
from .quote_providers import QuoteProvider, get_provider

log = logging.getLogger(__name__)


def poll_quotes(
    session: Session,
    *,
    provider: Optional[QuoteProvider] = None,
    force: bool = False,
) -> dict:
    """Hämta kurser för alla aktiva tickers och spara i StockQuote +
    LatestStockQuote.

    Hoppar över om börsen är stängd såvida `force=True`. När börsen är
    stängd används senaste fetched_at för LatestStockQuote — vi vill
    inte radera senaste kursen bara för att marknaden stängde.

    Returnerar `{fetched: N, skipped_market_closed: bool, ts: ISO}`.
    """
    if not force and not is_market_open(session):
        log.debug("poll_quotes: marknaden stängd, hoppar över")
        return {"fetched": 0, "skipped_market_closed": True, "ts": None}

    p = provider or get_provider()
    tickers = [
        s.ticker
        for s in session.query(StockMaster).filter(StockMaster.active == 1).all()
    ]
    if not tickers:
        return {"fetched": 0, "skipped_market_closed": False, "ts": None}

    quotes = p.fetch_quotes(tickers)
    # Fallback: om primär provider inte fick några quotes (t.ex. Finnhub
    # free tier som saknar Stockholm-börsen) — försök yfinance som backup.
    # Auto-faller bara tillbaka om provider inte är explicit specificerad.
    if not quotes and provider is None and p.name != "yfinance":
        from .quote_providers import YFinanceProvider
        log.info(
            "poll_quotes: %s gav 0 quotes, försöker yfinance-fallback",
            p.name,
        )
        try:
            yf = YFinanceProvider()
            quotes = yf.fetch_quotes(tickers)
            if quotes:
                p = yf  # uppdatera source-namnet på sparade rader
        except Exception:
            log.exception("poll_quotes: yfinance-fallback misslyckades")

    ts_iso: Optional[str] = None
    fetched = 0
    for q in quotes:
        # 1. Append history
        sq = StockQuote(
            ticker=q.ticker,
            ts=q.ts,
            last=q.last,
            bid=q.bid,
            ask=q.ask,
            volume=q.volume,
            change_pct=q.change_pct,
            source=p.name,
        )
        session.add(sq)
        session.flush()

        # 2. Upsert latest
        latest = (
            session.query(LatestStockQuote)
            .filter(LatestStockQuote.ticker == q.ticker)
            .first()
        )
        if latest is None:
            session.add(LatestStockQuote(
                ticker=q.ticker,
                last=q.last,
                bid=q.bid,
                ask=q.ask,
                change_pct=q.change_pct,
                ts=q.ts,
                quote_id=sq.id,
            ))
        else:
            latest.last = q.last
            latest.bid = q.bid
            latest.ask = q.ask
            latest.change_pct = q.change_pct
            latest.ts = q.ts
            latest.quote_id = sq.id
        fetched += 1
        ts_iso = q.ts.isoformat()

    session.flush()
    return {
        "fetched": fetched,
        "skipped_market_closed": False,
        "ts": ts_iso,
    }


def downsample_old_history(
    session: Session,
    *,
    keep_full_days: int = 90,
) -> int:
    """Behåll full upplösning senaste N dagar; reducera äldre till en
    rad per dag (sista quote per dag). Sparar storlek över tid.

    Returnerar antal raderade rader.
    """
    from datetime import date, timedelta
    from sqlalchemy import func as sa_func

    cutoff = date.today() - timedelta(days=keep_full_days)

    # Hitta alla (ticker, datum) där det finns >1 rad äldre än cutoff
    rows = (
        session.query(
            StockQuote.ticker,
            sa_func.date(StockQuote.ts).label("d"),
            sa_func.max(StockQuote.id).label("keep_id"),
        )
        .filter(StockQuote.ts < datetime.combine(cutoff, datetime.min.time()))
        .group_by(StockQuote.ticker, sa_func.date(StockQuote.ts))
        .all()
    )
    if not rows:
        return 0

    keep_ids = {r.keep_id for r in rows}
    deleted = (
        session.query(StockQuote)
        .filter(
            StockQuote.ts < datetime.combine(cutoff, datetime.min.time()),
            ~StockQuote.id.in_(keep_ids),
        )
        .delete(synchronize_session=False)
    )
    session.flush()
    return int(deleted or 0)
