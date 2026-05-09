"""Cross-engine wellbeing-faktorer · företag → privat-pentagon.

Pedagogisk princip: företagets resultat påverkar privat-pentagon — men
INTE 1:1. Det är en *asymmetrisk* funktion:
- Stora positiva företagshändelser → SMÅ positiva privat-effekter
  (företagsvinst ≠ automatiskt privat välstånd; du kan inte ta ut
   allt direkt; pengar är låsta i bolaget tills egen lön)
- Stora negativa företagshändelser → STÖRRE negativa privat-effekter
  (oro, stress, osäkerhet om kassaflöde drabbar verkliga personen)

Funktionen returnerar en lista WellbeingFactor-objekt som
calculate_wellbeing kan injicera i sin axel-summering. Faktorerna är
*förklarade* så eleven ser i pentagon-flip-kortets baksida varför
hens privat-axel rört sig — pedagogiskt avgörande.

Tids-aspekt: separat funktion `compute_time_stress_factors()` läser
elevens vecko-timmar (anställd + biz) och drar ner fritid/social/hälsa
om totalen blir orimlig.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


PrivatePentAxis = Literal["economy", "safety", "health", "social", "leisure"]


@dataclass
class CrossFactor:
    """En faktor som ska adderas till privat-pentagon från
    företags-tillståndet."""
    axis: PrivatePentAxis
    points: int                 # +/- bidrag
    explanation: str            # pedagogisk text till flip-kortet


def biz_to_private_factors(biz_axes: dict) -> list[CrossFactor]:
    """Beräkna cross-engine faktorer från företagets pentagon-axlar.

    Läser:
        biz_axes = {"omsattning", "kundbas", "likviditet", "tidsatgang", "vinst"}
    Returnerar lista CrossFactor som applicerats på privat-pentagon.

    Asymmetrisk vikt:
        Negativa företags-axlar (< 30) → kraftiga privat-penalties
        Positiva företags-axlar (> 70) → milda privat-bonusar
    """
    factors: list[CrossFactor] = []

    likv = biz_axes.get("likviditet", 50)
    vinst = biz_axes.get("vinst", 50)
    tids = biz_axes.get("tidsatgang", 50)
    kund = biz_axes.get("kundbas", 50)
    oms = biz_axes.get("omsattning", 50)

    # === LIKVIDITET → privat economy ===
    if likv < 20:
        factors.append(CrossFactor(
            axis="economy",
            points=-8,
            explanation=(
                "Företaget har akut kassakris · oro för att inte kunna "
                "ta ut egen lön drar ner ekonomi-axeln."
            ),
        ))
    elif likv < 30:
        factors.append(CrossFactor(
            axis="economy",
            points=-5,
            explanation=(
                "Tunn likviditet i företaget · ständig oro för "
                "kassaflöde."
            ),
        ))
    elif likv >= 80 and oms >= 50:
        factors.append(CrossFactor(
            axis="economy",
            points=+3,        # mild positiv (asymmetri!)
            explanation=(
                "Stark likviditet + omsättning · företaget bygger "
                "kapital som senare kan tas ut."
            ),
        ))

    # === VINST → privat health (stress) ===
    if vinst < 20:
        factors.append(CrossFactor(
            axis="health",
            points=-5,
            explanation=(
                "Förlust i företaget · sömnlös oro över kostnader > "
                "intäkter slår mot hälsan."
            ),
        ))
    elif vinst < 35:
        factors.append(CrossFactor(
            axis="health",
            points=-2,
            explanation="Tunn marginal · konstant stress över ekonomin.",
        ))
    elif vinst >= 80:
        factors.append(CrossFactor(
            axis="health",
            points=+1,        # mild
            explanation=(
                "Företaget går starkt · känslan av att lyckas hjälper "
                "mående lite."
            ),
        ))

    # === TIDSÅTGÅNG → privat leisure + social ===
    if tids > 85:
        factors.append(CrossFactor(
            axis="leisure",
            points=-7,
            explanation=(
                "Företaget tar för många timmar · fritiden krymper "
                "kraftigt."
            ),
        ))
        factors.append(CrossFactor(
            axis="social",
            points=-5,
            explanation=(
                "Övertilltecknad · vänner och familj kommer i andra "
                "hand när jobb-deadlines pressar."
            ),
        ))
    elif tids > 70:
        factors.append(CrossFactor(
            axis="leisure",
            points=-3,
            explanation="Företaget kapar fritid · 5–10h mindre/v till nöje.",
        ))
        factors.append(CrossFactor(
            axis="social",
            points=-2,
            explanation="Mer jobb · mindre tid med vänner/familj.",
        ))

    # === KUNDBAS → privat safety (rykte = framtidstrygghet) ===
    if kund >= 80:
        factors.append(CrossFactor(
            axis="safety",
            points=+3,        # mild positiv
            explanation=(
                "Stark kundbas · ryktet ger framtida pipeline · "
                "trygghet i att ha kunder."
            ),
        ))
    elif kund < 25:
        factors.append(CrossFactor(
            axis="safety",
            points=-3,
            explanation=(
                "Tunn kundbas · framtida intäkter osäkra · känsla "
                "av yrkes-otrygghet."
            ),
        ))

    # === OMSÄTTNING-trend → economy bonus om mycket bra ===
    if oms >= 85 and vinst >= 60:
        factors.append(CrossFactor(
            axis="economy",
            points=+2,
            explanation=(
                "Stigande omsättning · högre egen-lön möjlig nästa "
                "månad → mer kvar privat."
            ),
        ))

    return factors


# === Tids-stress · separat utility ===

@dataclass
class TimeStressInput:
    weekly_hours_employed: int          # 0-40h vanligt jobb
    weekly_hours_business: int          # från active jobs
    consecutive_weeks_overload: int     # hur många veckor i rad > 50h


def compute_time_stress_factors(
    inp: TimeStressInput,
) -> list[CrossFactor]:
    """Räkna tids-stress-deltas på privat-pentagon.

    Trösklar (svenska arbetsmiljö-normer som referens):
        50-55 h/v → -2 leisure (mild varning)
        55-65 h/v → -5 leisure, -3 health, -3 social (märkbar stress)
        65+  h/v → -10 leisure, -8 health, -8 social (burnout-risk)

    Konsekutiva-veckor-bonus: om eleven legat över 50h i 4+ veckor i
    rad → kraftigare straff på health (kropp orkar inte i längden).
    """
    total = inp.weekly_hours_employed + inp.weekly_hours_business
    factors: list[CrossFactor] = []

    if total < 50:
        return factors           # ingen stress

    if total >= 65:
        factors.append(CrossFactor(
            axis="leisure",
            points=-10,
            explanation=f"{total} h/vecka totalt · ingen fritid kvar (burnout-risk).",
        ))
        factors.append(CrossFactor(
            axis="health",
            points=-8,
            explanation=(
                f"{total} h/v är inte hållbart · sömnen, träningen och "
                "matvanorna lider."
            ),
        ))
        factors.append(CrossFactor(
            axis="social",
            points=-8,
            explanation=(
                "Ingen tid för vänner, familj eller partner · isolering."
            ),
        ))
    elif total >= 55:
        factors.append(CrossFactor(
            axis="leisure",
            points=-5,
            explanation=f"{total} h/v · märkbar krympt fritid.",
        ))
        factors.append(CrossFactor(
            axis="health",
            points=-3,
            explanation="Stress påverkar sömn/återhämtning.",
        ))
        factors.append(CrossFactor(
            axis="social",
            points=-3,
            explanation="Mindre tid för relationer.",
        ))
    elif total >= 50:
        factors.append(CrossFactor(
            axis="leisure",
            points=-2,
            explanation=(
                f"{total} h/v · första varningen · börjar äta av "
                "fritiden."
            ),
        ))

    # Förstärkt straff vid uthållig överbelastning
    if inp.consecutive_weeks_overload >= 4 and total >= 55:
        factors.append(CrossFactor(
            axis="health",
            points=-3,
            explanation=(
                f"{inp.consecutive_weeks_overload} veckor i rad över "
                "50h · kroppen tappar återhämtning."
            ),
        ))

    return factors


def compute_weekly_business_hours(
    in_progress_jobs: list,
    industry_key: str | None = None,
) -> int:
    """Beräkna förväntade biz-timmar/vecka från active jobs.

    in_progress_jobs är en lista Job-instanser eller dict-liknande
    objekt med fält 'agreed_price' och 'expected_complete_on' /
    'started_on'. Vi approximerar timmar utifrån branschens
    `time_per_job_hours` mid-värde och delar på antal veckor till
    deadline.
    """
    if not in_progress_jobs:
        return 0

    # Bransch-baseline (om okänd → 12h per jobb)
    hours_per_job_mid = 12
    if industry_key:
        try:
            from .industries import get_industry
            ind = get_industry(industry_key)
            hours_per_job_mid = (
                ind.time_per_job_hours_min + ind.time_per_job_hours_max
            ) // 2
        except Exception:
            pass

    total_remaining_hours = 0
    # SPEL-TID-FIX: tidigare _d.today() (real-tid) jämfördes mot
    # job.expected_complete_on (spel-tid) → days_left blev kraftigt
    # negativt → max(1, days_left) gav 1 vecka kvar för alla jobb →
    # weekly_hours överskattades drastiskt → Maria-säg-upp-prompten
    # triggades alldeles för aggressivt.
    from .game_clock import current_game_date
    today = current_game_date()
    for job in in_progress_jobs:
        # Approximera resten av jobbet som hours_per_job_mid
        # delat på dagar till deadline
        try:
            deadline = job.expected_complete_on
        except AttributeError:
            deadline = job.get("expected_complete_on") if isinstance(
                job, dict,
            ) else None
        if deadline is None:
            total_remaining_hours += hours_per_job_mid
            continue
        days_left = max(1, (deadline - today).days)
        weeks_left = max(1, days_left // 7)
        # Fördelat på veckor → timmar/vecka
        total_remaining_hours += hours_per_job_mid // weeks_left

    return total_remaining_hours
