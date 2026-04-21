"""Matcha transaktioner mot registrerade lån.

Två nivåer:
1. `match_pattern` — fritextsträng på låneposten som matchas mot
   transaktionens beskrivning (case-insensitivt).
2. Klassificering — när en transaktion matchar ett lån, avgör om det är
   ränta eller amortering baserat på nyckelord i beskrivningen.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from ..db.models import Category, Loan, LoanPayment, Transaction

log = logging.getLogger(__name__)


INTEREST_KEYWORDS = (
    "ränta",
    "bolåneränta",
    "räntebetalning",
    "kreditavgift",
    "interest",
)

AMORTIZATION_KEYWORDS = (
    "amort",          # matchar amortering, amort
    "amortisation",
    "amortization",
    "kapital",        # "kapitalbelopp" används ibland
)


def classify_payment(description: str) -> str | None:
    """Return 'interest', 'amortization', or None if unclear."""
    s = (description or "").lower()
    for kw in AMORTIZATION_KEYWORDS:
        if kw in s:
            return "amortization"
    for kw in INTEREST_KEYWORDS:
        if kw in s:
            return "interest"
    return None


@dataclass
class LoanLinkResult:
    linked: int
    unclassified: int      # matchade lån men vi kunde inte avgöra ränta/amort


class LoanMatcher:
    def __init__(self, session: Session):
        self.session = session

    def match_and_classify(self, transactions: list[Transaction]) -> LoanLinkResult:
        loans: list[Loan] = (
            self.session.query(Loan).filter(Loan.active.is_(True)).all()
        )
        if not loans:
            return LoanLinkResult(0, 0)

        category_interest = self._category_id("Bolåneränta")
        category_amort = self._category_id("Amortering")

        linked = 0
        unclassified = 0

        for tx in transactions:
            if tx.amount >= 0 or tx.is_transfer:
                continue
            if self._already_linked(tx.id):
                continue
            loan = self._find_loan(loans, tx)
            if loan is None:
                continue
            ptype = classify_payment(tx.raw_description)
            if ptype is None:
                unclassified += 1
                continue
            self.session.add(
                LoanPayment(
                    loan_id=loan.id,
                    transaction_id=tx.id,
                    date=tx.date,
                    amount=-tx.amount,   # store positive
                    payment_type=ptype,
                )
            )
            if ptype == "interest" and category_interest is not None:
                tx.category_id = category_interest
            elif ptype == "amortization" and category_amort is not None:
                tx.category_id = category_amort
            linked += 1

        if linked > 0:
            self.session.flush()
        return LoanLinkResult(linked=linked, unclassified=unclassified)

    def outstanding_balance(self, loan: Loan) -> Decimal:
        """Current = principal − summa amorteringar."""
        rows = (
            self.session.query(LoanPayment)
            .filter(
                LoanPayment.loan_id == loan.id,
                LoanPayment.payment_type == "amortization",
                LoanPayment.date >= loan.start_date,
            )
            .all()
        )
        amortized = sum((p.amount for p in rows), Decimal("0"))
        return (loan.principal_amount - amortized).quantize(Decimal("0.01"))

    def total_interest_paid(self, loan: Loan) -> Decimal:
        rows = (
            self.session.query(LoanPayment)
            .filter(
                LoanPayment.loan_id == loan.id,
                LoanPayment.payment_type == "interest",
            )
            .all()
        )
        return sum((p.amount for p in rows), Decimal("0")).quantize(Decimal("0.01"))

    def _category_id(self, name: str) -> int | None:
        c = self.session.query(Category).filter(Category.name == name).first()
        return c.id if c else None

    def _find_loan(self, loans: list[Loan], tx: Transaction) -> Loan | None:
        desc = (tx.raw_description or "").lower()
        for loan in loans:
            if loan.match_pattern and loan.match_pattern.lower() in desc:
                return loan
        return None

    def _already_linked(self, tx_id: int) -> bool:
        return (
            self.session.query(LoanPayment)
            .filter(LoanPayment.transaction_id == tx_id)
            .first()
            is not None
        )
