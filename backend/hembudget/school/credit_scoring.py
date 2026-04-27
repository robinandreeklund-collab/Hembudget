"""EkonomiSkalan — kreditbetyg-beräkning (idé 3 i dev_v1.md).

Pedagogisk variant av UC:s 300-850-skala. Faktorerna är:
- Sena betalningar (PaymentReminder-rader)
- Misslyckade scheduled-payments (saldo räckte inte)
- Skuldkvot (totala lån / årsinkomst-proxy)
- Sparande-buffert (sparkonto / månadsutgifter)
- Satisfaction-score från arbetsplatsen
- Aktivt antal månader på kontot (hur länge eleven har varit i systemet)

Allt är synligt i `reasons_md` så eleven kan räkna efter.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


# Default-startscore — 700 är "bra" hos UC
DEFAULT_BASE_SCORE = 700

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
    if s >= 800:
        return "A+"
    if s >= 720:
        return "A"
    if s >= 640:
        return "B"
    if s >= 560:
        return "C"
    return "D"


def compute_score(
    *,
    late_payments: int,
    failed_payments: int,
    reminders_l3_or_higher: int,
    debt_ratio: float,  # totala lån / 12*månadslön (~årsinkomst)
    savings_buffer_months: float,  # sparkonto / månadsutgifter
    satisfaction_score: int,  # 0–100
    months_on_platform: int,
) -> ScoreResult:
    """Beräkna kreditbetyg från strukturerade ingångar.

    Vikt-fördelning är pedagogisk, inte en kopia av UC:s riktiga
    formel. Vi visar varje delta i `factors._score_components`.
    """
    components: dict[str, int] = {}
    base = DEFAULT_BASE_SCORE

    # Sena betalningar: -25 per påminnelse av nivå 1-2, -60 per nivå 3+
    light_late = late_payments - reminders_l3_or_higher
    components["sena_betalningar"] = -25 * max(0, light_late)
    if reminders_l3_or_higher > 0:
        components["inkasso_eller_kronofogden"] = -60 * reminders_l3_or_higher

    # Misslyckade signerade betalningar (saldo räckte inte): -15 var
    if failed_payments > 0:
        components["misslyckade_betalningar"] = -15 * failed_payments

    # Skuldkvot: 0–0.4 = neutral, 0.4-0.6 = -30, 0.6+ = -80
    if debt_ratio >= 0.6:
        components["hög_skuldkvot"] = -80
    elif debt_ratio >= 0.4:
        components["medel_skuldkvot"] = -30

    # Sparande-buffert: 0 mån = -50, 1 mån = neutral, 3+ = +30
    if savings_buffer_months <= 0:
        components["ingen_buffert"] = -50
    elif savings_buffer_months >= 3:
        components["bra_buffert"] = 30
    elif savings_buffer_months >= 6:
        components["stark_buffert"] = 50

    # Satisfaction (arbetsgivar-nöjdhet)
    if satisfaction_score < 30:
        components["arbetsgivar_låg"] = -40
    elif satisfaction_score >= 75:
        components["arbetsgivar_hög"] = 20

    # Tid på plattformen
    if months_on_platform >= 12:
        components["långsiktig_kund"] = 30
    elif months_on_platform >= 6:
        components["etablerad"] = 15

    score = base + sum(components.values())
    score = max(MIN_SCORE, min(MAX_SCORE, score))
    grade = _grade_from_score(score)

    # Sortera komponenter för pedagogisk läsbarhet
    sorted_comps = sorted(
        components.items(), key=lambda kv: -abs(kv[1]),
    )

    reasons_lines = [
        f"## Din EkonomiSkala-score: {score}/{MAX_SCORE} (grad {grade})",
        f"\nUtgångsläge: {base} (genomsnittligt 'bra' kreditbetyg).\n",
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
        "_score_components": components,
        "_base": base,
    }

    return ScoreResult(
        score=score,
        grade=grade,
        factors=factors,
        reasons_md="\n".join(reasons_lines),
    )
