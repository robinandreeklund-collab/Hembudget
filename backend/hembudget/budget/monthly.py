from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Iterable

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


def _shift_months(d: date, months: int) -> date:
    """Flytta till samma dag-i-månaden N månader framåt/bakåt (negativt tal = bakåt).
    Vid månadsbyte där dagen inte finns (t.ex. 31 → februari) används sista dagen."""
    import calendar
    m = d.month - 1 + months
    y = d.year + m // 12
    new_month = m % 12 + 1
    last_day = calendar.monthrange(y, new_month)[1]
    return date(y, new_month, min(d.day, last_day))


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

    def auto_budget(
        self,
        target_month: str,
        lookback_months: int = 6,
        overwrite: bool = False,
    ) -> list[Budget]:
        """Sätt planerad budget per kategori = median av de senaste N månaderna.

        Utgiftskategorier sparas som NEGATIVA plannerade belopp (konsistent
        med transaktionstecken). Inkomstkategorier sparas som positiva. Både
        splits och plain transactions räknas.

        Om `overwrite=False` lämnas befintliga budgetrader orörda — endast
        kategorier utan budget i target_month uppdateras. Detta gör det
        säkert att köra upprepade gånger utan att skriva över manuella
        justeringar.
        """
        target_start, _ = _month_bounds(target_month)
        lookback_start = _shift_months(target_start, -lookback_months)

        # Samla utgift/inkomst per kategori per månad från båda tabellerna.
        split_tx_ids = (
            select(TransactionSplit.transaction_id).distinct().scalar_subquery()
        )
        plain_rows = self.session.execute(
            select(
                func.strftime("%Y-%m", Transaction.date).label("m"),
                Transaction.category_id,
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.date >= lookback_start,
                Transaction.date < target_start,
                Transaction.is_transfer.is_(False),
                Transaction.category_id.is_not(None),
                Transaction.id.not_in(split_tx_ids),
            )
            .group_by("m", Transaction.category_id)
        ).all()

        split_rows = self.session.execute(
            select(
                func.strftime("%Y-%m", Transaction.date).label("m"),
                TransactionSplit.category_id,
                func.sum(TransactionSplit.amount).label("total"),
            )
            .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
            .where(
                Transaction.date >= lookback_start,
                Transaction.date < target_start,
                Transaction.is_transfer.is_(False),
                TransactionSplit.category_id.is_not(None),
            )
            .group_by("m", TransactionSplit.category_id)
        ).all()

        # cat_id → { month → summa }
        per_cat: dict[int, dict[str, float]] = {}
        for month, cat_id, total in list(plain_rows) + list(split_rows):
            if cat_id is None:
                continue
            per_cat.setdefault(int(cat_id), {})
            per_cat[int(cat_id)][month] = (
                per_cat[int(cat_id)].get(month, 0.0) + float(total or 0)
            )

        existing = {
            b.category_id: b
            for b in self.session.query(Budget).filter(Budget.month == target_month).all()
        }

        out: list[Budget] = []
        for cat_id, series in per_cat.items():
            values = list(series.values())
            if not values:
                continue
            med = Decimal(str(round(median(values), 2)))
            # Hoppa över kategorier med mycket liten aktivitet (median < 50 kr)
            if abs(med) < Decimal("50"):
                continue
            if cat_id in existing and not overwrite:
                continue
            out.append(self.set_budget(target_month, cat_id, med))
        return out

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
