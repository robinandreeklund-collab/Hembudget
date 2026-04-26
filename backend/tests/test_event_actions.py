"""Tester för accept/decline-endpoints."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.db.models import (
    Account,
    Base,
    StudentEvent,
    Transaction,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _make_event(s, *, code="bio_filmstaden", category="social",
                cost=180, declinable=True):
    """Skapa pending event direkt i scope-DB:n. Master-templaten
    måste seedas separat i testet om vi ska kalla accept_event-API."""
    e = StudentEvent(
        event_code=code, title="Test event", description="d",
        category=category, cost=Decimal(str(cost)),
        deadline=date.today() + timedelta(days=5),
        status="pending", declinable=declinable,
    )
    s.add(e); s.flush()
    return e


def _make_checking(s, *, opening=10_000):
    a = Account(
        name="Lön", bank="d", type="checking",
        opening_balance=Decimal(str(opening)),
        opening_balance_date=date(2026, 1, 1),
    )
    s.add(a); s.flush()
    return a


# --- DECLINE-tester (kräver inte master) ---

def test_decline_social_event_lowers_social(session):
    from hembudget.api.events import DeclineIn, decline_event
    ev = _make_event(session, category="social")
    r = decline_event(ev.id, DeclineIn(), session)
    assert r.status == "declined"
    assert r.impact_applied["social"] == -1
    assert "kostnad" in r.pedagogical_note.lower() or "ned" in r.pedagogical_note.lower()


def test_decline_with_savings_reason_no_impact(session):
    from hembudget.api.events import DeclineIn, decline_event
    ev = _make_event(session, category="social")
    r = decline_event(ev.id, DeclineIn(decision_reason="valde sparande"), session)
    assert r.status == "declined"
    assert r.impact_applied["social"] == 0
    assert "sparande" in r.pedagogical_note.lower()


def test_decline_unexpected_event_blocked(session):
    from hembudget.api.events import DeclineIn, decline_event
    ev = _make_event(session, category="unexpected", declinable=False)
    with pytest.raises(HTTPException) as exc:
        decline_event(ev.id, DeclineIn(), session)
    assert exc.value.status_code == 400
    assert "kan inte" in exc.value.detail.lower() or "går inte" in exc.value.detail.lower()


def test_decline_lifestyle_no_impact(session):
    """Lifestyle (Spotify, kläder) → neka utan impact."""
    from hembudget.api.events import DeclineIn, decline_event
    ev = _make_event(session, category="lifestyle")
    r = decline_event(ev.id, DeclineIn(), session)
    assert r.impact_applied["social"] == 0


def test_decline_already_decided_blocked(session):
    from hembudget.api.events import DeclineIn, decline_event
    ev = _make_event(session, category="social")
    ev.status = "accepted"
    session.flush()
    with pytest.raises(HTTPException) as exc:
        decline_event(ev.id, DeclineIn(), session)
    assert exc.value.status_code == 400


def test_decline_unknown_event_404(session):
    from hembudget.api.events import DeclineIn, decline_event
    with pytest.raises(HTTPException) as exc:
        decline_event(9999, DeclineIn(), session)
    assert exc.value.status_code == 404
