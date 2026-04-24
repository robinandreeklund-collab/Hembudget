"""Fixtures för slumpning av elev-profiler.

Realistiska svenska yrken med medellöner enligt SCB 2024 (justerat
+5% för 2026-nivå), arbetsgivare per yrke, livsmanus.

Slumpningen är seedad på student_id så samma elev alltid får samma
profil — eleven kan inte få en ny "identitet" mellan inloggningar.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class Profession:
    title: str
    salary_low: int   # bruttolön kr/mån (ingångsnivå)
    salary_high: int  # bruttolön kr/mån (efter några år)
    employers: list[str]


PROFESSIONS: list[Profession] = [
    Profession("Undersköterska", 28_500, 33_500, [
        "Region Stockholm", "Region Västra Götaland", "Stockholms Stad",
        "Göteborgs Stad", "Malmö Stad", "Aleris Vård", "Attendo",
    ]),
    Profession("Lärare F-3", 32_500, 41_000, [
        "Stockholms Stad", "Göteborgs Stad", "Malmö Stad",
        "Internationella Engelska Skolan", "Kunskapsskolan",
    ]),
    Profession("IT-konsult", 42_000, 65_000, [
        "Cygni AB", "Knowit Sverige", "Capgemini", "TCS Sverige",
        "Accenture", "Sopra Steria",
    ]),
    Profession("Sjuksköterska", 34_500, 42_500, [
        "Region Stockholm", "Region Skåne", "Karolinska Universitetssjukhuset",
        "Sahlgrenska Universitetssjukhuset", "Capio S:t Görans Sjukhus",
    ]),
    Profession("Snickare", 31_000, 39_500, [
        "NCC AB", "Skanska Sverige", "PEAB", "JM AB",
        "Bygg- och Snickeri AB", "HBV Bygg",
    ]),
    Profession("Frisör", 26_500, 33_000, [
        "Cutters", "Klippoteket", "Hairdo Sthlm",
        "Egen verksamhet", "Frisörsalong Lockigt",
    ]),
    Profession("Bilmekaniker", 30_500, 37_500, [
        "Mekonomen", "AD Bildelar", "Bilia AB", "Volvo Cars Service",
        "Werksta", "Hedin Bil",
    ]),
    Profession("Butiksmedarbetare", 26_000, 30_500, [
        "ICA", "Coop", "Willys", "H&M", "Lindex", "Clas Ohlson",
        "Elgiganten", "Kjell & Company",
    ]),
    Profession("Elektriker", 33_500, 42_000, [
        "Bravida", "Elajo", "Eitech", "Caverion",
        "Eltel Networks", "Vinci Energies",
    ]),
    Profession("Ekonomiassistent", 30_000, 38_500, [
        "Skanska Sverige", "Vattenfall AB", "PostNord",
        "AcadeMedia AB", "Apoteket AB", "Securitas",
    ]),
    Profession("Projektledare", 44_000, 62_000, [
        "Ericsson AB", "Volvo Cars", "ABB Sverige",
        "Saab AB", "AstraZeneca", "H&M Group",
    ]),
    Profession("Marknadsassistent", 31_000, 39_000, [
        "Spotify Sverige", "Klarna Bank AB", "King Digital Entertainment",
        "Mojang Studios", "Telia Company",
    ]),
    Profession("Säljare", 30_000, 45_000, [
        "Telia Company", "Tele2 AB", "Bauhaus", "Elgiganten",
        "Mediamarkt", "ICA", "Hjärtums Mark & Trädgård",
    ]),
    Profession("Kock", 28_500, 36_500, [
        "Operakällaren", "Sturehof", "Tre Små Rum", "Restaurang Volt",
        "Ekstedt", "Egen verksamhet",
    ]),
    Profession("Barnskötare", 26_500, 31_500, [
        "Stockholms Stad förskola", "Göteborgs Stad förskola",
        "Pysslingen Förskolor", "Vittra", "Kunskapsförskolan",
    ]),
    Profession("Barista", 25_500, 29_000, [
        "Espresso House", "Wayne's Coffee", "Joe & The Juice",
        "Starbucks Sverige", "Café Pascal",
    ]),
    Profession("Förskollärare", 32_000, 39_500, [
        "Stockholms Stad", "Göteborgs Stad", "Malmö Stad",
        "Pysslingen Förskolor", "Tellusbarn",
    ]),
]


CITIES: list[tuple[str, float]] = [
    # (stad, hyrespristfaktor relativt riksgenomsnittet)
    ("Stockholm", 1.45),
    ("Göteborg", 1.20),
    ("Malmö", 1.10),
    ("Uppsala", 1.15),
    ("Linköping", 1.00),
    ("Västerås", 0.95),
    ("Örebro", 0.90),
    ("Norrköping", 0.90),
    ("Helsingborg", 1.00),
    ("Jönköping", 0.95),
    ("Umeå", 0.95),
    ("Borås", 0.85),
    ("Karlstad", 0.85),
    ("Kalmar", 0.85),
    ("Halmstad", 0.95),
]


# Boendekostnad per typ (basbelopp, multipliceras med stadsfaktor)
HOUSING_BASE: dict[str, tuple[int, int]] = {
    "hyresratt":   (5_500, 12_500),
    "bostadsratt": (4_200, 9_500),  # avgift; vi separerar lån
    "villa":       (3_500, 8_500),  # driftkostnad; vi separerar lån
}


PERSONALITIES = ["sparsam", "blandad", "blandad", "slosaktig"]
# blandad x2 → 50% chans, sparsam/slösaktig vardera 25%


@dataclass
class GeneratedProfile:
    profession: str
    employer: str
    gross_salary_monthly: int
    age: int
    city: str
    family_status: str
    housing_type: str
    housing_monthly: int
    has_mortgage: bool
    has_car_loan: bool
    has_student_loan: bool
    has_credit_card: bool
    personality: str
    backstory: str
    children_ages: list[int]
    partner_age: int | None


def generate_profile(student_id: int, display_name: str) -> GeneratedProfile:
    rng = random.Random(_seed_for_student(student_id))

    prof = rng.choice(PROFESSIONS)
    employer = rng.choice(prof.employers)
    age = rng.randint(22, 48)

    # Yngre = närmare ingångslön; äldre = mer mot toppen
    age_factor = min(1.0, (age - 22) / 18)  # 0..1 över 22-40 år
    salary = round(
        prof.salary_low + (prof.salary_high - prof.salary_low) * age_factor
        + rng.randint(-1500, 1500),  # individuell variation
        -2,  # avrunda till hundratal
    )

    city, city_factor = rng.choice(CITIES)

    # Familjesituation styrs delvis av ålder
    if age < 26:
        family_status = rng.choice(["ensam", "ensam", "sambo"])
    elif age < 35:
        family_status = rng.choice(["ensam", "sambo", "sambo", "familj_med_barn"])
    else:
        family_status = rng.choice(["sambo", "familj_med_barn", "familj_med_barn"])

    # Boendetyp — yngre/lägre lön = oftare hyresrätt; äldre = mer ägt
    if salary < 32_000 or age < 28:
        housing_type = rng.choice(["hyresratt", "hyresratt", "bostadsratt"])
    elif age >= 35 and family_status == "familj_med_barn":
        housing_type = rng.choice(["bostadsratt", "villa", "villa"])
    else:
        housing_type = rng.choice(["hyresratt", "bostadsratt", "bostadsratt", "villa"])

    h_low, h_high = HOUSING_BASE[housing_type]
    housing_monthly = round(rng.randint(h_low, h_high) * city_factor, -2)
    if family_status == "familj_med_barn":
        housing_monthly = int(housing_monthly * 1.25)

    has_mortgage = housing_type in ("bostadsratt", "villa")
    has_car_loan = (
        family_status in ("sambo", "familj_med_barn")
        and rng.random() < 0.55
    )
    has_student_loan = (
        prof.title in ("Lärare F-3", "Sjuksköterska", "IT-konsult",
                       "Projektledare", "Förskollärare", "Ekonomiassistent")
        and age < 38
        and rng.random() < 0.7
    )
    has_credit_card = rng.random() < 0.85

    personality = rng.choice(PERSONALITIES)

    # Partner — om sambo eller familj_med_barn
    partner_age: int | None = None
    if family_status in ("sambo", "familj_med_barn"):
        partner_age = age + rng.randint(-4, 4)
        partner_age = max(20, min(60, partner_age))

    # Barn — endast om family_med_barn
    children_ages: list[int] = []
    if family_status == "familj_med_barn":
        n_kids = rng.choices([1, 2, 3], weights=[0.45, 0.45, 0.10])[0]
        # Yngsta förälder bestämmer max barnålder (rimlighetstest)
        youngest_parent = min(age, partner_age or age)
        max_child_age = max(0, youngest_parent - 22)
        for _ in range(n_kids):
            children_ages.append(rng.randint(0, max_child_age or 12))
        children_ages.sort()

    backstory = _build_backstory(
        display_name, prof.title, employer, age, city,
        family_status, housing_type, personality, children_ages,
    )

    return GeneratedProfile(
        profession=prof.title,
        employer=employer,
        gross_salary_monthly=int(salary),
        age=age,
        city=city,
        family_status=family_status,
        housing_type=housing_type,
        housing_monthly=int(housing_monthly),
        has_mortgage=has_mortgage,
        has_car_loan=has_car_loan,
        has_student_loan=has_student_loan,
        has_credit_card=has_credit_card,
        personality=personality,
        backstory=backstory,
        children_ages=children_ages,
        partner_age=partner_age,
    )


def _build_backstory(
    name: str, profession: str, employer: str, age: int, city: str,
    family_status: str, housing_type: str, personality: str,
    children_ages: list[int],
) -> str:
    if family_status == "ensam":
        family_text = "bor ensam"
    elif family_status == "sambo":
        family_text = "bor med din sambo"
    else:
        n = len(children_ages)
        if n == 1:
            kids = f"ett barn på {children_ages[0]} år"
        elif n == 2:
            kids = (
                f"två barn ({children_ages[0]} och {children_ages[1]} år)"
            )
        else:
            kids = f"{n} barn ({', '.join(str(a) for a in children_ages)} år)"
        family_text = f"bor med din sambo och {kids}"

    housing_text = (
        " i en hyresrätt" if housing_type == "hyresratt"
        else " i en bostadsrätt" if housing_type == "bostadsratt"
        else " i en villa"
    )

    personality_text = {
        "sparsam": (
            "Du är en sparsam person — du föredrar att leva enkelt och "
            "lägga undan pengar varje månad."
        ),
        "blandad": (
            "Du har en balanserad inställning till pengar — sparar lite, "
            "unnar dig lite."
        ),
        "slosaktig": (
            "Du gillar att leva i nuet och unna dig — restaurangbesök, "
            "shopping och prylar är viktigt för dig. Det blir sällan "
            "mycket pengar över i slutet av månaden."
        ),
    }[personality]

    return (
        f"Du är {age} år gammal och jobbar som {profession.lower()} på "
        f"{employer} i {city}. Du {family_text}{housing_text}. "
        f"{personality_text}"
    )


def _seed_for_student(student_id: int) -> int:
    return abs(hash(("profile", student_id))) & 0xFFFFFFFF
