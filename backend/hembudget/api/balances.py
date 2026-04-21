from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import Account, Transaction
from .deps import db, require_auth

router = APIRouter(prefix="/balances", tags=["balances"], dependencies=[Depends(require_auth)])


@router.get("/")
def list_balances(
    as_of: Optional[date] = None,
    session: Session = Depends(db),
) -> dict:
    """Nuvarande saldo per konto = opening_balance + summa(transaktioner efter
    opening_balance_date, till och med as_of eller idag). Om ingen öppningsbalans
    finns utgår vi från 0 och summerar alla transaktioner."""
    target_date = as_of or date.today()
    accounts = session.query(Account).order_by(Account.id).all()
    out = []
    total = Decimal("0")

    for acc in accounts:
        start = acc.opening_balance_date
        ob = acc.opening_balance or Decimal("0")

        q = session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.account_id == acc.id,
            Transaction.date <= target_date,
        )
        if start is not None:
            q = q.filter(Transaction.date > start)
        movement = Decimal(str(q.scalar() or 0))

        current = ob + movement
        total += current
        out.append({
            "id": acc.id,
            "name": acc.name,
            "bank": acc.bank,
            "type": acc.type,
            "account_number": acc.account_number,
            "opening_balance": float(ob),
            "opening_balance_date": start.isoformat() if start else None,
            "movement_since_opening": float(movement),
            "current_balance": float(current),
        })

    return {
        "as_of": target_date.isoformat(),
        "accounts": out,
        "total_balance": float(total),
    }
