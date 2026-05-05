"""A1+A2 · Match-score-beräkning + tillgängliga jobb.

Spec: dev/game-motor/05-arbetsformedlingen.md (Match-poäng)

Match-score (0-100) baseras på:
- Yrkets education_level vs elevens nuvarande nivå (proxy)
- Stadens job_density (utbud) — låg = svårare att få jobb
- Hushåll-faktor: stora familjer mer riskaverta
- Tidigare jobbyte-historik (kommer i Sprint 6b)
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from ..pools.stadspool import STAD_BY_KEY
from ..pools.yrkespool import YRKESPOOL, Yrke
from ..profile_generator.schema import GeneratedProfile


MATS_OPENING_MESSAGE = (
    "Hej! Jag är Mats, din kontakt på Arbetsförmedlingen. "
    "Jag visar dig några jobb som passar din profil — du väljer själv "
    "vilka du vill söka. Varje ansökan tar dig genom 5 ronder: "
    "CV → telefon → case → intervju → erbjudande."
)


# Företagsnamn-pool för en realistisk svensk arbetsmarknad
EMPLOYER_NAMES = {
    "vard_underskoterska": ["Region Stockholm", "Region Skåne", "Attendo", "Vardaga"],
    "vard_sjukskoterska": ["Karolinska Sjukhuset", "Sahlgrenska", "Capio S:t Görans"],
    "it_konsult_junior": ["Tieto", "Cybercom", "Knowit", "Sigma"],
    "it_konsult_senior": ["Spotify", "Klarna", "Truecaller", "Ericsson R&D"],
    "it_systemutvecklare": ["IKEA Tech", "King Digital", "DICE", "Mojang"],
    "butiksbitrade": ["ICA", "Coop", "H&M", "Lindex", "Stadium"],
    "kassorska": ["ICA", "Coop", "Hemköp", "Willys"],
    "kock": ["Operakällaren", "Frantzén", "Restaurang Mat", "Vapiano"],
    "lar_grundskola": ["Stockholms Stad Skolförvaltning", "Göteborgs Stad", "Malmö Stad"],
    "lar_vikarie": ["Manpower Education", "Lärarvikarier"],
    "snickare": ["NCC Bygg", "Skanska", "Peab", "Veidekke"],
    "elektriker": ["E.ON", "Vattenfall Service", "ELON", "Bravida"],
    "lastbilschauffor": ["DHL", "PostNord", "Schenker", "Bring"],
    "ekonom_controller": ["EY", "PwC", "KPMG", "Deloitte"],
    "polis": ["Polismyndigheten Stockholm", "Polismyndigheten Region Väst"],
    "brandman": ["Storstockholms Brandförsvar", "Räddningstjänsten"],
}
DEFAULT_EMPLOYERS = ["Företaget AB", "Branschledaren", "Lokalbolaget", "Norra AB"]


@dataclass(frozen=True)
class JobOpening:
    """En jobbannons baserad på yrkespool + stad + slumpad arbetsgivare."""
    listing_id: str           # "{city}-{ym}-{yrke_key}-{idx}"
    yrke_key: str
    yrke_display: str
    yrke_ssyk: str
    employer_name: str
    city_key: str
    city_display: str
    monthly_gross_min: int
    monthly_gross_median: int
    monthly_gross_max: int
    education_level: str
    match_score: int          # 0-100, beräknad för aktuell elev
    description: str
    # === Sprint 7 · utökad annons-data för riktig fakturalook ===
    company_blurb: str        # 2-3 meningar om arbetsgivaren
    job_description: list[str]   # 4-6 punkter "Vad du kommer göra"
    requirements: list[str]      # krav-lista
    meriter: list[str]           # "extra plus"-lista
    benefits: list[str]          # förmåner-lista
    employment_type: str         # "heltid" | "deltid 75%" | "vikariat 6 mån"
    application_deadline: str    # ISO-datum
    work_hours: str              # "08-17 mån-fre" / "skift" / "flexibel"
    start_date: str              # "Tillträde omgående" / "1 juli"


def calculate_match_score(
    profile: GeneratedProfile,
    yrke: Yrke,
    *,
    rng: random.Random | None = None,
) -> int:
    """Räkna match-score 0-100 för en (elev, yrke).

    Faktorer:
    - Education-match (25 p): elev:s yrke:s edu-level mot vald yrke
    - Stadsfaktor (15 p): lokala job-density × yrkets weight i staden
    - Erfarenhet (20 p): elev:s nuvarande yrke vs målyrket
    - Karriärlogik (20 p): naturligt nästa steg eller side-step?
    - Random shock (20 p): variation så samma elev får olika score
      för samma jobb över tid (= olika rekryterare har olika smak)
    """
    rng = rng or random.Random(f"match|{profile.seed}|{yrke.key}")
    score = 0

    # Education-match
    edu_levels = ["ingen", "gymnasium", "yh", "hogskola", "doktor"]
    profile_edu = profile.facts.get("competency_match_with_yrke", False)
    profile_idx = edu_levels.index("gymnasium")  # default
    target_idx = edu_levels.index(yrke.education_level) if yrke.education_level in edu_levels else 1
    diff = profile_idx - target_idx
    if diff >= 0:
        score += 25  # samma eller högre utbildning än krävs
    else:
        score += max(0, 25 + diff * 8)  # -8 per nivå under

    # Stadsfaktor
    city = STAD_BY_KEY.get(profile.city_key)
    if city:
        density_mult = min(1.5, city.job_density)
        score += int(15 * (density_mult / 1.5))
    else:
        score += 8

    # Erfarenhet
    age = profile.facts.get("age", 25)
    if age >= yrke.experience_years_required[0] + 18:  # 18 + min år
        score += 20
    else:
        score += 10

    # Karriärlogik · är detta i samma "spår"?
    if profile.facts.get("competency_match_with_yrke"):
        # Eleven har kompetens som matchar nuvarande yrke
        # Om vi väljer ett yrke från "realistic_career_paths" → bonus
        from ..pools.yrkespool import YRKE_BY_KEY
        current = YRKE_BY_KEY.get(profile.yrke_key)
        if current and yrke.key in current.realistic_career_paths:
            score += 20
        elif current and current.education_level == yrke.education_level:
            score += 10

    # Random shock
    score += rng.randint(0, 20)

    return max(0, min(100, score))


def _employer_for(yrke_key: str, rng: random.Random) -> str:
    pool = EMPLOYER_NAMES.get(yrke_key, DEFAULT_EMPLOYERS)
    return rng.choice(pool)


def available_jobs_for_student(
    profile: GeneratedProfile,
    year_month: str,
    *,
    n: int = 6,
    same_city_only: bool = True,
) -> list[JobOpening]:
    """Generera deterministisk pool av jobb för (elev, year_month).

    Filterar:
    - Bara yrken med education_level ≤ elevens (eller +1 nivå utveckling)
    - Stadsfilter: bara samma stad om same_city_only=True
    """
    rng = random.Random(f"jobs|{profile.seed}|{year_month}|{profile.city_key}")
    edu_levels = ["ingen", "gymnasium", "yh", "hogskola", "doktor"]
    target_max = min(
        len(edu_levels) - 1,
        edu_levels.index("hogskola"),  # tillåt upp till hogskola
    )

    candidates: list[Yrke] = []
    for y in YRKESPOOL:
        if y.education_level not in edu_levels:
            continue
        idx = edu_levels.index(y.education_level)
        if idx > target_max:
            continue
        # Filtrera bort elevens nuvarande yrke (man söker INTE samma jobb)
        if y.key == profile.yrke_key:
            continue
        # Filtrera bort studerande-arketyper (inte vuxen-jobb)
        if y.key.startswith("studerande_"):
            continue
        candidates.append(y)

    # Slumpa n stycken viktat efter match-score så toppen syns
    scored: list[tuple[JobOpening, int]] = []
    for y in candidates:
        ms = calculate_match_score(profile, y, rng=random.Random(rng.random()))
        ad_rng = random.Random(f"ad|{profile.seed}|{year_month}|{y.key}")
        full_ad = _build_full_ad(y, ad_rng)
        opening = JobOpening(
            listing_id=(
                f"{profile.city_key}-{year_month}-{y.key}-"
                f"{rng.randint(0,99):02d}"
            ),
            yrke_key=y.key,
            yrke_display=y.display,
            yrke_ssyk=y.ssyk,
            employer_name=_employer_for(y.key, rng),
            city_key=profile.city_key,
            city_display=STAD_BY_KEY.get(
                profile.city_key, STAD_BY_KEY["medelstad"],
            ).display,
            monthly_gross_min=y.monthly_gross_min,
            monthly_gross_median=y.monthly_gross_median,
            monthly_gross_max=y.monthly_gross_max,
            education_level=y.education_level,
            match_score=ms,
            description=y.description,
            company_blurb=full_ad["company_blurb"],
            job_description=full_ad["job_description"],
            requirements=full_ad["requirements"],
            meriter=full_ad["meriter"],
            benefits=full_ad["benefits"],
            employment_type=full_ad["employment_type"],
            application_deadline=full_ad["application_deadline"],
            work_hours=full_ad["work_hours"],
            start_date=full_ad["start_date"],
        )
        scored.append((opening, ms))

    # Sortera DESC på match_score, returnera top-n
    scored.sort(key=lambda x: x[1], reverse=True)
    return [o for o, _ in scored[:n]]


# === Sprint 7 · annons-data-byggare =============================
# Genererar requirements/meriter/benefits/employment_type/etc. baserat
# på yrke + deterministisk slump så samma student+yrke får samma
# annons men olika studenter ser olika varianter.

# Generella krav-mallar per yrkesgrupp (ssyk-prefix)
_REQUIREMENTS_BY_GROUP = {
    "vard": [
        ["Sjuksköterskelegitimation", "Minst 2 års erfarenhet av somatisk vård", "B-körkort"],
        ["Undersköterskeutbildning", "Erfarenhet av äldreomsorg", "Goda kunskaper i svenska"],
        ["Specialistutbildning inom geriatrik", "Datorvana", "Stresstolerans"],
    ],
    "it": [
        ["Högskoleexamen inom IT/data", "3+ års erfarenhet av Python eller Java", "Erfarenhet av agilt arbetssätt"],
        ["YH-utbildning eller motsvarande", "Erfarenhet av REST-API:er", "Kunskap i Git"],
        ["Senior systemutvecklare", "Cloud-erfarenhet (AWS/Azure)", "Mentorerfarenhet"],
    ],
    "butik": [
        ["Gymnasieutbildning", "Servicekänsla", "Erfarenhet av kassasystem"],
        ["B-körkort", "Helger och kvällar", "Truckkort A"],
    ],
    "lar": [
        ["Lärarlegitimation", "Behörighet i ämnet", "Pedagogisk erfarenhet"],
        ["Lärarutbildning eller motsvarande", "Goda kunskaper i svenska", "B-körkort"],
    ],
    "transport": [
        ["C-körkort + YKB", "Digitalfärdskrivare", "Tunga lyft (15 kg+)"],
        ["B-körkort", "Erfarenhet av distribution", "Skiftarbete"],
    ],
    "ekonom": [
        ["Civilekonomexamen eller motsvarande", "Erfarenhet av redovisning enligt K3", "Excel-vana"],
        ["3+ års erfarenhet inom controlling", "Auktoriserad revisor", "Goda kunskaper i engelska"],
    ],
    "default": [
        ["Gymnasieutbildning", "Goda kunskaper i svenska", "Personlig lämplighet"],
        ["Erfarenhet inom branschen", "Datorvana", "Servicekänsla"],
        ["Drivkraft och egen motivation", "B-körkort", "God samarbetsförmåga"],
    ],
}
_MERITER_BY_GROUP = {
    "vard": ["Specialistutbildning", "Erfarenhet av handledning", "Andra språk", "HLR-utbildning"],
    "it": ["TypeScript-erfarenhet", "Open source-bidrag", "Talat på konferens", "DevOps-kunskap"],
    "butik": ["Visuell merchandising", "Andra språk", "Produktkännedom", "E-handel"],
    "lar": ["Specialpedagogik", "Digital pedagogik", "Klassföreståndarerfarenhet", "Andra språk"],
    "transport": ["ADR-bevis", "ISO 9001", "Truckkort", "ECO-driving-utbildning"],
    "ekonom": ["FAR-medlemskap", "K2/K3-expertis", "Budgetarbete", "Investeringsanalys"],
    "default": ["Andra språk", "Volontärerfarenhet", "Egna projekt", "Internationell erfarenhet"],
}
_BENEFITS_POOL = [
    "Tjänstepension via ITP1 (4,5 % av lön)",
    "Friskvårdsbidrag 5 000 kr/år",
    "30 semesterdagar",
    "Flexibla arbetstider",
    "Möjlighet till hemarbete 2 dagar/vecka",
    "Tjänstebil enligt avtal",
    "Subventionerad lunch",
    "Föräldralön upp till 90 % av lön",
    "Kompetensutvecklings-budget 15 000 kr/år",
    "Sjuklön över Försäkringskassans tak",
    "Kollektivavtal Akavia / Unionen",
    "Sjuk-vårdsförsäkring",
]
_EMPLOYMENT_TYPES = [
    "Heltid · tillsvidareanställning",
    "Heltid · provanställning 6 mån",
    "Vikariat · 12 månader (ev. förlängning)",
    "Deltid 75 % · tillsvidare",
    "Heltid · projektanställning 18 mån",
]
_WORK_HOURS = [
    "08:00–17:00 mån-fre",
    "Skiftarbete · dag/kväll/natt",
    "Flexibla tider med kärntid 09–15",
    "07:00–16:00 mån-fre",
    "Helger ingår enligt schema",
]
_COMPANY_BLURBS = {
    "vard": (
        "{employer} är en av regionens större vårdaktörer med fokus på "
        "kvalitet och kontinuitet. Vi erbjuder en stabil arbetsmiljö där "
        "patientens trygghet alltid kommer först."
    ),
    "it": (
        "{employer} är ett expansivt techbolag med produkter som används av "
        "hundratusentals användare dagligen. Vi tror på platta organisationer, "
        "open source och att lärande aldrig tar slut."
    ),
    "butik": (
        "{employer} är en av landets mest etablerade detaljhandelskedjor. "
        "Hos oss möter du engagerade kollegor och en miljö där service är "
        "kärnan i allt vi gör."
    ),
    "lar": (
        "{employer} driver kvalitetsskolor med tydligt pedagogiskt fokus. "
        "Vi tror på att varje elev kan, med rätt stöd och förväntningar."
    ),
    "transport": (
        "{employer} är en stor logistikaktör med dagliga rutter över hela "
        "Norden. Säkerhet, leveranssäkerhet och respekt för chaufförens tid "
        "är våra ledord."
    ),
    "ekonom": (
        "{employer} är en av de ledande revisions- och rådgivningsbyråerna. "
        "Vi arbetar med några av Sveriges mest spännande företag och växer "
        "stadigt."
    ),
    "default": (
        "{employer} är ett etablerat företag med stark närvaro på den svenska "
        "marknaden. Vi värderar kompetens, samarbete och långsiktighet."
    ),
}


def _yrke_group(yrke_key: str) -> str:
    """Mappa yrke_key till en grupp för annons-templates."""
    if yrke_key.startswith("vard_") or yrke_key.startswith("under"):
        return "vard"
    if yrke_key.startswith("it_") or yrke_key.startswith("system"):
        return "it"
    if yrke_key.startswith("butik") or yrke_key.startswith("kass"):
        return "butik"
    if yrke_key.startswith("lar_"):
        return "lar"
    if yrke_key.startswith("lastbil") or yrke_key.startswith("transport"):
        return "transport"
    if yrke_key.startswith("ekonom") or yrke_key.startswith("controller"):
        return "ekonom"
    return "default"


def _build_full_ad(yrke: Yrke, rng: random.Random) -> dict:
    """Bygg full annons-data deterministiskt från yrke + rng."""
    from datetime import date as _d, timedelta as _td

    group = _yrke_group(yrke.key)

    requirements = list(rng.choice(
        _REQUIREMENTS_BY_GROUP.get(group, _REQUIREMENTS_BY_GROUP["default"]),
    ))
    meriter_pool = _MERITER_BY_GROUP.get(group, _MERITER_BY_GROUP["default"])
    meriter = rng.sample(meriter_pool, k=min(3, len(meriter_pool)))
    benefits = rng.sample(_BENEFITS_POOL, k=4)
    employment_type = rng.choice(_EMPLOYMENT_TYPES)
    work_hours = rng.choice(_WORK_HOURS)

    # Job-description (4-6 punkter härledda från description + yrke-typ)
    job_desc_templates = {
        "vard": [
            "Ge omvårdnad och stöd till våra patienter/brukare",
            "Dokumentera enligt gällande riktlinjer i journalsystem",
            "Samverka i tvärprofessionellt team",
            "Delta i ronder och morgonmöten",
            "Bidra till verksamhetens kvalitetsutveckling",
            "Utbilda och handleda nya kollegor",
        ],
        "it": [
            "Utveckla och underhålla våra produkter i dagligt arbete",
            "Delta aktivt i kodgranskningar och tekniska beslut",
            "Skriva tester och bidra till CI/CD-pipeline",
            "Samverka med produktägare och designers i tvärfunktionellt team",
            "Bidra till tekniska beslut och arkitekturval",
            "Mentorera juniora utvecklare",
        ],
        "butik": [
            "Möta kunder och ge förstklassig service",
            "Påfyllnad av varor och säkerställa tilltalande exponering",
            "Hantera kassa enligt rutiner",
            "Delta i inventering och varuflöde",
            "Bidra till butikens försäljningsmål",
        ],
        "lar": [
            "Planera och genomföra undervisning enligt läroplan",
            "Bedöma elevers kunskapsutveckling löpande",
            "Samverka med vårdnadshavare i utvecklingssamtal",
            "Delta i kollegialt utvecklingsarbete",
            "Vara klassföreståndare för en grupp elever",
        ],
        "transport": [
            "Köra fasta eller varierande rutter enligt schema",
            "Lasta och lossa gods enligt säkerhetsföreskrifter",
            "Föra digital körjournal",
            "Säkerställa fordonets dagliga skick",
        ],
        "ekonom": [
            "Ansvara för månadsbokslut och årsbokslut",
            "Analysera och rapportera ekonomiska nyckeltal",
            "Stödja verksamheten med beslutsunderlag",
            "Driva förbättringsarbete inom ekonomifunktionen",
            "Samarbeta med revisorer och myndigheter",
        ],
        "default": [
            f"Arbeta som {yrke.display} i ett etablerat team",
            "Bidra med din kompetens i dagligt arbete",
            "Delta i löpande utvecklingsarbete",
            "Samverka med kollegor och externa parter",
        ],
    }
    desc_pool = job_desc_templates.get(group, job_desc_templates["default"])
    job_description = rng.sample(desc_pool, k=min(5, len(desc_pool)))

    # Sista ansökningsdag · 14-30 dagar fram
    deadline = _d.today() + _td(days=rng.randint(14, 30))

    # Tillträdesdatum · "omgående" eller specifikt datum
    if rng.random() < 0.4:
        start_date = "Tillträde omgående"
    else:
        start = _d.today() + _td(days=rng.randint(45, 120))
        start_date = f"Tillträde {start.strftime('%-d %B %Y')}"

    company_blurb = _COMPANY_BLURBS.get(group, _COMPANY_BLURBS["default"])

    return {
        "company_blurb": company_blurb,
        "job_description": job_description,
        "requirements": requirements,
        "meriter": meriter,
        "benefits": benefits,
        "employment_type": employment_type,
        "work_hours": work_hours,
        "start_date": start_date,
        "application_deadline": deadline.isoformat(),
    }
