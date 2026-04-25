"""Seed för landningssidans gallery-slots.

Sex fasta slots motsvarar de sex korten i Vyerna-galleriet på
landningssidan. Här seedas bara metadata (titel, kropp, chip);
super-admin laddar sedan upp den faktiska skärmdumpen via
/admin/landing/gallery.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import LandingAsset


# Sex slots i samma ordning som de tidigare hårdkodades i Landing.tsx.
# Slot:en är en stabil sträng-nyckel som UI:n filtrerar/sorterar på,
# inte ett ID — så vi kan lägga till/ta bort slots utan migration.
LANDING_SLOTS = [
    {
        "slot": "dashboard",
        "title": "Lärarens dashboard",
        "body": (
            "Alla elever, inbox, uppdrag och AI-lägesbilder på en "
            "skärm."
        ),
        "chip": "Lä",
        "chip_color": "special",
        "sort_order": 10,
    },
    {
        "slot": "modules",
        "title": "Elevens kursplan",
        "body": (
            "Moduler steg för steg: läs, reflektera, quiz och uppdrag."
        ),
        "chip": "Mo",
        "chip_color": "grund",
        "sort_order": 20,
    },
    {
        "slot": "mastery",
        "title": "Mastery-grafen",
        "body": (
            "Per-kompetens mastery, milstolpar och nästa-steg-hint."
        ),
        "chip": "Ms",
        "chip_color": "fordj",
        "sort_order": 30,
    },
    {
        "slot": "portfolio",
        "title": "Portfolio-PDF",
        "body": (
            "Exporteras per elev eller som ZIP för hela klassen."
        ),
        "chip": "Pf",
        "chip_color": "special",
        "sort_order": 40,
    },
    {
        "slot": "ai",
        "title": "Fråga Ekon",
        "body": (
            "Multi-turn AI-coach som anpassar svaren till elevens nivå."
        ),
        "chip": "AI",
        "chip_color": "special",
        "sort_order": 50,
    },
    {
        "slot": "time-on-task",
        "title": "Time on task",
        "body": (
            "Se vilka steg som fastnar för eleverna i din klass."
        ),
        "chip": "Tt",
        "chip_color": "risk",
        "sort_order": 60,
    },
]


def seed_landing_assets(s: Session) -> int:
    """Lägg in saknade slots. Idempotent — befintliga rader rörs ej."""
    existing = {
        a.slot for a in s.query(LandingAsset).all()
    }
    n = 0
    for spec in LANDING_SLOTS:
        if spec["slot"] in existing:
            continue
        s.add(LandingAsset(**spec))
        n += 1
    return n
