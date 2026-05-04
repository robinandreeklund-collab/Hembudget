"""Kreditprövning + KALP-beräkning för v2 Lånegivaren-modulen.

Två publika funktioner:
- compute_credit_check(s, profile) → ny CreditCheck-rad sparad
- compute_kalp(s, profile, loan_amount, loan_term_months) → KALPCalculation

Båda läser FAKTISK data från scope-DB (Loan, PaymentMark) + master-DB
(StudentProfile.gross_salary_monthly). Inga schabloner förutom
Konsumentverkets levnadsschablon (faktisk myndighetsdata).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import (
    CreditCheck,
    KALPCalculation,
    Loan,
    PaymentMark,
)
from ..loans.matcher import LoanMatcher


# Konsumentverkets levnadsschablon kr/mån för ensamhushåll 18-25 år
# (2026, exklusive boende). Används i KALP. Källa: konsumentverket.se
# Vi tar approximationen direkt — riktiga siffror seedas i scope-DB
# vid behov.
CONSUMER_BASIC_LIVING_COST_SEK = {
    "ensam": Decimal("8500"),
    "sambo": Decimal("13500"),  # 2 vuxna delar bostadens fasta
    "familj_med_barn": Decimal("16500"),  # 2 vuxna + 1 barn snittvikt
}


def _basic_consumer_cost(family_status: Optional[str]) -> Decimal:
    """Konsumentverkets schablon-levnadskostnad (utan boende)."""
    return CONSUMER_BASIC_LIVING_COST_SEK.get(
        family_status or "ensam",
        CONSUMER_BASIC_LIVING_COST_SEK["ensam"],
    )


def _classify_uc_score(
    debt_ratio: float,
    payment_marks: int,
    running_apps: int,
    annual_income: float,
) -> tuple[str, int]:
    """Mappa till UC-stil A-E + numeriskt värde 0-100.

    Modellen är förenklad men deterministisk:
    - 100 baseline
    - −15 per betalningsanmärkning (max 60)
    - −5 per pågående ansökan över 1
    - −10 om debt_ratio > 4.5 (över FI-tak)
    - −5 om debt_ratio > 3.0
    - −20 om annual_income < 100 000 (instabil inkomst)
    """
    score = 100
    score -= min(60, payment_marks * 15)
    if running_apps > 1:
        score -= 5 * (running_apps - 1)
    if debt_ratio > 4.5:
        score -= 10
    elif debt_ratio > 3.0:
        score -= 5
    if annual_income < 100_000:
        score -= 20
    score = max(0, min(100, score))

    # A-E mapping
    if score >= 80:
        cls = "A"
    elif score >= 60:
        cls = "B"
    elif score >= 40:
        cls = "C"
    elif score >= 20:
        cls = "D"
    else:
        cls = "E"
    return cls, score


def compute_credit_check(
    s: Session,
    annual_income: Decimal,
    running_applications: int = 0,
) -> CreditCheck:
    """Räkna kreditprövning + spara ny CreditCheck-rad.

    annual_income: brutto * 12 från StudentProfile.
    running_applications: antal pågående LoanApplication
    (placeholder — alltid 0 tills LoanApplication-modellen finns).
    """
    today = date.today()

    # Total skuld från aktiva lån
    matcher = LoanMatcher(s)
    active_loans = s.query(Loan).filter(Loan.active.is_(True)).all()
    total_debt = sum(
        (matcher.outstanding_balance(loan) for loan in active_loans),
        Decimal("0"),
    )

    # Aktiva betalningsanmärkningar (ej utgångna)
    marks_count = (
        s.query(_func_count())
        .select_from(PaymentMark)
        .filter(
            (PaymentMark.expires_at.is_(None)) |
            (PaymentMark.expires_at >= today)
        )
        .scalar()
        or 0
    )

    debt_ratio = (
        float(total_debt) / float(annual_income)
        if annual_income > 0 else 0.0
    )
    cls, score = _classify_uc_score(
        debt_ratio=debt_ratio,
        payment_marks=int(marks_count),
        running_apps=running_applications,
        annual_income=float(annual_income),
    )

    check = CreditCheck(
        annual_income=annual_income,
        total_debt=total_debt,
        debt_ratio=Decimal(str(round(debt_ratio, 3))),
        payment_marks_count=int(marks_count),
        running_applications=running_applications,
        uc_score_class=cls,
        uc_score_value=score,
    )
    s.add(check)
    s.flush()
    return check


def latest_credit_check(s: Session) -> Optional[CreditCheck]:
    """Hämta senaste CreditCheck-raden, eller None om ingen finns.

    OBS: SQLite har 1-sekunds resolution på CURRENT_TIMESTAMP, så
    flera rader inom samma sekund får identiska computed_at. Vi
    sorterar därför både på computed_at OCH id för stabil ordning.
    """
    return (
        s.query(CreditCheck)
        .order_by(CreditCheck.computed_at.desc(), CreditCheck.id.desc())
        .first()
    )


def _annuity_payment(principal: Decimal, rate: Decimal, n: int) -> Decimal:
    """Annuitetsbetalning = P · r / (1 − (1 + r)^−n).

    rate = månadsränta (årsränta / 12), n = antal månader.
    """
    if n <= 0:
        return Decimal("0")
    if rate <= 0:
        return principal / Decimal(n)
    one_plus_r_neg_n = (Decimal("1") + rate) ** (-n)
    return principal * rate / (Decimal("1") - one_plus_r_neg_n)


def compute_kalp(
    s: Session,
    monthly_income_net: Decimal,
    family_status: str,
    monthly_housing: Decimal,
    loan_amount: Decimal,
    loan_term_months: int = 300,
    stress_test_rate: Decimal = Decimal("0.07"),
) -> KALPCalculation:
    """Beräkna och spara KALP för ett tänkt lånebelopp.

    Logik:
    1. monthly_consumer = Konsumentverkets levnadsschablon (familjetyp)
    2. existing_debt_payments = summa amortering+ränta på aktiva lån
    3. stress_payment = annuitet på loan_amount vid stress_test_rate
    4. left_after_all = monthly_income_net - housing - consumer
       - existing_debt - stress_payment
    5. passed = left_after_all >= 0 (hen klarar månadskostnaden)
    """
    # Befintliga låne-månadsbetalningar
    active_loans = s.query(Loan).filter(Loan.active.is_(True)).all()
    existing_debt_payments = sum(
        (Decimal(str(loan.amortization_monthly or 0)) for loan in active_loans),
        Decimal("0"),
    )

    consumer_schablon = _basic_consumer_cost(family_status)
    monthly_rate = stress_test_rate / Decimal("12")
    stress_payment = _annuity_payment(
        loan_amount, monthly_rate, loan_term_months,
    ).quantize(Decimal("0.01"))

    left = (
        monthly_income_net
        - monthly_housing
        - consumer_schablon
        - existing_debt_payments
        - stress_payment
    ).quantize(Decimal("0.01"))

    calc = KALPCalculation(
        monthly_income_net=monthly_income_net,
        monthly_housing=monthly_housing,
        monthly_consumer_schablon=consumer_schablon,
        monthly_existing_debt_payments=existing_debt_payments,
        stress_test_rate=stress_test_rate,
        loan_amount=loan_amount,
        loan_term_months=loan_term_months,
        monthly_loan_payment_at_stress=stress_payment,
        monthly_left_after_all=left,
        passed=left >= 0,
    )
    s.add(calc)
    s.flush()
    return calc


def latest_kalp(s: Session) -> Optional[KALPCalculation]:
    return (
        s.query(KALPCalculation)
        .order_by(
            KALPCalculation.computed_at.desc(),
            KALPCalculation.id.desc(),
        )
        .first()
    )


def _func_count():
    """SQLAlchemy COUNT(*) — wrapper så vi inte behöver importera func
    på flera ställen."""
    return func.count()
