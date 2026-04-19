from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Transaction


@dataclass
class ForecastMonth:
    month: str
    projected_income: Decimal
    projected_expenses: Decimal
    projected_net: Decimal


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    return date(y, m % 12 + 1, 1)


class CashflowForecaster:
    """Enkel projektion: snitt av de senaste N månaderna (exkl. pågående)."""

    def __init__(self, session: Session, lookback_months: int = 6):
        self.session = session
        self.lookback = lookback_months

    def project(self, horizon_months: int = 6, as_of: date | None = None) -> list[ForecastMonth]:
        today = as_of or date.today()
        lookback_start = _add_months(today.replace(day=1), -self.lookback)
        end = today.replace(day=1)

        rows = self.session.execute(
            select(
                func.strftime("%Y-%m", Transaction.date).label("month"),
                func.sum(Transaction.amount).label("total"),
            )
            .where(Transaction.date >= lookback_start, Transaction.date < end)
            .group_by("month")
            .order_by("month")
        ).all()

        incomes: list[float] = []
        expenses: list[float] = []
        for _, total in rows:
            t = float(total or 0)
            if t > 0:
                incomes.append(t)
            else:
                expenses.append(-t)
        avg_income = Decimal(str(mean(incomes))) if incomes else Decimal("0")
        avg_expenses = Decimal(str(mean(expenses))) if expenses else Decimal("0")

        out: list[ForecastMonth] = []
        for i in range(1, horizon_months + 1):
            m = _add_months(end, i - 1)
            out.append(
                ForecastMonth(
                    month=m.strftime("%Y-%m"),
                    projected_income=avg_income.quantize(Decimal("0.01")),
                    projected_expenses=avg_expenses.quantize(Decimal("0.01")),
                    projected_net=(avg_income - avg_expenses).quantize(Decimal("0.01")),
                )
            )
        return out
