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


def seed_profession_agreements(session: Session) -> int:
    """Mappa de 17 yrkena från profile_fixtures till avtal.

    Tom i C2a — fylls i C2c när alla avtal är seedade.
    """
    return 0  # stub, fylls i C2c
