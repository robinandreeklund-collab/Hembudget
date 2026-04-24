"""Test av auto-budget: fyll i planerade belopp från historiskt snitt."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.budget.monthly import MonthlyBudgetService, _shift_months
from hembudget.db.models import (
    Account,
    Base,
    Budget,
    Category,
    Transaction,
    TransactionSplit,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _cat(s, name):
    c = Category(name=name)
    s.add(c); s.flush()
    return c


def _acc(s, name="X"):
    a = Account(name=name, bank="nordea", type="checking")
    s.add(a); s.flush()
    return a


def _tx(s, acc_id, d, amount, cat_id, desc="x"):
    t = Transaction(
        account_id=acc_id, date=d, amount=Decimal(str(amount)),
        currency="SEK", raw_description=desc,
        hash=f"{acc_id}-{d}-{amount}-{desc}",
        category_id=cat_id,
    )
    s.add(t); s.flush()
    return t


def test_shift_months_handles_year_boundary():
    assert _shift_months(date(2026, 1, 15), -3) == date(2025, 10, 15)
    assert _shift_months(date(2026, 1, 15), 12) == date(2027, 1, 15)
    # 31 mars → 30 april (ingen 31 april)
    assert _shift_months(date(2026, 3, 31), 1) == date(2026, 4, 30)


def test_auto_budget_uses_median_of_last_n_months(session):
    mat = _cat(session, "Mat")
    acc = _acc(session)
    # 4 månader historik — utgifter: 500, 800, 1000, 1200. Median = 900.
    amounts = [500, 800, 1000, 1200]
    for i, amt in enumerate(amounts, start=1):
        _tx(session, acc.id, date(2025, i, 10), -amt, cat_id=mat.id, desc=f"m{i}")

    svc = MonthlyBudgetService(session)
    out = svc.auto_budget("2025-05", lookback_months=4)
    assert len(out) == 1
    assert out[0].category_id == mat.id
    assert out[0].planned_amount == Decimal("-900.00")


def test_auto_budget_skips_categories_with_existing_budget(session):
    mat = _cat(session, "Mat")
    rest = _cat(session, "Restaurang")
    acc = _acc(session)
    _tx(session, acc.id, date(2025, 1, 10), -1000, cat_id=mat.id)
    _tx(session, acc.id, date(2025, 2, 10), -1000, cat_id=mat.id)
    _tx(session, acc.id, date(2025, 1, 15), -500, cat_id=rest.id)
    _tx(session, acc.id, date(2025, 2, 15), -500, cat_id=rest.id)

    # Sätt manuell budget för Mat i målmånaden
    session.add(Budget(month="2025-03", category_id=mat.id, planned_amount=Decimal("-2000")))
    session.flush()

    out = MonthlyBudgetService(session).auto_budget("2025-03", lookback_months=3)
    # Bara Restaurang ska uppdateras — Mat lämnas ifred
    assert len(out) == 1
    assert out[0].category_id == rest.id

    existing_mat = session.query(Budget).filter(
        Budget.month == "2025-03", Budget.category_id == mat.id
    ).first()
    assert existing_mat.planned_amount == Decimal("-2000")


def test_auto_budget_overwrite_replaces_existing(session):
    mat = _cat(session, "Mat")
    acc = _acc(session)
    _tx(session, acc.id, date(2025, 1, 10), -1500, cat_id=mat.id)
    _tx(session, acc.id, date(2025, 2, 10), -1500, cat_id=mat.id)

    session.add(Budget(month="2025-03", category_id=mat.id, planned_amount=Decimal("-999")))
    session.flush()

    out = MonthlyBudgetService(session).auto_budget("2025-03", lookback_months=3, overwrite=True)
    assert len(out) == 1
    assert out[0].planned_amount == Decimal("-1500.00")


def test_auto_budget_filters_tiny_activity(session):
    """Kategorier med median < 50 kr hoppas över — det är oftast engångshändelser."""
    mat = _cat(session, "Mat")
    petty = _cat(session, "Småposter")
    acc = _acc(session)
    _tx(session, acc.id, date(2025, 1, 10), -1000, cat_id=mat.id)
    _tx(session, acc.id, date(2025, 2, 10), -1000, cat_id=mat.id)
    _tx(session, acc.id, date(2025, 1, 15), -10, cat_id=petty.id)
    _tx(session, acc.id, date(2025, 2, 15), -20, cat_id=petty.id)

    out = MonthlyBudgetService(session).auto_budget("2025-03", lookback_months=3)
    cat_ids = {b.category_id for b in out}
    assert mat.id in cat_ids
    assert petty.id not in cat_ids


def test_auto_budget_counts_splits(session):
    """Transaktioner med splits ska räknas per-split, inte på tx.category_id."""
    el = _cat(session, "El")
    misc = _cat(session, "Övrigt")
    acc = _acc(session)

    # En faktura som splittrats: 1000 el, 500 VA. tx.category = Övrigt.
    for m in [1, 2]:
        tx = Transaction(
            account_id=acc.id, date=date(2025, m, 10),
            amount=Decimal("-1500"), currency="SEK",
            raw_description="Energi", hash=f"h-{m}",
            category_id=misc.id,
        )
        session.add(tx); session.flush()
        session.add(TransactionSplit(
            transaction_id=tx.id, description="El", amount=Decimal("-1000"),
            category_id=el.id, sort_order=0,
        ))
    session.flush()

    out = MonthlyBudgetService(session).auto_budget("2025-03", lookback_months=3)
    cat_ids = {b.category_id: b.planned_amount for b in out}
    assert el.id in cat_ids
    assert cat_ids[el.id] == Decimal("-1000.00")
    # Övrigt borde INTE ha fått en budget (hela beloppet splittades bort)
    assert misc.id not in cat_ids


def test_auto_budget_includes_income(session):
    lon = _cat(session, "Lön")
    acc = _acc(session)
    for m in [1, 2, 3]:
        _tx(session, acc.id, date(2025, m, 25), 30000, cat_id=lon.id, desc=f"m{m}")

    out = MonthlyBudgetService(session).auto_budget("2025-04", lookback_months=3)
    cat_ids = {b.category_id: b.planned_amount for b in out}
    assert lon.id in cat_ids
    assert cat_ids[lon.id] == Decimal("30000.00")


def test_auto_budget_empty_history_no_op(session):
    _cat(session, "Mat")
    out = MonthlyBudgetService(session).auto_budget("2025-05", lookback_months=6)
    assert out == []
