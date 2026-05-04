"""Tester för Wellbeing-beräkningsmotorn (fas 1: bara ekonomi)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.db.models import (
    Account,
    Base,
    Budget,
    Category,
    Loan,
    Transaction,
    WellbeingScore,
)
from hembudget.wellbeing.calculator import (
    calculate_wellbeing,
    persist_wellbeing,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _acc(s, name, type_, *, opening=0):
    a = Account(
        name=name, bank="d", type=type_,
        opening_balance=Decimal(str(opening)),
        opening_balance_date=date(2026, 1, 1),
    )
    s.add(a); s.flush()
    return a


def test_baseline_returns_50_with_no_data(session):
    r = calculate_wellbeing(session, "2026-04")
    assert r.total_score == 50
    assert r.economy == 50
    assert r.health == 50
    # Inga faktorer alls = neutral
    assert len(r.factors) == 0


def test_negative_checking_lowers_economy(session):
    _acc(session, "Lön", "checking", opening=-3_000)
    r = calculate_wellbeing(session, "2026-04")
    assert r.economy < 50
    factors_for_eco = [f for f in r.factors if f.dimension == "economy"]
    assert any("minus" in f.explanation.lower() for f in factors_for_eco)


def test_good_checking_raises_economy(session):
    _acc(session, "Lön", "checking", opening=15_000)
    r = calculate_wellbeing(session, "2026-04")
    assert r.economy > 50


def test_high_cost_credit_kills_economy(session):
    _acc(session, "Lön", "checking", opening=5_000)
    s = session
    s.add(Loan(
        name="SMS-lån X", lender="Bynk",
        principal_amount=Decimal("5000"),
        start_date=date(2026, 4, 1),
        interest_rate=0.30,
        loan_kind="sms",
        is_high_cost_credit=True,
        active=True,
    ))
    s.flush()
    r = calculate_wellbeing(s, "2026-04")
    assert r.economy < 50
    eco = [f for f in r.factors if f.dimension == "economy"]
    assert any("sms" in f.explanation.lower() for f in eco)


def test_savings_50k_max_safety(session):
    _acc(session, "Spar", "savings", opening=60_000)
    r = calculate_wellbeing(session, "2026-04")
    assert r.safety >= 70


def test_low_savings_lowers_safety(session):
    _acc(session, "Spar", "savings", opening=2_000)
    r = calculate_wellbeing(session, "2026-04")
    assert r.safety < 50


def test_budget_violation_lowers_health(session):
    s = session
    cat = Category(name="Mat", parent_id=None)
    s.add(cat); s.flush()
    # Mat-min är 2 840 kr; sätt 1 000 = subexistens
    s.add(Budget(month="2026-04", category_id=cat.id,
                 planned_amount=Decimal("1000")))
    s.flush()
    r = calculate_wellbeing(s, "2026-04")
    assert r.health < 50
    assert r.budget_violations >= 1


def test_realistic_budget_raises_health(session):
    s = session
    cat = Category(name="Mat", parent_id=None)
    s.add(cat); s.flush()
    s.add(Budget(month="2026-04", category_id=cat.id,
                 planned_amount=Decimal("3500")))
    s.flush()
    r = calculate_wellbeing(s, "2026-04")
    assert r.health > 50
    assert r.budget_violations == 0


def test_explanation_lists_factors(session):
    _acc(session, "Lön", "checking", opening=-2_000)
    r = calculate_wellbeing(session, "2026-04")
    assert "Wellbeing" in r.explanation
    assert "minus" in r.explanation.lower()


def test_total_clamp_0_to_100(session):
    """Extremfall: brutal ekonomi ska aldrig ge negativt total."""
    _acc(session, "Lön", "checking", opening=-50_000)
    s = session
    for i in range(5):
        s.add(Loan(
            name=f"SMS {i}", lender="X",
            principal_amount=Decimal("10000"),
            start_date=date(2026, 4, 1),
            interest_rate=0.5,
            loan_kind="sms",
            is_high_cost_credit=True,
            active=True,
        ))
    s.flush()
    r = calculate_wellbeing(s, "2026-04")
    assert 0 <= r.total_score <= 100
    assert 0 <= r.economy <= 100


def test_persist_creates_row(session):
    r = calculate_wellbeing(session, "2026-04")
    persist_wellbeing(session, r)
    rows = session.query(WellbeingScore).all()
    assert len(rows) == 1
    assert rows[0].year_month == "2026-04"
    assert rows[0].total_score == r.total_score


def test_accepted_events_raise_social(session):
    """Accepterat social-event med +3 social → social-dim +3."""
    from datetime import datetime, date as _d
    from hembudget.db.models import StudentEvent
    s = session
    s.add(StudentEvent(
        event_code="bio", title="Bio", description="d", category="social",
        cost=Decimal("180"),
        deadline=_d(2026, 4, 30),
        status="accepted",
        decided_at=datetime(2026, 4, 15, 10, 0, 0),
        impact_applied={"economy": 0, "health": 0, "social": 3, "leisure": 2, "safety": 0},
    ))
    s.flush()
    r = calculate_wellbeing(s, "2026-04")
    assert r.social >= 53  # 50 + 3
    assert r.events_accepted == 1


def test_many_declines_lower_social(session):
    """3+ declined social-events i samma månad → social sjunker."""
    from datetime import datetime, date as _d
    from hembudget.db.models import StudentEvent
    s = session
    for i in range(4):
        s.add(StudentEvent(
            event_code=f"x{i}", title="X", description="d",
            category="social", cost=Decimal("100"),
            deadline=_d(2026, 4, 30),
            status="declined",
            decided_at=datetime(2026, 4, 10 + i, 10, 0, 0),
            impact_applied={"social": -1, "economy": 0, "health": 0,
                            "leisure": 0, "safety": 0},
        ))
    s.flush()
    r = calculate_wellbeing(s, "2026-04")
    assert r.social < 50
    assert r.events_declined == 4


def test_persist_updates_existing(session):
    r = calculate_wellbeing(session, "2026-04")
    persist_wellbeing(session, r)
    # Ändra ekonomi och persist igen
    _acc(session, "Lön", "checking", opening=20_000)
    r2 = calculate_wellbeing(session, "2026-04")
    persist_wellbeing(session, r2)
    rows = session.query(WellbeingScore).all()
    assert len(rows) == 1
    assert rows[0].total_score == r2.total_score
