"""Profile Generator · syntetisk svensk vuxen-profil per elev.

Spec: dev/game-motor/02-profile-generator.md

`generate_profile()` slumpar deterministiskt:
- Yrke (från yrkespoolen, viktat efter arketyp + startnivå)
- Stad (från stadspoolen, viktat efter yrkets city_preference)
- Boende (matchat mot nettolön + max-procent-regler)
- Familj (sambo / barn / ensam)
- Initial pentagon (60 ± modifierare baserat på profil-fakta)

Resultatet är en `GeneratedProfile` (Pydantic) som kan visas direkt i UI
eller persisteras genom seeder (kommer i G3.5/Sprint 1.5).
"""
from .schema import GeneratedProfile, HousingChoice, FamilyChoice
from .generator import generate_profile
from .pentagon_init import compute_initial_pentagon

__all__ = [
    "GeneratedProfile",
    "HousingChoice",
    "FamilyChoice",
    "generate_profile",
    "compute_initial_pentagon",
]
