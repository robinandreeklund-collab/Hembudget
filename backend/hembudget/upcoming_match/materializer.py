"""Materialisera UpcomingTransaction från andra källor.

Idag skapas UpcomingTransaction via:
- manuell form (Upcoming-sidan)
- vision-parser (faktura-PDF)
- kreditkortsfaktura-parser

Här materialiserar vi även planerade poster från:
- **LoanScheduleEntry** — alla framtida, omatchade rater i lånescheman
  blir kommande fakturor (kind="bill") på rätt konto.
- **Subscription** — aktiva prenumerationer med next_expected_date
  blir kommande fakturor, rullar N månader framåt.

Logiken är idempotent: vi skapar bara nya rader om inte en liknande
UpcomingTransaction redan finns (matchar på källreferens i notes).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from ..db.models import (
    Account,
    LoanScheduleEntry,
    Subscription,
    UpcomingTransaction,
)

log = logging.getLogger(__name__)


# Marker-strängar så vi kan identifiera auto-skapade rader och inte
# duplicera dem om man kör materialisatorn flera gånger.
LOAN_SOURCE = "auto:loan_schedule"
SUB_SOURCE = "auto:subscription"


@dataclass
class MaterializeResult:
    loan_upcoming_created: int = 0
    sub_upcoming_created: int = 0
    skipped_existing: int = 0


class UpcomingMaterializer:
    def __init__(self, session: Session, horizon_days: int = 60):
        self.session = session
        self.horizon_days = horizon_days

    def run(self) -> MaterializeResult:
        result = MaterializeResult()
        self._materialize_loans(result)
        self._materialize_subscriptions(result)
        self.session.flush()
        return result

    # ---- Loans ----

    def _materialize_loans(self, result: MaterializeResult) -> None:
        today = date.today()
        horizon = today + timedelta(days=self.horizon_days)
        entries = (
            self.session.query(LoanScheduleEntry)
            .filter(
                LoanScheduleEntry.due_date >= today,
                LoanScheduleEntry.due_date <= horizon,
                LoanScheduleEntry.matched_transaction_id.is_(None),
            )
            .all()
        )
        if not entries:
            return

        # Cachad look-up av redan materialiserade (via notes-marker)
        existing_keys = {
            u.notes
            for u in self.session.query(UpcomingTransaction)
            .filter(UpcomingTransaction.source == LOAN_SOURCE)
            .all()
            if u.notes
        }

        # Slå ihop rater för samma (loan_id, due_date) till ETT upcoming
        # eftersom ränta och amortering dras som en gemensam autogiro-rad.
        bucket: dict[tuple[int, date], list[LoanScheduleEntry]] = {}
        for e in entries:
            bucket.setdefault((e.loan_id, e.due_date), []).append(e)

        for (loan_id, due_date), rows in bucket.items():
            total = sum((r.amount for r in rows), Decimal("0"))
            key = f"loan:{loan_id}:{due_date.isoformat()}"
            if key in existing_keys:
                result.skipped_existing += 1
                continue
            from ..db.models import Loan
            loan = self.session.get(Loan, loan_id)
            if loan is None:
                continue

            types = sorted({r.payment_type for r in rows})
            type_label = " + ".join(types) if len(types) > 1 else types[0]
            upcoming = UpcomingTransaction(
                kind="bill",
                name=f"{loan.name} ({type_label})",
                amount=total,
                expected_date=due_date,
                debit_date=due_date,
                autogiro=True,
                source=LOAN_SOURCE,
                notes=key,
            )
            self.session.add(upcoming)
            result.loan_upcoming_created += 1

    # ---- Subscriptions ----

    def _materialize_subscriptions(self, result: MaterializeResult) -> None:
        today = date.today()
        horizon = today + timedelta(days=self.horizon_days)
        subs = (
            self.session.query(Subscription)
            .filter(Subscription.active.is_(True))
            .all()
        )
        if not subs:
            return

        existing_keys = {
            u.notes
            for u in self.session.query(UpcomingTransaction)
            .filter(UpcomingTransaction.source == SUB_SOURCE)
            .all()
            if u.notes
        }

        for sub in subs:
            if not sub.next_expected_date:
                continue
            due = sub.next_expected_date
            # Rulla framåt tills horisonten — upp till 6 cycles så vi inte
            # råkar skapa hundratals för dagliga prenumerationer.
            count = 0
            while due <= horizon and count < 6:
                key = f"sub:{sub.id}:{due.isoformat()}"
                if key in existing_keys:
                    result.skipped_existing += 1
                else:
                    # Subscription.amount är signerat (negativt för utgifter)
                    # men UpcomingTransaction.amount följer konventionen
                    # "alltid positivt — tecken bestäms av kind (bill = dras,
                    # income = kommer in)". Därför abs:ar vi.
                    upcoming = UpcomingTransaction(
                        kind="bill",
                        name=sub.merchant,
                        amount=abs(sub.amount),
                        expected_date=due,
                        debit_date=due,
                        debit_account_id=sub.account_id,
                        category_id=sub.category_id,
                        autogiro=True,
                        recurring_monthly=(25 <= sub.interval_days <= 35),
                        source=SUB_SOURCE,
                        notes=key,
                    )
                    self.session.add(upcoming)
                    result.sub_upcoming_created += 1
                due = due + timedelta(days=sub.interval_days)
                count += 1
