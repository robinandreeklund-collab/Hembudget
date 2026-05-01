"""Health Engine · sjukdom + VAB + lönepåverkan + EmployerSatisfaction.

Källor (2024-statistik från svenska myndigheter):
- Försäkringskassan · VAB-statistik 2023 (~7-8 dagar/barn/år)
- Försäkringskassan · "när vabbas det som mest" (jan-feb pikar pga RS-virus)
- Arbetsgivarverket · Statlig sjukfrånvaro 4.7 % av ordinarie arbetstid
- AFA-försäkring · korta sjukperioder dominerar (~70 % är 1-7 dagar)

Sjuklöneregler 2026:
  Dag 1     karensavdrag = 20 % × snittveckans lön (≈ 1 månadslön/4.33 × 0.20)
  Dag 2-14  sjuklön 80 % från arbetsgivare
  Dag 15+   sjukpenning ~80 % av SGI från Försäkringskassan
            (max 1209 kr/dag 2026, motsvarar SGI tak ~554 200 kr/år)

VAB-regler 2026:
  Tillfällig föräldrapenning ~80 % av SGI (samma tak som sjukpenning)
  Karensdag = 0 (gäller från första dag)
  120 dagar/barn/år upp till 12 års ålder
"""
from .roller import (
    HealthEvent,
    HealthOccurrence,
    SICK_EVENT_TEMPLATES,
    apply_health_episode,
    apply_sick_pay_reduction,
    roll_monthly_health_events,
)

__all__ = [
    "HealthEvent",
    "HealthOccurrence",
    "SICK_EVENT_TEMPLATES",
    "apply_health_episode",
    "apply_sick_pay_reduction",
    "roll_monthly_health_events",
]
