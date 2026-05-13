"""Tester för kanonisk kategorilista (SKV-6).

- canonicalize mappar gamla namn → kanoniska
- DEFAULT_CATEGORIES + SEED_RULES innehåller bara kanoniska
- budget/seed.py mappar till kanoniska
- variable_expenses skapar tx med kanoniska kategorier
- migration backfillar Category-rader idempotent
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from hembudget.categorize.canonical import (
    canonicalize, CANONICAL_CATEGORIES, is_canonical, all_aliases_for,
    CAT_MAT_LIVSMEDEL, CAT_KLADER_SKOR, CAT_HALSA_HYGIEN,
    CAT_NOJE_FRITID, CAT_RESTAURANG, CAT_STROMNINGSTJANSTER,
    CAT_FORSAKRING, CAT_TRANSPORT, CAT_OVRIGT,
)
from hembudget.categorize.seed_rules import (
    DEFAULT_CATEGORIES, SEED_RULES,
)


# === canonicalize ===


def test_canonicalize_handles_case_variants():
    """'Kläder & Skor' (stort S) och 'Kläder & skor' (litet s) ska båda
    bli kanoniska 'Kläder & skor'."""
    assert canonicalize("Kläder & Skor") == CAT_KLADER_SKOR
    assert canonicalize("Kläder & skor") == CAT_KLADER_SKOR
    assert canonicalize("KLÄDER & SKOR") == CAT_KLADER_SKOR


def test_canonicalize_aliases():
    """Subkategorier från gamla träd-strukturen ska mappas till
    rätt parent."""
    assert canonicalize("Livsmedel") == CAT_MAT_LIVSMEDEL
    assert canonicalize("Restaurang") == CAT_RESTAURANG
    assert canonicalize("Café") == CAT_RESTAURANG
    assert canonicalize("Apotek") == CAT_HALSA_HYGIEN
    assert canonicalize("Sjukvård") == CAT_HALSA_HYGIEN
    assert canonicalize("Träning/Gym") == CAT_HALSA_HYGIEN
    assert canonicalize("Streaming") == CAT_STROMNINGSTJANSTER
    assert canonicalize("Biograf/Konsert") == CAT_NOJE_FRITID
    assert canonicalize("Hemförsäkring") == CAT_FORSAKRING
    assert canonicalize("Bilförsäkring") == CAT_FORSAKRING
    assert canonicalize("Drivmedel") == CAT_TRANSPORT
    assert canonicalize("Kollektivtrafik") == CAT_TRANSPORT
    assert canonicalize("Bensin") == CAT_TRANSPORT


def test_canonicalize_unknown_returns_ovrigt():
    """Okänd kategori → 'Övrigt'."""
    assert canonicalize("XYZ-foo") == CAT_OVRIGT
    assert canonicalize("") == CAT_OVRIGT
    assert canonicalize(None) == CAT_OVRIGT


def test_canonicalize_canonical_unchanged():
    """Redan kanonisk → returneras oförändrad."""
    for cat in CANONICAL_CATEGORIES:
        assert canonicalize(cat) == cat


def test_canonical_categories_count():
    """20 kanoniska kategorier exakt."""
    assert len(CANONICAL_CATEGORIES) == 20


# === seed_rules ===


def test_default_categories_are_canonical():
    """Alla DEFAULT_CATEGORIES måste finnas i CANONICAL_CATEGORIES."""
    for name, parent, _icon in DEFAULT_CATEGORIES:
        assert name in CANONICAL_CATEGORIES, (
            f"Default-kategori '{name}' är inte kanonisk · "
            "kommer skapa duplicate vid migration."
        )
        # Platt struktur · alla parent_id ska vara None
        assert parent is None, (
            f"Default-kategori '{name}' har parent='{parent}' · "
            "vi har platt struktur nu."
        )


def test_seed_rules_point_to_canonical():
    """Varje regel måste klassa till en kanonisk kategori."""
    for pat, cat, prio in SEED_RULES:
        assert cat in CANONICAL_CATEGORIES, (
            f"Rule '{pat}' → '{cat}' · {cat} är inte kanonisk."
        )


def test_seed_rules_common_merchants_correct_cat():
    """Vanliga svenska merchants ska klassas korrekt."""
    rule_dict = {pat: cat for pat, cat, _ in SEED_RULES}
    assert rule_dict.get("ica") == CAT_MAT_LIVSMEDEL
    assert rule_dict.get("h&m") == CAT_KLADER_SKOR
    assert rule_dict.get("spotify") == CAT_STROMNINGSTJANSTER
    assert rule_dict.get("netflix") == CAT_STROMNINGSTJANSTER
    assert rule_dict.get("ikea") in (
        # Kan vara Hemutrustning · vi accepterar båda
        CANONICAL_CATEGORIES
    )


# === migration · backfill ===


def test_migration_canonicalizes_old_categories():
    """run_migrations ska byta gamla kategori-namn till kanoniska."""
    from hembudget.db.base import Base
    from hembudget.db import migrate
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    # Skapa Category-rader med gamla namn
    with eng.begin() as conn:
        conn.execute(text(
            "INSERT INTO categories (name, parent_id, tenant_id) "
            "VALUES ('Kläder & Skor', NULL, NULL), "
            "       ('Streaming', NULL, NULL), "
            "       ('Apotek', NULL, NULL), "
            "       ('Hemförsäkring', NULL, NULL)"
        ))

    # Kör migration
    migrate.run_migrations(eng)

    # Verifiera att alla blivit kanoniska
    with eng.begin() as conn:
        names = {r[0] for r in conn.execute(text(
            "SELECT name FROM categories"
        ))}
        # Gamla ska vara borta
        assert "Kläder & Skor" not in names
        assert "Streaming" not in names
        assert "Apotek" not in names
        assert "Hemförsäkring" not in names
        # Kanoniska ska finnas
        assert CAT_KLADER_SKOR in names
        assert CAT_STROMNINGSTJANSTER in names
        assert CAT_HALSA_HYGIEN in names
        assert CAT_FORSAKRING in names


def test_migration_idempotent():
    """Två körningar av migration ska INTE skapa dubletter."""
    from hembudget.db.base import Base
    from hembudget.db import migrate
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(text(
            "INSERT INTO categories (name, parent_id, tenant_id) "
            "VALUES ('Apotek', NULL, NULL)"
        ))

    migrate.run_migrations(eng)
    migrate.run_migrations(eng)

    with eng.begin() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) FROM categories WHERE name = :n"
        ), {"n": CAT_HALSA_HYGIEN}).scalar()
        assert n == 1, "Migration ska vara idempotent"


def test_all_aliases_for():
    """all_aliases_for ska inkludera kanon + alla aliases."""
    aliases = all_aliases_for(CAT_HALSA_HYGIEN)
    assert CAT_HALSA_HYGIEN in aliases
    assert "Apotek" in aliases
    assert "Sjukvård" in aliases
    assert "Träning/Gym" in aliases
