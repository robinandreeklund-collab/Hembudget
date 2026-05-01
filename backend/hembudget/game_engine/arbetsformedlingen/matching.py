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
        )
        scored.append((opening, ms))

    # Sortera DESC på match_score, returnera top-n
    scored.sort(key=lambda x: x[1], reverse=True)
    return [o for o, _ in scored[:n]]
