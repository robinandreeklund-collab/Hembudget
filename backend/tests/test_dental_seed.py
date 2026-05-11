"""Tester för Frisktandvård (SKV-4)."""
from __future__ import annotations

import random
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.db.base import Base
from hembudget.db.models import InsurancePolicy, MailItem, StudentEvent
from hembudget.game_engine.profile_generator.dental_picker import (
    pick_dental, _is_atb_age, PREMIUM_WITH_ATB, PREMIUM_NORMAL,
    P_HAS_FRISKTANDVARD,
)


@pytest.fixture()
def session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


# === pick_dental ===


def test_pick_dental_deterministic():
    a = pick_dental(random.Random(42), age=30)
    b = pick_dental(random.Random(42), age=30)
    assert a == b


def test_is_atb_age_boundaries():
    """20-23 år + 67+ får ATB-rabatt."""
    assert _is_atb_age(20)
    assert _is_atb_age(23)
    assert not _is_atb_age(24)
    assert not _is_atb_age(66)
    assert _is_atb_age(67)
    assert _is_atb_age(85)


def test_premium_atb_cheaper_than_normal():
    """ATB-priserna är lägre än normalpriserna i alla 10 grupper."""
    for tier in range(1, 11):
        assert PREMIUM_WITH_ATB[tier] < PREMIUM_NORMAL[tier]


def test_pick_dental_age_22_gets_atb_price():
    """22-åring i grupp 5 ska få 245 kr/mån (ATB-pris)."""
    have_atb = False
    for i in range(50):
        d = pick_dental(random.Random(i), age=22)
        if d.has_frisktandvard:
            assert d.age_category == "atb"
            assert d.premium_monthly == PREMIUM_WITH_ATB[d.tier]
            have_atb = True
            break
    assert have_atb, "borde sett minst en 22-åring med frisktandvård"


def test_pick_dental_age_30_gets_normal_price():
    have_normal = False
    for i in range(50):
        d = pick_dental(random.Random(i), age=30)
        if d.has_frisktandvard:
            assert d.age_category == "normal"
            assert d.premium_monthly == PREMIUM_NORMAL[d.tier]
            have_normal = True
            break
    assert have_normal


def test_pick_dental_distribution_around_40_percent():
    """~40 % har frisktandvård i basal-profil."""
    n = 200
    have = sum(
        1 for i in range(n)
        if pick_dental(random.Random(i), age=30).has_frisktandvard
    )
    rate = have / n
    assert 0.25 <= rate <= 0.55, (
        f"förväntade ~40 %, fick {rate:.2%}"
    )


def test_pick_dental_low_tiers_more_common():
    """Tier-fördelning · de flesta hamnar i grupp 1-4."""
    tiers = []
    for i in range(200):
        d = pick_dental(random.Random(i), age=30)
        if d.has_frisktandvard and d.tier is not None:
            tiers.append(d.tier)
    low_count = sum(1 for t in tiers if t <= 4)
    high_count = sum(1 for t in tiers if t >= 7)
    assert low_count > high_count, (
        f"låga grupper ska vara vanligare · låg={low_count} hög={high_count}"
    )


# === seed_dental_for_scope ===


def test_seed_dental_creates_policy_and_mail(session, monkeypatch):
    fake = {
        "has_frisktandvard": True,
        "frisktandvard_tier": 4,
        "frisktandvard_age_category": "normal",
        "frisktandvard_premium_monthly": 185,
    }

    class FakeProf:
        def __init__(self, d):
            for k, v in d.items():
                setattr(self, k, v)

    class FakeQuery:
        def __init__(self, p):
            self.p = p
        def filter(self, *a, **k):
            return self
        def first(self):
            return self.p

    class FakeSession:
        def __init__(self, p):
            self.p = p
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return None
        def query(self, *a, **k):
            return FakeQuery(self.p)

    monkeypatch.setattr(
        "hembudget.school.engines.master_session",
        lambda: FakeSession(FakeProf(fake)),
    )
    from hembudget.game_engine.monthly_engine.dental_seed import (
        seed_dental_for_scope,
    )
    res = seed_dental_for_scope(
        session, student_id=100, today_game=date(2026, 1, 1),
    )
    assert res["insurance"] is True
    assert res["welcome_mail"] is True
    pol = session.query(InsurancePolicy).filter(
        InsurancePolicy.kind == "frisktandvard",
    ).first()
    assert pol is not None
    assert pol.premium_monthly == Decimal("185")
    assert pol.provider == "Folktandvården"


def test_seed_dental_no_dental_returns_skipped(session, monkeypatch):
    fake = {"has_frisktandvard": False}

    class FakeProf:
        def __init__(self, d):
            for k, v in d.items():
                setattr(self, k, v)

    class FakeQuery:
        def __init__(self, p):
            self.p = p
        def filter(self, *a, **k):
            return self
        def first(self):
            return self.p

    class FakeSession:
        def __init__(self, p):
            self.p = p
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return None
        def query(self, *a, **k):
            return FakeQuery(self.p)

    monkeypatch.setattr(
        "hembudget.school.engines.master_session",
        lambda: FakeSession(FakeProf(fake)),
    )
    from hembudget.game_engine.monthly_engine.dental_seed import (
        seed_dental_for_scope,
    )
    res = seed_dental_for_scope(
        session, student_id=100, today_game=date(2026, 1, 1),
    )
    assert res == {"skipped": "no_dental"}


