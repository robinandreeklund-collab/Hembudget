from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..db.models import Loan, LoanPayment, LoanScheduleEntry, Transaction
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
    # Rensa tidigare länkar så att mönster- och schemaändringar slår igenom
    session.query(LoanPayment).delete()
    session.query(LoanScheduleEntry).filter(
        LoanScheduleEntry.matched_transaction_id.is_not(None)
    ).update({"matched_transaction_id": None, "matched_at": None})
    session.flush()
    txs = session.query(Transaction).filter(Transaction.amount < 0).all()
    r = LoanMatcher(session).match_and_classify(txs)
    return {
        "linked": r.linked,
        "unclassified": r.unclassified,
        "matched_via_schedule": r.matched_via_schedule,
        "matched_via_pattern": r.matched_via_pattern,
    }


# ----- Schema / planerade betalningar -----

class ScheduleEntryIn(BaseModel):
    due_date: date
    amount: Decimal
    payment_type: str  # "interest" | "amortization"
    notes: Optional[str] = None


class ScheduleEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    loan_id: int
    due_date: date
    amount: Decimal
    payment_type: str
    matched_transaction_id: Optional[int]
    notes: Optional[str]


@router.get("/{loan_id}/schedule", response_model=list[ScheduleEntryOut])
def list_schedule(loan_id: int, session: Session = Depends(db)) -> list[LoanScheduleEntry]:
    return (
        session.query(LoanScheduleEntry)
        .filter(LoanScheduleEntry.loan_id == loan_id)
        .order_by(LoanScheduleEntry.due_date.asc())
        .all()
    )


@router.post("/{loan_id}/schedule", response_model=ScheduleEntryOut)
def create_schedule_entry(
    loan_id: int,
    payload: ScheduleEntryIn,
    session: Session = Depends(db),
) -> LoanScheduleEntry:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    if payload.payment_type not in ("interest", "amortization"):
        raise HTTPException(400, "payment_type must be 'interest' or 'amortization'")
    entry = LoanScheduleEntry(
        loan_id=loan_id,
        due_date=payload.due_date,
        amount=payload.amount,
        payment_type=payload.payment_type,
        notes=payload.notes,
    )
    session.add(entry)
    session.flush()
    # Kör matcher så nya schemaraden kan plocka upp befintliga transaktioner
    txs = session.query(Transaction).filter(Transaction.amount < 0).all()
    LoanMatcher(session).match_and_classify(txs)
    return entry


@router.delete("/{loan_id}/schedule/{entry_id}")
def delete_schedule_entry(
    loan_id: int, entry_id: int, session: Session = Depends(db)
) -> dict:
    entry = session.get(LoanScheduleEntry, entry_id)
    if entry is None or entry.loan_id != loan_id:
        raise HTTPException(404, "Schedule entry not found")
    # Rensa kopplade LoanPayment om schemat matchade en transaktion
    if entry.matched_transaction_id:
        session.query(LoanPayment).filter(
            LoanPayment.transaction_id == entry.matched_transaction_id,
            LoanPayment.loan_id == loan_id,
        ).delete()
    session.delete(entry)
    return {"deleted": entry_id}


class ScheduleGenerateIn(BaseModel):
    months: int = 3
    day_of_month: Optional[int] = None


@router.post("/{loan_id}/schedule/generate", response_model=list[ScheduleEntryOut])
def generate_schedule(
    loan_id: int,
    payload: ScheduleGenerateIn,
    session: Session = Depends(db),
) -> list[LoanScheduleEntry]:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    m = LoanMatcher(session)
    entries = m.generate_schedule(
        loan, months=payload.months, day_of_month=payload.day_of_month
    )
    # Direkt-matcha mot befintliga transaktioner
    txs = session.query(Transaction).filter(Transaction.amount < 0).all()
    m.match_and_classify(txs)
    return entries
