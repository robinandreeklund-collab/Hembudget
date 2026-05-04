from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import mean

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..db.models import Transaction
from ..db.sql_compat import month_str


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

        _m_expr = month_str(self.session, Transaction.date)
        # Bug-fix: aggregera inkomst (positiva belopp) och utgift
        # (negativa belopp) SEPARAT per månad. Tidigare aggregerade vi
        # alla transaktioner till ett netto per månad och sorterade
        # månaden som "inkomst-månad" eller "utgift-månad" beroende på
        # nettots tecken — vilket är fel: en typisk månad har både
        # inkomst (+30000) och utgift (−25000) men klassificerades som
        # bara den ena baserat på +5000 netto.
        rows = self.session.execute(
            select(
                _m_expr.label("month"),
                func.coalesce(
                    func.sum(
                        case(
                            (Transaction.amount > 0, Transaction.amount),
                            else_=0,
                        )
                    ),
                    0,
                ).label("income"),
                func.coalesce(
                    func.sum(
                        case(
                            (Transaction.amount < 0, -Transaction.amount),
                            else_=0,
                        )
                    ),
                    0,
                ).label("expenses"),
            )
            .where(
                Transaction.date >= lookback_start,
                Transaction.date < end,
                Transaction.is_transfer.is_(False),
            )
            .group_by(_m_expr)
            .order_by(_m_expr)
        ).all()

        incomes: list[float] = []
        expenses: list[float] = []
        for _, inc, exp in rows:
            incomes.append(float(inc or 0))
            expenses.append(float(exp or 0))
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
