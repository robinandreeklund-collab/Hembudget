"""Courtage-beräkning enligt valbar modell.

Avanza Mini-courtage är default: 1 kr fast minimi + 0,25 % av belopp
över 400 kr (minimi gäller för affärer upp till ~400 kr).

Andra modeller:
- "start": 39 kr fast (för pedagogisk demo av högre minimicourtage)
- "none": 0 kr (övningsläge utan friction)

Modell väljs via env-var `HEMBUDGET_COURTAGE_MODEL` (default `mini`).
"""
from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP


PCT_MINI = Decimal("0.0025")  # 0,25 %
MIN_MINI = Decimal("1.00")
FIXED_START = Decimal("39.00")


def compute_courtage(amount: Decimal, model: str | None = None) -> Decimal:
    """Returnera courtage-beloppet i kr för en given affärsbelopp.

    `amount` ska vara positivt — för köp och sälj är det quantity*price,
    courtage adderas vid köp och dras av vid sälj utöver detta.
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
    return max(MIN_MINI, pct_amount)
