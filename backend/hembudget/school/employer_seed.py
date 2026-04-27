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
    WorkplaceQuestion,
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
    {
        "code": "byggavtalet_2026",
        "name": "Byggavtalet — Byggnads",
        "union": "Byggnads",
        "employer_org": "Byggföretagen",
        "valid_from": date(2025, 5, 1),
        "valid_to": date(2027, 4, 30),
        "source_url": "https://www.byggnads.se/avtal/",
        "summary_md": (
            "## Byggavtalet — Byggnads / Byggföretagen\n\n"
            "Ditt avtal som anställd i bygg-, anläggnings- eller "
            "snickeriföretag. Förbund: Byggnads. Motpart: Bygg-"
            "företagen.\n\n"
            "**Lön.** Du tjänar antingen på prestationslön (ackord) "
            "eller månadslön. Ackord betalar mer om du är snabb och "
            "noggrann men är osäkrare. Centralt sätts grundlön och "
            "ackordsnormer; lokala förhandlingar avgör potten.\n\n"
            "**Lönerevision.** ~3,2 % 2025; ~3,0 % 2026 i centrala "
            "påslag, plus prestationsbaserade lönelyft.\n\n"
            "**Semester.** 25 dagar; särskild semesterersättning "
            "12 % av lönen utbetalas i juni (eftersom byggjobb varierar "
            "från år till år).\n\n"
            "**Övertid.** 50 % första två timmar; 100 % därefter, "
            "samt helger. Restidsersättning för resor till "
            "arbetsplats utanför hemorten.\n\n"
            "**Sjuklön.** Karens + 80 % dag 2–14.\n\n"
            "**Tjänstepension.** Avtalspension SAF-LO: 4,5 % av "
            "brutto under 7,5 IBB, 30 % över. Du väljer förvaltare "
            "via Fora."
        ),
        "meta": {
            "revision_pct_year": {"2025": 3.2, "2026": 3.0},
            "wage_form": "ackord eller månadslön",
            "vacation_days": 25,
            "vacation_pay_pct": 12,
            "overtime_pct": 50,
            "overtime_pct_extra": 100,
            "travel_compensation": True,
            "sick_pay_steps": [
                {"days": "1", "pct": 0, "note": "karensavdrag"},
                {"days": "2-14", "pct": 80},
                {"days": "15+", "pct": 0, "note": "FK tar över"},
            ],
            "pension_system": "SAF-LO",
            "pension_pct": 4.5,
            "pension_pct_above_75ibb": 30.0,
        },
        "verified_at": None,
    },
    {
        "code": "motorbranschen_2026",
        "name": "Motorbranschavtalet — IF Metall",
        "union": "IF Metall",
        "employer_org": "Motorbranschens Arbetsgivareförbund",
        "valid_from": date(2025, 4, 1),
        "valid_to": date(2027, 3, 31),
        "source_url": "https://www.ifmetall.se/avtal",
        "summary_md": (
            "## Motorbranschavtalet — IF Metall\n\n"
            "Ditt avtal som bilmekaniker, lackerare eller bilplåts"
            "lagare. Förbund: IF Metall. Motpart: Motorbranschens "
            "Arbetsgivareförbund (MAF).\n\n"
            "**Lönerevision.** Industri-märket sätter taket: ~3,0 % "
            "2025 och 2026. Generellt påslag + lokal pott.\n\n"
            "**Semester.** 25 dagar grundregel.\n\n"
            "**Övertid.** 50 % vardagar de första två timmarna; "
            "100 % därefter och helger. OB-tillägg för kvällar "
            "och nätter.\n\n"
            "**Sjuklön.** Karens + 80 % dag 2–14.\n\n"
            "**Tjänstepension.** SAF-LO Avtalspension: 4,5 % av "
            "brutto under 7,5 IBB, 30 % över. Förvaltas via Fora."
        ),
        "meta": {
            "revision_pct_year": {"2025": 3.0, "2026": 3.0},
            "vacation_days": 25,
            "overtime_pct": 50,
            "overtime_pct_extra": 100,
            "sick_pay_steps": [
                {"days": "1", "pct": 0, "note": "karensavdrag"},
                {"days": "2-14", "pct": 80},
                {"days": "15+", "pct": 0, "note": "FK tar över"},
            ],
            "pension_system": "SAF-LO",
            "pension_pct": 4.5,
            "pension_pct_above_75ibb": 30.0,
        },
        "verified_at": None,
    },
    {
        "code": "detaljhandel_2026",
        "name": "Detaljhandelsavtalet — Handels",
        "union": "Handelsanställdas Förbund",
        "employer_org": "Svensk Handel",
        "valid_from": date(2025, 4, 1),
        "valid_to": date(2027, 3, 31),
        "source_url": "https://www.handels.se/avtal",
        "summary_md": (
            "## Detaljhandelsavtalet — Handels\n\n"
            "Ditt avtal som butiksmedarbetare, säljare eller "
            "lagerarbetare i detaljhandeln. Förbund: Handels. "
            "Motpart: Svensk Handel.\n\n"
            "**Lönerevision.** ~3,0 % 2025 och 2026 i centrala "
            "påslag. Lokala förhandlingar fördelar.\n\n"
            "**Semester.** 25 dagar.\n\n"
            "**OB-tillägg.** Stort i detaljhandeln eftersom "
            "öppettider sträcker sig över kvällar och helger. "
            "Kvällar +50 %; lördagar +100 %; söndagar och röda "
            "dagar +100 %. Dessa tillägg utgör ofta 10–20 % av "
            "totala lönen.\n\n"
            "**Övertid.** 50 % vardagar; 100 % helger.\n\n"
            "**Sjuklön.** Karens + 80 % dag 2–14.\n\n"
            "**Tjänstepension.** SAF-LO Avtalspension: 4,5 % av "
            "brutto under 7,5 IBB, 30 % över. Förvaltas via Fora."
        ),
        "meta": {
            "revision_pct_year": {"2025": 3.0, "2026": 3.0},
            "vacation_days": 25,
            "ob_evening_pct": 50,
            "ob_saturday_pct": 100,
            "ob_sunday_pct": 100,
            "overtime_pct": 50,
            "overtime_pct_weekend": 100,
            "sick_pay_steps": [
                {"days": "1", "pct": 0, "note": "karensavdrag"},
                {"days": "2-14", "pct": 80},
                {"days": "15+", "pct": 0, "note": "FK tar över"},
            ],
            "pension_system": "SAF-LO",
            "pension_pct": 4.5,
            "pension_pct_above_75ibb": 30.0,
        },
        "verified_at": None,
    },
    {
        "code": "installation_2026",
        "name": "Installationsavtalet — Elektrikerna",
        "union": "Svenska Elektrikerförbundet",
        "employer_org": "Installatörsföretagen",
        "valid_from": date(2025, 5, 1),
        "valid_to": date(2027, 4, 30),
        "source_url": "https://www.sef.se/avtal",
        "summary_md": (
            "## Installationsavtalet — Elektrikerna\n\n"
            "Ditt avtal som installations-elektriker. Förbund: "
            "Svenska Elektrikerförbundet (SEF). Motpart: "
            "Installatörsföretagen.\n\n"
            "**Lön.** Liknande Bygg: ackord eller månadslön. "
            "Höga grundlöner relativt andra LO-avtal eftersom "
            "yrket kräver certifiering.\n\n"
            "**Lönerevision.** ~3,0 % 2025 och 2026.\n\n"
            "**Semester.** 25 dagar.\n\n"
            "**Övertid.** 50 % första två timmar; 100 % därefter "
            "och helger. Restidsersättning för resor utanför "
            "hemorten.\n\n"
            "**Sjuklön.** Karens + 80 % dag 2–14.\n\n"
            "**Tjänstepension.** SAF-LO Avtalspension: 4,5 % av "
            "brutto under 7,5 IBB, 30 % över."
        ),
        "meta": {
            "revision_pct_year": {"2025": 3.0, "2026": 3.0},
            "wage_form": "ackord eller månadslön",
            "vacation_days": 25,
            "overtime_pct": 50,
            "overtime_pct_extra": 100,
            "travel_compensation": True,
            "sick_pay_steps": [
                {"days": "1", "pct": 0, "note": "karensavdrag"},
                {"days": "2-14", "pct": 80},
                {"days": "15+", "pct": 0, "note": "FK tar över"},
            ],
            "pension_system": "SAF-LO",
            "pension_pct": 4.5,
            "pension_pct_above_75ibb": 30.0,
        },
        "verified_at": None,
    },
    {
        "code": "grona_riks_2026",
        "name": "Gröna Riks — HRF",
        "union": "Hotell- och Restaurang Facket (HRF)",
        "employer_org": "Visita",
        "valid_from": date(2025, 4, 1),
        "valid_to": date(2027, 3, 31),
        "source_url": "https://www.hrf.net/avtal",
        "summary_md": (
            "## Gröna Riks — HRF / Visita\n\n"
            "Ditt avtal som kock, servitör eller barista i hotell- "
            "och restaurangbranschen. Förbund: HRF. Motpart: "
            "Visita.\n\n"
            "**Lön.** Branschen har låga grundlöner men höga OB-"
            "tillägg eftersom restauranger har sena kvällar och "
            "helger.\n\n"
            "**Lönerevision.** ~3,0 % 2025; 2026 förhandlas.\n\n"
            "**Semester.** 25 dagar.\n\n"
            "**OB-tillägg.** Vardagar efter 18.00 +25 %; nätter "
            "+50 %; helger +75–100 %. Kan utgöra 15–25 % av "
            "totallönen.\n\n"
            "**Övertid.** 50 % vardagar; 100 % helger och natt.\n\n"
            "**Sjuklön.** Karens + 80 % dag 2–14.\n\n"
            "**Tjänstepension.** SAF-LO Avtalspension: 4,5 % av "
            "brutto under 7,5 IBB."
        ),
        "meta": {
            "revision_pct_year": {"2025": 3.0, "2026": 3.0},
            "vacation_days": 25,
            "ob_evening_pct": 25,
            "ob_night_pct": 50,
            "ob_weekend_pct": 100,
            "overtime_pct": 50,
            "overtime_pct_weekend": 100,
            "sick_pay_steps": [
                {"days": "1", "pct": 0, "note": "karensavdrag"},
                {"days": "2-14", "pct": 80},
                {"days": "15+", "pct": 0, "note": "FK tar över"},
            ],
            "pension_system": "SAF-LO",
            "pension_pct": 4.5,
            "pension_pct_above_75ibb": 30.0,
        },
        "verified_at": None,
    },
    {
        "code": "smaforetag_inget_avtal",
        "name": "Småföretag utan kollektivavtal",
        "union": "—",
        "employer_org": "—",
        "valid_from": date(2025, 1, 1),
        "valid_to": None,
        "source_url": None,
        "summary_md": (
            "## Småföretag utan kollektivavtal\n\n"
            "Du jobbar på en arbetsplats som inte har tecknat "
            "kollektivavtal. Det betyder att din lön och dina "
            "förmåner regleras av lagen — inte av ett avtal "
            "förhandlat mellan facket och arbetsgivar-"
            "organisationen.\n\n"
            "**Lön.** Inget centralt revisionsutrymme. Höjningar "
            "förhandlas direkt med din chef. Du har rätt att veta "
            "vad jobbet betalar — men ingen avtalsmodell håller "
            "lönen i takt med branschen.\n\n"
            "**Semester.** 25 dagar enligt semesterlagen — det "
            "är minimum. Inga extra dagar för ålder.\n\n"
            "**Sjuklön.** Karens + 80 % dag 2–14 enligt sjuk"
            "lönelagen. Dag 15 tar Försäkringskassan över.\n\n"
            "**Övertid.** Du har rätt till övertidsersättning "
            "enligt arbetstidslagen, men nivån är inte avtalad. "
            "Förhandla själv med chefen.\n\n"
            "**Tjänstepension.** **Ingen tjänstepension** utöver "
            "den allmänna pensionen. Det är en stor skillnad: en "
            "kollektiv-anställd får ~4,5 % av lönen extra varje "
            "månad in på pensionen som du inte ser. På 30 års "
            "arbete blir det hundratusentals kronor.\n\n"
            "**Vad kan du göra?** Pensionsspara själv (ISK eller "
            "kapitalförsäkring) — det rekommenderas särskilt för "
            "anställda utan tjänstepension. Eller kräva att "
            "arbetsgivaren betalar in motsvarande belopp."
        ),
        "meta": {
            "revision_pct_year": {},
            "revision_note": "ingen central revision — individuell förhandling",
            "vacation_days": 25,
            "overtime_pct": None,
            "overtime_note": "lagstadgad rätt, ingen avtalsnivå",
            "sick_pay_steps": [
                {"days": "1", "pct": 0, "note": "karensavdrag (lag)"},
                {"days": "2-14", "pct": 80, "note": "sjuklönelagen"},
                {"days": "15+", "pct": 0, "note": "FK tar över"},
            ],
            "pension_system": None,
            "pension_pct": 0.0,
            "pension_note": "saknas — viktig att kompensera privat",
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


# Yrke → avtal-mappning. Måste matcha Profession.title i
# profile_fixtures.PROFESSIONS exakt. employer_pattern är substring som
# matchas mot StudentProfile.employer; tom = default för yrket.
# Specifika patterns kommer först (mer specifikt vinner — vi sorterar
# i seedaren så att längre pattern matchas först).
PROFESSION_MAPPINGS: list[dict] = [
    # Vård och omsorg → Kommunal HÖK
    {"profession": "Undersköterska", "agreement_code": "hok_kommunal_2026"},
    {"profession": "Barnskötare", "agreement_code": "hok_kommunal_2026"},

    # Lärare → Lärar-HÖK
    {"profession": "Lärare F-3", "agreement_code": "hok_larare_2026"},
    {"profession": "Förskollärare", "agreement_code": "hok_larare_2026"},

    # Sjukvård → Vårdförbundet HÖK
    {"profession": "Sjuksköterska", "agreement_code": "hok_vard_2026"},

    # IT-konsult → IT-tjänstemannaavtalet
    {"profession": "IT-konsult", "agreement_code": "tjm_it_2026"},

    # Bygg → Byggavtalet
    {"profession": "Snickare", "agreement_code": "byggavtalet_2026"},

    # El → Installationsavtalet
    {"profession": "Elektriker", "agreement_code": "installation_2026"},

    # Bil → Motorbranschavtalet
    {"profession": "Bilmekaniker", "agreement_code": "motorbranschen_2026"},

    # Detaljhandel → Handels (default), några employers helt utan avtal
    {"profession": "Butiksmedarbetare", "agreement_code": "detaljhandel_2026"},

    # Säljare: tjänstemanna-default; ICA/Bauhaus etc. har detaljhandel
    {"profession": "Säljare", "agreement_code": "tjm_general_2026"},
    {
        "profession": "Säljare",
        "employer_pattern": "ICA",
        "agreement_code": "detaljhandel_2026",
    },
    {
        "profession": "Säljare",
        "employer_pattern": "Bauhaus",
        "agreement_code": "detaljhandel_2026",
    },
    {
        "profession": "Säljare",
        "employer_pattern": "Elgiganten",
        "agreement_code": "detaljhandel_2026",
    },
    {
        "profession": "Säljare",
        "employer_pattern": "Mediamarkt",
        "agreement_code": "detaljhandel_2026",
    },

    # HRF — Kock + Barista (några specifika utan avtal)
    {"profession": "Kock", "agreement_code": "grona_riks_2026"},
    {
        "profession": "Kock",
        "employer_pattern": "Egen verksamhet",
        "agreement_code": "smaforetag_inget_avtal",
    },
    {"profession": "Barista", "agreement_code": "grona_riks_2026"},

    # Frisör — Cutters/Klippoteket har avtal, "Egen verksamhet" inte
    {
        "profession": "Frisör",
        "agreement_code": "detaljhandel_2026",
        "notes": "Frisörföretagarna ansluter till Handels-/Detaljhandelsavtalet",
    },
    {
        "profession": "Frisör",
        "employer_pattern": "Egen verksamhet",
        "agreement_code": "smaforetag_inget_avtal",
    },

    # Tjänstemanna-yrken (Almega-area)
    {"profession": "Ekonomiassistent", "agreement_code": "tjm_general_2026"},
    {"profession": "Projektledare", "agreement_code": "tjm_general_2026"},
    {"profession": "Marknadsassistent", "agreement_code": "tjm_general_2026"},
]


def seed_profession_agreements(session: Session) -> int:
    """Idempotent seed av yrke→avtal-mappningar.

    Sorterar mappningar så längre employer_pattern kommer först — gör
    inga skillnad i seedningen i sig (vi adderar alla rader), men
    läsare av tabellen som vill matcha 'mest specifik först' kan
    sortera på `LENGTH(employer_pattern) DESC`.

    Returnerar antal nya rader.
    """
    # Bygg lookup code → CollectiveAgreement.id
    code_to_id: dict[str, int] = {
        ag.code: ag.id for ag in session.query(CollectiveAgreement).all()
    }

    existing = {
        (pa.profession, pa.employer_pattern)
        for pa in session.query(ProfessionAgreement).all()
    }
    added = 0
    for m in PROFESSION_MAPPINGS:
        prof = m["profession"]
        pattern = m.get("employer_pattern", "")
        key = (prof, pattern)
        if key in existing:
            continue
        agreement_id = code_to_id.get(m["agreement_code"])
        # Defensivt: om koden saknas (t.ex. seedet kördes innan
        # avtalen) — hoppa över, kör om vid nästa boot.
        if agreement_id is None and m["agreement_code"] != "smaforetag_inget_avtal":
            continue
        # För "småföretag" sätter vi agreement_id om den finns, annars
        # behåller vi NULL — pedagogiskt OK eftersom UI:n hanterar
        # båda fallen.
        if m["agreement_code"] == "smaforetag_inget_avtal":
            agreement_id = code_to_id.get("smaforetag_inget_avtal")
        # Pension-rate: läs default från avtalets meta om finns
        pension_pct = None
        for ag in session.query(CollectiveAgreement).filter(
            CollectiveAgreement.code == m["agreement_code"],
        ).all():
            pp = ag.meta.get("pension_pct") if ag.meta else None
            if pp is not None:
                pension_pct = Decimal(str(pp))
                break
        session.add(ProfessionAgreement(
            profession=prof,
            employer_pattern=pattern,
            agreement_id=agreement_id,
            pension_rate_pct=pension_pct,
            notes=m.get("notes"),
        ))
        added += 1
    session.flush()
    return added


# Slumpade arbetsplats-frågor som skickas till eleven från
# arbetsgivaren. Pedagogiskt fokus: konkreta vardagssituationer där
# eleven får träna omdöme. Inga politiska frågor, inga åldersolämpliga
# ämnen. Varje option har ett delta som speglar HUR arbetsgivaren
# typiskt skulle reagera — inte vad som är "moraliskt rätt".
WORKPLACE_QUESTIONS: list[dict] = [
    {
        "code": "sick_call_in_001",
        "scenario_md": (
            "Du vaknar med halsont och feber. Klockan är 06:30 och ditt "
            "arbetspass börjar 07:30. Vad gör du?"
        ),
        "options": [
            {
                "text": "Ringer chefen direkt och sjukanmäler dig.",
                "delta": 2,
                "explanation": (
                    "Tidig sjukanmälan ger chefen tid att ordna ersättare. "
                    "Det visar respekt för verksamheten och dina kollegor."
                ),
            },
            {
                "text": "Skickar ett SMS strax innan passet börjar.",
                "delta": -2,
                "explanation": (
                    "Sent meddelande gör det svårt att ordna ersättning — "
                    "kollegor blir överbelastade. Ring tidigt nästa gång."
                ),
            },
            {
                "text": "Går till jobbet ändå för att inte verka svag.",
                "delta": -3,
                "explanation": (
                    "Smitta sprids till kollegor och kunder. Sjukfrånvaro "
                    "är inte ett karaktärsfel — det är att skydda andra."
                ),
            },
            {
                "text": "Säger inget och hoppas att ingen märker.",
                "delta": -5,
                "explanation": (
                    "Olovlig frånvaro är allvarligt. Det förstör tillit "
                    "och kan leda till skriftlig varning eller uppsägning."
                ),
            },
        ],
        "correct_path_md": (
            "Bra praxis: ring (inte SMS) chefen så tidigt som möjligt. "
            "Säg kort vad som hänt och när du tror du kan vara tillbaka. "
            "Om du är borta över sju dagar krävs läkarintyg enligt "
            "sjuklönelagen — då hör Försäkringskassan av sig."
        ),
        "tags": ["sjukfrånvaro", "kommunikation"],
        "difficulty": 1,
    },
    {
        "code": "vab_001",
        "scenario_md": (
            "Ditt barn på fyra år har magsjuka och kan inte gå till "
            "förskolan. Du har ett viktigt möte 09:00 där du ska "
            "presentera kvartalsrapporten. Vad gör du?"
        ),
        "options": [
            {
                "text": (
                    "Ringer chefen, förklarar situationen och föreslår "
                    "att en kollega tar mötet eller att det skjuts upp."
                ),
                "delta": 1,
                "explanation": (
                    "VAB är en lagstadgad rätt för dig som förälder. "
                    "Att proaktivt föreslå lösning visar ansvar."
                ),
            },
            {
                "text": (
                    "Lämnar barnet hos en granne du knappt känner och "
                    "går till mötet."
                ),
                "delta": -3,
                "explanation": (
                    "Dåligt omdöme — barnet är sjukt och behöver dig. "
                    "Och om grannen ringer dig under mötet ändå förlorar "
                    "du fokus."
                ),
            },
            {
                "text": (
                    "Sjukanmäler dig själv istället för att VAB:a, "
                    "eftersom det 'ser bättre ut'."
                ),
                "delta": -5,
                "explanation": (
                    "Det är försäkringsbedrägeri — Försäkringskassan "
                    "betalar ut fel ersättning. Kan leda till "
                    "polisanmälan."
                ),
            },
            {
                "text": (
                    "VAB:ar och skickar i förväg en utförlig skriftlig "
                    "sammanfattning + alla siffror till chefen."
                ),
                "delta": 3,
                "explanation": (
                    "Bästa praxis: dokumentera så någon annan kan ta "
                    "över. Visar professionalism trots oplanerad frånvaro."
                ),
            },
        ],
        "correct_path_md": (
            "VAB (vård av barn) ger ersättning från Försäkringskassan upp "
            "till 120 dagar per år och barn under 12. Du anmäler själv "
            "till FK och berättar för chefen. Det är inte sjukfrånvaro — "
            "det är en helt separat rätt."
        ),
        "tags": ["VAB", "föräldraskap", "kommunikation"],
        "difficulty": 2,
    },
    {
        "code": "late_meeting_001",
        "scenario_md": (
            "Tunnelbanan står stilla och du inser att du kommer 15 "
            "minuter sent till ett team-möte. Vad gör du?"
        ),
        "options": [
            {
                "text": (
                    "Skickar ett snabbt meddelande i Teams: 'T-bana står, "
                    "är där om 15 min.' Hoppar in när det går."
                ),
                "delta": 1,
                "explanation": (
                    "Förvarning gör att kollegorna kan börja utan dig "
                    "eller skjuta upp dina punkter."
                ),
            },
            {
                "text": (
                    "Säger inget — slipper det krångliga och hoppas "
                    "ingen märker."
                ),
                "delta": -3,
                "explanation": (
                    "Tystnad signalerar slarv. Mötesdeltagare väntar "
                    "och blir frustrerade."
                ),
            },
            {
                "text": (
                    "Skyller på kollegan när du kommer fram för att "
                    "dölja förseningen."
                ),
                "delta": -4,
                "explanation": (
                    "Att skylla på andra för egna förseningar är "
                    "tillitskrossande. Kollegor noterar."
                ),
            },
            {
                "text": (
                    "Tar en taxi på företagets kort utan att fråga."
                ),
                "delta": -2,
                "explanation": (
                    "Personliga utlägg på företagets pengar utan "
                    "godkännande är gråzon — fråga först."
                ),
            },
        ],
        "correct_path_md": (
            "Punktlighet är en signal: 'jag respekterar din tid'. När "
            "tåg eller buss står är det inte ditt fel — men det är ditt "
            "ansvar att meddela. Kort SMS eller chatt-meddelande räcker."
        ),
        "tags": ["punktlighet", "kommunikation"],
        "difficulty": 1,
    },
    {
        "code": "honest_mistake_001",
        "scenario_md": (
            "Du har skickat fel siffror till en viktig kund. Det märks "
            "först nästa dag, och bara du har sett felet. Vad gör du?"
        ),
        "options": [
            {
                "text": (
                    "Berättar för chefen direkt och föreslår en plan "
                    "för att rätta till det."
                ),
                "delta": 4,
                "explanation": (
                    "Att äga sina misstag är en av de mest värdefulla "
                    "egenskaperna. Chefer minns vem som är ärlig."
                ),
            },
            {
                "text": (
                    "Försöker rätta till det själv utan att säga något, "
                    "i hopp om att kunden inte märker."
                ),
                "delta": -3,
                "explanation": (
                    "Risken är att felet upptäcks ändå — och då blir "
                    "du också den som dolde det. Dubbel förlust."
                ),
            },
            {
                "text": (
                    "Skyller felet på en kollega som råkade kontrollera "
                    "siffrorna."
                ),
                "delta": -6,
                "explanation": (
                    "Att skylla på oskyldiga är allvarligt. Om det "
                    "kommer fram kan du sägas upp av personliga skäl."
                ),
            },
            {
                "text": (
                    "Säger inget och hoppas att kunden inte hör av sig."
                ),
                "delta": -4,
                "explanation": (
                    "Passivitet vid fel är samma sak som dölja. Det "
                    "blir värre ju längre tid som går."
                ),
            },
        ],
        "correct_path_md": (
            "Ingen är felfri. Den som äger sina misstag tidigt får "
            "förtroende. 'Jag har gjort fel — så här tänker jag rätta "
            "det' är en mening som lyfter dig i chefens ögon."
        ),
        "tags": ["ärlighet", "ansvar"],
        "difficulty": 2,
    },
    {
        "code": "cover_for_colleague_001",
        "scenario_md": (
            "En kollega ber dig täcka för henom under hennes pass nästa "
            "vecka — hon säger att hon är 'lite trött' och vill ta "
            "ledigt utan att sjukanmäla sig. Vad gör du?"
        ),
        "options": [
            {
                "text": (
                    "Säger nej men föreslår att hon tar en semesterdag "
                    "eller pratar med chefen istället."
                ),
                "delta": 3,
                "explanation": (
                    "Att hjälpa en kollega är fint — men inte genom "
                    "att medverka till oärlighet mot arbetsgivaren."
                ),
            },
            {
                "text": (
                    "Ja, du täcker för henne. Kollegial solidaritet är "
                    "viktigt."
                ),
                "delta": -3,
                "explanation": (
                    "Du blir medskyldig till olovlig frånvaro. Om det "
                    "uppdagas drabbas båda — och chefen tappar tillit "
                    "till dig."
                ),
            },
            {
                "text": (
                    "Säger ja och tar 500 kr av henne för besväret."
                ),
                "delta": -4,
                "explanation": (
                    "Du sätter dig i en utpressningsbar position och "
                    "har dessutom medverkat till bedrägeri mot "
                    "arbetsgivaren."
                ),
            },
            {
                "text": (
                    "Skvallrar för chefen utan att prata med kollegan "
                    "först."
                ),
                "delta": -1,
                "explanation": (
                    "Bättre att först säga till kollegan: 'jag tänker "
                    "inte täcka för dig, prata med chefen'. Skvaller "
                    "utan förvarning skadar relationen i onödan."
                ),
            },
        ],
        "correct_path_md": (
            "Lojalitet mot kollegor är viktigt — men inte gränslös. "
            "Att hjälpa någon att ljuga gör dig medskyldig. Bättre att "
            "vägledning: 'jag förstår att du behöver vila, men prata "
            "med chefen om en ledig dag'."
        ),
        "tags": ["lojalitet", "ärlighet", "konflikt"],
        "difficulty": 3,
    },
]


def seed_workplace_questions(session: Session) -> int:
    """Idempotent seed av arbetsplats-frågor. Returnerar antal nya rader."""
    existing = {q.code for q in session.query(WorkplaceQuestion).all()}
    added = 0
    for q in WORKPLACE_QUESTIONS:
        if q["code"] in existing:
            continue
        session.add(WorkplaceQuestion(
            code=q["code"],
            scenario_md=q["scenario_md"],
            options=q["options"],
            correct_path_md=q["correct_path_md"],
            tags=q.get("tags"),
            difficulty=q.get("difficulty", 1),
        ))
        added += 1
    session.flush()
    return added


def seed_all(session: Session) -> dict:
    """Seedare för hela arbetsgivar-paketet. Kör i rätt ordning:
    avtal först, sedan mappningar (som behöver avtals-IDn), sedan
    arbetsplats-frågor (oberoende av övriga).
    """
    n_ag = seed_collective_agreements(session)
    n_pm = seed_profession_agreements(session)
    n_q = seed_workplace_questions(session)
    return {
        "agreements_added": n_ag,
        "profession_mappings_added": n_pm,
        "workplace_questions_added": n_q,
    }
