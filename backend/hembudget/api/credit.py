"""Kredit-API: affordability-check + privatlån + SMS-lån.

Wrappar credit/-domänlogiken med FastAPI-deps. Ren router så
StudentScopeMiddleware automatiskt isolerar per elev.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..credit.affordability import check_affordability
from ..credit.scoring import (
    annuity_monthly_payment,
    calculate_credit_score,
)
from ..db.models import CreditApplication, Loan, Transaction
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


# ---------- Privatlån ----------

class PrivateLoanApplyIn(BaseModel):
    requested_amount: Decimal = Field(gt=0, le=500_000)
    requested_months: int = Field(ge=12, le=84)
    purpose: Optional[str] = "Oförutsedda utgifter"
    triggered_by_tx_id: Optional[int] = None


class ScoreFactorOut(BaseModel):
    name: str
    points: int
    explanation: str


class PrivateLoanApplyOut(BaseModel):
    application_id: int
    approved: bool
    score: int
    score_threshold: int
    factors: list[ScoreFactorOut]
    simulated_lender: str
    # Vid godkänd:
    offered_rate: Optional[float] = None
    offered_monthly_payment: Optional[float] = None
    offered_total_cost: Optional[float] = None
    offered_total_interest: Optional[float] = None
    # Vid avslag:
    decline_reason: Optional[str] = None
    # Pedagogisk advice oavsett:
    pedagogical_summary: str


def _pedagogical_summary(score, factors, approved: bool, decline: Optional[str]) -> str:
    """En sammanfattande pedagogisk text som binder ihop poängen och
    elevens situation. Ska aldrig 'rekommendera' lånet — bara
    förklara vad scoren betyder."""
    lines = []
    if approved:
        lines.append(
            f"Banken har godkänt din ansökan med kreditscore {score} av 850."
        )
        lines.append(
            "Räntan baseras på din score — högre score = lägre ränta."
        )
    else:
        lines.append(
            f"Banken har tackat nej. Din kreditscore är {score} av 850 — "
            "under deras gräns."
        )
    # Top-3 faktorer (positivt + negativt)
    pos = sorted([f for f in factors if f.points > 0],
                 key=lambda f: -f.points)[:2]
    neg = sorted([f for f in factors if f.points < 0],
                 key=lambda f: f.points)[:2]
    if pos:
        ps = ", ".join(f"{f.name} ({f.points:+d})" for f in pos)
        lines.append(f"För dig talar: {ps}.")
    if neg:
        ns = ", ".join(f"{f.name} ({f.points:+d})" for f in neg)
        lines.append(f"Mot dig talar: {ns}.")
    if not approved and decline:
        lines.append(decline)
    lines.append(
        "Tänk på att hela skulden + räntan ska betalas tillbaka — det "
        "krymper utrymmet i framtida budgetar."
    )
    return "\n\n".join(lines)


@router.post("/private/apply", response_model=PrivateLoanApplyOut)
def private_apply(
    payload: PrivateLoanApplyIn, session: Session = Depends(db),
) -> PrivateLoanApplyOut:
    """Skicka in privatlån-ansökan. Kör scoring och returnerar
    godkännande/avslag — men *skapar inte* lånet ännu. Eleven måste
    explicit acceptera erbjudandet via /credit/private/accept.

    En CreditApplication-rad skapas alltid (audit-spår).
    """
    # student_seed — använd amount + months så det är deterministiskt
    seed = int(payload.requested_amount) * 1000 + payload.requested_months
    result = calculate_credit_score(
        session,
        requested_amount=payload.requested_amount,
        requested_months=payload.requested_months,
        student_seed=seed,
    )

    monthly = None
    total_cost = None
    total_interest = None
    if result.approved and result.offered_rate is not None:
        monthly = annuity_monthly_payment(
            payload.requested_amount,
            result.offered_rate,
            payload.requested_months,
        )
        total_cost = monthly * payload.requested_months
        total_interest = total_cost - payload.requested_amount

    # Logga ansökan
    app_row = CreditApplication(
        kind="private",
        requested_amount=payload.requested_amount,
        requested_months=payload.requested_months,
        purpose=payload.purpose,
        result="approved" if result.approved else "declined",
        score_value=result.score,
        decline_reason=result.decline_reason,
        simulated_lender=result.simulated_lender,
        offered_rate=result.offered_rate,
        offered_monthly_payment=monthly,
        triggered_by_tx_id=payload.triggered_by_tx_id,
        decided_at=datetime.utcnow(),
    )
    session.add(app_row)
    session.flush()

    summary = _pedagogical_summary(
        result.score, result.factors, result.approved, result.decline_reason,
    )

    return PrivateLoanApplyOut(
        application_id=app_row.id,
        approved=result.approved,
        score=result.score,
        score_threshold=result.approval_threshold,
        factors=[
            ScoreFactorOut(name=f.name, points=f.points, explanation=f.explanation)
            for f in result.factors
        ],
        simulated_lender=result.simulated_lender,
        offered_rate=result.offered_rate,
        offered_monthly_payment=float(monthly) if monthly else None,
        offered_total_cost=float(total_cost) if total_cost else None,
        offered_total_interest=float(total_interest) if total_interest else None,
        decline_reason=result.decline_reason,
        pedagogical_summary=summary,
    )


class PrivateLoanAcceptIn(BaseModel):
    application_id: int
    deposit_account_id: int  # Vart pengarna ska sättas in (oftast lönekontot)


class PrivateLoanAcceptOut(BaseModel):
    loan_id: int
    transaction_id: int
    deposited_amount: float
    monthly_payment: float
    interest_rate: float
    months: int
    pedagogical_note: str


@router.post("/private/accept", response_model=PrivateLoanAcceptOut)
def private_accept(
    payload: PrivateLoanAcceptIn, session: Session = Depends(db),
) -> PrivateLoanAcceptOut:
    """Eleven accepterar ett godkänt privatlån-erbjudande. Skapar:
    1. Loan-rad med rätt loan_kind, ränta, amortering
    2. Transaction på lönekontot (+lånebelopp som intäkt)
    3. Uppdaterar CreditApplication.result = 'accepted'
    """
    app_row = session.get(CreditApplication, payload.application_id)
    if app_row is None:
        raise HTTPException(404, "Ansökan saknas")
    if app_row.kind != "private":
        raise HTTPException(400, "Fel ansökningstyp")
    if app_row.result != "approved":
        raise HTTPException(400, "Ansökan är inte godkänd")
    if app_row.resulting_loan_id is not None:
        raise HTTPException(400, "Lånet är redan accepterat")

    monthly = app_row.offered_monthly_payment or annuity_monthly_payment(
        app_row.requested_amount,
        app_row.offered_rate or 0.09,
        app_row.requested_months,
    )

    loan = Loan(
        name=f"Privatlån {app_row.simulated_lender}",
        lender=app_row.simulated_lender or "Bank",
        principal_amount=app_row.requested_amount,
        start_date=date.today(),
        interest_rate=float(app_row.offered_rate or 0.09),
        binding_type="rörlig",
        amortization_monthly=monthly,
        active=True,
        loan_kind="private",
        is_high_cost_credit=False,
        applied_at=app_row.created_at,
        score_at_application=app_row.score_value,
    )
    session.add(loan)
    session.flush()

    # Insättning på elevens valda konto
    import hashlib as _hashlib
    h = _hashlib.sha256(
        f"private-loan-{loan.id}-{datetime.utcnow().isoformat()}".encode()
    ).hexdigest()
    deposit_tx = Transaction(
        account_id=payload.deposit_account_id,
        date=date.today(),
        amount=app_row.requested_amount,
        currency="SEK",
        raw_description=f"Privatlån utbetalning — {app_row.simulated_lender}",
        is_transfer=False,
        hash=h,
    )
    session.add(deposit_tx)
    session.flush()

    app_row.result = "accepted"
    app_row.resulting_loan_id = loan.id
    session.flush()

    note = (
        f"Du har lånat {app_row.requested_amount:.0f} kr av {loan.lender} "
        f"till {float(loan.interest_rate)*100:.1f} % ränta i "
        f"{app_row.requested_months} månader. "
        f"Du betalar {float(monthly):.0f} kr/månad — total kostnad blir "
        f"{float(monthly) * app_row.requested_months:.0f} kr varav räntan "
        f"är {float(monthly) * app_row.requested_months - float(app_row.requested_amount):.0f} kr."
    )

    return PrivateLoanAcceptOut(
        loan_id=loan.id,
        transaction_id=deposit_tx.id,
        deposited_amount=float(app_row.requested_amount),
        monthly_payment=float(monthly),
        interest_rate=float(loan.interest_rate),
        months=app_row.requested_months,
        pedagogical_note=note,
    )


class DeclineIn(BaseModel):
    application_id: int


@router.post("/private/decline")
def private_decline(payload: DeclineIn, session: Session = Depends(db)) -> dict:
    """Eleven tackar nej till ett godkänt erbjudande."""
    app_row = session.get(CreditApplication, payload.application_id)
    if app_row is None:
        raise HTTPException(404, "Ansökan saknas")
    if app_row.result == "approved":
        app_row.result = "rejected"
        app_row.decided_at = datetime.utcnow()
        session.flush()
    return {"ok": True, "application_id": app_row.id, "result": app_row.result}


@router.get("/applications")
def list_applications(session: Session = Depends(db)) -> dict:
    """Lista alla kreditansökningar (audit-spår)."""
    rows = (
        session.query(CreditApplication)
        .order_by(CreditApplication.created_at.desc())
        .all()
    )
    return {
        "applications": [
            {
                "id": r.id,
                "kind": r.kind,
                "requested_amount": float(r.requested_amount),
                "requested_months": r.requested_months,
                "purpose": r.purpose,
                "result": r.result,
                "score_value": r.score_value,
                "simulated_lender": r.simulated_lender,
                "offered_rate": r.offered_rate,
                "offered_monthly_payment": (
                    float(r.offered_monthly_payment)
                    if r.offered_monthly_payment else None
                ),
                "decline_reason": r.decline_reason,
                "resulting_loan_id": r.resulting_loan_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            }
            for r in rows
        ],
        "count": len(rows),
    }