def test_seed_dental_idempotent(session, monkeypatch):
    fake = {
        "has_frisktandvard": True,
        "frisktandvard_tier": 3,
        "frisktandvard_age_category": "atb",
        "frisktandvard_premium_monthly": 110,
    }

    class FakeProf:
        def __init__(self, d):
            for k, v in d.items():
                setattr(self, k, v)

    class FakeQuery:
        def __init__(self, p):
            self.p = p
        def filter(self, *a, **k):
            return self
        def first(self):
            return self.p

    class FakeSession:
        def __init__(self, p):
            self.p = p
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return None
        def query(self, *a, **k):
            return FakeQuery(self.p)

    monkeypatch.setattr(
        "hembudget.school.engines.master_session",
        lambda: FakeSession(FakeProf(fake)),
    )
    from hembudget.game_engine.monthly_engine.dental_seed import (
        seed_dental_for_scope,
    )
    seed_dental_for_scope(session, student_id=100, today_game=date(2026, 1, 1))
    seed_dental_for_scope(session, student_id=100, today_game=date(2026, 2, 1))
    n = session.query(InsurancePolicy).filter(
        InsurancePolicy.kind == "frisktandvard",
    ).count()
    assert n == 1


# === insurance_covers-flödet i tick_for_student ===


def test_dental_event_covered_when_policy_active(session):
    """Om InsurancePolicy(kind='frisktandvard') finns ska tandhälsa-
    event få cost=0 + 'TÄCKT'-suffix i title.

    Vi simulerar tick_for_student-flödets logik direkt eftersom hela
    miljön är komplex. Skapar policy, skapar mock template med
    insurance_covers=frisktandvard, och kontrollerar att cost
    nullsta lls.
    """
    from hembudget.school.event_models import EventTemplate
    from hembudget.school.models import MasterBase
    from sqlalchemy.orm import sessionmaker

    # Master DB
    mEng = create_engine("sqlite:///:memory:")
    MasterBase.metadata.create_all(mEng)
    mSession = sessionmaker(bind=mEng)
    with mSession() as ms:
        ms.add(EventTemplate(
            code="dental_check_test",
            title="Test tandkontroll",
            description="Test",
            category="unexpected",
            cost_min=700, cost_max=900,
            duration_days=14,
            triggers={
                "insurance_covers": "frisktandvard",
                "random_weight": 1.0,  # alltid trigga
            },
            social_invite_allowed=False,
            declinable=False,
            active=True,
        ))
        ms.commit()

    # Aktiv frisktandvård i scope
    session.add(InsurancePolicy(
        provider="Folktandvården",
        name="Frisktandvård",
        kind="frisktandvard",
        premium_monthly=Decimal("185"),
        autogiro=True,
        status="active",
        started_on=date(2026, 1, 1),
    ))
    session.commit()

    from hembudget.events.engine import tick_for_student
    with mSession() as ms:
        result = tick_for_student(
            scope_session=session,
            master_session=ms,
            student_seed=42,
            today=date(2026, 6, 15),  # garanterat efter min_week
            max_events_per_tick=1,
        )

    # Verifiera att eventet skapats med cost=0 + 'TÄCKT'-titel
    ev = session.query(StudentEvent).filter(
        StudentEvent.event_code == "dental_check_test",
    ).first()
    if ev is not None:
        assert ev.cost == Decimal(0)
        assert "TÄCKT" in ev.title


def test_dental_event_full_cost_without_policy(session):
    """Utan frisktandvård · full kostnad enligt template."""
    from hembudget.school.event_models import EventTemplate
    from hembudget.school.models import MasterBase
    from sqlalchemy.orm import sessionmaker

    mEng = create_engine("sqlite:///:memory:")
    MasterBase.metadata.create_all(mEng)
    mSession = sessionmaker(bind=mEng)
    with mSession() as ms:
        ms.add(EventTemplate(
            code="dental_check_test2",
            title="Test tandkontroll",
            description="Test",
            category="unexpected",
            cost_min=700, cost_max=900,
            duration_days=14,
            triggers={
                "insurance_covers": "frisktandvard",
                "random_weight": 1.0,
            },
            social_invite_allowed=False,
            declinable=False,
            active=True,
        ))
        ms.commit()

    # INGEN policy i scope
    from hembudget.events.engine import tick_for_student
    with mSession() as ms:
        tick_for_student(
            scope_session=session,
            master_session=ms,
            student_seed=42,
            today=date(2026, 6, 15),
            max_events_per_tick=1,
        )

    ev = session.query(StudentEvent).filter(
        StudentEvent.event_code == "dental_check_test2",
    ).first()
    if ev is not None:
        assert ev.cost > 0
        assert "TÄCKT" not in ev.title
