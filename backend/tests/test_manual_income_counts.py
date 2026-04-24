"""Tester för att manuella kommande löner/fakturor med passerat datum
räknas som riktiga inkomster/utgifter — utan att behöva importera
partnerns kontoutdrag."""
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
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = S()
    # Seed category
    from hembudget.db.models import Category
    s.add(Category(name="Lön", parent_id=None))
    s.commit()
    try:
        yield s
    finally:
        s.close()


def test_manual_income_counts_in_ytd_when_user_exists(session):
    """Användaren har lagt till 'Evelina' som medlem + manuellt en lön
    för henne. Den ska dyka upp under user_{evelina_id} i YTD."""
    from hembudget.db.models import User, UpcomingTransaction
    from hembudget.chat.tools import ytd_income_by_person

    eve = User(name="Evelina")
    session.add(eve); session.flush()

    # Robin lägger in fruns lön manuellt (datum passerat)
    session.add(UpcomingTransaction(
        kind="income", name="Inkab",
        amount=Decimal("30000"),
        expected_date=date(2026, 3, 25),
        owner="Evelina",
        source="manual",
    ))
    session.commit()

    result = ytd_income_by_person(session, year=2026)
    assert result["grand_total"] == pytest.approx(30000.0)
    key = f"user_{eve.id}"
    assert key in result["by_owner"]
    assert result["by_owner"][key]["total"] == pytest.approx(30000.0)
    assert result["by_owner"][key]["count"] == 1


def test_manual_income_counts_in_ytd_when_user_missing(session):
    """Om man lägger in 'Evelina' som owner UTAN att först skapa user —
    ska ändå räknas, under raw-string-key."""
    from hembudget.db.models import UpcomingTransaction
    from hembudget.chat.tools import ytd_income_by_person

    session.add(UpcomingTransaction(
        kind="income", name="Inkab",
        amount=Decimal("30000"),
        expected_date=date(2026, 2, 25),
        owner="Evelina",
    ))
    session.commit()

    result = ytd_income_by_person(session, year=2026)
    assert "Evelina" in result["by_owner"]
    assert result["by_owner"]["Evelina"]["total"] == pytest.approx(30000.0)


def test_manual_income_combined_with_real_transaction(session):
    """Robin har riktig lön via CSV, frun har manuell upcoming —
    båda räknas, rätt fördelade."""
    from hembudget.db.models import (
        Account, Category, Transaction, UpcomingTransaction, User,
    )
    from hembudget.chat.tools import ytd_income_by_person

    robin = User(name="Robin")
    session.add(robin); session.flush()
    acc = Account(
        name="Robins lönekonto", bank="nordea", type="checking",
        owner_id=robin.id,
    )
    session.add(acc); session.flush()
    lon = session.query(Category).filter(Category.name == "Lön").one()
    session.add(Transaction(
        account_id=acc.id, date=date(2026, 2, 25),
        amount=Decimal("35000"), currency="SEK",
        raw_description="Inkab", hash="h1",
        category_id=lon.id,
    ))
    # Frugans manuella lön (owner-sträng som inte finns som User än)
    session.add(UpcomingTransaction(
        kind="income", name="Evelinas jobb",
        amount=Decimal("30000"),
        expected_date=date(2026, 2, 28),
        owner="Evelina",
    ))
    session.commit()

    result = ytd_income_by_person(session, year=2026)
    assert result["grand_total"] == pytest.approx(65000.0)
    assert f"user_{robin.id}" in result["by_owner"]
    assert "Evelina" in result["by_owner"]


