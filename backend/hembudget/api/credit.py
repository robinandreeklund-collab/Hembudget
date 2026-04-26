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
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..credit.affordability import check_affordability
from ..credit.scoring import (
    annuity_monthly_payment,
    calculate_credit_score,
)
from ..db.models import Account, CreditApplication, Loan, Transaction
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


# ---------- SMS-lån (sista utväg) ----------
#
# SMS-lån är medvetet *enkelt att få* men *väldigt dyrt*. Pedagogiken
# är att eleven ska se konsekvenserna i klartext innan acceptans —
# inte att vi ska göra det svårt att ta lånet (det är inte verkligheten).

SMS_LENDERS = ["Klarna Quick", "Bynk", "Cashbuddy", "GF Money"]
# Effektiv ränta beror på avgifter + nominell ränta. Vi simulerar
# realistiskt: nominell ~30 % årligen + uppläggningsavgift + aviavgift.
SMS_NOMINAL_RATE = 0.30
SMS_SETUP_FEE = Decimal("500")
SMS_AVI_FEE_PER_MONTH = Decimal("50")


def _sms_total_cost(amount: Decimal, months: int) -> tuple[Decimal, Decimal, Decimal, float]:
    """Returnera (total, ränta_kr, total_avgifter, effektiv_ränta_årlig)."""
    # Beräkna ränta på principal under perioden (förenklat — riktiga
    # SMS-lån räknar på utestående saldo men vi gör det rakare).
    interest_part = amount * Decimal(str(SMS_NOMINAL_RATE)) * Decimal(months) / Decimal("12")
    avi = SMS_AVI_FEE_PER_MONTH * months
    fees = SMS_SETUP_FEE + avi
    total = amount + interest_part + fees
    # Effektiv ränta = (total/amount)^(12/months) − 1, annualiserat
    if amount > 0 and months > 0:
        ratio = float(total / amount)
        eff = (ratio ** (12.0 / months) - 1.0)
    else:
        eff = 0.0
    return total.quantize(Decimal("0.01")), interest_part.quantize(Decimal("0.01")), fees.quantize(Decimal("0.01")), eff


def _sms_lender(student_seed: int, amount: Decimal) -> str:
    import hashlib as _hashlib
    key = f"sms-{student_seed}-{int(amount)}"
    h = int(_hashlib.sha256(key.encode()).hexdigest()[:8], 16)
    return SMS_LENDERS[h % len(SMS_LENDERS)]


class SmsApplyIn(BaseModel):
    requested_amount: Decimal = Field(ge=1_000, le=30_000)
    requested_months: int = Field(ge=1, le=3)  # 1, 2, eller 3 månader
    triggered_by_tx_id: Optional[int] = None


class SmsApplyOut(BaseModel):
    application_id: int
    approved: bool
    simulated_lender: str
    nominal_rate: float
    effective_rate: float
    setup_fee: float
    avi_fee_per_month: float
    months: int
    requested_amount: float
    total_to_pay: float
    interest_kr: float
    total_fees: float
    pedagogical_warning: str


@router.post("/sms/apply", response_model=SmsApplyOut)
def sms_apply(payload: SmsApplyIn, session: Session = Depends(db)) -> SmsApplyOut:
    """SMS-lån: snabb, dyr kredit. Auto-godkänd så länge inkomsten är
    >0 (annars skulle ingen vilja låna ut). Eleven ska se den
    effektiva räntan + total kostnad innan acceptans."""
    # Vi godkänner alltid om eleven har någon lön (rimlig minimum-
    # spärr så det inte blir absurt). I verkligheten ger SMS-lånare
    # nästan alltid OK — det är just det som gör dem farliga.
    income = (
        session.query(sa_func.coalesce(sa_func.sum(Transaction.amount), 0))
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.type == "checking",
            Transaction.amount >= Decimal("5000"),
            Transaction.is_transfer.is_(False),
        )
        .scalar() or Decimal("0")
    )
    if not isinstance(income, Decimal):
        income = Decimal(str(income))
    approved = income > 0

    seed = int(payload.requested_amount) * 100 + payload.requested_months
    lender = _sms_lender(seed, payload.requested_amount)

    total, interest_kr, total_fees, eff_rate = _sms_total_cost(
        payload.requested_amount, payload.requested_months,
    )

    # Pedagogisk varning som visas ordagrant
    warning = (
        f"⚠️ DETTA ÄR DYR KREDIT.\n"
        f"Du lånar {payload.requested_amount:.0f} kr, men ska "
        f"betala tillbaka {total:.0f} kr på {payload.requested_months} "
        f"månader. Effektiv ränta: {eff_rate*100:.0f} %.\n\n"
        f"För att jämföra: ett vanligt privatlån på samma belopp i "
        f"24 månader hade kostat ungefär {payload.requested_amount * Decimal('1.08'):.0f} kr totalt — "
        f"alltså ~{(total - payload.requested_amount * Decimal('1.08')):.0f} kr mindre.\n\n"
        f"SMS-lån är vettigt bara om du är 100 % säker på att kunna "
        f"betala tillbaka i tid. Missade betalningar leder till "
        f"inkasso och betalningsanmärkning."
    )

    app_row = CreditApplication(
        kind="sms",
        requested_amount=payload.requested_amount,
        requested_months=payload.requested_months,
        purpose="Sista utväg",
        result="approved" if approved else "declined",
        score_value=None,  # SMS-lån har ingen score
        decline_reason=None if approved else "Vi hittar ingen inkomst.",
        simulated_lender=lender,
        offered_rate=SMS_NOMINAL_RATE,
        offered_monthly_payment=(total / payload.requested_months).quantize(Decimal("0.01")),
        triggered_by_tx_id=payload.triggered_by_tx_id,
        decided_at=datetime.utcnow(),
    )
    session.add(app_row)
    session.flush()

    return SmsApplyOut(
        application_id=app_row.id,
        approved=approved,
        simulated_lender=lender,
        nominal_rate=SMS_NOMINAL_RATE,
        effective_rate=eff_rate,
        setup_fee=float(SMS_SETUP_FEE),
        avi_fee_per_month=float(SMS_AVI_FEE_PER_MONTH),
        months=payload.requested_months,
        requested_amount=float(payload.requested_amount),
        total_to_pay=float(total),
        interest_kr=float(interest_kr),
        total_fees=float(total_fees),
        pedagogical_warning=warning,
    )


