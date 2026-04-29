"""Courtage-beräkning enligt valbar modell.

Avanza Mini-courtage är default: 1 kr fast minimi + 0,25 % av belopp
över 400 kr (minimi gäller för affärer upp till ~400 kr).

Utlandshandel (USA-aktier i USD):
- Minicourtage: 1 USD minimi + 0,25 % av belopp i USD
- Valutaväxlingsavgift: 0,25 % växlingspålägg på köpbeloppet
  (Avanzas standard) — pedagogiskt viktigt: kostar mer att handla
  utomlands även om mäklarcourtaget verkar lika
- Vi exponerar separat 'fx_fee' så frontend kan förklara

Andra modeller:
- "start": 39 kr fast (för pedagogisk demo av högre minimicourtage)
- "none": 0 kr (övningsläge utan friction)
"""
from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP
from typing import NamedTuple


PCT_MINI = Decimal("0.0025")  # 0,25 %
MIN_MINI_SEK = Decimal("1.00")
MIN_MINI_USD = Decimal("1.00")  # 1 USD ≈ 10 kr
FIXED_START = Decimal("39.00")
# Valutaväxlingsavgift: 0,25 % pålägg utöver mid-rate (Avanzas standard
# på Mini-erbjudanden). Tas på affärsbeloppet vid USD-affär, både köp
# och sälj. Pedagogiskt viktigt — annars verkar utlandshandel "gratis".
FX_FEE_PCT = Decimal("0.0025")


class CourtageBreakdown(NamedTuple):
    """Detaljerad uppdelning av handelskostnader. Kept synligt så
    eleven ser exakt vad varje krona går till."""
    courtage: Decimal       # mäklarcourtage i affärsvalutan
    fx_fee: Decimal         # valutaväxlingspålägg i affärsvalutan
    total_fee: Decimal      # courtage + fx_fee
    currency: str           # "SEK" eller "USD"


def compute_courtage(amount: Decimal, model: str | None = None) -> Decimal:
    """Returnera courtage-beloppet i kr för en given affärsbelopp.

    Bakåtkompat: returnerar bara mäklarcourtage utan FX. För komplett
    uppdelning av utlandshandel använd compute_courtage_breakdown().
    """
    if amount <= 0:
        return Decimal("0.00")
    model = (
        model
        or os.environ.get("HEMBUDGET_COURTAGE_MODEL", "mini")
    ).lower().strip()

    if model == "none":
        return Decimal("0.00")
    if model == "start":
        return FIXED_START

    # Default: mini
    pct_amount = (amount * PCT_MINI).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
    return max(MIN_MINI_SEK, pct_amount)


def compute_courtage_breakdown(
    amount: Decimal,
    *,
    currency: str = "SEK",
    model: str | None = None,
) -> CourtageBreakdown:
    """Beräkna courtage + ev. valutaväxlingsavgift för en affär.

    amount är i affärsvalutan (SEK för svenska aktier, USD för US).

    SEK-affär: bara mäklarcourtage (ingen FX-fee).
    USD-affär: mäklarcourtage 0.25 % min 1 USD + valutaväxlingsavgift
    0.25 % av amount.
    """
    if amount <= 0:
        return CourtageBreakdown(
            Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), currency,
        )
    model = (
        model
        or os.environ.get("HEMBUDGET_COURTAGE_MODEL", "mini")
    ).lower().strip()

    if model == "none":
        return CourtageBreakdown(
            Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), currency,
        )
    if model == "start":
        return CourtageBreakdown(
            FIXED_START, Decimal("0.00"), FIXED_START, currency,
        )

    # Default: mini
    pct_amount = (amount * PCT_MINI).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
    minimum = MIN_MINI_USD if currency == "USD" else MIN_MINI_SEK
    courtage = max(minimum, pct_amount)
    if currency == "USD":
        fx_fee = (amount * FX_FEE_PCT).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
    else:
        fx_fee = Decimal("0.00")
    return CourtageBreakdown(
        courtage=courtage,
        fx_fee=fx_fee,
        total_fee=courtage + fx_fee,
        currency=currency,
    )
