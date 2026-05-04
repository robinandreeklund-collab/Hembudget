"""BizDifficultyProfile · basics vs advanced.

Spec: deb/README.md avsnitt 3 ("Två svårighetsnivåer i en och samma
simulator").

basics  → ÄK1 / Entreprenörskap · färre jobb/v, enklare kunder,
          inga oväntade händelser, manuell stega-vecka, ingen
          dubbel bokföring, ingen avstämning, inga nyckeltal
advanced → ÄK2 · fler jobb/v, mer priskänsliga kunder,
           slumpevents (klagomål, datorn-gick-sönder, miljöskatt),
           dubbel bokföring tillgänglig, bankavstämning, nyckeltal,
           peer-revision

Analog med game_engine/difficulty.py för privatmotorn.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BizDifficultyProfile:
    level: str  # basics | advanced

    # Pipeline
    base_opportunities_per_week: int
    market_price_volatility: float  # ±% av riktpris

    # Kund
    customer_price_pressure_mult: float  # multiplicerar customer.price_sensitivity

    # Slumpevents
    event_probability_per_week: float    # 0..1
    max_events_per_week: int

    # Acceptansmodell
    acceptance_threshold_shift: float    # negativt = svårare

    # AI-användning
    ai_enabled_default: bool

    @property
    def label(self) -> str:
        return {
            "basics": "Företagsekonomi 1 (grund)",
            "advanced": "Företagsekonomi 2 (fördjupning)",
        }.get(self.level, self.level)


BASICS = BizDifficultyProfile(
    level="basics",
    base_opportunities_per_week=2,
    market_price_volatility=0.05,
    customer_price_pressure_mult=0.8,    # mindre priskänslig
    event_probability_per_week=0.0,       # inga oväntade händelser
    max_events_per_week=0,
    acceptance_threshold_shift=0.5,       # +0.5 logits = mildare
    ai_enabled_default=True,
)

ADVANCED = BizDifficultyProfile(
    level="advanced",
    base_opportunities_per_week=3,
    market_price_volatility=0.15,
    customer_price_pressure_mult=1.2,    # mer priskänslig
    event_probability_per_week=0.4,       # en händelse var 2-3 vecka
    max_events_per_week=2,
    acceptance_threshold_shift=-0.3,
    ai_enabled_default=True,
)


def get_biz_difficulty(level: str) -> BizDifficultyProfile:
    """Returnera profil för en nivå. Default basics om okänd."""
    if level == "advanced":
        return ADVANCED
    return BASICS
