"""Kredit-API: affordability-check + privatlån + SMS-lån.

Wrappar credit/-domänlogiken med FastAPI-deps. Ren router så
StudentScopeMiddleware automatiskt isolerar per elev.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..credit.affordability import check_affordability
from .deps import db, require_auth


router = APIRouter(
    prefix="/credit",
    tags=["credit"],
    dependencies=[Depends(require_auth)],
)


class AffordabilityIn(BaseModel):
    """Förfrågan: 'om jag drar X kr från konto Y, går det ihop?'"""
    account_id: int
    amount: Decimal = Field(gt=0)
    threshold: Optional[Decimal] = None  # buffert; default 0


class AffordabilityOut(BaseModel):
    ok: bool
    current_balance: float
    threshold: float
    shortfall: float
    explanation: str
    account_kind: str
    # Pedagogiska alternativ när ok=False:
    options: list[str]


@router.post("/check-affordability", response_model=AffordabilityOut)
def affordability(payload: AffordabilityIn, session: Session = Depends(db)) -> AffordabilityOut:
    """Kollar om en planerad transaktion ryms. Returnerar pedagogisk
    förklaring + alternativ om det inte gör det."""
    threshold = payload.threshold or Decimal("0")
    result = check_affordability(
        session,
        account_id=payload.account_id,
        amount=payload.amount,
        threshold=threshold,
    )
    options: list[str] = []
    if not result.ok:
        # Privatlån är förstaval, SMS sista utväg, avbryta alltid sista option
        options = ["private_loan", "sms_loan", "cancel"]
        # Sparkonton kan inte lånas till — då bara cancel
        if result.account_kind in {"savings", "isk", "pension"}:
            options = ["cancel"]
    return AffordabilityOut(
        ok=result.ok,
        current_balance=float(result.current_balance),
        threshold=float(result.threshold),
        shortfall=float(result.shortfall),
        explanation=result.explanation,
        account_kind=result.account_kind,
        options=options,
    )
