"""Tester för affordability-checken."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.credit.affordability import check_affordability
from hembudget.db.models import Account, Base, Transaction


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _acc(s, name, type_, *, opening=0, opening_date=date(2026, 1, 1),
         credit_limit=None):
    a = Account(
        name=name, bank="demo", type=type_,
        opening_balance=Decimal(str(opening)),
        opening_balance_date=opening_date,
        credit_limit=Decimal(str(credit_limit)) if credit_limit else None,
    )
    s.add(a); s.flush()
    return a


def test_checking_with_enough_balance_is_ok(session):
    acc = _acc(session, "Lön", "checking", opening=10_000)
    r = check_affordability(session, account_id=acc.id, amount=Decimal("3000"))
    assert r.ok is True
    assert r.shortfall == Decimal("0")
    assert "7000" in r.explanation or "7 000" in r.explanation


def test_checking_short_returns_shortfall_and_explanation(session):
    acc = _acc(session, "Lön", "checking", opening=2_000)
    r = check_affordability(session, account_id=acc.id, amount=Decimal("8000"))
    assert r.ok is False
    assert r.shortfall == Decimal("6000")
    assert "saknar" in r.explanation.lower()
    assert "6000" in r.explanation or "6 000" in r.explanation


def test_checking_with_threshold_blocks_at_buffer(session):
    """Threshold=1000 — saldot får inte gå under 1000 efter uttaget."""
    acc = _acc(session, "Lön", "checking", opening=5_000)
    r = check_affordability(
        session, account_id=acc.id,
        amount=Decimal("4500"), threshold=Decimal("1000"),
    )
    assert r.ok is False
    assert r.shortfall == Decimal("500")  # 1000 - (5000-4500)
    assert "buffert" in r.explanation.lower()


def test_savings_block_with_explanation(session):
    acc = _acc(session, "Spar", "savings", opening=500)
    r = check_affordability(session, account_id=acc.id, amount=Decimal("1000"))
    assert r.ok is False
    assert "sparkonto" in r.explanation.lower()
    assert r.account_kind == "savings"


def test_isk_block(session):
    acc = _acc(session, "ISK", "isk", opening=200)
    r = check_affordability(session, account_id=acc.id, amount=Decimal("500"))
    assert r.ok is False
    assert r.account_kind == "isk"


def test_credit_card_within_limit_is_ok(session):
    acc = _acc(session, "Visa", "credit", opening=0, credit_limit=10_000)
    r = check_affordability(session, account_id=acc.id, amount=Decimal("3000"))
    assert r.ok is True
    assert "kreditgränsen" in r.explanation.lower() or "kvar efter köpet" in r.explanation.lower()


def test_credit_card_over_limit_blocked(session):
    """Saldo -8000 (utnyttjat 8000), gräns 10000 → bara 2000 kvar.
    Försöker handla för 5000 → ok=False."""
    acc = _acc(session, "Visa", "credit", opening=-8_000, credit_limit=10_000)
    r = check_affordability(session, account_id=acc.id, amount=Decimal("5000"))
    assert r.ok is False
    assert r.shortfall == Decimal("3000")
    assert "kreditgränsen" in r.explanation.lower()


def test_unknown_account_returns_not_ok(session):
    r = check_affordability(session, account_id=9999, amount=Decimal("100"))
    assert r.ok is False
    assert "saknas" in r.explanation.lower()


def test_balance_includes_existing_transactions(session):
    acc = _acc(session, "Lön", "checking", opening=10_000)
    # Existerande utgift
    session.add(Transaction(
        account_id=acc.id, date=date(2026, 4, 1),
        amount=Decimal("-3000"), currency="SEK",
        raw_description="x", hash="h1",
    ))
    session.flush()
    # 10000 - 3000 = 7000 kvar; vi vill ta 5000 → går
    r = check_affordability(session, account_id=acc.id, amount=Decimal("5000"))
    assert r.ok is True
    # Vi vill ta 8000 → går inte
    r2 = check_affordability(session, account_id=acc.id, amount=Decimal("8000"))
    assert r2.ok is False
    assert r2.shortfall == Decimal("1000")
