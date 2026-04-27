"""API-router för aktier — universum, kurser, marknadsstatus.

Per-elev-endpoints (köp/sälj/portfölj) ligger i en egen router som
läggs till i Fas C.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..school.engines import master_session
from ..school.stock_models import (
    LatestStockQuote,
    MarketCalendar,
    StockMaster,
    StockQuote,
)
from ..stocks.calendar import is_market_open, next_open
from ..stocks.poller import poll_quotes
from .deps import require_auth


router = APIRouter(
    prefix="/stocks", tags=["stocks"], dependencies=[Depends(require_auth)],
)


def _stock_out(s: StockMaster, latest: Optional[LatestStockQuote] = None) -> dict:
    out = {
        "ticker": s.ticker,
        "name": s.name,
        "name_sv": s.name_sv,
        "sector": s.sector,
        "currency": s.currency,
        "exchange": s.exchange,
        "active": bool(s.active),
    }
    if latest is not None:
        out.update({
            "last": float(latest.last),
            "bid": float(latest.bid) if latest.bid is not None else None,
            "ask": float(latest.ask) if latest.ask is not None else None,
            "change_pct": latest.change_pct,
            "ts": latest.ts.isoformat() if latest.ts else None,
        })
    return out


@router.get("/universe")
def list_universe() -> dict:
    """Lista alla 30 tillgängliga aktier med senaste kurs (om finns)."""
    with master_session() as s:
        stocks = (
            s.query(StockMaster).filter(StockMaster.active == 1)
            .order_by(StockMaster.sector, StockMaster.name).all()
        )
        latest_map = {
            l.ticker: l for l in s.query(LatestStockQuote).all()
        }
        return {
            "stocks": [_stock_out(st, latest_map.get(st.ticker)) for st in stocks],
            "count": len(stocks),
        }


@router.get("/{ticker}")
def get_stock(ticker: str) -> dict:
    """Detaljer + senaste kurs + dagens utveckling för en aktie."""
    with master_session() as s:
        stock = (
            s.query(StockMaster).filter(StockMaster.ticker == ticker).first()
        )
        if stock is None:
            raise HTTPException(404, f"Okänd ticker: {ticker}")
        latest = (
            s.query(LatestStockQuote).filter(LatestStockQuote.ticker == ticker).first()
        )
        return _stock_out(stock, latest)


@router.get("/{ticker}/history")
def get_history(
    ticker: str,
    period: str = Query("1d", pattern="^(1d|1w|1m|1y)$"),
) -> dict:
    """Returnerar kursvärden för en period.

    Aggregering:
      1d → råa quotes senaste dygnet
      1w → senaste 7 dagar (fortfarande råa)
      1m → senaste 30 dagar
      1y → max 365 dagar (downsamplead till close-per-dag)
    """
    days_map = {"1d": 1, "1w": 7, "1m": 30, "1y": 365}
    days = days_map[period]
    cutoff = datetime.utcnow() - timedelta(days=days)

    with master_session() as s:
        rows = (
            s.query(StockQuote)
            .filter(
                StockQuote.ticker == ticker,
                StockQuote.ts >= cutoff,
            )
            .order_by(StockQuote.ts.asc())
            .all()
        )
        return {
            "ticker": ticker,
            "period": period,
            "points": [
                {"ts": r.ts.isoformat(), "last": float(r.last)}
                for r in rows
            ],
            "count": len(rows),
        }


@router.get("/fx/usd-sek")
def fx_usd_sek() -> dict:
    """Aktuell USD/SEK-kurs + 30 dagars historik för pedagogisk graf.

    Returnerar:
      - rate: SEK per 1 USD (senast pollade värde)
      - ts: tidpunkt för senaste poll
      - history: [{date, rate}] — senaste 30 dagar (en rad per dag)
      - change_pct_30d: hur mycket kronan stärkts/försvagats senaste 30d
    """
    from datetime import timedelta
    from ..school.stock_models import FxRate, LatestFxRate

    with master_session() as s:
        latest = (
            s.query(LatestFxRate)
            .filter(LatestFxRate.base == "USD", LatestFxRate.quote == "SEK")
            .first()
        )
        if not latest:
            return {
                "rate": None, "ts": None,
                "history": [], "change_pct_30d": None,
            }
        cutoff = datetime.utcnow() - timedelta(days=30)
        rows = (
            s.query(FxRate)
            .filter(
                FxRate.base == "USD", FxRate.quote == "SEK",
                FxRate.ts >= cutoff,
            )
            .order_by(FxRate.ts.asc())
            .all()
        )
        # En rad per dag (sista quoten per datum) för rimligt graf-data
        by_date: dict = {}
        for r in rows:
            by_date[r.ts.date().isoformat()] = float(r.rate)
        history = [
            {"date": d, "rate": v}
            for d, v in sorted(by_date.items())
        ]
        change_pct_30d = None
        if len(history) >= 2:
            first_rate = history[0]["rate"]
            if first_rate > 0:
                change_pct_30d = round(
                    (history[-1]["rate"] - first_rate) / first_rate * 100, 2,
                )
        return {
            "rate": float(latest.rate),
            "ts": latest.ts.isoformat() if latest.ts else None,
            "history": history,
            "change_pct_30d": change_pct_30d,
        }


@router.get("/market/status")
def market_status() -> dict:
    """Är börsen öppen just nu? + nästa öppning om stängd.

    Använder is_market_open() utan at-argument så servern hämtar
    Stockholm-tid via _now_stockholm. Tidigare passades datetime.now()
    (naiv UTC på Cloud Run) som tolkades som Stockholm-naiv → börsen
    visades som stängd första 1-2 timmar varje dag.
    """
    with master_session() as s:
        is_open = is_market_open(s)
        nxt = next_open(s) if not is_open else None
        return {
            "open": is_open,
            "now": datetime.utcnow().isoformat(),
            "next_open": nxt.isoformat() if nxt else None,
        }


@router.post("/internal/poll-quotes")
def trigger_poll_quotes(force: bool = False) -> dict:
    """Manuell trigger av kurspollning. Cloud Scheduler kan pinga
    denna var 5:e min under börstid; alternativt köras manuellt vid
    utveckling.

    OBS: Skyddad av require_auth ovan — i prod ska Cloud Scheduler
    skicka identitetstoken. För dev räcker bearer-token.
    """
    with master_session() as s:
        return poll_quotes(s, force=force)
