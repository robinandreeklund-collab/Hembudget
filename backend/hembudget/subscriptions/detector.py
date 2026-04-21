from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean, pstdev

from sqlalchemy.orm import Session

from ..db.models import Subscription, Transaction


@dataclass
class SubscriptionCandidate:
    merchant: str
    amount: Decimal
    interval_days: int
    occurrences: int
    last_date: date
    next_expected_date: date
    account_id: int | None = None
    category_id: int | None = None


class SubscriptionDetector:
    """Hittar återkommande utgifter baserat på merchant + belopp + intervall."""

    def __init__(
        self,
        session: Session,
        min_occurrences: int = 3,
        amount_tolerance: float = 0.05,
        day_tolerance: int = 4,
    ):
        self.session = session
        self.min_occurrences = min_occurrences
        self.amount_tolerance = amount_tolerance
        self.day_tolerance = day_tolerance

    def detect(self, since: date | None = None) -> list[SubscriptionCandidate]:
        q = self.session.query(Transaction).filter(
            Transaction.amount < 0,
            Transaction.normalized_merchant.is_not(None),
            Transaction.is_transfer.is_(False),
        )
        if since:
            q = q.filter(Transaction.date >= since)
        txs = q.order_by(Transaction.date.asc()).all()

        by_merchant: dict[str, list[Transaction]] = defaultdict(list)
        for tx in txs:
            by_merchant[tx.normalized_merchant].append(tx)

        candidates: list[SubscriptionCandidate] = []
        for merchant, group in by_merchant.items():
            if len(group) < self.min_occurrences:
                continue
            # Cluster by similar amount
            amounts = [float(t.amount) for t in group]
            avg_amount = mean(amounts)
            if avg_amount == 0:
                continue
            tol = abs(avg_amount) * self.amount_tolerance
            filtered = [t for t in group if abs(float(t.amount) - avg_amount) <= tol]
            if len(filtered) < self.min_occurrences:
                continue
            # Interval
            dates = sorted(t.date for t in filtered)
            intervals = [(b - a).days for a, b in zip(dates, dates[1:])]
            if not intervals:
                continue
            interval = round(mean(intervals))
            spread = pstdev(intervals) if len(intervals) > 1 else 0
            if spread > self.day_tolerance + 1:
                continue
            # Snap to typical intervals
            for ref in (7, 14, 30, 31, 90, 180, 365):
                if abs(interval - ref) <= self.day_tolerance:
                    interval = ref
                    break
            last = dates[-1]
            next_expected = last + timedelta(days=interval)
            candidates.append(
                SubscriptionCandidate(
                    merchant=merchant,
                    amount=Decimal(str(round(avg_amount, 2))),
                    interval_days=interval,
                    occurrences=len(filtered),
                    last_date=last,
                    next_expected_date=next_expected,
                    account_id=filtered[-1].account_id,
                    category_id=filtered[-1].category_id,
                )
            )
        candidates.sort(key=lambda c: -abs(float(c.amount)))
        return candidates

    def persist(self, candidates: list[SubscriptionCandidate]) -> list[Subscription]:
        saved: list[Subscription] = []
        for c in candidates:
            existing = (
                self.session.query(Subscription)
                .filter(Subscription.merchant == c.merchant)
                .first()
            )
            if existing:
                existing.amount = c.amount
                existing.interval_days = c.interval_days
                existing.next_expected_date = c.next_expected_date
                existing.category_id = c.category_id
                existing.active = True
                saved.append(existing)
            else:
                s = Subscription(
                    merchant=c.merchant,
                    amount=c.amount,
                    interval_days=c.interval_days,
                    next_expected_date=c.next_expected_date,
                    account_id=c.account_id,
                    category_id=c.category_id,
                )
                self.session.add(s)
                self.session.flush()
                saved.append(s)
        return saved
