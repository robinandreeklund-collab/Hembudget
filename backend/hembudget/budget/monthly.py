from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db.models import Budget, Category, Transaction, TransactionSplit


@dataclass
class CategoryLine:
    category_id: int
    category: str
    planned: Decimal
    actual: Decimal
    diff: Decimal
    # Nya fält för v2-UI:n. Bakåtkompatibla — äldre kod som bara läser
    # (category_id, category, planned, actual, diff) fortsätter fungera.
    kind: str = "expense"  # "income" | "expense"
    group_id: int | None = None  # parent_id om kategorin är under en grupp
    group: str | None = None  # parent.name
    progress_pct: float = 0.0  # |actual| / |planned|, 0.0 om planned=0
    trend_median: Decimal = Decimal("0")  # median utfall senaste 3 mån


@dataclass
class GroupSummary:
    """Aggregat per kategorigrupp (parent). 'Utan grupp' samlar
    kategorier utan parent."""
    group_id: int | None
    group: str
    planned: Decimal
    actual: Decimal
    diff: Decimal
    progress_pct: float
    category_ids: list[int] = field(default_factory=list)


@dataclass
class AutoFillSuggestion:
    """En förslags-rad för auto-fyll-modalen. Användaren kan bocka i vilka
    som ska sparas — allt eller inget är fel UX."""
    category_id: int
    category: str
    group: str | None
    suggested: Decimal  # median av utfall senaste N månader
    current_planned: Decimal | None  # nuvarande budget för target_month
    months_with_data: int
    kind: str  # "income" | "expense"


