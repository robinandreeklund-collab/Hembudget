"""Game Engine — orkestreringslagret för den simulerade spelmotorn.

Spec: dev/game-motor/README.md

Nuvarande implementation:
- pools/ · Yrkespool + Stadspool (G1)
- profile_generator/ · Profil-syntes (G3-G4)
- monthly_engine/ · Veckotick (M1-M3, M5)

Kommande:
- monthly_engine/ · M4 (drift) + M6 (cron) i Sprint 4
- event_engine/ · Oväntade händelser (E1-E7)
- pentagon/ · Tröghet, drift, mål (P1-P5)
- arbetsformedlingen/ · 5-rond intervju (A1-A5)
- housing_market/ · Köp/sälj/flytt (B1-B5)
- monte_carlo/ · Validering (Fas 8)
- elev_tester/ · Veckotest (Fas 9)
"""
