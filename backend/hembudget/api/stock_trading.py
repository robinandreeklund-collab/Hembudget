"""Per-elev-endpoints för aktiehandel — köp, sälj, portfölj, ledger.

Wrappar `stocks/trading.py`-funktioner med FastAPI-deps. Body-validering
via Pydantic, fel översätts till HTTPException 400 med felkod.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db.models import StockHolding, StockTransaction, StockWatchlist
from ..school.engines import master_session
from ..stocks.trading import (
    TradeError,
    TradeResult,
    buy_stock,
    get_portfolio,
    sell_stock,
)
from .deps import db, require_auth


router = APIRouter(
    prefix="/stocks", tags=["stocks-trading"], dependencies=[Depends(require_auth)],
)


class BuyIn(BaseModel):
    account_id: int
    quantity: int = Field(gt=0)
    student_rationale: Optional[str] = None


class SellIn(BaseModel):
    account_id: int
    quantity: int = Field(gt=0)
    student_rationale: Optional[str] = None


def _result_dict(r: TradeResult) -> dict:
    return {
        "transaction_id": r.transaction_id,
        "side": r.side,
        "ticker": r.ticker,
        "quantity": r.quantity,
        "price": float(r.price),
        "courtage": float(r.courtage),
        "total_amount": float(r.total_amount),
        "realized_pnl": (
            float(r.realized_pnl) if r.realized_pnl is not None else None
        ),
        "holding_quantity_after": r.holding_quantity_after,
        "holding_avg_cost_after": (
            float(r.holding_avg_cost_after)
            if r.holding_avg_cost_after is not None else None
        ),
        "cash_balance_after": float(r.cash_balance_after),
    }


@router.post("/{ticker}/buy")
def buy(ticker: str, payload: BuyIn, scope: Session = Depends(db)) -> dict:
    """Köp aktier till marknadspris."""
    try:
        with master_session() as ms:
            r = buy_stock(
                scope_session=scope,
                master_session=ms,
                account_id=payload.account_id,
                ticker=ticker,
                quantity=payload.quantity,
                student_rationale=payload.student_rationale,
            )
        return _result_dict(r)
    except TradeError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{ticker}/sell")
def sell(ticker: str, payload: SellIn, scope: Session = Depends(db)) -> dict:
    """Sälj aktier till marknadspris."""
    try:
        with master_session() as ms:
            r = sell_stock(
                scope_session=scope,
                master_session=ms,
                account_id=payload.account_id,
                ticker=ticker,
                quantity=payload.quantity,
                student_rationale=payload.student_rationale,
            )
        return _result_dict(r)
    except TradeError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/portfolio")
def portfolio(account_id: Optional[int] = None, scope: Session = Depends(db)) -> dict:
    """Hela portföljen — alla ISK-konton om account_id saknas."""
    with master_session() as ms:
        return get_portfolio(
            scope_session=scope, master_session=ms, account_id=account_id,
        )


@router.get("/ledger")
def ledger(
    limit: int = Query(default=200, le=500),
    ticker: Optional[str] = None,
    scope: Session = Depends(db),
) -> dict:
    """Hela elevens ledger — append-only StockTransaction-rader.

    Lärare har drilldown-vy som använder samma endpoint i
    impersonations-läge."""
    q = scope.query(StockTransaction).order_by(StockTransaction.executed_at.desc())
    if ticker:
        q = q.filter(StockTransaction.ticker == ticker)
    rows = q.limit(limit).all()
    return {
        "ledger": [
            {
                "id": r.id,
                "ticker": r.ticker,
                "side": r.side,
                "quantity": r.quantity,
                "price": float(r.price),
                "courtage": float(r.courtage),
                "total_amount": float(r.total_amount),
                "realized_pnl": (
                    float(r.realized_pnl) if r.realized_pnl is not None else None
                ),
                "quote_id": r.quote_id,
                "transaction_id": r.transaction_id,
                "student_rationale": r.student_rationale,
                "executed_at": r.executed_at.isoformat(),
            }
            for r in rows
        ],
        "count": len(rows),
    }


# --- Watchlist ---

class WatchlistIn(BaseModel):
    ticker: str


@router.get("/watchlist")
def list_watchlist(scope: Session = Depends(db)) -> dict:
    rows = scope.query(StockWatchlist).order_by(StockWatchlist.added_at.desc()).all()
    return {
        "tickers": [r.ticker for r in rows],
        "count": len(rows),
    }


@router.post("/watchlist/add")
def add_to_watchlist(payload: WatchlistIn, scope: Session = Depends(db)) -> dict:
    existing = (
        scope.query(StockWatchlist)
        .filter(StockWatchlist.ticker == payload.ticker)
        .first()
    )
    if existing is None:
        scope.add(StockWatchlist(ticker=payload.ticker))
        scope.flush()
    return {"ok": True, "ticker": payload.ticker}


@router.post("/watchlist/remove")
def remove_from_watchlist(payload: WatchlistIn, scope: Session = Depends(db)) -> dict:
    deleted = (
        scope.query(StockWatchlist)
        .filter(StockWatchlist.ticker == payload.ticker)
        .delete(synchronize_session=False)
    )
    scope.flush()
    return {"ok": True, "deleted": int(deleted)}


# --- Pending orders (kö) ---

class QueueOrderIn(BaseModel):
    account_id: int
    side: str  # "buy" | "sell"
    quantity: int = Field(gt=0)
    student_rationale: Optional[str] = None


@router.post("/{ticker}/queue")
def queue(ticker: str, payload: QueueOrderIn, scope: Session = Depends(db)) -> dict:
    """Lägg en kö-order — utförs när marknaden öppnar (eller direkt
    om den redan är öppen vid nästa polltick)."""
    from ..stocks.orders import queue_order
    try:
        with master_session() as ms:
            order = queue_order(
                scope_session=scope,
                master_session=ms,
                account_id=payload.account_id,
                ticker=ticker,
                side=payload.side,
                quantity=payload.quantity,
                student_rationale=payload.student_rationale,
            )
        return _order_dict(order)
    except TradeError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/orders")
def list_pending_orders(
    account_id: Optional[int] = None,
    scope: Session = Depends(db),
) -> dict:
    """Lista pending + senaste executade/cancelled-ordrar.

    Lazy execution: vi försöker exekvera pending-ordrar BARA om
    marknaden är öppen NU. På så sätt utförs köordrar när eleven
    nästa gång öppnar /investments — inget cron-jobb behövs.
    """
    from ..stocks.orders import execute_pending_orders, list_orders
    with master_session() as ms:
        try:
            execute_pending_orders(scope_session=scope, master_session=ms)
        except Exception:
            pass  # fail-soft — listan visas oavsett
    rows = list_orders(scope_session=scope, account_id=account_id, limit=100)
    return {
        "orders": [_order_dict(o) for o in rows],
        "count": len(rows),
    }


@router.delete("/orders/{order_id}")
def cancel_pending_order(
    order_id: int,
    account_id: int,
    scope: Session = Depends(db),
) -> dict:
    """Avbryt en pending order. Eleven kan bara avbryta sina egna."""
    from ..stocks.orders import cancel_order
    try:
        order = cancel_order(
            scope_session=scope,
            account_id=account_id,
            order_id=order_id,
        )
        return _order_dict(order)
    except TradeError as exc:
        raise HTTPException(400, str(exc)) from exc


def _order_dict(o) -> dict:
    return {
        "id": o.id,
        "account_id": o.account_id,
        "ticker": o.ticker,
        "side": o.side,
        "quantity": o.quantity,
        "reference_price": float(o.reference_price),
        "status": o.status,
        "requested_at": o.requested_at.isoformat() if o.requested_at else None,
        "executed_at": o.executed_at.isoformat() if o.executed_at else None,
        "executed_price": (
            float(o.executed_price) if o.executed_price is not None else None
        ),
        "locked_amount": float(o.locked_amount),
        "cancel_reason": o.cancel_reason,
        "student_rationale": o.student_rationale,
    }
