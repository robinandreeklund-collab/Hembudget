"""Pris-modul · marknadsmässigt riktpris per (jobbmall, kundtyp).

Kunden beräknar sitt "riktpris" baserat på jobbmallens base_price +
segment-justering. Detta är vad eleven jämförs mot i acceptansmodellen.
"""
from __future__ import annotations

from .seed_data import CustomerSeed, JobTemplate


# Segment-multiplikatorer på base_price (1.0 = privat, baseline)
SEGMENT_PRICE_FACTOR: dict[str, float] = {
    "privat": 1.0,
    "foretag": 1.2,   # företag har högre budget
    "kommun": 1.4,    # kommun har upphandlade priser men accepterar högre
}


def market_price_for(
    template: JobTemplate, customer: CustomerSeed,
) -> int:
    """Returnera marknadsmässigt riktpris för (mall, kund).

    Multiplicera template.base_price med segment-faktor. Avrunda till
    närmaste 100 kr för pedagogisk klarhet.
    """
    factor = SEGMENT_PRICE_FACTOR.get(customer.segment, 1.0)
    raw = template.base_price * factor
    return int(round(raw / 100) * 100)
