"""Helpers för UpcomingTransaction-payments.

En UpcomingTransaction kan ha flera Transaction-matchningar via
UpcomingPayment-tabellen (t.ex. en kreditkortsfaktura betald i två
omgångar). Denna modul samlar logiken för att beräkna:
- Summan av alla delbetalningar
- Återstående belopp
- Status: 'unpaid' | 'partial' | 'paid' | 'overpaid'
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from ..db.models import Transaction, UpcomingPayment, UpcomingTransaction


# Tolerans för "fullt betalt" — svenska fakturor har ofta öresavrundning
# på någon krona, så vi ger lite slack för att räkna som fullt betald.
FULL_PAID_TOLERANCE = Decimal("2.00")


def list_payment_tx_ids(session: Session, upcoming_id: int) -> list[int]:
    rows = (
        session.query(UpcomingPayment.transaction_id)
        .filter(UpcomingPayment.upcoming_id == upcoming_id)
        .all()
    )
    return [r[0] for r in rows]


def paid_amount(session: Session, up: UpcomingTransaction) -> Decimal:
    """Summa av alla länkade Transactions, alltid returnerad som POSITIVT
    belopp (oavsett kind) för att jämföra med up.amount."""
    ids = list_payment_tx_ids(session, up.id)
    if not ids:
        return Decimal("0")
    txs = session.query(Transaction).filter(Transaction.id.in_(ids)).all()
    total = sum((abs(t.amount) for t in txs), Decimal("0"))
    return total


def payment_status(session: Session, up: UpcomingTransaction) -> str:
    """Returnera 'unpaid', 'partial', 'paid', eller 'overpaid'."""
    paid = paid_amount(session, up)
    if paid == 0:
        return "unpaid"
    remaining = up.amount - paid
    if abs(remaining) <= FULL_PAID_TOLERANCE:
        return "paid"
    if remaining > 0:
        return "partial"
    return "overpaid"


def add_payment(
    session: Session, up: UpcomingTransaction, tx: Transaction,
) -> bool:
    """Lägg till en Transaction som en delbetalning av upcomingen.

    Returnerar True om en ny rad skapades, False om den redan fanns.
    Om upcomingens `matched_transaction_id` är None sätts den till denna
    tx.id (för bakåtkompatibilitet med UI som fortfarande tittar på
    single-match-fältet).
    """
    existing = (
        session.query(UpcomingPayment)
        .filter(
            UpcomingPayment.upcoming_id == up.id,
            UpcomingPayment.transaction_id == tx.id,
        )
        .first()
    )
    if existing is not None:
        return False

    session.add(UpcomingPayment(upcoming_id=up.id, transaction_id=tx.id))
    if up.matched_transaction_id is None:
        up.matched_transaction_id = tx.id
    session.flush()
    return True


def remove_payment(
    session: Session, up: UpcomingTransaction, tx_id: int,
) -> bool:
    """Ta bort en delbetalning. Om det var den "primära" matchningen,
    flytta fältet till nästa kvarvarande betalning (eller None)."""
    row = (
        session.query(UpcomingPayment)
        .filter(
            UpcomingPayment.upcoming_id == up.id,
            UpcomingPayment.transaction_id == tx_id,
        )
        .first()
    )
    if row is None:
        return False
    session.delete(row)
    session.flush()
    if up.matched_transaction_id == tx_id:
        next_row = (
            session.query(UpcomingPayment)
            .filter(UpcomingPayment.upcoming_id == up.id)
            .order_by(UpcomingPayment.id)
            .first()
        )
        up.matched_transaction_id = next_row.transaction_id if next_row else None
    return True


def remove_all_payments_for_tx(session: Session, tx_id: int) -> list[int]:
    """När en Transaction unmatchas från alla sina upcomings. Returnerar
    listan av upcoming-IDs som påverkades."""
    rows = (
        session.query(UpcomingPayment)
        .filter(UpcomingPayment.transaction_id == tx_id)
        .all()
    )
    upcoming_ids: list[int] = []
    for r in rows:
        upcoming_ids.append(r.upcoming_id)
        session.delete(r)
    session.flush()
    # Uppdatera matched_transaction_id på upcomings där det pekade på tx_id
    from ..db.models import UpcomingTransaction as _UT
    affected = (
        session.query(_UT).filter(_UT.matched_transaction_id == tx_id).all()
    )
    for up in affected:
        next_row = (
            session.query(UpcomingPayment)
            .filter(UpcomingPayment.upcoming_id == up.id)
            .order_by(UpcomingPayment.id)
            .first()
        )
        up.matched_transaction_id = next_row.transaction_id if next_row else None
    return upcoming_ids
