from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..budget.forecast import CashflowForecaster
from ..budget.monthly import MonthlyBudgetService
from ..chat import tools as chat_tools
from ..db.models import Transaction
from ..school.activity import log_activity as _log_activity
from ..subscriptions.detector import SubscriptionDetector
from .deps import db, require_auth
from .schemas import BudgetBulkIn, BudgetIn

router = APIRouter(prefix="/budget", tags=["budget"], dependencies=[Depends(require_auth)])


@router.get("/months")
def available_months(session: Session = Depends(db)) -> dict:
    """Returnerar alla månader som har minst en icke-transfer transaktion."""
    rows = session.execute(
        select(
            func.strftime("%Y-%m", Transaction.date).label("month"),
            func.count(Transaction.id).label("count"),
        )
        .where(Transaction.is_transfer.is_(False))
        .group_by("month")
        .order_by("month")
    ).all()
    return {"months": [{"month": m, "count": c} for m, c in rows]}


@router.post("/")
def set_budget(payload: BudgetIn, session: Session = Depends(db)) -> dict:
    svc = MonthlyBudgetService(session)
    b = svc.set_budget(payload.month, payload.category_id, payload.planned_amount)
    _log_activity(
        "budget.set",
        f"Satte budget för {payload.month}: "
        f"{float(payload.planned_amount):.0f} kr",
        payload={
            "month": payload.month,
            "category_id": payload.category_id,
            "amount": float(payload.planned_amount),
        },
    )
    return {"id": b.id, "month": b.month, "category_id": b.category_id,
            "planned_amount": float(b.planned_amount)}


@router.post("/auto")
def auto_budget(
    month: str,
    lookback_months: int = 6,
    overwrite: bool = False,
    session: Session = Depends(db),
) -> dict:
    """Fyll i planerad budget automatiskt från medianen av senaste
    `lookback_months` månader. Default: ändrar bara kategorier som saknar
    budget för given månad — sätt overwrite=true för att ersätta allt.

    OBS: denna endpoint är legacy. Nya UI:n använder
    /budget/{month}/auto-fill-preview + /budget/bulk-set istället, där
    användaren markerar vilka rader som ska sparas."""
    svc = MonthlyBudgetService(session)
    created = svc.auto_budget(month, lookback_months=lookback_months, overwrite=overwrite)
    return {
        "month": month,
        "lookback_months": lookback_months,
        "updated": len(created),
        "budgets": [
            {
                "category_id": b.category_id,
                "planned_amount": float(b.planned_amount),
            }
            for b in created
        ],
    }


@router.get("/{month}/breakdown")
def month_breakdown(
    month: str,
    kind: str = "income",
    session: Session = Depends(db),
) -> dict:
    """Platt lista med poster (transaktioner + omatchade upcomings) för
    månaden, filtrerat på income/expense. Summan stämmer med
    MonthlyBudgetService.summary(month).income/expenses så KPI-kortet
    och breakdown-modalen visar samma siffra.

    Matchar exakt samma exkluderingsregler som summary:
    - Inga transfers
    - Inga privata utgifter på incognito-konton (men inkomster räknas)
    - Omatchade upcomings med expected_date i månaden tas med
    """
    import re
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        from fastapi import HTTPException
        raise HTTPException(404, f"Invalid month format: {month}")
    if kind not in ("income", "expense"):
        from fastapi import HTTPException
        raise HTTPException(400, "kind måste vara 'income' eller 'expense'")

    from ..db.models import Account, Category, UpcomingTransaction
    from ..budget.monthly import _month_bounds
    start, end = _month_bounds(month)

    items: list[dict] = []

    # 1. Transaktioner — inklusive splits-aware filtrering. För vår
    #    modal räcker det att visa raw-transaktioner — splits visas bara
    #    som tooltip-hint via category_id.
    q = (
        session.query(Transaction, Account, Category)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .filter(
            Transaction.date >= start,
            Transaction.date < end,
            Transaction.is_transfer.is_(False),
        )
    )
    if kind == "income":
        q = q.filter(Transaction.amount > 0)
    else:
        q = q.filter(Transaction.amount < 0)
        # Privata utgifter på inkognito-konton räknas inte i summary,
        # så vi ska inte visa dem i modalen heller.
        q = q.filter(Account.incognito.is_(False))

    for tx, acc, cat in q.all():
        items.append({
            "id": tx.id,
            "date": tx.date.isoformat(),
            "description": tx.raw_description,
            "amount": float(tx.amount),
            "category_id": tx.category_id,
            "category": cat.name if cat else None,
            "account": acc.name,
            "source": "transaction",
        })

    # 2. Omatchade upcomings inom månaden — samma logik som
    #    MonthlyBudgetService.summary() använder när den räknar in
    #    manuellt dokumenterade löner och bills.
    target_kind = "income" if kind == "income" else "bill"
    ups = (
        session.query(UpcomingTransaction, Category)
        .outerjoin(Category, Category.id == UpcomingTransaction.category_id)
        .filter(
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
            UpcomingTransaction.matched_transaction_id.is_(None),
            UpcomingTransaction.kind == target_kind,
        )
        .all()
    )
    for up, cat in ups:
        # Summary lägger på amount direkt (positivt för income, positivt
        # för bill → expense). För modalen normaliserar vi till samma
        # sign-konvention som transactions: income +, expense -.
        amt = float(up.amount)
        if kind == "expense":
            amt = -abs(amt)
        items.append({
            "id": f"upcoming_{up.id}",
            "date": up.expected_date.isoformat(),
            "description": up.name,
            "amount": amt,
            "category_id": up.category_id,
            "category": cat.name if cat else None,
            "account": None,
            "source": "upcoming",
        })

    items.sort(key=lambda i: i["date"])
    return {
        "month": month,
        "kind": kind,
        "items": items,
        "total": sum(i["amount"] for i in items),
    }


