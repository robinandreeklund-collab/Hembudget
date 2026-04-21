"""Hantering av transaktionsuppdelningar (splits).

En TransactionSplit låter en enskild bankrad fördelas över flera kategorier
— typfallet är en faktura från t.ex. Hjo Energi där totalsumman innehåller
el, vatten och bredband i samma transaktion. När vi matchar
UpcomingTransaction mot den riktiga bankraden kopieras eventuella
UpcomingTransactionLine hit.

Invarianter:
- sum(splits.amount) ska ligga inom SPLIT_TOLERANCE av transactions.amount.
- splits har samma tecken som transaktionen (negativt för utgift).
- Om avrundning gör summan icke-exakt, fördelas residualen på sista raden.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from ..db.models import (
    Category,
    Transaction,
    TransactionSplit,
    UpcomingTransaction,
    UpcomingTransactionLine,
)

log = logging.getLogger(__name__)

# Avrundningstolerans mellan sum(splits) och transaction.amount.
# Samma som UpcomingMatcher.amount_tolerance — ±1 kr räcker för att
# absorbera avrundning i vision-parsningen.
SPLIT_TOLERANCE = Decimal("1.00")


def resolve_category_id(session: Session, name: str | None) -> int | None:
    """Lös upp ett kategorinamn till id (case-insensitive)."""
    if not name:
        return None
    needle = name.strip().lower()
    if not needle:
        return None
    for c in session.query(Category).all():
        if c.name.lower() == needle:
            return c.id
    return None


def build_lines_from_vision(
    session: Session,
    parsed_lines: Iterable[dict],
) -> list[UpcomingTransactionLine]:
    """Konvertera vision-utdata {description, amount, category?} till
    UpcomingTransactionLine-objekt med category_id uppslaget."""
    out: list[UpcomingTransactionLine] = []
    for i, row in enumerate(parsed_lines or []):
        desc = str(row.get("description") or "").strip()
        if not desc:
            continue
        try:
            amount = Decimal(str(row.get("amount"))).quantize(Decimal("0.01"))
        except (TypeError, ValueError, ArithmeticError):
            continue
        if amount <= 0:
            continue
        cat_id = resolve_category_id(session, row.get("category"))
        out.append(
            UpcomingTransactionLine(
                description=desc[:200],
                amount=amount,
                category_id=cat_id,
                sort_order=i,
            )
        )
    return out


def apply_upcoming_lines_to_transaction(
    session: Session,
    upcoming: UpcomingTransaction,
    transaction: Transaction,
) -> list[TransactionSplit]:
    """Kopiera UpcomingTransactionLine → TransactionSplit med rätt tecken.

    Återger tomt om upcoming saknar rader. Om en split redan finns på
    transaktionen rör vi den inte (idempotent).
    """
    if not upcoming.lines:
        return []

    existing = session.query(TransactionSplit).filter(
        TransactionSplit.transaction_id == transaction.id
    ).first()
    if existing is not None:
        log.info("Transaction %s already has splits — skipping copy", transaction.id)
        return []

    # Bill → negativ; income → positiv. Notera att transaktionen själv är
    # negativ för utgift, så vi matchar tecken.
    sign = Decimal("-1") if upcoming.kind == "bill" else Decimal("1")

    new_splits: list[TransactionSplit] = []
    for line in upcoming.lines:
        new_splits.append(
            TransactionSplit(
                transaction_id=transaction.id,
                description=line.description,
                amount=(line.amount * sign).quantize(Decimal("0.01")),
                category_id=line.category_id,
                sort_order=line.sort_order,
                source="upcoming",
            )
        )

    # Justera residualen på sista raden så sum(splits) == transaction.amount
    # inom toleransen (visionens rader + slutsumma kan skilja någon krona).
    residual = transaction.amount - sum(
        (s.amount for s in new_splits), Decimal("0")
    )
    if new_splits and abs(residual) <= SPLIT_TOLERANCE and residual != 0:
        new_splits[-1].amount = (
            new_splits[-1].amount + residual
        ).quantize(Decimal("0.01"))

    for s in new_splits:
        session.add(s)
    session.flush()
    return new_splits


def splits_sum(splits: Iterable[TransactionSplit]) -> Decimal:
    return sum((s.amount for s in splits), Decimal("0"))
