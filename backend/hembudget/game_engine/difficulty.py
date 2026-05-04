"""Difficulty-konfiguration · per-nivå multiplikatorer.

Spec: dev/game-motor/09-difficulty-levels.md + Fas 8b kalibrering

Nivåerna styr **utmaningsnivån** — inte det grundläggande ekonomiska
realismen. En lärare väljer nivå 1 för 7:e-klassare som lär sig grunder,
nivå 3 för 9:e-klassare som ska få "vuxen-livets pressfunktion".

Designmål för end-of-year-balans efter 12 mån:

  Nivå 1 (Sparsam start)
    sparsam:    90-95 % positiv  (lätt att lyckas om man försöker)
    balanserad: 80-90 % positiv  (de flesta klarar sig)
    slosa:      75-85 % positiv  (varje 4-5:e elev hamnar i marginal)

  Nivå 2 (Balanserad)
    sparsam:    80-90 % positiv  (man måste fortfarande tänka)
    balanserad: 60-70 % positiv  (medelelev hamnar i marginalen)
    slosa:      45-55 % positiv  (slumpmässighet biter)

  Nivå 3 (Vuxen-press)
    sparsam:    55-65 % positiv  (även ärliga försök kan misslyckas)
    balanserad: 40-50 % positiv  (Sverige 2026 är inte gratis)
    slosa:      25-35 % positiv  (oansvarig livsstil = skuldfälla)

Kalibreringen sker iterativt via Monte Carlo (10k sims/cell).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DifficultyProfile:
    """Multiplikatorer som styr svårighetsgrad utan att bryta realism.

    Alla värden multipliceras på baseline från respektive motor:
    - 1.0 = neutral (ingen effekt)
    - >1.0 = mer/dyrare
    - <1.0 = mindre/billigare
    """

    # === Event Engine ===
    event_frequency_mult: float = 1.0
    """Multiplikator på frequency_per_year per template. Nivå 3 ger
    1.5-2x oftare events. Påverkar både kostnads- och inkomst-events
    proportionellt så fördelningen behålls."""

    event_cost_mult: float = 1.0
    """Multiplikator på cost_range för UTGIFTS-events (positiva cost).
    Nivå 3 = dyrare tandläkare/vattenskada. Inkomst-events oförändrade."""

    max_events_per_month: int = 3
    """Cap på antal events per månad efter slumpning. Nivå 3 = 4 (mer rörigt)."""

    # === Health Engine ===
    sick_probability_mult: float = 1.0
    """Multiplikator på P_SICK_PER_MONTH_BASELINE. Nivå 3 = 1.5x oftare sjuk."""

    long_sick_probability_mult: float = 1.0
    """Multiplikator på P_LONG_SICK (chans att en sjukperiod blir lång).
    Nivå 3 = 2.5-3x oftare lång (utbrändhet)."""

    vab_probability_mult: float = 1.0
    """Multiplikator på P_VAB_PER_CHILD_PER_MONTH. Nivå 3 = 1.3x mer VAB."""

    # === Variable Expenses ===
    variable_spend_extra_mult: float = 1.0
    """Extra ovanpå spend_profile-multipliern. Nivå 3 betyder att även
    'sparsam' har lite svårare att hålla budget pga oförutsedda småköp."""

    # === Profile Generator (initial) ===
    initial_savings_buffer_mult: float = 1.0
    """Hur stor öppningsbuffer eleven har. Nivå 3 = mindre marginal från start."""

    # === Spend-profile-spread ===
    spend_profile_amplifier: float = 1.0
    """Förstärker SPEND_MULTIPLIER-spreaden på högre nivåer.
    1.0 = neutral (sparsam=0.85, balanserad=1.00, slosa=1.25).
    1.5 = 1.5x avstånd från balanserad (sparsam=0.775, slosa=1.375).
    Slösa-elever straffas mer på högre nivåer pga vidare spread."""


# === KALIBRERADE PROFILER (Fas 8b · efter MC-iteration) ===

DIFFICULTY_PROFILES: dict[int, DifficultyProfile] = {
    1: DifficultyProfile(
        event_frequency_mult=1.25,
        event_cost_mult=1.18,
        max_events_per_month=2,
        sick_probability_mult=0.9,
        long_sick_probability_mult=0.6,
        vab_probability_mult=0.9,
        variable_spend_extra_mult=1.07,
        initial_savings_buffer_mult=1.2,
        spend_profile_amplifier=1.3,
    ),
    2: DifficultyProfile(
        event_frequency_mult=1.85,
        event_cost_mult=1.55,
        max_events_per_month=4,
        sick_probability_mult=1.4,
        long_sick_probability_mult=2.2,
        vab_probability_mult=1.1,
        variable_spend_extra_mult=1.13,
        initial_savings_buffer_mult=1.0,
        spend_profile_amplifier=2.5,
    ),
    3: DifficultyProfile(
        event_frequency_mult=2.4,
        event_cost_mult=1.85,
        max_events_per_month=5,
        sick_probability_mult=1.85,
        long_sick_probability_mult=3.2,
        vab_probability_mult=1.3,
        variable_spend_extra_mult=1.18,
        initial_savings_buffer_mult=0.7,
        spend_profile_amplifier=2.7,
    ),
}


def get_difficulty(level: int) -> DifficultyProfile:
    """Hämta DifficultyProfile för en nivå (clampar till 1-3)."""
    clamped = max(1, min(3, level))
    return DIFFICULTY_PROFILES[clamped]
