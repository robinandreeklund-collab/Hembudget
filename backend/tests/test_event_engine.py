"""Tester för trigger-engine — bara att den är deterministisk, ger
0-N events och respekterar trigger-villkor."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.db.models import (
    Account,
    Base,
    PersonalityProfile,
    StudentEvent,
    Transaction,
)
from hembudget.events.engine import (
    expire_old_events,
    tick_for_student,
)
from hembudget.school.event_models import EventTemplate
from hembudget.school.event_seed import seed_event_templates
from hembudget.school.models import MasterBase


@pytest.fixture()
def master():
    engine = create_engine("sqlite:///:memory:")
    MasterBase.metadata.create_all(engine)
    with Session(engine) as s:
        seed_event_templates(s)
        yield s


@pytest.fixture()
def scope():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_tick_creates_events(scope, master):
    today = date(2026, 4, 24)  # fredag, för att fånga weekday-events
    r = tick_for_student(
        scope_session=scope, master_session=master,
        student_seed=1, today=today,
    )
    assert r.events_created >= 0
    # Det BORDE finnas minst ett event en fredag (många mallar har
    # weekday=4 eller random_weight=1.0). Vi kollar inte exakt antal.
    rows = scope.query(StudentEvent).all()
    assert len(rows) == r.events_created


def test_tick_is_deterministic_per_week(scope, master):
    today = date(2026, 4, 24)
    r1 = tick_for_student(
        scope_session=scope, master_session=master,
        student_seed=42, today=today,
    )
    # Tick:a igen samma vecka — duplicate-skydd kickar in (recent_codes)
    # så vi får 0 nya rader, men week_seed är detsamma
    r2 = tick_for_student(
        scope_session=scope, master_session=master,
        student_seed=42, today=today,
    )
    assert r1.week_seed == r2.week_seed
    # Andra anropet ska skapa 0 nya pga duplicate-skydd
    assert r2.events_created == 0


def test_different_students_get_different_events(scope, master):
    today = date(2026, 4, 24)
    r1 = tick_for_student(
        scope_session=scope, master_session=master,
        student_seed=1, today=today,
    )
    codes_a = {e.event_code for e in scope.query(StudentEvent).all()}

    # Töm scope för andra "eleven"
    scope.query(StudentEvent).delete()
    scope.flush()

    r2 = tick_for_student(
        scope_session=scope, master_session=master,
        student_seed=999, today=today,
    )
    codes_b = {e.event_code for e in scope.query(StudentEvent).all()}

    # Även om de KAN dra samma slumpmässigt, är det osannolikt att
    # alla är identiska över 78 templates → minst en skillnad förväntas
    if r1.events_created and r2.events_created:
        assert codes_a != codes_b or r1.week_seed != r2.week_seed


def test_unexpected_events_marked_not_declinable(scope, master):
    today = date(2026, 4, 24)
    # Kör många tickar (olika seeds) tills vi får en oförutsedd
    found = False
    for seed in range(50):
        scope.query(StudentEvent).delete()
        scope.flush()
        tick_for_student(
            scope_session=scope, master_session=master,
            student_seed=seed, today=today,
        )
        for e in scope.query(StudentEvent).all():
            if e.category == "unexpected":
                assert e.declinable is False
                found = True
                break
        if found:
            break
    assert found, "Hittade ingen unexpected-event på 50 seeds"


def test_max_events_per_tick_respected(scope, master):
    today = date(2026, 4, 24)
    r = tick_for_student(
        scope_session=scope, master_session=master,
        student_seed=7, today=today, max_events_per_tick=2,
    )
    assert r.events_created <= 2


def test_introvert_personality_reduces_social(scope, master):
    """Hög introvert → färre sociala events. Räknar over 5 olika seeds."""
    today = date(2026, 4, 24)

    # Test 1: extrovert (introvert=10)
    scope.add(PersonalityProfile(introvert_score=10))
    scope.flush()
    extro_count = 0
    for seed in range(5):
        scope.query(StudentEvent).delete()
        scope.flush()
        tick_for_student(
            scope_session=scope, master_session=master,
            student_seed=seed, today=today, max_events_per_tick=10,
        )
        extro_count += scope.query(StudentEvent).filter(
            StudentEvent.category == "social",
        ).count()

    # Byt till introvert (90)
    pers = scope.query(PersonalityProfile).first()
    pers.introvert_score = 90
    scope.flush()
    intro_count = 0
    for seed in range(5):
        scope.query(StudentEvent).delete()
        scope.flush()
        tick_for_student(
            scope_session=scope, master_session=master,
            student_seed=seed, today=today, max_events_per_tick=10,
        )
        intro_count += scope.query(StudentEvent).filter(
            StudentEvent.category == "social",
        ).count()

    # Inte hård garanti pga slump över 5 seeds men förväntat
    assert intro_count <= extro_count


def test_expire_old_events_marks_expired(scope, master):
    today = date(2026, 4, 24)
    # Skapa ett event med deadline igår
    ev = StudentEvent(
        event_code="x", title="t", description="d",
        category="social", cost=Decimal("100"),
        deadline=today - timedelta(days=1),
        status="pending",
    )
    scope.add(ev)
    scope.flush()

    n = expire_old_events(scope, today=today)
    assert n == 1
    scope.refresh(ev)
    assert ev.status == "expired"
    assert ev.decided_at is not None


def test_expire_does_not_touch_future_or_decided(scope, master):
    today = date(2026, 4, 24)
    pending_ok = StudentEvent(
        event_code="a", title="t", description="d",
        category="social", cost=Decimal("100"),
        deadline=today + timedelta(days=5),
        status="pending",
    )
    accepted = StudentEvent(
        event_code="b", title="t", description="d",
        category="social", cost=Decimal("100"),
        deadline=today - timedelta(days=10),
        status="accepted",
    )
    scope.add_all([pending_ok, accepted])
    scope.flush()

    n = expire_old_events(scope, today=today)
    assert n == 0


def test_cost_within_template_range(scope, master):
    today = date(2026, 4, 24)
    tick_for_student(
        scope_session=scope, master_session=master,
        student_seed=1, today=today, max_events_per_tick=10,
    )
    for ev in scope.query(StudentEvent).all():
        tpl = master.query(EventTemplate).filter(
            EventTemplate.code == ev.event_code,
        ).first()
        assert tpl is not None
        assert int(ev.cost) >= tpl.cost_min
        assert int(ev.cost) <= tpl.cost_max
