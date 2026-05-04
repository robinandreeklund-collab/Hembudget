"""Simulerad kreditupplysning för pedagogisk användning.

Beräknar en kreditscore (300–850, lik UC/Bisnode) baserat på elevens
ekonomi i scope-DB:n. Returnerar deterministiskt resultat med
pedagogisk förklaring av varje viktningsfaktor — eleven ska kunna
förstå *varför* hen blev godkänd eller nekad.

Skala (interna trösklar):
  >= 600  → godkänns med bästa ränta (4 %)
  550-599 → godkänns med medelränta (6.5 %)
  500-549 → godkänns med hög ränta (9 %)
  < 500   → AVSLAG

(SMS-lån går utanför detta — har egen logik.)
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..db.models import Account, CreditApplication, Loan, Transaction


# Banker som "konkurrerar" — varje gång eleven söker väljs en
# deterministiskt baserat på student+månad+belopp så två elever som
# söker samma sak får samma bank.
SIMULATED_LENDERS = ["SEB", "Avanza", "SBAB", "Nordnet"]


@dataclass
class ScoreFactor:
    """En enskild viktningsfaktor med pedagogisk förklaring."""
    name: str           # "Inkomst", "Skuldkvot", osv
    points: int         # +/- bidrag till scoren
    explanation: str    # Pedagogisk text till eleven


@dataclass
class CreditScoreResult:
    score: int
    base: int = 600
    factors: list[ScoreFactor] = field(default_factory=list)
    approved: bool = False
    approval_threshold: int = 500
    offered_rate: Optional[float] = None       # 0.04, 0.065, 0.09
    decline_reason: Optional[str] = None
    simulated_lender: str = ""


def _avg_monthly_income(session: Session, *, months: int = 3) -> Decimal:
    """Snittinkomst per månad senaste N månader. Räknar transaktioner
    >= 5000 kr på checking-konton (rimlig löneminimi)."""
    cutoff = date.today() - timedelta(days=30 * months)
    q = (
        session.query(sa_func.sum(Transaction.amount))
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Account.type == "checking",
            Transaction.amount >= Decimal("5000"),
            Transaction.date >= cutoff,
            Transaction.is_transfer.is_(False),
        )
    )
    total = q.scalar() or Decimal("0")
    if not isinstance(total, Decimal):
        total = Decimal(str(total))
    return (total / Decimal(str(months))).quantize(Decimal("0.01"))


def _total_active_debt(session: Session) -> Decimal:
    """Summa principal_amount på alla aktiva lån."""
    total = (
        session.query(sa_func.coalesce(sa_func.sum(Loan.principal_amount), 0))
        .filter(Loan.active.is_(True))
        .scalar() or Decimal("0")
    )
    return Decimal(str(total)) if not isinstance(total, Decimal) else total


def _savings_buffer(session: Session) -> Decimal:
    """Saldo på alla sparkonton + ISK (tillgänglig buffert)."""
    accs = (
        session.query(Account)
        .filter(Account.type.in_({"savings", "isk"}))
        .all()
    )
    total = Decimal("0")
    for acc in accs:
        base = acc.opening_balance or Decimal("0")
        q = session.query(
            sa_func.coalesce(sa_func.sum(Transaction.amount), 0),
        ).filter(Transaction.account_id == acc.id)
        if acc.opening_balance_date is not None:
            q = q.filter(Transaction.date >= acc.opening_balance_date)
        movement = q.scalar() or Decimal("0")
        if not isinstance(movement, Decimal):
            movement = Decimal(str(movement))
        total += base + movement
    return total


def _recent_loan_count(session: Session, *, months: int = 6) -> int:
    """Antal lån tagna senaste N månader. Många nya lån är red flag."""
    cutoff = date.today() - timedelta(days=30 * months)
    return (
        session.query(Loan)
        .filter(Loan.start_date >= cutoff, Loan.active.is_(True))
        .count()
    )


def _previous_declines_this_month(session: Session) -> int:
    """Antal avslag senaste 30 dagar — ökat avslagsantal sänker score."""
    cutoff = date.today() - timedelta(days=30)
    return (
        session.query(CreditApplication)
        .filter(
            CreditApplication.created_at >= cutoff,
            CreditApplication.result == "declined",
        )
        .count()
    )


def _pick_lender(student_seed: int, requested_amount: Decimal) -> str:
    """Deterministisk bank baserat på student+belopp."""
    key = f"{student_seed}-{int(requested_amount)}"
    h = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
    return SIMULATED_LENDERS[h % len(SIMULATED_LENDERS)]


def _format_kr(d: Decimal) -> str:
    return f"{int(d):,}".replace(",", " ") + " kr"


def calculate_credit_score(
    session: Session,
    *,
    requested_amount: Decimal,
    requested_months: int,
    student_seed: int = 0,
) -> CreditScoreResult:
    """Beräknar kreditscore med pedagogisk uppdelning per faktor.

    Algoritmen är medvetet *transparent* och *deterministisk* — eleven
    ska kunna se exakt vilken faktor som drog ner scoren och göra
    något åt det till nästa månad.
    """
    factors: list[ScoreFactor] = []
    base = 600
    score = base

    # 1. INKOMST (snittlön senaste 3 mån)
    income = _avg_monthly_income(session)
    if income <= 0:
        income_pts = -50
        income_msg = (
            "Vi hittar ingen lön på dina konton. Banker vill se "
            "regelbunden inkomst innan de lånar ut."
        )
    elif income < 15_000:
        income_pts = -30
        income_msg = (
            f"Din snittinkomst är {_format_kr(income)}/mån — under "
            "den nivå banker brukar kräva (15 000 kr/mån)."
        )
    elif income < 25_000:
        income_pts = 10
        income_msg = (
            f"Din snittinkomst {_format_kr(income)}/mån är OK men "
            "inte hög — det ger små marginaler."
        )
    else:
        income_pts = 30
        income_msg = (
            f"Din snittinkomst {_format_kr(income)}/mån är god — "
            "banker ser dig som låntagare med stabil betalningsförmåga."
        )
    score += income_pts
    factors.append(ScoreFactor("Inkomst", income_pts, income_msg))

    # 2. SKULDKVOT (befintliga lån / årsinkomst)
    total_debt = _total_active_debt(session)
    annual_income = income * 12 if income > 0 else Decimal("1")
    debt_ratio = float(total_debt / annual_income) if annual_income > 0 else 99
    if debt_ratio > 5:
        debt_pts = -80
        debt_msg = (
            f"Din skuldkvot är {debt_ratio:.1f}x årsinkomsten "
            f"({_format_kr(total_debt)} i lån). Banker oroar sig om "
            "den passerar 4–5x."
        )
    elif debt_ratio > 3:
        debt_pts = -30
        debt_msg = (
            f"Skuldkvot {debt_ratio:.1f}x årsinkomsten — hög men "
            "inte avskräckande."
        )
    elif debt_ratio > 1:
        debt_pts = 0
        debt_msg = (
            f"Skuldkvot {debt_ratio:.1f}x — normal nivå för någon "
            "med bolån."
        )
    else:
        debt_pts = 20
        debt_msg = "Du har låg skuldkvot — fördel vid kreditbedömning."
    score += debt_pts
    factors.append(ScoreFactor("Skuldkvot", debt_pts, debt_msg))

    # 3. SPARANDE / BUFFERT
    savings = _savings_buffer(session)
    if savings < 5_000:
        sav_pts = -10
        sav_msg = (
            f"Du har {_format_kr(savings)} i buffert — knappt något "
            "att möta oväntade utgifter med."
        )
    elif savings < 25_000:
        sav_pts = 10
        sav_msg = (
            f"Buffert: {_format_kr(savings)}. Räcker för en "
            "tand-räkning men inte mycket mer."
        )
    else:
        sav_pts = 20
        sav_msg = (
            f"Buffert: {_format_kr(savings)} — gott tecken på att "
            "du redan sparar."
        )
    score += sav_pts
    factors.append(ScoreFactor("Sparkonto/buffert", sav_pts, sav_msg))

    # 4. NYLIGA LÅN
    recent = _recent_loan_count(session)
    if recent >= 2:
        rec_pts = -40
        rec_msg = (
            f"Du har tagit {recent} lån senaste halvåret. Banker "
            "tolkar det som att ekonomin är ansträngd."
        )
    elif recent == 1:
        rec_pts = -10
        rec_msg = "Ett nyligt lån — påverkar lite men inte mycket."
    else:
        rec_pts = 5
        rec_msg = "Inga nya lån senaste halvåret — bra signal."
    score += rec_pts
    factors.append(ScoreFactor("Nyliga lån", rec_pts, rec_msg))

    # 5. TIDIGARE AVSLAG denna månad
    declines = _previous_declines_this_month(session)
    if declines > 0:
        dec_pts = -20 * declines
        dec_msg = (
            f"Du har {declines} tidigare avslag senaste 30 dagarna. "
            "Många banker delar avslag mellan sig (UC-spår)."
        )
        score += dec_pts
        factors.append(ScoreFactor("Tidigare avslag", dec_pts, dec_msg))

    # 6. STORLEK PÅ ANSÖKAN vs INKOMST
    if income > 0:
        amount_to_income = float(requested_amount / income)
        if amount_to_income > 6:
            size_pts = -30
            size_msg = (
                f"Du söker {_format_kr(requested_amount)} — det är "
                f"{amount_to_income:.1f}x månadsinkomsten. Stora "
                "ansökningar får hårdare bedömning."
            )
        elif amount_to_income > 3:
            size_pts = -10
            size_msg = (
                f"Beloppet ({_format_kr(requested_amount)}) är "
                f"{amount_to_income:.1f}x din månadsinkomst — rimligt."
            )
        else:
            size_pts = 5
            size_msg = "Beloppet är väl avvägt mot din inkomst."
        score += size_pts
        factors.append(ScoreFactor("Lånebelopp", size_pts, size_msg))

    # 7. Deterministiskt slumpinslag (±15)
    seed_key = f"{student_seed}-{int(requested_amount)}-{requested_months}"
    h = int(hashlib.sha256(seed_key.encode()).hexdigest()[:8], 16)
    rand_pts = (h % 31) - 15  # -15 .. +15
    score += rand_pts
    # Vi visar inte denna faktor till eleven — det skulle förvirra.

    # Klamp
    score = max(300, min(850, score))

    # AVGÖRANDE
    threshold = 500
    if score >= 600:
        rate = 0.04
        approved = True
        decline = None
    elif score >= 550:
        rate = 0.065
        approved = True
        decline = None
    elif score >= 500:
        rate = 0.09
        approved = True
        decline = None
    else:
        rate = None
        approved = False
        decline = (
            f"Din kreditscore ({score}) ligger under bankens gräns "
            f"({threshold}). De största faktorerna mot dig är: "
        )
        worst = sorted(factors, key=lambda f: f.points)[:2]
        decline += "; ".join(f"{f.name} ({f.points:+d} p)" for f in worst) + "."

    return CreditScoreResult(
        score=score,
        base=base,
        factors=factors,
        approved=approved,
        approval_threshold=threshold,
        offered_rate=rate,
        decline_reason=decline,
        simulated_lender=_pick_lender(student_seed, requested_amount),
    )


def annuity_monthly_payment(
    principal: Decimal, annual_rate: float, months: int,
) -> Decimal:
    """Annuitetslån-månadsbetalning (PMT-formeln)."""
    if annual_rate <= 0:
        return (principal / months).quantize(Decimal("0.01"))
    r = Decimal(str(annual_rate)) / Decimal("12")
    n = Decimal(str(months))
    factor = (r * (1 + r) ** int(months)) / ((1 + r) ** int(months) - 1)
    return (principal * factor).quantize(Decimal("0.01"))
