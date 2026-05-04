"""Rykte-uppdatering · drivs av kvalitet, marknadsföring, klagomål.

Spec: deb/README.md avsnitt 4 (Business · "rykte 0–100, drivs av
kvalitet på leveranser") + avsnitt 5.2 (pipelinens bonus/penalty).

Designprincip: rykte ändras LÅNGSAMT (asymptotisk drift mot ett
mål-värde) så att eleven inte kan rusa upp till 100 över en natt.
Analog med pentagon-momentum för privatmotorn.
"""
from __future__ import annotations


def update_reputation_from_delivery(
    current: int, quality_score: int, weight: float = 0.15,
) -> int:
    """Levererat jobb påverkar rykte mot kvaliteten.

    weight=0.15 → tar ~5–6 leveranser för att gå från 50 till
    kvalitetsnivån. Pedagogiskt: konsistent kvalitet bygger rykte.
    """
    target = quality_score
    new_value = current + (target - current) * weight
    return max(0, min(100, int(round(new_value))))


def update_reputation_from_complaint(current: int, severity: int = 1) -> int:
    """Klagomål drar ner rykte direkt. severity 1=mild, 3=allvarligt."""
    drop = 5 * max(1, min(3, severity))
    return max(0, current - drop)


def update_reputation_from_marketing(
    current: int, ai_quality_factor: float | None,
) -> int:
    """Lyckad marknadsföring ger en liten skjuts (max +3 per kampanj).

    Bara *aktiverad* kampanj triggar detta — när kampanjen startar.
    """
    # AI-kvalitet 1.0 = neutral, 1.5 = excellent, 0.5 = dålig
    factor = 1.0 if ai_quality_factor is None else float(ai_quality_factor)
    bonus = int(round((factor - 1.0) * 6))   # -3..+3
    return max(0, min(100, current + bonus))


def update_avg_quality(
    current: int | None, new_quality: int, weight: float = 0.3,
) -> int:
    """Exponentiell utjämning av snitt-kvalitet."""
    if current is None:
        return new_quality
    return int(round(current + (new_quality - current) * weight))
