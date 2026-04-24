"""Tool-implementationer för chat-agenten.

Varje funktion är deterministisk, anropar DB direkt och returnerar
JSON-serialiserbara dicts. Ingen LLM-logik här — den ligger i agent.py.

Tools som ändrar data (t.ex. create_rule, update_budget) ska INTE
ligga här utan kräva bekräftelse via en separat 'actions'-modul i
framtida versioner.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..budget.forecast import CashflowForecaster
from ..budget.monthly import MonthlyBudgetService
from ..db.models import (
    Account,
    Budget,
    Category,
    Goal,
    Loan,
    LoanPayment,
    LoanScheduleEntry,
    Rule,
    Scenario,
    Subscription,
    TaxEvent,
    Transaction,
    TransactionSplit,
    UpcomingTransaction,
    User,
)
from ..loans.matcher import LoanMatcher
from ..scenarios.engine import ScenarioEngine
from ..subscriptions.detector import SubscriptionDetector

log = logging.getLogger(__name__)


def _d(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _month_bounds(month: str) -> tuple[date, date]:
    year, mon = map(int, month.split("-"))
    start = date(year, mon, 1)
    if mon == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, mon + 1, 1)
    return start, end


# ============================================================================
# Befintliga verktyg (samma beteende, flyttade hit från agent.py)
# ============================================================================

def get_month_summary(session: Session, month: str) -> dict:
    s = MonthlyBudgetService(session).summary(month)
    return {
        "month": s.month,
        "income": _d(s.income),
        "expenses": _d(s.expenses),
        "savings": _d(s.savings),
        "savings_rate": s.savings_rate,
        "lines": [
            {
                "category": l.category,
                "planned": _d(l.planned),
                "actual": _d(l.actual),
                "diff": _d(l.diff),
            }
            for l in s.lines
        ],
    }


def query_transactions(session: Session, **kw) -> dict:
    q = session.query(Transaction)
    if not kw.get("include_transfers"):
        q = q.filter(Transaction.is_transfer.is_(False))
    if kw.get("category"):
        q = q.join(Category, Category.id == Transaction.category_id).filter(
            Category.name == kw["category"]
        )
    if kw.get("merchant"):
        q = q.filter(
            Transaction.normalized_merchant.ilike(f"%{kw['merchant'].upper()}%")
        )
    if kw.get("from_date"):
        q = q.filter(Transaction.date >= _parse_date(kw["from_date"]))
    if kw.get("to_date"):
        q = q.filter(Transaction.date <= _parse_date(kw["to_date"]))
    if kw.get("min_amount") is not None:
        q = q.filter(Transaction.amount >= Decimal(str(kw["min_amount"])))
    if kw.get("max_amount") is not None:
        q = q.filter(Transaction.amount <= Decimal(str(kw["max_amount"])))
    if kw.get("account_id") is not None:
        q = q.filter(Transaction.account_id == int(kw["account_id"]))
    rows = (
        q.order_by(Transaction.date.desc())
        .limit(int(kw.get("limit", 50)))
        .all()
    )
    return {
        "transactions": [
            {
                "id": t.id,
                "date": t.date.isoformat(),
                "amount": _d(t.amount),
                "description": t.raw_description,
                "merchant": t.normalized_merchant,
                "category": t.category.name if t.category else None,
                "account_id": t.account_id,
                "is_transfer": t.is_transfer,
                "splits": [
                    {
                        "description": s.description,
                        "amount": _d(s.amount),
                        "category": s.category.name if s.category else None,
                    }
                    for s in t.splits
                ],
            }
            for t in rows
        ]
    }


def top_categories(
    session: Session, from_date: str, to_date: str, limit: int = 10
) -> dict:
    """Topp N utgiftskategorier över ett intervall.

    Honorerar transaction_splits: en transaktion med splits räknas per-
    split i stället för på transactions.category_id, så fakturauppdelning
    (el/vatten/bredband) syns som separata rader.
    """
    fd = _parse_date(from_date)
    td = _parse_date(to_date)

    # Transaktioner UTAN splits (undvik scalar-subquery → stabilare i sqlcipher3)
    split_tx_ids: set[int] = {
        row[0]
        for row in session.execute(
            select(TransactionSplit.transaction_id).distinct()
        ).all()
    }
    plain_q = (
        select(
            Category.name,
            func.sum(Transaction.amount).label("total"),
        )
        .join(Category, Category.id == Transaction.category_id, isouter=True)
        .where(
            Transaction.date >= fd,
            Transaction.date <= td,
            Transaction.amount < 0,
            Transaction.is_transfer.is_(False),
        )
        .group_by(Category.name)
    )
    if split_tx_ids:
        plain_q = plain_q.where(Transaction.id.not_in(split_tx_ids))
    plain = session.execute(plain_q).all()

    # Transaktioner MED splits
    split_rows = session.execute(
        select(
            Category.name,
            func.sum(TransactionSplit.amount).label("total"),
        )
        .join(Category, Category.id == TransactionSplit.category_id, isouter=True)
        .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
        .where(
            Transaction.date >= fd,
            Transaction.date <= td,
            TransactionSplit.amount < 0,
            Transaction.is_transfer.is_(False),
        )
        .group_by(Category.name)
    ).all()

    combined: dict[str, float] = {}
    for name, total in list(plain) + list(split_rows):
        key = name or "Okategoriserat"
        combined[key] = combined.get(key, 0.0) + _d(total)

    ranked = sorted(combined.items(), key=lambda kv: kv[1])[:limit]
    return {"top": [{"category": n, "total": v} for n, v in ranked]}


def find_subscriptions(session: Session) -> dict:
    subs = session.query(Subscription).filter(Subscription.active.is_(True)).all()
    if not subs:
        subs_live = SubscriptionDetector(session).detect()
        return {
            "subscriptions": [
                {
                    "merchant": s.merchant,
                    "amount": _d(s.amount),
                    "interval_days": s.interval_days,
                    "next_expected_date": _iso(s.next_expected_date),
                }
                for s in subs_live
            ]
        }
    return {
        "subscriptions": [
            {
                "merchant": s.merchant,
                "amount": _d(s.amount),
                "interval_days": s.interval_days,
                "next_expected_date": _iso(s.next_expected_date),
            }
            for s in subs
        ]
    }


def forecast_cashflow(session: Session, months: int = 6) -> dict:
    f = CashflowForecaster(session).project(horizon_months=months)
    return {
        "forecast": [
            {
                "month": m.month,
                "income": _d(m.projected_income),
                "expenses": _d(m.projected_expenses),
                "net": _d(m.projected_net),
            }
            for m in f
        ]
    }


def calculate_scenario(session: Session, kind: str, params: dict) -> dict:
    return ScenarioEngine().run(kind, params)


# ============================================================================
# Nya verktyg — full täckning av databasen
# ============================================================================

def get_accounts(session: Session, as_of: str | None = None) -> dict:
    """Lista alla konton med nuvarande saldo och typ."""
    target = _parse_date(as_of) or date.today()
    accounts = session.query(Account).order_by(Account.id).all()
    out = []
    total = Decimal("0")
    for acc in accounts:
        ob = acc.opening_balance or Decimal("0")
        q = session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.account_id == acc.id,
            Transaction.date <= target,
        )
        if acc.opening_balance_date is not None:
            q = q.filter(Transaction.date > acc.opening_balance_date)
        movement = Decimal(str(q.scalar() or 0))
        current = ob + movement
        total += current
        out.append(
            {
                "id": acc.id,
                "name": acc.name,
                "bank": acc.bank,
                "type": acc.type,
                "currency": acc.currency,
                "account_number": acc.account_number,
                "current_balance": _d(current),
                "owner_id": acc.owner_id,
            }
        )
    return {
        "as_of": target.isoformat(),
        "accounts": out,
        "total_balance": _d(total),
    }


def get_account_balance(
    session: Session, account_id: int, as_of: str | None = None
) -> dict:
    """Saldo för ett specifikt konto vid en viss tidpunkt."""
    target = _parse_date(as_of) or date.today()
    acc = session.get(Account, account_id)
    if acc is None:
        return {"error": f"account {account_id} not found"}
    ob = acc.opening_balance or Decimal("0")
    q = session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.account_id == acc.id,
        Transaction.date <= target,
    )
    if acc.opening_balance_date is not None:
        q = q.filter(Transaction.date > acc.opening_balance_date)
    movement = Decimal(str(q.scalar() or 0))
    return {
        "account_id": acc.id,
        "name": acc.name,
        "as_of": target.isoformat(),
        "opening_balance": _d(ob),
        "movement": _d(movement),
        "balance": _d(ob + movement),
    }


def get_balance_history(
    session: Session, account_id: int | None = None, months: int = 6
) -> dict:
    """Månadsvisa slutsaldon för ett eller alla konton."""
    today = date.today().replace(day=1)
    points: list[date] = []
    cur = today
    for _ in range(months):
        points.append(cur - timedelta(days=1))  # sista dagen föregående månad
        cur = (cur - timedelta(days=1)).replace(day=1)
    points = sorted(points)

    accounts = (
        [session.get(Account, account_id)]
        if account_id
        else session.query(Account).order_by(Account.id).all()
    )
    if account_id and accounts[0] is None:
        return {"error": f"account {account_id} not found"}

    series = []
    for acc in accounts:
        acc_points = []
        for p in points:
            ob = acc.opening_balance or Decimal("0")
            q = session.query(
                func.coalesce(func.sum(Transaction.amount), 0)
            ).filter(
                Transaction.account_id == acc.id,
                Transaction.date <= p,
            )
            if acc.opening_balance_date is not None:
                q = q.filter(Transaction.date > acc.opening_balance_date)
            movement = Decimal(str(q.scalar() or 0))
            acc_points.append(
                {"date": p.isoformat(), "balance": _d(ob + movement)}
            )
        series.append(
            {"account_id": acc.id, "name": acc.name, "points": acc_points}
        )
    return {"series": series}


def get_upcoming(
    session: Session,
    kind: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    only_unmatched: bool = True,
    owner: str | None = None,
) -> dict:
    """Lista planerade fakturor och löner."""
    q = session.query(UpcomingTransaction)
    if kind:
        q = q.filter(UpcomingTransaction.kind == kind)
    fd = _parse_date(from_date)
    td = _parse_date(to_date)
    if fd:
        q = q.filter(UpcomingTransaction.expected_date >= fd)
    if td:
        q = q.filter(UpcomingTransaction.expected_date <= td)
    if only_unmatched:
        q = q.filter(UpcomingTransaction.matched_transaction_id.is_(None))
    if owner:
        q = q.filter(UpcomingTransaction.owner == owner)
    rows = q.order_by(UpcomingTransaction.expected_date.asc()).all()
    return {
        "items": [
            {
                "id": u.id,
                "kind": u.kind,
                "name": u.name,
                "amount": _d(u.amount),
                "expected_date": _iso(u.expected_date),
                "owner": u.owner,
                "autogiro": u.autogiro,
                "matched": u.matched_transaction_id is not None,
                "lines": [
                    {
                        "description": line.description,
                        "amount": _d(line.amount),
                        "category": line.category.name if line.category else None,
                    }
                    for line in u.lines
                ],
            }
            for u in rows
        ]
    }


def get_loans(session: Session, active_only: bool = True) -> dict:
    """Lista alla lån med sammanfattning (saldo, ränta, LTV)."""
    q = session.query(Loan)
    if active_only:
        q = q.filter(Loan.active.is_(True))
    loans = q.order_by(Loan.id).all()
    matcher = LoanMatcher(session)
    out = []
    for loan in loans:
        balance = matcher.outstanding_balance(loan)
        interest_paid = matcher.total_interest_paid(loan)
        amortized = loan.principal_amount - balance
        count = (
            session.query(LoanPayment)
            .filter(LoanPayment.loan_id == loan.id)
            .count()
        )
        ltv = None
        if loan.property_value and loan.property_value > 0:
            ltv = _d(balance / loan.property_value)
        out.append(
            {
                "id": loan.id,
                "name": loan.name,
                "lender": loan.lender,
                "loan_number": loan.loan_number,
                "principal_amount": _d(loan.principal_amount),
                "outstanding_balance": _d(balance),
                "amortization_paid": _d(amortized),
                "interest_paid": _d(interest_paid),
                "interest_rate": loan.interest_rate,
                "binding_type": loan.binding_type,
                "binding_end_date": _iso(loan.binding_end_date),
                "ltv": ltv,
                "payments_count": count,
            }
        )
    return {"loans": out}


def get_loan_schedule(
    session: Session, loan_id: int | None = None, months: int = 12
) -> dict:
    """Kommande lånebetalningar för ett eller alla lån."""
    today = date.today()
    horizon = today + timedelta(days=31 * months)
    q = (
        session.query(LoanScheduleEntry)
        .filter(
            LoanScheduleEntry.due_date >= today,
            LoanScheduleEntry.due_date <= horizon,
        )
    )
    if loan_id:
        q = q.filter(LoanScheduleEntry.loan_id == loan_id)
    rows = q.order_by(LoanScheduleEntry.due_date.asc()).all()
    return {
        "schedule": [
            {
                "id": e.id,
                "loan_id": e.loan_id,
                "due_date": _iso(e.due_date),
                "amount": _d(e.amount),
                "type": e.payment_type,
                "matched": e.matched_transaction_id is not None,
            }
            for e in rows
        ]
    }


def get_goals(session: Session) -> dict:
    """Sparmål med progress."""
    rows = session.query(Goal).order_by(Goal.id).all()
    return {
        "goals": [
            {
                "id": g.id,
                "name": g.name,
                "target_amount": _d(g.target_amount),
                "current_amount": _d(g.current_amount),
                "progress_ratio": _d(
                    g.current_amount / g.target_amount
                )
                if g.target_amount and g.target_amount > 0
                else 0.0,
                "target_date": _iso(g.target_date),
                "account_id": g.account_id,
            }
            for g in rows
        ]
    }


def get_scenarios(session: Session) -> dict:
    rows = session.query(Scenario).order_by(Scenario.created_at.desc()).all()
    return {
        "scenarios": [
            {
                "id": s.id,
                "name": s.name,
                "kind": s.kind,
                "params": s.params,
                "result": s.result,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in rows
        ]
    }


def get_tax_events(
    session: Session, year: int | None = None, type: str | None = None
) -> dict:
    q = session.query(TaxEvent)
    if year:
        start = date(year, 1, 1)
        end = date(year + 1, 1, 1)
        q = q.filter(TaxEvent.date >= start, TaxEvent.date < end)
    if type:
        q = q.filter(TaxEvent.type == type)
    rows = q.order_by(TaxEvent.date.asc()).all()
    totals: dict[str, float] = {}
    for e in rows:
        totals[e.type] = totals.get(e.type, 0.0) + _d(e.amount)
    return {
        "events": [
            {
                "id": e.id,
                "type": e.type,
                "amount": _d(e.amount),
                "date": _iso(e.date),
                "transaction_id": e.transaction_id,
                "meta": e.meta,
            }
            for e in rows
        ],
        "totals_by_type": totals,
    }


def get_categories(session: Session) -> dict:
    rows = session.query(Category).order_by(Category.name).all()
    return {
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "parent_id": c.parent_id,
                "budget_monthly": _d(c.budget_monthly)
                if c.budget_monthly is not None
                else None,
                "icon": c.icon,
            }
            for c in rows
        ]
    }


def get_rules(session: Session, category: str | None = None) -> dict:
    q = session.query(Rule).join(Category, Category.id == Rule.category_id)
    if category:
        q = q.filter(Category.name.ilike(f"%{category}%"))
    rows = q.order_by(Rule.priority.desc()).all()
    return {
        "rules": [
            {
                "id": r.id,
                "pattern": r.pattern,
                "is_regex": r.is_regex,
                "category": session.get(Category, r.category_id).name
                if r.category_id
                else None,
                "priority": r.priority,
                "source": r.source,
            }
            for r in rows
        ]
    }


def get_budget_history(
    session: Session, from_month: str, to_month: str
) -> dict:
    """Budget + utfall över ett flertal månader för trendanalys."""
    from_start, _ = _month_bounds(from_month)
    _, to_end = _month_bounds(to_month)
    months: list[str] = []
    y, m = map(int, from_month.split("-"))
    target_y, target_m = map(int, to_month.split("-"))
    while (y, m) <= (target_y, target_m):
        months.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1

    service = MonthlyBudgetService(session)
    out = []
    for month in months:
        s = service.summary(month)
        out.append(
            {
                "month": s.month,
                "income": _d(s.income),
                "expenses": _d(s.expenses),
                "savings": _d(s.savings),
                "savings_rate": s.savings_rate,
            }
        )
    return {"months": out}


def compare_months(session: Session, month_a: str, month_b: str) -> dict:
    """Jämför två månader: inkomst, utgifter, sparande och per-kategori-diff."""
    service = MonthlyBudgetService(session)
    a = service.summary(month_a)
    b = service.summary(month_b)

    def _cat_dict(summary):
        return {line.category: _d(line.actual) for line in summary.lines}

    a_cats = _cat_dict(a)
    b_cats = _cat_dict(b)
    all_cats = set(a_cats) | set(b_cats)
    diffs = []
    for c in all_cats:
        va = a_cats.get(c, 0.0)
        vb = b_cats.get(c, 0.0)
        diffs.append(
            {
                "category": c,
                "a": va,
                "b": vb,
                "diff": vb - va,
            }
        )
    diffs.sort(key=lambda r: abs(r["diff"]), reverse=True)
    return {
        "a": {
            "month": a.month,
            "income": _d(a.income),
            "expenses": _d(a.expenses),
            "savings": _d(a.savings),
        },
        "b": {
            "month": b.month,
            "income": _d(b.income),
            "expenses": _d(b.expenses),
            "savings": _d(b.savings),
        },
        "delta": {
            "income": _d(b.income - a.income),
            "expenses": _d(b.expenses - a.expenses),
            "savings": _d(b.savings - a.savings),
        },
        "by_category": diffs,
    }


def detect_anomalies(
    session: Session, month: str, threshold_sigma: float = 2.0
) -> dict:
    """Jämför månadens utgifter per kategori mot snittet för de senaste
    6 månaderna. Anomali = avvikelse > threshold_sigma * stdev."""
    start, end = _month_bounds(month)
    lookback_start = start - timedelta(days=186)

    rows = session.execute(
        select(
            func.strftime("%Y-%m", Transaction.date).label("m"),
            Category.name,
            func.sum(Transaction.amount).label("total"),
        )
        .join(Category, Category.id == Transaction.category_id, isouter=True)
        .where(
            Transaction.date >= lookback_start,
            Transaction.date < end,
            Transaction.amount < 0,
            Transaction.is_transfer.is_(False),
        )
        .group_by("m", Category.name)
    ).all()

    by_cat: dict[str, dict[str, float]] = {}
    for m, cat, total in rows:
        key = cat or "Okategoriserat"
        by_cat.setdefault(key, {})[m] = abs(_d(total))

    anomalies = []
    current_month = month
    for cat, series in by_cat.items():
        current = series.get(current_month, 0.0)
        past = [v for m, v in series.items() if m != current_month]
        if len(past) < 2:
            continue
        mean = statistics.mean(past)
        stdev = statistics.stdev(past) if len(past) >= 2 else 0.0
        if stdev == 0:
            continue
        z = (current - mean) / stdev
        if abs(z) >= threshold_sigma:
            anomalies.append(
                {
                    "category": cat,
                    "current": current,
                    "average": round(mean, 2),
                    "stdev": round(stdev, 2),
                    "z_score": round(z, 2),
                    "direction": "higher" if z > 0 else "lower",
                }
            )
    anomalies.sort(key=lambda r: abs(r["z_score"]), reverse=True)
    return {"month": month, "anomalies": anomalies}


def get_elpris(
    session: Session,  # oanvänd men krävs av dispatch-signaturen
    day: str = "today",
    zone: str = "SE3",
) -> dict:
    """Hämta svenska spotelpriser per timme. day = 'today' | 'tomorrow' | YYYY-MM-DD."""
    from datetime import timedelta
    from ..elpris import ElprisClient, VALID_ZONES

    if zone not in VALID_ZONES:
        return {"error": f"zone must be one of {VALID_ZONES}"}

    if day == "today":
        target = date.today()
    elif day == "tomorrow":
        target = date.today() + timedelta(days=1)
    else:
        try:
            target = date.fromisoformat(day)
        except ValueError:
            return {"error": "day must be 'today', 'tomorrow' or YYYY-MM-DD"}

    # Återanvänd singleton-klienten i api/elpris.py så cachen delas
    from ..api import elpris as elpris_api
    try:
        prices = elpris_api.get_client().get(target, zone)
    except Exception as exc:
        return {"error": f"kunde inte hämta priser: {exc}"}

    return {
        "date": prices.date.isoformat(),
        "zone": prices.zone,
        "average_sek_per_kwh_inc_vat": prices.avg_inc_vat,
        "cheapest_hours": [
            {
                "start": h.time_start.isoformat(),
                "sek_per_kwh_inc_vat": round(h.sek_inc_vat, 4),
            }
            for h in prices.cheapest_hours(3)
        ],
        "most_expensive_hour": (
            {
                "start": prices.max_hour.time_start.isoformat(),
                "sek_per_kwh_inc_vat": round(prices.max_hour.sek_inc_vat, 4),
            }
            if prices.max_hour
            else None
        ),
        "hours_count": len(prices.hours),
    }


def subscription_health(session: Session, stale_days: int = 60) -> dict:
    """Hälsokoll för aktiva prenumerationer: hitta de som inte dragits
    senaste `stale_days` dagarna (användaren kanske glömt säga upp).

    Returnerar per prenumeration:
    - merchant, amount, interval_days
    - last_seen: datum för senaste transaktion som matchar merchant
    - days_since: dagar sedan senaste dragning (null om aldrig sett)
    - is_stale: True om days_since > stale_days
    - annual_cost: amount × (365 / interval_days)
    """
    from datetime import datetime
    today = date.today()
    subs = session.query(Subscription).filter(Subscription.active.is_(True)).all()
    out = []
    stale_total = 0.0
    for s in subs:
        last_tx = (
            session.query(Transaction)
            .filter(
                Transaction.normalized_merchant == s.merchant,
                Transaction.amount < 0,
                Transaction.is_transfer.is_(False),
            )
            .order_by(Transaction.date.desc())
            .first()
        )
        last_seen = last_tx.date if last_tx else None
        days_since = (today - last_seen).days if last_seen else None
        is_stale = days_since is not None and days_since > stale_days
        interval = max(s.interval_days, 1)
        annual = _d(s.amount) * (365.0 / interval)
        if is_stale:
            stale_total += abs(annual)
        out.append(
            {
                "id": s.id,
                "merchant": s.merchant,
                "amount": _d(s.amount),
                "interval_days": s.interval_days,
                "last_seen": _iso(last_seen),
                "days_since": days_since,
                "is_stale": is_stale,
                "annual_cost": round(abs(annual), 2),
            }
        )
    # Sortera så inaktiva (stale) kommer först, sen efter kostnad
    out.sort(key=lambda r: (not r["is_stale"], -r["annual_cost"]))
    return {
        "stale_days": stale_days,
        "subscriptions": out,
        "stale_annual_cost": round(stale_total, 2),
        "total_annual_cost": round(
            sum(r["annual_cost"] for r in out), 2
        ),
    }


def _resolve_owner_bucket_key(
    owner_string: str | None,
    user_name_to_id: dict[str, int],
    fallback_account_owner_id: int | None = None,
) -> str:
    """Mappa upcoming.owner (fritext, t.ex. 'Evelina') till en stabil
    bucket-nyckel för family/ytd-aggregering.

    Format-konsistens:
      - None / tom + ingen fallback → 'gemensamt'
      - None / tom + fallback_account_owner_id → 'user_{fallback_id}'
        (typiskt: en kommande lön på Evelinas konto utan owner-fält
         ifyllt → använd kontots owner_id istället för 'gemensamt')
      - matchar en User.name (case-insensitive) → 'user_{id}'
      - annars → raw string (t.ex. 'Evelina' om användaren inte finns
        i User-tabellen än — frontend visar namnet som det är)
    """
    if not owner_string or not owner_string.strip():
        if fallback_account_owner_id is not None:
            return f"user_{fallback_account_owner_id}"
        return "gemensamt"
    key = owner_string.strip()
    for name, uid in user_name_to_id.items():
        if name.lower() == key.lower():
            return f"user_{uid}"
    return key


def ytd_income_by_person(
    session: Session,
    year: int | None = None,
    category_name: str = "Lön",
) -> dict:
    """Totala inkomster (ofta lön) per kontoägare för innevarande eller
    angivet år.

    Källor:
    1. Transaction-rader kategoriserade som `category_name` (typ 'Lön'),
       grupperade på Account.owner_id.
    2. Manuellt inlagda UpcomingTransaction-rader (kind='income') med
       expected_date inom året — användaren kan dokumentera en partners
       lön utan att importera hens kontoutdrag. Endast omatchade
       upcomings räknas (om de är matchade finns motsvarande Transaction
       redan och räknas via källa 1).

    Fallback: om inga träffar på kategorin Lön i Transaction-tabellen,
    returnera alla positiva non-transfer transaktioner."""
    y = year or date.today().year
    start = date(y, 1, 1)
    end = date(y + 1, 1, 1)

    cat = session.query(Category).filter(Category.name == category_name).first()

    # Försök först med specifik kategori
    rows = []
    if cat is not None:
        rows = session.execute(
            select(
                Account.owner_id,
                Account.name.label("account_name"),
                func.sum(Transaction.amount).label("total"),
                func.count(Transaction.id).label("count"),
            )
            .join(Transaction, Transaction.account_id == Account.id)
            .where(
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.amount > 0,
                Transaction.is_transfer.is_(False),
                Transaction.category_id == cat.id,
            )
            .group_by(Account.owner_id, Account.name)
        ).all()

    # Om tomt → fallback: alla positiva non-transfer
    fallback_used = False
    if not rows:
        fallback_used = True
        rows = session.execute(
            select(
                Account.owner_id,
                Account.name.label("account_name"),
                func.sum(Transaction.amount).label("total"),
                func.count(Transaction.id).label("count"),
            )
            .join(Transaction, Transaction.account_id == Account.id)
            .where(
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.amount > 0,
                Transaction.is_transfer.is_(False),
            )
            .group_by(Account.owner_id, Account.name)
        ).all()

    by_owner: dict[str, dict] = {}
    total_from_transactions = 0.0
    for owner_id, account_name, total, count in rows:
        key = f"user_{owner_id}" if owner_id else "gemensamt"
        bucket = by_owner.setdefault(
            key,
            {"total": 0.0, "count": 0, "accounts": [],
             "from_transactions": 0.0, "from_manual": 0.0},
        )
        t = _d(total)
        bucket["total"] += t
        bucket["count"] += int(count or 0)
        bucket["from_transactions"] += t
        bucket["accounts"].append(
            {"name": account_name, "amount": t, "source": "tx"}
        )
        total_from_transactions += t

    # Källa 2: manuellt inlagda upcoming incomes — kompletterar när
    # partnerns kontoutdrag inte är importerat än.
    user_name_to_id = {u.name: u.id for u in session.query(User).all()}
    manual_incomes = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "income",
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
            UpcomingTransaction.matched_transaction_id.is_(None),
        )
        .all()
    )
    total_from_manual = 0.0
    # Cacha account-owner-id:s så vi kan falla tillbaka när upcoming.owner
    # är tomt — typiskt för en kommande lön som lagts till på partnerns
    # konto utan att owner-fältet fyllts i.
    account_owner_by_id = {
        a.id: a.owner_id for a in session.query(Account).all()
    }
    for up in manual_incomes:
        fallback_owner = (
            account_owner_by_id.get(up.debit_account_id)
            if up.debit_account_id else None
        )
        key = _resolve_owner_bucket_key(
            up.owner, user_name_to_id, fallback_owner,
        )
        bucket = by_owner.setdefault(
            key,
            {"total": 0.0, "count": 0, "accounts": [],
             "from_transactions": 0.0, "from_manual": 0.0},
        )
        a = _d(up.amount)
        bucket["total"] += a
        bucket["count"] += 1
        bucket["from_manual"] += a
        bucket["accounts"].append(
            {"name": f"{up.name} (manuellt)", "amount": a, "source": "manual"}
        )
        total_from_manual += a

    grand_total = sum(b["total"] for b in by_owner.values())
    return {
        "year": y,
        "category": category_name,
        "category_matched": not fallback_used,
        "by_owner": by_owner,
        "grand_total": round(grand_total, 2),
        # Uppdelning per källa så UI kan visa "från kontoutdrag" vs
        # "manuellt tillagda" och hjälpa användaren upptäcka dubletter
        # eller felkategoriseringar.
        "total_from_transactions": round(total_from_transactions, 2),
        "total_from_manual": round(total_from_manual, 2),
    }


def get_family_breakdown(session: Session, month: str) -> dict:
    """Fördela månadens utgifter/inkomster per kontoägare (owner_id) och
    kontotyp. Används för familjeekonomi: 'vem betalade vad'.

    Inkluderar både faktiska Transaction-rader OCH omatchade
    UpcomingTransaction-rader (kind=income/bill) inom månaden — så
    partner-löner som dokumenterats manuellt (utan CSV) också räknas."""
    start, end = _month_bounds(month)

    # Summera inkomster och utgifter SEPARAT, grupperat per ägare och konto.
    base_q = (
        select(
            Account.owner_id,
            Account.id.label("account_id"),
            Account.name.label("account_name"),
            Account.type.label("account_type"),
            func.sum(Transaction.amount).label("total"),
        )
        .join(Transaction, Transaction.account_id == Account.id)
        .where(
            Transaction.date >= start,
            Transaction.date < end,
            Transaction.is_transfer.is_(False),
        )
        .group_by(Account.owner_id, Account.id, Account.name, Account.type)
    )
    positives = session.execute(
        base_q.where(Transaction.amount > 0)
    ).all()
    # Inkognito-konton: exkludera privata utgifter (vi spårar dem inte).
    # Inkomster räknas dock fortfarande (ovan).
    negatives = session.execute(
        base_q.where(Transaction.amount < 0)
        .where(Account.incognito.is_(False))
    ).all()

    by_owner: dict[str, dict[str, float]] = {}

    def _bucket_for_id(owner_id):
        key = f"user_{owner_id}" if owner_id else "gemensamt"
        return by_owner.setdefault(key, {"income": 0.0, "expenses": 0.0})

    for owner_id, _aid, _name, _type, total in positives:
        _bucket_for_id(owner_id)["income"] += _d(total)
    for owner_id, _aid, _name, _type, total in negatives:
        _bucket_for_id(owner_id)["expenses"] += -_d(total)

    # Per konto
    per_account: dict[int, dict] = {}
    for owner_id, aid, name, acc_type, total in positives:
        per_account.setdefault(aid, {
            "account_id": aid, "account": name, "type": acc_type,
            "owner_id": owner_id, "income": 0.0, "expenses": 0.0,
        })["income"] += _d(total)
    for owner_id, aid, name, acc_type, total in negatives:
        per_account.setdefault(aid, {
            "account_id": aid, "account": name, "type": acc_type,
            "owner_id": owner_id, "income": 0.0, "expenses": 0.0,
        })["expenses"] += -_d(total)

    # Komplettera med omatchade upcomings inom månaden — partner-lön
    # som dokumenterats utan CSV, eller manuella fakturor.
    user_name_to_id = {u.name: u.id for u in session.query(User).all()}

    manual_ups = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
            UpcomingTransaction.matched_transaction_id.is_(None),
        )
        .all()
    )
    for up in manual_ups:
        if up.kind == "income":
            # Falla tillbaka på debit-kontots ägare när upcoming.owner
            # är tomt — typiskt för en kommande lön på partnerns konto
            # där fritextfältet inte fyllts i.
            fallback_owner = None
            if up.debit_account_id is not None:
                acc = session.get(Account, up.debit_account_id)
                if acc is not None:
                    fallback_owner = acc.owner_id
            key = _resolve_owner_bucket_key(
                up.owner, user_name_to_id, fallback_owner,
            )
            b = by_owner.setdefault(key, {"income": 0.0, "expenses": 0.0})
            b["income"] += _d(up.amount)
        elif up.kind == "bill":
            # Utgifter fördelas på debit-kontots ägare om satt, annars
            # gemensamt.
            owner_id = None
            if up.debit_account_id is not None:
                acc = session.get(Account, up.debit_account_id)
                if acc is not None:
                    owner_id = acc.owner_id
            b = _bucket_for_id(owner_id)
            b["expenses"] += _d(up.amount)

    return {
        "month": month,
        "by_owner": by_owner,
        "by_account": list(per_account.values()),
    }
