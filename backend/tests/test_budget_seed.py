"""Tester för KV-budget-seeden vid student-skapande.

`seed_initial_budget` ska sätta Budget-rader för rätt kategorier, med
KV-baserade belopp, idempotent (befintliga rörs ej).
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def session():
    """Frittstående scope-DB-session utan tenant-filter."""
    from hembudget.db.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False,
    )
    s = SessionLocal()
    yield s
    s.close()


def _stub_profile(*, partner=False, children=0):
    """Bygg en GeneratedProfile-stub för seed-test (utan att gå
    igenom hela profile_generator)."""
    from hembudget.game_engine.profile_generator.schema import (
        FamilyChoice,
        GeneratedProfile,
        HousingChoice,
        PentagonInit,
    )
    fam = FamilyChoice(
        status=(
            "familj_med_barn" if children > 0
            else ("sambo" if partner else "ensam")
        ),
        partner_model="ai" if partner else "solo",
        partner_yrke_key="larare" if partner else None,
        partner_gross_monthly=32_000 if partner else None,
        children_count=children,
        children_ages=[5 + i for i in range(children)],
    )
    housing = HousingChoice(
        type="hyresratt", monthly_cost=8_000, size_kvm=45,
    )
    pentagon = PentagonInit(
        economy=60, safety=55, health=60, social=55, leisure=55,
    )
    gross = 32_000 + (32_000 if partner else 0)
    net = 23_000 + (23_000 if partner else 0)
    return GeneratedProfile(
        seed=1,
        name="Test",
        yrke_key="larare",
        yrke_display="Lärare",
        yrke_ssyk="2330",
        monthly_gross=32_000,
        monthly_net=23_000,
        city_key="goteborg",
        city_display="Göteborg",
        region="Västra Götaland",
        housing=housing,
        family=fam,
        household_gross_monthly=gross,
        household_net_monthly=net,
        pentagon=pentagon,
        facts={"age": 30},
    )


def test_seed_creates_budget_rows_for_singel(session):
    from hembudget.budget.seed import seed_initial_budget
    from hembudget.db.models import Budget

    profile = _stub_profile()
    info = seed_initial_budget(
        session, profile=profile, year_month="2026-05",
    )
    session.flush()

    rows = session.query(Budget).filter(Budget.month == "2026-05").all()
    assert info["created"] >= 5  # minst mat + el + bredband + indiv-split
    assert len(rows) == info["created"]

    # Mat ska vara KV-singel-25-50 = 2 730 (lagrad NEGATIV)
    from hembudget.db.models import Category
    mat_cat = (
        session.query(Category)
        .filter(Category.name == "Mat & livsmedel")
        .first()
    )
    assert mat_cat is not None
    mat_budget = (
        session.query(Budget)
        .filter(
            Budget.month == "2026-05",
            Budget.category_id == mat_cat.id,
        )
        .first()
    )
    assert mat_budget is not None
    assert mat_budget.planned_amount == Decimal("-2730")


def test_seed_is_idempotent(session):
    """Andra seed-körningen ska inte skapa duplikat eller skriva över."""
    from hembudget.budget.seed import seed_initial_budget
    from hembudget.db.models import Budget

    profile = _stub_profile()
    info1 = seed_initial_budget(
        session, profile=profile, year_month="2026-05",
    )
    session.flush()
    info2 = seed_initial_budget(
        session, profile=profile, year_month="2026-05",
    )
    session.flush()
    assert info2["created"] == 0
    assert info2["skipped_existing"] == info1["created"]


def test_seed_doesnt_overwrite_student_changes(session):
    """Om eleven satt egen budget innan re-seed → behålls."""
    from hembudget.budget.seed import seed_initial_budget
    from hembudget.db.models import Budget, Category

    # Förbered: skapa Mat-kategori och en användarvald budget
    cat = Category(name="Mat & livsmedel")
    session.add(cat)
    session.flush()
    session.add(Budget(
        month="2026-05",
        category_id=cat.id,
        planned_amount=Decimal("-1000"),
    ))
    session.flush()

    profile = _stub_profile()
    seed_initial_budget(session, profile=profile, year_month="2026-05")
    session.flush()

    mat_b = (
        session.query(Budget)
        .filter(
            Budget.month == "2026-05",
            Budget.category_id == cat.id,
        )
        .first()
    )
    assert mat_b.planned_amount == Decimal("-1000")  # ej överskriven


def test_seed_familj_med_barn_higher_mat(session):
    """Familj med barn ska få högre mat-budget än singel."""
    from hembudget.budget.seed import seed_initial_budget
    from hembudget.db.models import Budget, Category

    profile = _stub_profile(partner=True, children=2)
    seed_initial_budget(
        session, profile=profile, year_month="2026-05",
    )
    session.flush()

    mat_cat = (
        session.query(Category)
        .filter(Category.name == "Mat & livsmedel")
        .first()
    )
    mat_b = (
        session.query(Budget)
        .filter(
            Budget.month == "2026-05",
            Budget.category_id == mat_cat.id,
        )
        .first()
    )
    # 2730 + 2730 + 2 × 1710 (barn 5+6 år, 4-6 + 7-10 åldersgrupper)
    # 5 år → 1710, 6 år → 1710 → 2730+2730+1710+1710 = 8880
    assert abs(int(mat_b.planned_amount)) >= 7_000
