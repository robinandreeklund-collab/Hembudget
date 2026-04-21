from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..budget.forecast import CashflowForecaster
from ..budget.monthly import MonthlyBudgetService
from ..chat import tools as chat_tools
from ..db.models import Transaction
from ..subscriptions.detector import SubscriptionDetector
from .deps import db, require_auth
from .schemas import BudgetIn

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


@router.get("/{month}")
def get_summary(month: str, session: Session = Depends(db)) -> dict:
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
            }
            for l in s.lines
        ],
    }


@router.post("/")
def set_budget(payload: BudgetIn, session: Session = Depends(db)) -> dict:
    svc = MonthlyBudgetService(session)
    b = svc.set_budget(payload.month, payload.category_id, payload.planned_amount)
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
    budget för given månad — sätt overwrite=true för att ersätta allt."""
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
