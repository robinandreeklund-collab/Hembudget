"""Pools · datafundament för Profile Generator + Arbetsförmedlingen.

- yrkespool.py · ~30 representativa svenska yrken med 2026-lönedata
- stadspool.py · 12 städer med boendekostnad-multiplikatorer

Källor: SCB SSYK-2012 strukturlönestatistik 2024 (uppjusterad ~3 % för
2026), Arbetsförmedlingen yrkesprognoser, Hyresgästföreningen,
Konsumentverket bopris-statistik.
"""
from .yrkespool import (
    YRKESPOOL,
    YRKE_BY_KEY,
    EducationLevel,
    Yrke,
    pick_yrke_by_archetype,
)
from .stadspool import (
    STADSPOOL,
    City,
    Stad,
    pick_city_weighted,
)

__all__ = [
    "YRKESPOOL", "YRKE_BY_KEY", "EducationLevel", "Yrke",
    "pick_yrke_by_archetype",
    "STADSPOOL", "City", "Stad", "pick_city_weighted",
]
