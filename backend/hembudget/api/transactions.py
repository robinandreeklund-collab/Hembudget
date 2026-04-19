from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..categorize.engine import normalize_merchant
from ..categorize.rules import create_rule_from_correction
from ..db.models import Account, Category, Transaction
from .deps import db, require_auth
from .schemas import AccountIn, AccountOut, CategoryOut, TransactionOut, TransactionUpdate

router = APIRouter(tags=["transactions"], dependencies=[Depends(require_auth)])


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(session: Session = Depends(db)) -> list[Account]:
    return session.query(Account).order_by(Account.id).all()


@router.post("/accounts", response_model=AccountOut)
def create_account(payload: AccountIn, session: Session = Depends(db)) -> Account:
    a = Account(**payload.model_dump())
    session.add(a)
    session.flush()
    return a


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(session: Session = Depends(db)) -> list[Category]:
    return session.query(Category).order_by(Category.name).all()


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    uncategorized: bool = False,
    limit: int = Query(500, le=2000),
    offset: int = 0,
    session: Session = Depends(db),
) -> list[Transaction]:
    q = session.query(Transaction)
    if account_id is not None:
        q = q.filter(Transaction.account_id == account_id)
    if category_id is not None:
        q = q.filter(Transaction.category_id == category_id)
    if from_date:
        q = q.filter(Transaction.date >= from_date)
    if to_date:
        q = q.filter(Transaction.date <= to_date)
    if uncategorized:
        q = q.filter(Transaction.category_id.is_(None))
    return q.order_by(Transaction.date.desc(), Transaction.id.desc()).offset(offset).limit(limit).all()


@router.patch("/transactions/{tx_id}", response_model=TransactionOut)
def update_transaction(
    tx_id: int, payload: TransactionUpdate, session: Session = Depends(db)
) -> Transaction:
    tx = session.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    fields = payload.model_dump(exclude_unset=True)
    create_rule = fields.pop("create_rule", True)

    if "category_id" in fields and fields["category_id"] is not None:
        tx.category_id = fields["category_id"]
        tx.user_verified = True
        if create_rule and tx.normalized_merchant:
            create_rule_from_correction(
                session,
                pattern=tx.normalized_merchant.lower(),
                category_id=fields["category_id"],
                priority=120,
            )
    for k, v in fields.items():
        if k == "category_id":
            continue
        setattr(tx, k, v)
    session.flush()
    return tx


@router.post("/transactions/{tx_id}/reclassify", response_model=TransactionOut)
def reclassify(tx_id: int, session: Session = Depends(db)) -> Transaction:
    tx = session.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    tx.normalized_merchant = normalize_merchant(tx.raw_description)
    session.flush()
    return tx
