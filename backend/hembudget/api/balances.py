from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..chat import tools as chat_tools
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
        is_incognito = bool(getattr(acc, "incognito", False))
        # Inkognito-konton exkluderas från total förmögenhet — de spåras
        # bara delvis (lön + överföringar) och saldo är meningslöst.
        if not is_incognito:
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
            "incognito": is_incognito,
        })

    return {
        "as_of": target_date.isoformat(),
        "accounts": out,
        "total_balance": float(total),
    }


@router.get("/history")
def balance_history(
    months: int = 12,
    account_id: Optional[int] = None,
    session: Session = Depends(db),
) -> dict:
    """Månadsvisa slutsaldon för varje konto. Dashboard använder detta för
    att visa nettoförmögenhetens utveckling över tid."""
    return chat_tools.get_balance_history(session, account_id=account_id, months=months)


@router.get("/net-worth")
def net_worth_timeline(
    months: int = 12,
    session: Session = Depends(db),
) -> dict:
    """Nettoförmögenhet = sum(alla kontosaldon) - sum(alla lånesaldon),
    per månad. Negativa kontotyper (credit) räknas som skuld redan."""
    from ..db.models import Loan
    from ..loans.matcher import LoanMatcher

    history = chat_tools.get_balance_history(session, months=months)
    # history.series är per konto; summera per tidpunkt
    totals: dict[str, float] = {}
    for serie in history.get("series", []):
        for p in serie["points"]:
            totals[p["date"]] = totals.get(p["date"], 0.0) + p["balance"]

    # Dagens lånesaldo används för alla historiska månader (approximation).
    # För exakt historik skulle vi behöva rekonstruera LoanPayment-summor
    # per datum — skickar det till en framtida version.
    loans = session.query(Loan).filter(Loan.active.is_(True)).all()
    matcher = LoanMatcher(session)
    debt = sum(
        (float(matcher.outstanding_balance(loan)) for loan in loans), 0.0
    )

    points = [
        {
            "date": d,
            "assets": round(totals[d], 2),
            "debt": round(debt, 2),
            "net_worth": round(totals[d] - debt, 2),
        }
        for d in sorted(totals)
    ]
    return {"points": points, "current_debt": round(debt, 2)}
