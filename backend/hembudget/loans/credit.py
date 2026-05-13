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
    *,
    age: int | None = None,
    monthly_net: int | None = None,
    family_status: str | None = None,
    housing_type: str | None = None,
    months_on_platform: int = 0,
    savings_buffer_months: float = 0.0,
) -> tuple[str, int]:
    """Realistisk UC-stil-bedömning · A-E + 0-100.

    Tidigare formel hade base 100 och drog bara små poäng vid problem.
    Resultat: alla elever fick A (100/100) trots att en 22-årig fresh-
    graduate utan kreditshistorik IRL skulle få C/D av en bank.

    Ny formel speglar verkliga UC-faktorer:
    - **Ålder + anställningstid** (proxy via age)
    - **Inkomstnivå** (band, inte cliff)
    - **Familjestatus** (stabilitet)
    - **Boendetyp** (BR/villa = etablerad)
    - **Befintliga lån / skuldkvot**
    - **Betalningsanmärkningar** (kraftigt straff)
    - **Pågående ansökningar** (många = oroande)
    - **Tid på plattformen** (= "tid sedan ansökan startade IRL")

    Vi använder samma viktning som school/credit_scoring.py::compute_score
    men exponerar bara A-E + 0-100 till caller eftersom CreditCheck-modellen
    förväntar det formatet.
    """
    from ..school.credit_scoring import compute_score, MIN_SCORE, MAX_SCORE
    # Mappa till compute_score-inputs. Bristfälliga args (None) hanteras
    # av compute_score genom att hoppa över respektive faktor.
    res = compute_score(
        late_payments=payment_marks,  # treat marks som late_payments
        failed_payments=0,
        reminders_l3_or_higher=payment_marks,  # marks räknas som L3+
        debt_ratio=debt_ratio,
        savings_buffer_months=savings_buffer_months,
        satisfaction_score=70,  # neutralt default
        months_on_platform=months_on_platform,
        age=age,
        monthly_net_income=monthly_net,
        family_status=family_status,
        housing_type=housing_type,
    )
    # Extra straff för många pågående ansökningar (UC-spår)
    score_300_850 = res.score
    if running_apps > 1:
        score_300_850 -= 8 * (running_apps - 1)
    score_300_850 = max(MIN_SCORE, min(MAX_SCORE, score_300_850))

    # Mappa 300-850 → 0-100 (verklig UC-skala)
    score_0_100 = int(round((score_300_850 - MIN_SCORE) * 100 / (MAX_SCORE - MIN_SCORE)))
    score_0_100 = max(0, min(100, score_0_100))

    # A-E mapping baserad på 0-100. Mer realistisk än tidigare:
    # - A: 80+ (utmärkt, etablerad)
    # - B: 60-79 (bra)
    # - C: 40-59 (medel — vad de flesta unga vuxna får)
    # - D: 20-39 (sämre — fresh-graduate ofta hamnar här)
    # - E: <20 (problematisk)
    if score_0_100 >= 80:
        cls = "A"
    elif score_0_100 >= 60:
        cls = "B"
    elif score_0_100 >= 40:
        cls = "C"
    elif score_0_100 >= 20:
        cls = "D"
    else:
        cls = "E"
    return cls, score_0_100


def compute_credit_check(
    s: Session,
    annual_income: Decimal,
    running_applications: int = 0,
    *,
    student_id: int | None = None,
) -> CreditCheck:
    """Räkna kreditprövning + spara ny CreditCheck-rad.

    annual_income: brutto * 12 från StudentProfile.
    running_applications: antal pågående LoanApplication.
    student_id: om angivet hämtas StudentProfile + Student.created_at
                från master-DB så ålder/familj/boende/tid-på-platform
                kan användas i scoring (verkligare UC-bedömning).
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

    # Sparbuffer = (sparkonto + ISK) / snittutgifter senaste 3 mån
    # Påverkar UC-score realistiskt: en 22-åring med 1-2 mån buffert
    # får C/D istället för E.
    savings_buffer_months = 0.0
    try:
        from ..db.models import Account, Transaction
        from sqlalchemy import func as _sf_uc
        from datetime import date as _d_uc, timedelta as _td_uc
        savings_balance = Decimal("0")
        for acc in s.query(Account).filter(
            Account.type.in_(("savings", "isk"))
        ).all():
            ob = acc.opening_balance or Decimal("0")
            mv = s.query(
                _sf_uc.coalesce(_sf_uc.sum(Transaction.amount), 0),
            ).filter(Transaction.account_id == acc.id).scalar() or Decimal("0")
            savings_balance += ob + Decimal(str(mv))
        cutoff = _d_uc.today() - _td_uc(days=90)
        expenses = s.query(
            _sf_uc.coalesce(_sf_uc.sum(Transaction.amount), 0),
        ).filter(
            Transaction.amount < 0,
            Transaction.date >= cutoff,
        ).scalar() or 0
        avg_monthly_expense = abs(Decimal(str(expenses))) / 3 or Decimal("1")
        savings_buffer_months = (
            float(savings_balance / avg_monthly_expense)
            if avg_monthly_expense > 0 else 0.0
        )
    except Exception:
        pass

    # Hämta livssituations-faktorer för realistisk UC-bedömning
    age = None
    monthly_net = None
    family_status = None
    housing_type = None
    months_on_platform = 0
    if student_id is not None:
        try:
            from ..school.engines import master_session
            from ..school.models import Student, StudentProfile
            from datetime import datetime as _dt_uc
            with master_session() as ms:
                profile = (
                    ms.query(StudentProfile)
                    .filter(StudentProfile.student_id == student_id)
                    .first()
                )
                if profile is not None:
                    age = profile.age
                    monthly_net = profile.net_salary_monthly
                    family_status = profile.family_status
                    housing_type = profile.housing_type
                stu = ms.get(Student, student_id)
                if stu is not None and stu.created_at is not None:
                    months_on_platform = (
                        _dt_uc.utcnow() - stu.created_at
                    ).days // 30
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "compute_credit_check: kunde inte hämta profil-data",
            )

    cls, score = _classify_uc_score(
        debt_ratio=debt_ratio,
        payment_marks=int(marks_count),
        running_apps=running_applications,
        annual_income=float(annual_income),
        age=age,
        monthly_net=monthly_net,
        family_status=family_status,
        housing_type=housing_type,
        months_on_platform=months_on_platform,
        savings_buffer_months=savings_buffer_months,
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
