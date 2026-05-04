"""Regression: ÖVERFÖRING SPARKONTO på lönekontoutdraget MÅSTE para mot
en motsvarande +rad på Sparkonto, annars försvinner pengarna ur
budget/balans/dashboard.

Bakgrund (2026-04-26): scenario.py skapade '-2000 ÖVERFÖRING SPARKONTO'
som en envelopps-event, batch.py importerade kontoutdraget och
landade -2000 på Lönekonto utan motsvarande +2000 någonstans. När
elev tittade i Saldo per konto saknades 2000 kr.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def session():
    from hembudget.db.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = S()
    try:
        yield s
    finally:
        s.close()


def _make_parsed(transactions):
    """Bygg ett minimalt EkonomilabbetParseResult."""
    from hembudget.parsers.base import RawTransaction
    from hembudget.parsers.ekonomilabbet import EkonomilabbetParseResult
    parsed_txs = [
        RawTransaction(
            date=d, description=desc, amount=Decimal(str(amt)),
            row_index=i,
        )
        for i, (d, desc, amt) in enumerate(transactions)
    ]
    return EkonomilabbetParseResult(
        kind="kontoutdrag",
        title="Kontoutdrag 2026-04",
        period="2026-04",
        account_no="1234 56 78901",
        transactions=parsed_txs,
        total_amount=None,
    )


def test_savings_transfer_creates_paired_sparkonto_tx(session):
    from hembudget.db.models import Account, Transaction
    from hembudget.teacher.batch import _import_kontoutdrag

    parsed = _make_parsed([
        (date(2026, 4, 25), "LÖN ELAJO", 24200),
        (date(2026, 4, 30), "ÖVERFÖRING SPARKONTO", -2000),
    ])
    stats = {
        "imported_tx": 0, "skipped_tx": 0, "accounts_touched": [],
    }
    _import_kontoutdrag(session, parsed, stats)
    session.commit()

    # Lönekonto har 2 rader: +24200 (lön) + -2000 (sparöverföring)
    lon = session.query(Account).filter(Account.name == "Lönekonto").one()
    lon_txs = (
        session.query(Transaction)
        .filter(Transaction.account_id == lon.id)
        .order_by(Transaction.date)
        .all()
    )
    assert len(lon_txs) == 2

    # Sparkonto har en +2000-rad parad mot lönekontots -2000
    sp = session.query(Account).filter(Account.name == "Sparkonto").one()
    sp_txs = (
        session.query(Transaction)
        .filter(Transaction.account_id == sp.id)
        .all()
    )
    assert len(sp_txs) == 1
    assert sp_txs[0].amount == Decimal("2000")
    assert sp_txs[0].is_transfer is True

    # Båda har transfer_pair_id som pekar på varandra
    src = next(t for t in lon_txs if t.amount < 0)
    pair = sp_txs[0]
    assert src.transfer_pair_id == pair.id
    assert pair.transfer_pair_id == src.id
    assert src.is_transfer is True


def test_savings_transfer_idempotent_on_re_import(session):
    """Om eleven importerar samma kontoutdrag igen ska INTE en ny
    Sparkonto-rad skapas (idempotent)."""
    from hembudget.db.models import Account, Transaction
    from hembudget.teacher.batch import _import_kontoutdrag

    parsed = _make_parsed([
        (date(2026, 4, 30), "ÖVERFÖRING SPARKONTO", -3000),
    ])
    for _ in range(3):
        stats = {
            "imported_tx": 0, "skipped_tx": 0, "accounts_touched": [],
        }
        _import_kontoutdrag(session, parsed, stats)
        session.commit()

    sp = session.query(Account).filter(Account.name == "Sparkonto").one()
    sp_count = (
        session.query(Transaction)
        .filter(Transaction.account_id == sp.id)
        .count()
    )
    assert sp_count == 1


def test_default_accounts_created_on_kontoutdrag_import(session):
    """Sparkonto + Kreditkort skapas automatiskt vid första import,
    med opening_balance från DEFAULT_ACCOUNTS."""
    from hembudget.db.models import Account
    from hembudget.teacher.batch import _import_kontoutdrag

    parsed = _make_parsed([
        (date(2026, 4, 25), "LÖN", 20000),
    ])
    stats = {
        "imported_tx": 0, "skipped_tx": 0, "accounts_touched": [],
    }
    _import_kontoutdrag(session, parsed, stats)
    session.commit()

    accs = {a.name: a for a in session.query(Account).all()}
    assert "Lönekonto" in accs
    assert "Sparkonto" in accs
    assert "Kreditkort" in accs
    assert accs["Lönekonto"].opening_balance == Decimal("25000")
    assert accs["Sparkonto"].opening_balance == Decimal("5000")
    assert accs["Kreditkort"].opening_balance == Decimal("0")
