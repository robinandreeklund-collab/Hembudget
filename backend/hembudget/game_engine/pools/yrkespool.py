"""Yrkespool · 30 representativa svenska yrken med 2026-data.

Källor:
- SCB Strukturlönestatistik 2024 (~3 % uppjustering för 2026)
- SSYK-2012 4-siffrig yrkeskod
- Arbetsförmedlingens prognos 2024–2026

Kompetenskoppling använder samma key:s som de 14 system-kompetenserna
i school::Competency.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal


EducationLevel = Literal[
    "ingen", "gymnasium", "yh", "hogskola", "doktor",
]

ArchetypeKey = Literal[
    "random",
    "vard_underskoterska", "vard_sjukskoterska",
    "it_konsult_junior", "it_konsult_senior", "it_systemutvecklare",
    "butiksbitrade", "kassorska", "lar_grundskola", "lar_vikarie",
    "snickare", "elektriker", "lastbilschaufför",
    "ekonom", "kock", "polis", "brandman", "personlig_assistent",
    "anstalld_kommun", "studerande_gymnasium",
]


@dataclass
class Yrke:
    """En realistisk svensk yrkesprofil för 2026."""

    key: str
    display: str
    ssyk: str                          # 4-siffrig yrkeskod
    monthly_gross_min: int             # SEK
    monthly_gross_median: int
    monthly_gross_max: int
    education_level: EducationLevel
    experience_years_required: tuple[int, int]  # (min, max för rolling)
    competency_match: list[str]        # Kompetens-keys yrket bygger
    weight_per_level: dict[int, float]  # Vikt per startnivå (1-3)
    collective_agreement: str | None
    description: str
    archetype: ArchetypeKey            # Mappar till lärar-val
    realistic_career_paths: list[str]  # Vad eleven kan utvecklas till
    physical_demand: int = 5           # 1-10 · påverkar hälsa-axel
    schedule_irregularity: int = 5     # 1-10 · OB, skift, jour


# === POOL ===

YRKESPOOL: list[Yrke] = [
    # --- VÅRD & OMSORG ---
    Yrke(
        key="underskoterska",
        display="Undersköterska, hemsjukvård",
        ssyk="5321",
        monthly_gross_min=26500,
        monthly_gross_median=28800,
        monthly_gross_max=32200,
        education_level="gymnasium",
        experience_years_required=(0, 5),
        competency_match=["health", "social"],
        weight_per_level={1: 1.2, 2: 1.0, 3: 0.7},
        collective_agreement="kommunal_vard",
        description=(
            "Vårdar äldre och sjuka i hemmet eller på boende. "
            "Schemabundet, OB-tillägg vanligt."
        ),
        archetype="vard_underskoterska",
        realistic_career_paths=["specialistundersköterska", "sjukskoterska"],
        physical_demand=8,
        schedule_irregularity=8,
    ),
    Yrke(
        key="sjukskoterska",
        display="Sjuksköterska",
        ssyk="2221",
        monthly_gross_min=36500,
        monthly_gross_median=41000,
        monthly_gross_max=47500,
        education_level="hogskola",
        experience_years_required=(0, 8),
        competency_match=["health", "social", "safety"],
        weight_per_level={1: 0.7, 2: 1.0, 3: 1.0},
        collective_agreement="vardforbundet",
        description=(
            "Legitimerad omvårdnadsspecialist. Hög kompetenskrav, "
            "schemabundet, ofta OB."
        ),
        archetype="vard_sjukskoterska",
        realistic_career_paths=["specialistsjukskoterska", "vårdchef"],
        physical_demand=7,
        schedule_irregularity=8,
    ),
    Yrke(
        key="personlig_assistent",
        display="Personlig assistent",
        ssyk="5322",
        monthly_gross_min=24000,
        monthly_gross_median=26500,
        monthly_gross_max=29500,
        education_level="ingen",
        experience_years_required=(0, 3),
        competency_match=["health", "social"],
        weight_per_level={1: 1.3, 2: 0.8, 3: 0.5},
        collective_agreement="kfo_assistans",
        description=(
            "Hjälper personer med funktionsnedsättning i vardagen. "
            "Vanligt deltidsjobb."
        ),
        archetype="personlig_assistent",
        realistic_career_paths=["arbetsledare assistans", "underskoterska"],
        physical_demand=6,
        schedule_irregularity=7,
    ),

    # --- IT & TEKNIK ---
    Yrke(
        key="it_konsult_junior",
        display="IT-konsult, junior",
        ssyk="2512",
        monthly_gross_min=35000,
        monthly_gross_median=41500,
        monthly_gross_max=49000,
        education_level="yh",
        experience_years_required=(0, 2),
        competency_match=["safety", "economy"],
        weight_per_level={1: 0.6, 2: 1.0, 3: 1.2},
        collective_agreement="almega_it",
        description=(
            "Utvecklar mjukvara åt klienter. Stor flexibilitet, "
            "ofta hybrid-arbete."
        ),
        archetype="it_konsult_junior",
        realistic_career_paths=["senior konsult", "tech lead"],
        physical_demand=2,
        schedule_irregularity=4,
    ),
    Yrke(
        key="it_konsult_senior",
        display="IT-konsult, senior",
        ssyk="2512",
        monthly_gross_min=52000,
        monthly_gross_median=64000,
        monthly_gross_max=82000,
        education_level="yh",
        experience_years_required=(5, 15),
        competency_match=["safety", "economy"],
        weight_per_level={1: 0.2, 2: 0.7, 3: 1.5},
        collective_agreement="almega_it",
        description=(
            "Erfaren utvecklare som leder projekt. Hög lön, "
            "ofta egen firma-möjlighet."
        ),
        archetype="it_konsult_senior",
        realistic_career_paths=["arkitekt", "egenföretagare"],
        physical_demand=2,
        schedule_irregularity=4,
    ),
    Yrke(
        key="it_systemutvecklare",
        display="Systemutvecklare (anställd)",
        ssyk="2512",
        monthly_gross_min=38000,
        monthly_gross_median=45000,
        monthly_gross_max=58000,
        education_level="hogskola",
        experience_years_required=(0, 10),
        competency_match=["safety", "economy"],
        weight_per_level={1: 0.7, 2: 1.0, 3: 1.0},
        collective_agreement="unionen_tech",
        description=(
            "Anställd utvecklare hos produktbolag. Stabilt, "
            "förmåner, mindre flexibilitet än konsult."
        ),
        archetype="it_konsult_junior",
        realistic_career_paths=["tech lead", "engineering manager"],
        physical_demand=2,
        schedule_irregularity=3,
    ),

    # --- HANDEL & SERVICE ---
    Yrke(
        key="butiksbitrade",
        display="Butiksbiträde, dagligvaruhandel",
        ssyk="5223",
        monthly_gross_min=23800,
        monthly_gross_median=25800,
        monthly_gross_max=28500,
        education_level="gymnasium",
        experience_years_required=(0, 5),
        competency_match=["social"],
        weight_per_level={1: 1.3, 2: 0.7, 3: 0.4},
        collective_agreement="handels",
        description=(
            "Kassa, hyllpåfyllning, kundservice. Vanligt första-jobbet "
            "eller kvällstjänst."
        ),
        archetype="butiksbitrade",
        realistic_career_paths=["butikschef", "dagligvaruchef"],
        physical_demand=6,
        schedule_irregularity=7,
    ),
    Yrke(
        key="kassorska",
        display="Kassörska",
        ssyk="5230",
        monthly_gross_min=23500,
        monthly_gross_median=25500,
        monthly_gross_max=28000,
        education_level="gymnasium",
        experience_years_required=(0, 3),
        competency_match=["social"],
        weight_per_level={1: 1.4, 2: 0.6, 3: 0.3},
        collective_agreement="handels",
        description="Kundbetalning + enklare service. Typiskt deltidsjobb.",
        archetype="kassorska",
        realistic_career_paths=["butiksbitrade", "kundtjanstchef"],
        physical_demand=4,
        schedule_irregularity=7,
    ),
    Yrke(
        key="kock",
        display="Kock, restaurang",
        ssyk="5120",
        monthly_gross_min=27500,
        monthly_gross_median=30800,
        monthly_gross_max=36500,
        education_level="gymnasium",
        experience_years_required=(0, 8),
        competency_match=["social"],
        weight_per_level={1: 1.0, 2: 1.0, 3: 0.8},
        collective_agreement="hrf",
        description=(
            "Tillagar mat på restaurang. Stress-tunga middagspass, "
            "OB på helger."
        ),
        archetype="kock",
        realistic_career_paths=["sous-chef", "köksmästare", "egen krog"],
        physical_demand=8,
        schedule_irregularity=9,
    ),
    Yrke(
        key="servitor",
        display="Servitör",
        ssyk="5131",
        monthly_gross_min=24500,
        monthly_gross_median=27000,
        monthly_gross_max=32000,
        education_level="ingen",
        experience_years_required=(0, 5),
        competency_match=["social"],
        weight_per_level={1: 1.3, 2: 0.8, 3: 0.5},
        collective_agreement="hrf",
        description=(
            "Restaurang-service. Dricks vanligt på finrestaurang. "
            "Kvälls- och helgarbete."
        ),
        archetype="kock",
        realistic_career_paths=["hovmästare", "restaurangägare"],
        physical_demand=7,
        schedule_irregularity=9,
    ),

    # --- BYGG & TRANSPORT ---
    Yrke(
        key="snickare",
        display="Snickare, bygg",
        ssyk="7115",
        monthly_gross_min=30000,
        monthly_gross_median=34800,
        monthly_gross_max=41500,
        education_level="gymnasium",
        experience_years_required=(0, 15),
        competency_match=["safety", "economy"],
        weight_per_level={1: 1.0, 2: 1.0, 3: 0.9},
        collective_agreement="byggnads",
        description=(
            "Bygger och renoverar hus. Ofta resor mellan arbetsplatser, "
            "ackordslön möjlig."
        ),
        archetype="snickare",
        realistic_career_paths=["arbetsledare", "egen firma"],
        physical_demand=9,
        schedule_irregularity=4,
    ),
    Yrke(
        key="elektriker",
        display="Elektriker",
        ssyk="7411",
        monthly_gross_min=31500,
        monthly_gross_median=36500,
        monthly_gross_max=44000,
        education_level="gymnasium",
        experience_years_required=(0, 15),
        competency_match=["safety", "economy"],
        weight_per_level={1: 0.9, 2: 1.0, 3: 1.0},
        collective_agreement="seko_el",
        description=(
            "Installerar och underhåller elsystem. Certifierad, "
            "stark efterfrågan."
        ),
        archetype="snickare",
        realistic_career_paths=["arbetsledare", "egen firma"],
        physical_demand=7,
        schedule_irregularity=5,
    ),
    Yrke(
        key="lastbilschauffor",
        display="Lastbilschaufför",
        ssyk="8332",
        monthly_gross_min=28500,
        monthly_gross_median=32500,
        monthly_gross_max=38500,
        education_level="gymnasium",
        experience_years_required=(0, 20),
        competency_match=["safety"],
        weight_per_level={1: 1.0, 2: 1.0, 3: 0.9},
        collective_agreement="transport",
        description=(
            "Kör lastbil i regional eller fjärrtrafik. Långa pass, "
            "borta från familjen ibland."
        ),
        archetype="lastbilschaufför",
        realistic_career_paths=["transportledare", "egen åkare"],
        physical_demand=5,
        schedule_irregularity=8,
    ),
    Yrke(
        key="bussforare",
        display="Bussförare, kollektivtrafik",
        ssyk="8331",
        monthly_gross_min=26500,
        monthly_gross_median=29500,
        monthly_gross_max=34000,
        education_level="gymnasium",
        experience_years_required=(0, 15),
        competency_match=["safety", "social"],
        weight_per_level={1: 1.1, 2: 0.9, 3: 0.7},
        collective_agreement="transport_buss",
        description="Kör buss i tätort. Skiftarbete, OB.",
        archetype="lastbilschaufför",
        realistic_career_paths=["arbetsledare", "trafikplanerare"],
        physical_demand=4,
        schedule_irregularity=9,
    ),

    # --- UTBILDNING ---
    Yrke(
        key="lar_grundskola",
        display="Lärare, grundskola 4-6",
        ssyk="2330",
        monthly_gross_min=33500,
        monthly_gross_median=37800,
        monthly_gross_max=43500,
        education_level="hogskola",
        experience_years_required=(0, 25),
        competency_match=["social", "safety"],
        weight_per_level={1: 0.7, 2: 1.0, 3: 1.0},
        collective_agreement="lf_skolverket",
        description=(
            "Undervisar 10-12-åringar. Stress-tunga perioder vid prov, "
            "men långa lov."
        ),
        archetype="lar_grundskola",
        realistic_career_paths=["förstelärare", "rektor"],
        physical_demand=4,
        schedule_irregularity=3,
    ),
    Yrke(
        key="lar_vikarie",
        display="Lärar-vikarie",
        ssyk="2310",
        monthly_gross_min=24500,
        monthly_gross_median=28000,
        monthly_gross_max=33500,
        education_level="gymnasium",
        experience_years_required=(0, 5),
        competency_match=["social"],
        weight_per_level={1: 1.4, 2: 0.7, 3: 0.3},
        collective_agreement="lf_skolverket",
        description="Vikarierar för lärare. Tidsbegränsade kontrakt, osäkra timmar.",
        archetype="lar_vikarie",
        realistic_career_paths=["lärar-utbildning", "fast tjänst"],
        physical_demand=4,
        schedule_irregularity=6,
    ),
    Yrke(
        key="forskollarare",
        display="Förskollärare",
        ssyk="2342",
        monthly_gross_min=30500,
        monthly_gross_median=34500,
        monthly_gross_max=39500,
        education_level="hogskola",
        experience_years_required=(0, 20),
        competency_match=["social", "health"],
        weight_per_level={1: 0.9, 2: 1.0, 3: 0.8},
        collective_agreement="lf_skolverket",
        description="Pedagogisk verksamhet med 1-5-åringar. Skön men fysisk vardag.",
        archetype="lar_grundskola",
        realistic_career_paths=["specialpedagog", "rektor"],
        physical_demand=6,
        schedule_irregularity=3,
    ),

    # --- EKONOMI & ADMIN ---
    Yrke(
        key="ekonom_controller",
        display="Ekonom / Controller",
        ssyk="2411",
        monthly_gross_min=38000,
        monthly_gross_median=46500,
        monthly_gross_max=58000,
        education_level="hogskola",
        experience_years_required=(0, 15),
        competency_match=["economy", "safety"],
        weight_per_level={1: 0.5, 2: 0.9, 3: 1.2},
        collective_agreement="unionen",
        description=(
            "Bokslut, budget, rapportering. Kontorsjobb med bra "
            "arbetsmiljö."
        ),
        archetype="ekonom",
        realistic_career_paths=["CFO", "controller-chef"],
        physical_demand=2,
        schedule_irregularity=2,
    ),
    Yrke(
        key="redovisningskonsult",
        display="Redovisningskonsult",
        ssyk="3313",
        monthly_gross_min=32500,
        monthly_gross_median=38000,
        monthly_gross_max=46500,
        education_level="yh",
        experience_years_required=(0, 15),
        competency_match=["economy"],
        weight_per_level={1: 0.8, 2: 1.0, 3: 1.0},
        collective_agreement="unionen",
        description=(
            "Bokföring och bokslut åt småföretag. "
            "Hög efterfrågan, period-stress vid årsbokslut."
        ),
        archetype="ekonom",
        realistic_career_paths=["auktoriserad redovisningskonsult", "egen byrå"],
        physical_demand=2,
        schedule_irregularity=4,
    ),

    # --- OFFENTLIG SEKTOR ---
    Yrke(
        key="polis",
        display="Polis",
        ssyk="3411",
        monthly_gross_min=32500,
        monthly_gross_median=37000,
        monthly_gross_max=44500,
        education_level="hogskola",
        experience_years_required=(0, 20),
        competency_match=["safety", "social"],
        weight_per_level={1: 0.7, 2: 1.0, 3: 1.0},
        collective_agreement="polisforbundet",
        description=(
            "Polis i yttre eller inre tjänst. OB, helger, "
            "psykiskt krävande."
        ),
        archetype="polis",
        realistic_career_paths=["kommissarie", "specialpolis"],
        physical_demand=8,
        schedule_irregularity=9,
    ),
    Yrke(
        key="brandman",
        display="Brandman",
        ssyk="5411",
        monthly_gross_min=28500,
        monthly_gross_median=32000,
        monthly_gross_max=37500,
        education_level="gymnasium",
        experience_years_required=(0, 25),
        competency_match=["safety", "health"],
        weight_per_level={1: 0.9, 2: 1.0, 3: 0.8},
        collective_agreement="kommunal",
        description=(
            "Räddningstjänst i kommun. Skifttjänst, "
            "fysiskt krävande, jourtid."
        ),
        archetype="brandman",
        realistic_career_paths=["styrkeledare", "brandinspektör"],
        physical_demand=10,
        schedule_irregularity=10,
    ),
    Yrke(
        key="anstalld_kommun",
        display="Handläggare, kommun",
        ssyk="3343",
        monthly_gross_min=29500,
        monthly_gross_median=33500,
        monthly_gross_max=39500,
        education_level="hogskola",
        experience_years_required=(0, 20),
        competency_match=["economy", "social"],
        weight_per_level={1: 0.9, 2: 1.0, 3: 0.9},
        collective_agreement="kommunal_kontor",
        description=(
            "Administration på kommunkontor. Stabilt, "
            "rimliga arbetstider."
        ),
        archetype="anstalld_kommun",
        realistic_career_paths=["enhetschef", "förvaltningschef"],
        physical_demand=2,
        schedule_irregularity=2,
    ),

    # --- KREATIVT & MEDIA ---
    Yrke(
        key="grafisk_designer",
        display="Grafisk designer",
        ssyk="2166",
        monthly_gross_min=29000,
        monthly_gross_median=34500,
        monthly_gross_max=42000,
        education_level="yh",
        experience_years_required=(0, 12),
        competency_match=["safety"],
        weight_per_level={1: 0.8, 2: 1.0, 3: 1.0},
        collective_agreement="unionen_kreativ",
        description="Designar trycksaker och digital media.",
        archetype="grafisk_designer",
        realistic_career_paths=["AD", "creative director"],
        physical_demand=2,
        schedule_irregularity=3,
    ),

    # --- INDUSTRI ---
    Yrke(
        key="industrioperator",
        display="Industri-operatör",
        ssyk="8160",
        monthly_gross_min=28500,
        monthly_gross_median=32500,
        monthly_gross_max=38500,
        education_level="gymnasium",
        experience_years_required=(0, 25),
        competency_match=["safety"],
        weight_per_level={1: 1.0, 2: 1.0, 3: 0.8},
        collective_agreement="if_metall",
        description="Driver och övervakar produktionsanläggning. 3-skift vanligt.",
        archetype="industrioperator",
        realistic_career_paths=["arbetsledare", "produktionschef"],
        physical_demand=6,
        schedule_irregularity=8,
    ),

    # --- LAGER & LOGISTIK ---
    Yrke(
        key="lagermedarbetare",
        display="Lagermedarbetare",
        ssyk="9333",
        monthly_gross_min=25500,
        monthly_gross_median=28500,
        monthly_gross_max=33000,
        education_level="ingen",
        experience_years_required=(0, 10),
        competency_match=["safety"],
        weight_per_level={1: 1.2, 2: 0.9, 3: 0.6},
        collective_agreement="handels_lager",
        description="Plock, pack och materialhantering. Fysiskt krävande.",
        archetype="lagermedarbetare",
        realistic_career_paths=["arbetsledare", "logistikchef"],
        physical_demand=8,
        schedule_irregularity=6,
    ),

    # --- VÅRD-SPECIALISTER ---
    Yrke(
        key="tandlakare",
        display="Tandläkare",
        ssyk="2261",
        monthly_gross_min=49000,
        monthly_gross_median=58000,
        monthly_gross_max=72000,
        education_level="hogskola",
        experience_years_required=(0, 20),
        competency_match=["health", "safety", "economy"],
        weight_per_level={1: 0.2, 2: 0.6, 3: 1.4},
        collective_agreement="sveriges_tandlakarforbund",
        description="Tandvård i privat eller folktandvården. Hög kompetenskrav.",
        archetype="tandlakare",
        realistic_career_paths=["specialisttandläkare", "egen klinik"],
        physical_demand=4,
        schedule_irregularity=2,
    ),

    # --- STUDERANDE / ENTRY ---
    Yrke(
        key="studerande_gymnasium",
        display="Gymnasie-elev (deltid)",
        ssyk="9999",
        monthly_gross_min=4500,
        monthly_gross_median=7500,
        monthly_gross_max=12000,
        education_level="gymnasium",
        experience_years_required=(0, 0),
        competency_match=["leisure"],
        weight_per_level={1: 1.5, 2: 0.3, 3: 0.0},
        collective_agreement=None,
        description=(
            "Studiebidrag + deltidsjobb. Begränsad arbetstid, "
            "fokus på skolan."
        ),
        archetype="studerande_gymnasium",
        realistic_career_paths=["yh", "hogskola", "praktiskt yrke"],
        physical_demand=3,
        schedule_irregularity=5,
    ),

    # --- FÖRSÄLJNING ---
    Yrke(
        key="saljare_b2b",
        display="Account manager (B2B)",
        ssyk="3322",
        monthly_gross_min=32500,
        monthly_gross_median=42000,
        monthly_gross_max=58000,
        education_level="hogskola",
        experience_years_required=(2, 15),
        competency_match=["social", "economy"],
        weight_per_level={1: 0.5, 2: 1.0, 3: 1.2},
        collective_agreement="unionen_salj",
        description=(
            "Säljer komplexa lösningar till företag. Ofta provisions-"
            "lön — variabel inkomst."
        ),
        archetype="saljare_b2b",
        realistic_career_paths=["säljchef", "key account manager"],
        physical_demand=3,
        schedule_irregularity=5,
    ),

    # --- UNDERHÅLL ---
    Yrke(
        key="vaktmastare",
        display="Vaktmästare / fastighetsskötare",
        ssyk="5152",
        monthly_gross_min=26500,
        monthly_gross_median=29500,
        monthly_gross_max=34000,
        education_level="gymnasium",
        experience_years_required=(0, 25),
        competency_match=["safety"],
        weight_per_level={1: 1.0, 2: 1.0, 3: 0.8},
        collective_agreement="fastighetsanstalldas",
        description="Sköter fastighet, mindre reparationer, snöröjning.",
        archetype="vaktmastare",
        realistic_career_paths=["fastighetsförvaltare"],
        physical_demand=6,
        schedule_irregularity=5,
    ),
]


# === LOOKUP-INDEX ===

YRKE_BY_KEY: dict[str, Yrke] = {y.key: y for y in YRKESPOOL}


# === HJÄLPFUNKTIONER ===


def pick_yrke_by_archetype(
    rng: random.Random,
    archetype: ArchetypeKey,
    starting_level: int,
) -> Yrke:
    """Returnerar ett yrke baserat på arketyp + startnivå.

    Om archetype="random": vikta hela poolen efter level-vikten.
    Annars: filtrera till matchande arketyp(er) och välj.
    """
    if archetype == "random":
        # Vikta hela poolen efter level-vikten
        weights = [
            y.weight_per_level.get(starting_level, 0.5)
            for y in YRKESPOOL
        ]
        return rng.choices(YRKESPOOL, weights=weights, k=1)[0]

    # Filtrera till yrken med matchande arketyp
    matching = [y for y in YRKESPOOL if y.archetype == archetype]
    if not matching:
        # Fallback: random med level-vikt
        return pick_yrke_by_archetype(rng, "random", starting_level)
    weights = [
        y.weight_per_level.get(starting_level, 0.5)
        for y in matching
    ]
    return rng.choices(matching, weights=weights, k=1)[0]
