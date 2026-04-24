"""Fördefinierade system-kompetenser för Ekonomilabbet.

Används som grundramverk — lärare kan skapa egna ovanpå dessa.
Seedas vid startup om saknas.
"""
from __future__ import annotations


SYSTEM_COMPETENCIES = [
    # Grund
    ("salary_slip",      "Läsa en lönespec", "grund",
     "Förstå bruttolön, skatteavdrag och nettolön."),
    ("bank_statement",   "Tolka ett kontoutdrag", "grund",
     "Veta vad ingående/utgående saldo och transaktion innebär."),
    ("budget_basics",    "Sätta en grundbudget", "grund",
     "Dela in sina utgifter i kategorier och ge varje en månadsram."),
    ("tax_understanding", "Förstå skattedragning", "grund",
     "Veta skillnaden mellan kommunal/statlig skatt och grundavdrag."),
    ("categorization",   "Kategorisera transaktioner", "grund",
     "Placera bank-tx i rätt kategori."),

    # Fördjupning
    ("save_habit",       "Spara regelbundet", "fordjup",
     "Etablera rutin av månadssparande."),
    ("household_costs",  "Räkna hushållskostnader", "fordjup",
     "Använda Konsumentverkets referenssiffror för realistisk planering."),
    ("mortgage_basics",  "Förstå bolån", "fordjup",
     "Ränta vs amortering, rörlig vs bunden."),
    ("unexpected",       "Hantera oplanerade utgifter", "fordjup",
     "Bygga och använda en buffert."),
    ("credit_card_use",  "Använda kreditkort klokt", "fordjup",
     "Veta hur faktura och ränta fungerar."),

    # Expert
    ("long_term_plan",   "Långsiktig ekonomisk plan", "expert",
     "Bygg en plan 3-5 år framåt inkl. sparmål och investering."),
    ("rate_decision",    "Fatta räntebeslut", "expert",
     "Välja bindning/rörligt baserat på räntekurva och risk."),
]


def seed_system_competencies(master_session) -> int:
    """Lägg till system-kompetenser om de saknas. Idempotent."""
    from .models import Competency
    existing = {
        c.key for c in master_session.query(Competency).filter(
            Competency.is_system.is_(True)
        ).all()
    }
    n = 0
    for key, name, level, desc in SYSTEM_COMPETENCIES:
        if key in existing:
            continue
        master_session.add(Competency(
            key=key, name=name, level=level,
            description=desc, is_system=True,
        ))
        n += 1
    return n
