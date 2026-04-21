"""Test av fakturauppdelningar (invoice line splitting).

När en UpcomingTransaction har rader (t.ex. en faktura från Hjo Energi med
el + vatten + bredband) ska dessa kopieras till TransactionSplit när
fakturan matchas mot en riktig bankrad. Budget-sammanfattningen ska sedan
fördela beloppet på rätt kategorier.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.budget.monthly import MonthlyBudgetService
from hembudget.db.models import (
    Account,
    Base,
    Budget,
    Category,
    Transaction,
    TransactionSplit,
    UpcomingTransaction,
    UpcomingTransactionLine,
)
from hembudget.splits import (
    apply_upcoming_lines_to_transaction,
    build_lines_from_vision,
    resolve_category_id,
)
from hembudget.upcoming_match import UpcomingMatcher


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _cat(session, name):
    c = Category(name=name)
    session.add(c)
    session.flush()
    return c


def _acc(session, name="Gemensamt"):
    a = Account(name=name, bank="nordea", type="checking")
    session.add(a)
    session.flush()
    return a


def _tx(session, account_id, d, amount, desc="X"):
    t = Transaction(
        account_id=account_id,
        date=d,
        amount=Decimal(str(amount)),
        currency="SEK",
        raw_description=desc,
        hash=f"{account_id}-{d}-{amount}-{desc}",
    )
    session.add(t)
    session.flush()
    return t


def test_resolve_category_id_case_insensitive(session):
    c = _cat(session, "Elektricitet")
    assert resolve_category_id(session, "elektricitet") == c.id
    assert resolve_category_id(session, "ELEKTRICITET") == c.id
    assert resolve_category_id(session, "  Elektricitet  ") == c.id
    assert resolve_category_id(session, "okänd") is None
    assert resolve_category_id(session, None) is None
    assert resolve_category_id(session, "") is None


def test_build_lines_from_vision_resolves_categories(session):
    el = _cat(session, "El")
    va = _cat(session, "Vatten och avlopp")
    _cat(session, "Bredband")

    lines = build_lines_from_vision(
        session,
        [
            {"description": "Elnät", "amount": 612.50, "category": "El"},
            {"description": "Elförbrukning", "amount": 421.00, "category": "el"},
            {"description": "VA", "amount": 380, "category": "Vatten och avlopp"},
            {"description": "Bredband 100/100", "amount": 399, "category": "Bredband"},
            {"description": "Okänd", "amount": 50, "category": "Finns inte"},
        ],
    )
    assert len(lines) == 5
    assert lines[0].category_id == el.id
    assert lines[1].category_id == el.id
    assert lines[2].category_id == va.id
    assert lines[4].category_id is None


def test_build_lines_skips_empty_and_nonpositive(session):
    lines = build_lines_from_vision(
        session,
        [
            {"description": "", "amount": 100},
            {"description": "Negativ", "amount": -50},
            {"description": "Noll", "amount": 0},
            {"description": "OK", "amount": 100},
        ],
    )
    assert len(lines) == 1
    assert lines[0].description == "OK"


def test_apply_lines_splits_with_correct_sign_for_bill(session):
    el = _cat(session, "El")
    va = _cat(session, "VA")
    bb = _cat(session, "Bredband")
    acc = _acc(session)

    up = UpcomingTransaction(
        kind="bill",
        name="Hjo Energi",
        amount=Decimal("1500"),
        expected_date=date(2026, 4, 30),
        debit_account_id=acc.id,
    )
    up.lines.extend([
        UpcomingTransactionLine(description="Elnät", amount=Decimal("700"), category_id=el.id, sort_order=0),
        UpcomingTransactionLine(description="VA", amount=Decimal("400"), category_id=va.id, sort_order=1),
        UpcomingTransactionLine(description="Bredband", amount=Decimal("400"), category_id=bb.id, sort_order=2),
    ])
    session.add(up)
    session.flush()

    # Riktig bankrad: -1500 på debet-kontot
    tx = _tx(session, acc.id, date(2026, 4, 30), -1500, "Autogiro Hjo Energi")

    splits = apply_upcoming_lines_to_transaction(session, up, tx)
    assert len(splits) == 3
    # Utgift → splits ska vara negativa
    assert all(s.amount < 0 for s in splits)
    # Summan ska stämma mot bankraden
    assert sum(s.amount for s in splits) == Decimal("-1500.00")
    # Kategorierna bevarade
    assert {s.category_id for s in splits} == {el.id, va.id, bb.id}


def test_apply_lines_adjusts_residual_within_tolerance(session):
    el = _cat(session, "El")
    acc = _acc(session)
    up = UpcomingTransaction(
        kind="bill",
        name="Hjo Energi",
        amount=Decimal("1000"),
        expected_date=date(2026, 4, 30),
        debit_account_id=acc.id,
    )
    # Raderna summerar till 999.50 — 0.50 kr avrundning
    up.lines.extend([
        UpcomingTransactionLine(description="A", amount=Decimal("499.75"), sort_order=0, category_id=el.id),
        UpcomingTransactionLine(description="B", amount=Decimal("499.75"), sort_order=1, category_id=el.id),
    ])
    session.add(up)
    session.flush()

    tx = _tx(session, acc.id, date(2026, 4, 30), -1000, "Autogiro")
    splits = apply_upcoming_lines_to_transaction(session, up, tx)
    # Sista raden absorberar residualen
    assert sum(s.amount for s in splits) == Decimal("-1000.00")


def test_apply_lines_is_idempotent(session):
    el = _cat(session, "El")
    acc = _acc(session)
    up = UpcomingTransaction(
        kind="bill",
        name="Hjo Energi",
        amount=Decimal("500"),
        expected_date=date(2026, 4, 30),
        debit_account_id=acc.id,
    )
    up.lines.append(
        UpcomingTransactionLine(description="El", amount=Decimal("500"), category_id=el.id, sort_order=0)
    )
    session.add(up)
    session.flush()
    tx = _tx(session, acc.id, date(2026, 4, 30), -500)

    first = apply_upcoming_lines_to_transaction(session, up, tx)
    second = apply_upcoming_lines_to_transaction(session, up, tx)
    assert len(first) == 1
    assert len(second) == 0  # Redan applicerat, skippar
    total_splits = session.query(TransactionSplit).filter(
        TransactionSplit.transaction_id == tx.id
    ).count()
    assert total_splits == 1


def test_upcoming_matcher_copies_lines_to_splits(session):
    """End-to-end: vision skapar upcoming m. lines, bankimport kör matcher,
    splits ska finnas på bankraden efteråt."""
    el = _cat(session, "El")
    va = _cat(session, "VA")
    bb = _cat(session, "Bredband")
    acc = _acc(session)

    up = UpcomingTransaction(
        kind="bill",
        name="Hjo Energi",
        amount=Decimal("1500"),
        expected_date=date(2026, 4, 30),
        debit_account_id=acc.id,
        source="vision_ai",
    )
    up.lines.extend([
        UpcomingTransactionLine(description="El", amount=Decimal("700"), category_id=el.id, sort_order=0),
        UpcomingTransactionLine(description="VA", amount=Decimal("400"), category_id=va.id, sort_order=1),
        UpcomingTransactionLine(description="Bredband", amount=Decimal("400"), category_id=bb.id, sort_order=2),
    ])
    session.add(up)
    session.flush()

    tx = _tx(session, acc.id, date(2026, 4, 30), -1500, "Autogiro Hjo Energi")
    matched = UpcomingMatcher(session).match([tx])
    assert matched == 1

    session.refresh(up)
    assert up.matched_transaction_id == tx.id

    splits = session.query(TransactionSplit).filter(
        TransactionSplit.transaction_id == tx.id
    ).all()
    assert len(splits) == 3
    assert sum(s.amount for s in splits) == Decimal("-1500.00")
    assert {s.category_id for s in splits} == {el.id, va.id, bb.id}


def test_upcoming_without_lines_creates_no_splits(session):
    """Vanliga fakturor utan rader ska inte få splits — inget byte av beteende."""
    acc = _acc(session)
    up = UpcomingTransaction(
        kind="bill",
        name="Spotify",
        amount=Decimal("139"),
        expected_date=date(2026, 4, 15),
        debit_account_id=acc.id,
    )
    session.add(up)
    session.flush()

    tx = _tx(session, acc.id, date(2026, 4, 15), -139, "Spotify")
    UpcomingMatcher(session).match([tx])

    splits = session.query(TransactionSplit).filter(
        TransactionSplit.transaction_id == tx.id
    ).all()
    assert splits == []


def test_budget_summary_uses_splits_over_tx_category(session):
    """När en transaktion har splits ska budgetrapporten fördela över splits
    i stället för att lägga hela beloppet på transactions.category_id."""
    el = _cat(session, "El")
    va = _cat(session, "VA")
    bb = _cat(session, "Bredband")
    misc = _cat(session, "Övrigt")
    acc = _acc(session)

    # Transaktion med category_id = Övrigt (som fallback), men splits finns
    tx = Transaction(
        account_id=acc.id,
        date=date(2026, 4, 30),
        amount=Decimal("-1500"),
        currency="SEK",
        raw_description="Autogiro Hjo Energi",
        hash="h1",
        category_id=misc.id,
    )
    session.add(tx)
    session.flush()
    for desc, amt, cid in [("El", -700, el.id), ("VA", -400, va.id), ("Bredband", -400, bb.id)]:
        session.add(TransactionSplit(
            transaction_id=tx.id,
            description=desc,
            amount=Decimal(str(amt)),
            category_id=cid,
            sort_order=0,
        ))
    session.flush()

    summary = MonthlyBudgetService(session).summary("2026-04")
    by_cat = {line.category: line.actual for line in summary.lines}

    # Övrigt (fallback-kategorin) ska INTE ha fått någonting
    assert by_cat.get("Övrigt", Decimal("0")) == Decimal("0")
    # Splits har fördelats
    assert by_cat["El"] == Decimal("-700")
    assert by_cat["VA"] == Decimal("-400")
    assert by_cat["Bredband"] == Decimal("-400")
    # Utgifterna summerar till 1500
    assert summary.expenses == Decimal("1500")


def test_budget_summary_falls_back_to_tx_category_when_no_splits(session):
    """Regression: transaktioner utan splits ska fortfarande räknas på
    transactions.category_id (gamla beteendet)."""
    groceries = _cat(session, "Mat")
    acc = _acc(session)
    tx = Transaction(
        account_id=acc.id,
        date=date(2026, 4, 10),
        amount=Decimal("-450"),
        currency="SEK",
        raw_description="ICA Maxi",
        hash="h-ica",
        category_id=groceries.id,
    )
    session.add(tx)
    session.flush()

    summary = MonthlyBudgetService(session).summary("2026-04")
    by_cat = {line.category: line.actual for line in summary.lines}
    assert by_cat["Mat"] == Decimal("-450")
    assert summary.expenses == Decimal("450")


def test_budget_summary_mixes_splits_and_regular(session):
    """Både splittrade och regulära transaktioner samma månad → båda räknas."""
    el = _cat(session, "El")
    mat = _cat(session, "Mat")
    acc = _acc(session)

    # Splittrad
    tx1 = Transaction(
        account_id=acc.id, date=date(2026, 4, 30),
        amount=Decimal("-1000"), currency="SEK",
        raw_description="Energi", hash="h1",
    )
    session.add(tx1); session.flush()
    session.add(TransactionSplit(
        transaction_id=tx1.id, description="El", amount=Decimal("-1000"),
        category_id=el.id, sort_order=0,
    ))

    # Regulär
    tx2 = Transaction(
        account_id=acc.id, date=date(2026, 4, 15),
        amount=Decimal("-300"), currency="SEK",
        raw_description="ICA", hash="h2", category_id=mat.id,
    )
    session.add(tx2); session.flush()

    summary = MonthlyBudgetService(session).summary("2026-04")
    by_cat = {line.category: line.actual for line in summary.lines}
    assert by_cat["El"] == Decimal("-1000")
    assert by_cat["Mat"] == Decimal("-300")
    assert summary.expenses == Decimal("1300")


def test_income_lines_get_positive_sign(session):
    """Inkomst-UpcomingTransaction med lines → splits ska vara POSITIVA
    (det här är mindre vanligt men vi måste stödja det)."""
    lon = _cat(session, "Lön")
    bonus = _cat(session, "Bonus")
    acc = _acc(session)
    up = UpcomingTransaction(
        kind="income",
        name="Inkab",
        amount=Decimal("30000"),
        expected_date=date(2026, 4, 25),
        debit_account_id=acc.id,
    )
    up.lines.extend([
        UpcomingTransactionLine(description="Grundlön", amount=Decimal("25000"), category_id=lon.id, sort_order=0),
        UpcomingTransactionLine(description="Bonus", amount=Decimal("5000"), category_id=bonus.id, sort_order=1),
    ])
    session.add(up); session.flush()

    tx = _tx(session, acc.id, date(2026, 4, 25), 30000, "Lön Inkab")
    UpcomingMatcher(session).match([tx])

    splits = session.query(TransactionSplit).filter(
        TransactionSplit.transaction_id == tx.id
    ).all()
    assert all(s.amount > 0 for s in splits)
    assert sum(s.amount for s in splits) == Decimal("30000.00")


def test_delete_transaction_cascades_splits(session):
    el = _cat(session, "El")
    acc = _acc(session)
    tx = _tx(session, acc.id, date(2026, 4, 30), -500)
    session.add(TransactionSplit(
        transaction_id=tx.id, description="El",
        amount=Decimal("-500"), category_id=el.id, sort_order=0,
    ))
    session.flush()

    # FOREIGN KEYS är ON i cipher-mode men OFF by default i memory-SQLite;
    # slå på explicit så ON DELETE CASCADE faktiskt aktiveras.
    session.execute(
        __import__("sqlalchemy").text("PRAGMA foreign_keys = ON")
    )
    session.delete(tx)
    session.flush()

    remaining = session.query(TransactionSplit).count()
    assert remaining == 0


def test_delete_upcoming_cascades_lines(session):
    el = _cat(session, "El")
    acc = _acc(session)
    up = UpcomingTransaction(
        kind="bill", name="X", amount=Decimal("500"),
        expected_date=date(2026, 4, 30), debit_account_id=acc.id,
    )
    up.lines.append(UpcomingTransactionLine(
        description="El", amount=Decimal("500"), category_id=el.id, sort_order=0,
    ))
    session.add(up); session.flush()

    session.delete(up)
    session.flush()
    remaining = session.query(UpcomingTransactionLine).count()
    assert remaining == 0
