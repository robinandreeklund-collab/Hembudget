"""Tester för POST /transfers/create — proaktiv elev-överföring.

Vi testar endpoint-funktionen direkt mot en in-memory SQLite, exakt
som test_transfers.py gör för TransferDetector. FastAPI-app behövs
inte — funktionen tar emot redan upplöst payload och Session.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.api.transfers import (
    CreateTransferIn,
    _balance_for,
    create_transfer,
)
from hembudget.db.models import Account, Base, Transaction


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _acc(s, name, type_, *, opening=None, opening_date=None):
    a = Account(
        name=name,
        bank="nordea",
        type=type_,
        opening_balance=Decimal(str(opening)) if opening is not None else None,
        opening_balance_date=opening_date,
    )
    s.add(a)
    s.flush()
    return a


def test_create_basic_transfer_creates_two_paired_transactions(session):
    src = _acc(session, "Lön", "checking", opening=10000, opening_date=date(2026, 1, 1))
    dst = _acc(session, "Spar", "savings", opening=0, opening_date=date(2026, 1, 1))

    payload = CreateTransferIn(
        from_account_id=src.id, to_account_id=dst.id, amount=Decimal("500"),
    )
    result = create_transfer(payload, session)

    assert result["ok"] is True
    assert result["amount"] == 500.0
    assert result["from_balance_after"] == 9500.0
    assert result["to_balance_after"] == 500.0

    src_tx = session.get(Transaction, result["source_tx_id"])
    dst_tx = session.get(Transaction, result["destination_tx_id"])
    assert src_tx.amount == Decimal("-500")
    assert dst_tx.amount == Decimal("500")
    assert src_tx.is_transfer and dst_tx.is_transfer
    assert src_tx.transfer_pair_id == dst_tx.id
    assert dst_tx.transfer_pair_id == src_tx.id


def test_create_rejects_same_account(session):
    a = _acc(session, "Lön", "checking", opening=1000, opening_date=date(2026, 1, 1))
    payload = CreateTransferIn(
        from_account_id=a.id, to_account_id=a.id, amount=Decimal("100"),
    )
    with pytest.raises(HTTPException) as exc:
        create_transfer(payload, session)
    assert exc.value.status_code == 400
    assert "olika" in exc.value.detail.lower()


def test_create_rejects_unknown_account(session):
    src = _acc(session, "Lön", "checking", opening=1000, opening_date=date(2026, 1, 1))
    payload = CreateTransferIn(
        from_account_id=src.id, to_account_id=9999, amount=Decimal("100"),
    )
    with pytest.raises(HTTPException) as exc:
        create_transfer(payload, session)
    assert exc.value.status_code == 404


def test_create_blocks_negative_savings(session):
    src = _acc(session, "Spar", "savings", opening=200, opening_date=date(2026, 1, 1))
    dst = _acc(session, "Lön", "checking", opening=0, opening_date=date(2026, 1, 1))

    payload = CreateTransferIn(
        from_account_id=src.id, to_account_id=dst.id, amount=Decimal("500"),
    )
    with pytest.raises(HTTPException) as exc:
        create_transfer(payload, session)
    assert exc.value.status_code == 400
    assert "minus" in exc.value.detail.lower()


def test_create_blocks_negative_isk(session):
    """ISK ska aldrig kunna gå minus — samma regel som sparkonto."""
    src = _acc(session, "ISK", "isk", opening=100, opening_date=date(2026, 1, 1))
    dst = _acc(session, "Lön", "checking", opening=0, opening_date=date(2026, 1, 1))
    payload = CreateTransferIn(
        from_account_id=src.id, to_account_id=dst.id, amount=Decimal("500"),
    )
    with pytest.raises(HTTPException) as exc:
        create_transfer(payload, session)
    assert exc.value.status_code == 400
    assert "ISK-kontot" in exc.value.detail


def test_create_blocks_negative_pension(session):
    """Pensionskonto ska aldrig kunna gå minus."""
    src = _acc(session, "Pension", "pension", opening=100, opening_date=date(2026, 1, 1))
    dst = _acc(session, "Lön", "checking", opening=0, opening_date=date(2026, 1, 1))
    payload = CreateTransferIn(
        from_account_id=src.id, to_account_id=dst.id, amount=Decimal("500"),
    )
    with pytest.raises(HTTPException) as exc:
        create_transfer(payload, session)
    assert exc.value.status_code == 400
    assert "Pensionskontot" in exc.value.detail


def test_create_allows_negative_checking(session):
    """Checking får gå minus — pedagogiskt: man kan övertrassera lön men
    inte sparkonto."""
    src = _acc(session, "Lön", "checking", opening=100, opening_date=date(2026, 1, 1))
    dst = _acc(session, "Spar", "savings", opening=0, opening_date=date(2026, 1, 1))

    payload = CreateTransferIn(
        from_account_id=src.id, to_account_id=dst.id, amount=Decimal("500"),
    )
    result = create_transfer(payload, session)
    assert result["from_balance_after"] == -400.0


def test_create_idempotency_key_prevents_duplicate(session):
    src = _acc(session, "Lön", "checking", opening=10000, opening_date=date(2026, 1, 1))
    dst = _acc(session, "Spar", "savings", opening=0, opening_date=date(2026, 1, 1))

    payload = CreateTransferIn(
        from_account_id=src.id,
        to_account_id=dst.id,
        amount=Decimal("500"),
        idempotency_key="abc-123",
    )
    r1 = create_transfer(payload, session)
    r2 = create_transfer(payload, session)

    assert r2.get("idempotent") is True
    assert r2["source_tx_id"] == r1["source_tx_id"]
    # Bara två transaktioner totalt — ingen dubblering
    assert session.query(Transaction).count() == 2


def test_balance_helper_includes_opening_balance(session):
    a = _acc(session, "Lön", "checking", opening=1000, opening_date=date(2026, 1, 1))
    assert _balance_for(session, a.id) == Decimal("1000")
    # Lägg på en transaktion
    tx = Transaction(
        account_id=a.id, date=date(2026, 1, 5), amount=Decimal("500"),
        currency="SEK", raw_description="test", hash="x1",
    )
    session.add(tx); session.flush()
    assert _balance_for(session, a.id) == Decimal("1500")


def test_create_uses_default_description(session):
    src = _acc(session, "Lön", "checking", opening=1000, opening_date=date(2026, 1, 1))
    dst = _acc(session, "Sparmål Buffert", "savings", opening=0, opening_date=date(2026, 1, 1))

    payload = CreateTransferIn(
        from_account_id=src.id, to_account_id=dst.id, amount=Decimal("100"),
    )
    result = create_transfer(payload, session)
    src_tx = session.get(Transaction, result["source_tx_id"])
    assert src_tx.raw_description == "Överföring till Sparmål Buffert"


def test_create_uses_today_when_no_date(session):
    src = _acc(session, "Lön", "checking", opening=1000, opening_date=date(2026, 1, 1))
    dst = _acc(session, "Spar", "savings", opening=0, opening_date=date(2026, 1, 1))

    payload = CreateTransferIn(
        from_account_id=src.id, to_account_id=dst.id, amount=Decimal("100"),
    )
    result = create_transfer(payload, session)
    assert result["date"] == date.today().isoformat()


def test_create_rejects_zero_or_negative_amount():
    """Pydantic-validering — amount=Field(gt=0) ska fånga detta innan
    funktionen anropas."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CreateTransferIn(from_account_id=1, to_account_id=2, amount=Decimal("0"))
    with pytest.raises(ValidationError):
        CreateTransferIn(from_account_id=1, to_account_id=2, amount=Decimal("-5"))
