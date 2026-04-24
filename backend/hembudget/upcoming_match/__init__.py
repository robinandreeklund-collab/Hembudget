"""Matcha UpcomingTransaction (planerade fakturor/löner) mot riktiga
Transaction-rader.

Exakt belopp (±1 kr) + datum (±5 dagar) + rätt konto → par ihop. Sätter
`matched_transaction_id` så UI kan visa ✓ bokförd, och forecasten slutar
räkna raden som "kommande" (eftersom den redan inträffat).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Transaction, UpcomingPayment, UpcomingTransaction
from ..splits import apply_upcoming_lines_to_transaction
from .payments import add_payment

log = logging.getLogger(__name__)


class UpcomingMatcher:
    def __init__(
        self,
        session: Session,
        amount_tolerance: Decimal = Decimal("1.00"),
        date_tolerance_days: int = 5,
    ):
        self.session = session
        self.amount_tolerance = amount_tolerance
        self.date_tolerance_days = date_tolerance_days

    def match(self, new_transactions: list[Transaction]) -> int:
        """Matcha nyimporterade transaktioner mot öppna upcoming-rader.

        Används av CSV-import-flödet. Returnerar antal par-ihopningar."""
        if not new_transactions:
            return 0

        open_ups = self._open_upcomings()
        if not open_ups:
            return 0
        return self._pair(open_ups, new_transactions)

    def backfill_match(
        self,
        upcomings: list[UpcomingTransaction] | None = None,
    ) -> int:
        """Matcha öppna upcoming-rader mot BEFINTLIGA transaktioner.

        Användsfall: användaren laddar upp en gammal kreditkortsfaktura
        där autogiro-dragningen redan finns i databasen. Utan denna match
        blir fakturan liggande under "Kommande" för evigt. Med den flyttas
        den till "Betalda"-listan direkt.

        Söker efter matchande Transaction per upcoming (belopps- och
        datumtolerans + rätt konto om angivet). Returnerar antal nya par.
        """
        ups = upcomings if upcomings is not None else self._open_upcomings()
        if not ups:
            return 0

        matched = 0
        for up in ups:
            if up.matched_transaction_id is not None:
                continue
            expected_amount = up.amount if up.kind == "income" else -up.amount
            target_date = up.debit_date or up.expected_date
            low = target_date - timedelta(days=self.date_tolerance_days)
            high = target_date + timedelta(days=self.date_tolerance_days)

            q = select(Transaction).where(
                Transaction.date >= low,
                Transaction.date <= high,
            )
            if up.debit_account_id is not None:
                q = q.where(Transaction.account_id == up.debit_account_id)
            # Undvik transaktioner som redan är kopplade till NÅGON upcoming.
            # Kollar både nya junction-tabellen OCH legacy matched_transaction_id
            # för att hantera data som migrerats och testscenarios.
            q = q.where(
                Transaction.id.not_in(
                    select(UpcomingPayment.transaction_id)
                ),
                Transaction.id.not_in(
                    select(UpcomingTransaction.matched_transaction_id).where(
                        UpcomingTransaction.matched_transaction_id.is_not(None),
                    )
                ),
            )
            candidates = [
                tx for tx in self.session.execute(q).scalars().all()
                if abs(tx.amount - expected_amount) <= self.amount_tolerance
            ]
            if not candidates:
                continue
            candidates.sort(key=lambda t: abs((t.date - target_date).days))
            chosen = candidates[0]
            add_payment(self.session, up, chosen)
            matched += 1
            if up.lines:
                apply_upcoming_lines_to_transaction(self.session, up, chosen)

        if matched:
            self.session.flush()
        return matched

    # ---------- helpers ----------

    def _open_upcomings(self) -> list[UpcomingTransaction]:
        return (
            self.session.query(UpcomingTransaction)
            .filter(UpcomingTransaction.matched_transaction_id.is_(None))
            .all()
        )

    def _pair(
        self,
        open_ups: list[UpcomingTransaction],
        new_transactions: list[Transaction],
    ) -> int:
        matched = 0
        used_tx_ids: set[int] = set()

        for up in open_ups:
            expected_amount = up.amount if up.kind == "income" else -up.amount
            target_date = up.debit_date or up.expected_date

            candidates = []
            for tx in new_transactions:
                if tx.id in used_tx_ids:
                    continue
                if up.debit_account_id is not None and tx.account_id != up.debit_account_id:
                    continue
                if abs(tx.amount - expected_amount) > self.amount_tolerance:
                    continue
                if abs((tx.date - target_date).days) > self.date_tolerance_days:
                    continue
                candidates.append(tx)

            if not candidates:
                continue

            candidates.sort(key=lambda t: abs((t.date - target_date).days))
            chosen = candidates[0]
            add_payment(self.session, up, chosen)
            used_tx_ids.add(chosen.id)
            matched += 1

            if up.lines:
                apply_upcoming_lines_to_transaction(self.session, up, chosen)

        if matched:
            self.session.flush()
        return matched
