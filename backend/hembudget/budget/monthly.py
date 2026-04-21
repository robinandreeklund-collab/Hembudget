from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Budget, Category, Transaction, TransactionSplit


@dataclass
class CategoryLine:
    category_id: int
    category: str
    planned: Decimal
    actual: Decimal
    diff: Decimal


@dataclass
class MonthSummary:
    month: str
    income: Decimal
    expenses: Decimal
    savings: Decimal
    savings_rate: float
    lines: list[CategoryLine] = field(default_factory=list)


def _month_bounds(month: str) -> tuple[date, date]:
    year, mon = map(int, month.split("-"))
    start = date(year, mon, 1)
    if mon == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, mon + 1, 1)
    return start, end


class MonthlyBudgetService:
    def __init__(self, session: Session):
        self.session = session

    def set_budget(self, month: str, category_id: int, planned: Decimal) -> Budget:
        b = (
            self.session.query(Budget)
            .filter(Budget.month == month, Budget.category_id == category_id)
            .first()
        )
        if b:
            b.planned_amount = planned
        else:
            b = Budget(month=month, category_id=category_id, planned_amount=planned)
            self.session.add(b)
            self.session.flush()
        return b

    def summary(self, month: str) -> MonthSummary:
        start, end = _month_bounds(month)

        # Transaktioner som INTE är uppsplittrade — grupperas på
        # transactions.category_id som vanligt.
        split_tx_ids = (
            select(TransactionSplit.transaction_id)
            .distinct()
            .scalar_subquery()
        )
        tx_rows = (
            self.session.execute(
                select(
                    Transaction.category_id,
                    Category.name,
                    func.sum(Transaction.amount).label("total"),
                )
                .join(Category, Category.id == Transaction.category_id, isouter=True)
                .where(
                    Transaction.date >= start,
                    Transaction.date < end,
                    Transaction.is_transfer.is_(False),
                    Transaction.id.not_in(split_tx_ids),
                )
                .group_by(Transaction.category_id, Category.name)
            )
        ).all()

        # Uppsplittrade transaktioner — grupperas på splits.category_id.
        # Filtrerar även här bort transfers via join mot transactions.
        split_rows = (
            self.session.execute(
                select(
                    TransactionSplit.category_id,
                    Category.name,
                    func.sum(TransactionSplit.amount).label("total"),
                )
                .join(Category, Category.id == TransactionSplit.category_id, isouter=True)
                .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
                .where(
                    Transaction.date >= start,
                    Transaction.date < end,
                    Transaction.is_transfer.is_(False),
                )
                .group_by(TransactionSplit.category_id, Category.name)
            )
        ).all()

        income = Decimal("0")
        expenses = Decimal("0")
        actual_by_cat: dict[int, tuple[str, Decimal]] = {}

        def _accumulate(cat_id, cat_name, total):
            nonlocal income, expenses
            total = Decimal(total or 0)
            if cat_id is not None:
                prev_name, prev_total = actual_by_cat.get(
                    cat_id, (cat_name or "Okategoriserat", Decimal("0"))
                )
                actual_by_cat[cat_id] = (
                    cat_name or prev_name or "Okategoriserat",
                    prev_total + total,
                )
            if total > 0:
                income += total
            else:
                expenses += -total

        for cat_id, cat_name, total in tx_rows:
            _accumulate(cat_id, cat_name, total)
        for cat_id, cat_name, total in split_rows:
            _accumulate(cat_id, cat_name, total)

        planned_rows = (
            self.session.query(Budget, Category)
            .join(Category, Category.id == Budget.category_id)
            .filter(Budget.month == month)
            .all()
        )
        lines: list[CategoryLine] = []
        seen: set[int] = set()
        for b, c in planned_rows:
            actual_name, actual = actual_by_cat.get(c.id, (c.name, Decimal("0")))
            lines.append(
                CategoryLine(
                    category_id=c.id,
                    category=c.name,
                    planned=b.planned_amount,
                    actual=actual,
                    diff=b.planned_amount - (-actual if actual < 0 else actual),
                )
            )
            seen.add(c.id)
        for cat_id, (name, actual) in actual_by_cat.items():
            if cat_id in seen:
                continue
            lines.append(
                CategoryLine(
                    category_id=cat_id,
                    category=name,
                    planned=Decimal("0"),
                    actual=actual,
                    diff=Decimal("0") - (-actual if actual < 0 else actual),
                )
            )

        savings = income - expenses
        rate = float(savings / income) if income > 0 else 0.0
        lines.sort(key=lambda l: l.actual)
        return MonthSummary(
            month=month,
            income=income,
            expenses=expenses,
            savings=savings,
            savings_rate=round(rate, 4),
            lines=lines,
        )
