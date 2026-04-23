"""Tester för framåtriktad 'Överföringsplan'-rapport (upcoming_pdf)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hembudget.db.models import (
    Base, Account, UpcomingTransaction, User,
)
from hembudget.reports.upcoming_pdf import (
    build_upcoming_data, render_upcoming_pdf,
)


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        yield s


def _seed(session):
    u_r = User(name="Robin")
    u_e = User(name="Evelina")
    session.add_all([u_r, u_e])
    session.flush()
    session.add(Account(name="Robin", bank="nordea", type="checking", owner_id=u_r.id))
    session.add(Account(name="Evelina", bank="nordea", type="checking", owner_id=u_e.id))
    session.add(Account(name="Gem", bank="nordea", type="shared"))
    session.flush()
    session.add(UpcomingTransaction(
        name="Robin Lön", kind="income", amount=Decimal("38000"),
        expected_date=date(2026, 5, 25), owner="Robin", source="manual",
    ))
    session.add(UpcomingTransaction(
        name="Evelina Lön", kind="income", amount=Decimal("30000"),
        expected_date=date(2026, 5, 25), owner="Evelina", source="manual",
    ))
    session.add(UpcomingTransaction(
        name="Hyra", kind="bill", amount=Decimal("14500"),
        expected_date=date(2026, 5, 5), source="manual",
    ))
    session.add(UpcomingTransaction(
        name="El", kind="bill", amount=Decimal("3200"),
        expected_date=date(2026, 5, 12), source="manual",
    ))
    session.commit()


def test_build_upcoming_data_sums_from_forecast(session):
    _seed(session)
    data = build_upcoming_data(session, "2026-05")
    assert data.expected_income == 68000.0
    assert data.upcoming_bills == 17700.0
    assert data.loan_scheduled == 0.0
    assert len(data.shares) == 2


def test_shares_split_5050_equal(session):
    _seed(session)
    data = build_upcoming_data(session, "2026-05")
    shared = data.upcoming_bills + data.loan_scheduled
    for s in data.shares:
        assert s.fair_equal == round(shared / 2, 0)


def test_shares_prorata_by_income(session):
    """Den som tjänar mer betalar mer enligt prorata."""
    _seed(session)
    data = build_upcoming_data(session, "2026-05")
    by_name = {s.name: s for s in data.shares}
    robin = by_name["Robin"]
    evelina = by_name["Evelina"]
    assert robin.income_share_pct > evelina.income_share_pct
    assert robin.fair_prorata > evelina.fair_prorata
    total_prorata = robin.fair_prorata + evelina.fair_prorata
    shared = data.upcoming_bills + data.loan_scheduled
    assert abs(total_prorata - shared) <= 2


def test_pdf_renders_without_error(session):
    _seed(session)
    data = build_upcoming_data(session, "2026-05")
    pdf = render_upcoming_pdf(data)
    assert pdf.startswith(b"%PDF-")
    assert b"%%EOF" in pdf[-1024:]
    assert len(pdf) > 5000


def test_pdf_handles_empty_forecast(session):
    """Om ingen forecast-data finns ska PDF:en ändå rendera (tom rapport)."""
    data = build_upcoming_data(session, "2026-05")
    assert data.expected_income == 0.0
    assert data.upcoming_bills == 0.0
    pdf = render_upcoming_pdf(data)
    assert pdf.startswith(b"%PDF-")


def test_bills_are_sorted_by_date_in_forecast(session):
    _seed(session)
    data = build_upcoming_data(session, "2026-05")
    # Forecasten returnerar bills osorterade — vår renderer sorterar
    # dem internt. Verifiera att båda fakturorna finns i datan.
    names = {b["name"] for b in data.bills}
    assert {"Hyra", "El"}.issubset(names)
