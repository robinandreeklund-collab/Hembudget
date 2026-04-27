"""Kärnlogik för aktiehandel.

Funktionerna är rena (tar Session + master-Session) så de kan testas
isolerat utan FastAPI. Endpoints i api/stock_trading.py wrappar dem.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..db.models import Account, StockHolding, StockTransaction, Transaction
from ..school.stock_models import LatestStockQuote, StockMaster
from .calendar import is_market_open
from .courtage import compute_courtage

log = logging.getLogger(__name__)


class TradeError(Exception):
    """Affärsfel — översätts till HTTP 400 i endpoint-lagret."""

    def __init__(self, message: str, code: str = "trade_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class TradeResult:
    transaction_id: int
    side: str
    ticker: str
    quantity: int
    price: Decimal
    courtage: Decimal
    total_amount: Decimal
    realized_pnl: Optional[Decimal]
    holding_quantity_after: int
    holding_avg_cost_after: Optional[Decimal]
    cash_balance_after: Decimal


def _balance_for(session: Session, account_id: int) -> Decimal:
    """Lokal kopia av balans-helpern för att undvika cyklisk import."""
    from sqlalchemy import func as sa_func

    acc = session.get(Account, account_id)
    if acc is None:
        return Decimal("0")
    base = acc.opening_balance or Decimal("0")
    q = session.query(
        sa_func.coalesce(sa_func.sum(Transaction.amount), 0),
    ).filter(Transaction.account_id == account_id)
    if acc.opening_balance_date is not None:
        q = q.filter(Transaction.date >= acc.opening_balance_date)
    total = q.scalar() or Decimal("0")
    if not isinstance(total, Decimal):
        total = Decimal(str(total))
    return base + total


def _verify_isk_account(session: Session, account_id: int) -> Account:
    acc = session.get(Account, account_id)
    if acc is None:
        raise TradeError("Konto saknas", code="account_not_found")
    if acc.type != "isk":
        raise TradeError(
            "Aktiehandel kräver ISK-konto", code="account_wrong_type",
        )
    return acc


def buy_stock(
    *,
    scope_session: Session,
    master_session: Session,
    account_id: int,
    ticker: str,
    quantity: int,
    student_rationale: Optional[str] = None,
    require_market_open: bool = True,
) -> TradeResult:
    """Genomför ett köp till marknadspris.

    Steg:
      1. Validera börstid + konto + saldo + ticker existerar
      2. Hämta senaste kurs (LatestStockQuote)
      3. Beräkna courtage + totalt
      4. Skapa StockTransaction (append) + Transaction på ISK-kontot
      5. Upsert StockHolding (viktad snittkurs)
    """
    if quantity <= 0:
        raise TradeError("Antal måste vara positivt", code="invalid_quantity")

    acc = _verify_isk_account(scope_session, account_id)

    if require_market_open and not is_market_open(master_session):
        raise TradeError(
            "Börsen är stängd just nu", code="market_closed",
        )

    stock = (
        master_session.query(StockMaster)
        .filter(StockMaster.ticker == ticker, StockMaster.active == 1)
        .first()
    )
    if stock is None:
        raise TradeError(f"Okänd ticker: {ticker}", code="unknown_ticker")

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

    price = Decimal(str(latest.last))
    gross = (price * quantity).quantize(Decimal("0.01"))
    # Utlandshandel: USD-aktier → courtage i USD + valutaväxlingsavgift
    # Används av compute_courtage_breakdown via stock.currency.
    from .courtage import compute_courtage_breakdown
    breakdown = compute_courtage_breakdown(
        gross, currency=stock.currency or "SEK",
    )
    courtage = breakdown.courtage + breakdown.fx_fee
    total = gross + courtage

    cash_balance = _balance_for(scope_session, account_id)
    if cash_balance < total:
        raise TradeError(
            f"Saldot räcker inte (har {cash_balance}, behöver {total})",
            code="insufficient_funds",
        )

    # 1. Skapa Transaction på ISK-kontot för att dra likviden.
    # Beskrivning visar valuta + ev. FX-fee så eleven ser kostnaden.
    fx_note = (
        f" (inkl. {breakdown.fx_fee} {stock.currency} valutaväxling)"
        if breakdown.fx_fee > 0 else ""
    )
    key = f"stockbuy-{account_id}-{ticker}-{quantity}-{price}-{datetime.utcnow().isoformat()}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    cash_tx = Transaction(
        account_id=account_id,
        date=date.today(),
        amount=-total,
        currency=acc.currency or "SEK",
        raw_description=(
            f"Köp {quantity} st {stock.name} @ {price} "
            f"{stock.currency or 'SEK'}{fx_note}"
        ),
        is_transfer=False,
        hash=h,
    )
    scope_session.add(cash_tx)
    scope_session.flush()

    # 2. Skapa StockTransaction
    st = StockTransaction(
        account_id=account_id,
        ticker=ticker,
        side="buy",
        quantity=quantity,
        price=price,
        courtage=courtage,
        total_amount=total,
        realized_pnl=None,
        quote_id=latest.quote_id,
        transaction_id=cash_tx.id,
        student_rationale=student_rationale,
    )
    scope_session.add(st)
    scope_session.flush()

    # 3. Upsert StockHolding med viktad snittkurs
    holding = (
        scope_session.query(StockHolding)
        .filter(
            StockHolding.account_id == account_id,
            StockHolding.ticker == ticker,
        )
        .first()
    )
    if holding is None:
        new_avg = total / quantity
        holding = StockHolding(
            account_id=account_id, ticker=ticker, quantity=quantity,
            avg_cost=new_avg.quantize(Decimal("0.0001")),
            currency=stock.currency,
        )
        scope_session.add(holding)
    else:
        new_total_cost = (
            Decimal(holding.quantity) * Decimal(holding.avg_cost) + total
        )
        new_qty = holding.quantity + quantity
        new_avg = (new_total_cost / new_qty).quantize(Decimal("0.0001"))
        holding.quantity = new_qty
        holding.avg_cost = new_avg
    scope_session.flush()

    return TradeResult(
        transaction_id=st.id,
        side="buy",
        ticker=ticker,
        quantity=quantity,
        price=price,
        courtage=courtage,
        total_amount=total,
        realized_pnl=None,
        holding_quantity_after=holding.quantity,
        holding_avg_cost_after=Decimal(holding.avg_cost),
        cash_balance_after=_balance_for(scope_session, account_id),
    )


def sell_stock(
    *,
    scope_session: Session,
    master_session: Session,
    account_id: int,
    ticker: str,
    quantity: int,
    student_rationale: Optional[str] = None,
    require_market_open: bool = True,
) -> TradeResult:
    """Genomför ett sälj till marknadspris.

    Säljpriset jämförs mot holding.avg_cost för att räkna ut realiserad
    vinst/förlust. Snittkursen ändras inte vid sälj.
    """
    if quantity <= 0:
        raise TradeError("Antal måste vara positivt", code="invalid_quantity")

    acc = _verify_isk_account(scope_session, account_id)

    if require_market_open and not is_market_open(master_session):
        raise TradeError(
            "Börsen är stängd just nu", code="market_closed",
        )

    stock = (
        master_session.query(StockMaster)
        .filter(StockMaster.ticker == ticker, StockMaster.active == 1)
        .first()
    )
    if stock is None:
        raise TradeError(f"Okänd ticker: {ticker}", code="unknown_ticker")

    holding = (
        scope_session.query(StockHolding)
        .filter(
            StockHolding.account_id == account_id,
            StockHolding.ticker == ticker,
        )
        .first()
    )
    if holding is None or holding.quantity < quantity:
        raise TradeError(
            "Du har inte så många aktier", code="insufficient_holding",
        )

    latest = (
        master_session.query(LatestStockQuote)
        .filter(LatestStockQuote.ticker == ticker)
        .first()
    )
    if latest is None:
        raise TradeError("Ingen aktuell kurs", code="no_quote")

    price = Decimal(str(latest.last))
    gross = (price * quantity).quantize(Decimal("0.01"))
    # Sälj: courtage + valutaväxling tas av nettot.
    from .courtage import compute_courtage_breakdown
    breakdown = compute_courtage_breakdown(
        gross, currency=stock.currency or "SEK",
    )
    courtage = breakdown.courtage + breakdown.fx_fee
    net_proceeds = gross - courtage

    realized_pnl = (
        (price - Decimal(holding.avg_cost)) * quantity - courtage
    ).quantize(Decimal("0.01"))

    # 1. Skapa Transaction (positivt — pengar in)
    key = f"stocksell-{account_id}-{ticker}-{quantity}-{price}-{datetime.utcnow().isoformat()}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    cash_tx = Transaction(
        account_id=account_id,
        date=date.today(),
        amount=net_proceeds,
        currency=acc.currency or "SEK",
        raw_description=f"Sälj {quantity} st {stock.name} @ {price}",
        is_transfer=False,
        hash=h,
    )
    scope_session.add(cash_tx)
    scope_session.flush()

    # 2. StockTransaction
    st = StockTransaction(
        account_id=account_id,
        ticker=ticker,
        side="sell",
        quantity=quantity,
        price=price,
        courtage=courtage,
        total_amount=net_proceeds,
        realized_pnl=realized_pnl,
        quote_id=latest.quote_id,
        transaction_id=cash_tx.id,
        student_rationale=student_rationale,
    )
    scope_session.add(st)
    scope_session.flush()

    # 3. Uppdatera holding (radera om kvantitet = 0)
    new_qty = holding.quantity - quantity
    if new_qty == 0:
        scope_session.delete(holding)
        scope_session.flush()
        holding_qty_after = 0
        holding_avg_cost_after: Optional[Decimal] = None
    else:
        holding.quantity = new_qty
        scope_session.flush()
        holding_qty_after = holding.quantity
        holding_avg_cost_after = Decimal(holding.avg_cost)

    return TradeResult(
        transaction_id=st.id,
        side="sell",
        ticker=ticker,
        quantity=quantity,
        price=price,
        courtage=courtage,
        total_amount=net_proceeds,
        realized_pnl=realized_pnl,
        holding_quantity_after=holding_qty_after,
        holding_avg_cost_after=holding_avg_cost_after,
        cash_balance_after=_balance_for(scope_session, account_id),
    )


def get_portfolio(
    *,
    scope_session: Session,
    master_session: Session,
    account_id: Optional[int] = None,
) -> dict:
    """Returnera portföljvärdering: innehav + likvid + total + sektorvikter.

    Om `account_id` ges filtreras till det kontot, annars alla
    ISK-konton."""
    holdings_q = scope_session.query(StockHolding)
    if account_id is not None:
        holdings_q = holdings_q.filter(StockHolding.account_id == account_id)
    holdings = holdings_q.all()

    if not holdings:
        cash = (
            _balance_for(scope_session, account_id)
            if account_id is not None
            else Decimal("0")
        )
        return {
            "holdings": [],
            "total_market_value": 0.0,
            "total_cost_basis": 0.0,
            "unrealized_pnl": 0.0,
            "cash_balance": float(cash),
            "total_value": float(cash),
            "sector_weights": {},
        }

    tickers = {h.ticker for h in holdings}
    latest_map = {
        l.ticker: l
        for l in master_session.query(LatestStockQuote)
        .filter(LatestStockQuote.ticker.in_(tickers))
        .all()
    }
    stock_map = {
        s.ticker: s
        for s in master_session.query(StockMaster)
        .filter(StockMaster.ticker.in_(tickers))
        .all()
    }
    # FX-kurs USD→SEK för USD-aktier. Default 1 om FX-data saknas
    # (t.ex. första gången pollar inte hunnit). I så fall behandlas
    # USD-värden som vore de SEK — UI:n får ändå information.
    from ..school.stock_models import LatestFxRate
    fx_row = (
        master_session.query(LatestFxRate)
        .filter(LatestFxRate.base == "USD", LatestFxRate.quote == "SEK")
        .first()
    )
    usd_to_sek = Decimal(str(fx_row.rate)) if fx_row else Decimal("1")

    out_holdings = []
    total_mv = Decimal("0")  # i SEK
    total_cost = Decimal("0")  # i SEK
    sector_values: dict[str, Decimal] = {}

    for h in holdings:
        latest = latest_map.get(h.ticker)
        last = Decimal(str(latest.last)) if latest else Decimal(h.avg_cost)
        stock = stock_map.get(h.ticker)
        currency = stock.currency if stock else "SEK"
        sector = stock.sector if stock else "Okänd"
        market_value_native = (last * h.quantity).quantize(Decimal("0.01"))
        cost_native = (Decimal(h.avg_cost) * h.quantity).quantize(Decimal("0.01"))
        unrealized_native = (market_value_native - cost_native).quantize(
            Decimal("0.01"),
        )
        # Konvertera till SEK för totalsummering. För SEK-aktier blir det
        # samma värde; för USD-aktier multipliceras med aktuell kurs.
        # cost_basis_sek använder också CURRENT fx — blandas valutarisk
        # in i unrealized_pnl. Pedagogiskt viktigt: man ser den TOTALA
        # P&L i SEK utan att artificiellt dela upp.
        if currency == "USD":
            market_value_sek = (market_value_native * usd_to_sek).quantize(
                Decimal("0.01"),
            )
            cost_sek = (cost_native * usd_to_sek).quantize(Decimal("0.01"))
        else:
            market_value_sek = market_value_native
            cost_sek = cost_native
        unrealized_sek = (market_value_sek - cost_sek).quantize(Decimal("0.01"))
        sector_values[sector] = sector_values.get(sector, Decimal("0")) + market_value_sek
        total_mv += market_value_sek
        total_cost += cost_sek
        out_holdings.append({
            "ticker": h.ticker,
            "quantity": h.quantity,
            "avg_cost": float(h.avg_cost),
            "last_price": float(last),
            "market_value": float(market_value_sek),
            "market_value_native": float(market_value_native),
            "cost_basis": float(cost_sek),
            "cost_basis_native": float(cost_native),
            "unrealized_pnl": float(unrealized_sek),
            "unrealized_pnl_native": float(unrealized_native),
            "currency": currency,
            "sector": sector,
            "account_id": h.account_id,
        })

    cash = (
        _balance_for(scope_session, account_id)
        if account_id is not None
        else Decimal("0")
    )

    sector_weights: dict[str, float] = {}
    if total_mv > 0:
        for k, v in sector_values.items():
            sector_weights[k] = float((v / total_mv) * 100)

    total_value = total_mv + cash
    return {
        "holdings": out_holdings,
        "total_market_value": float(total_mv),
        "total_cost_basis": float(total_cost),
        "unrealized_pnl": float(total_mv - total_cost),
        "cash_balance": float(cash),
        "total_value": float(total_value),
        "sector_weights": sector_weights,
        "fx_usd_sek": float(usd_to_sek) if fx_row else None,
    }