@router.get("/{month}/auto-fill-preview")
def auto_fill_preview(
    month: str,
    lookback_months: int = 6,
    session: Session = Depends(db),
) -> dict:
    """Förhandsvisa auto-fyll-förslag utan att spara något. UI:n visar
    en lista där användaren bockar i vilka kategorier som ska fyllas —
    sen skickas valen till POST /budget/bulk-set."""
    import re
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        from fastapi import HTTPException
        raise HTTPException(404, f"Invalid month format: {month}")
    svc = MonthlyBudgetService(session)
    suggestions = svc.auto_fill_suggestions(month, lookback_months=lookback_months)
    return {
        "month": month,
        "lookback_months": lookback_months,
        "suggestions": [
            {
                "category_id": s.category_id,
                "category": s.category,
                "group": s.group,
                "suggested": float(s.suggested),
                "current_planned": (
                    float(s.current_planned) if s.current_planned is not None else None
                ),
                "months_with_data": s.months_with_data,
                "kind": s.kind,
            }
            for s in suggestions
        ],
    }


@router.post("/bulk-set")
def bulk_set_budget(payload: BudgetBulkIn, session: Session = Depends(db)) -> dict:
    """Sätt budget för flera kategorier samtidigt. Används när användaren
    godkänt ett urval från auto-fyll-modalen."""
    svc = MonthlyBudgetService(session)
    saved = svc.bulk_set(
        payload.month,
        [(r.category_id, r.planned_amount) for r in payload.rows],
    )
    if saved:
        total = sum(float(b.planned_amount) for b in saved)
        _log_activity(
            "budget.set",
            f"Satte budget för {len(saved)} kategorier i {payload.month} "
            f"(totalt {total:.0f} kr)",
            payload={"month": payload.month, "count": len(saved), "total": total},
        )
    return {
        "month": payload.month,
        "saved": len(saved),
        "budgets": [
            {"category_id": b.category_id, "planned_amount": float(b.planned_amount)}
            for b in saved
        ],
    }


@router.get("/forecast/cashflow")
def forecast(months: int = 6, session: Session = Depends(db)) -> dict:
    out = CashflowForecaster(session).project(horizon_months=months)
    return {
        "forecast": [
            {
                "month": m.month,
                "income": float(m.projected_income),
                "expenses": float(m.projected_expenses),
                "net": float(m.projected_net),
            }
            for m in out
        ]
    }


@router.get("/anomalies/{month}")
def anomalies(
    month: str,
    threshold_sigma: float = 2.0,
    session: Session = Depends(db),
) -> dict:
    """Statistiska avvikelser mot 6 månaders historik — z-score per kategori."""
    return chat_tools.detect_anomalies(session, month, threshold_sigma=threshold_sigma)


