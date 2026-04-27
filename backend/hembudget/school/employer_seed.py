"""Idempotent seedare för kollektivavtal + yrke→avtal-mappningar.

Avtals-summaries är pedagogiska utkast — siffrorna baseras på publika
avtals-PDF:er men ska faktagranskas av domänkunnig innan release.
`verified_at` lämnas tom tills granskning skett; UI:n visar disclaimer
"Senast verifierat: —" så elever förstår att det är preliminärt.

Idé 1 i dev_v1.md. Anropas vid uppstart från main.py likt
seed_event_templates.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from .employer_models import (
    CollectiveAgreement,
    ProfessionAgreement,
)


# Avtals-data. Varje rad är ett dict — vi tar inte med id (auto-PK).
# `meta` följer schemat:
#   revision_pct_year: dict[year_str, pct_float]
#   vacation_days: int (lagstadgat 25 är default)
#   overtime_pct: int (procentpåslag på OB/övertid)
#   sick_pay_steps: list[{days, pct}]
#   pension_system: str ("ITP1" | "KAP-KL" | "AKAP-KR" | "SAF-LO" | "BTP" | None)
#   pension_pct: float (% av brutto under 7,5 IBB)
#   notes_md: str (interna kommentarer för faktagranskning)
AGREEMENTS: list[dict] = [
    {
        "code": "hok_kommunal_2026",
        "name": "HÖK 24 — Kommunal",
        "union": "Kommunal",
        "employer_org": "SKR + Sobona",
        "valid_from": date(2024, 5, 1),
        "valid_to": date(2027, 3, 31),
        "source_url": "https://www.kommunal.se/avtal2024",
        "summary_md": (
            "## HÖK 24 — Kommunal\n\n"
            "Ditt avtal som anställd inom kommun, region eller kommunalt "
            "bolag. Löper 2024-05-01 till 2027-03-31. Förbund: Kommunal. "
            "Motpart: SKR (Sveriges Kommuner och Regioner) och Sobona.\n\n"
            "**Lönerevision.** Avtalet ger generella påslag varje år: "
            "2025 ~3,3 %, 2026 ~3,1 %. Det finns både en lägstanivå "
            "(individgaranti) och ett potten-utrymme för fördelning "
            "som chefen sätter utifrån prestation. Du kan alltså få "
            "mer ELLER mindre än snittet beroende på samtalet.\n\n"
            "**Semester.** 25 dagar grundregel; 31 dagar från det år du "
            "fyller 40, 32 dagar från 50. Lagen ger 25 minst.\n\n"
            "**Sjuklön.** Dag 1 = karensavdrag (motsvarar ~20 % av en "
            "veckas lön). Dag 2–14 betalar arbetsgivaren 80 %. "
            "Dag 15+ tar Försäkringskassan över.\n\n"
            "**Övertid.** Vardagar 50 % påslag; helger och natt 100 %. "
            "OB-tillägg gäller utöver schemalagd tid.\n\n"
            "**Tjänstepension.** AKAP-KR (för dig född 1986 eller "
            "senare) eller KAP-KL (äldre). Arbetsgivaren betalar "
            "6 % av brutto upp till 7,5 IBB, 31,5 % över. Den växer "
            "till en pension du får från ~65 år."
        ),
        "meta": {
            "revision_pct_year": {"2025": 3.3, "2026": 3.1},
            "vacation_days": 25,
            "vacation_days_age_40": 31,
            "vacation_days_age_50": 32,
            "overtime_pct": 50,
            "overtime_pct_weekend": 100,
            "sick_pay_steps": [
                {"days": "1", "pct": 0, "note": "karensavdrag"},
                {"days": "2-14", "pct": 80},
                {"days": "15+", "pct": 0, "note": "FK tar över"},
            ],
            "pension_system": "AKAP-KR",
            "pension_pct": 6.0,
            "pension_pct_above_75ibb": 31.5,
        },
        "verified_at": None,  # AVVAKTAR FAKTAGRANSKNING
    },
    {
        "code": "tjm_it_2026",
        "name": "Tjänstemannaavtalet IT — Unionen + Akavia",
        "union": "Unionen + Akavia + Sveriges Ingenjörer",
        "employer_org": "IT&Telekomföretagen (Almega)",
        "valid_from": date(2025, 4, 1),
        "valid_to": date(2027, 3, 31),
        "source_url": "https://www.unionen.se/avtal/it-telekom",
        "summary_md": (
            "## Tjänstemannaavtalet IT — Unionen / Akavia\n\n"
            "Ditt avtal som tjänsteman inom IT- och telekomsektorn. "
            "Avtalsförbund: Unionen, Akavia, Sveriges Ingenjörer. "
            "Motpart: IT&Telekomföretagen (del av Almega).\n\n"
            "**Lönerevision.** Sifferlöst på principen: "
            "marknadsmässiga löner sätts lokalt mellan chef och "
            "medarbetare. Industri-märket (~3 %/år) brukar vara "
            "riktmärket. Inga centrala individgaranti — det är ditt "
            "lönesamtal som avgör.\n\n"
            "**Semester.** 25 dagar; många bolag erbjuder 30 efter "
            "viss anställningstid (kollektivavtalad förmån utöver "
            "lagen).\n\n"
            "**Sjuklön.** Dag 1 = karensavdrag. Dag 2–14 = 80 %. "
            "Dag 15+ Försäkringskassan; många IT-bolag fyller på "
            "till ~90 % under en period (företagsförmån, ej avtal).\n\n"
            "**Övertid.** I praktiken är de flesta IT-tjänstemän "
            "övertidsbefriade — du har 'fri arbetstid' med högre "
            "grundlön i utbyte (typiskt +3-5 dagar extra semester).\n\n"
            "**Tjänstepension.** ITP1 standard. Arbetsgivaren betalar "
            "4,5 % av brutto upp till 7,5 IBB, 30 % över. Du väljer "
            "själv förvaltare via Collectum (max 50 % av summan får "
            "vara aktiefond)."
        ),
        "meta": {
            "revision_pct_year": {"2025": 3.0, "2026": 3.0},
            "revision_note": "sifferlöst — riktmärke industri-märket",
            "vacation_days": 25,
            "vacation_days_common_extra": 30,
            "overtime_pct": 50,
            "overtime_typically_waived": True,
            "sick_pay_steps": [
                {"days": "1", "pct": 0, "note": "karensavdrag"},
                {"days": "2-14", "pct": 80},
                {"days": "15+", "pct": 0, "note": "FK tar över"},
            ],
            "pension_system": "ITP1",
            "pension_pct": 4.5,
            "pension_pct_above_75ibb": 30.0,
        },
        "verified_at": None,
    },
    {
        "code": "hok_larare_2026",
        "name": "HÖK 21 — Lärarna",
        "union": "Lärarförbundet + Lärarnas Riksförbund (Sveriges Lärare)",
        "employer_org": "SKR + Sobona",
        "valid_from": date(2024, 4, 1),
        "valid_to": date(2026, 3, 31),
        "source_url": "https://www.sverigeslarare.se/avtal",
        "summary_md": (
            "## HÖK — Lärarna (Sveriges Lärare)\n\n"
            "Ditt avtal som lärare i kommunal eller regional grund-, "
            "gymnasie- eller särskola. Förbund: Sveriges Lärare "
            "(sammanslagningen av Lärarförbundet och LR sedan 2023). "
            "Motpart: SKR och Sobona.\n\n"
            "**Lönerevision.** Generellt påslag + lokal pott. 2025 "
            "~3,4 %, 2026 ~3,0 %. För lärare finns en uttalad "
            "ambition att lyfta läraryrkets snittlön — ditt "
            "lönesamtal kan ge mer än potten om du visar "
            "professionell utveckling, kollegialt ledarskap eller "
            "ämnesfördjupning.\n\n"
            "**Semester.** 25 dagar grund; 31 dagar från 40 års "
            "ålder; 32 dagar från 50. Lärarens semester ligger "
            "till stor del förlagd över sommaren.\n\n"
            "**Arbetstid.** Reglerad arbetstid: ca 1 360 h/år "
            "(ferieanställning) eller 1 700 h/år (semester-"
            "anställning). Förtroendetid utöver det.\n\n"
            "**Sjuklön.** Identisk med Kommunal HÖK: dag 1 karens, "
            "dag 2–14 80 %, FK från dag 15.\n\n"
            "**Tjänstepension.** AKAP-KR (yngre) / KAP-KL (äldre). "
            "6 % av brutto under 7,5 IBB; 31,5 % över."
        ),
        "meta": {
            "revision_pct_year": {"2025": 3.4, "2026": 3.0},
            "vacation_days": 25,
            "vacation_days_age_40": 31,
            "vacation_days_age_50": 32,
            "annual_hours_ferie": 1360,
            "annual_hours_semester": 1700,
            "overtime_pct": 50,
            "sick_pay_steps": [
                {"days": "1", "pct": 0, "note": "karensavdrag"},
                {"days": "2-14", "pct": 80},
                {"days": "15+", "pct": 0, "note": "FK tar över"},
            ],
            "pension_system": "AKAP-KR",
            "pension_pct": 6.0,
            "pension_pct_above_75ibb": 31.5,
        },
        "verified_at": None,
    },
    {
        "code": "hok_vard_2026",
        "name": "HÖK 22 — Vårdförbundet",
        "union": "Vårdförbundet",
        "employer_org": "SKR + Sobona",
        "valid_from": date(2022, 4, 1),
        "valid_to": date(2025, 3, 31),
        "source_url": "https://www.vardforbundet.se/avtal",
        "summary_md": (
            "## HÖK — Vårdförbundet\n\n"
            "Ditt avtal som sjuksköterska, barnmorska, biomedicinsk "
            "analytiker eller röntgensjuksköterska anställd i region "
            "eller kommunal vård. Förbund: Vårdförbundet. Motpart: "
            "SKR och Sobona.\n\n"
            "**Lönerevision.** Generellt + lokal pott. 2025 ~3,2 %, "
            "2026 ~3,0 %. Avtalet har långsiktig löneutveckling "
            "som mål — chefer kan ge tydliga lönelyft för "
            "specialistutbildning eller nattens svåraste pass.\n\n"
            "**Semester.** 25 dagar grund; 31 från 40; 32 från 50.\n\n"
            "**OB-tillägg.** För kvällar, nätter, helger och röda "
            "dagar tillkommer OB-tillägg utöver grundlön — kan "
            "vara 10–100 % av timlönen beroende på tid. Här tjänar "
            "många nattsjuksköterskor en betydande del av total-"
            "lönen.\n\n"
            "**Sjuklön.** Som övriga HÖK-avtal: karens dag 1, "
            "80 % dag 2–14.\n\n"
            "**Tjänstepension.** AKAP-KR / KAP-KL. 6 % under 7,5 "
            "IBB, 31,5 % över."
        ),
        "meta": {
            "revision_pct_year": {"2025": 3.2, "2026": 3.0},
            "vacation_days": 25,
            "vacation_days_age_40": 31,
            "vacation_days_age_50": 32,
            "ob_evening_pct": 22,
            "ob_night_pct": 50,
            "ob_weekend_pct": 100,
            "overtime_pct": 50,
            "sick_pay_steps": [
                {"days": "1", "pct": 0, "note": "karensavdrag"},
                {"days": "2-14", "pct": 80},
                {"days": "15+", "pct": 0, "note": "FK tar över"},
            ],
            "pension_system": "AKAP-KR",
            "pension_pct": 6.0,
            "pension_pct_above_75ibb": 31.5,
        },
        "verified_at": None,
    },
    {
        "code": "tjm_general_2026",
        "name": "Tjänstemannaavtalet (generellt) — Unionen / Almega",
        "union": "Unionen + Akademikerförbunden",
        "employer_org": "Almega",
        "valid_from": date(2025, 4, 1),
        "valid_to": date(2027, 3, 31),
        "source_url": "https://www.unionen.se/avtal",
        "summary_md": (
            "## Tjänstemannaavtalet (generellt)\n\n"
            "Det breda tjänstemanna-avtalet för privatanställda inom "
            "tjänstesektorn — projektledare, ekonomiassistent, "
            "marknadsförare, säljare med tjänstemannaroll. Förbund: "
            "Unionen, Akavia, Sveriges Ingenjörer. Motpart: Almega.\n\n"
            "**Lönerevision.** Sifferlöst (eller siffersatt med ~3 % "
            "i centrala potten). Lokal förhandling avgör hur fördelas. "
            "Ditt lönesamtal är där höjningen sätts.\n\n"
            "**Semester.** 25 dagar.\n\n"
            "**Sjuklön.** Karens + 80 % dag 2–14, sedan FK.\n\n"
            "**Övertid.** 50 % vardagar, 100 % helger. Många "
            "tjänstemän är övertidsbefriade mot extra semester "
            "(typiskt 3–5 dagar).\n\n"
            "**Tjänstepension.** ITP1: 4,5 % av brutto under 7,5 "
            "IBB, 30 % över. Du väljer förvaltare via Collectum."
        ),
        "meta": {
            "revision_pct_year": {"2025": 3.0, "2026": 3.0},
            "revision_note": "sifferlöst eller centralt ~3%",
            "vacation_days": 25,
            "overtime_pct": 50,
            "overtime_pct_weekend": 100,
            "sick_pay_steps": [
                {"days": "1", "pct": 0, "note": "karensavdrag"},
                {"days": "2-14", "pct": 80},
                {"days": "15+", "pct": 0, "note": "FK tar över"},
            ],
            "pension_system": "ITP1",
            "pension_pct": 4.5,
            "pension_pct_above_75ibb": 30.0,
        },
        "verified_at": None,
    },
]


def seed_collective_agreements(session: Session) -> int:
    """Idempotent seed av kollektivavtal. Returnerar antal nya rader."""
    existing = {a.code for a in session.query(CollectiveAgreement).all()}
    added = 0
    for ag in AGREEMENTS:
        if ag["code"] in existing:
            continue
        session.add(CollectiveAgreement(
            code=ag["code"],
            name=ag["name"],
            union=ag["union"],
            employer_org=ag["employer_org"],
            valid_from=ag["valid_from"],
            valid_to=ag.get("valid_to"),
            source_url=ag.get("source_url"),
            summary_md=ag["summary_md"],
            meta=ag["meta"],
            verified_at=ag.get("verified_at"),
        ))
        added += 1
    session.flush()
    return added


def seed_profession_agreements(session: Session) -> int:
    """Mappa de 17 yrkena från profile_fixtures till avtal.

    Tom i C2a — fylls i C2c när alla avtal är seedade.
    """
    return 0  # stub, fylls i C2c
