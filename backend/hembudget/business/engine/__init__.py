"""Business spelmotor — analog med game_engine/ för privatekonomin.

Spec: deb/README.md (avsnitt 4–6 + 12).

Moduler:
- seed_data       · Branscher, kundtyper, jobbmallar
- pricing         · Marknadsmässigt riktpris per (industry, customer_segment)
- acceptance_model· P(accept) = sigmoid(...) — deterministisk
- pipeline_generator · Antal nya offertförfrågningar per vecka
- reputation      · Rykte-uppdatering från kvalitet/marknadsföring/klagomål
- difficulty      · BizDifficultyProfile (basics vs advanced)
- events          · Slumpevents (klagomål, datorn-gick-sönder, miljöskatt)
- tick_engine     · Huvud-orkestrator · run_business_week()

Determinism: alla slumpgenerationer seedade på (company_id, week_no)
så att läraren kan spela om en vecka och få samma utfall.
"""
from .tick_engine import auto_tick_if_due, run_business_week
from .difficulty import BizDifficultyProfile, get_biz_difficulty

__all__ = [
    "auto_tick_if_due",
    "run_business_week",
    "BizDifficultyProfile",
    "get_biz_difficulty",
]
