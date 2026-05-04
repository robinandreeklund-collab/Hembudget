"""Pentagon-mekanik · drift, tröghet, WellbeingEvent-logg.

Spec: dev/game-motor/07-pentagon-mekanik.md

Tre lager:
  M4 · drift_calculator     — månadsvis drift baserat på elevbeteende
  P1 · momentum             — klamp per event/dag/månad
  P2 · WellbeingEvent-logg  — spårar varje pentagon-delta för audit + Echo
"""
from .drift_calculator import (
    DriftResult,
    compute_monthly_drift,
)
from .momentum import (
    MAX_PER_DAY,
    MAX_PER_EVENT,
    MAX_PER_MONTH,
    apply_momentum,
)
from .wellbeing_log import (
    apply_pentagon_delta,
    log_wellbeing_event,
    pentagon_history_for_student,
)

__all__ = [
    "DriftResult",
    "compute_monthly_drift",
    "MAX_PER_EVENT",
    "MAX_PER_DAY",
    "MAX_PER_MONTH",
    "apply_momentum",
    "apply_pentagon_delta",
    "log_wellbeing_event",
    "pentagon_history_for_student",
]
