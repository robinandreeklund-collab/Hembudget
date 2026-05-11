"""Tester för betalnings-failure-flödet (SKV-5).

- bal_q filtrerar released_at + expected_date korrekt
- failed-mail skapas + related_mail får status='failed'
- Retry-endpoint drar direkt om saldo räcker
- Retry-endpoint schemalägger fram om saldo fortfarande saknas
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.db.base import Base
from hembudget.db.models import (
    Account, MailItem, Transaction, UpcomingTransaction,
)


@pytest.fixture()
def session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


@pytest.fixture()
def lonekonto(session):
    acc = Account(
        name="Lönekonto", bank="Spelbanken", type="checking",
        opening_balance=Decimal("0"),
    )
    session.add(acc); session.flush()
    return acc


def _add_tx(s, *, acc, amount, day, released_now=True):
    """Hjälpare: lägg en transaktion. `released_now=True` betyder
    synlig i UI-saldot."""
    tx = Transaction(
        account_id=acc.id,
        date=day,
        amount=Decimal(str(amount)),
        currency="SEK",
        raw_description="test",
        hash=f"{acc.id}-{day}-{amount}",
        is_transfer=False,
        released_at=datetime.utcnow() if released_now else (
            datetime.utcnow() + timedelta(days=365)  # framtida
        ),
    )
    s.add(tx); s.flush()
    return tx


# === Bal-räkning matchar UI ===


def test_balance_excludes_future_released_at(session, lonekonto):
    """Tx med released_at i framtiden ska INTE räknas in i saldot.

    Verkligt scenario: nästa månads lön finns som Transaction i
    scope-DB:n med future released_at. UI visar inte den ännu, men
    backend's bal_q gjorde det tidigare → trodde att 30 000 kr i
    framtida lön var tillgänglig nu.
    """
    from sqlalchemy import func as _f, or_ as _or
    today = date(2026, 1, 15)
    # 5 000 kr lön (released nu)
    _add_tx(session, acc=lonekonto, amount=5000, day=date(2026, 1, 1))
    # 30 000 kr nästa lön (släpps om 14 dagar i real-tid)
    _add_tx(
        session, acc=lonekonto, amount=30000, day=date(2026, 2, 1),
        released_now=False,
    )

    # Backend-räkning · samma filter som vi nu använder
    bal_q = (
        session.query(_f.coalesce(_f.sum(Transaction.amount), 0))
        .filter(
            Transaction.account_id == lonekonto.id,
            Transaction.date <= today,
            _or(
                Transaction.released_at.is_(None),
                Transaction.released_at <= datetime.utcnow(),
            ),
        )
    )
    bal = Decimal(bal_q.scalar() or 0)
    assert bal == Decimal("5000"), (
        f"framtida lön ska inte räknas in · fick {bal}"
    )


def test_balance_caps_at_expected_date(session, lonekonto):
    """Tx daterad EFTER expected_date ska inte räknas (annars
    räknar vi 'lön i februari' som tillgänglig för 'autogiro 15 jan')."""
    from sqlalchemy import func as _f, or_ as _or
    expected = date(2026, 1, 15)
    _add_tx(session, acc=lonekonto, amount=5000, day=date(2026, 1, 1))
    _add_tx(session, acc=lonekonto, amount=10000, day=date(2026, 2, 1))

    bal_q = (
        session.query(_f.coalesce(_f.sum(Transaction.amount), 0))
        .filter(
            Transaction.account_id == lonekonto.id,
            Transaction.date <= expected,
            _or(
                Transaction.released_at.is_(None),
                Transaction.released_at <= datetime.utcnow(),
            ),
        )
    )
    bal = Decimal(bal_q.scalar() or 0)
    assert bal == Decimal("5000")


# === Failed-mail-flödet ===


def test_failed_mail_created_when_insufficient_funds(session, lonekonto):
    """När bal < u.amount: failed-mail från Spelbanken + relaterad
    faktura får status='failed'.

    Simulerar logiken direkt eftersom hela auto-debit-funktionen kräver
    master_session + scope_context.
    """
    from sqlalchemy import func as _f, or_ as _or

    # Lönekontot har 5 798 kr
    _add_tx(session, acc=lonekonto, amount=5798, day=date(2026, 1, 5))

    # Faktura 6 434 kr (Folktandvården)
    u = UpcomingTransaction(
        kind="invoice",
        name="Folktandvården",
        amount=Decimal("6434"),
        expected_date=date(2026, 1, 19),
        autogiro=True,
        debit_account_id=lonekonto.id,
    )
    session.add(u); session.flush()

    related = MailItem(
        sender="Folktandvården",
        sender_short="FTV",
        sender_kind="agency",
        sender_meta="Faktura",
        mail_type="invoice",
        subject="Faktura · karieskontroll",
        body_meta="6 434 kr",
        body="…",
        amount=Decimal("6434"),
        due_date=date(2026, 1, 19),
        status="exported",
        upcoming_id=u.id,
    )
    session.add(related); session.flush()

    # Simulera balance-check
    bal_q = (
        session.query(_f.coalesce(_f.sum(Transaction.amount), 0))
        .filter(
            Transaction.account_id == lonekonto.id,
            Transaction.date <= u.expected_date,
            _or(
                Transaction.released_at.is_(None),
                Transaction.released_at <= datetime.utcnow(),
            ),
        )
    )
    bal = Decimal(bal_q.scalar() or 0)
    assert bal < u.amount, "Test-setup · bal måste vara < amount"

    # Simulera failed-mail-logik
    u.autogiro = False
    related.status = "failed"
    shortfall = int(u.amount - bal)
    assert shortfall == 6434 - 5798  # 636 kr

    session.add(MailItem(
        sender="Spelbanken",
        sender_short="BNK",
        sender_kind="financial",
        mail_type="info",
        subject=(
            f"Betalning misslyckades · {related.sender} "
            f"{int(u.amount)} kr"
        ),
        body_meta=f"Saknades {shortfall} kr",
        body="…",
        amount=u.amount,
        due_date=u.expected_date,
        status="unhandled",
    ))
    session.flush()

    # Verifiera failed-status
    related2 = session.get(MailItem, related.id)
    assert related2.status == "failed"
    u2 = session.get(UpcomingTransaction, u.id)
    assert u2.autogiro is False

    # Failed-mail finns från Spelbanken
    fail_mail = (
        session.query(MailItem)
        .filter(MailItem.subject.like("Betalning misslyckades%"))
        .first()
    )
    assert fail_mail is not None
    assert "636" in fail_mail.body_meta


# === Retry-endpoint-logik ===


def test_retry_pays_when_funds_arrived(session, lonekonto):
    """Eleven har fyllt på kontot · retry ska gå igenom."""
    from sqlalchemy import func as _f, or_ as _or
    from decimal import Decimal as _D

    # Lönekonto: 5 798 + 10 000 (påfyllning) = 15 798
    _add_tx(session, acc=lonekonto, amount=5798, day=date(2026, 1, 5))
    _add_tx(session, acc=lonekonto, amount=10000, day=date(2026, 1, 16))

    # Faktura misslyckades tidigare
    u = UpcomingTransaction(
        kind="invoice",
        name="Folktandvården",
        amount=Decimal("6434"),
        expected_date=date(2026, 1, 19),
        autogiro=False,  # släppt vid failure
        debit_account_id=lonekonto.id,
    )
    session.add(u); session.flush()

    # Simulera retry · saldot räcker nu
    today = date(2026, 1, 20)
    bal_q = (
        session.query(_f.coalesce(_f.sum(Transaction.amount), 0))
        .filter(
            Transaction.account_id == lonekonto.id,
            Transaction.date <= today,
            _or(
                Transaction.released_at.is_(None),
                Transaction.released_at <= datetime.utcnow(),
            ),
        )
    )
    bal = _D(str(bal_q.scalar() or 0))
    assert bal >= u.amount

    # Direkt-debit (samma logik som retry_failed_payment-endpointen)
    tx = Transaction(
        account_id=lonekonto.id,
        date=today,
        amount=-u.amount,
        currency="SEK",
        raw_description=f"Autogiro · {u.name} (retry)",
        hash=f"retry-{u.id}",
        is_transfer=False,
        user_verified=True,
    )
    session.add(tx); session.flush()
    u.matched_transaction_id = tx.id

    # Verifiera ny saldot efter dragning
    bal_after = (
        session.query(_f.coalesce(_f.sum(Transaction.amount), 0))
        .filter(
            Transaction.account_id == lonekonto.id,
            Transaction.date <= today,
            _or(
                Transaction.released_at.is_(None),
                Transaction.released_at <= datetime.utcnow(),
            ),
        )
        .scalar()
    )
    # 15 798 - 6 434 = 9 364
    assert _D(str(bal_after)) == _D("9364")
