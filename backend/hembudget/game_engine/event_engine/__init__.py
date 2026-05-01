"""Event Engine · oväntade händelser, försäkrings-mildring, lärar-injektion.

Spec: dev/game-motor/04-event-engine.md

Pipeline per spelmånad:
  1. Slumpa vilka templates som triggas (frequency_per_year / 12, viktat
     mot profil-filter ålder/familjestatus)
  2. Apply_mitigation: matcha mot elevens InsurancePolicy:s, räkna ut
     effective cost + pentagon-impact
  3. Skapa MailItem (kind="invoice" eller "info" beroende på cost)
  4. Skapa InsuranceClaim om mitigation användes (för pedagogisk spårbarhet)
  5. Logga i WeekTickRun.summary["events"]

Manuell injektion via /v2/teacher/students/{id}/inject-event.
"""
from .templates import (
    EVENT_TEMPLATES,
    EVENT_BY_KEY,
    EventTemplate,
    Mitigation,
    PentagonImpact,
    list_active_templates,
)
from .mitigation import (
    MitigationResult,
    apply_mitigation,
    best_mitigation_for,
)
from .roller import (
    EventOccurrence,
    apply_event,
    roll_monthly_events,
)

__all__ = [
    "EVENT_TEMPLATES",
    "EVENT_BY_KEY",
    "EventTemplate",
    "Mitigation",
    "PentagonImpact",
    "list_active_templates",
    "MitigationResult",
    "apply_mitigation",
    "best_mitigation_for",
    "EventOccurrence",
    "apply_event",
    "roll_monthly_events",
]
