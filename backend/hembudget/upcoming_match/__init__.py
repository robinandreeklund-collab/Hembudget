"""Matcha UpcomingTransaction (planerade fakturor/löner) mot riktiga
Transaction-rader när de dyker upp i CSV-import.

Exakt belopp (±1 kr) + datum (±5 dagar) + rätt konto → par ihop. Sätter
`matched_transaction_id` så UI kan visa ✓ bokförd, och forecasten slutar
räkna raden som "kommande" (eftersom den redan inträffat).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from ..db.models import Transaction, UpcomingTransaction
from ..splits import apply_upcoming_lines_to_transaction

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
        """Returnera antal par-ihopningar. Kollar bara UpcomingTransaction
        som ännu inte är matchade. När en match sker och UpcomingTransaction
        har lines (t.ex. el/vatten/bredband på samma faktura), kopieras de
        till transaction_splits så budget/rapporter kan fördela rätt."""
        if not new_transactions:
            return 0

        open_ups: list[UpcomingTransaction] = (
            self.session.query(UpcomingTransaction)
            .filter(UpcomingTransaction.matched_transaction_id.is_(None))
            .all()
        )
        if not open_ups:
            return 0

        matched = 0
        used_tx_ids: set[int] = set()

        for up in open_ups:
            expected_amount = up.amount if up.kind == "income" else -up.amount
            target_date = up.debit_date or up.expected_date

            candidates = []
            for tx in new_transactions:
                if tx.id in used_tx_ids:
                    continue
                # Korrekt konto om angivet
                if up.debit_account_id is not None and tx.account_id != up.debit_account_id:
                    continue
                # Beloppstolerans
                if abs(tx.amount - expected_amount) > self.amount_tolerance:
                    continue
                # Datumtolerans
                if abs((tx.date - target_date).days) > self.date_tolerance_days:
                    continue
                candidates.append(tx)

            if not candidates:
                continue

            # Välj närmaste i datum
            candidates.sort(key=lambda t: abs((t.date - target_date).days))
            chosen = candidates[0]
            up.matched_transaction_id = chosen.id
            used_tx_ids.add(chosen.id)
            matched += 1

            # Kopiera ev. fakturarader till transaction_splits
            if up.lines:
                apply_upcoming_lines_to_transaction(self.session, up, chosen)

        if matched:
            self.session.flush()
        return matched