@router.get("/family/{month}")
def family(month: str, session: Session = Depends(db)) -> dict:
    """Per-ägare och per-konto: inkomst och utgift separat för månaden."""
    return chat_tools.get_family_breakdown(session, month)


@router.get("/ytd-income")
def ytd_income(
    year: int | None = None,
    category_name: str = "Lön",
    session: Session = Depends(db),
) -> dict:
    """Total lön/inkomst per kontoägare för året (YTD eller angivet år)."""
    return chat_tools.ytd_income_by_person(
        session, year=year, category_name=category_name
    )


@router.get("/subscriptions/health")
def subscription_health(
    stale_days: int = 60,
    session: Session = Depends(db),
) -> dict:
    """Hälsokoll för prenumerationer — hitta de som inte dragits på länge."""
    return chat_tools.subscription_health(session, stale_days=stale_days)


@router.post("/subscriptions/detect")
def detect_subs(session: Session = Depends(db)) -> dict:
    det = SubscriptionDetector(session)
    candidates = det.detect()
    det.persist(candidates)
    return {
        "count": len(candidates),
        "subscriptions": [
            {
                "merchant": c.merchant,
                "amount": float(c.amount),
                "interval_days": c.interval_days,
                "next_expected_date": c.next_expected_date.isoformat(),
                "occurrences": c.occurrences,
            }
            for c in candidates
        ],
    }


@router.post("/subscriptions/{sub_id}/deactivate")
def deactivate_subscription(sub_id: int, session: Session = Depends(db)) -> dict:
    """Markera en prenumeration som inaktiv — slutar dyka upp i hälso-
    kollen och genererar inga nya kommande-rader. Bakomliggande
    transaktioner berörs inte."""
    from ..db.models import Subscription
    sub = session.get(Subscription, sub_id)
    if sub is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Subscription not found")
    sub.active = False
    session.flush()
    return {"id": sub_id, "active": False}


@router.delete("/subscriptions/{sub_id}")
def delete_subscription(sub_id: int, session: Session = Depends(db)) -> dict:
    """Ta bort en prenumeration helt. Auto-materialiserade kommande-
    rader (source=auto:subscription, matched_transaction_id IS NULL)
    raderas också så de inte stör prognosen. Bankrader rör vi inte."""
    from ..db.models import Subscription, UpcomingTransaction
    sub = session.get(Subscription, sub_id)
    if sub is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Subscription not found")
    # Rensa auto-genererade upcomings där name matchar merchant
    deleted_ups = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.source == "auto:subscription",
            UpcomingTransaction.name == sub.merchant,
            UpcomingTransaction.matched_transaction_id.is_(None),
        )
        .all()
    )
    for u in deleted_ups:
        session.delete(u)
    session.delete(sub)
    session.flush()
    return {"deleted": sub_id, "removed_upcomings": len(deleted_ups)}


@router.get("/{month}")
def get_summary(month: str, session: Session = Depends(db)) -> dict:
    """Månadsöversikt. OBS: måste deklareras SIST bland GET-routes annars
    fångar `{month}` catch-all andra endpoints som /ytd-income, /family/…,
    /subscriptions/health osv."""
    import re
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        from fastapi import HTTPException
        raise HTTPException(404, f"Invalid month format: {month}")
    s = MonthlyBudgetService(session).summary(month)
    return {
        "month": s.month,
        "income": float(s.income),
        "expenses": float(s.expenses),
        "savings": float(s.savings),
        "savings_rate": s.savings_rate,
        "lines": [
            {
                "category_id": l.category_id,
                "category": l.category,
                "planned": float(l.planned),
                "actual": float(l.actual),
                "diff": float(l.diff),
                "kind": l.kind,
                "group_id": l.group_id,
                "group": l.group,
                "progress_pct": l.progress_pct,
                "trend_median": float(l.trend_median),
            }
            for l in s.lines
        ],
        "groups": [
            {
                "group_id": g.group_id,
                "group": g.group,
                "planned": float(g.planned),
                "actual": float(g.actual),
                "diff": float(g.diff),
                "progress_pct": g.progress_pct,
                "category_ids": g.category_ids,
            }
            for g in s.groups
        ],
    }
