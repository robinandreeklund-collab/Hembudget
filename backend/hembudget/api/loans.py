from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..db.models import Loan, LoanPayment, Transaction
from ..loans.matcher import LoanMatcher
from .deps import db, require_auth

router = APIRouter(prefix="/loans", tags=["loans"], dependencies=[Depends(require_auth)])


class LoanIn(BaseModel):
    name: str
    lender: str
    loan_number: Optional[str] = None
    principal_amount: Decimal
    start_date: date
    interest_rate: float
    binding_type: str = "rörlig"
    binding_end_date: Optional[date] = None
    amortization_monthly: Optional[Decimal] = None
    property_value: Optional[Decimal] = None
    match_pattern: Optional[str] = None
    notes: Optional[str] = None


class LoanUpdate(BaseModel):
    name: Optional[str] = None
    lender: Optional[str] = None
    loan_number: Optional[str] = None
    principal_amount: Optional[Decimal] = None
    start_date: Optional[date] = None
    interest_rate: Optional[float] = None
    binding_type: Optional[str] = None
    binding_end_date: Optional[date] = None
    amortization_monthly: Optional[Decimal] = None
    property_value: Optional[Decimal] = None
    match_pattern: Optional[str] = None
    notes: Optional[str] = None
    active: Optional[bool] = None


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    lender: str
    loan_number: Optional[str]
    principal_amount: Decimal
    start_date: date
    interest_rate: float
    binding_type: str
    binding_end_date: Optional[date]
    amortization_monthly: Optional[Decimal]
    property_value: Optional[Decimal]
    match_pattern: Optional[str]
    notes: Optional[str]
    active: bool


class LoanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    lender: str
    principal_amount: Decimal
    outstanding_balance: Decimal
    amortization_paid: Decimal
    interest_paid: Decimal
    interest_rate: float
    binding_type: str
    binding_end_date: Optional[date]
    ltv: Optional[float] = None     # balance / property_value
    payments_count: int


@router.get("/", response_model=list[LoanOut])
def list_loans(session: Session = Depends(db)) -> list[Loan]:
    return session.query(Loan).order_by(Loan.id).all()


@router.post("/", response_model=LoanOut)
def create_loan(payload: LoanIn, session: Session = Depends(db)) -> Loan:
    loan = Loan(**payload.model_dump())
    session.add(loan)
    session.flush()
    # Match existing transactions against the new loan
    txs = session.query(Transaction).filter(Transaction.amount < 0).all()
    LoanMatcher(session).match_and_classify(txs)
    return loan


@router.patch("/{loan_id}", response_model=LoanOut)
def update_loan(loan_id: int, payload: LoanUpdate, session: Session = Depends(db)) -> Loan:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(loan, k, v)
    session.flush()
    if payload.match_pattern is not None:
        txs = session.query(Transaction).filter(Transaction.amount < 0).all()
        LoanMatcher(session).match_and_classify(txs)
    return loan


@router.delete("/{loan_id}")
def delete_loan(loan_id: int, session: Session = Depends(db)) -> dict:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    # Remove associated payment links (not the underlying transactions)
    session.query(LoanPayment).filter(LoanPayment.loan_id == loan_id).delete()
    session.delete(loan)
    return {"deleted": loan_id}


@router.get("/{loan_id}/summary", response_model=LoanSummary)
def loan_summary(loan_id: int, session: Session = Depends(db)) -> LoanSummary:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    m = LoanMatcher(session)
    balance = m.outstanding_balance(loan)
    interest = m.total_interest_paid(loan)
    amortized = loan.principal_amount - balance
    count = session.query(LoanPayment).filter(LoanPayment.loan_id == loan.id).count()
    ltv = None
    if loan.property_value and loan.property_value > 0:
        ltv = float(balance / loan.property_value)
    return LoanSummary(
        id=loan.id,
        name=loan.name,
        lender=loan.lender,
        principal_amount=loan.principal_amount,
        outstanding_balance=balance,
        amortization_paid=amortized,
        interest_paid=interest,
        interest_rate=loan.interest_rate,
        binding_type=loan.binding_type,
        binding_end_date=loan.binding_end_date,
        ltv=ltv,
        payments_count=count,
    )


@router.get("/summaries/all", response_model=list[LoanSummary])
def all_summaries(session: Session = Depends(db)) -> list[LoanSummary]:
    loans = session.query(Loan).filter(Loan.active.is_(True)).all()
    out: list[LoanSummary] = []
    m = LoanMatcher(session)
    for loan in loans:
        balance = m.outstanding_balance(loan)
        interest = m.total_interest_paid(loan)
        amortized = loan.principal_amount - balance
        count = session.query(LoanPayment).filter(LoanPayment.loan_id == loan.id).count()
        ltv = None
        if loan.property_value and loan.property_value > 0:
            ltv = float(balance / loan.property_value)
        out.append(LoanSummary(
            id=loan.id, name=loan.name, lender=loan.lender,
            principal_amount=loan.principal_amount,
            outstanding_balance=balance, amortization_paid=amortized,
            interest_paid=interest, interest_rate=loan.interest_rate,
            binding_type=loan.binding_type, binding_end_date=loan.binding_end_date,
            ltv=ltv, payments_count=count,
        ))
    return out


@router.get("/{loan_id}/payments")
def list_payments(loan_id: int, session: Session = Depends(db)) -> dict:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    rows = (
        session.query(LoanPayment)
        .filter(LoanPayment.loan_id == loan_id)
        .order_by(LoanPayment.date.asc())
        .all()
    )
    return {
        "payments": [
            {
                "id": p.id,
                "date": p.date.isoformat(),
                "amount": float(p.amount),
                "type": p.payment_type,
                "transaction_id": p.transaction_id,
            }
            for p in rows
        ]
    }


@router.post("/rescan")
def rescan(session: Session = Depends(db)) -> dict:
    """Kör om matchning mot alla historiska transaktioner."""
    # Wipe existing links so pattern changes take effect
    session.query(LoanPayment).delete()
    session.flush()
    txs = session.query(Transaction).filter(Transaction.amount < 0).all()
    r = LoanMatcher(session).match_and_classify(txs)
    return {"linked": r.linked, "unclassified": r.unclassified}
