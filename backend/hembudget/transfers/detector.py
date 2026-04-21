"""Upptäck överföringar mellan egna konton för att undvika dubbelbokföring.

Typiska scenarion:
- Nordea lönekonto betalar Amex-fakturan:
    "AMEX AUTOGIRO -15 000 kr"  (Nordea-raden)
    "AMEX ÅTERBETALNING +15 000 kr"  (Amex-raden, om CSV:n innehåller den)
- Överföring till sparkonto:
    "ÖVERFÖRING SPARKONTO -5 000 kr"  (Nordea)
    "INSÄTTNING +5 000 kr"  (Sparkontot, om importerat)

Kreditkortsbetalningar markeras som `is_transfer=True` så de inte
räknas som utgifter (detaljerna finns ju i kreditkortsraderna).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import Account, Transaction

log = logging.getLogger(__name__)


# Merchant-substring → bank-id. Matchas case-insensitivt.
CREDIT_CARD_PAYMENT_PATTERNS: dict[str, list[str]] = {
    "amex": [
        "amex",
        "american express",
        "eurobonus amex",
    ],
    "seb_kort": [
        "seb kort",
        "sebkort",
        "seb mastercard",
        "seb eurobonus",
    ],
}

# Generiska överförings-mönster — markerar som transfer men parar inte ihop
# automatiskt om motkontot inte är känt.
GENERIC_TRANSFER_PATTERNS: list[str] = [
    "överföring",
    "egen överföring",
    "isk insättning",
    "sparkonto",
]


@dataclass
class TransferLinkResult:
    marked: int              # antal transaktioner markerade som transfer
    paired: int              # antal som också parades ihop med sin motpart


@dataclass
class InternalScanResult:
    pairs: int                         # antal ihoparade par
    ambiguous: int                     # antal som hade flera matchningar
    details: list[tuple[int, int]]     # (src_id, dst_id) par


class TransferDetector:
    def __init__(
        self,
        session: Session,
        amount_tolerance: float = 0.02,   # 2 % slack för växelkurser/avgifter
        day_tolerance: int = 7,
    ):
        self.session = session
        self.amount_tolerance = amount_tolerance
        self.day_tolerance = day_tolerance

    def detect_and_link(self, new_transactions: list[Transaction]) -> TransferLinkResult:
        """Kör efter import. Markerar credit-card-payments från transaktionerna
        och försöker para ihop med motsvarande rad på kreditkortskontot."""
        if not new_transactions:
            return TransferLinkResult(0, 0)

        # Karta bank → credit-konto
        credit_by_bank: dict[str, Account] = {}
        for acc in self.session.query(Account).filter(Account.type == "credit").all():
            credit_by_bank[acc.bank] = acc

        marked = 0
        paired = 0

        for tx in new_transactions:
            if tx.is_transfer:
                continue
            if tx.amount >= 0:
                # Betalningar är negativa. Positiva rader hanteras via
                # reverse-matchning (när kreditkorts-repayment hittas).
                continue

            desc = (tx.raw_description or "").lower()

            # 1. Match mot explicit kreditkortsbetalning
            matched_bank: str | None = None
            for bank, patterns in CREDIT_CARD_PAYMENT_PATTERNS.items():
                if any(p in desc for p in patterns):
                    matched_bank = bank
                    break

            if matched_bank:
                tx.is_transfer = True
                tx.category_id = None  # inte en utgift
                marked += 1
                credit_acc = credit_by_bank.get(matched_bank)
                if credit_acc:
                    repayment = self._find_repayment_on_credit(tx, credit_acc.id)
                    if repayment is not None:
                        tx.transfer_pair_id = repayment.id
                        repayment.is_transfer = True
                        repayment.transfer_pair_id = tx.id
                        repayment.category_id = None
                        paired += 1
                continue

            # 2. Generiska överförings-mönster (t.ex. till sparkonto)
            if any(p in desc for p in GENERIC_TRANSFER_PATTERNS):
                tx.is_transfer = True
                tx.category_id = None
                marked += 1

        if marked:
            self.session.flush()
        return TransferLinkResult(marked, paired)

    def _find_repayment_on_credit(
        self, payment_tx: Transaction, credit_account_id: int
    ) -> Transaction | None:
        """Hitta en positiv rad på kreditkortskontot som motsvarar betalningen."""
        abs_amount = abs(payment_tx.amount)
        low = abs_amount * Decimal(str(1 - self.amount_tolerance))
        high = abs_amount * Decimal(str(1 + self.amount_tolerance))
        date_from = payment_tx.date - timedelta(days=self.day_tolerance)
        date_to = payment_tx.date + timedelta(days=self.day_tolerance)

        return (
            self.session.query(Transaction)
            .filter(
                Transaction.account_id == credit_account_id,
                Transaction.amount >= low,
                Transaction.amount <= high,
                Transaction.date >= date_from,
                Transaction.date <= date_to,
                Transaction.transfer_pair_id.is_(None),
                Transaction.id != payment_tx.id,
            )
            .order_by(
                func.abs(
                    func.julianday(Transaction.date) - func.julianday(payment_tx.date)
                )
            )
            .first()
        )

    def detect_internal_transfers(
        self,
        date_tolerance_days: int = 3,
        amount_tolerance: float = 0.005,   # 0.5 %
    ) -> InternalScanResult:
        """Para ihop överföringar mellan egna konton baserat på datum + belopp.

        Conservative: parar bara om exakt en kandidat matchar, eller en
        kandidat ligger på samma dag medan övriga ligger utanför. Detta
        minimerar falska positiva som kan gömma riktiga utgifter.
        """
        account_ids = [a.id for a in self.session.query(Account).all()]
        if len(account_ids) < 2:
            return InternalScanResult(0, 0, [])

        unpaired = (
            self.session.query(Transaction)
            .filter(
                Transaction.account_id.in_(account_ids),
                Transaction.is_transfer.is_(False),
                Transaction.transfer_pair_id.is_(None),
            )
            .order_by(Transaction.date.asc(), Transaction.id.asc())
            .all()
        )

        claimed: set[int] = set()
        pairs: list[tuple[int, int]] = []
        ambiguous = 0
        tol = Decimal(str(amount_tolerance))

        for src in unpaired:
            if src.id in claimed or src.amount >= 0:
                continue
            abs_amt = -src.amount
            low = abs_amt * (Decimal("1") - tol)
            high = abs_amt * (Decimal("1") + tol)

            candidates = [
                t
                for t in unpaired
                if t.id not in claimed
                and t.id != src.id
                and t.account_id != src.account_id
                and t.amount > 0
                and low <= t.amount <= high
                and abs((t.date - src.date).days) <= date_tolerance_days
            ]

            dst: Transaction | None = None
            if len(candidates) == 1:
                dst = candidates[0]
            elif len(candidates) > 1:
                # Om exakt en ligger samma dag, välj den
                same_day = [c for c in candidates if c.date == src.date]
                if len(same_day) == 1:
                    dst = same_day[0]
                else:
                    ambiguous += 1

            if dst is not None:
                src.is_transfer = True
                src.transfer_pair_id = dst.id
                src.category_id = None
                dst.is_transfer = True
                dst.transfer_pair_id = src.id
                dst.category_id = None
                claimed.add(src.id)
                claimed.add(dst.id)
                pairs.append((src.id, dst.id))

        if pairs:
            self.session.flush()
        return InternalScanResult(pairs=len(pairs), ambiguous=ambiguous, details=pairs)

    def link_manual(self, tx_a_id: int, tx_b_id: int) -> None:
        """Manuellt para ihop två transaktioner som en överföring."""
        a = self.session.get(Transaction, tx_a_id)
        b = self.session.get(Transaction, tx_b_id)
        if a is None or b is None:
            raise ValueError("Transaction not found")
        a.is_transfer = True
        b.is_transfer = True
        a.transfer_pair_id = b.id
        b.transfer_pair_id = a.id
        a.category_id = None
        b.category_id = None
        self.session.flush()

    def unlink(self, tx_id: int) -> None:
        """Ta bort transfer-markering."""
        tx = self.session.get(Transaction, tx_id)
        if tx is None:
            return
        pair_id = tx.transfer_pair_id
        tx.is_transfer = False
        tx.transfer_pair_id = None
        if pair_id is not None:
            pair = self.session.get(Transaction, pair_id)
            if pair is not None:
                pair.is_transfer = False
                pair.transfer_pair_id = None
        self.session.flush()
