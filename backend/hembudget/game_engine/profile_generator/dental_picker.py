"""Frisktandvård · vanlig svensk tandförsäkring som täcker
löpande besök hos folktandvården mot en fast månadsavgift.

Folktandvården placerar varje patient i en av 10 prisgrupper baserat
på tandhälsa (Grupp 1 = bäst tandhälsa, lägst risk · Grupp 10 = sämst).
Premien beror också på åldersgrupp · 20-23-åringar och 67+ får
allmänna tandvårdsbidraget (ATB) som sänker priset, 24-66-åringar
betalar normalpris.

Spelet seedar slumpat:
- ~40 % av karaktärerna har frisktandvård (verklighet · Folktandvården)
- Tier-fördelning: ~35 % grupp 1-2, ~35 % grupp 3-4, ~18 % grupp 5-6,
  ~8 % grupp 7-8, ~4 % grupp 9-10 (skev mot frisk · de flesta är ok)

När en tandhälsa-event tickas (kontroll, karies, lagning) kollar
event-engine om eleven har aktiv frisktandvård → cost = 0 kr +
"(täckt av frisktandvård)"-etikett.
"""
from __future__ import annotations

import random
from typing import Literal, Optional

from pydantic import BaseModel


# === Pris per grupp + ålderskategori ===
# Källa: Folktandvården 2026 (justerat för spel-pedagogik).
# Pris med ATB (Allmänt tandvårdsbidrag) · 20-23 år och 67+
PREMIUM_WITH_ATB = {
    1: 40,
    2: 70,
    3: 110,
    4: 160,
    5: 245,
    6: 335,
    7: 415,
    8: 515,
    9: 650,
    10: 855,
}

# Normalpris · 24-66 år
PREMIUM_NORMAL = {
    1: 65,
    2: 95,
    3: 135,
    4: 185,
    5: 270,
    6: 360,
    7: 440,
    8: 540,
    9: 675,
    10: 880,
}

# Realistisk fördelning · de flesta hamnar i låga grupper
TIER_DISTRIBUTION = [
    (1, 0.18),
    (2, 0.17),
    (3, 0.18),
    (4, 0.17),
    (5, 0.10),
    (6, 0.08),
    (7, 0.05),
    (8, 0.03),
    (9, 0.025),
    (10, 0.015),
]

# Andel av befolkningen som har frisktandvårdsavtal · ~40 % enligt
# Folktandvården (siffran varierar mellan regioner men ger god
# pedagogisk fördelning).
P_HAS_FRISKTANDVARD = 0.40


def _is_atb_age(age: int) -> bool:
    """ATB-bidrag · 20-23 år och 67+. Övriga 24-66 betalar normalpris.
    Pedagogiskt: yngsta och äldsta får statligt stöd.
    """
    return age <= 23 or age >= 67


def _pick_tier(rng: random.Random) -> int:
    """Slumpa tier 1-10 enligt realistisk fördelning."""
    r = rng.random()
    acc = 0.0
    for tier, weight in TIER_DISTRIBUTION:
        acc += weight
        if r <= acc:
            return tier
    return TIER_DISTRIBUTION[-1][0]


class DentalChoice(BaseModel):
    has_frisktandvard: bool
    tier: Optional[int] = None              # 1-10 om has_*=True
    age_category: Optional[Literal["atb", "normal"]] = None
    premium_monthly: Optional[int] = None   # kr/mån
    provider: Optional[str] = None          # "Folktandvården"


def pick_dental(
    rng: random.Random,
    *,
    age: int,
    spend_profile: str = "balanserad",
) -> DentalChoice:
    """Slumpa tand-status för en karaktär.

    Spend-profile-justering:
      sparsam → -5 procentenheter chans att ha frisktandvård
      extravagant → +5 procentenheter (väljer trygghet)
    """
    base_chance = P_HAS_FRISKTANDVARD
    if spend_profile == "sparsam":
        base_chance -= 0.05
    elif spend_profile == "extravagant":
        base_chance += 0.05
    base_chance = max(0.20, min(0.70, base_chance))

    has = rng.random() < base_chance
    if not has:
        return DentalChoice(has_frisktandvard=False)

    tier = _pick_tier(rng)
    if _is_atb_age(age):
        prem = PREMIUM_WITH_ATB[tier]
        cat = "atb"
    else:
        prem = PREMIUM_NORMAL[tier]
        cat = "normal"

    return DentalChoice(
        has_frisktandvard=True,
        tier=tier,
        age_category=cat,  # type: ignore[arg-type]
        premium_monthly=prem,
        provider="Folktandvården",
    )