class SmsAcceptIn(BaseModel):
    application_id: int
    deposit_account_id: int


class SmsAcceptOut(BaseModel):
    loan_id: int
    transaction_id: int
    deposited_amount: float
    total_to_pay: float
    months: int
    pedagogical_note: str


@router.post("/sms/accept", response_model=SmsAcceptOut)
def sms_accept(payload: SmsAcceptIn, session: Session = Depends(db)) -> SmsAcceptOut:
    """Eleven accepterar SMS-lånet. Skapar Loan med is_high_cost_credit=True."""
    app_row = session.get(CreditApplication, payload.application_id)
    if app_row is None:
        raise HTTPException(404, "Ansökan saknas")
    if app_row.kind != "sms":
        raise HTTPException(400, "Fel ansökningstyp")
    if app_row.result != "approved":
        raise HTTPException(400, "Ansökan är inte godkänd")
    if app_row.resulting_loan_id is not None:
        raise HTTPException(400, "Lånet är redan accepterat")

    total, interest_kr, total_fees, _ = _sms_total_cost(
        app_row.requested_amount, app_row.requested_months,
    )
    monthly = (total / app_row.requested_months).quantize(Decimal("0.01"))

    loan = Loan(
        name=f"SMS-lån {app_row.simulated_lender}",
        lender=app_row.simulated_lender or "Snabblån",
        principal_amount=app_row.requested_amount,
        start_date=date.today(),
        interest_rate=float(app_row.offered_rate or SMS_NOMINAL_RATE),
        binding_type="rörlig",
        amortization_monthly=monthly,
        active=True,
        loan_kind="sms",
        is_high_cost_credit=True,
        applied_at=app_row.created_at,
    )
    session.add(loan)
    session.flush()

    import hashlib as _hashlib
    h = _hashlib.sha256(
        f"sms-loan-{loan.id}-{datetime.utcnow().isoformat()}".encode()
    ).hexdigest()
    deposit_tx = Transaction(
        account_id=payload.deposit_account_id,
        date=date.today(),
        amount=app_row.requested_amount,
        currency="SEK",
        raw_description=f"SMS-lån utbetalning — {app_row.simulated_lender}",
        is_transfer=False,
        hash=h,
    )
    session.add(deposit_tx)
    session.flush()

    app_row.result = "accepted"
    app_row.resulting_loan_id = loan.id
    session.flush()

    note = (
        f"Du har tagit ett SMS-lån på {app_row.requested_amount:.0f} kr.\n\n"
        f"Du ska betala tillbaka {total:.0f} kr på "
        f"{app_row.requested_months} månader — det är "
        f"{total - app_row.requested_amount:.0f} kr mer än vad du lånade.\n\n"
        f"Reflektion: hur hamnade du här? Vad kunde du gjort annorlunda? "
        f"Ett buffertsparande på ungefär en månadslön hade troligen "
        f"räckt för att slippa det här lånet."
    )

    return SmsAcceptOut(
        loan_id=loan.id,
        transaction_id=deposit_tx.id,
        deposited_amount=float(app_row.requested_amount),
        total_to_pay=float(total),
        months=app_row.requested_months,
        pedagogical_note=note,
    )


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
