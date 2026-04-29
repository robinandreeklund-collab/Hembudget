"""Realtids-påverkan på Wellbeing.Trygghet från aktieportföljen.

Pedagogiskt syfte: eleven SKA känna ekonomisk oro när portföljen rasar
— det är hela poängen med övningen. Vi modellerar Kahneman/Tversky's
prospect theory: förluster gör ungefär 2× så ont som motsvarande vinster
känns bra (loss aversion, λ ≈ 2.0). Eleven får uppleva fenomenet på
riktigt istället för att bara läsa om det.

Påverkar BARA Trygghet-dimensionen i Wellbeing-räkningen. Realiserade
kassaflöden (sälj som blev till likvid) hanteras separat av vanlig
wellbeing-logik via Ekonomi-dimensionen.

Källa: Tversky & Kahneman 1992, "Advances in Prospect Theory: Cumulative
Representation of Uncertainty". Empiri ger λ mellan 1.5 och 2.5; vi tar
ett rakt 2.0 — pedagogiskt rent.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from .calculator import WellbeingFactor

log = logging.getLogger(__name__)

# Loss-aversion-koefficient (Kahneman/Tversky). Förluster räknas λ× så
# hårt som vinster — empirisk litteratur ger 1.5–2.5, vi väljer 2.0.
LOSS_AVERSION = 2.0

# Skalfaktor: % portföljrörelse → Trygghet-poäng.
# Exempel: -10 % drop × λ=2.0 = -20 % effektiv × 0.5 = -10 p (innan cap
# och concentration-justering). Räcker för en kännbar reaktion utan att
# rasera hela scoren på en dålig dag.
PCT_TO_POINTS = 0.5

# Koncentration: om en enskild post väger > 40 % av portföljen så
# förstärks reaktionen. Pedagogiskt: "alla ägg i en korg" ÄR farligare.
CONCENTRATION_THRESHOLD = 0.4
CONCENTRATION_MULTIPLIER = 1.5

# Asymmetrisk cap — Trygghet kan tappa upp till 20 p på en katastrofdag,
# men vinna max 10 p på en bra. Speglar verkligheten: marknadsuppgångar
# är förväntade, krascher är chocker.
MAX_NEGATIVE_IMPACT = -20
MAX_POSITIVE_IMPACT = 10


def compute_portfolio_impact(scope_session: Session) -> list:
    """Beräkna Trygghet-påverkan från senaste 24h portföljrörelse.

    Returnerar lista av WellbeingFactor (dimension="safety"). Tom lista
    om eleven inte äger några aktier eller om kursdata saknas.

    Räknas live — ingen persistans. Anropas från calculate_wellbeing.
    """
    # Lazy import — undvik cirkulär (calculator → portfolio_impact → ...)
    from .calculator import WellbeingFactor
    from ..db.models import StockHolding
    from ..school.engines import master_session
    from ..school.stock_models import LatestFxRate, LatestStockQuote, StockMaster

    holdings = scope_session.query(StockHolding).all()
    if not holdings:
        return []

    tickers = {h.ticker for h in holdings}
    try:
        with master_session() as ms:
            latest_map = {
                lq.ticker: lq for lq in ms.query(LatestStockQuote)
                .filter(LatestStockQuote.ticker.in_(tickers)).all()
            }
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
    except Exception:
        log.exception("portfolio_impact: master-session misslyckades — hoppar över")
        return []

    # Bygg per-innehav-data: marknadsvärde i SEK + dagens % rörelse.
    per_holding: list[dict] = []
    total_value = Decimal("0")
    for h in holdings:
        latest = latest_map.get(h.ticker)
        if latest is None:
            continue  # ingen kurs → kan inte räkna
        stock = stock_map.get(h.ticker)
        currency = stock.currency if stock else "SEK"
        last_price = Decimal(str(latest.last))
        market_native = last_price * h.quantity
        market_sek = (
            market_native * usd_to_sek if currency == "USD" else market_native
        )
        change_pct = (
            float(latest.change_pct) if latest.change_pct is not None else 0.0
        )
        per_holding.append({
            "ticker": h.ticker,
            "name": (stock.name if stock else h.ticker),
            "value_sek": market_sek,
            "change_pct": change_pct,
        })
        total_value += market_sek

    if total_value <= 0 or not per_holding:
        return []

    # Viktad portfölj-rörelse + största enskild vikt (för concentration).
    weighted_pct = 0.0
    max_weight = 0.0
    max_weight_ticker = ""
    for p in per_holding:
        w = float(p["value_sek"] / total_value)
        weighted_pct += w * p["change_pct"]
        if w > max_weight:
            max_weight = w
            max_weight_ticker = p["ticker"]

    concentrated = max_weight > CONCENTRATION_THRESHOLD

    # Loss aversion appliceras BARA på portföljnivå, inte per ticker —
    # vi vill att eleven ser nettoeffekten, inte räknar matematik.
    if weighted_pct < 0:
        effective_pct = weighted_pct * LOSS_AVERSION
    else:
        effective_pct = weighted_pct

    raw_impact = effective_pct * PCT_TO_POINTS
    if concentrated:
        raw_impact *= CONCENTRATION_MULTIPLIER

    impact = int(round(raw_impact))
    impact = max(MAX_NEGATIVE_IMPACT, min(MAX_POSITIVE_IMPACT, impact))

    if impact == 0:
        # Liten rörelse — ingen pedagogisk poäng att rapportera 0.
        return []

    # Plocka topp-3 bidragsgivare för pedagogisk transparens i UI:t.
    contribs = sorted(
        per_holding,
        key=lambda p: abs(
            float(p["value_sek"] / total_value) * p["change_pct"]
        ),
        reverse=True,
    )[:3]

    detail_parts: list[str] = []
    for c in contribs:
        w = float(c["value_sek"] / total_value)
        ch = c["change_pct"]
        detail_parts.append(f"{c['ticker']} {ch:+.1f}% × {w*100:.0f}% vikt")

    if weighted_pct < 0:
        text = (
            f"Portföljen {weighted_pct:+.1f}% senaste 24h × λ={LOSS_AVERSION:.1f} "
            "(loss aversion: förluster känns ~2× starkare än vinster). "
        )
    else:
        text = f"Portföljen {weighted_pct:+.1f}% senaste 24h. "
    text += "Topp-bidrag: " + ", ".join(detail_parts) + "."
    if concentrated:
        text += (
            f" {max_weight_ticker} väger {max_weight*100:.0f}% — koncentration "
            "förstärker reaktionen 1.5×."
        )

    return [WellbeingFactor("safety", impact, text)]


def compute_portfolio_impact_summary(scope_session: Session) -> dict:
    """Detaljerad portfölj-impact-rapport för UI-kort på /investments.

    Returnerar dict med:
    - total_value_sek: portföljens totala värde
    - weighted_pct: viktad 24h-rörelse i %
    - effective_pct: efter loss aversion
    - safety_impact: poäng-effekt på Trygghet (-20..+10)
    - concentration: True om största post > 40%
    - max_weight: största viktningen (0..1)
    - max_weight_ticker: vilken ticker
    - holdings: lista av {ticker, name, weight, change_pct, contribution}
    - explanation: pedagogisk text

    Tom dict om inga innehav. Används i frontend för att visa "live"-
    påverkan utan att räkna om hela Wellbeing-scoren.
    """
    from ..db.models import StockHolding
    from ..school.engines import master_session
    from ..school.stock_models import LatestFxRate, LatestStockQuote, StockMaster

    holdings = scope_session.query(StockHolding).all()
    if not holdings:
        return {
            "has_holdings": False,
            "total_value_sek": 0,
            "weighted_pct": 0.0,
            "effective_pct": 0.0,
            "safety_impact": 0,
            "concentration": False,
            "max_weight": 0.0,
            "max_weight_ticker": "",
            "holdings": [],
            "explanation": "Du äger inga aktier än — Trygghet påverkas inte.",
        }

    tickers = {h.ticker for h in holdings}
    try:
        with master_session() as ms:
            latest_map = {
                lq.ticker: lq for lq in ms.query(LatestStockQuote)
                .filter(LatestStockQuote.ticker.in_(tickers)).all()
            }
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
    except Exception:
        log.exception("portfolio_impact_summary: master-session fail")
        return {
            "has_holdings": True,
            "total_value_sek": 0,
            "weighted_pct": 0.0,
            "effective_pct": 0.0,
            "safety_impact": 0,
            "concentration": False,
            "max_weight": 0.0,
            "max_weight_ticker": "",
            "holdings": [],
            "explanation": "Kunde inte hämta kursdata just nu.",
        }

    rows: list[dict] = []
    total_value = Decimal("0")
    for h in holdings:
        latest = latest_map.get(h.ticker)
        if latest is None:
            continue
        stock = stock_map.get(h.ticker)
        currency = stock.currency if stock else "SEK"
        last_price = Decimal(str(latest.last))
        market_native = last_price * h.quantity
        market_sek = (
            market_native * usd_to_sek if currency == "USD" else market_native
        )
        change_pct = (
            float(latest.change_pct) if latest.change_pct is not None else 0.0
        )
        rows.append({
            "ticker": h.ticker,
            "name": (stock.name if stock else h.ticker),
            "value_sek": market_sek,
            "change_pct": change_pct,
        })
        total_value += market_sek

    if total_value <= 0 or not rows:
        return {
            "has_holdings": True,
            "total_value_sek": float(total_value),
            "weighted_pct": 0.0,
            "effective_pct": 0.0,
            "safety_impact": 0,
            "concentration": False,
            "max_weight": 0.0,
            "max_weight_ticker": "",
            "holdings": [],
            "explanation": "Inga aktuella kurser — kan inte räkna påverkan just nu.",
        }

    weighted_pct = 0.0
    max_weight = 0.0
    max_weight_ticker = ""
    holdings_out: list[dict] = []
    for r in rows:
        w = float(r["value_sek"] / total_value)
        contribution = w * r["change_pct"]
        weighted_pct += contribution
        if w > max_weight:
            max_weight = w
            max_weight_ticker = r["ticker"]
        holdings_out.append({
            "ticker": r["ticker"],
            "name": r["name"],
            "weight": round(w, 4),
            "change_pct": round(r["change_pct"], 2),
            "contribution_pct": round(contribution, 3),
        })

    concentrated = max_weight > CONCENTRATION_THRESHOLD
    if weighted_pct < 0:
        effective_pct = weighted_pct * LOSS_AVERSION
    else:
        effective_pct = weighted_pct
    raw_impact = effective_pct * PCT_TO_POINTS
    if concentrated:
        raw_impact *= CONCENTRATION_MULTIPLIER
    safety_impact = max(
        MAX_NEGATIVE_IMPACT, min(MAX_POSITIVE_IMPACT, int(round(raw_impact)))
    )

    if weighted_pct < -0.1:
        explanation = (
            f"Portföljen rör sig {weighted_pct:+.2f}% senaste 24h. "
            f"Med loss aversion (λ={LOSS_AVERSION:.1f}) känns det som "
            f"{effective_pct:+.2f}% — Trygghet justeras {safety_impact:+d} p."
        )
    elif weighted_pct > 0.1:
        explanation = (
            f"Portföljen rör sig {weighted_pct:+.2f}% senaste 24h. "
            f"Trygghet justeras {safety_impact:+d} p."
        )
    else:
        explanation = (
            f"Portföljen rör sig {weighted_pct:+.2f}% senaste 24h "
            "— för litet för att påverka Trygghet."
        )
    if concentrated:
        explanation += (
            f" {max_weight_ticker} väger {max_weight*100:.0f}% av portföljen — "
            "alla ägg i en korg förstärker effekten."
        )

    holdings_out.sort(key=lambda h: -abs(h["contribution_pct"]))

    return {
        "has_holdings": True,
        "total_value_sek": float(total_value),
        "weighted_pct": round(weighted_pct, 3),
        "effective_pct": round(effective_pct, 3),
        "safety_impact": safety_impact,
        "concentration": concentrated,
        "max_weight": round(max_weight, 4),
        "max_weight_ticker": max_weight_ticker,
        "holdings": holdings_out,
        "explanation": explanation,
        "loss_aversion": LOSS_AVERSION,
    }
