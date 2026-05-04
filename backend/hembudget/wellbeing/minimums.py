"""Konsumentverkets minimibelopp omräknat till budget-kategorier.

Användsfall:
- Vid POST /budget/ — varna eleven om hen sätter under minimum
- Generator-anpassning — om budget < minimum genereras färre rader
- Wellbeing-beräkning — Mat & hälsa-dimensionen sjunker vid violations

Alla belopp är kr/månad för en ensamboende vuxen 18-24 år (typisk
elev-profil). Familje-justeringar görs via _household_factor i
suggest_minimum_for_category.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Mappning från generella budget-kategorinamn (som elever skapar)
# till Konsumentverket-data. Alla kategorier som finns här validas mot
# minimum. Övriga kategorier får ingen minimum.
#
# Beloppen är ungefärliga 2026 baserat på Konsumentverkets siffror för
# 18-24-åring som ensamhushåll. Syftet är pedagogiskt — att ge eleven
# ett *referensvärde* att förhålla sig till, inte en absolut sanning.
CATEGORY_MINIMUMS_SEK_MONTH: dict[str, int] = {
    # Mat-kategorier (alla varianter mappar till samma minimum)
    "Mat": 2_840,
    "Livsmedel": 2_840,
    "ICA": 2_840,
    "Mathandel": 2_840,
    # Personlig hygien + kläder
    "Hygien": 700,
    "Kläder": 600,
    "Hygien & kläder": 1_300,
    # Fritid (vad du betalar för aktiviteter, ej ev. resor)
    "Fritid": 700,
    "Nöje": 700,
    # Bostad-kringkostnader (boende själv är separat budgetering)
    "Hemförsäkring": 200,
    "Hushållsel": 400,
    "Vatten": 220,
    "Bredband": 300,
    "Internet & mobil": 1_000,
    "Telefon": 250,
    "Mobil": 250,
    # Hemutrustning + förbrukningsvaror
    "Hemutrustning": 920,
    "Förbrukningsvaror": 200,
    # Transport (kollektivtrafik som minimum)
    "Transport": 970,  # SL-kort 30 dagar
    "Resor": 970,
    "SL": 970,
    # Sjukvård + tandvård (uppskattat)
    "Sjukvård": 200,
    "Tandvård": 150,
    "Hälsa": 350,
}


@dataclass
class MinimumCheck:
    category: str
    minimum: int
    actual: int
    ratio: float  # actual / minimum
    severity: str  # "ok" | "snålt" | "subexistens"
    message: str   # Pedagogisk text

    @property
    def is_violation(self) -> bool:
        return self.ratio < 0.8


def lookup_minimum(category: str) -> Optional[int]:
    """Returnera minimi-rekommendation för en kategori (kr/mån) eller
    None om kategorin inte är reglerad i vår mappning."""
    if not category:
        return None
    # Case-insensitiv lookup
    lower = category.lower().strip()
    for key, val in CATEGORY_MINIMUMS_SEK_MONTH.items():
        if key.lower() == lower:
            return val
    return None


def check_against_minimum(category: str, planned_amount: int) -> MinimumCheck:
    """Kollar en planerad budget mot Konsumentverket-minimum och
    returnerar pedagogisk klassificering + text.

    Trösklar (V2):
    - >= minimum: 'ok'
    - 80-100% av minimum: 'snålt' (varning, ej violation)
    - < 80%: 'snålt' med violation-flagga (Wellbeing -2 p)
    - < 50%: 'subexistens' (Wellbeing -5 p)
    """
    minimum = lookup_minimum(category)
    if minimum is None:
        return MinimumCheck(
            category=category, minimum=0, actual=planned_amount,
            ratio=1.0, severity="ok",
            message="Ingen Konsumentverket-rekommendation för denna kategori.",
        )
    actual = max(0, planned_amount)
    ratio = actual / minimum if minimum > 0 else 1.0

    if ratio < 0.5:
        sev = "subexistens"
        msg = (
            f"Konsumentverket räknar med ungefär {minimum:,} kr/mån för "
            f"{category} (ensamboende 18-24 år). Du har satt {actual:,} kr — "
            f"under hälften. Pedagogiskt: går teoretiskt, men förvänta dig "
            "att Wellbeing → Mat & hälsa sjunker tydligt och att kontoutdraget "
            "kommer visa väldigt sparsamma rader."
        ).replace(",", " ")
    elif ratio < 0.8:
        sev = "snålt"
        msg = (
            f"Konsumentverket räknar med ungefär {minimum:,} kr/mån för "
            f"{category}. Din budget på {actual:,} kr är under 80 % av det. "
            f"Det funkar men du kommer märka det — Wellbeing → Mat & hälsa "
            "drabbas något."
        ).replace(",", " ")
    elif ratio < 1.0:
        sev = "snålt"
        msg = (
            f"Du har {actual:,} kr för {category} — strax under "
            f"Konsumentverkets riktvärde {minimum:,} kr/mån. OK men inget "
            "marginal."
        ).replace(",", " ")
    else:
        sev = "ok"
        msg = (
            f"Bra. {actual:,} kr är i nivå med eller över Konsumentverkets "
            f"riktvärde ({minimum:,} kr/mån) för {category}."
        ).replace(",", " ")

    return MinimumCheck(
        category=category, minimum=minimum, actual=actual,
        ratio=ratio, severity=sev, message=msg,
    )
