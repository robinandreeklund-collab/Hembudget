"""Kanonisk kategorilista · enda källa-av-sanning för utgifts-/inkomst-
kategorier i hela appen.

VARFÖR: Tidigare hade vi tre olika nomenklatur-system samexisterande:
  - Budget-verktyget (Konsumentverket-schablon): "Mat & livsmedel"
  - Categorize-regelmotor: "Mat" (parent) → "Livsmedel", "Restaurang"
  - Engine-genererade tx: blandning av båda

Resultat: Budget-jämförelse "förbrukat" stannade på 0 kr för flera
kategorier eftersom tx klassats till "Restaurang" men budget letade
efter "Restaurang & café".

Nu: EN lista som ALLA delar. Alias-mappningen sköter backfill av
gammal data via db/migrate.py.

PRAKTISK ANVÄNDNING:
- Skapa Category-rader med namn från CANONICAL_CATEGORIES
- Vid klassning av tx från externa källor (parsers/AI) → kalla
  canonicalize() för att normalisera
- Budget-aggregering matchar direkt mot CANONICAL-strängen
- Migration kör UPDATE categories SET name = canonicalize(name)
"""
from __future__ import annotations

from typing import Optional


# === Kanonisk lista · 20 kategorier ===

# Fasta utgifter (månadsvis, autogiro-vänliga)
CAT_BOENDE = "Boende"
CAT_HUSHALLSEL = "Hushållsel"
CAT_INTERNET_MOBIL = "Internet & mobil"
CAT_STROMNINGSTJANSTER = "Strömningstjänster"
CAT_FORSAKRING = "Försäkring"
CAT_LAN = "Lån"

# Rörliga utgifter
CAT_MAT_LIVSMEDEL = "Mat & livsmedel"
CAT_RESTAURANG = "Restaurang & café"
CAT_KLADER_SKOR = "Kläder & skor"
CAT_HALSA_HYGIEN = "Hälsa & hygien"
CAT_NOJE_FRITID = "Nöje & fritid"
CAT_HEMUTRUSTNING = "Hemutrustning"
CAT_FORBRUKNINGSVAROR = "Förbrukningsvaror"
CAT_TRANSPORT = "Transport"

# Sparande
CAT_SPARMAL = "Sparmål"
CAT_PENSION = "Pension"

# Inkomst
CAT_LON = "Lön"
CAT_SKATTEATERBARING = "Skatteåterbäring"
CAT_OVRIG_INKOMST = "Övrig inkomst"

# Övrigt (fallback)
CAT_OVRIGT = "Övrigt"


CANONICAL_CATEGORIES = [
    # Fasta utgifter
    CAT_BOENDE,
    CAT_HUSHALLSEL,
    CAT_INTERNET_MOBIL,
    CAT_STROMNINGSTJANSTER,
    CAT_FORSAKRING,
    CAT_LAN,
    # Rörliga utgifter
    CAT_MAT_LIVSMEDEL,
    CAT_RESTAURANG,
    CAT_KLADER_SKOR,
    CAT_HALSA_HYGIEN,
    CAT_NOJE_FRITID,
    CAT_HEMUTRUSTNING,
    CAT_FORBRUKNINGSVAROR,
    CAT_TRANSPORT,
    # Sparande
    CAT_SPARMAL,
    CAT_PENSION,
    # Inkomst
    CAT_LON,
    CAT_SKATTEATERBARING,
    CAT_OVRIG_INKOMST,
    # Övrigt
    CAT_OVRIGT,
]


# === Alias-mappning · gamla namn → kanonisk ===
# Används av canonicalize() vid läsning + db/migrate.py vid backfill.
# Format: (alias, canonical). Case-insensitiv matchning.

