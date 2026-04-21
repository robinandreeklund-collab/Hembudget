"""Test av chat/tools.py — verktygsimplementationerna som LLM:en anropar.

Vi testar mot minnes-SQLite med riktiga models, utan LM Studio.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.chat import tools
from hembudget.db.models import (
    Account,
    Base,
    Budget,
    Category,
    Goal,
    Loan,
    LoanPayment,
    LoanScheduleEntry,
    Rule,
    Scenario,
    TaxEvent,
    Transaction,
    TransactionSplit,
    UpcomingTransaction,
    UpcomingTransactionLine,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _cat(s, name):
    c = Category(name=name)
    s.add(c)
    s.flush()
    return c


def _acc(s, name, type_="checking", owner_id=None, ob=None, ob_date=None):
    a = Account(
        name=name, bank="nordea", type=type_, owner_id=owner_id,
        opening_balance=ob, opening_balance_date=ob_date,
    )
    s.add(a)
    s.flush()
    return a


def _tx(s, acc_id, d, amount, desc="x", cat_id=None, is_transfer=False):
    t = Transaction(
        account_id=acc_id, date=d, amount=Decimal(str(amount)),
        currency="SEK", raw_description=desc,
        hash=f"{acc_id}-{d}-{amount}-{desc}",
        category_id=cat_id, is_transfer=is_transfer,
    )
    s.add(t)
    s.flush()
    return t


# ---------- get_accounts / balances ----------

def test_get_accounts_sums_opening_plus_transactions(session):
    acc = _acc(session, "Lön", ob=Decimal("1000"), ob_date=date(2026, 1, 1))
    _tx(session, acc.id, date(2026, 2, 5), 500)
    _tx(session, acc.id, date(2026, 2, 10), -200)

    out = tools.get_accounts(session, as_of="2026-03-01")
    assert len(out["accounts"]) == 1
    a = out["accounts"][0]
    assert a["name"] == "Lön"
    assert a["current_balance"] == 1300.0
    assert out["total_balance"] == 1300.0


def test_get_account_balance_excludes_after_as_of(session):
    acc = _acc(session, "Lön")
    _tx(session, acc.id, date(2026, 1, 10), 1000)
    _tx(session, acc.id, date(2026, 2, 10), 500)
    out = tools.get_account_balance(session, acc.id, as_of="2026-01-31")
    assert out["balance"] == 1000.0


def test_get_account_balance_unknown_account(session):
    out = tools.get_account_balance(session, 999)
    assert "error" in out


def test_get_balance_history_has_month_points(session):
    acc = _acc(session, "Lön")
    _tx(session, acc.id, date(2026, 1, 15), 1000)
    out = tools.get_balance_history(session, months=3)
    assert len(out["series"]) == 1
    assert len(out["series"][0]["points"]) == 3


# ---------- get_upcoming ----------

def test_get_upcoming_filters_by_kind_and_unmatched(session):
    acc = _acc(session, "Gem")
    u1 = UpcomingTransaction(
        kind="bill", name="Vattenfall", amount=Decimal("1000"),
        expected_date=date(2026, 5, 1), debit_account_id=acc.id,
    )
    u2 = UpcomingTransaction(
        kind="income", name="Lön", amount=Decimal("30000"),
        expected_date=date(2026, 5, 25), debit_account_id=acc.id,
    )
    u3 = UpcomingTransaction(
        kind="bill", name="Matchad", amount=Decimal("500"),
        expected_date=date(2026, 4, 1), debit_account_id=acc.id,
        matched_transaction_id=None,
    )
    session.add_all([u1, u2, u3])
    session.flush()

    # Mark u3 as matched
    tx = _tx(session, acc.id, date(2026, 4, 1), -500)
    u3.matched_transaction_id = tx.id
    session.flush()

    bills = tools.get_upcoming(session, kind="bill", only_unmatched=True)
    names = [i["name"] for i in bills["items"]]
    assert "Vattenfall" in names
    assert "Matchad" not in names
    assert "Lön" not in names


def test_get_upcoming_includes_lines(session):
    el = _cat(session, "El")
    acc = _acc(session, "Gem")
    u = UpcomingTransaction(
        kind="bill", name="Hjo Energi", amount=Decimal("1500"),
        expected_date=date(2026, 5, 1), debit_account_id=acc.id,
    )
    u.lines.append(UpcomingTransactionLine(
        description="Elnät", amount=Decimal("700"), category_id=el.id, sort_order=0,
    ))
    session.add(u)
    session.flush()

    out = tools.get_upcoming(session)
    item = next(i for i in out["items"] if i["name"] == "Hjo Energi")
    assert len(item["lines"]) == 1
    assert item["lines"][0]["category"] == "El"


# ---------- get_loans / schedule ----------

def test_get_loans_computes_balance_and_amortization(session):
    loan = Loan(
        name="Bolån", lender="Nordea", principal_amount=Decimal("2000000"),
        start_date=date(2020, 1, 1), interest_rate=0.042, binding_type="rörlig",
        property_value=Decimal("4000000"),
    )
    session.add(loan)
    session.flush()
    # Lägg till en amortering
    acc = _acc(session, "Lön")
    tx = _tx(session, acc.id, date(2026, 1, 25), -5000, "Amortering Nordea")
    session.add(LoanPayment(
        loan_id=loan.id, transaction_id=tx.id, date=tx.date,
        amount=Decimal("5000"), payment_type="amortization",
    ))
    session.flush()

    out = tools.get_loans(session)
    assert len(out["loans"]) == 1
    l = out["loans"][0]
    assert l["principal_amount"] == 2000000.0
    assert l["outstanding_balance"] == 1995000.0
    assert l["amortization_paid"] == 5000.0
    assert l["payments_count"] == 1
    assert l["ltv"] is not None


def test_get_loan_schedule_filters_future_only(session):
    loan = Loan(
        name="L", lender="X", principal_amount=Decimal("100"),
        start_date=date(2020, 1, 1), interest_rate=0.04,
    )
    session.add(loan)
    session.flush()
    past = LoanScheduleEntry(
        loan_id=loan.id, due_date=date(2020, 6, 1),
        amount=Decimal("10"), payment_type="interest",
    )
    future = LoanScheduleEntry(
        loan_id=loan.id, due_date=date.today() + timedelta(days=30),
        amount=Decimal("10"), payment_type="interest",
    )
    session.add_all([past, future])
    session.flush()

    out = tools.get_loan_schedule(session, loan.id, months=12)
    assert len(out["schedule"]) == 1
    assert out["schedule"][0]["type"] == "interest"


# ---------- goals / scenarios / tax / categories / rules ----------

def test_get_goals_progress_ratio(session):
    g = Goal(
        name="Resa", target_amount=Decimal("20000"),
        current_amount=Decimal("5000"),
    )
    session.add(g)
    session.flush()
    out = tools.get_goals(session)
    assert out["goals"][0]["progress_ratio"] == 0.25


def test_get_scenarios_returns_all(session):
    session.add(Scenario(
        name="Flytt Stockholm", kind="move",
        params={"old_rent": 8000, "new_rent": 12000},
        result={"break_even_months": 24},
    ))
    session.flush()
    out = tools.get_scenarios(session)
    assert out["scenarios"][0]["kind"] == "move"


def test_get_tax_events_filters_by_year_and_aggregates(session):
    session.add_all([
        TaxEvent(type="isk_deposit", amount=Decimal("1000"), date=date(2026, 3, 1)),
        TaxEvent(type="isk_deposit", amount=Decimal("2000"), date=date(2026, 5, 1)),
        TaxEvent(type="rot", amount=Decimal("5000"), date=date(2026, 7, 1)),
        TaxEvent(type="isk_deposit", amount=Decimal("999"), date=date(2025, 12, 1)),
    ])
    session.flush()
    out = tools.get_tax_events(session, year=2026)
    assert len(out["events"]) == 3
    assert out["totals_by_type"]["isk_deposit"] == 3000.0
    assert out["totals_by_type"]["rot"] == 5000.0


def test_get_categories_lists_budget(session):
    c = Category(name="Mat", budget_monthly=Decimal("6000"))
    session.add(c)
    session.flush()
    out = tools.get_categories(session)
    names = {c["name"]: c for c in out["categories"]}
    assert names["Mat"]["budget_monthly"] == 6000.0


def test_get_rules_filters_by_category(session):
    mat = _cat(session, "Mat")
    spot = _cat(session, "Prenumerationer")
    session.add_all([
        Rule(pattern="ica", category_id=mat.id, priority=100),
        Rule(pattern="spotify", category_id=spot.id, priority=100),
    ])
    session.flush()
    out = tools.get_rules(session, category="Mat")
    assert len(out["rules"]) == 1
    assert out["rules"][0]["pattern"] == "ica"


# ---------- budget-history / compare / anomaly / family ----------

def test_get_budget_history_spans_months(session):
    mat = _cat(session, "Mat")
    acc = _acc(session, "X")
    _tx(session, acc.id, date(2026, 1, 10), -500, cat_id=mat.id)
    _tx(session, acc.id, date(2026, 2, 10), -700, cat_id=mat.id)
    out = tools.get_budget_history(session, "2026-01", "2026-03")
    months = [m["month"] for m in out["months"]]
    assert months == ["2026-01", "2026-02", "2026-03"]
    assert out["months"][0]["expenses"] == 500.0
    assert out["months"][1]["expenses"] == 700.0


def test_compare_months_highlights_category_diffs(session):
    mat = _cat(session, "Mat")
    rest = _cat(session, "Restaurang")
    acc = _acc(session, "X")
    _tx(session, acc.id, date(2026, 1, 10), -1000, cat_id=mat.id)
    _tx(session, acc.id, date(2026, 1, 15), -500, cat_id=rest.id)
    _tx(session, acc.id, date(2026, 2, 10), -1200, cat_id=mat.id)
    _tx(session, acc.id, date(2026, 2, 15), -2000, cat_id=rest.id)

    out = tools.compare_months(session, "2026-01", "2026-02")
    diffs = {r["category"]: r["diff"] for r in out["by_category"]}
    # Restaurang ökade mest i absolut tal
    assert out["by_category"][0]["category"] == "Restaurang"
    assert diffs["Restaurang"] == -1500.0  # mer negativt i månad B


def test_detect_anomalies_flags_large_spike(session):
    mat = _cat(session, "Mat")
    acc = _acc(session, "X")
    # Baseline med lite variation så stdev inte blir 0
    baseline = [450, 520, 480, 510, 490, 530]
    for m, val in enumerate(baseline, start=1):
        _tx(session, acc.id, date(2025, m, 10), -val, cat_id=mat.id, desc=f"m{m}")
    # Toppar i juli — 3000 kr (många gånger större än baseline)
    _tx(session, acc.id, date(2025, 7, 10), -3000, cat_id=mat.id, desc="spike")
    out = tools.detect_anomalies(session, "2025-07")
    names = [a["category"] for a in out["anomalies"]]
    assert "Mat" in names
    anomaly = next(a for a in out["anomalies"] if a["category"] == "Mat")
    assert anomaly["direction"] == "higher"


def test_detect_anomalies_needs_history(session):
    """Kategori med bara en historisk månad → ingen anomali."""
    mat = _cat(session, "Mat")
    acc = _acc(session, "X")
    _tx(session, acc.id, date(2026, 3, 10), -500, cat_id=mat.id)
    out = tools.detect_anomalies(session, "2026-03")
    assert out["anomalies"] == []


def test_get_family_breakdown_splits_by_owner(session):
    mat = _cat(session, "Mat")
    robin = _acc(session, "Robin", owner_id=1)
    partner = _acc(session, "Partner", owner_id=2)
    gem = _acc(session, "Gemensamt")
    _tx(session, robin.id, date(2026, 4, 10), 30000)  # Robins lön
    _tx(session, partner.id, date(2026, 4, 25), 28000)  # Partners lön
    _tx(session, robin.id, date(2026, 4, 12), -500, cat_id=mat.id)
    _tx(session, gem.id, date(2026, 4, 12), -2000)

    out = tools.get_family_breakdown(session, "2026-04")
    assert "user_1" in out["by_owner"]
    assert "user_2" in out["by_owner"]
    assert "gemensamt" in out["by_owner"]
    assert out["by_owner"]["user_1"]["income"] == 30000.0
    assert out["by_owner"]["user_1"]["expenses"] == 500.0


# ---------- top_categories med splits ----------

def test_top_categories_honors_splits(session):
    el = _cat(session, "El")
    va = _cat(session, "VA")
    misc = _cat(session, "Övrigt")
    acc = _acc(session, "Gem")

    # En transaktion med splits (utgift 1500 fördelat 1000/500)
    tx = Transaction(
        account_id=acc.id, date=date(2026, 4, 30),
        amount=Decimal("-1500"), currency="SEK",
        raw_description="Hjo Energi", hash="h-split",
        category_id=misc.id,  # fallback-kategori
    )
    session.add(tx)
    session.flush()
    session.add_all([
        TransactionSplit(
            transaction_id=tx.id, description="El",
            amount=Decimal("-1000"), category_id=el.id, sort_order=0,
        ),
        TransactionSplit(
            transaction_id=tx.id, description="VA",
            amount=Decimal("-500"), category_id=va.id, sort_order=1,
        ),
    ])
    session.flush()

    out = tools.top_categories(session, "2026-04-01", "2026-04-30")
    cats = {r["category"]: r["total"] for r in out["top"]}
    # Övrigt ska inte dyka upp (har splits)
    assert "Övrigt" not in cats
    assert cats["El"] == -1000.0
    assert cats["VA"] == -500.0


def test_query_transactions_returns_splits(session):
    el = _cat(session, "El")
    acc = _acc(session, "Gem")
    tx = _tx(session, acc.id, date(2026, 4, 30), -1000, "Hjo Energi")
    tx.normalized_merchant = "HJO ENERGI"
    session.add(TransactionSplit(
        transaction_id=tx.id, description="El",
        amount=Decimal("-1000"), category_id=el.id, sort_order=0,
    ))
    session.flush()

    out = tools.query_transactions(session, merchant="HJO")
    assert len(out["transactions"]) == 1
    assert len(out["transactions"][0]["splits"]) == 1
    assert out["transactions"][0]["splits"][0]["category"] == "El"
