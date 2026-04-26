"""Idempotent seed för EventTemplate-mallarna.

Mål V2: ~80 events över alla kategorier för pedagogisk variation.
Den här filen växer commit för commit — börjar med ~20 i fas 2/4 och
fylls på i fas 2/2 till 80.

Triggers-format (JSON):
- weekday: [4,5] = bara fredag/lördag
- month_day_min/max: 25-31 = bara mot månadsslutet
- reactive: "low_savings_buffer" | "high_balance" | etc.
- random_weight: 1.0 (default), högre = oftare
- season: "summer" | "christmas" | etc.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .event_models import EventTemplate


# Skelett-uppsättning för fas 2/4 — ~20 events. Fylls på till 80 i 2/2.
EVENT_TEMPLATES: list[dict] = [
    # --- SOCIAL ---
    {
        "code": "bio_filmstaden",
        "title": "Bio på Filmstaden",
        "description": "Anna och Karim har bjudit dig på den nya storfilmen på Filmstaden Söndergatan på fredag.",
        "category": "social",
        "brand": "Filmstaden",
        "cost_min": 150, "cost_max": 200,
        "impact_social": 3, "impact_leisure": 2,
        "duration_days": 5,
        "triggers": {"weekday": [4, 5], "random_weight": 1.0},
        "social_invite_allowed": True,
    },
    {
        "code": "vapiano_pasta",
        "title": "Pasta på Vapiano",
        "description": "Två kompisar vill äta pasta efter jobbet. Vapiano vid Sergels torg.",
        "category": "social",
        "brand": "Vapiano",
        "cost_min": 220, "cost_max": 320,
        "impact_social": 4, "impact_leisure": 1,
        "duration_days": 3,
        "triggers": {"weekday": [3, 4], "random_weight": 1.0},
        "social_invite_allowed": True,
    },
    {
        "code": "karaoke_friday",
        "title": "Karaoke på Friday Bar",
        "description": "Klassen ska sjunga karaoke i fredag kväll. Kostar minst 350 kr för entré och drinkar.",
        "category": "social",
        "brand": "Friday Bar",
        "cost_min": 300, "cost_max": 450,
        "impact_social": 5, "impact_leisure": 3,
        "duration_days": 4,
        "triggers": {"weekday": [4], "random_weight": 0.8},
        "social_invite_allowed": True,
    },

    # --- SPORT ---
    {
        "code": "aik_match",
        "title": "AIK–Hammarby på Tele2 Arena",
        "description": "Stockholmsderby på fredag kväll! Biljettpris 450 kr. Korv och dryck inkluderat lite till.",
        "category": "sport",
        "brand": "AIK Fotboll",
        "cost_min": 400, "cost_max": 550,
        "impact_social": 5, "impact_leisure": 5,
        "duration_days": 7,
        "triggers": {"random_weight": 0.7},
        "social_invite_allowed": True,
    },
    {
        "code": "stockholm_marathon",
        "title": "Stockholm Marathon-anmälan",
        "description": "Anmälan stänger nästa vecka — om du betalar 600 kr nu får du sista platsen.",
        "category": "sport",
        "brand": "Stockholm Marathon",
        "cost_min": 600, "cost_max": 600,
        "impact_health": 6, "impact_social": 3,
        "duration_days": 7,
        "triggers": {"random_weight": 0.4, "season": "spring"},
        "social_invite_allowed": False,
    },

    # --- KULTUR ---
    {
        "code": "musikal_mamma_mia",
        "title": "Musikalen Mamma Mia på Cirkus",
        "description": "Mamma Mia-uppsättningen kommer till Stockholm. Biljett från 800 kr.",
        "category": "culture",
        "brand": "Cirkus",
        "cost_min": 800, "cost_max": 1100,
        "impact_social": 4, "impact_leisure": 5,
        "duration_days": 14,
        "triggers": {"random_weight": 0.3},
        "social_invite_allowed": True,
    },
    {
        "code": "spelmuseum",
        "title": "Spelmuseum med en kompis",
        "description": "En kompis vill gå till Spelmuseum vid Slussen — kostar 150 kr inträde.",
        "category": "culture",
        "brand": "Spelmuseum",
        "cost_min": 120, "cost_max": 180,
        "impact_social": 3, "impact_leisure": 2,
        "duration_days": 14,
        "triggers": {"random_weight": 0.6},
        "social_invite_allowed": True,
    },

    # --- FAMILY ---
    {
        "code": "mormor_kalas",
        "title": "Mormors 80-årskalas",
        "description": "Mormor fyller 80 nästa månad — du behöver köpa en present (förslag 500 kr).",
        "category": "family",
        "brand": None,
        "cost_min": 400, "cost_max": 700,
        "impact_social": 5, "impact_safety": 2,
        "duration_days": 14,
        "triggers": {"random_weight": 0.4},
        "social_invite_allowed": False,
    },
    {
        "code": "syskon_fodelsedag",
        "title": "Syskonets födelsedag",
        "description": "Ditt syskon fyller år nästa vecka — present på ungefär 350 kr räcker bra.",
        "category": "family",
        "brand": None,
        "cost_min": 250, "cost_max": 500,
        "impact_social": 3,
        "duration_days": 7,
        "triggers": {"random_weight": 0.5},
        "social_invite_allowed": False,
    },
    {
        "code": "familj_helg_gotland",
        "title": "Familjesemester en helg på Gotland",
        "description": "Föräldrarna föreslår en helg på Gotland. Du står för dina egna 1 200 kr.",
        "category": "family",
        "brand": None,
        "cost_min": 1100, "cost_max": 1400,
        "impact_social": 6, "impact_leisure": 6,
        "duration_days": 21,
        "triggers": {"random_weight": 0.3, "season": "summer"},
        "social_invite_allowed": False,
    },

    # --- UNEXPECTED (oförutsedda — inte declinable) ---
    {
        "code": "tandlakare_akut",
        "title": "Akut visdomstand",
        "description": "Du har fått en akut tandvärk. Tandläkaren sätter igång genast — 2 800 kr för ingreppet.",
        "category": "unexpected",
        "brand": None,
        "cost_min": 2500, "cost_max": 3200,
        "impact_safety": -2, "impact_health": -1,
        "duration_days": 1,
        "triggers": {"random_weight": 0.2},
        "social_invite_allowed": False,
        "declinable": False,
    },
    {
        "code": "diskmaskin_trasig",
        "title": "Diskmaskinen går sönder",
        "description": "Diskmaskinen läcker vatten — reparationen kostar 4 500 kr.",
        "category": "unexpected",
        "brand": None,
        "cost_min": 4000, "cost_max": 5500,
        "impact_safety": -3,
        "duration_days": 1,
        "triggers": {"random_weight": 0.15},
        "social_invite_allowed": False,
        "declinable": False,
    },
    {
        "code": "cykel_dack",
        "title": "Cykeln punktade",
        "description": "Cykeldäcket punktade på vägen hem. Servicebesök kostar 350 kr.",
        "category": "unexpected",
        "brand": None,
        "cost_min": 250, "cost_max": 500,
        "impact_economy": -1,
        "duration_days": 1,
        "triggers": {"random_weight": 0.4},
        "social_invite_allowed": False,
        "declinable": False,
    },

    # --- OPPORTUNITY ---
    {
        "code": "rea_volt_cykel",
        "title": "Rea på Volt-elcykeln du tittat på",
        "description": "Den elcykel du har följt är på rea — 4 500 kr istället för 7 000. Sluttid 3 dagar.",
        "category": "opportunity",
        "brand": "Volt",
        "cost_min": 4500, "cost_max": 4500,
        "impact_economy": -2, "impact_leisure": 4, "impact_health": 2,
        "duration_days": 3,
        "triggers": {"random_weight": 0.2},
        "social_invite_allowed": False,
    },
    {
        "code": "kompis_saljer_soffa",
        "title": "Kompis säljer sin gamla soffa",
        "description": "En kompis flyttar och vill bli av med sin soffa — 800 kr om du hämtar.",
        "category": "opportunity",
        "brand": None,
        "cost_min": 600, "cost_max": 1000,
        "impact_safety": 1, "impact_economy": -1,
        "duration_days": 5,
        "triggers": {"random_weight": 0.3},
        "social_invite_allowed": False,
    },

    # --- MAT ---
    {
        "code": "foodora_torsdag",
        "title": "Foodora-leverans en torsdag",
        "description": "Du orkar inte laga middag — 220 kr för en pasta från grillen.",
        "category": "mat",
        "brand": "Foodora",
        "cost_min": 180, "cost_max": 280,
        "impact_economy": -1, "impact_leisure": 1,
        "duration_days": 1,
        "triggers": {"weekday": [3], "random_weight": 0.6},
        "social_invite_allowed": False,
    },
    {
        "code": "espresso_house",
        "title": "Fika på Espresso House",
        "description": "Lunch utan att laga själv — 95 kr för dagens lunch på Espresso House.",
        "category": "mat",
        "brand": "Espresso House",
        "cost_min": 80, "cost_max": 130,
        "impact_economy": -0, "impact_leisure": 1,
        "duration_days": 1,
        "triggers": {"weekday": [1, 2], "random_weight": 0.5},
        "social_invite_allowed": True,
    },

    # --- LIFESTYLE ---
    {
        "code": "frisor_klippning",
        "title": "Klippning hos frisören",
        "description": "Det är dags att klippa sig — 450 kr på Stadsmissionen.",
        "category": "lifestyle",
        "brand": None,
        "cost_min": 350, "cost_max": 600,
        "impact_health": 1,
        "duration_days": 14,
        "triggers": {"random_weight": 0.3},
        "social_invite_allowed": False,
    },
    {
        "code": "spotify_premium",
        "title": "Spotify Premium fortsätter",
        "description": "Din Spotify Premium-prenumeration förnyas — 119 kr/mån.",
        "category": "lifestyle",
        "brand": "Spotify",
        "cost_min": 119, "cost_max": 119,
        "impact_leisure": 1,
        "duration_days": 1,
        "triggers": {"month_day_min": 1, "month_day_max": 5},
        "social_invite_allowed": False,
        "declinable": True,  # Eleven kan säga upp
    },
]


def seed_event_templates(session: Session) -> int:
    """Idempotent seed — bara nya rader läggs till."""
    existing = {e.code for e in session.query(EventTemplate).all()}
    added = 0
    for tpl in EVENT_TEMPLATES:
        if tpl["code"] in existing:
            continue
        session.add(EventTemplate(
            code=tpl["code"],
            title=tpl["title"],
            description=tpl["description"],
            category=tpl["category"],
            brand=tpl.get("brand"),
            cost_min=tpl["cost_min"],
            cost_max=tpl["cost_max"],
            impact_economy=tpl.get("impact_economy", 0),
            impact_health=tpl.get("impact_health", 0),
            impact_social=tpl.get("impact_social", 0),
            impact_leisure=tpl.get("impact_leisure", 0),
            impact_safety=tpl.get("impact_safety", 0),
            duration_days=tpl.get("duration_days", 5),
            triggers=tpl.get("triggers"),
            social_invite_allowed=tpl.get("social_invite_allowed", False),
            declinable=tpl.get("declinable", True),
            ai_text_template=tpl.get("ai_text_template"),
        ))
        added += 1
    if added:
        session.flush()
    return added
