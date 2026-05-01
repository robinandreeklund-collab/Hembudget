"""Monte Carlo · Fas 8 V1 · validering av spelmotorns ekonomiska balans.

Spec: dev/game-motor/11-implementations-plan.md (V1: 10k simuleringar/nivå)

Kör N in-memory simuleringar (utan DB-skrivning) per konfiguration och
samlar statistik. Avgör om den genomsnittliga eleven hamnar i:
- Positiv balans (sparar)
- Marginal (spenderar allt)
- Underskott (skuldsätter sig)

Pedagogiskt verktyg för läraren och oss att kalibrera difficulty-nivåer:
- Nivå 1 (sparsam) → 90 % positiva
- Nivå 2 (balanserad) → 60-70 % positiva
- Nivå 3 (slösa) → 30-40 % positiva (medvetet utmanande)
"""
from .runner import (
    MCResult,
    MCSimulation,
    SimConfig,
    run_simulations,
    summarize,
)

__all__ = ["MCResult", "MCSimulation", "SimConfig", "run_simulations", "summarize"]
