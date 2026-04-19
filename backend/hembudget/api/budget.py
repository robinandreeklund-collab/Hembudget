from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..budget.forecast import CashflowForecaster
from ..budget.monthly import MonthlyBudgetService
from ..subscriptions.detector import SubscriptionDetector
from .deps import db, require_auth
from .schemas import BudgetIn

router = APIRouter(prefix="/budget", tags=["budget"], dependencies=[Depends(require_auth)])


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
