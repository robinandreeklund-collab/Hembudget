from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db.models import Account, Transaction
from ..transfers.detector import TransferDetector
from .deps import db, require_auth

router = APIRouter(prefix="/transfers", tags=["transfers"], dependencies=[Depends(require_auth)])


def _tx_out(tx: Transaction, accounts: dict[int, Account]) -> dict:
    acc = accounts.get(tx.account_id)
    return {
        "id": tx.id,
        "account_id": tx.account_id,
        "account_name": acc.name if acc else None,
        "date": tx.date.isoformat(),
        "amount": float(tx.amount),
        "description": tx.raw_description,
        "is_transfer": tx.is_transfer,
        "transfer_pair_id": tx.transfer_pair_id,
    }


@router.get("/paired")
def list_paired(session: Session = Depends(db)) -> dict:
    """Alla transaktioner där båda sidor är markerade som transfer och parade."""
    rows = (
        session.query(Transaction)
        .filter(
            Transaction.is_transfer.is_(True),
            Transaction.transfer_pair_id.is_not(None),
            Transaction.amount < 0,
        )
        .order_by(Transaction.date.desc())
        .all()
    )
    accounts = {a.id: a for a in session.query(Account).all()}
    tx_by_id = {t.id: t for t in session.query(Transaction).all()}

    pairs = []
    for src in rows:
        dst = tx_by_id.get(src.transfer_pair_id)
        if dst is None:
            continue
        pairs.append({
            "source": _tx_out(src, accounts),
            "destination": _tx_out(dst, accounts),
        })
    return {"pairs": pairs, "count": len(pairs)}


@router.get("/unpaired")
def list_unpaired(session: Session = Depends(db)) -> dict:
    """Markerade som transfer men utan motpart — kräver granskning."""
    rows = (
        session.query(Transaction)
        .filter(
            Transaction.is_transfer.is_(True),
            Transaction.transfer_pair_id.is_(None),
        )
        .order_by(Transaction.date.desc())
        .all()
    )
    accounts = {a.id: a for a in session.query(Account).all()}
    return {
        "transactions": [_tx_out(t, accounts) for t in rows],
        "count": len(rows),
    }


@router.get("/suggestions")
def list_suggestions(
    date_tolerance_days: int = 5,
    amount_tolerance: float = 0.01,
    session: Session = Depends(db),
) -> dict:
    """Okategoriserade rader som SER UT som möjliga transfers — en negativ
    på ett konto och en positiv med liknande belopp på ett annat konto."""
    account_ids = [a.id for a in session.query(Account).all()]
    if len(account_ids) < 2:
        return {"suggestions": []}

    accounts = {a.id: a for a in session.query(Account).all()}
    unpaired = (
        session.query(Transaction)
        .filter(
            Transaction.account_id.in_(account_ids),
            Transaction.transfer_pair_id.is_(None),
            Transaction.is_transfer.is_(False),
        )
        .all()
    )

    tol = Decimal(str(amount_tolerance))
    suggestions = []
    seen: set[tuple[int, int]] = set()

    for src in unpaired:
        if src.amount >= 0:
            continue
        abs_amt = -src.amount
        low = abs_amt * (Decimal("1") - tol)
        high = abs_amt * (Decimal("1") + tol)
        for dst in unpaired:
            if dst.amount <= 0 or dst.account_id == src.account_id:
                continue
            if not (low <= dst.amount <= high):
                continue
            if abs((dst.date - src.date).days) > date_tolerance_days:
                continue
            key = tuple(sorted((src.id, dst.id)))
            if key in seen:
                continue
            seen.add(key)
            suggestions.append({
                "source": _tx_out(src, accounts),
                "destination": _tx_out(dst, accounts),
                "date_diff_days": abs((dst.date - src.date).days),
                "amount_diff": float(abs(dst.amount - abs_amt)),
            })

    # Sortera: mest uppenbara först (samma dag + exakt belopp)
    suggestions.sort(key=lambda s: (s["date_diff_days"], s["amount_diff"]))
    return {"suggestions": suggestions[:100], "count": len(suggestions)}


class LinkIn(BaseModel):
    tx_a_id: int
    tx_b_id: int


@router.post("/link")
def link_pair(payload: LinkIn, session: Session = Depends(db)) -> dict:
    try:
        TransferDetector(session).link_manual(payload.tx_a_id, payload.tx_b_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"ok": True}


