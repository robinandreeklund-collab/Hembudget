"""Regressionstest: UpcomingTransaction.amount ska ALLTID lagras
positivt (konvention: tecken bestäms av kind, inte av amount)."""
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
    S = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = S()
    try:
        yield s
    finally:
        s.close()


def test_materializer_stores_positive_amount_from_negative_sub(session):
    """Subscription.amount är signerat negativt. När materializer skapar
    UpcomingTransaction ska amount vara POSITIVT."""
    from hembudget.db.models import (
        Account, Subscription, UpcomingTransaction,
    )
    from hembudget.upcoming_match.materializer import UpcomingMaterializer

    acc = Account(name="A", bank="nordea", type="checking")
    session.add(acc); session.flush()
    sub = Subscription(
        merchant="Spotify", amount=Decimal("-129"),
        interval_days=30,
        next_expected_date=date.today(),
        account_id=acc.id, active=True,
    )
    session.add(sub); session.commit()

    UpcomingMaterializer(session, horizon_days=30).run()

    ups = session.query(UpcomingTransaction).all()
    assert len(ups) >= 1
    for u in ups:
        assert u.amount > 0, (
            f"Upcoming '{u.name}' har negativt amount {u.amount} — "
            "bryter mot konvention 'alltid positivt'"
        )


def test_migration_normalizes_negative_amounts_to_positive():
    """Befintlig data med negativa amounts ska migreras till positivt."""
    from sqlalchemy import text
    from hembudget.db.models import Base, UpcomingTransaction
    from hembudget.db.migrate import run_migrations

    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    # Skapa ett upcoming med negativt amount (simulerar gammal bug-data)
    with S() as s:
        u = UpcomingTransaction(
            kind="bill", name="Gammal bugg", amount=Decimal("-299"),
            expected_date=date(2026, 3, 1),
        )
        s.add(u); s.commit()
        up_id = u.id

    # Kör migration
    applied = run_migrations(engine)
    assert any("amount normaliserad" in a for a in applied), (
        f"Förväntade migration i output, fick: {applied}"
    )

    with S() as s:
        u = s.get(UpcomingTransaction, up_id)
        assert float(u.amount) == 299.0  # flippad till positiv
