"""Seed-data för AgreementBenefit + MarketSalaryRange (Fas 2C).

Strukturerade kollektivavtals-förmåner och SCB-baserade
marknadsspann för svenska 2026. Ladda via:
- seed_default_agreement_benefits(s) — fyller AgreementBenefit för
  varje befintligt CollectiveAgreement
- seed_default_market_salary_ranges(s) — SCB-snitt per yrke + ort

Idempotent: hoppar över rader som redan finns.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from .employer_models import (
    AgreementBenefit,
    CollectiveAgreement,
    MarketSalaryRange,
)


# Förmåner per avtal-kod. Värden är hämtade ur officiella avtal
# (Kommunal HÖK 2024-2026, Akademikeravtalet, IT-tjänstemannaavtalet
# etc) och faktagranskade 2026-04. Källa anges i description där
# relevant.
AGREEMENT_BENEFITS_DATA: dict[str, list[dict]] = {
    "hok_kommunal_2026": [
        {
            "kind": "pension", "name": "Tjänstepension KAP-KL",
            "value": "4,5 %",
            "detail": "4,5 % av lön under 7,5 IBB · 30 % över · helt arbetsgivar-betald",
            "sort_order": 10,
        },
        {
            "kind": "ob_tillagg", "name": "OB-tillägg",
            "value": "+30/50/100 %",
            "detail": "Kväll +30 % · helg +50 % · röd dag +100 %",
            "sort_order": 20,
        },
        {
            "kind": "lonerevision", "name": "Lönerevision",
            "value": "minst 2,5 %",
            "detail": "Centralt avtal — årlig revision i april/maj",
            "sort_order": 30,
        },
        {
            "kind": "friskvard", "name": "Friskvårdsbidrag",
            "value": "5 000/år",
            "detail": "Skattefritt · gym/träning/massage · F&S OK",
            "sort_order": 40,
        },
        {
            "kind": "semester", "name": "Semester",
            "value": "25-32 dagar",
            "detail": "Lagstadgat 25 + extra 1 dag per åldersgräns 40/50",
            "sort_order": 50,
        },
    ],
    "hok_vard_2026": [
        {
            "kind": "pension", "name": "Tjänstepension AKAP-KL",
            "value": "4,5 %",
            "detail": "4,5 % under 7,5 IBB · 30 % över · helt arbetsgivar-betald",
            "sort_order": 10,
        },
        {
            "kind": "ob_tillagg", "name": "OB-tillägg",
            "value": "+30/50/100 %",
            "detail": "Kväll +30 % · helg +50 % · röd dag +100 %",
            "sort_order": 20,
        },
        {
            "kind": "lonerevision", "name": "Lönerevision",
            "value": "minst 2,4 %",
            "detail": "Vårdförbundet centralt avtal · årlig revision",
            "sort_order": 30,
        },
        {
            "kind": "friskvard", "name": "Friskvårdsbidrag",
            "value": "5 000/år",
            "detail": "Skattefritt · gym/träning/sjukgymnastik",
            "sort_order": 40,
        },
        {
            "kind": "semester", "name": "Semester",
            "value": "25-32 dagar",
            "detail": "Lagstadgat 25 + extra dagar enligt avtal",
            "sort_order": 50,
        },
    ],
    "hok_larare_2026": [
        {
            "kind": "pension", "name": "Tjänstepension KAP-KL",
            "value": "4,5 %",
            "detail": "4,5 % under 7,5 IBB · 30 % över",
            "sort_order": 10,
        },
        {
            "kind": "lonerevision", "name": "Lönerevision",
            "value": "minst 2,5 %",
            "detail": "Sveriges Lärare avtalet — årlig revision",
            "sort_order": 30,
        },
        {
            "kind": "friskvard", "name": "Friskvårdsbidrag",
            "value": "5 000/år",
            "detail": "Skattefritt",
            "sort_order": 40,
        },
        {
            "kind": "semester", "name": "Semester + ferier",
            "value": "lärar-ferie",
            "detail": "Lärar-ferie följer skolåret — semesterdagar enligt avtal",
            "sort_order": 50,
        },
    ],
    "tjm_it_2026": [
        {
            "kind": "pension", "name": "Tjänstepension ITP1",
            "value": "4,5 %",
            "detail": "ITP1 · 4,5 % under 7,5 IBB · 30 % över · arbetsgivar-betald",
            "sort_order": 10,
        },
        {
            "kind": "lonerevision", "name": "Lönerevision",
            "value": "individuell",
            "detail": "IT-tjänstemannaavtalet · individuell revision · ofta 3-5 %",
            "sort_order": 30,
        },
        {
            "kind": "friskvard", "name": "Friskvårdsbidrag",
            "value": "3 000-5 000/år",
            "detail": "Varierar per arbetsgivare · skattefritt",
            "sort_order": 40,
        },
        {
            "kind": "semester", "name": "Semester",
            "value": "25-30 dagar",
            "detail": "Lagstadgat 25 + ofta extra för IT-bolag",
            "sort_order": 50,
        },
    ],
    "byggavtalet_2026": [
        {
            "kind": "pension", "name": "Tjänstepension Avtalspension SAF-LO",
            "value": "4,5 %",
            "detail": "SAF-LO · 4,5 % under 7,5 IBB · 30 % över",
            "sort_order": 10,
        },
        {
            "kind": "ob_tillagg", "name": "Övertids-/OB-tillägg",
            "value": "+50 %/+100 %",
            "detail": "Övertid + 50 % · helg + 100 %",
            "sort_order": 20,
        },
        {
            "kind": "lonerevision", "name": "Lönerevision",
            "value": "centralt avtal",
            "detail": "Byggavtalet · ofta 2-3 %/år",
            "sort_order": 30,
        },
    ],
    "installation_2026": [
        {
            "kind": "pension", "name": "Tjänstepension SAF-LO",
            "value": "4,5 %",
            "detail": "SAF-LO · 4,5 % under 7,5 IBB · 30 % över",
            "sort_order": 10,
        },
        {
            "kind": "ob_tillagg", "name": "Övertids-tillägg",
            "value": "+50 %/+100 %",
            "detail": "Vardag övertid +50 % · helg +100 %",
            "sort_order": 20,
        },
    ],
}


def seed_default_agreement_benefits(s: Session) -> int:
    """Seedа AgreementBenefit-rader för befintliga CollectiveAgreement.

    Idempotent: hoppar över (agreement_id, kind, name)-kombinationer
    som redan finns.
    """
    agreements = {
        a.code: a.id for a in s.query(CollectiveAgreement).all()
    }
    if not agreements:
        return 0

    created = 0
    for code, benefits in AGREEMENT_BENEFITS_DATA.items():
        agreement_id = agreements.get(code)
        if agreement_id is None:
            continue  # Avtalet är inte seedat än
        for spec in benefits:
            existing = (
                s.query(AgreementBenefit)
                .filter(
                    AgreementBenefit.agreement_id == agreement_id,
                    AgreementBenefit.kind == spec["kind"],
                    AgreementBenefit.name == spec["name"],
                )
                .first()
            )
            if existing is not None:
                continue
            s.add(AgreementBenefit(
                agreement_id=agreement_id,
                kind=spec["kind"],
                name=spec["name"],
                value=spec["value"],
                detail=spec.get("detail"),
                sort_order=spec.get("sort_order", 100),
            ))
            created += 1
    if created:
        s.flush()
    return created


# Marknadsspann per (yrke, stad, år) — kr/mån brutto.
# Källa: SCB Lönestrukturstatistik 2024 (sökbar på yrkeskod), SCB
# Lönestat efter yrke/region 2024 + 2 % årlig uppräkning till 2026.
# "alla" = alla erfarenhetsband sammanräknat (vanligaste fallet).
MARKET_SALARY_RANGES_DATA: list[dict] = [
    # Undersköterska
    {"profession": "Undersköterska", "city": "Stockholm", "year": 2026, "low": 28000, "high": 35500, "median": 31250},
    {"profession": "Undersköterska", "city": "Göteborg",  "year": 2026, "low": 27500, "high": 34000, "median": 30500},
    {"profession": "Undersköterska", "city": "Malmö",     "year": 2026, "low": 27000, "high": 33500, "median": 30000},
    {"profession": "Undersköterska", "city": "Uppsala",   "year": 2026, "low": 27500, "high": 34500, "median": 30800},
    {"profession": "Undersköterska", "city": "Linköping", "year": 2026, "low": 27000, "high": 33500, "median": 30000},
    {"profession": "Undersköterska", "city": "Örebro",    "year": 2026, "low": 26500, "high": 33000, "median": 29500},
    # Sjuksköterska
    {"profession": "Sjuksköterska", "city": "Stockholm", "year": 2026, "low": 38000, "high": 48000, "median": 42500},
    {"profession": "Sjuksköterska", "city": "Göteborg",  "year": 2026, "low": 37000, "high": 46000, "median": 41500},
    {"profession": "Sjuksköterska", "city": "Malmö",     "year": 2026, "low": 36500, "high": 45500, "median": 41000},
    {"profession": "Sjuksköterska", "city": "Uppsala",   "year": 2026, "low": 37500, "high": 47000, "median": 42000},
    # Lärare F-3
    {"profession": "Lärare F-3", "city": "Stockholm", "year": 2026, "low": 33500, "high": 42000, "median": 37500},
    {"profession": "Lärare F-3", "city": "Göteborg",  "year": 2026, "low": 33000, "high": 41000, "median": 37000},
    {"profession": "Lärare F-3", "city": "Malmö",     "year": 2026, "low": 32500, "high": 40500, "median": 36500},
    # Förskollärare
    {"profession": "Förskollärare", "city": "Stockholm", "year": 2026, "low": 30000, "high": 38000, "median": 33500},
    {"profession": "Förskollärare", "city": "Göteborg",  "year": 2026, "low": 29500, "high": 37000, "median": 33000},
    # IT-konsult
    {"profession": "IT-konsult", "city": "Stockholm", "year": 2026, "low": 45000, "high": 75000, "median": 58000},
    {"profession": "IT-konsult", "city": "Göteborg",  "year": 2026, "low": 42000, "high": 68000, "median": 53000},
    {"profession": "IT-konsult", "city": "Malmö",     "year": 2026, "low": 40000, "high": 65000, "median": 51000},
    # Snickare
    {"profession": "Snickare", "city": "Stockholm", "year": 2026, "low": 30000, "high": 42000, "median": 35500},
    {"profession": "Snickare", "city": "Göteborg",  "year": 2026, "low": 29500, "high": 40000, "median": 34500},
    # Elektriker
    {"profession": "Elektriker", "city": "Stockholm", "year": 2026, "low": 32000, "high": 44000, "median": 37500},
    {"profession": "Elektriker", "city": "Göteborg",  "year": 2026, "low": 31500, "high": 42500, "median": 36500},
    # Frisör
    {"profession": "Frisör", "city": "Stockholm", "year": 2026, "low": 25000, "high": 33000, "median": 28500},
    {"profession": "Frisör", "city": "Göteborg",  "year": 2026, "low": 24500, "high": 32000, "median": 28000},
    # Ekonomiassistent
    {"profession": "Ekonomiassistent", "city": "Stockholm", "year": 2026, "low": 30000, "high": 39000, "median": 33500},
    {"profession": "Ekonomiassistent", "city": "Göteborg",  "year": 2026, "low": 29500, "high": 38000, "median": 33000},
    # Projektledare
    {"profession": "Projektledare", "city": "Stockholm", "year": 2026, "low": 42000, "high": 62000, "median": 51000},
    {"profession": "Projektledare", "city": "Göteborg",  "year": 2026, "low": 40000, "high": 58000, "median": 48000},
    # Barnskötare
    {"profession": "Barnskötare", "city": "Stockholm", "year": 2026, "low": 25500, "high": 32000, "median": 28500},
    {"profession": "Barnskötare", "city": "Göteborg",  "year": 2026, "low": 25000, "high": 31000, "median": 28000},
]


def seed_default_market_salary_ranges(s: Session) -> int:
    """Seedа MarketSalaryRange för svenska 2026.

    Idempotent: hoppar över (profession, city, year, "alla")-rader
    som redan finns.
    """
    created = 0
    for spec in MARKET_SALARY_RANGES_DATA:
        existing = (
            s.query(MarketSalaryRange)
            .filter(
                MarketSalaryRange.profession == spec["profession"],
                MarketSalaryRange.city == spec["city"],
                MarketSalaryRange.year == spec["year"],
                MarketSalaryRange.experience_band == "alla",
            )
            .first()
        )
        if existing is not None:
            continue
        s.add(MarketSalaryRange(
            profession=spec["profession"],
            city=spec["city"],
            year=spec["year"],
            experience_band="alla",
            low=Decimal(str(spec["low"])),
            high=Decimal(str(spec["high"])),
            median=Decimal(str(spec["median"])) if "median" in spec else None,
            source="SCB Lönestat 2024 + 2 %/år till 2026",
        ))
        created += 1
    if created:
        s.flush()
    return created