@router.post("/unlink/{tx_id}")
def unlink(tx_id: int, session: Session = Depends(db)) -> dict:
    TransferDetector(session).unlink(tx_id)
    return {"ok": True}


@router.post("/batch-create-counterparts")
def batch_create_counterparts(
    payload: dict, session: Session = Depends(db),
) -> dict:
    """Skapa motsvarigheter för ALLA orphan-transfers mot ett valt konto.

    Typiskt användsfall: du har massor av insättningar från partnerns
    sida som flaggats som transfer utan motpart. Välj hennes inkognito-
    konto, klicka "Skapa motsvarande för alla" → systemet gör det i ett
    svep.

    Body: `{"target_account_id": int, "tx_ids"?: list[int]}`. Om tx_ids
    är None körs det för ALLA orphans (is_transfer=True, inget pair-id,
    och inte redan på target-kontot).
    """
    import hashlib

    target_id = payload.get("target_account_id")
    if not isinstance(target_id, int):
        raise HTTPException(400, "target_account_id (int) krävs i body")
    target = session.get(Account, target_id)
    if target is None:
        raise HTTPException(404, "Target account not found")

    tx_ids_raw = payload.get("tx_ids")
    q = (
        session.query(Transaction)
        .filter(
            Transaction.is_transfer.is_(True),
            Transaction.transfer_pair_id.is_(None),
            Transaction.account_id != target_id,
        )
    )
    if tx_ids_raw:
        q = q.filter(Transaction.id.in_(tx_ids_raw))
    orphans = q.all()

    created_ids: list[int] = []
    detector = TransferDetector(session)
    for tx in orphans:
        counterpart_amount = -tx.amount
        key = f"batch-counter|{target_id}|{tx.date}|{counterpart_amount}|from-{tx.id}"
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        counter = Transaction(
            account_id=target_id,
            date=tx.date,
            amount=counterpart_amount,
            currency=tx.currency,
            raw_description=f"Motpart till {tx.raw_description or 'tx #' + str(tx.id)}",
            hash=h,
        )
        session.add(counter)
        session.flush()
        try:
            detector.link_manual(tx.id, counter.id)
            created_ids.append(counter.id)
        except ValueError:
            # Något gick fel med pairing — rulla inte tillbaka hela batchen
            continue
    session.flush()
    return {
        "target_account_id": target_id,
        "target_account_name": target.name,
        "orphans_processed": len(orphans),
        "counterparts_created": len(created_ids),
        "counterpart_tx_ids": created_ids,
    }


@router.post("/{tx_id}/create-counterpart")
def create_counterpart(
    tx_id: int, payload: dict, session: Session = Depends(db),
) -> dict:
    """Skapa en motsatt-tecknad Transaction på ett annat konto och para
    ihop de som överföring. Används för att manuellt dokumentera
    partnerns sida när man bara ser en orphan-transfer på gemensamt
    kontot.

    Body: `{account_id: int, description?: str, date?: YYYY-MM-DD}`.
    Datumet defaultar till source-tx:s datum.
    """
    import hashlib
    from datetime import date as _date

    tx = session.get(Transaction, tx_id)
    if tx is None:
        raise HTTPException(404, "Transaction not found")
    account_id = payload.get("account_id")
    if not isinstance(account_id, int):
        raise HTTPException(400, "account_id (int) krävs")
    if account_id == tx.account_id:
        raise HTTPException(400, "Motparten måste vara ett ANNAT konto")
    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(404, "Target account not found")

    date_s = payload.get("date")
    if date_s:
        try:
            tx_date = _date.fromisoformat(date_s)
        except ValueError:
            raise HTTPException(400, f"Ogiltigt datum: {date_s}") from None
    else:
        tx_date = tx.date

    description = (payload.get("description") or "").strip()
    if not description:
        description = f"Motpart till tx #{tx.id}"

    counterpart_amount = -tx.amount  # motsatt tecken
    key = f"counterpart|{account_id}|{tx_date}|{counterpart_amount}|from-tx-{tx.id}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()

    counter = Transaction(
        account_id=account_id,
        date=tx_date,
        amount=counterpart_amount,
        currency=tx.currency,
        raw_description=description,
        hash=h,
    )
    session.add(counter)
    session.flush()

    # Para ihop dem som transfer
    TransferDetector(session).link_manual(tx.id, counter.id)
    session.flush()

    return {
        "source_tx_id": tx.id,
        "counterpart_tx_id": counter.id,
        "account_id": account_id,
        "amount": float(counterpart_amount),
        "paired_as_transfer": True,
    }