def test_matched_upcoming_not_double_counted(session):
    """Om en manuell upcoming redan matchats mot en Transaction ska den
    INTE räknas en gång till — Transaction är källan."""
    from hembudget.db.models import (
        Account, Category, Transaction, UpcomingTransaction, User,
    )
    from hembudget.chat.tools import ytd_income_by_person

    robin = User(name="Robin")
    session.add(robin); session.flush()
    acc = Account(
        name="A", bank="nordea", type="checking", owner_id=robin.id,
    )
    session.add(acc); session.flush()
    lon = session.query(Category).filter(Category.name == "Lön").one()
    tx = Transaction(
        account_id=acc.id, date=date(2026, 2, 25),
        amount=Decimal("35000"), currency="SEK",
        raw_description="Inkab", hash="h1",
        category_id=lon.id,
    )
    session.add(tx); session.flush()

    # Upcoming som matchats mot tx
    session.add(UpcomingTransaction(
        kind="income", name="Inkab",
        amount=Decimal("35000"),
        expected_date=date(2026, 2, 25),
        owner="Robin",
        matched_transaction_id=tx.id,
    ))
    session.commit()

    result = ytd_income_by_person(session, year=2026)
    # Bara ETT räknat: 35 000 från Transaction
    assert result["grand_total"] == pytest.approx(35000.0)


def test_family_breakdown_includes_manual_incomes_and_bills(session):
    """Familje-vyn för en månad ska summera både Transaction-rader och
    omatchade upcomings."""
    from hembudget.db.models import (
        Account, Category, Transaction, UpcomingTransaction, User,
    )
    from hembudget.chat.tools import get_family_breakdown

    robin = User(name="Robin")
    session.add(robin); session.flush()

    acc_shared = Account(
        name="Gemensamt", bank="nordea", type="shared",
    )
    acc_robin = Account(
        name="Robin Privat", bank="nordea", type="checking",
        owner_id=robin.id,
    )
    session.add_all([acc_shared, acc_robin]); session.flush()

    # Robin: verklig lön-tx
    lon = session.query(Category).filter(Category.name == "Lön").one()
    session.add(Transaction(
        account_id=acc_robin.id, date=date(2026, 3, 25),
        amount=Decimal("35000"), currency="SEK",
        raw_description="Inkab", hash="h-robin",
        category_id=lon.id,
    ))
    # Manuell lön för Evelina (ingen User, ingen CSV)
    session.add(UpcomingTransaction(
        kind="income", name="Evelinas arbetsgivare",
        amount=Decimal("30000"),
        expected_date=date(2026, 3, 25),
        owner="Evelina",
    ))
    # Manuell faktura dragen från gemensamma (inte matchad)
    session.add(UpcomingTransaction(
        kind="bill", name="Elräkning",
        amount=Decimal("3000"),
        expected_date=date(2026, 3, 27),
        debit_account_id=acc_shared.id,
    ))
    session.commit()

    result = get_family_breakdown(session, "2026-03")
    by_owner = result["by_owner"]

    # Robin: 35k income
    assert f"user_{robin.id}" in by_owner
    assert by_owner[f"user_{robin.id}"]["income"] == pytest.approx(35000.0)

    # Evelina (raw string): 30k income
    assert "Evelina" in by_owner
    assert by_owner["Evelina"]["income"] == pytest.approx(30000.0)

    # Gemensamt: 3k expenses (elräkningen)
    assert "gemensamt" in by_owner
    assert by_owner["gemensamt"]["expenses"] == pytest.approx(3000.0)


def test_owner_string_case_insensitive_match(session):
    """Om användaren skrev 'EVELINA' i en upcoming ska den ändå
    matcha User.name='Evelina'."""
    from hembudget.db.models import User, UpcomingTransaction
    from hembudget.chat.tools import ytd_income_by_person

    eve = User(name="Evelina")
    session.add(eve); session.flush()
    session.add(UpcomingTransaction(
        kind="income", name="Inkab",
        amount=Decimal("10000"),
        expected_date=date(2026, 1, 25),
        owner="EVELINA",  # versaler
    ))
    session.commit()

    result = ytd_income_by_person(session, year=2026)
    assert f"user_{eve.id}" in result["by_owner"]
    assert result["by_owner"][f"user_{eve.id}"]["total"] == pytest.approx(10000.0)
