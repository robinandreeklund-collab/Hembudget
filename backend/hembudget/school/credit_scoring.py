"""EkonomiSkalan — kreditbetyg-beräkning (idé 3 i dev_v1.md).

Pedagogisk variant av UC:s 300-850-skala. En 22-åring nystart i livet
ska INTE få högsta betyg automatiskt — kreditvärdighet byggs upp av:

1. **Livssituation** — ålder, anställningstid, familjestatus, boendetyp,
   inkomstnivå (statiska faktorer som speglar verkligheten i vart vi
   är i livscykeln).
2. **Beteende** — sparvana, skuldkvot, betalningsdisciplin, arbetsgivar-
   nöjdhet, tid på plattformen (dynamiska faktorer som eleven kan
   påverka direkt).

Allt visas i `reasons_md` så eleven kan räkna efter hur de förbättrar
sin score.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Bas-score = 500 (mellanvärde 300–850). En nystart-elev (ung, kort
# anställning, ingen historik) hamnar runt 380–450 → grad C/D, vilket
# är realistiskt. Eleven förtjänar A-betyg genom etablerad ekonomi.
DEFAULT_BASE_SCORE = 500

# Klampgränser
MIN_SCORE = 300
MAX_SCORE = 850


@dataclass
class ScoreResult:
    score: int
    grade: str
    factors: dict
    reasons_md: str


def _grade_from_score(s: int) -> str:
    # Trösklarna är kalibrerade så att en typisk fresh 22-åring landar
    # runt D, en etablerad 30-åring runt B/A, en pensionär med stabil
    # ekonomi runt B, och någon med betalningsanmärkningar på E.
    if s >= 800:
        return "A+"
    if s >= 700:
        return "A"
    if s >= 600:
        return "B"
    if s >= 500:
        return "C"
    if s >= 400:
        return "D"
    return "E"


def _age_points(age: Optional[int]) -> tuple[int, str]:
    if age is None:
        return 0, ""
    if age <= 19:
        return -50, "mycket_ung_18_19"
    if age <= 22:
        return -25, "ung_20_22"
    if age <= 29:
        return 5, "ung_vuxen_23_29"
    if age <= 49:
        return 30, "etablerad_30_49"
    if age <= 65:
        return 40, "mogen_50_65"
    return 20, "pensionar_65"


def _employment_points(years_employed: Optional[float]) -> tuple[int, str]:
    if years_employed is None:
        return 0, ""
    if years_employed < 0.5:
        return -25, "knappt_borjat_arbeta"
    if years_employed < 2:
        return 0, "ny_pa_arbetsmarknaden"
    if years_employed < 5:
        return 25, "etablerad_pa_jobbet"
    if years_employed < 10:
        return 45, "lang_anstallningshistorik"
    return 60, "mycket_lang_anstallning"


def _income_points(monthly_net: Optional[int]) -> tuple[int, str]:
    if monthly_net is None or monthly_net <= 0:
        return -40, "saknar_inkomst"
    if monthly_net < 15000:
        return -30, "lag_inkomst"
    if monthly_net < 23000:
        return -5, "modest_inkomst"
    if monthly_net < 33000:
        return 20, "medelinkomst"
    if monthly_net < 45000:
        return 40, "god_inkomst"
    return 55, "hog_inkomst"


def _family_points(family_status: Optional[str]) -> tuple[int, str]:
    if family_status == "sambo":
        return 15, "sambo_tva_inkomster"
    if family_status == "familj_med_barn":
        return 10, "familj_med_barn"
    if family_status == "ensam":
        return 0, "ensam"
    return 0, ""


def _housing_points(housing_type: Optional[str]) -> tuple[int, str]:
    if housing_type == "bostadsratt":
        return 25, "ager_bostadsratt"
    if housing_type == "villa":
        return 30, "ager_villa"
    if housing_type == "radhus":
        return 25, "ager_radhus"
    if housing_type == "hyresratt":
        return 0, "hyr_bostad"
    return 0, ""


def compute_score(
    *,
    late_payments: int,
    failed_payments: int,
    reminders_l3_or_higher: int,
    debt_ratio: float,
    savings_buffer_months: float,
    satisfaction_score: int,
    months_on_platform: int,
    # Livssituations-faktorer (None = okänd, hoppas över)
    age: Optional[int] = None,
    years_employed: Optional[float] = None,
    monthly_net_income: Optional[int] = None,
    family_status: Optional[str] = None,
    housing_type: Optional[str] = None,
) -> ScoreResult:
    """Beräkna EkonomiSkalan-score från strukturerade ingångar.

    Vikt-fördelningen är pedagogisk, inte en kopia av UC:s riktiga
    formel, men följer samma logik: livssituation + beteende.
    Varje delta visas i `factors._score_components`.

    Om `years_employed` inte skickas härleds den ur ålder
    (`max(0, age - 22)`) som schablon för "år sedan gymnasium/uni".
    """
    components: dict[str, int] = {}
    base = DEFAULT_BASE_SCORE

    # === LIVSSITUATION (statiska faktorer) ===
    age_pts, age_key = _age_points(age)
    if age_key:
        components[age_key] = age_pts

    if years_employed is None and age is not None:
        years_employed = max(0.0, float(age - 22))
    emp_pts, emp_key = _employment_points(years_employed)
    if emp_key:
        components[emp_key] = emp_pts

    inc_pts, inc_key = _income_points(monthly_net_income)
    if inc_key:
        components[inc_key] = inc_pts

    fam_pts, fam_key = _family_points(family_status)
    if fam_key:
        components[fam_key] = fam_pts

    hou_pts, hou_key = _housing_points(housing_type)
    if hou_key:
        components[hou_key] = hou_pts

    # === BETEENDE (dynamiska faktorer eleven kan påverka) ===

    # Sena betalningar: -25 per påminnelse av nivå 1-2, -60 per nivå 3+
    light_late = late_payments - reminders_l3_or_higher
    if light_late > 0:
        components["sena_betalningar"] = -25 * light_late
    if reminders_l3_or_higher > 0:
        components["inkasso_eller_kronofogden"] = -60 * reminders_l3_or_higher

    # Misslyckade signerade betalningar (saldo räckte inte): -15 var
    if failed_payments > 0:
        components["misslyckade_betalningar"] = -20 * failed_payments

    # Skuldkvot: 0 = positiv, 0-0.3 = neutral, 0.3-0.5 = neutral,
    # 0.5-0.7 = -40, 0.7+ = -100
    if debt_ratio <= 0:
        components["skuldfri"] = 20
    elif debt_ratio < 0.3:
        components["lag_skuldkvot"] = 10
    elif debt_ratio >= 0.7:
        components["mycket_hog_skuldkvot"] = -100
    elif debt_ratio >= 0.5:
        components["hog_skuldkvot"] = -40

    # Sparande-buffert
    if savings_buffer_months <= 0:
        components["ingen_buffert"] = -50
    elif savings_buffer_months >= 6:
        components["stark_buffert"] = 50
    elif savings_buffer_months >= 3:
        components["bra_buffert"] = 30
    elif savings_buffer_months < 1:
        components["liten_buffert"] = -20

    # Satisfaction (arbetsgivar-nöjdhet)
    if satisfaction_score < 30:
        components["arbetsgivar_lag"] = -40
    elif satisfaction_score >= 75:
        components["arbetsgivar_hog"] = 20

    # Tid på plattformen
    if months_on_platform >= 12:
        components["langsiktig_kund"] = 30
    elif months_on_platform >= 6:
        components["etablerad"] = 15
    elif months_on_platform <= 1:
        components["ny_pa_plattformen"] = -10

    score = base + sum(components.values())
    score = max(MIN_SCORE, min(MAX_SCORE, score))
    grade = _grade_from_score(score)

    sorted_comps = sorted(
        components.items(), key=lambda kv: -abs(kv[1]),
    )

    reasons_lines = [
        f"## Din EkonomiSkala-score: {score}/{MAX_SCORE} (grad {grade})",
        f"\nUtgångsläge: {base} (mellanvärde — kreditvärdighet "
        "byggs upp över tid).\n",
        "**Påverkande faktorer:**",
    ]
    for name, delta in sorted_comps:
        sign = "+" if delta > 0 else ""
        label = name.replace("_", " ").capitalize()
        reasons_lines.append(f"- {label}: **{sign}{delta} p**")
    if not sorted_comps:
        reasons_lines.append("- Inga avvikelser från utgångsläget.")

    factors = {
        "late_payments": late_payments,
        "failed_payments": failed_payments,
        "reminders_l3_or_higher": reminders_l3_or_higher,
        "debt_ratio": round(debt_ratio, 2),
        "savings_buffer_months": round(savings_buffer_months, 1),
        "satisfaction": satisfaction_score,
        "months_on_platform": months_on_platform,
        "age": age,
        "years_employed": (
            round(years_employed, 1) if years_employed is not None else None
        ),
        "monthly_net_income": monthly_net_income,
        "family_status": family_status,
        "housing_type": housing_type,
        "_score_components": components,
        "_base": base,
    }

    return ScoreResult(
        score=score,
        grade=grade,
        factors=factors,
        reasons_md="\n".join(reasons_lines),
    )
