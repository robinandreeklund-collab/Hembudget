"""10 fasta branscher för företagsläget.

Pedagogisk principen: istället för att låta eleven skriva fri text
('AB-konsult och hjälp') begränsar vi till 10 branscher som faktiskt
finns på svensk marknad. Varje bransch har metadata som styr:

- pris-baseline (kr/h marknadssnitt)
- typisk marginal (%)
- antal-timmar-per-jobb-spann
- kund-segment-mix (privat / företag / kommun)
- säsong (när är peak)
- equipment-cost (engångskostnad vid start)
- om branschen kräver lokal (fast hyra) eller ej
- pipeline-täthet (offerter / vecka i baseline)

Stad-multipliers ligger i pools/stadspool.py och kombineras med dessa.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


IndustryKey = Literal[
    "it_konsult",
    "webbdesigner",
    "snickare",
    "rormokare",
    "elektriker",
    "frisor",
    "coach",
    "personal_trainer",
    "fotograf",
    "catering",
]


# Säsongs-vikt per månad (12 värden, jan→dec). 1.0 = baseline.
JAMN: list[float] = [1.0] * 12
SOMMAR_TOPP: list[float] = [
    0.7, 0.7, 0.8, 0.9, 1.1, 1.3, 1.4, 1.4, 1.2, 1.0, 0.8, 0.7,
]
VINTER_TOPP: list[float] = [
    1.3, 1.3, 1.1, 1.0, 0.8, 0.6, 0.5, 0.6, 0.8, 1.0, 1.2, 1.4,
]
JAN_TOPP: list[float] = [
    1.6, 1.4, 1.2, 1.0, 0.9, 0.8, 0.7, 0.7, 0.9, 1.0, 1.0, 1.0,
]
SOMMAR_HOST: list[float] = [
    0.8, 0.8, 0.9, 1.0, 1.2, 1.4, 1.4, 1.4, 1.3, 1.2, 0.9, 0.7,
]
HELG_TOPP: list[float] = [
    1.2, 1.0, 1.0, 1.0, 1.1, 1.3, 1.3, 1.2, 1.1, 1.0, 1.2, 1.6,
]


@dataclass(frozen=True)
class Industry:
    """Metadata för en bransch · driver pipeline + pris + tid."""
    key: IndustryKey
    label: str
    short_description: str
    sni_code: str                      # SCB SNI 2007 (5-siffrig)
    # Priser: spann i kr/h (baseline · stockholm-1.0)
    hourly_rate_min: int
    hourly_rate_max: int
    # Marginal · vinst som % av omsättning (matchar realistiska siffror)
    margin_baseline_pct: int           # baseline-mitt
    margin_range_pct: int              # ± från baseline
    # Tids-åtgång per jobb (timmar). Vissa branscher har stora jobb,
    # andra många små.
    time_per_job_hours_min: int
    time_per_job_hours_max: int
    # Kund-segment-mix · summerar till 1.0
    segment_mix_privat: float
    segment_mix_foretag: float
    segment_mix_kommun: float
    # Säsongs-kurva (12 mån-vikter)
    seasonality: list[float] = field(default_factory=lambda: JAMN)
    # Equipment-cost · engångskostnad vid företagsstart (kr)
    equipment_cost_init: int = 0
    # Kräver lokal · fast hyra varje månad
    requires_lokal: bool = False
    monthly_lokal_cost_baseline: int = 0   # om requires_lokal=True
    # Pipeline-täthet · genomsnitt offert-förfrågningar / vecka
    pipeline_per_week_baseline: float = 1.5
    # Stad-anpassning · vissa branscher kräver storstad
    min_city_size: Literal["any", "medium", "large"] = "any"
    # Pedagogisk länk till lärandemål
    learning_focus: str = ""


INDUSTRIES: dict[IndustryKey, Industry] = {
    "it_konsult": Industry(
        key="it_konsult",
        label="IT-konsult",
        short_description=(
            "Webb, integrationer, support, utveckling. Hög marginal "
            "men kräver kompetens-uppdatering hela tiden."
        ),
        sni_code="62020",
        hourly_rate_min=750,
        hourly_rate_max=1400,
        margin_baseline_pct=42,
        margin_range_pct=10,
        time_per_job_hours_min=8,
        time_per_job_hours_max=40,
        segment_mix_privat=0.15,
        segment_mix_foretag=0.65,
        segment_mix_kommun=0.20,
        seasonality=JAMN,
        equipment_cost_init=15_000,        # bra dator + skärmar
        requires_lokal=False,
        pipeline_per_week_baseline=2.0,
        min_city_size="any",
        learning_focus=(
            "Pris-elasticitet · IT-konsult kan kosta från 750 till 1400 "
            "beroende på erfarenhet · pitch-text påverkar acceptans"
        ),
    ),
    "webbdesigner": Industry(
        key="webbdesigner",
        label="Webb- & grafisk designer",
        short_description=(
            "Logo, hemsidor, social media-grafik. Kreativt yrke där "
            "rykte och portfolio är allt."
        ),
        sni_code="74100",
        hourly_rate_min=600,
        hourly_rate_max=1100,
        margin_baseline_pct=38,
        margin_range_pct=12,
        time_per_job_hours_min=6,
        time_per_job_hours_max=30,
        segment_mix_privat=0.20,
        segment_mix_foretag=0.70,
        segment_mix_kommun=0.10,
        seasonality=JAMN,
        equipment_cost_init=22_000,        # Mac + Adobe-licenser första året
        requires_lokal=False,
        pipeline_per_week_baseline=1.8,
        min_city_size="any",
        learning_focus=(
            "Portfolio är kapital · varje levererat projekt är en "
            "referens · prissättning kreativa tjänster"
        ),
    ),
    "snickare": Industry(
        key="snickare",
        label="Snickare / hantverkare",
        short_description=(
            "Renoveringar, kök, altaner, finsnickeri. Stora jobb, "
            "ROT-avdrag för privatkunder."
        ),
        sni_code="43320",
        hourly_rate_min=550,
        hourly_rate_max=850,
        margin_baseline_pct=27,
        margin_range_pct=8,
        time_per_job_hours_min=8,
        time_per_job_hours_max=80,
        segment_mix_privat=0.65,
        segment_mix_foretag=0.30,
        segment_mix_kommun=0.05,
        seasonality=SOMMAR_TOPP,
        equipment_cost_init=45_000,        # Verktyg + transport
        requires_lokal=True,
        monthly_lokal_cost_baseline=2_500,  # mindre förråd
        pipeline_per_week_baseline=1.5,
        min_city_size="any",
        learning_focus=(
            "ROT-avdrag · 30 % på arbetskostnad direkt på fakturan "
            "(privat) · säsongs-cyklicitet"
        ),
    ),
    "rormokare": Industry(
        key="rormokare",
        label="Rörmokare / VVS",
        short_description=(
            "Vatten, värme, sanitet. Akut-uppdrag = höga timpriser, "
            "service-avtal = stadigt flöde."
        ),
        sni_code="43221",
        hourly_rate_min=650,
        hourly_rate_max=1050,
        margin_baseline_pct=32,
        margin_range_pct=8,
        time_per_job_hours_min=4,
        time_per_job_hours_max=16,
        segment_mix_privat=0.60,
        segment_mix_foretag=0.25,
        segment_mix_kommun=0.15,
        seasonality=VINTER_TOPP,
        equipment_cost_init=55_000,
        requires_lokal=True,
        monthly_lokal_cost_baseline=3_500,
        pipeline_per_week_baseline=2.5,    # Akut-uppdrag = hög
        min_city_size="any",
        learning_focus=(
            "Akut-pris · 50 % påslag jour · service-avtal som "
            "återkommande intäkt · ROT-avdrag"
        ),
    ),
    "elektriker": Industry(
        key="elektriker",
        label="Elektriker",
        short_description=(
            "Installationer, felsökning, byggnader. Behörighets-krav "
            "men stadig efterfrågan."
        ),
        sni_code="43210",
        hourly_rate_min=600,
        hourly_rate_max=950,
        margin_baseline_pct=30,
        margin_range_pct=8,
        time_per_job_hours_min=4,
        time_per_job_hours_max=20,
        segment_mix_privat=0.45,
        segment_mix_foretag=0.40,
        segment_mix_kommun=0.15,
        seasonality=JAMN,
        equipment_cost_init=40_000,
        requires_lokal=True,
        monthly_lokal_cost_baseline=2_800,
        pipeline_per_week_baseline=2.0,
        min_city_size="any",
        learning_focus=(
            "Behörighets-krav (Elsäkerhetsverket) · ansvars-försäkring "
            "obligatorisk · ROT-avdrag"
        ),
    ),
    "frisor": Industry(
        key="frisor",
        label="Frisör / barberare",
        short_description=(
            "Klippning, färgning, behandlingar. Lokal bunden, många "
            "korta jobb · stam-kunder driver omsättningen."
        ),
        sni_code="96021",
        hourly_rate_min=400,
        hourly_rate_max=750,
        margin_baseline_pct=42,
        margin_range_pct=8,
        time_per_job_hours_min=1,
        time_per_job_hours_max=3,
        segment_mix_privat=0.95,
        segment_mix_foretag=0.05,
        segment_mix_kommun=0.0,
        seasonality=JAMN,
        equipment_cost_init=35_000,        # Stol, speglar, första lager
        requires_lokal=True,
        monthly_lokal_cost_baseline=8_000,  # Innerstadslokal är dyr
        pipeline_per_week_baseline=20.0,   # Många små jobb
        min_city_size="medium",
        learning_focus=(
            "Lokal-bunden · fasta kostnader oavsett kund-flöde · "
            "stamkund-värde är allt"
        ),
    ),
    "coach": Industry(
        key="coach",
        label="Coach / livsstilsexpert",
        short_description=(
            "1:1-coaching, grupper, online-kurser. Hög marginal · "
            "prissätter du värdet eller tiden?"
        ),
        sni_code="85590",
        hourly_rate_min=700,
        hourly_rate_max=1500,
        margin_baseline_pct=58,
        margin_range_pct=12,
        time_per_job_hours_min=2,
        time_per_job_hours_max=10,
        segment_mix_privat=0.75,
        segment_mix_foretag=0.20,
        segment_mix_kommun=0.05,
        seasonality=JAN_TOPP,           # Nyår-resolutions
        equipment_cost_init=8_000,         # Webbkamera + ljud + plattform
        requires_lokal=False,
        pipeline_per_week_baseline=1.2,
        min_city_size="any",
        learning_focus=(
            "Värde-baserad prissättning · paket vs timpris · "
            "online vs IRL-skalbarhet"
        ),
    ),
    "personal_trainer": Industry(
        key="personal_trainer",
        label="Personal Trainer / friskvård",
        short_description=(
            "Träningspass 1:1 eller smågrupper. Friskvårdsbidrag-"
            "berättigad = företagskunder också."
        ),
        sni_code="85510",
        hourly_rate_min=500,
        hourly_rate_max=900,
        margin_baseline_pct=38,
        margin_range_pct=10,
        time_per_job_hours_min=1,
        time_per_job_hours_max=4,
        segment_mix_privat=0.70,
        segment_mix_foretag=0.30,
        segment_mix_kommun=0.0,
        seasonality=JAN_TOPP,
        equipment_cost_init=12_000,
        requires_lokal=False,           # Använder gym-lokal
        pipeline_per_week_baseline=2.5,
        min_city_size="medium",
        learning_focus=(
            "Friskvårdsbidrag · företag betalar 5 000/anställd skattefritt · "
            "B2B vs B2C-marginal"
        ),
    ),
    "fotograf": Industry(
        key="fotograf",
        label="Fotograf",
        short_description=(
            "Bröllop, porträtt, företag. Säsongs-tunga jobb, hög "
            "marginal när man är etablerad."
        ),
        sni_code="74201",
        hourly_rate_min=600,
        hourly_rate_max=1200,
        margin_baseline_pct=35,
        margin_range_pct=12,
        time_per_job_hours_min=4,
        time_per_job_hours_max=20,
        segment_mix_privat=0.55,
        segment_mix_foretag=0.40,
        segment_mix_kommun=0.05,
        seasonality=SOMMAR_HOST,
        equipment_cost_init=80_000,        # Kamera + objektiv + ljus
        requires_lokal=False,
        pipeline_per_week_baseline=1.5,
        min_city_size="medium",
        learning_focus=(
            "Tung utrustnings-investering · avskrivning på 5 år · "
            "säsongs-cyklicitet (bröllops-säsong)"
        ),
    ),
    "catering": Industry(
        key="catering",
        label="Catering / kokerska",
        short_description=(
            "Lunch-leveranser, fest-catering, weekend-evenemang. Låg "
            "marginal pga råvaror, hög volym."
        ),
        sni_code="56290",
        hourly_rate_min=350,
        hourly_rate_max=650,
        margin_baseline_pct=18,
        margin_range_pct=8,
        time_per_job_hours_min=8,
        time_per_job_hours_max=40,
        segment_mix_privat=0.30,
        segment_mix_foretag=0.55,
        segment_mix_kommun=0.15,
        seasonality=HELG_TOPP,
        equipment_cost_init=65_000,        # Kök-utrustning
        requires_lokal=True,
        monthly_lokal_cost_baseline=12_000, # Kommersiellt kök
        pipeline_per_week_baseline=1.8,
        min_city_size="medium",
        learning_focus=(
            "Råvaru-marginal är knivskarp · volym-rabatter på inköp · "
            "kontrakts-affärer (företagsluncher) ger stadigt flöde"
        ),
    ),
}


def get_industry(key: str) -> Industry:
    """Slå upp en bransch · raise om okänd nyckel."""
    if key not in INDUSTRIES:
        raise ValueError(
            f"Okänd bransch '{key}'. Giltiga: {list(INDUSTRIES.keys())}",
        )
    return INDUSTRIES[key]


def list_industries() -> list[Industry]:
    """Returnera alla branscher i samma ordning som i koden."""
    return list(INDUSTRIES.values())


# ============================================================
# Stadssize-mapping (vilka städer kvalar för medium/large)
# ============================================================
LARGE_CITIES = {"stockholm", "goteborg", "malmo"}
MEDIUM_CITIES = {
    "uppsala", "vasteras", "orebro", "linkoping", "helsingborg",
    "norrkoping", "jonkoping", "umea", "lund", "boras", "sundsvall",
    "eskilstuna", "halmstad", "vaxjo", "karlstad",
}


def industry_available_in_city(
    industry_key: str, city_key: str,
) -> bool:
    """Kollar om en bransch är meningsfull i en stad.

    Catering, frisör, fotograf och PT kräver minst medel-stad
    (kund-volym för att överleva).
    """
    industry = get_industry(industry_key)
    if industry.min_city_size == "any":
        return True
    if industry.min_city_size == "medium":
        return city_key in LARGE_CITIES or city_key in MEDIUM_CITIES
    return city_key in LARGE_CITIES


def industries_for_city(city_key: str) -> list[Industry]:
    """Returnerar alla branscher som är realistiska i staden."""
    return [
        i for i in list_industries()
        if industry_available_in_city(i.key, city_key)
    ]
