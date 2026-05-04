"""Pending orders — köorder som utförs när marknaden öppnar.

Pedagogiskt syfte: eleven kan planera trades utanför börstid och se
exakt vilket pris hen fick vid öppning. Lär ut att timing är osäker
och att man inte kan välja exakt pris om man inte sätter limit-order
(framtida feature).

Flöde:
  1. queue_order() — lägg ordern i kö, lås cash (köp) eller andelar (sälj)
  2. execute_pending_orders() — körs efter varje poll-cycle. Utför
     pending-ordrar för tickers vars marknad är öppen, till latest
     price. Skapar StockTransaction + Transaction (som vid direkt-handel).
  3. cancel_order() — eleven avbryter och lås frigörs.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..db.models import (
    Account, PendingOrder, StockHolding, Transaction,
)
from ..school.stock_models import LatestStockQuote, StockMaster
from .calendar import is_market_open
from .courtage import compute_courtage_breakdown
from .trading import TradeError, _balance_for, buy_stock, sell_stock

log = logging.getLogger(__name__)


def queue_order(
    *,
    scope_session: Session,
    master_session: Session,
    account_id: int,
    ticker: str,
    side: str,
    quantity: int,
    student_rationale: Optional[str] = None,
) -> PendingOrder:
    """Lägg en kö-order. Validerar konto + ticker + cash/holding och
    låser belopp/antal. Kastar TradeError vid problem."""
    if side not in ("buy", "sell"):
        raise TradeError(f"Ogiltig side: {side}")
    if quantity <= 0:
        raise TradeError("Antal måste vara > 0")

    acc = scope_session.get(Account, account_id)
    if acc is None:
        raise TradeError("Konto saknas")
    stock = (
        master_session.query(StockMaster)
        .filter(StockMaster.ticker == ticker)
        .first()
    )
    if stock is None:
        raise TradeError(f"Aktie {ticker} finns inte i universumet")

    latest = (
        master_session.query(LatestStockQuote)
        .filter(LatestStockQuote.ticker == ticker)
        .first()
    )
    if latest is None:
        raise TradeError(
            "Ingen aktuell kurs — vänta tills nästa polltick",
            code="no_quote",
        )
    ref_price = Decimal(str(latest.last))

    locked_amount = Decimal("0")
    if side == "buy":
        # Reservera cash + 5 % buffert för pris/FX-rörelse till exekvering
        gross = (ref_price * quantity).quantize(Decimal("0.01"))
        breakdown = compute_courtage_breakdown(
            gross, currency=stock.currency or "SEK",
        )
        # 5 % buffert räcker för normala pris-rörelser över helg
        estimate = (gross + breakdown.total_fee) * Decimal("1.05")
        # Lokal valuta-konvertering till SEK om USD-aktie
        if stock.currency == "USD":
            from ..school.stock_models import LatestFxRate
            fx = (
                master_session.query(LatestFxRate)
                .filter(LatestFxRate.base == "USD",
                        LatestFxRate.quote == "SEK")
                .first()
            )
            if fx:
                estimate = (estimate * Decimal(str(fx.rate))).quantize(
                    Decimal("0.01"),
                )
        locked_amount = estimate.quantize(Decimal("0.01"))
        cash_available = _available_cash(scope_session, account_id)
        if cash_available < locked_amount:
            raise TradeError(
                f"Saldot räcker inte (har {cash_available} kr, "
                f"behöver ~{locked_amount} kr inkl. buffert)",
                code="insufficient_funds",
            )
    else:  # sell
        held = (
            scope_session.query(StockHolding)
            .filter(
                StockHolding.account_id == account_id,
                StockHolding.ticker == ticker,
            )
            .first()
        )
        if held is None or held.quantity < quantity:
            available = held.quantity if held else 0
            # Dra av redan-pending sell-ordrar
            pending_sells = (
                scope_session.query(PendingOrder)
                .filter(
                    PendingOrder.account_id == account_id,
                    PendingOrder.ticker == ticker,
                    PendingOrder.side == "sell",
                    PendingOrder.status == "pending",
                )
                .all()
            )
            already_locked = sum(p.quantity for p in pending_sells)
            free = available - already_locked
            if free < quantity:
                raise TradeError(
                    f"Du har bara {free} st {ticker} ledigt att sälja "
                    f"({already_locked} redan i kö)",
                    code="insufficient_shares",
                )

    order = PendingOrder(
        account_id=account_id,
        ticker=ticker,
        side=side,
        quantity=quantity,
        reference_price=ref_price,
        status="pending",
        requested_at=datetime.utcnow(),
        locked_amount=locked_amount,
        student_rationale=student_rationale,
    )
    scope_session.add(order)
    scope_session.flush()
    return order


def cancel_order(
    *, scope_session: Session, account_id: int, order_id: int,
) -> PendingOrder:
    """Eleven avbryter en pending order. Lås frigörs automatiskt
    (cash är inte fysiskt dragen, antals-låsning beräknas dynamiskt)."""
    order = (
        scope_session.query(PendingOrder)
        .filter(
            PendingOrder.id == order_id,
            PendingOrder.account_id == account_id,
        )
        .first()
    )
    if order is None:
        raise TradeError("Ordern finns inte", code="not_found")
    if order.status != "pending":
        raise TradeError(
            f"Ordern är redan {order.status}", code="not_pending",
        )
    order.status = "cancelled"
    order.cancel_reason = "user_cancelled"
    scope_session.flush()
    return order


def list_orders(
    *, scope_session: Session, account_id: Optional[int] = None,
    limit: int = 50,
) -> list[PendingOrder]:
    """Lista ordrar för konto (eller alla för eleven om account_id=None)."""
    q = scope_session.query(PendingOrder).order_by(
        PendingOrder.requested_at.desc(),
    )
    if account_id is not None:
        q = q.filter(PendingOrder.account_id == account_id)
    return q.limit(limit).all()


def execute_pending_orders(
    *, scope_session: Session, master_session: Session,
) -> dict:
    """Utför alla pending-ordrar vars marknad nu är öppen.

    Körs efter varje poll-cycle. Idempotent — re-körning ignorerar
    redan executade/cancelled-ordrar.

    Returnerar {executed: N, cancelled: N, skipped: N, errors: [...]}.
    """
    pending = (
        scope_session.query(PendingOrder)
        .filter(PendingOrder.status == "pending")
        .all()
    )
    if not pending:
        return {"executed": 0, "cancelled": 0, "skipped": 0, "errors": []}

    executed = 0
    cancelled = 0
    skipped = 0
    errors: list[str] = []
    for order in pending:
        # Kolla att ticker fortfarande finns och dess marknad är öppen
        stock = (
            master_session.query(StockMaster)
            .filter(StockMaster.ticker == order.ticker)
            .first()
        )
        if stock is None:
            order.status = "cancelled"
            order.cancel_reason = "ticker_removed"
            cancelled += 1
            continue
        # is_market_open kollar tid mot calendar — för USA-aktier
        # kommer de hoppas över i Sverige-tid 09:00-15:30 (NYSE öppnar
        # 15:30 svensk vintertid). Detta är bara approximativt — för
        # full korrekthet skulle vi behöva exchange-specifik kalender.
        # Vi tar pragmatiskt: alla tickers utförs när XSTO är öppet.
        if not is_market_open(master_session):
            skipped += 1
            continue
        try:
            if order.side == "buy":
                result = buy_stock(
                    scope_session=scope_session,
                    master_session=master_session,
                    account_id=order.account_id,
                    ticker=order.ticker,
                    quantity=order.quantity,
                    student_rationale=order.student_rationale,
                    # Vi har redan gated på XSTO ovan; för US-aktier
                    # kanske NYSE är stängd men vi tillåter execution
                    # ändå mot senaste pris (pedagogisk simplification).
                    require_market_open=False,
                )
            else:
                result = sell_stock(
                    scope_session=scope_session,
                    master_session=master_session,
                    account_id=order.account_id,
                    ticker=order.ticker,
                    quantity=order.quantity,
                    student_rationale=order.student_rationale,
                    require_market_open=False,
                )
            order.status = "executed"
            order.executed_at = datetime.utcnow()
            order.executed_price = result.price
            order.stock_transaction_id = result.stock_transaction_id
            order.locked_amount = Decimal("0")
            executed += 1
        except TradeError as exc:
            order.status = "cancelled"
            order.cancel_reason = exc.code or str(exc)[:80]
            cancelled += 1
            errors.append(
                f"{order.ticker} {order.side} #{order.id}: {exc}"
            )
        except Exception as exc:
            log.exception(
                "execute_pending_orders: oväntat fel för order %s",
                order.id,
            )
            order.status = "cancelled"
            order.cancel_reason = f"error:{type(exc).__name__}"
            cancelled += 1
            errors.append(f"{order.ticker} #{order.id}: {exc}")

    scope_session.flush()
    return {
        "executed": executed,
        "cancelled": cancelled,
        "skipped": skipped,
        "errors": errors,
    }


def _available_cash(scope_session: Session, account_id: int) -> Decimal:
    """Cash på kontot MINUS låsta belopp för pending buy-ordrar."""
    base = _balance_for(scope_session, account_id)
    locked = (
        scope_session.query(PendingOrder)
        .filter(
            PendingOrder.account_id == account_id,
            PendingOrder.side == "buy",
            PendingOrder.status == "pending",
        )
        .all()
    )
    locked_total = sum(
        (p.locked_amount for p in locked), Decimal("0"),
    )
    return base - locked_total