_ALIAS_MAP_RAW = [
    # Mat
    ("Mat", CAT_MAT_LIVSMEDEL),
    ("Livsmedel", CAT_MAT_LIVSMEDEL),
    ("Matvaror", CAT_MAT_LIVSMEDEL),
    ("Mat & Livsmedel", CAT_MAT_LIVSMEDEL),  # gammal versalisering
    # Restaurang
    ("Restaurang", CAT_RESTAURANG),
    ("Café", CAT_RESTAURANG),
    ("Restaurang & Café", CAT_RESTAURANG),  # case-variant
    ("Cafe", CAT_RESTAURANG),
    ("Uteätande", CAT_RESTAURANG),
    # Kläder
    ("Kläder", CAT_KLADER_SKOR),
    ("Kläder & Skor", CAT_KLADER_SKOR),  # stort S
    ("Skor", CAT_KLADER_SKOR),
    ("Kläder barn", CAT_KLADER_SKOR),  # vi gör inte separat barn-bucket
    # Hälsa
    ("Hälsa", CAT_HALSA_HYGIEN),
    ("Hygien", CAT_HALSA_HYGIEN),
    ("Apotek", CAT_HALSA_HYGIEN),
    ("Sjukvård", CAT_HALSA_HYGIEN),
    ("Träning/Gym", CAT_HALSA_HYGIEN),
    ("Träning", CAT_HALSA_HYGIEN),
    ("Tandvård", CAT_HALSA_HYGIEN),
    ("Frisktandvård", CAT_HALSA_HYGIEN),  # premie räknas till hälsa
    # Nöje
    ("Nöje", CAT_NOJE_FRITID),
    ("Fritid", CAT_NOJE_FRITID),
    ("Biograf/Konsert", CAT_NOJE_FRITID),
    ("Biograf", CAT_NOJE_FRITID),
    ("Konsert", CAT_NOJE_FRITID),
    ("Spel", CAT_NOJE_FRITID),
    ("Böcker/Media", CAT_NOJE_FRITID),
    ("Böcker", CAT_NOJE_FRITID),
    ("Hobby", CAT_NOJE_FRITID),
    # Streaming (vi separerar från Nöje · fast kostnad pedagogiskt)
    ("Streaming", CAT_STROMNINGSTJANSTER),
    # Internet & mobil
    ("Internet", CAT_INTERNET_MOBIL),
    ("Mobil", CAT_INTERNET_MOBIL),
    ("Bredband", CAT_INTERNET_MOBIL),
    ("Telefon", CAT_INTERNET_MOBIL),
    ("Prenumerationer", CAT_INTERNET_MOBIL),
    # Försäkring (all försäkring i samma bucket)
    ("Hemförsäkring", CAT_FORSAKRING),
    ("Bilförsäkring", CAT_FORSAKRING),
    ("Olycksfallsförsäkring", CAT_FORSAKRING),
    ("Livförsäkring", CAT_FORSAKRING),
    ("Barnförsäkring", CAT_FORSAKRING),
    ("Bostadsrättsförsäkring", CAT_FORSAKRING),
    ("Olycksfall", CAT_FORSAKRING),
    ("Liv", CAT_FORSAKRING),
    # Transport
    ("Kollektivtrafik", CAT_TRANSPORT),
    ("Drivmedel", CAT_TRANSPORT),
    ("Bensin", CAT_TRANSPORT),
    ("Diesel", CAT_TRANSPORT),
    ("Bil", CAT_TRANSPORT),
    ("Parkering", CAT_TRANSPORT),
    ("Taxi", CAT_TRANSPORT),
    ("Transport (övrigt)", CAT_TRANSPORT),
    # Boende
    ("Hyra", CAT_BOENDE),
    ("Bolån", CAT_BOENDE),
    ("Avgift", CAT_BOENDE),
    # El (separat från boende eftersom det varierar och pedagogiskt
    # är intressant att se elens kostnad)
    ("El", CAT_HUSHALLSEL),
    # Lån
    ("CSN", CAT_LAN),
    ("Studielån", CAT_LAN),
    ("Privatlån", CAT_LAN),
    ("Billån", CAT_LAN),
    # Sparande
    ("Spara", CAT_SPARMAL),
    ("Sparkonto", CAT_SPARMAL),
    ("ISK", CAT_SPARMAL),
    ("Fonder", CAT_SPARMAL),
    # Inkomst
    ("Lön", CAT_LON),
    ("Skatteåterbäring", CAT_SKATTEATERBARING),
    ("Återbäring", CAT_SKATTEATERBARING),
]


# Bygg case-insensitiv lookup-dict
_ALIAS_LOOKUP: dict[str, str] = {}
for alias, canonical in _ALIAS_MAP_RAW:
    _ALIAS_LOOKUP[alias.casefold()] = canonical
# Lägg också kanoniska namnen själva → returnera oförändrade
for canon in CANONICAL_CATEGORIES:
    _ALIAS_LOOKUP[canon.casefold()] = canon


def canonicalize(name: Optional[str]) -> str:
    """Normalisera ett kategori-namn till kanonisk form.

    - None / tom → "Övrigt"
    - Case-insensitivt matchat alias → kanonisk
    - Okänt namn → "Övrigt" (men logga · framtida aliasing-kandidat)

    Exempel:
        canonicalize("Kläder & Skor") → "Kläder & skor"
        canonicalize("MAT")            → "Mat & livsmedel"
        canonicalize("Streaming")      → "Strömningstjänster"
        canonicalize(None)             → "Övrigt"
        canonicalize("Random")         → "Övrigt"
    """
    if not name or not name.strip():
        return CAT_OVRIGT
    canon = _ALIAS_LOOKUP.get(name.strip().casefold())
    if canon is not None:
        return canon
    return CAT_OVRIGT


def is_canonical(name: str) -> bool:
    """Är namnet redan kanoniskt?"""
    return name in CANONICAL_CATEGORIES


def all_aliases_for(canonical: str) -> list[str]:
    """Returnera alla aliases (inkl. själva kanonen) för en kategori.
    Används av budget-aggregering om vi behöver räkna in icke-migrerad
    legacy-data."""
    if canonical not in CANONICAL_CATEGORIES:
        return []
    result = [canonical]
    for alias, canon in _ALIAS_MAP_RAW:
        if canon == canonical:
            result.append(alias)
    return result
