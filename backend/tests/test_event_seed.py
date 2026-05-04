"""Tester för event-seedmotor."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.school.event_models import EventTemplate
from hembudget.school.event_seed import EVENT_TEMPLATES, seed_event_templates
from hembudget.school.models import MasterBase


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    MasterBase.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_seed_creates_all_templates(session):
    n = seed_event_templates(session)
    assert n == len(EVENT_TEMPLATES)
    assert session.query(EventTemplate).count() == n


def test_seed_is_idempotent(session):
    seed_event_templates(session)
    n2 = seed_event_templates(session)
    assert n2 == 0


def test_codes_are_unique():
    codes = [t["code"] for t in EVENT_TEMPLATES]
    assert len(codes) == len(set(codes)), "duplicates: " + str(
        [c for c in codes if codes.count(c) > 1]
    )


def test_all_templates_have_costs():
    for t in EVENT_TEMPLATES:
        assert t["cost_min"] >= 0
        assert t["cost_max"] >= t["cost_min"]


def test_unexpected_events_not_declinable():
    """Oförutsedda kostnader ska aldrig vara declinable — eleven kan
    inte tacka nej till tandvärken."""
    for t in EVENT_TEMPLATES:
        if t["category"] == "unexpected":
            assert t.get("declinable") is False


def test_categories_are_valid():
    valid = {
        "social", "family", "culture", "sport", "opportunity",
        "unexpected", "mat", "lifestyle",
    }
    for t in EVENT_TEMPLATES:
        assert t["category"] in valid


def test_social_invite_only_for_social_categories():
    """Bara social/family/culture/sport får tillåta klasskompis-bjudningar
    — det vore konstigt att bjuda en kompis på din tandläkarräkning."""
    for t in EVENT_TEMPLATES:
        if t.get("social_invite_allowed"):
            assert t["category"] in {"social", "family", "culture", "sport", "mat"}


def test_seeded_template_has_all_fields(session):
    seed_event_templates(session)
    t = session.query(EventTemplate).filter(
        EventTemplate.code == "bio_filmstaden",
    ).first()
    assert t is not None
    assert t.brand == "Filmstaden"
    assert t.impact_social == 3
    assert t.declinable is True
    assert t.social_invite_allowed is True
