"""Acceptansmodell · P(accept) = sigmoid(...) deterministisk.

Spec: deb/README.md avsnitt 5.1.

Inga LLM-anrop. Eleven måste kunna räkna ut sambandet, läraren måste
kunna förklara varför kunden tackade nej. Bara *innehåll* (jobbeskrivning,
pitch-bedömning) får komma från LLM.

Vikter (w1..w5) är kalibrerade så att:
- En offert exakt på riktpris med rep=50, ingen pitch-bonus → ~50 % accept
- Offert 30 % billigare → ~85 %
- Offert 30 % dyrare → ~15 %
- Hög pitch-kvalitet (0.9) lägger på ~10 %
- Långsam leverans (3x längre än förväntat) drar bort ~25 %
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass


# === Vikter ===

W_PRICE = 4.5         # Priskänslighet · stort utrymme runt riktpriset
W_REPUTATION = 0.025  # Rykte 0..100 → max +2.5 i logits
W_MARKETING = 0.5     # Aktiv kampanj-effekt
W_PITCH = 1.5         # AI-bedömd pitch_quality 0..1 → max +1.5
W_DELAY = 1.2         # Leveranstid-avvikelse (× expected) → straffas


@dataclass
class AcceptanceInput:
    market_price: int
    offered_price: int
    reputation: int                  # 0..100
    marketing_boost: float           # 0..1 (1 = full kampanjeffekt)
    pitch_quality: float | None      # 0..1 från AI · None = neutral 0.5
    expected_delivery_days: int
    offered_delivery_days: int
    customer_price_sensitivity: float    # 0..1
    customer_quality_sensitivity: float  # 0..1


@dataclass
class AcceptanceResult:
    probability: float       # 0..1 efter sigmoid
    accepted: bool
    explanation: str         # Pedagogisk motivering
    contributions: dict[str, float]  # Per-faktor-bidrag i logits


def _sigmoid(x: float) -> float:
    if x > 50:
        return 1.0
    if x < -50:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def evaluate_quote(
    inp: AcceptanceInput, *, seed: int,
) -> AcceptanceResult:
    """Räkna sannolikhet att kunden accepterar offerten + slå tärning.

    Seed:as deterministiskt så samma input ger samma utfall (för
    re-spelning av en vecka).
    """
    # Pris-bidrag — symmetri runt riktpris, skalas av kundens priskänslighet
    price_diff_ratio = (
        (inp.market_price - inp.offered_price) / max(inp.market_price, 1)
    )
    price_term = (
        W_PRICE
        * price_diff_ratio
        * (0.5 + inp.customer_price_sensitivity)  # max 1.5x för supersensitive
    )

    # Rykte-bidrag · centrerat på 50 (medel)
    reputation_term = W_REPUTATION * (inp.reputation - 50)

    # Marknadsföring-bidrag
    marketing_term = W_MARKETING * inp.marketing_boost

    # Pitch-bidrag · skalas av kundens kvalitetskänslighet
    pq = 0.5 if inp.pitch_quality is None else inp.pitch_quality
    pitch_term = (
        W_PITCH
        * (pq - 0.5)
        * (0.5 + inp.customer_quality_sensitivity)
    )

    # Leveranstid-avvikelse · bara straff vid längre tid än förväntat
    delay_ratio = max(
        0.0,
        (inp.offered_delivery_days - inp.expected_delivery_days)
        / max(inp.expected_delivery_days, 1),
    )
    delay_term = -W_DELAY * delay_ratio

    logits = (
        price_term + reputation_term + marketing_term + pitch_term
        + delay_term
    )
    p = _sigmoid(logits)

    rng = random.Random(seed)
    rnd = rng.random()
    accepted = rnd < p

    expl = _explain(
        inp=inp, p=p,
        price_term=price_term,
        reputation_term=reputation_term,
        marketing_term=marketing_term,
        pitch_term=pitch_term,
        delay_term=delay_term,
        accepted=accepted,
    )

    return AcceptanceResult(
        probability=p,
        accepted=accepted,
        explanation=expl,
        contributions={
            "price": round(price_term, 3),
            "reputation": round(reputation_term, 3),
            "marketing": round(marketing_term, 3),
            "pitch": round(pitch_term, 3),
            "delay": round(delay_term, 3),
            "total_logits": round(logits, 3),
        },
    )


def _explain(
    *, inp: AcceptanceInput, p: float,
    price_term: float, reputation_term: float, marketing_term: float,
    pitch_term: float, delay_term: float, accepted: bool,
) -> str:
    """Bygg en pedagogisk klartext-motivering."""
    parts: list[str] = []

    # Pris
    diff = inp.offered_price - inp.market_price
    if diff <= -inp.market_price * 0.1:
        parts.append(
            f"Priset ({inp.offered_price} kr) är klart under riktpris "
            f"({inp.market_price} kr) — det gör kunden nyfiken."
        )
    elif diff <= 0:
        parts.append(
            f"Priset ({inp.offered_price} kr) är något under riktpris "
            f"({inp.market_price} kr) — rimligt."
        )
    elif diff <= inp.market_price * 0.1:
        parts.append(
            f"Priset ({inp.offered_price} kr) är något över riktpris "
            f"({inp.market_price} kr) — kunden tvekar."
        )
    else:
        parts.append(
            f"Priset ({inp.offered_price} kr) är högre än kunden räknat med "
            f"(marknad: {inp.market_price} kr) — ett tufft pris."
        )

    # Rykte
    if inp.reputation >= 70:
        parts.append("Ditt goda rykte spelar roll.")
    elif inp.reputation <= 30:
        parts.append("Lågt rykte gör kunden försiktig.")

    # Pitch
    if inp.pitch_quality is not None:
        if inp.pitch_quality >= 0.75:
            parts.append("Pitchen träffade rätt.")
        elif inp.pitch_quality <= 0.35:
            parts.append("Pitchen var inte övertygande.")

    # Marknadsföring
    if inp.marketing_boost >= 0.6:
        parts.append("Pågående marknadsföring gör att de hört talas om er.")

    # Leverans
    if inp.offered_delivery_days > inp.expected_delivery_days * 1.5:
        parts.append(
            f"Leveranstiden ({inp.offered_delivery_days} dagar) är för lång — "
            f"kunden tänkte sig {inp.expected_delivery_days} dagar."
        )

    head = (
        f"Kunden TACKADE JA ({int(p*100)}% chans att lyckas)."
        if accepted
        else f"Kunden TACKADE NEJ ({int(p*100)}% chans att lyckas)."
    )
    return head + " " + " ".join(parts)
