"""Pipeline-generator · antal nya offertförfrågningar per vecka.

Spec: deb/README.md avsnitt 5.2 ("Får eleven fler liknande jobb?").

```
antal_nya = base
  + bonus(rykte)
  + bonus(aktiva_marknadsföringskampanjer)
  + bonus(senaste_levererade_kvalitet)
  - penalty(öppna_klagomål)
```

Deterministisk · seedad på (company_id, week_no). Returnerar 0..N nya
JobOpportunity-instanser (ej commitade).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass
class PipelineInput:
    week_no: int
    reputation: int               # 0..100
    avg_quality: int | None       # 0..100, None = ingen historik
    open_complaints: int
    active_marketing_boost: float  # summa av aktiva kampanjers boost (0..3)
    delivery_capacity: int        # max antal samtidiga jobb
    in_progress_jobs: int         # nuvarande
    base_per_week: int            # från BizDifficultyProfile


@dataclass
class PipelineOutput:
    n_opportunities: int          # antal nya att skapa
    explanation: str


def calculate_n_opportunities(
    inp: PipelineInput, *, seed: int,
) -> PipelineOutput:
    """Räkna deterministiskt fram antal nya offertförfrågningar."""
    base = inp.base_per_week

    # Rykte-bonus · centrerat på 50
    if inp.reputation >= 80:
        rep_bonus = 2
    elif inp.reputation >= 60:
        rep_bonus = 1
    elif inp.reputation <= 30:
        rep_bonus = -1
    else:
        rep_bonus = 0

    # Marknadsföring · 0..3 boost → +0..2 jobb
    marketing_bonus = min(2, int(round(inp.active_marketing_boost * 0.7)))

    # Senaste levererade kvalitet · höjt till bonus om hög, dragit av om låg
    if inp.avg_quality is not None:
        if inp.avg_quality >= 80:
            quality_bonus = 1
        elif inp.avg_quality <= 40:
            quality_bonus = -1
        else:
            quality_bonus = 0
    else:
        quality_bonus = 0

    # Klagomål-straff
    complaint_penalty = min(2, inp.open_complaints)

    # Kapacitet · om eleven har 0 lediga slots, halvera pipelinen
    free_slots = max(0, inp.delivery_capacity - inp.in_progress_jobs)
    if free_slots == 0:
        capacity_factor = 0.4
    elif free_slots == 1:
        capacity_factor = 0.7
    else:
        capacity_factor = 1.0

    raw = base + rep_bonus + marketing_bonus + quality_bonus - complaint_penalty
    raw = max(0, int(round(raw * capacity_factor)))

    # Lägg på en liten slumpvariation ±1 för att inte allt blir
    # exakt likadant varje vecka (eleven märker variation, men
    # determinism är intakt eftersom seed = (company_id, week_no))
    rng = random.Random(seed)
    variance = rng.choice([-1, 0, 0, 1])
    n = max(0, raw + variance)

    expl_parts = [f"Bas {base}"]
    if rep_bonus:
        expl_parts.append(f"rykte {'+' if rep_bonus > 0 else ''}{rep_bonus}")
    if marketing_bonus:
        expl_parts.append(f"marknadsföring +{marketing_bonus}")
    if quality_bonus:
        expl_parts.append(
            f"kvalitet {'+' if quality_bonus > 0 else ''}{quality_bonus}"
        )
    if complaint_penalty:
        expl_parts.append(f"klagomål -{complaint_penalty}")
    if capacity_factor < 1.0:
        expl_parts.append(f"kapacitetsbrist (×{capacity_factor:.1f})")
    expl_parts.append(f"slump {variance:+d}")

    explanation = " · ".join(expl_parts) + f" → {n} nya förfrågningar"

    return PipelineOutput(n_opportunities=n, explanation=explanation)
