"""Konsumentverkets minimibelopp omräknat till budget-kategorier.

Användsfall:
- Vid POST /budget/ — varna eleven om hen sätter under minimum
- Generator-anpassning — om budget < minimum genereras färre rader
- Wellbeing-beräkning — Mat & hälsa-dimensionen sjunker vid violations

`CATEGORY_MINIMUMS_SEK_MONTH` är default för en ensamboende vuxen 18-24
år. För familje-aware lookup (sambo, barn, hyresrätt vs villa) använd
`kv_minimum_for_household()` som räknar dynamiskt via
school.konsumentverket-tabellerna.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..school.konsumentverket import (
    GEMENSAMT_PER_PERSONER,
    INDIVID_OVRIGT_PER_AGE,
    MAT_HEMMA_PER_AGE,
)


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


def check_against_minimum(
    category: str,
    planned_amount: int,
    *,
    profile: object | None = None,
) -> MinimumCheck:
    """Kollar en planerad budget mot Konsumentverket-minimum och
    returnerar pedagogisk klassificering + text.

    Trösklar (V2):
    - >= minimum: 'ok'
    - 80-100% av minimum: 'snålt' (varning, ej violation)
    - < 80%: 'snålt' med violation-flagga (Wellbeing -2 p)
    - < 50%: 'subexistens' (Wellbeing -5 p)
    """
    if profile is not None:
        minimum = kv_minimum_for_student(category, profile)
    else:
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


# === Familje-aware KV-lookup ===========================================
# Konsumentverkets siffror skiljer sig kraftigt mellan ensam, sambo och
# barnfamilj. En sambo-familj med två barn kan ha 2-3× högre matbudget
# än en singel — så hårdkodade tabellen ovan är pedagogiskt förvillande
# i de fallen. Vi räknar dynamiskt via tabellerna i school.konsumentverket.
#
# Mappning: våra interna kategorinamn → KV-bucket
#  - "mat"      → MAT_HEMMA per person (summa)
#  - "individ"  → INDIVID_OVRIGT per person (summa) → vidaresplittas
#                 per kategori (kläder/fritid/hygien har olika andel)
#  - "gemensamt-<key>" → GEMENSAMT_PER_PERSONER[key] enligt antal personer

# Andelar av "individuellt övrigt" per sub-kategori (KV-PDF 2026 ger
# uppskattning mellan kläder/skor, fritid, hygien, försäkring,
# barnutrustning). Använt för att splittra individ-totalen i smalare
# budget-poster eleven själv brukar skapa.
_INDIV_ANDELAR: dict[str, float] = {
    "kläder": 0.27,    # ~27 % kläder/skor
    "klader": 0.27,
    "kläder & skor": 0.27,
    "skor": 0.27,
    "fritid": 0.32,    # ~32 % fritid/aktiviteter
    "nöje": 0.32,
    "noje": 0.32,
    "nöje & fritid": 0.32,
    "hygien": 0.18,    # ~18 % hygien/personlig vård
    "hälsa": 0.10,     # ~10 % egen vård (sjukvård/tandvård i indiv)
    "halsa": 0.10,
    "hälsa & hygien": 0.28,
    "halsa & hygien": 0.28,
    "sjukvård": 0.05,
    "tandvård": 0.05,
}


def _gemensamt_for(key: str, persons: int) -> int:
    arr = GEMENSAMT_PER_PERSONER.get(key, [])
    if not arr:
        return 0
    idx = max(0, min(len(arr) - 1, persons - 1))
    return arr[idx]


def _lookup_age(age: int, table: list[tuple[range, int]]) -> int:
    for r, v in table:
        if age in r:
            return v
    return table[-1][1]


def kv_minimum_for_household(
    category: str,
    *,
    adult_age: int = 25,
    partner_age: int | None = None,
    children_ages: list[int] | None = None,
    housing_type: str = "hyresratt",
) -> Optional[int]:
    """Räkna ut KV-minimum för en specifik hushållsprofil.

    Använder Konsumentverkets 2026-tabeller: per-person mat/individ
    enligt åldersgrupp + per-personer-antal för gemensamma kostnader.
    Returnerar None om kategorin inte är KV-reglerad.
    """
    if not category:
        return None
    lower = category.lower().strip()
    children_ages = children_ages or []
    persons = 1 + (1 if partner_age is not None else 0) + len(children_ages)

    # === Mat (per person) ===
    if any(k in lower for k in ("mat", "livsmedel", "ica", "coop", "willys")):
        total = _lookup_age(adult_age, MAT_HEMMA_PER_AGE)
        if partner_age is not None:
            total += _lookup_age(partner_age, MAT_HEMMA_PER_AGE)
        for c_age in children_ages:
            total += _lookup_age(c_age, MAT_HEMMA_PER_AGE)
        return total

    # === Individuellt (kläder/fritid/hygien/hälsa) ===
    indiv_andelar_key = None
    for key in _INDIV_ANDELAR:
        if key in lower:
            indiv_andelar_key = key
            break
    if indiv_andelar_key is not None:
        total = _lookup_age(adult_age, INDIVID_OVRIGT_PER_AGE)
        if partner_age is not None:
            total += _lookup_age(partner_age, INDIVID_OVRIGT_PER_AGE)
        for c_age in children_ages:
            total += _lookup_age(c_age, INDIVID_OVRIGT_PER_AGE)
        return int(round(total * _INDIV_ANDELAR[indiv_andelar_key]))

    # === Gemensamma kostnader (hushållsnivå) ===
    if "förbruk" in lower or "forbruk" in lower:
        return _gemensamt_for("förbrukningsvaror", persons)
    if "hemutr" in lower or "möbler" in lower or "mobler" in lower:
        return _gemensamt_for("hemutrustning", persons)
    if "internet" in lower or "bredband" in lower or "mobil" in lower or "telefon" in lower:
        return _gemensamt_for("internet och mobil", persons)
    if "media" in lower or "streaming" in lower or "abonnemang" in lower:
        return _gemensamt_for("övriga medietjänster", persons)
    if "el" in lower and "elektricitet" not in lower and len(lower) <= 20:
        # "el" / "hushållsel" / "elräkning" — undvik "bil" eller "elementarskola"
        if any(t in lower for t in ("hushåll", "elräkn", "elnät", "elavtal", "elhandel")) or lower.strip() == "el":
            return _gemensamt_for("hushållsel", persons)
    if "hushållsel" in lower or "elräkn" in lower:
        return _gemensamt_for("hushållsel", persons)
    if "vatten" in lower or "avlopp" in lower:
        # Hyresrätt har ofta vatten i hyran — då sätt 0
        if housing_type == "hyresratt":
            return 0
        return _gemensamt_for("vatten och avlopp", persons)
    if "hemförsäkr" in lower or "hemforsakr" in lower:
        return _gemensamt_for("hemförsäkring", persons)

    # === Transport (heuristik per familjestorlek) ===
    if "transport" in lower or "resor" in lower or " sl" in lower or lower in ("sl", "sj"):
        if children_ages or partner_age is not None:
            return 1_500
        return 970

    return None


def kv_minimum_for_student(
    category: str,
    profile: object,
) -> Optional[int]:
    """Wrappar `kv_minimum_for_household` med fält från en
    StudentProfile-master-DB-rad (school.models.StudentProfile)
    eller dataclass med samma fält. Saknas fält antas singel 25 år."""
    if profile is None:
        return lookup_minimum(category)
    age = int(getattr(profile, "age", None) or 25)
    fam_status = (getattr(profile, "family_status", "") or "").lower()
    children_ages = list(getattr(profile, "children_ages", []) or [])
    housing_type = (getattr(profile, "housing_type", "hyresratt") or "hyresratt").lower()

    partner_age: int | None = None
    if fam_status in ("sambo", "gift", "partner", "familj_med_barn"):
        # Antar partner är samma åldersgrupp ±0 år (saknas i master-DB)
        partner_age = age
    return kv_minimum_for_household(
        category,
        adult_age=age,
        partner_age=partner_age,
        children_ages=children_ages,
        housing_type=housing_type,
    )