@dataclass
class MonthSummary:
    month: str
    income: Decimal
    expenses: Decimal
    savings: Decimal
    savings_rate: float
    lines: list[CategoryLine] = field(default_factory=list)
    groups: list[GroupSummary] = field(default_factory=list)


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

        # Set av transaktion-IDs med splits (Python-set, ej scalar-subquery).
        split_tx_ids: set[int] = {
            row[0]
            for row in self.session.execute(
                select(TransactionSplit.transaction_id).distinct()
            ).all()
        }
        plain_q = (
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
            )
            .group_by("m", Transaction.category_id)
        )
        if split_tx_ids:
            plain_q = plain_q.where(Transaction.id.not_in(split_tx_ids))
        plain_rows = self.session.execute(plain_q).all()

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

        # Hämta alla transaktions-id som har splits — som Python-set.
        # (Scalar-subquery mot en korrelerad NOT IN har visat sig segfaulta
        # sqlcipher3 i WSL; vanlig SQL-IN med explicit lista är mer stabilt.)
        split_tx_ids: set[int] = {
            row[0]
            for row in self.session.execute(
                select(TransactionSplit.transaction_id).distinct()
            ).all()
        }

        # Transaktioner som INTE är uppsplittrade — grupperas på
        # transactions.category_id som vanligt. Inkognito-kontons privata
        # utgifter exkluderas (vi spårar dem inte), bara deras inkomster
        # räknas i familj/totaler.
        from ..db.models import Account as _Acc
        base_q = (
            select(
                Transaction.category_id,
                Category.name,
                func.sum(Transaction.amount).label("total"),
            )
            .join(Category, Category.id == Transaction.category_id, isouter=True)
            .join(_Acc, _Acc.id == Transaction.account_id)
            .where(
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.is_transfer.is_(False),
                # Privata utgifter på inkognito-konton räknas inte —
                # men inkomster gör det
                or_(
                    _Acc.incognito.is_(False),
                    Transaction.amount > 0,
                ),
            )
            .group_by(Transaction.category_id, Category.name)
        )
        if split_tx_ids:
            base_q = base_q.where(Transaction.id.not_in(split_tx_ids))
        tx_rows = self.session.execute(base_q).all()

        # Uppsplittrade transaktioner — grupperas på splits.category_id.
        # Filtrerar även här bort transfers + privata utgifter på incognito.
        split_rows = (
            self.session.execute(
                select(
                    TransactionSplit.category_id,
                    Category.name,
                    func.sum(TransactionSplit.amount).label("total"),
                )
                .join(Category, Category.id == TransactionSplit.category_id, isouter=True)
                .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
                .join(_Acc, _Acc.id == Transaction.account_id)
                .where(
                    Transaction.date >= start,
                    Transaction.date < end,
                    Transaction.is_transfer.is_(False),
                    or_(
                        _Acc.incognito.is_(False),
                        TransactionSplit.amount > 0,
                    ),
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

        # Inkludera omatchade upcomings för månaden — användaren kan ha
        # lagt in partnerns lön manuellt utan CSV, eller en bill som
        # förfaller men ännu inte bokförts. Detta speglar logiken i
        # /budget/ytd-income och /budget/family.
        from ..db.models import UpcomingTransaction
        manual_ups = (
            self.session.query(UpcomingTransaction)
            .filter(
                UpcomingTransaction.expected_date >= start,
                UpcomingTransaction.expected_date < end,
                UpcomingTransaction.matched_transaction_id.is_(None),
            )
            .all()
        )
        for up in manual_ups:
            if up.kind == "income":
                income += up.amount
            elif up.kind == "bill":
                expenses += up.amount

        planned_rows = (
            self.session.query(Budget, Category)
            .join(Category, Category.id == Budget.category_id)
            .filter(Budget.month == month)
            .all()
        )

        # Förladda kategori-träd så vi kan gruppera per parent utan N+1.
        all_cats = self.session.query(Category).all()
        cat_by_id: dict[int, Category] = {c.id: c for c in all_cats}

        def _parent_info(cat_id: int) -> tuple[int | None, str | None]:
            c = cat_by_id.get(cat_id)
            if c is None or c.parent_id is None:
                return None, None
            parent = cat_by_id.get(c.parent_id)
            if parent is None:
                return None, None
            return parent.id, parent.name

        # Trend: median absolut utfall per kategori över de 3 senaste
        # månaderna (exklusive innevarande). Används som hint i UI:n.
        trend_start = _shift_months(start, -3)
        trend_by_cat = self._history_median_abs(trend_start, start)

        lines: list[CategoryLine] = []
        seen: set[int] = set()

        def _kind_of(planned: Decimal, actual: Decimal) -> str:
            """Kategoriklassning: om någon av planerad eller utfall är
            positiv kallar vi den 'income'. Utgiftskategorier har typiskt
            negativa utfall (pengar UT från kontot) — planned_amount sparas
            också negativt via auto_budget."""
            if actual > 0 or planned > 0:
                return "income"
            return "expense"

        def _progress(planned: Decimal, actual: Decimal) -> float:
            if planned == 0:
                return 0.0
            # Jämför absoluta belopp för att hantera negativa utgifter
            # konsistent. Returnera procent (0-200 är typiska värden).
            return round(float(abs(actual) / abs(planned) * 100), 1)

        for b, c in planned_rows:
            _, actual = actual_by_cat.get(c.id, (c.name, Decimal("0")))
            planned_v = b.planned_amount
            kind = _kind_of(planned_v, actual)
            g_id, g_name = _parent_info(c.id)
            lines.append(
                CategoryLine(
                    category_id=c.id,
                    category=c.name,
                    planned=planned_v,
                    actual=actual,
                    diff=planned_v - (-actual if actual < 0 else actual),
                    kind=kind,
                    group_id=g_id,
                    group=g_name,
                    progress_pct=_progress(planned_v, actual),
                    trend_median=trend_by_cat.get(c.id, Decimal("0")),
                )
            )
            seen.add(c.id)
        for cat_id, (name, actual) in actual_by_cat.items():
            if cat_id in seen:
                continue
            kind = _kind_of(Decimal("0"), actual)
            g_id, g_name = _parent_info(cat_id)
            lines.append(
                CategoryLine(
                    category_id=cat_id,
                    category=name,
                    planned=Decimal("0"),
                    actual=actual,
                    diff=Decimal("0") - (-actual if actual < 0 else actual),
                    kind=kind,
                    group_id=g_id,
                    group=g_name,
                    progress_pct=0.0,
                    trend_median=trend_by_cat.get(cat_id, Decimal("0")),
                )
            )

        savings = income - expenses
        rate = float(savings / income) if income > 0 else 0.0
        # Sortera utgifter efter hur nära/över budget man är (mest röd
        # överst), inkomster separat underst. Ger en naturlig "fokusera på
        # det som sticker ut"-vy.
        lines.sort(
            key=lambda l: (
                l.kind == "income",  # False (expenses) först
                -l.progress_pct,
                float(l.actual),
            )
        )

        # Gruppaggregat — används av UI:n för collapsible-grupper.
        groups_map: dict[tuple[int | None, str], GroupSummary] = {}
        for l in lines:
            # Inkomster hamnar i sin egen bucket "Inkomster" så det blir
            # tydligt — annars skulle de slåss med utgifter i samma grupp.
            if l.kind == "income":
                key = (None, "Inkomster")
                label = "Inkomster"
                gid = None
            else:
                key = (l.group_id, l.group or "Övrigt")
                label = l.group or "Övrigt"
                gid = l.group_id
            g = groups_map.get(key)
            if g is None:
                g = GroupSummary(
                    group_id=gid,
                    group=label,
                    planned=Decimal("0"),
                    actual=Decimal("0"),
                    diff=Decimal("0"),
                    progress_pct=0.0,
                )
                groups_map[key] = g
            g.planned += l.planned
            g.actual += l.actual
            g.diff += l.diff
            g.category_ids.append(l.category_id)
        for g in groups_map.values():
            g.progress_pct = _progress(g.planned, g.actual)

        groups = list(groups_map.values())
        groups.sort(
            key=lambda g: (g.group == "Inkomster", -g.progress_pct, g.group)
        )

        return MonthSummary(
            month=month,
            income=income,
            expenses=expenses,
            savings=savings,
            savings_rate=round(rate, 4),
            lines=lines,
            groups=groups,
        )

    def _history_median_abs(
        self, start: date, end: date
    ) -> dict[int, Decimal]:
        """Median absolut utfall per kategori i perioden [start, end).
        Används av UI:n för att visa 'snitt senaste 3 mån' bredvid budget.
        Inkluderar både plain tx och splits."""
        split_tx_ids: set[int] = {
            row[0]
            for row in self.session.execute(
                select(TransactionSplit.transaction_id).distinct()
            ).all()
        }
        plain_q = (
            select(
                func.strftime("%Y-%m", Transaction.date).label("m"),
                Transaction.category_id,
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.is_transfer.is_(False),
                Transaction.category_id.is_not(None),
            )
            .group_by("m", Transaction.category_id)
        )
        if split_tx_ids:
            plain_q = plain_q.where(Transaction.id.not_in(split_tx_ids))
        plain_rows = self.session.execute(plain_q).all()

        split_rows = self.session.execute(
            select(
                func.strftime("%Y-%m", Transaction.date).label("m"),
                TransactionSplit.category_id,
                func.sum(TransactionSplit.amount).label("total"),
            )
            .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
            .where(
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.is_transfer.is_(False),
                TransactionSplit.category_id.is_not(None),
            )
            .group_by("m", TransactionSplit.category_id)
        ).all()

        per_cat: dict[int, dict[str, float]] = {}
        for m, cat_id, total in list(plain_rows) + list(split_rows):
            if cat_id is None:
                continue
            per_cat.setdefault(int(cat_id), {})
            per_cat[int(cat_id)][m] = per_cat[int(cat_id)].get(m, 0.0) + float(total or 0)
        out: dict[int, Decimal] = {}
        for cat_id, series in per_cat.items():
            values = [abs(v) for v in series.values()]
            if not values:
                continue
            out[cat_id] = Decimal(str(round(median(values), 2)))
        return out

    def auto_fill_suggestions(
        self, target_month: str, lookback_months: int = 6
    ) -> list[AutoFillSuggestion]:
        """Förbered auto-fyll-förslag per kategori utan att spara. Används
        av /budget/{month}/auto-fill-preview så användaren kan markera
        vilka rader som ska sparas via /budget/bulk-set."""
        target_start, _ = _month_bounds(target_month)
        lookback_start = _shift_months(target_start, -lookback_months)

        split_tx_ids: set[int] = {
            row[0]
            for row in self.session.execute(
                select(TransactionSplit.transaction_id).distinct()
            ).all()
        }
        plain_q = (
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
            )
            .group_by("m", Transaction.category_id)
        )
        if split_tx_ids:
            plain_q = plain_q.where(Transaction.id.not_in(split_tx_ids))
        plain_rows = self.session.execute(plain_q).all()
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

        per_cat: dict[int, dict[str, float]] = {}
        for m, cat_id, total in list(plain_rows) + list(split_rows):
            if cat_id is None:
                continue
            per_cat.setdefault(int(cat_id), {})
            per_cat[int(cat_id)][m] = per_cat[int(cat_id)].get(m, 0.0) + float(total or 0)

        existing = {
            b.category_id: b
            for b in self.session.query(Budget).filter(Budget.month == target_month).all()
        }
        all_cats = {c.id: c for c in self.session.query(Category).all()}

        out: list[AutoFillSuggestion] = []
        for cat_id, series in per_cat.items():
            values = list(series.values())
            if not values:
                continue
            med = Decimal(str(round(median(values), 2)))
            if abs(med) < Decimal("50"):
                continue
            c = all_cats.get(cat_id)
            if c is None:
                continue
            parent = all_cats.get(c.parent_id) if c.parent_id else None
            kind = "income" if med > 0 else "expense"
            out.append(
                AutoFillSuggestion(
                    category_id=cat_id,
                    category=c.name,
                    group=parent.name if parent else None,
                    suggested=med,
                    current_planned=(
                        existing[cat_id].planned_amount
                        if cat_id in existing
                        else None
                    ),
                    months_with_data=len(values),
                    kind=kind,
                )
            )
        # Sortera: utgifter först (störst absolut belopp överst), sen inkomster.
        out.sort(
            key=lambda s: (s.kind == "income", -abs(float(s.suggested)))
        )
        return out

    def bulk_set(
        self, month: str, rows: list[tuple[int, Decimal]]
    ) -> list[Budget]:
        """Sätt budget för flera kategorier i ett svep. Används av
        auto-fyll-modalen där användaren valt specifika förslag."""
        out: list[Budget] = []
        for cat_id, amount in rows:
            out.append(self.set_budget(month, cat_id, amount))
        return out
