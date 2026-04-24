"""Konsumentverkets riktlinjer för hushållskostnader 2026.

Källa: kostnadsberakningar-hushallskostnader-2026-sv-kov_tga_32d.pdf
Används pedagogiskt som "vad är ett rimligt budgetbelopp för X?" i
budget-setup-steget. Värdena är kr/månad.

Vi exponerar dem via /school/konsumentverket-endpointen + använder dem
för att beräkna en rekommenderad startbudget i onboardingen.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# Källwebbplats — länk visas i budget-setup-vyn
SOURCE_URL = "https://www.konsumentverket.se/ekonomi/vilka-kostnader-har-ett-hushall/"
SOURCE_TITLE = "Konsumentverket – Hushållskostnader 2026"


# Individuell matkostnad per åldersgrupp (kr/mån, alla måltider hemma)
MAT_HEMMA_PER_AGE: list[tuple[range, int]] = [
    (range(0, 1),    1_030),  # 0 år
    (range(1, 4),    1_100),  # 1-3 år
    (range(4, 7),    1_710),  # 4-6 år
    (range(7, 11),   2_130),  # 7-10 år
    (range(11, 15),  2_650),  # 11-14 år
    (range(15, 18),  3_050),  # 15-17 år
    (range(18, 25),  2_840),  # 18-24 år
    (range(25, 51),  2_730),  # 25-50 år
    (range(51, 71),  2_490),  # 51-70 år
    (range(71, 121), 2_450),  # 71+ år
]

# Övriga individuella kostnader (kläder, fritid, hygien, försäkring,
# barnutrustning) per åldersgrupp — summa-rad enligt PDF
INDIVID_OVRIGT_PER_AGE: list[tuple[range, int]] = [
    (range(0, 1),    2_920),
    (range(1, 4),    2_730),
    (range(4, 7),    2_000),
    (range(7, 11),   2_090),
    (range(11, 15),  2_070),
    (range(15, 18),  2_390),
    (range(18, 25),  2_200),
    (range(25, 51),  2_140),
    (range(51, 71),  2_070),
    (range(71, 121), 1_940),
]

# Hushållets gemensamma kostnader per månad — efter antal personer
GEMENSAMT_PER_PERSONER: dict[str, list[int]] = {
    # nyckel = kategori, värde = [1pers, 2pers, 3pers, 4pers, 5pers, 6pers, 7pers]
    "förbrukningsvaror":     [200, 300, 460, 560, 690, 790, 890],
    "hemutrustning":         [920, 1_030, 1_310, 1_560, 1_790, 1_950, 2_060],
    "internet och mobil":    [1_000, 1_230, 1_460, 1_690, 1_920, 2_150, 2_380],
    "övriga medietjänster":  [640, 690, 720, 720, 720, 720, 840],
    "hushållsel":            [400, 530, 700, 870, 1_010, 1_150, 1_280],
    "vatten och avlopp":     [220, 440, 650, 880, 1_080, 1_310, 1_530],
    "hemförsäkring":         [180, 210, 240, 270, 300, 330, 360],
}


def _lookup_age(age: int, table: list[tuple[range, int]]) -> int:
    for r, v in table:
        if age in r:
            return v
    return table[-1][1]


def _lookup_persons(category: str, n: int) -> int:
    arr = GEMENSAMT_PER_PERSONER.get(category, [])
    if not arr:
        return 0
    idx = max(0, min(len(arr) - 1, n - 1))
    return arr[idx]


@dataclass
class BudgetSuggestion:
    """Rekommenderad budget per kategori (kr/mån).

    Baseras på Konsumentverkets 2026-värden + profil-specifika kostnader
    (boende, transport, lån). Eleven kan justera i UI:n.
    """
    mat: int                    # all individuell mat
    individuellt_ovrigt: int    # kläder, fritid, hygien, försäkring
    boende: int                 # från profilens housing_monthly
    el: int
    bredband_mobil: int
    medietjanster: int
    forbrukningsvaror: int
    hemutrustning: int
    vatten_avlopp: int          # 0 om hyresrätt (ofta i hyran)
    hemforsakring: int
    transport: int              # SL/bensin/bilförsäkring
    lan_amortering_ranta: int   # bolån + ev. billån + studielån
    sparande: int               # rekommendation (10% av netto)
    nojen_marginal: int         # buffert för restaurang/nöje/shopping

    @property
    def total(self) -> int:
        return sum([
            self.mat, self.individuellt_ovrigt, self.boende, self.el,
            self.bredband_mobil, self.medietjanster, self.forbrukningsvaror,
            self.hemutrustning, self.vatten_avlopp, self.hemforsakring,
            self.transport, self.lan_amortering_ranta, self.sparande,
            self.nojen_marginal,
        ])

    def to_dict(self) -> dict:
        return {
            "mat": self.mat,
            "individuellt_ovrigt": self.individuellt_ovrigt,
            "boende": self.boende,
            "el": self.el,
            "bredband_mobil": self.bredband_mobil,
            "medietjanster": self.medietjanster,
            "forbrukningsvaror": self.forbrukningsvaror,
            "hemutrustning": self.hemutrustning,
            "vatten_avlopp": self.vatten_avlopp,
            "hemforsakring": self.hemforsakring,
            "transport": self.transport,
            "lan_amortering_ranta": self.lan_amortering_ranta,
            "sparande": self.sparande,
            "nojen_marginal": self.nojen_marginal,
            "total": self.total,
        }


def suggest_budget(
    *,
    adult_age: int,
    partner_age: int | None,
    children_ages: list[int],
    housing_type: Literal["hyresratt", "bostadsratt", "villa"],
    housing_monthly: int,
    has_mortgage: bool,
    has_car_loan: bool,
    has_student_loan: bool,
    net_salary_monthly: int,
) -> BudgetSuggestion:
    """Räkna fram rekommenderad startbudget för hushållet."""
    persons = 1 + (1 if partner_age else 0) + len(children_ages)

    # Mat = summa per person (enl Konsumentverket)
    mat_total = _lookup_age(adult_age, MAT_HEMMA_PER_AGE)
    if partner_age is not None:
        mat_total += _lookup_age(partner_age, MAT_HEMMA_PER_AGE)
    for c_age in children_ages:
        mat_total += _lookup_age(c_age, MAT_HEMMA_PER_AGE)

    # Individuellt övrigt
    indiv_total = _lookup_age(adult_age, INDIVID_OVRIGT_PER_AGE)
    if partner_age is not None:
        indiv_total += _lookup_age(partner_age, INDIVID_OVRIGT_PER_AGE)
    for c_age in children_ages:
        indiv_total += _lookup_age(c_age, INDIVID_OVRIGT_PER_AGE)

    el = _lookup_persons("hushållsel", persons)
    bredband = _lookup_persons("internet och mobil", persons)
    media = _lookup_persons("övriga medietjänster", persons)
    forbruk = _lookup_persons("förbrukningsvaror", persons)
    hemutr = _lookup_persons("hemutrustning", persons)
    vatten = (
        _lookup_persons("vatten och avlopp", persons)
        if housing_type != "hyresratt" else 0
    )
    hemfors = _lookup_persons("hemförsäkring", persons)

    # Transport — uppskattning beroende på familjesituation
    if children_ages or partner_age:
        transport = 1_500   # ofta bil + SL
    else:
        transport = 950     # mest SL

    # Lån — om profilen har bolån/billån/studielån
    lan = 0
    if has_mortgage:
        # Förenklat: 4% ränta på 1.5M = 5000/mån + amort 1500/mån
        lan += 6_500
    if has_car_loan:
        lan += 2_500
    if has_student_loan:
        lan += 1_500

    # Sparande = 10% av nettolön (rekommendation)
    sparande = int(round(net_salary_monthly * 0.10, -2))

    # Nöjen/marginal = vad som blir kvar (bör vara positivt!)
    fasta = (
        mat_total + indiv_total + housing_monthly + el + bredband + media
        + forbruk + hemutr + vatten + hemfors + transport + lan + sparande
    )
    nojen = max(0, net_salary_monthly - fasta)
    # Om hushållet skuldsatts mer än lönen täcker, sätter vi nöjen=0 så
    # eleven själv ser obalansen i siffrorna.

    return BudgetSuggestion(
        mat=mat_total,
        individuellt_ovrigt=indiv_total,
        boende=housing_monthly,
        el=el,
        bredband_mobil=bredband,
        medietjanster=media,
        forbrukningsvaror=forbruk,
        hemutrustning=hemutr,
        vatten_avlopp=vatten,
        hemforsakring=hemfors,
        transport=transport,
        lan_amortering_ranta=lan,
        sparande=sparande,
        nojen_marginal=nojen,
    )
