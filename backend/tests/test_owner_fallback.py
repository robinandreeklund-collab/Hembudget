"""Test för _resolve_owner_bucket_key fallback till account.owner_id.

Användsfall: en kommande lön läggs in på frugans konto utan att
fritext-fältet 'owner' fylls i. Då ska den ändå räknas till henne i
familjeöversikten/YTD — INTE som 'Gemensamt'.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def session():
    from hembudget.db.models import Base

    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SL = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = SL()
    try:
        yield s
    finally:
        s.close()


def test_resolve_uses_account_owner_when_string_blank():
    from hembudget.chat.tools import _resolve_owner_bucket_key

    user_map = {"Evelina": 2}
    assert _resolve_owner_bucket_key(None, user_map, fallback_account_owner_id=2) == "user_2"
    assert _resolve_owner_bucket_key("", user_map, fallback_account_owner_id=2) == "user_2"
    assert _resolve_owner_bucket_key("  ", user_map, fallback_account_owner_id=2) == "user_2"


def test_resolve_returns_gemensamt_only_when_both_blank():
    from hembudget.chat.tools import _resolve_owner_bucket_key

    assert _resolve_owner_bucket_key(None, {}, fallback_account_owner_id=None) == "gemensamt"


def test_resolve_owner_string_takes_precedence_over_fallback():
    """Om användaren explicit har skrivit owner ska det respekteras
    även om kontot tillhör någon annan."""
    from hembudget.chat.tools import _resolve_owner_bucket_key

    assert (
        _resolve_owner_bucket_key("Robin", {"Robin": 1, "Evelina": 2}, fallback_account_owner_id=2)
        == "user_1"
    )


def test_ytd_unmatched_income_attributed_to_account_owner(session):
    """Komande lön på frugans konto utan owner-text ska räknas som
    user_2, inte gemensamt."""
    from hembudget.chat.tools import ytd_income_by_person
    from hembudget.db.models import Account, Category, User, UpcomingTransaction

    robin = User(name="Robin")
    evelina = User(name="Evelina")
    session.add_all([robin, evelina]); session.flush()

    her_account = Account(
        name="Evelinas konto", bank="nordea", type="checking",
        owner_id=evelina.id,
    )
    session.add(her_account); session.flush()

    # Sätt en kategori "Lön" så den hittas (annars kör fallback)
    cat = Category(name="Lön")
    session.add(cat); session.commit()

    # Komande lön — owner är tom, men debit_account_id pekar på frugans konto
    up = UpcomingTransaction(
        kind="income", name="Evelina Lön april",
        amount=Decimal("35604"),
        expected_date=date(2026, 4, 25),
        debit_account_id=her_account.id,
        # owner är None — användaren har inte fyllt i fältet
    )
    session.add(up); session.commit()

    result = ytd_income_by_person(session, year=2026)
    assert "user_2" in result["by_owner"]
    assert result["by_owner"]["user_2"]["total"] == pytest.approx(35604.0)
    # INGEN gemensamt-bucket eftersom fallback funkade
    assert "gemensamt" not in result["by_owner"]
