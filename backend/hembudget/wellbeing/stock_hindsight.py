"""Aktie-eftertanke: 60-dagars hindsight på elevens sälj.

Pedagogiskt syfte: i månadsrapporten ska eleven KONFRONTERAS med
konsekvenserna av sina beslut. Forskningen kring loss aversion +
disposition effect visar att amatörer säljer vinnare för tidigt och
behåller förlorare för länge — vi hjälper eleven se mönstret hos sig
själv.

För varje sälj senaste 30 dagarna räknar vi ut "vad hade hänt om du
väntat 60 dagar" och presenterar det utan att moralisera. Tonen är
"så här ser data ut" — inte "du gjorde fel".

Loss-aversion-kvot: antal sälj med förlust ÷ antal sälj med vinst.
> 2.0 → eleven realiserar förluster oftare än vinster (vanligt mönster).

Lägger sig som en rapport-sektion på dashboard / wellbeing-vyn —
inte i en separat PDF, för att den ska kännas i varje månadsskifte.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# Antal dagar för hindsight-jämförelsen. 60 dagar valt för att
# (a) inte vara så kort att marknadsbrus dominerar
# (b) inte så långt att eleven tappar koppling till sitt beslut
HINDSIGHT_DAYS = 60

# Hur långt tillbaka tittar vi på sälj? 30 dagar = en vanlig "månad".
# Räcker för att månadsrapporten ska ha innehåll utan att överbelasta.
LOOKBACK_DAYS = 30


def _parse_year_month(year_month: Optional[str]) -> tuple[date, date]:
    """Returnerar (start, end_exclusive) för månaden eller senaste 30d."""
    if year_month:
        try:
            y, m = year_month.split("-")
            start = date(int(y), int(m), 1)
            if int(m) == 12:
                end = date(int(y) + 1, 1, 1)
            else:
                end = date(int(y), int(m) + 1, 1)
            return start, end
        except Exception:
            pass
    today = date.today()
    return today - timedelta(days=LOOKBACK_DAYS), today + timedelta(days=1)


def _quote_at(master_session: Session, ticker: str, target_dt: datetime) -> Optional[Decimal]:
    """Hämta kursen närmast `target_dt`. Returnerar None om ingen kurs
    finns inom ±3 dagar (för glesa helger / marknad stängd)."""
    from ..school.stock_models import StockQuote

    window = timedelta(days=3)
    q = (
        master_session.query(StockQuote)
        .filter(
            StockQuote.ticker == ticker,
            StockQuote.ts >= target_dt - window,
            StockQuote.ts <= target_dt + window,
        )
        .order_by(
            # Sortera efter absolut tidsdiff — närmaste först.
            # SQLAlchemy: använd func.abs(extract('epoch', ts - target))
            # men enklare att hämta alla kandidater och välja i Python.
            StockQuote.ts.asc(),
        )
        .all()
    )
    if not q:
        return None
    closest = min(q, key=lambda r: abs((r.ts - target_dt).total_seconds()))
    return Decimal(str(closest.last))


def _latest_quote(master_session: Session, ticker: str) -> Optional[Decimal]:
    from ..school.stock_models import LatestStockQuote

    row = (
        master_session.query(LatestStockQuote)
        .filter(LatestStockQuote.ticker == ticker)
        .first()
    )
    return Decimal(str(row.last)) if row else None


def compute_stock_hindsight(
    scope_session: Session,
    year_month: Optional[str] = None,
) -> dict:
    """Beräkna aktie-eftertanke för en månad (default: senaste 30 dagar).

    Returnerar dict med:
    - month: "YYYY-MM" eller "senaste-30d"
    - sells_count: antal sälj i fönstret
    - sells_in_profit, sells_in_loss
    - loss_aversion_quotient: förluster / vinster (eller None)
    - best_decision: dict med största realiserade vinst (eller None)
    - worst_decision: dict med största realiserade förlust (eller None)
    - hindsight: list per sälj med 60-d-jämförelse
    - explanation: pedagogisk sammanfattning
    """
    from ..db.models import StockTransaction
    from ..school.engines import master_session
    from ..school.stock_models import LatestFxRate, StockMaster

    start, end = _parse_year_month(year_month)
    label = year_month or f"senaste {LOOKBACK_DAYS}d"

    sells = (
        scope_session.query(StockTransaction)
        .filter(
            StockTransaction.side == "sell",
            StockTransaction.executed_at >= datetime.combine(start, datetime.min.time()),
            StockTransaction.executed_at < datetime.combine(end, datetime.min.time()),
        )
        .order_by(StockTransaction.executed_at.asc())
        .all()
    )

    if not sells:
        return {
            "month": label,
            "sells_count": 0,
            "sells_in_profit": 0,
            "sells_in_loss": 0,
            "loss_aversion_quotient": None,
            "best_decision": None,
            "worst_decision": None,
            "hindsight": [],
            "explanation": (
                "Inga aktier såldes denna period — ingen eftertanke att räkna på."
            ),
        }

    # Hämta master-data en gång — sektor, valuta, FX
    tickers = {s.ticker for s in sells}
    try:
        with master_session() as ms:
            stock_map = {
                s.ticker: s for s in ms.query(StockMaster)
                .filter(StockMaster.ticker.in_(tickers)).all()
            }
            fx_row = (
                ms.query(LatestFxRate)
                .filter(LatestFxRate.base == "USD",
                        LatestFxRate.quote == "SEK")
                .first()
            )
            usd_to_sek = Decimal(str(fx_row.rate)) if fx_row else Decimal("1")

            now_dt = datetime.now()
            hindsight_rows: list[dict] = []
            for tx in sells:
                stock = stock_map.get(tx.ticker)
                currency = stock.currency if stock else "SEK"
                fx = usd_to_sek if currency == "USD" else Decimal("1")

                target_dt = tx.executed_at + timedelta(days=HINDSIGHT_DAYS)
                is_complete = target_dt <= now_dt
                if is_complete:
                    hindsight_price = _quote_at(ms, tx.ticker, target_dt)
                else:
                    hindsight_price = _latest_quote(ms, tx.ticker)

                if hindsight_price is None:
                    hindsight_rows.append({
                        "ticker": tx.ticker,
                        "name": (stock.name if stock else tx.ticker),
                        "sold_at": tx.executed_at.date().isoformat(),
                        "sell_price": float(tx.price),
                        "quantity": tx.quantity,
                        "currency": currency,
                        "hindsight_price": None,
                        "hindsight_date": target_dt.date().isoformat(),
                        "is_complete": is_complete,
                        "missed_profit_sek": None,
                        "explanation": (
                            f"Du sålde {tx.quantity} st {tx.ticker} @"
                            f"{float(tx.price):.2f} {currency} "
                            f"{tx.executed_at.date().isoformat()}. "
                            "Ingen kursdata för 60-dagars-jämförelsen."
                        ),
                    })
                    continue

                # Vad hade du fått om du behållit till hindsight-datum?
                # Brutto, ignorerar courtage på det hypotetiska säljet.
                price_diff = hindsight_price - Decimal(str(tx.price))
                missed_native = price_diff * tx.quantity
                missed_sek = (missed_native * fx).quantize(Decimal("0.01"))

                if missed_sek > 0:
                    if is_complete:
                        verb = "missade"
                        tail = f"+{int(missed_sek):,} kr".replace(",", " ")
                    else:
                        verb = "missar (hittills)"
                        tail = f"+{int(missed_sek):,} kr".replace(",", " ")
                    explanation = (
                        f"Du sålde {tx.quantity} st {tx.ticker} @"
                        f"{float(tx.price):.2f} {currency} "
                        f"{tx.executed_at.date().isoformat()}. "
                        f"60 dagar senare står den i {float(hindsight_price):.2f} "
                        f"{currency} — du {verb} {tail} genom att sälja."
                    )
                else:
                    if is_complete:
                        verb = "sparade"
                        tail = f"{int(abs(missed_sek)):,} kr".replace(",", " ")
                    else:
                        verb = "sparar (hittills)"
                        tail = f"{int(abs(missed_sek)):,} kr".replace(",", " ")
                    explanation = (
                        f"Du sålde {tx.quantity} st {tx.ticker} @"
                        f"{float(tx.price):.2f} {currency} "
                        f"{tx.executed_at.date().isoformat()}. "
                        f"60 dagar senare står den i {float(hindsight_price):.2f} "
                        f"{currency} — du {verb} {tail} genom att sälja i tid."
                    )

                hindsight_rows.append({
                    "ticker": tx.ticker,
                    "name": (stock.name if stock else tx.ticker),
                    "sold_at": tx.executed_at.date().isoformat(),
                    "sell_price": float(tx.price),
                    "quantity": tx.quantity,
                    "currency": currency,
                    "hindsight_price": float(hindsight_price),
                    "hindsight_date": target_dt.date().isoformat(),
                    "is_complete": is_complete,
                    "missed_profit_sek": float(missed_sek),
                    "explanation": explanation,
                })
    except Exception:
        log.exception("compute_stock_hindsight: master-session fail")
        return {
            "month": label,
            "sells_count": len(sells),
            "sells_in_profit": 0,
            "sells_in_loss": 0,
            "loss_aversion_quotient": None,
            "best_decision": None,
            "worst_decision": None,
            "hindsight": [],
            "explanation": "Kunde inte räkna eftertanke — kursdata otillgänglig.",
        }

    # Best/worst REALISERAD P&L (det eleven faktiskt fick).
    sells_with_pnl = [s for s in sells if s.realized_pnl is not None]
    sells_in_profit = sum(1 for s in sells_with_pnl if s.realized_pnl > 0)
    sells_in_loss = sum(1 for s in sells_with_pnl if s.realized_pnl < 0)

    best = None
    worst = None
    if sells_with_pnl:
        best_tx = max(sells_with_pnl, key=lambda s: s.realized_pnl)
        worst_tx = min(sells_with_pnl, key=lambda s: s.realized_pnl)
        best = _decision_dict(best_tx, stock_map)
        worst = _decision_dict(worst_tx, stock_map)

    laq: Optional[float] = None
    if sells_in_profit > 0:
        laq = round(sells_in_loss / sells_in_profit, 2)
    elif sells_in_loss > 0:
        # Bara förluster — oändlig kvot, men markera den som "inf" för UI
        laq = float("inf")

    explanation_parts = [
        f"{len(sells)} sälj denna period."
    ]
    if sells_in_profit + sells_in_loss > 0:
        explanation_parts.append(
            f"{sells_in_profit} med vinst, {sells_in_loss} med förlust."
        )
    if laq is not None and laq != float("inf"):
        if laq >= 2:
            explanation_parts.append(
                f"Du realiserar förluster {laq:.1f}× oftare än vinster — "
                "vanligt mönster när loss aversion påverkar besluten "
                "(håller på förlorare, tar hem vinnare för tidigt)."
            )
        elif laq < 0.5:
            explanation_parts.append(
                f"Du tar hem vinster {1/laq:.1f}× oftare än förluster — "
                "kontrollerad linje, men kolla att du inte sitter på "
                "förlorare som borde säljas."
            )

    completed_hindsight = [h for h in hindsight_rows if h["is_complete"]
                           and h["missed_profit_sek"] is not None]
    if completed_hindsight:
        total_missed = sum(h["missed_profit_sek"] for h in completed_hindsight)
        if total_missed > 0:
            explanation_parts.append(
                f"Hade du väntat 60 dagar med dessa sälj hade du fått "
                f"{int(total_missed):,} kr till.".replace(",", " ")
            )
        elif total_missed < 0:
            explanation_parts.append(
                f"Hade du väntat 60 dagar hade du istället förlorat "
                f"{int(abs(total_missed)):,} kr — bra timing.".replace(",", " ")
            )

    return {
        "month": label,
        "sells_count": len(sells),
        "sells_in_profit": sells_in_profit,
        "sells_in_loss": sells_in_loss,
        "loss_aversion_quotient": (
            None if laq is None else (
                "inf" if laq == float("inf") else laq
            )
        ),
        "best_decision": best,
        "worst_decision": worst,
        "hindsight": hindsight_rows,
        "explanation": " ".join(explanation_parts),
        "hindsight_days": HINDSIGHT_DAYS,
    }


def _decision_dict(tx, stock_map: dict) -> dict:
    stock = stock_map.get(tx.ticker)
    currency = stock.currency if stock else "SEK"
    name = stock.name if stock else tx.ticker
    pnl = float(tx.realized_pnl) if tx.realized_pnl is not None else 0.0
    if pnl >= 0:
        verb = "vinst"
    else:
        verb = "förlust"
    return {
        "ticker": tx.ticker,
        "name": name,
        "quantity": tx.quantity,
        "sell_price": float(tx.price),
        "currency": currency,
        "realized_pnl_sek": pnl,
        "sold_at": tx.executed_at.date().isoformat(),
        "explanation": (
            f"Du sålde {tx.quantity} st {tx.ticker} @"
            f"{float(tx.price):.2f} {currency} "
            f"{tx.executed_at.date().isoformat()} — realiserad {verb}: "
            f"{int(pnl):+,} kr.".replace(",", " ")
        ),
    }
