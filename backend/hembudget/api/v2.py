"""V2-router · parallell-migration av elev-dashboarden.

Strategi: gamla v1 (`/dashboard`, `/transactions`, ...) körs orört.
v2 byggs ut bredvid på `/v2/*` endpoints + `/v2/*` frontend-routes.
Migrationen sker modul för modul, urlerna byter när vi är klara.

Första PR:n (denna): onboarding-endpoint + status. Sätter
`v2_onboarding_completed_at`, `v2_spend_profile`, `v2_fairness_choice`,
`v2_partner_model` på Student-tabellen — utan att röra v1-data.

Super-admin auto-routas till v2 (handlas i frontend via /v2/-flag).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from datetime import date as _date
from decimal import Decimal

from ..db.base import session_scope
from ..db.models import (
    Account, Transaction, FundHolding, UpcomingTransaction, Goal,
    MailItem, Loan, LoanProduct, PaymentMark, CreditCheck, KALPCalculation,
    TaxDeduction, TaxProposal, TaxYearReturn,
    InsurancePolicy, InsuranceClaim,
    UtilitySubscription, UtilityReading,
    RentalContract, RentalNotice,
    PensionAssumption, StockHolding, StockTransaction,
    Category,
)
from ..insurance import seed_default_insurance_policies
from ..utility import seed_default_utility_subscriptions
from ..rental import seed_default_rental
from ..pension import (
    seed_default_pension,
    get_or_create_assumptions as _get_pension_assumptions,
    isk_balance as _compute_isk_balance,
    compute_pension_forecast,
)
from ..loans.credit import (
    compute_credit_check, latest_credit_check, latest_kalp,
)
from ..loans.matcher import LoanMatcher
from ..loans.products_seed import seed_default_loan_products
from ..tax.proposals import (
    auto_generate_proposals, compute_tax_summary, approve_proposal,
    reject_proposal, submit_tax_year, latest_tax_year_return,
)
from ..school.employer_models import (
    AgreementBenefit,
    CollectiveAgreement,
    EmployerSatisfaction,
    EmployerSatisfactionEvent,
    MarketSalaryRange,
    NegotiationRound,
    ProfessionAgreement,
    SalaryNegotiation,
    WorkplaceQuestion,
    WorkplaceQuestionAnswer,
)
from ..school.employer_market_seed import (
    seed_default_agreement_benefits,
    seed_default_market_salary_ranges,
)
from ..school.engines import master_session
from ..school.models import Student, StudentProfile, Teacher, V2OnboardingEvent
from ..wellbeing.calculator import calculate_wellbeing
from .deps import TokenInfo, require_token
from sqlalchemy import func as _func


router = APIRouter(prefix="/v2", tags=["v2"])


# === Schemas ===

SpendProfile = Literal["sparsam", "balanserad", "slosa"]
FairnessChoice = Literal["50_50", "proportionellt", "pool"]
PartnerModel = Literal["solo", "ai", "klasskompis"]


class V2StatusResponse(BaseModel):
    """Vad eleven (eller läraren) ser om sitt v2-läge."""
    role: Literal["student", "teacher", "demo"]
    v2_eligible: bool = Field(
        description=(
            "True om eleven ska routas till v2-frontend. "
            "Super-admins är alltid eligible."
        ),
    )
    v2_onboarding_completed: bool
    v2_level: int = 1
    v2_spend_profile: SpendProfile = "sparsam"
    v2_fairness_choice: Optional[FairnessChoice] = None
    v2_partner_model: PartnerModel = "solo"
    is_super_admin: bool = False


class OnboardingCompleteRequest(BaseModel):
    spend_profile: SpendProfile = Field(
        default="sparsam",
        description=(
            "Sparsam är default på Nivå 1. Lärare kan höja senare."
        ),
    )
    fairness_choice: Optional[FairnessChoice] = Field(
        default=None,
        description=(
            "Värderingsval om sambo-ekonomi. NULL om karaktären är solo."
        ),
    )
    partner_model: PartnerModel = Field(default="solo")


class OnboardingCompleteResponse(BaseModel):
    student_id: int
    completed_at: datetime
    v2_level: int
    redirect_to: str = Field(
        description=(
            "URL som frontend ska navigera till efter onboarding. "
            "/v2/hub om allt klart."
        ),
    )


# === Hub aggregate-data (riktig data från DB) ===

class HubCharacter(BaseModel):
    # display_name = karaktärsnamn (Sara Andersson) om
    # StudentProfile.character_first_name + character_last_name finns,
    # annars fallback till student.display_name (login-namnet).
    display_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profession: Optional[str] = None
    employer: Optional[str] = None
    age: Optional[int] = None
    city: Optional[str] = None
    family_status: Optional[str] = None
    housing_type: Optional[str] = None
    housing_monthly: Optional[float] = None
    gross_salary_monthly: Optional[float] = None
    net_salary_monthly: Optional[float] = None
    personality: Optional[str] = None


class HubPentagon(BaseModel):
    """Pentagonens 5 axlar mappade från wellbeing.

    Mappning (backend → prototypens namn):
      economy → ekonomi
      safety  → karriär (anställning, skydd, säkerhet)
      health  → hälsa
      social  → relation
      leisure → fritid
    """
    total_score: int
    ekonomi: int
    karriar: int
    halsa: int
    relation: int
    fritid: int
    year_month: str


class HubMonthSummary(BaseModel):
    income: float
    expenses: float
    saved: float
    save_rate_pct: float
    transactions_count: int


class HubResponse(BaseModel):
    student_id: int
    character: HubCharacter
    v2_level: int
    v2_spend_profile: str
    v2_fairness_choice: Optional[str] = None
    v2_partner_model: str
    pentagon: Optional[HubPentagon] = None
    month_summary: HubMonthSummary
    total_balance: float
    accounts_count: int


def _current_year_month() -> str:
    today = _date.today()
    return f"{today.year:04d}-{today.month:02d}"


@router.get("/hub", response_model=HubResponse)
def get_hub(info: TokenInfo = Depends(require_token)) -> HubResponse:
    """Aggregerar all data hubben behöver i ett anrop.

    Hämtar från:
    - master-DB: Student, StudentProfile (karaktär, v2-fält)
    - scope-DB: transactions, accounts (månads-summa, saldon)
    - wellbeing-modulen (5 axlar)

    Demo/teacher får en minimal placeholder utan scope-data.
    """
    if info.role != "student" or info.student_id is None:
        # Teacher eller demo ser inte sin egen hub-data — de ska
        # se elevernas via /teacher/students/* istället.
        return HubResponse(
            student_id=0,
            character=HubCharacter(display_name="—"),
            v2_level=1,
            v2_spend_profile="sparsam",
            v2_partner_model="solo",
            month_summary=HubMonthSummary(
                income=0, expenses=0, saved=0,
                save_rate_pct=0, transactions_count=0,
            ),
            total_balance=0,
            accounts_count=0,
        )

    # 1. Karaktär från master-DB
    with master_session() as mdb:
        student = mdb.get(Student, info.student_id)
        if not student:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Student hittades inte",
            )
        profile = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == info.student_id)
            .one_or_none()
        )
        # Karaktärsnamn — använd StudentProfile.character_first/last_name
        # om de finns. Fallback till student.display_name så v1-elever
        # eller demo-konton inte får tomt namn. Använder _safe_profile_attr
        # för att inte krascha om migrationen inte hunnit lägga till
        # kolumnerna i prod-Postgres.
        from .school import _safe_profile_attr  # type: ignore[attr-defined]
        first_name: Optional[str] = None
        last_name: Optional[str] = None
        if profile is not None:
            first_name = _safe_profile_attr(profile, "character_first_name")
            last_name = _safe_profile_attr(profile, "character_last_name")
        if first_name and last_name:
            display = f"{first_name} {last_name}"
        elif first_name:
            display = first_name
        else:
            display = student.display_name

        char = HubCharacter(
            display_name=display,
            first_name=first_name,
            last_name=last_name,
            profession=profile.profession if profile else None,
            employer=profile.employer if profile else None,
            age=profile.age if profile else None,
            city=profile.city if profile else None,
            family_status=profile.family_status if profile else None,
            housing_type=profile.housing_type if profile else None,
            housing_monthly=(
                float(profile.housing_monthly) if profile and profile.housing_monthly else None
            ),
            gross_salary_monthly=(
                float(profile.gross_salary_monthly)
                if profile and profile.gross_salary_monthly else None
            ),
            net_salary_monthly=(
                float(profile.net_salary_monthly)
                if profile and profile.net_salary_monthly else None
            ),
            personality=profile.personality if profile else None,
        )
        v2_level = getattr(student, "v2_level", None) or 1
        v2_spend = getattr(student, "v2_spend_profile", None) or "sparsam"
        v2_fair = getattr(student, "v2_fairness_choice", None)
        v2_partner = getattr(student, "v2_partner_model", None) or "solo"

    # 2. Pentagon (live via wellbeing-calculator)
    pentagon: Optional[HubPentagon] = None
    month_summary = HubMonthSummary(
        income=0, expenses=0, saved=0, save_rate_pct=0, transactions_count=0,
    )
    total_balance = 0.0
    accounts_count = 0

    try:
        with session_scope() as s:
            ym = _current_year_month()
            wb = calculate_wellbeing(s, ym)
            pentagon = HubPentagon(
                total_score=wb.total_score,
                ekonomi=wb.economy,
                karriar=wb.safety,
                halsa=wb.health,
                relation=wb.social,
                fritid=wb.leisure,
                year_month=ym,
            )

            # 3. Månads-summa från transactions (innevarande månad)
            today = _date.today()
            month_start = _date(today.year, today.month, 1)
            txs = (
                s.query(Transaction)
                .filter(Transaction.date >= month_start)
                .filter(Transaction.date <= today)
                .all()
            )
            income = sum(
                float(t.amount) for t in txs if float(t.amount) > 0
            )
            expenses = sum(
                -float(t.amount) for t in txs if float(t.amount) < 0
            )
            saved = income - expenses
            save_rate = (saved / income * 100) if income > 0 else 0.0
            month_summary = HubMonthSummary(
                income=round(income, 2),
                expenses=round(expenses, 2),
                saved=round(saved, 2),
                save_rate_pct=round(save_rate, 1),
                transactions_count=len(txs),
            )

            # 4. Saldon
            accounts = s.query(Account).all()
            accounts_count = len(accounts)
            tot = Decimal("0")
            for acc in accounts:
                ob = acc.opening_balance or Decimal("0")
                start = acc.opening_balance_date
                q = s.query(_func.coalesce(_func.sum(Transaction.amount), 0)).filter(
                    Transaction.account_id == acc.id,
                    Transaction.date <= today,
                )
                if start is not None:
                    q = q.filter(Transaction.date > start)
                movement = Decimal(str(q.scalar() or 0))
                cur = ob + movement
                # Lägg till fond-värde för ISK
                fund_total = Decimal(str(
                    s.query(_func.coalesce(_func.sum(FundHolding.market_value), 0))
                    .filter(FundHolding.account_id == acc.id)
                    .scalar() or 0
                ))
                if not bool(getattr(acc, "incognito", False)):
                    tot += (cur + fund_total) if fund_total > 0 else cur
            total_balance = float(tot)
    except Exception:
        # Scope-DB saknas eller wellbeing failar — returnera minimal
        # data så hubben inte blir vit. Eleven kan fortfarande se
        # karaktär + v2-fält från master.
        pass

    return HubResponse(
        student_id=info.student_id,
        character=char,
        v2_level=v2_level,
        v2_spend_profile=v2_spend,
        v2_fairness_choice=v2_fair,
        v2_partner_model=v2_partner,
        pentagon=pentagon,
        month_summary=month_summary,
        total_balance=total_balance,
        accounts_count=accounts_count,
    )


# === Bank-aggregat (riktig data från scope-DB) ===

class BankAccount(BaseModel):
    id: int
    name: str
    bank: str
    type: str
    account_number: Optional[str] = None
    current_balance: float
    fund_value: float
    total_value: float
    incognito: bool


class BankTransaction(BaseModel):
    id: int
    account_id: int
    account_name: str
    date: _date
    amount: float
    description: str
    merchant: Optional[str] = None
    category_id: Optional[int] = None
    is_transfer: bool


class BankUpcoming(BaseModel):
    id: int
    name: str
    kind: Literal["bill", "income"]
    amount: float
    expected_date: _date
    debit_account_id: Optional[int] = None
    bankgiro: Optional[str] = None
    plusgiro: Optional[str] = None
    autogiro: bool
    is_paid: bool


class BankSummary(BaseModel):
    total_balance: float
    accounts_count: int
    upcoming_open_total: float
    upcoming_open_count: int
    income_this_month: float
    expenses_this_month: float
    transactions_count: int


class BankResponse(BaseModel):
    student_id: int
    year_month: str
    summary: BankSummary
    accounts: list[BankAccount]
    recent_transactions: list[BankTransaction]
    upcoming_bills: list[BankUpcoming]


def _empty_bank(student_id: int) -> BankResponse:
    return BankResponse(
        student_id=student_id,
        year_month=_current_year_month(),
        summary=BankSummary(
            total_balance=0,
            accounts_count=0,
            upcoming_open_total=0,
            upcoming_open_count=0,
            income_this_month=0,
            expenses_this_month=0,
            transactions_count=0,
        ),
        accounts=[],
        recent_transactions=[],
        upcoming_bills=[],
    )


@router.get("/bank", response_model=BankResponse)
def get_bank(
    limit_transactions: int = 30,
    info: TokenInfo = Depends(require_token),
) -> BankResponse:
    """Aggregat-endpoint för bank-vyn.

    Returnerar i ETT anrop:
    - Alla konton med saldo (cash + fond-värde)
    - Senaste N transaktioner kronologiskt (default 30)
    - Öppna kommande fakturor (förfallodag framåt, ej fullbetalda)
    - Månads-summa (in/ut/antal)

    Demo/teacher får en tom payload (de har ingen scope-DB).
    Om scope-DB saknas eller failar: returnera tom payload, blanka
    inte ut vyn.
    """
    if info.role != "student" or info.student_id is None:
        return _empty_bank(0)

    try:
        with session_scope() as s:
            today = _date.today()
            month_start = _date(today.year, today.month, 1)

            # 1. Konton + saldo
            accounts_db = s.query(Account).order_by(Account.id).all()
            fund_values: dict[int, Decimal] = {}
            for acc_id, fund_total in (
                s.query(
                    FundHolding.account_id,
                    _func.coalesce(_func.sum(FundHolding.market_value), 0),
                )
                .group_by(FundHolding.account_id)
                .all()
            ):
                fund_values[acc_id] = Decimal(str(fund_total or 0))

            accounts_out: list[BankAccount] = []
            account_names: dict[int, str] = {}
            total_balance = Decimal("0")
            for acc in accounts_db:
                ob = acc.opening_balance or Decimal("0")
                start = acc.opening_balance_date
                q = s.query(
                    _func.coalesce(_func.sum(Transaction.amount), 0)
                ).filter(
                    Transaction.account_id == acc.id,
                    Transaction.date <= today,
                )
                if start is not None:
                    q = q.filter(Transaction.date > start)
                movement = Decimal(str(q.scalar() or 0))
                cur = ob + movement
                fv = fund_values.get(acc.id, Decimal("0"))
                tv = cur + fv
                is_incog = bool(getattr(acc, "incognito", False))
                if not is_incog:
                    total_balance += tv if fv > 0 else cur
                accounts_out.append(BankAccount(
                    id=acc.id,
                    name=acc.name,
                    bank=acc.bank,
                    type=acc.type,
                    account_number=acc.account_number,
                    current_balance=float(cur),
                    fund_value=float(fv),
                    total_value=float(tv),
                    incognito=is_incog,
                ))
                account_names[acc.id] = acc.name

            # 2. Senaste transaktioner
            tx_rows = (
                s.query(Transaction)
                .order_by(Transaction.date.desc(), Transaction.id.desc())
                .limit(max(1, min(limit_transactions, 200)))
                .all()
            )
            recent_tx: list[BankTransaction] = [
                BankTransaction(
                    id=t.id,
                    account_id=t.account_id,
                    account_name=account_names.get(t.account_id, "—"),
                    date=t.date,
                    amount=float(t.amount),
                    description=t.raw_description or "",
                    merchant=t.normalized_merchant,
                    category_id=t.category_id,
                    is_transfer=bool(getattr(t, "is_transfer", False)),
                )
                for t in tx_rows
            ]

            # 3. Kommande fakturor (öppna = ej fullt matchade)
            upcoming_rows = (
                s.query(UpcomingTransaction)
                .filter(UpcomingTransaction.expected_date >= today)
                .order_by(UpcomingTransaction.expected_date.asc())
                .all()
            )
            upcoming: list[BankUpcoming] = []
            upcoming_open_total = Decimal("0")
            upcoming_open_count = 0
            for u in upcoming_rows:
                # En upcoming räknas som "betald" när den är matchad mot
                # en faktisk transaktion. Mer nyanserad delbetalnings-
                # status finns i /upcoming-endpointen — för v2/bank
                # räcker is_paid=True/False.
                paid = u.matched_transaction_id is not None
                if not paid:
                    upcoming_open_total += u.amount
                    upcoming_open_count += 1
                upcoming.append(BankUpcoming(
                    id=u.id,
                    name=u.name,
                    kind=u.kind if u.kind in ("bill", "income") else "bill",
                    amount=float(u.amount),
                    expected_date=u.expected_date,
                    debit_account_id=u.debit_account_id,
                    bankgiro=u.bankgiro,
                    plusgiro=u.plusgiro,
                    autogiro=bool(u.autogiro),
                    is_paid=paid,
                ))

            # 4. Månads-summa
            month_txs = (
                s.query(Transaction)
                .filter(Transaction.date >= month_start)
                .filter(Transaction.date <= today)
                .all()
            )
            income = sum(
                float(t.amount) for t in month_txs if float(t.amount) > 0
            )
            expenses = sum(
                -float(t.amount) for t in month_txs if float(t.amount) < 0
            )

            return BankResponse(
                student_id=info.student_id,
                year_month=_current_year_month(),
                summary=BankSummary(
                    total_balance=float(total_balance),
                    accounts_count=len(accounts_out),
                    upcoming_open_total=float(upcoming_open_total),
                    upcoming_open_count=upcoming_open_count,
                    income_this_month=round(income, 2),
                    expenses_this_month=round(expenses, 2),
                    transactions_count=len(month_txs),
                ),
                accounts=accounts_out,
                recent_transactions=recent_tx,
                upcoming_bills=upcoming,
            )
    except Exception:
        return _empty_bank(info.student_id)


# === Budget-aggregat (plan vs utfall + Konsumentverket) ===

class V2BudgetCategoryRow(BaseModel):
    category_id: int
    category_name: str
    group_name: Optional[str] = None
    icon: str = "·"
    planned: float
    actual: float
    consumer_reference: Optional[float] = None
    progress_pct: float
    status: Literal["under", "near", "over", "fixed", "savings", "income"]
    is_fixed: bool = False
    is_income: bool = False


class V2BudgetSummary(BaseModel):
    income_total: float
    expenses_total: float
    planned_expenses_total: float
    saved: float
    save_rate_pct: float
    days_into_month: int
    days_in_month: int
    progress_pct: float
    over_budget_total: float
    categories_count: int


class V2BudgetResponse(BaseModel):
    student_id: int
    month: str
    summary: V2BudgetSummary
    categories: list[V2BudgetCategoryRow]


# Fasta kategorier (autogiro/återkommande) — match på ord i kategori-namn
_FIXED_KEYWORDS = (
    "hyra", "boende", "stockholmshem", "lan", "lån", "ranta", "ränta",
    "amortering", "abonnemang", "telia", "spotify", "tibber", "el",
    "bredband", "vatten", "csn", "försäkring", "forsakring", "folksam",
    "trygg-hansa", "autogiro",
)

_SAVINGS_KEYWORDS = (
    "sparmål", "sparmal", "buffert", "isk", "avanza", "spara", "körkort",
    "korkort", "interrail", "sparande",
)

# Kategori-emoji (matchar prototypens visuella språk)
_CATEGORY_ICONS: dict[str, str] = {
    "hyra": "▥",
    "boende": "▥",
    "mat": "🍴",
    "livsmedel": "🍴",
    "ica": "🍴",
    "restaurang": "🍽",
    "nöje": "🍽",
    "transport": "🚇",
    "sl": "🚇",
    "resor": "🚇",
    "sparande": "◎",
    "sparmål": "◎",
    "buffert": "◎",
    "körkort": "◎",
    "interrail": "◎",
    "isk": "↗",
    "avanza": "↗",
    "investering": "↗",
    "el": "⚡",
    "förbrukning": "⚡",
    "elektricitet": "⚡",
    "tibber": "⚡",
    "bredband": "⚡",
    "internet": "⚡",
    "spotify": "♪",
    "abonnemang": "♪",
    "försäkring": "⛨",
    "forsakring": "⛨",
    "folksam": "⛨",
    "kläder": "👕",
    "hygien": "🧴",
    "fritid": "★",
    "hälsa": "✚",
    "vård": "✚",
    "tandvård": "✚",
    "lön": "💰",
    "csn": "🎓",
    "studie": "🎓",
}


def _icon_for(category: str) -> str:
    lower = category.lower()
    for key, icon in _CATEGORY_ICONS.items():
        if key in lower:
            return icon
    return "·"


def _is_fixed(category: str) -> bool:
    lower = category.lower()
    return any(k in lower for k in _FIXED_KEYWORDS)


def _is_savings(category: str) -> bool:
    lower = category.lower()
    return any(k in lower for k in _SAVINGS_KEYWORDS)


def _empty_budget(student_id: int, month: str) -> V2BudgetResponse:
    today = _date.today()
    import calendar as _cal
    days_in_month = _cal.monthrange(today.year, today.month)[1]
    return V2BudgetResponse(
        student_id=student_id,
        month=month,
        summary=V2BudgetSummary(
            income_total=0,
            expenses_total=0,
            planned_expenses_total=0,
            saved=0,
            save_rate_pct=0,
            days_into_month=today.day,
            days_in_month=days_in_month,
            progress_pct=0,
            over_budget_total=0,
            categories_count=0,
        ),
        categories=[],
    )


@router.get("/budget", response_model=V2BudgetResponse)
def get_budget(
    month: Optional[str] = None,
    info: TokenInfo = Depends(require_token),
) -> V2BudgetResponse:
    """Aggregat-endpoint för budget-vyn.

    Returnerar:
    - month_summary (in/ut/sparat/sparkvot/progress)
    - kategorier med planned + actual + Konsumentverket-referens
    - status per rad (under/near/over/fixed/savings/income)

    Använder MonthlyBudgetService.summary() som datakälla — samma
    siffror som v1 /budget visar. Lägger på Konsumentverket-mappning
    från wellbeing.minimums.

    Demo/teacher får tom payload utan crash.
    """
    ym = month or _current_year_month()
    if info.role != "student" or info.student_id is None:
        return _empty_budget(0, ym)

    try:
        from ..budget.monthly import MonthlyBudgetService
        from ..wellbeing.minimums import (
            lookup_minimum, CATEGORY_MINIMUMS_SEK_MONTH,
        )
        import calendar as _cal

        def _fuzzy_minimum(category: str) -> Optional[int]:
            """Hitta Konsumentverket-referens även om kategorinamnet
            inte matchar exakt. Letar efter nyckelord i namnet,
            t.ex. 'Mat & livsmedel' → 'Mat' → 2840 kr."""
            if not category:
                return None
            exact = lookup_minimum(category)
            if exact is not None:
                return exact
            lower = category.lower()
            for key, val in CATEGORY_MINIMUMS_SEK_MONTH.items():
                if key.lower() in lower:
                    return val
            return None

        with session_scope() as s:
            svc = MonthlyBudgetService(s)
            summ = svc.summary(ym)

            categories: list[V2BudgetCategoryRow] = []
            over_budget_total = Decimal("0")
            for line in summ.lines:
                planned_abs = abs(Decimal(line.planned or 0))
                actual_abs = abs(Decimal(line.actual or 0))
                is_inc = line.kind == "income"
                ref = _fuzzy_minimum(line.category)

                # Status-logik:
                # - income → "income" (inga gränser)
                # - planned == 0 → använd actual som vägledning
                # - savings-kategori → "savings"
                # - fast kostnad → "fixed"
                # - actual > planned * 1.05 → "over"
                # - actual > planned * 0.95 → "near"
                # - else → "under"
                if is_inc:
                    status: str = "income"
                elif _is_savings(line.category):
                    status = "savings"
                elif _is_fixed(line.category):
                    status = "fixed"
                elif planned_abs == 0:
                    status = "near"
                else:
                    # Status-trösklar (matchar prototypen):
                    # - actual > planned * 1.05 → "over" (röd, "+ N över")
                    # - actual >= planned * 1.0 → "near" (gul, "klart")
                    # - actual < planned * 1.0 → "under" (grön, "under budget")
                    ratio = actual_abs / planned_abs
                    if ratio > Decimal("1.05"):
                        status = "over"
                        over_budget_total += actual_abs - planned_abs
                    elif ratio >= Decimal("1.0"):
                        status = "near"
                    else:
                        status = "under"

                progress = (
                    float(actual_abs / planned_abs * 100)
                    if planned_abs > 0
                    else 0.0
                )
                categories.append(V2BudgetCategoryRow(
                    category_id=line.category_id,
                    category_name=line.category,
                    group_name=line.group,
                    icon=_icon_for(line.category),
                    planned=float(planned_abs if not is_inc else line.planned or 0),
                    actual=float(actual_abs if not is_inc else line.actual or 0),
                    consumer_reference=float(ref) if ref else None,
                    progress_pct=round(progress, 1),
                    status=status,  # type: ignore[arg-type]
                    is_fixed=_is_fixed(line.category),
                    is_income=is_inc,
                ))

            today = _date.today()
            year, mon = map(int, ym.split("-"))
            days_in_month = _cal.monthrange(year, mon)[1]
            days_into = today.day if (today.year, today.month) == (year, mon) else days_in_month

            income_total = float(summ.income or 0)
            expenses_total = float(summ.expenses or 0)
            saved = income_total - expenses_total
            save_rate = (saved / income_total * 100) if income_total > 0 else 0.0
            planned_total = float(sum(
                Decimal(c.planned)
                for c in categories
                if not c.is_income
            ))
            progress_pct = (
                expenses_total / planned_total * 100
                if planned_total > 0 else 0.0
            )

            return V2BudgetResponse(
                student_id=info.student_id,
                month=ym,
                summary=V2BudgetSummary(
                    income_total=round(income_total, 2),
                    expenses_total=round(expenses_total, 2),
                    planned_expenses_total=round(planned_total, 2),
                    saved=round(saved, 2),
                    save_rate_pct=round(save_rate, 1),
                    days_into_month=days_into,
                    days_in_month=days_in_month,
                    progress_pct=round(progress_pct, 1),
                    over_budget_total=float(over_budget_total),
                    categories_count=len(categories),
                ),
                categories=categories,
            )
    except Exception:
        return _empty_budget(info.student_id, ym)


# === Budget · skriv-endpoints (PATCH/POST per kategori) ===

class V2BudgetUpdateRequest(BaseModel):
    """Uppdatera planerad budget för en kategori i en månad.

    Beloppet skickas alltid som POSITIV summa. Backend lagrar
    expense-budgetar som negativa internt (konsistent med
    transaktionstecken), men v2-API:et exponerar absoluta belopp.
    """
    planned_amount: float = Field(..., ge=0)
    month: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    is_income: bool = Field(default=False)


class V2BudgetCreateCategoryRequest(BaseModel):
    """Skapa ny kategori + sätt initial budget i ett anrop."""
    category_name: str = Field(..., min_length=1, max_length=80)
    planned_amount: float = Field(..., ge=0)
    month: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    is_income: bool = Field(default=False)


def _build_category_row(
    s, line, _fuzzy_minimum, over_acc: list,
) -> V2BudgetCategoryRow:
    """Bygg en V2BudgetCategoryRow från en MonthlyBudgetService.CategoryLine."""
    planned_abs = abs(Decimal(line.planned or 0))
    actual_abs = abs(Decimal(line.actual or 0))
    is_inc = line.kind == "income"
    ref = _fuzzy_minimum(line.category)

    if is_inc:
        status: str = "income"
    elif _is_savings(line.category):
        status = "savings"
    elif _is_fixed(line.category):
        status = "fixed"
    elif planned_abs == 0:
        status = "near"
    else:
        ratio = actual_abs / planned_abs
        if ratio > Decimal("1.05"):
            status = "over"
            over_acc.append(actual_abs - planned_abs)
        elif ratio >= Decimal("1.0"):
            status = "near"
        else:
            status = "under"

    progress = (
        float(actual_abs / planned_abs * 100)
        if planned_abs > 0 else 0.0
    )
    return V2BudgetCategoryRow(
        category_id=line.category_id,
        category_name=line.category,
        group_name=line.group,
        icon=_icon_for(line.category),
        planned=float(planned_abs if not is_inc else line.planned or 0),
        actual=float(actual_abs if not is_inc else line.actual or 0),
        consumer_reference=float(ref) if ref else None,
        progress_pct=round(progress, 1),
        status=status,  # type: ignore[arg-type]
        is_fixed=_is_fixed(line.category),
        is_income=is_inc,
    )


@router.post("/budget/category", response_model=V2BudgetCategoryRow)
def create_budget_category_first(
    body: V2BudgetCreateCategoryRequest,
    info: TokenInfo = Depends(require_token),
) -> V2BudgetCategoryRow:
    """OBS: registrerad här FÖRST (före /budget/{category_id}) så
    FastAPI inte matchar 'category' som ett int-id. Implementationen
    delegerar till create_budget_category nedan."""
    return _create_budget_category_impl(body, info)


@router.post("/budget/{category_id}", response_model=V2BudgetCategoryRow)
def update_budget_category(
    category_id: int,
    body: V2BudgetUpdateRequest,
    info: TokenInfo = Depends(require_token),
) -> V2BudgetCategoryRow:
    """Uppdatera planerad budget för en kategori.

    - Income-kategorier sparas som POSITIVA belopp.
    - Expense-kategorier sparas som NEGATIVA belopp internt
      (konsistent med transaktionstecken).
    - Returnerar den färska V2BudgetCategoryRow med uppdaterat
      progress/status så frontend kan rendera direkt utan att
      refetcha hela /v2/budget.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast elever kan uppdatera sin budget",
        )

    ym = body.month or _current_year_month()

    from ..budget.monthly import MonthlyBudgetService
    from ..wellbeing.minimums import (
        lookup_minimum, CATEGORY_MINIMUMS_SEK_MONTH,
    )
    from ..db.models import Category as _Cat

    def _fuzzy_minimum(category: str) -> Optional[int]:
        if not category:
            return None
        exact = lookup_minimum(category)
        if exact is not None:
            return exact
        lower = category.lower()
        for key, val in CATEGORY_MINIMUMS_SEK_MONTH.items():
            if key.lower() in lower:
                return val
        return None

    with session_scope() as s:
        cat = s.get(_Cat, category_id)
        if cat is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Kategori {category_id} hittades inte",
            )
        # Internt teckenkonvention: expense → negativ, income → positiv
        signed = (
            Decimal(str(body.planned_amount)) if body.is_income
            else -Decimal(str(body.planned_amount))
        )
        svc = MonthlyBudgetService(s)
        svc.set_budget(ym, category_id, signed)
        s.flush()

        # Bygg svar via summary för att få färsk progress/status
        summ = svc.summary(ym)
        for line in summ.lines:
            if line.category_id == category_id:
                over_acc: list = []
                return _build_category_row(s, line, _fuzzy_minimum, over_acc)
        # Fallback om kategorin inte syns i summary än (ingen actual)
        return V2BudgetCategoryRow(
            category_id=category_id,
            category_name=cat.name,
            group_name=None,
            icon=_icon_for(cat.name),
            planned=float(body.planned_amount),
            actual=0.0,
            consumer_reference=(
                float(_fuzzy_minimum(cat.name) or 0) or None
            ),
            progress_pct=0.0,
            status=(
                "income" if body.is_income
                else "savings" if _is_savings(cat.name)
                else "fixed" if _is_fixed(cat.name)
                else "near"
            ),  # type: ignore[arg-type]
            is_fixed=_is_fixed(cat.name),
            is_income=body.is_income,
        )


def _create_budget_category_impl(
    body: V2BudgetCreateCategoryRequest,
    info: TokenInfo,
) -> V2BudgetCategoryRow:
    """Skapa ny kategori + sätt initial budget för månaden.

    Idempotent: om kategorin redan finns, sätt bara budgeten.
    Returnerar den färska V2BudgetCategoryRow.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast elever kan lägga till kategorier i sin budget",
        )

    ym = body.month or _current_year_month()
    name = body.category_name.strip()
    if not name:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Kategori-namn får inte vara tomt",
        )

    from ..budget.monthly import MonthlyBudgetService
    from ..wellbeing.minimums import (
        lookup_minimum, CATEGORY_MINIMUMS_SEK_MONTH,
    )
    from ..db.models import Category as _Cat

    def _fuzzy_minimum(category: str) -> Optional[int]:
        if not category:
            return None
        exact = lookup_minimum(category)
        if exact is not None:
            return exact
        lower = category.lower()
        for key, val in CATEGORY_MINIMUMS_SEK_MONTH.items():
            if key.lower() in lower:
                return val
        return None

    with session_scope() as s:
        # Hitta eller skapa kategori
        cat = s.query(_Cat).filter(_Cat.name == name).first()
        if cat is None:
            cat = _Cat(name=name)
            s.add(cat)
            s.flush()
        signed = (
            Decimal(str(body.planned_amount)) if body.is_income
            else -Decimal(str(body.planned_amount))
        )
        svc = MonthlyBudgetService(s)
        svc.set_budget(ym, cat.id, signed)
        s.flush()
        summ = svc.summary(ym)
        for line in summ.lines:
            if line.category_id == cat.id:
                over_acc: list = []
                return _build_category_row(s, line, _fuzzy_minimum, over_acc)
        return V2BudgetCategoryRow(
            category_id=cat.id,
            category_name=cat.name,
            group_name=None,
            icon=_icon_for(cat.name),
            planned=float(body.planned_amount),
            actual=0.0,
            consumer_reference=(
                float(_fuzzy_minimum(cat.name) or 0) or None
            ),
            progress_pct=0.0,
            status=(
                "income" if body.is_income
                else "near"
            ),  # type: ignore[arg-type]
            is_fixed=_is_fixed(cat.name),
            is_income=body.is_income,
        )


@router.delete("/budget/{category_id}", status_code=204)
def delete_budget_row(
    category_id: int,
    month: Optional[str] = None,
    info: TokenInfo = Depends(require_token),
) -> None:
    """Ta bort budget-raden för en kategori i en månad.

    Kategorin själv tas INTE bort (transaktionerna behåller sin
    tagg). Bara Budget-raden för månaden raderas.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast elever kan ta bort budget-rader",
        )

    ym = month or _current_year_month()
    from ..db.models import Budget as _Bd
    with session_scope() as s:
        row = (
            s.query(_Bd)
            .filter(_Bd.month == ym, _Bd.category_id == category_id)
            .first()
        )
        if row is not None:
            s.delete(row)
            s.flush()


# === Sparmål (Goal-tabellen) ===

class V2GoalRow(BaseModel):
    id: int
    name: str
    icon: str
    target_amount: float
    current_amount: float
    target_date: Optional[_date] = None
    progress_pct: float
    months_remaining: Optional[int] = None
    monthly_pace_target: Optional[float] = None
    expected_progress_pct: Optional[float] = None
    account_name: Optional[str] = None
    status: Literal["new", "ahead", "on_track", "behind", "complete"]
    color: str  # CSS-färg som matchar prototypen


class V2GoalsSummary(BaseModel):
    total_saved: float
    total_target: float
    overall_progress_pct: float
    monthly_pace_total: float
    goals_count: int
    on_track_count: int
    behind_count: int


class V2GoalsResponse(BaseModel):
    student_id: int
    summary: V2GoalsSummary
    goals: list[V2GoalRow]


# Mappning mål-namn → emoji + färg (matchar prototypens mål-kort).
# Prototypens 4 mål: Buffert (orange/accent), Körkort (gul/warm),
# Interrail (grön), Kontantinsats (grå/dim).
_GOAL_KEYWORDS_TO_COLOR: list[tuple[tuple[str, ...], str, str]] = [
    (("buffert", "akut"), "var(--accent)", "🛡"),  # accent (orange) — bufferten
    (("körkort", "korkort", "körkortet"), "var(--warm)", "🚗"),  # warm (gul)
    (("interrail", "resa", "europa"), "#6ee7b7", "🌍"),  # grön
    (("kontant", "bostad", "lägenhet", "lagenhet", "hus"), "var(--text-dim)", "🏠"),
    (("pension",), "#a5b4fc", "🪴"),
    (("dator", "laptop", "skola"), "#c7d2fe", "💻"),
    (("semester",), "#f59e0b", "🏖"),
]


def _goal_color_icon(name: str) -> tuple[str, str]:
    lower = (name or "").lower()
    for keys, color, icon in _GOAL_KEYWORDS_TO_COLOR:
        if any(k in lower for k in keys):
            return color, icon
    return "var(--warm)", "◎"


def _empty_goals(student_id: int) -> V2GoalsResponse:
    return V2GoalsResponse(
        student_id=student_id,
        summary=V2GoalsSummary(
            total_saved=0,
            total_target=0,
            overall_progress_pct=0,
            monthly_pace_total=0,
            goals_count=0,
            on_track_count=0,
            behind_count=0,
        ),
        goals=[],
    )


@router.get("/mal", response_model=V2GoalsResponse)
def get_goals(info: TokenInfo = Depends(require_token)) -> V2GoalsResponse:
    """Aggregat-endpoint för sparmål-vyn (/v2/mal).

    Returnerar:
    - Alla Goal-rader med beräknat progress, månadsbidrag-mål, status
    - Summary med totalt sparat, totalt mål, snittprogress

    Status per mål (pedagogisk):
    - complete    · current >= target
    - new         · progress < 5 % (precis startat)
    - ahead       · progress överstiger förväntad + 10 %-enheter
    - on_track    · progress nära förväntad (±10 %-enheter)
    - behind      · progress under förväntad - 10 %-enheter

    Förväntad progress = elapsed_days / total_days mellan
    skapande och target_date. Om target_date saknas → status=on_track
    eller new beroende på actual progress.
    """
    if info.role != "student" or info.student_id is None:
        return _empty_goals(0)

    try:
        with session_scope() as s:
            today = _date.today()
            goals_db = s.query(Goal).order_by(Goal.id).all()
            accounts = {a.id: a.name for a in s.query(Account).all()}

            total_saved = Decimal("0")
            total_target = Decimal("0")
            monthly_pace_total = Decimal("0")
            on_track_count = 0
            behind_count = 0
            rows: list[V2GoalRow] = []

            for g in goals_db:
                target = g.target_amount or Decimal("0")
                current = g.current_amount or Decimal("0")
                pct = float(current / target * 100) if target > 0 else 0.0

                # Beräkna months_remaining + monthly_pace_target
                months_remaining: Optional[int] = None
                monthly_pace: Optional[Decimal] = None
                expected_pct: Optional[float] = None

                if g.target_date is not None:
                    days_remaining = (g.target_date - today).days
                    months_remaining = max(0, days_remaining // 30)
                    if days_remaining > 0 and current < target:
                        # Vad som krävs/mån för att hinna
                        if months_remaining > 0:
                            monthly_pace = (target - current) / Decimal(
                                months_remaining
                            )
                            monthly_pace_total += monthly_pace
                        else:
                            # Mindre än en månad kvar — rapportera diffen
                            monthly_pace = target - current

                # Status
                if current >= target and target > 0:
                    status: str = "complete"
                elif pct < 5:
                    status = "new"
                elif expected_pct is not None:
                    diff = pct - expected_pct
                    if diff > 10:
                        status = "ahead"
                    elif diff < -10:
                        status = "behind"
                        behind_count += 1
                    else:
                        status = "on_track"
                        on_track_count += 1
                else:
                    # Ingen deadline — kategorisera enbart på progress
                    if pct > 50:
                        status = "on_track"
                        on_track_count += 1
                    else:
                        status = "new"

                color, icon = _goal_color_icon(g.name)

                rows.append(V2GoalRow(
                    id=g.id,
                    name=g.name,
                    icon=icon,
                    target_amount=float(target),
                    current_amount=float(current),
                    target_date=g.target_date,
                    progress_pct=round(pct, 1),
                    months_remaining=months_remaining,
                    monthly_pace_target=(
                        float(monthly_pace) if monthly_pace else None
                    ),
                    expected_progress_pct=(
                        round(expected_pct, 1) if expected_pct is not None else None
                    ),
                    account_name=accounts.get(g.account_id) if g.account_id else None,
                    status=status,  # type: ignore[arg-type]
                    color=color,
                ))

                total_saved += current
                total_target += target

            overall_pct = (
                float(total_saved / total_target * 100)
                if total_target > 0 else 0.0
            )

            return V2GoalsResponse(
                student_id=info.student_id,
                summary=V2GoalsSummary(
                    total_saved=float(total_saved),
                    total_target=float(total_target),
                    overall_progress_pct=round(overall_pct, 1),
                    monthly_pace_total=float(monthly_pace_total),
                    goals_count=len(rows),
                    on_track_count=on_track_count,
                    behind_count=behind_count,
                ),
                goals=rows,
            )
    except Exception:
        return _empty_goals(info.student_id)


# === Postlådan (MailItem-tabellen) ===

MailType = Literal["invoice", "salary_slip", "authority", "reminder", "info"]
MailStatus = Literal["unhandled", "viewed", "exported", "paid", "expired"]
MailSenderKind = Literal[
    "bank", "cred", "skv", "ins", "land", "util", "work", "pen", "other",
]


class V2MailItemRow(BaseModel):
    id: int
    sender: str
    sender_short: Optional[str] = None
    sender_kind: MailSenderKind
    sender_meta: Optional[str] = None
    mail_type: MailType
    subject: str
    body_meta: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[_date] = None
    received_at: datetime
    status: MailStatus
    upcoming_id: Optional[int] = None
    transaction_id: Optional[int] = None
    is_recurring: bool
    ocr_reference: Optional[str] = None
    bankgiro: Optional[str] = None


class V2MailSummary(BaseModel):
    total_count: int
    unhandled_count: int
    invoice_count: int
    salary_slip_count: int
    authority_count: int
    info_count: int
    other_count: int  # reminder + ev. övrigt
    to_pay_amount: float
    incoming_amount: float
    overdue_count: int
    spend_profile: str
    last_received_at: Optional[datetime] = None
    next_due_date: Optional[_date] = None


class V2MailResponse(BaseModel):
    student_id: int
    summary: V2MailSummary
    items: list[V2MailItemRow]


def _empty_mail(student_id: int) -> V2MailResponse:
    return V2MailResponse(
        student_id=student_id,
        summary=V2MailSummary(
            total_count=0,
            unhandled_count=0,
            invoice_count=0,
            salary_slip_count=0,
            authority_count=0,
            info_count=0,
            other_count=0,
            to_pay_amount=0,
            incoming_amount=0,
            overdue_count=0,
            spend_profile="balanserad",
        ),
        items=[],
    )


@router.get("/postladan", response_model=V2MailResponse)
def get_mail(
    filter: Optional[str] = None,
    info: TokenInfo = Depends(require_token),
) -> V2MailResponse:
    """Postlådan · alla brev sorterade nyaste först.

    `filter` kan vara: "unhandled", "invoice", "salary_slip",
    "authority", "info", eller None (alla).

    Demo/teacher får tom payload.
    """
    if info.role != "student" or info.student_id is None:
        return _empty_mail(0)

    # Hämta spend_profile från student-tabellen för header-meta
    spend_profile = "balanserad"
    with master_session() as mdb:
        st = mdb.get(Student, info.student_id)
        if st:
            spend_profile = (
                getattr(st, "v2_spend_profile", None) or "balanserad"
            )

    try:
        with session_scope() as s:
            q = s.query(MailItem).order_by(
                MailItem.received_at.desc(), MailItem.id.desc()
            )
            if filter == "unhandled":
                q = q.filter(MailItem.status == "unhandled")
            elif filter == "invoice":
                q = q.filter(MailItem.mail_type == "invoice")
            elif filter == "salary_slip":
                q = q.filter(MailItem.mail_type == "salary_slip")
            elif filter == "authority":
                q = q.filter(MailItem.mail_type == "authority")
            elif filter == "info":
                q = q.filter(MailItem.mail_type == "info")
            elif filter == "other":
                q = q.filter(MailItem.mail_type.in_(("reminder",)))

            mails = q.all()
            items: list[V2MailItemRow] = []

            # Summary räknar ALLTID på alla mail (inte filtrerade), så
            # tab-counts visas korrekt även när man har en aktiv filter.
            all_mails = (
                s.query(MailItem)
                .order_by(MailItem.received_at.desc())
                .all()
                if filter else mails
            )

            today = _date.today()
            unhandled_count = 0
            invoice_count = 0
            salary_slip_count = 0
            authority_count = 0
            info_count = 0
            other_count = 0
            to_pay = Decimal("0")
            incoming = Decimal("0")
            overdue = 0
            last_received: Optional[datetime] = None
            next_due: Optional[_date] = None

            for m in all_mails:
                if m.status == "unhandled":
                    unhandled_count += 1
                if m.mail_type == "invoice":
                    invoice_count += 1
                elif m.mail_type == "salary_slip":
                    salary_slip_count += 1
                elif m.mail_type == "authority":
                    authority_count += 1
                elif m.mail_type == "info":
                    info_count += 1
                else:
                    other_count += 1  # reminder + ev. okända typer
                if (
                    m.amount is not None
                    and m.amount < 0
                    and m.status not in ("paid",)
                ):
                    to_pay += -m.amount
                if (
                    m.amount is not None
                    and m.amount > 0
                    and m.status not in ("paid",)
                ):
                    incoming += m.amount
                if (
                    m.due_date is not None
                    and m.due_date < today
                    and m.status not in ("paid", "exported")
                ):
                    overdue += 1
                if last_received is None or m.received_at > last_received:
                    last_received = m.received_at
                if (
                    m.due_date is not None
                    and m.due_date >= today
                    and m.status not in ("paid",)
                    and (next_due is None or m.due_date < next_due)
                ):
                    next_due = m.due_date

            for m in mails:
                items.append(V2MailItemRow(
                    id=m.id,
                    sender=m.sender,
                    sender_short=m.sender_short,
                    sender_kind=m.sender_kind,  # type: ignore[arg-type]
                    sender_meta=m.sender_meta,
                    mail_type=m.mail_type,  # type: ignore[arg-type]
                    subject=m.subject,
                    body_meta=m.body_meta,
                    amount=float(m.amount) if m.amount is not None else None,
                    due_date=m.due_date,
                    received_at=m.received_at,
                    status=m.status,  # type: ignore[arg-type]
                    upcoming_id=m.upcoming_id,
                    transaction_id=m.transaction_id,
                    is_recurring=bool(m.is_recurring),
                    ocr_reference=m.ocr_reference,
                    bankgiro=m.bankgiro,
                ))

            return V2MailResponse(
                student_id=info.student_id,
                summary=V2MailSummary(
                    total_count=len(all_mails),
                    unhandled_count=unhandled_count,
                    invoice_count=invoice_count,
                    salary_slip_count=salary_slip_count,
                    authority_count=authority_count,
                    info_count=info_count,
                    other_count=other_count,
                    to_pay_amount=float(to_pay),
                    incoming_amount=float(incoming),
                    overdue_count=overdue,
                    spend_profile=spend_profile,
                    last_received_at=last_received,
                    next_due_date=next_due,
                ),
                items=items,
            )
    except Exception:
        return _empty_mail(info.student_id)


class V2MailStatusUpdate(BaseModel):
    status: MailStatus


@router.patch(
    "/postladan/{mail_id}/status",
    response_model=V2MailItemRow,
)
def update_mail_status(
    mail_id: int,
    body: V2MailStatusUpdate,
    info: TokenInfo = Depends(require_token),
) -> V2MailItemRow:
    """Eleven uppdaterar status på ett brev (öppnar = viewed,
    exporterar = exported, etc.)."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast eleven själv kan uppdatera brev-status.",
        )

    with session_scope() as s:
        m = s.get(MailItem, mail_id)
        if m is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Brevet hittades inte"
            )
        m.status = body.status
        s.flush()
        return V2MailItemRow(
            id=m.id,
            sender=m.sender,
            sender_short=m.sender_short,
            sender_kind=m.sender_kind,  # type: ignore[arg-type]
            sender_meta=m.sender_meta,
            mail_type=m.mail_type,  # type: ignore[arg-type]
            subject=m.subject,
            body_meta=m.body_meta,
            amount=float(m.amount) if m.amount is not None else None,
            due_date=m.due_date,
            received_at=m.received_at,
            status=m.status,  # type: ignore[arg-type]
            upcoming_id=m.upcoming_id,
            transaction_id=m.transaction_id,
            is_recurring=bool(m.is_recurring),
            ocr_reference=m.ocr_reference,
            bankgiro=m.bankgiro,
        )


# === Lärar-seed för postlådan ===

class V2MailSeedItem(BaseModel):
    sender: str
    sender_short: Optional[str] = None
    sender_kind: MailSenderKind = "other"
    sender_meta: Optional[str] = None
    mail_type: MailType
    subject: str
    body_meta: Optional[str] = None
    body: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[_date] = None
    is_recurring: bool = False
    ocr_reference: Optional[str] = None
    bankgiro: Optional[str] = None


class V2MailSeedRequest(BaseModel):
    items: list[V2MailSeedItem]
    replace_existing: bool = False


class V2MailSeedResponse(BaseModel):
    student_id: int
    created: int
    deleted: int


@router.post(
    "/teacher/students/{student_id}/mail-seed",
    response_model=V2MailSeedResponse,
)
def seed_mail_for_student(
    student_id: int,
    body: V2MailSeedRequest,
    info: TokenInfo = Depends(require_token),
) -> V2MailSeedResponse:
    """Lärare seedar mail-rader till elevens postlåda.

    `replace_existing=True` → tömmer postlådan först. Annars läggs
    nya mail till befintliga.

    Bara elevens egen lärare får göra detta.
    """
    if info.role != "teacher" or info.teacher_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Endast lärare kan seeda postlådan."
        )

    # Verifiera att eleven tillhör läraren
    from ..school.engines import scope_context, scope_for_student
    with master_session() as mdb:
        student = mdb.get(Student, student_id)
        if student is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Eleven hittades inte"
            )
        if student.teacher_id != info.teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Du kan bara seeda till dina egna elever.",
            )
        scope_key = scope_for_student(student)

    # Skriv till elevens scope-DB
    deleted = 0
    created = 0
    with scope_context(scope_key):
        with session_scope() as s:
            if body.replace_existing:
                deleted = s.query(MailItem).delete()
            for item in body.items:
                amount = (
                    Decimal(str(item.amount))
                    if item.amount is not None else None
                )
                s.add(MailItem(
                    sender=item.sender,
                    sender_short=item.sender_short,
                    sender_kind=item.sender_kind,
                    sender_meta=item.sender_meta,
                    mail_type=item.mail_type,
                    subject=item.subject,
                    body_meta=item.body_meta,
                    body=item.body,
                    amount=amount,
                    due_date=item.due_date,
                    is_recurring=item.is_recurring,
                    ocr_reference=item.ocr_reference,
                    bankgiro=item.bankgiro,
                    status="unhandled",
                ))
                created += 1

    return V2MailSeedResponse(
        student_id=student_id,
        created=created,
        deleted=deleted,
    )


# === Arbetsgivaren (/v2/arbetsgivaren) ===

class V2EmployerSalarySlip(BaseModel):
    """En lönespec — härledd från transactions där category='Lön' och
    amount > 0. För framtid: separat SalarySlip-tabell med brutto/skatt
    explicit. För nu räknar vi netto från transaktionen och uppskattar
    brutto via _safe_profile_attr(gross_salary_monthly)."""
    id: int
    month: str
    date: _date
    net_amount: float
    gross_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    pension_amount: Optional[float] = None
    description: str


class V2EmployerAgreementBenefit(BaseModel):
    """En rad i kollektivavtals-tabellen ("Kollektivavtalet · vad det säger").

    Kan komma från CollectiveAgreement.meta JSON eller från en
    default-mappning baserad på agreement.code."""
    name: str
    detail: str
    value: str


class V2EmployerNegotiation(BaseModel):
    id: int
    status: str  # active | completed | abandoned
    round_no: int  # senaste rond
    max_rounds: int
    starting_salary: float
    requested_salary: Optional[float] = None  # från senaste rond
    proposed_pct: Optional[float] = None  # AI:ns senaste bud
    avtal_norm_pct: Optional[float] = None
    final_salary: Optional[float] = None
    final_pct: Optional[float] = None
    started_at: datetime
    completed_at: Optional[datetime] = None


class V2EmployerQuestionRow(BaseModel):
    id: int  # answer-id (eller 0 om obesvarad)
    question_id: int
    question_text: str
    difficulty: str  # "easy" | "medium" | "hard"
    answered_at: Optional[datetime] = None
    student_answer: Optional[str] = None
    delta: Optional[int] = None  # ±N nöjdhet-poäng
    is_open: bool  # True om obesvarad → "Svara nu"


class V2EmployerSatisfaction(BaseModel):
    score: int
    trend: str  # rising | falling | stable
    delta_4w: int  # förändring senaste 4 veckor


class V2EmployerResponse(BaseModel):
    student_id: int
    profession: str
    employer: str
    agreement_name: Optional[str] = None
    agreement_union: Optional[str] = None
    gross_salary_monthly: float
    net_salary_monthly: float
    pension_pct: Optional[float] = None
    pension_monthly: Optional[float] = None
    employed_since: Optional[_date] = None
    next_revision_date: Optional[_date] = None
    market_low: Optional[float] = None
    market_high: Optional[float] = None
    satisfaction: V2EmployerSatisfaction
    negotiation: Optional[V2EmployerNegotiation] = None
    salary_slips: list[V2EmployerSalarySlip]
    agreement_benefits: list[V2EmployerAgreementBenefit]
    questions: list[V2EmployerQuestionRow]
    open_question_id: Optional[int] = None


def _empty_employer(student_id: int) -> V2EmployerResponse:
    return V2EmployerResponse(
        student_id=student_id,
        profession="—",
        employer="—",
        gross_salary_monthly=0,
        net_salary_monthly=0,
        satisfaction=V2EmployerSatisfaction(
            score=70, trend="stable", delta_4w=0,
        ),
        salary_slips=[],
        agreement_benefits=[],
        questions=[],
    )


def _agreement_benefits_from_db(
    mdb: Session,
    agreement: Optional[CollectiveAgreement],
) -> list[V2EmployerAgreementBenefit]:
    """Hämta strukturerade kollektivavtals-förmåner från
    AgreementBenefit-tabellen.

    Returnerar tom lista om avtalet saknar seedade förmåner — då
    visar frontend en "Snart"-state istället för defaults.
    """
    out: list[V2EmployerAgreementBenefit] = []
    if agreement is None:
        return out
    rows = (
        mdb.query(AgreementBenefit)
        .filter(AgreementBenefit.agreement_id == agreement.id)
        .order_by(AgreementBenefit.sort_order, AgreementBenefit.id)
        .all()
    )
    for r in rows:
        out.append(V2EmployerAgreementBenefit(
            name=r.name,
            detail=r.detail or "",
            value=r.value,
        ))
    return out


def _market_range_from_db(
    mdb: Session,
    profession: str,
    city: Optional[str],
    year: int,
) -> tuple[Optional[float], Optional[float]]:
    """Slå upp marknadsspann från MarketSalaryRange-tabellen.

    Försök i ordning:
    1. (profession, city, year, "alla")
    2. (profession, city, närmaste år)
    3. (profession, "Stockholm", year) som fallback
    Returnerar (None, None) om inget hittas — då visas inte side-card.
    """
    if not profession:
        return None, None
    q = (
        mdb.query(MarketSalaryRange)
        .filter(MarketSalaryRange.profession == profession)
    )
    if city:
        q1 = q.filter(
            MarketSalaryRange.city == city,
            MarketSalaryRange.year == year,
        ).first()
        if q1:
            return float(q1.low), float(q1.high)
        # Närmaste år
        q2 = (
            q.filter(MarketSalaryRange.city == city)
            .order_by(MarketSalaryRange.year.desc())
            .first()
        )
        if q2:
            return float(q2.low), float(q2.high)
    # Stockholm-fallback
    q3 = (
        mdb.query(MarketSalaryRange)
        .filter(
            MarketSalaryRange.profession == profession,
            MarketSalaryRange.city == "Stockholm",
        )
        .order_by(MarketSalaryRange.year.desc())
        .first()
    )
    if q3:
        return float(q3.low), float(q3.high)
    return None, None


def _difficulty_label(diff: object) -> str:
    """Mappar WorkplaceQuestion.difficulty (INT 1-5) till
    visuell etikett. 1-2 = easy, 3 = medium, 4-5 = hard."""
    if diff is None:
        return "medium"
    try:
        n = int(diff)
        if n <= 2:
            return "easy"
        if n >= 4:
            return "hard"
        return "medium"
    except (TypeError, ValueError):
        return "medium"


def _short_question_text(scenario_md: str, max_len: int = 120) -> str:
    """Plocka första meningen ur scenario_md som rubrik. Tar bort
    markdown-tecken och citationstecken så det blir läsbart i en
    tabell-rad."""
    if not scenario_md:
        return ""
    # Första meningen (innan första punkt eller radbrytning)
    first = scenario_md.split("\n", 1)[0].split(". ", 1)[0]
    first = first.replace("**", "").replace("*", "").strip()
    if len(first) > max_len:
        first = first[: max_len - 1].rstrip() + "…"
    return first


@router.get("/arbetsgivaren", response_model=V2EmployerResponse)
def get_employer(
    info: TokenInfo = Depends(require_token),
) -> V2EmployerResponse:
    """Aggregat-endpoint för arbetsgivar-vyn (/v2/arbetsgivaren).

    Sammanställer i ett anrop:
    - Profil (yrke, arbetsgivare, lön) från StudentProfile
    - Kollektivavtal (ITP1, friskvård, OB, lönerevision) från
      ProfessionAgreement + CollectiveAgreement
    - Lönespecar (senaste 4 mån) från Transaction där amount > 0 och
      raw_description innehåller "lön"
    - Aktiv eller senaste lönesamtal från SalaryNegotiation
    - Frågor från arbetsgivaren från WorkplaceQuestionAnswer (5 senaste)
      + WorkplaceQuestion (nästa öppna)
    - Nöjdhet (score, trend, delta_4w) från EmployerSatisfaction +
      EmployerSatisfactionEvent

    Demo/teacher får tom payload.
    Try/except runt scope-anrop → tom payload utan crash.
    """
    if info.role != "student" or info.student_id is None:
        return _empty_employer(0)

    with master_session() as mdb:
        student = mdb.get(Student, info.student_id)
        if not student:
            return _empty_employer(0)
        profile = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == info.student_id)
            .first()
        )
        if not profile:
            return _empty_employer(info.student_id)

        # Hitta avtal via profession (ProfessionAgreement-mapping)
        prof_agr = (
            mdb.query(ProfessionAgreement)
            .filter(ProfessionAgreement.profession == profile.profession)
            .first()
        )
        agreement = None
        if prof_agr:
            agreement = mdb.get(CollectiveAgreement, prof_agr.agreement_id)

        agreement_name = agreement.name if agreement else None
        agreement_union = agreement.union if agreement else None
        pension_pct = (
            float(prof_agr.pension_rate_pct)
            if prof_agr and prof_agr.pension_rate_pct is not None
            else None
        )

        # Avtal-norm för lönerevisions-procent (i meta JSON)
        avtal_norm_pct: Optional[float] = None
        if agreement and agreement.meta:
            try:
                avtal_norm_pct = float(agreement.meta.get("norm_pct") or 0) or None
            except Exception:
                avtal_norm_pct = None

        gross = float(profile.gross_salary_monthly or 0)
        net = float(profile.net_salary_monthly or 0)
        pension_monthly = (
            round(gross * (pension_pct / 100), 2)
            if pension_pct else None
        )

        # Marknadsspann från MarketSalaryRange (Fas 2C). Söker
        # (profession, city, current_year). Faller tillbaka på
        # närmaste år eller Stockholm. Returnerar (None, None) om
        # inget seedat — frontend visar då inte side-card.
        from datetime import date as _d_market
        market_low, market_high = _market_range_from_db(
            mdb, profile.profession, profile.city,
            _d_market.today().year,
        )

        # Anställd sedan / lönerevision — hämta från CollectiveAgreement.meta
        # om strukturerat. Annars lämna None.
        employed_since: Optional[_date] = None
        next_revision: Optional[_date] = None
        if agreement and agreement.meta:
            try:
                if agreement.meta.get("review_month"):
                    today = _date.today()
                    rm = int(agreement.meta["review_month"])
                    yr = today.year if rm >= today.month else today.year + 1
                    next_revision = _date(yr, rm, 1)
            except Exception:
                pass

        # Nöjdhet
        sat_row = (
            mdb.query(EmployerSatisfaction)
            .filter(EmployerSatisfaction.student_id == info.student_id)
            .first()
        )
        if sat_row:
            sat_score = sat_row.score
            sat_trend = sat_row.trend
        else:
            sat_score = 70
            sat_trend = "stable"

        # Delta senaste 4 veckor (summa av alla event-deltas senaste 28 d)
        from datetime import timedelta as _td
        cutoff = datetime.utcnow() - _td(days=28)
        delta_4w_q = (
            mdb.query(_func.coalesce(_func.sum(EmployerSatisfactionEvent.delta_score), 0))
            .filter(EmployerSatisfactionEvent.student_id == info.student_id)
            .filter(EmployerSatisfactionEvent.ts >= cutoff)
            .scalar()
        )
        delta_4w = int(delta_4w_q or 0)

        # Aktiv eller senaste lönesamtal
        neg_row = (
            mdb.query(SalaryNegotiation)
            .filter(SalaryNegotiation.student_id == info.student_id)
            .order_by(SalaryNegotiation.started_at.desc())
            .first()
        )
        negotiation_out: Optional[V2EmployerNegotiation] = None
        if neg_row:
            last_round = (
                mdb.query(NegotiationRound)
                .filter(NegotiationRound.negotiation_id == neg_row.id)
                .order_by(NegotiationRound.round_no.desc())
                .first()
            )
            negotiation_out = V2EmployerNegotiation(
                id=neg_row.id,
                status=neg_row.status,
                round_no=last_round.round_no if last_round else 0,
                max_rounds=5,
                starting_salary=float(neg_row.starting_salary),
                requested_salary=None,  # eleven kan ha skrivit i texten
                proposed_pct=(
                    float(last_round.proposed_pct)
                    if last_round and last_round.proposed_pct is not None
                    else None
                ),
                avtal_norm_pct=neg_row.avtal_norm_pct,
                final_salary=(
                    float(neg_row.final_salary)
                    if neg_row.final_salary is not None else None
                ),
                final_pct=neg_row.final_pct,
                started_at=neg_row.started_at,
                completed_at=neg_row.completed_at,
            )

        # Frågor från arbetsgivaren — 5 senaste svar + 1 obesvarad
        answered_q = (
            mdb.query(WorkplaceQuestionAnswer, WorkplaceQuestion)
            .join(
                WorkplaceQuestion,
                WorkplaceQuestion.id == WorkplaceQuestionAnswer.question_id,
            )
            .filter(WorkplaceQuestionAnswer.student_id == info.student_id)
            .order_by(WorkplaceQuestionAnswer.answered_at.desc())
            .limit(5)
            .all()
        )
        question_rows: list[V2EmployerQuestionRow] = []
        for ans, q in answered_q:
            # Plocka elevens valda alternativ-text från options-listan
            chosen_text: Optional[str] = None
            try:
                if isinstance(q.options, list) and 0 <= ans.chosen_index < len(q.options):
                    opt = q.options[ans.chosen_index]
                    if isinstance(opt, dict):
                        chosen_text = opt.get("text")
            except Exception:
                chosen_text = None

            question_rows.append(V2EmployerQuestionRow(
                id=ans.id,
                question_id=q.id,
                question_text=_short_question_text(q.scenario_md or ""),
                difficulty=_difficulty_label(q.difficulty),
                answered_at=ans.answered_at,
                student_answer=chosen_text,
                delta=ans.delta_applied,
                is_open=False,
            ))

        # Hitta en obesvarad fråga som öppen "Svara nu"-rad
        answered_ids = {a.question_id for a, _ in answered_q}
        open_q_query = mdb.query(WorkplaceQuestion)
        if answered_ids:
            open_q_query = open_q_query.filter(
                ~WorkplaceQuestion.id.in_(answered_ids)
            )
        open_q = open_q_query.order_by(_func.random()).first()
        open_question_id: Optional[int] = None
        if open_q:
            open_question_id = open_q.id
            question_rows.insert(0, V2EmployerQuestionRow(
                id=0,
                question_id=open_q.id,
                question_text=_short_question_text(open_q.scenario_md or ""),
                difficulty=_difficulty_label(open_q.difficulty),
                answered_at=None,
                student_answer=None,
                delta=None,
                is_open=True,
            ))

        # Avtals-förmåner (från meta eller default)
        benefits = _agreement_benefits_from_db(mdb, agreement)

    # Lönespecar — från scope-DB:s transactions där amount > 0 och
    # description innehåller "lön" eller liknande, senaste 4 mån.
    salary_slips: list[V2EmployerSalarySlip] = []
    try:
        with session_scope() as s:
            today = _date.today()
            from datetime import timedelta as _td
            cutoff_d = today - _td(days=120)
            tx_rows = (
                s.query(Transaction)
                .filter(Transaction.amount > 0)
                .filter(Transaction.date >= cutoff_d)
                .filter(_func.lower(Transaction.raw_description).like("%lön%"))
                .order_by(Transaction.date.desc())
                .limit(4)
                .all()
            )
            for t in tx_rows:
                month_str = f"{t.date.year:04d}-{t.date.month:02d}"
                # Härled brutto från net via skattesats om vi har den
                net_amt = float(t.amount)
                gross_amt = (
                    float(profile.gross_salary_monthly)
                    if profile.gross_salary_monthly else None
                )
                tax_amt = (
                    round(gross_amt - net_amt, 2)
                    if gross_amt and gross_amt > net_amt else None
                )
                pension_amt = (
                    round(gross_amt * (pension_pct / 100), 2)
                    if gross_amt and pension_pct else None
                )
                salary_slips.append(V2EmployerSalarySlip(
                    id=t.id,
                    month=month_str,
                    date=t.date,
                    net_amount=net_amt,
                    gross_amount=gross_amt,
                    tax_amount=tax_amt,
                    pension_amount=pension_amt,
                    description=t.raw_description or "Lön",
                ))
    except Exception:
        # Scope-DB saknas eller fel — låt salary_slips vara tomma
        pass

    return V2EmployerResponse(
        student_id=info.student_id,
        profession=profile.profession,
        employer=profile.employer,
        agreement_name=agreement_name,
        agreement_union=agreement_union,
        gross_salary_monthly=gross,
        net_salary_monthly=net,
        pension_pct=pension_pct,
        pension_monthly=pension_monthly,
        employed_since=employed_since,
        next_revision_date=next_revision,
        market_low=market_low,
        market_high=market_high,
        satisfaction=V2EmployerSatisfaction(
            score=sat_score,
            trend=sat_trend,
            delta_4w=delta_4w,
        ),
        negotiation=negotiation_out,
        salary_slips=salary_slips,
        agreement_benefits=benefits,
        questions=question_rows,
        open_question_id=open_question_id,
    )


# === Skatten (/v2/skatten) ===

class V2TaxLineItem(BaseModel):
    """En rad i deklarationen — matchar prototypens .tx-row."""
    category: Literal["income", "deduction", "capital", "tax", "diff"]
    label: str  # vänster-kolumn, t.ex. "Inkomst", "Avdrag", "Kapital", "Skatt", "Diff"
    name: str
    detail: str
    amount: float  # signed: + för inkomst/återbäring, − för avdrag/skatt
    is_proposal: bool = False
    proposal_id: Optional[str] = None


class V2TaxDeductionRow(BaseModel):
    id: int
    year: int
    kind: str
    name: str
    description: Optional[str] = None
    amount: float
    source: str
    created_at: datetime


class V2TaxProposalRow(BaseModel):
    id: int
    year: int
    kind: str
    name: str
    description: Optional[str] = None
    suggested_amount: float
    status: Literal["pending", "approved", "rejected"]
    decided_at: Optional[datetime] = None
    deduction_id: Optional[int] = None
    source: str
    created_at: datetime


class V2TaxYearReturnOut(BaseModel):
    id: int
    year: int
    submitted_at: datetime
    locked: bool
    gross_income: float
    prelim_tax_paid: float
    deductions_total: float
    final_tax: float
    diff: float


class V2TaxResponse(BaseModel):
    student_id: int
    year: int
    deadline: Optional[_date] = None
    gross_income: float
    prelim_tax_paid: float
    final_tax: float
    diff: float  # positiv = återbäring, negativ = kvarskatt
    pending_proposal_count: int
    items: list[V2TaxLineItem]
    deductions: list[V2TaxDeductionRow] = []
    proposals: list[V2TaxProposalRow] = []
    submitted: Optional[V2TaxYearReturnOut] = None
    can_submit: bool = True


def _empty_tax(student_id: int, year: int) -> V2TaxResponse:
    return V2TaxResponse(
        student_id=student_id,
        year=year,
        gross_income=0,
        prelim_tax_paid=0,
        final_tax=0,
        diff=0,
        pending_proposal_count=0,
        items=[],
        deductions=[],
        proposals=[],
        submitted=None,
        can_submit=False,
    )


@router.get("/skatten", response_model=V2TaxResponse)
def get_skatten(
    year: Optional[int] = None,
    info: TokenInfo = Depends(require_token),
) -> V2TaxResponse:
    """Aggregat för deklarationssidan /v2/skatten.

    Beräknar (ENDAST riktig data — inga schabloner):
    - Bruttoinkomst = projekterad årslön (gross_salary_monthly × 12)
    - Förskottsinbetald skatt = från lönespec-transactions ELLER
      uppskattning (brutto × tax_rate_effective)
    - Schablonskatt ISK (FundHolding.market_value × 0,89 %) — endast
      om eleven har fonder i scope-DB
    - Slutlig skatt = preliminär + ISK-schablonskatt
    - Diff = preliminär − slutlig

    OBS · Fas 2:
    Reseavdrag, ränteavdrag (CSN/bolån) och Skatteverkets förslag
    kräver TaxDeduction- och TaxProposal-modeller som lärare/elev
    seedar med faktiska räntor och reseregister.

    Demo/teacher får tom payload.
    """
    if info.role != "student" or info.student_id is None:
        return _empty_tax(0, year or _date.today().year)

    target_year = year or _date.today().year
    deadline = _date(target_year + 1, 5, 2)  # 2 maj året efter

    with master_session() as mdb:
        student = mdb.get(Student, info.student_id)
        if not student:
            return _empty_tax(info.student_id, target_year)
        profile = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == info.student_id)
            .first()
        )
        if not profile:
            return _empty_tax(info.student_id, target_year)

        gross_monthly = float(profile.gross_salary_monthly or 0)
        gross_annual = round(gross_monthly * 12, 0)
        tax_rate = float(profile.tax_rate_effective or 0.30)
        prelim_tax = round(gross_annual * tax_rate, 0)
        net_annual = gross_annual - prelim_tax

        employer = profile.employer or "Arbetsgivare"

    # Hämta ISK-värde + lönespec-aktualer från scope-DB
    isk_value = 0.0
    actual_prelim_tax: Optional[float] = None
    try:
        with session_scope() as s:
            from datetime import date as _d2
            year_start = _d2(target_year, 1, 1)
            year_end = _d2(target_year + 1, 1, 1)

            # ISK-värde = summa fond-market_value
            isk_q = s.query(
                _func.coalesce(_func.sum(FundHolding.market_value), 0)
            ).scalar()
            isk_value = float(isk_q or 0)

            # Faktisk preliminärskatt — om vi har lönespec-transaktioner
            # där notes innehåller skatte-info. Förenklad: räkna inkomst-
            # transaktioner och anta tax_rate på dem.
            income_q = (
                s.query(_func.coalesce(_func.sum(Transaction.amount), 0))
                .filter(Transaction.amount > 0)
                .filter(Transaction.date >= year_start)
                .filter(Transaction.date < year_end)
                .filter(_func.lower(Transaction.raw_description).like("%lön%"))
                .scalar()
            )
            year_net_income = float(income_q or 0)
            if year_net_income > 0:
                # Bruttera upp via tax_rate, dra netto → preliminär skatt
                year_gross = year_net_income / max(0.001, 1 - tax_rate)
                actual_prelim_tax = round(year_gross - year_net_income, 0)
    except Exception:
        pass

    if actual_prelim_tax is not None and actual_prelim_tax > 0:
        prelim_tax = actual_prelim_tax

    # Bygg deklarationsrader (matchar prototypens 6 rader)
    items: list[V2TaxLineItem] = []
    pending_proposals = 0

    items.append(V2TaxLineItem(
        category="income",
        label="Inkomst",
        name=f"Lön · {employer}",
        detail="Kontrolluppgift KU10 · brutto helår",
        amount=gross_annual,
    ))

    # Schablonskatt ISK (0,89 % av FAKTISKT underlag från FundHolding).
    isk_tax = 0.0
    if isk_value > 0:
        isk_tax = round(isk_value * 0.0089, 0)
        items.append(V2TaxLineItem(
            category="capital",
            label="Kapital",
            name="Schablonskatt ISK",
            detail=f"Underlag {int(isk_value):,} kr × 0,89 %".replace(",", " "),
            amount=-isk_tax,
        ))

    # Hämta riktiga TaxDeduction + TaxProposal från scope-DB
    deductions_out: list[V2TaxDeductionRow] = []
    proposals_out: list[V2TaxProposalRow] = []
    submitted_out: Optional[V2TaxYearReturnOut] = None
    deductions_total_amount = Decimal("0")
    pending_proposals = 0

    try:
        with session_scope() as s:
            # Auto-generera förslag baserat på faktiska räntor i scope-DB
            # (idempotent — skapar inte dubbletter)
            auto_generate_proposals(s, target_year)

            ded_rows = (
                s.query(TaxDeduction)
                .filter(TaxDeduction.year == target_year)
                .order_by(TaxDeduction.created_at.asc())
                .all()
            )
            for d in ded_rows:
                deductions_out.append(V2TaxDeductionRow(
                    id=d.id, year=d.year, kind=d.kind,
                    name=d.name, description=d.description,
                    amount=float(d.amount), source=d.source,
                    created_at=d.created_at,
                ))
                deductions_total_amount += d.amount
                items.append(V2TaxLineItem(
                    category="deduction",
                    label="Avdrag",
                    name=d.name,
                    detail=d.description or "",
                    amount=-(float(d.amount) * 0.30),
                ))

            prop_rows = (
                s.query(TaxProposal)
                .filter(TaxProposal.year == target_year)
                .order_by(TaxProposal.created_at.asc())
                .all()
            )
            for p in prop_rows:
                proposals_out.append(V2TaxProposalRow(
                    id=p.id, year=p.year, kind=p.kind,
                    name=p.name, description=p.description,
                    suggested_amount=float(p.suggested_amount),
                    status=p.status, decided_at=p.decided_at,
                    deduction_id=p.deduction_id, source=p.source,
                    created_at=p.created_at,
                ))
                if p.status == "pending":
                    pending_proposals += 1
                    # Pending-förslag visas också i items-listan med
                    # is_proposal=True så frontend kan rendera dem som
                    # "Granska"-rader
                    items.append(V2TaxLineItem(
                        category="deduction",
                        label="Avdrag",
                        name=f"{p.name} · förslag",
                        detail=p.description or "",
                        amount=-(float(p.suggested_amount) * 0.30),
                        is_proposal=True,
                        proposal_id=str(p.id),
                    ))

            submitted_row = latest_tax_year_return(s, target_year)
            if submitted_row is not None:
                submitted_out = V2TaxYearReturnOut(
                    id=submitted_row.id,
                    year=submitted_row.year,
                    submitted_at=submitted_row.submitted_at,
                    locked=submitted_row.locked,
                    gross_income=float(submitted_row.gross_income),
                    prelim_tax_paid=float(submitted_row.prelim_tax_paid),
                    deductions_total=float(submitted_row.deductions_total),
                    final_tax=float(submitted_row.final_tax),
                    diff=float(submitted_row.diff),
                )
    except Exception:
        pass

    # Slutlig skatt = preliminär + ISK-schablon − avdrag-effekt (30 %)
    deduction_effect = round(float(deductions_total_amount) * 0.30, 0)
    final_tax = round(prelim_tax + isk_tax - deduction_effect, 0)

    items.append(V2TaxLineItem(
        category="tax",
        label="Skatt",
        name="Slutlig skatt",
        detail=(
            "Förskottsbetalt − avdragseffekt + ISK-schablon"
            if deduction_effect or isk_tax else
            "Förskottsbetalt"
        ),
        amount=-final_tax,
    ))

    diff = round(prelim_tax - final_tax, 0)
    items.append(V2TaxLineItem(
        category="diff",
        label="Diff",
        name="Återbäring" if diff >= 0 else "Kvarskatt",
        detail=f"Insatt {int(prelim_tax):,} − slutlig {int(final_tax):,}".replace(",", " "),
        amount=diff,
    ))

    return V2TaxResponse(
        student_id=info.student_id,
        year=target_year,
        deadline=deadline,
        gross_income=gross_annual,
        prelim_tax_paid=prelim_tax,
        final_tax=final_tax,
        diff=diff,
        pending_proposal_count=pending_proposals,
        items=items,
        deductions=deductions_out,
        proposals=proposals_out,
        submitted=submitted_out,
        can_submit=(submitted_out is None or not submitted_out.locked),
    )


# === Lånegivaren (/v2/lan) ===

class V2LoanCard(BaseModel):
    """Ett lån eller låneprodukt (aktivt eller möjligt) för aktör 04."""
    id: Optional[int] = None  # None om det är en möjlig produkt (CTA)
    eyebrow: str  # "Aktivt" / "Möjligt" / "Avråds"
    name: str
    detail: str
    balance: Optional[float] = None
    monthly_text: Optional[str] = None
    is_active: bool = False
    is_warning: bool = False  # gör badge röd för "avråds"


class V2LoanScheduleRow(BaseModel):
    """En rad i amorteringsplanen."""
    month: str  # YYYY-MM
    label: str  # t.ex. "Apr 2026"
    description: str
    monthly_amount: float
    capital_part: Optional[float] = None
    interest_part: Optional[float] = None
    status: str  # "betald" / "kommande" / "−312" osv


class V2CreditFactor(BaseModel):
    """Rad i kreditprövnings-tabellen."""
    factor: str
    detail: str
    value: str
    assessment: str
    severity: Literal["good", "warn", "bad", "neutral"]


class V2LoanResponse(BaseModel):
    student_id: int
    total_debt: float
    debt_ratio: float  # total_debt / annual_income
    annual_income: float
    credit_class: str  # "A" / "B" / "C" / "D" / "E"
    cards: list[V2LoanCard]
    schedule: list[V2LoanScheduleRow]
    credit_factors: list[V2CreditFactor]


def _empty_loans(student_id: int) -> V2LoanResponse:
    return V2LoanResponse(
        student_id=student_id,
        total_debt=0,
        debt_ratio=0,
        annual_income=0,
        credit_class="A",
        cards=[],
        schedule=[],
        credit_factors=[],
    )


@router.get("/lan", response_model=V2LoanResponse)
def get_loans(info: TokenInfo = Depends(require_token)) -> V2LoanResponse:
    """Aggregat för Lånegivaren (/v2/lan) — riktig data från:

    - StudentProfile (inkomst)
    - Loan-tabellen (aktiva lån + saldo via LoanMatcher)
    - LoanProduct-tabellen (möjliga produkter, lärar-seedade)
    - PaymentMark-tabellen (anmärkningar för UC-score)
    - CreditCheck-tabellen (senaste kreditprövning)
    - Transaction-tabellen (amorteringsbetalningar)

    Inga schabloner: om eleven inte har lärar-seedade låneprodukter
    visas listan tom. Om CreditCheck saknas räknas ny direkt.
    """
    if info.role != "student" or info.student_id is None:
        return _empty_loans(0)

    # Profil för bedömningar
    with master_session() as mdb:
        student = mdb.get(Student, info.student_id)
        if not student:
            return _empty_loans(0)
        profile = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == info.student_id)
            .first()
        )
        annual_gross_dec = (
            Decimal(profile.gross_salary_monthly) * 12
            if profile and profile.gross_salary_monthly else Decimal("0")
        )
        annual_gross = float(annual_gross_dec)

    cards: list[V2LoanCard] = []
    schedule: list[V2LoanScheduleRow] = []
    total_debt = Decimal("0")
    credit_class = ""
    credit_factors: list[V2CreditFactor] = []

    try:
        with session_scope() as s:
            # 1. Aktiva lån
            loans = s.query(Loan).filter(Loan.active.is_(True)).all()
            matcher = LoanMatcher(s)

            for loan in loans:
                outstanding = matcher.outstanding_balance(loan)
                total_debt += outstanding

                rate_pct = float(loan.interest_rate or 0) * 100 if (
                    loan.interest_rate is not None and loan.interest_rate < 1
                ) else float(loan.interest_rate or 0)
                amort_text = ""
                if loan.amortization_monthly:
                    amort_text = (
                        f"{int(loan.amortization_monthly)} kr/mån"
                    )
                detail_parts = []
                if loan.loan_number:
                    detail_parts.append(loan.loan_number)
                if loan.interest_rate is not None:
                    detail_parts.append(f"ränta {rate_pct:.1f} %")
                cards.append(V2LoanCard(
                    id=loan.id,
                    eyebrow="Aktivt",
                    name=loan.name,
                    detail=" · ".join(detail_parts) or loan.lender,
                    balance=float(outstanding),
                    monthly_text=amort_text or None,
                    is_active=True,
                ))

                tx_q = (
                    s.query(Transaction)
                    .filter(Transaction.loan_id == loan.id)
                    .order_by(Transaction.date.desc())
                    .limit(4)
                    .all()
                )
                for t in tx_q:
                    month_str = f"{t.date.year:04d}-{t.date.month:02d}"
                    schedule.append(V2LoanScheduleRow(
                        month=month_str,
                        label=t.date.strftime("%b %Y"),
                        description=loan.name,
                        monthly_amount=float(abs(t.amount)),
                        capital_part=None,
                        interest_part=None,
                        status="betald",
                    ))

            # 2. Möjliga låneprodukter (lärar-seedade)
            products = (
                s.query(LoanProduct)
                .filter(LoanProduct.available.is_(True))
                .order_by(LoanProduct.risk_class, LoanProduct.id)
                .all()
            )
            for p in products:
                # Hoppa över produkter som matchar aktiva lån (CSN
                # finns redan på "Aktivt"-kortet om eleven har det)
                if any(c.is_active and p.kind in (c.name.lower())
                       for c in cards):
                    continue
                rate_min = float(p.interest_rate_min) * 100
                rate_max = float(p.interest_rate_max) * 100
                rate_text = (
                    f"{rate_min:.1f} %"
                    if abs(rate_min - rate_max) < 0.001
                    else f"{rate_min:.1f}–{rate_max:.1f} %"
                )
                detail = f"{p.lender} · {rate_text}"
                if p.max_amount:
                    detail += f" · max {int(p.max_amount):,} kr".replace(
                        ",", " ",
                    )
                eyebrow = (
                    "Möjligt" if p.risk_class == "billig"
                    else "Möjligt" if p.risk_class == "medel"
                    else "Avråds"
                )
                cards.append(V2LoanCard(
                    id=None,
                    eyebrow=eyebrow,
                    name=p.name,
                    detail=detail,
                    balance=None,
                    monthly_text=p.description,
                    is_active=False,
                    is_warning=p.risk_class == "dyr",
                ))

            # 3. Kreditprövning — säkerställ att vi har en aktuell
            # CreditCheck. Räkna ny om det inte finns någon, eller om
            # senaste är äldre än 7 dagar (motsvarar UC-uppdaterings-
            # frekvens).
            from datetime import timedelta as _td
            check = latest_credit_check(s)
            stale = (
                check is None
                or (datetime.utcnow() - check.computed_at) > _td(days=7)
            )
            if stale and annual_gross_dec > 0:
                check = compute_credit_check(s, annual_gross_dec)

            if check is not None:
                credit_class = check.uc_score_class
                # Bygg credit-factors-rader från riktig data
                if annual_gross > 0 and profile is not None:
                    credit_factors.append(V2CreditFactor(
                        factor="Inkomst (årlig brutto)",
                        detail=f"{profile.employer} · {profile.profession}",
                        value=f"{int(annual_gross):,}".replace(",", " "),
                        assessment="Stabil · kollektivavtal",
                        severity="good",
                    ))
                if check.total_debt > 0:
                    debt_ratio = float(check.debt_ratio)
                    credit_factors.append(V2CreditFactor(
                        factor="Skuldkvot",
                        detail="Total skuld / årsinkomst",
                        value=f"{debt_ratio:.2f}×",
                        assessment=(
                            "Långt under tak (4,5×)" if debt_ratio < 1.5
                            else "Måttlig" if debt_ratio < 3
                            else "Hög — närmar sig tak" if debt_ratio < 4.5
                            else "Över tak — ingen mer skuld"
                        ),
                        severity=(
                            "good" if debt_ratio < 1.5
                            else "warn" if debt_ratio < 4.5
                            else "bad"
                        ),
                    ))
                # KALP-rad: senaste KALP-beräkning om den finns
                kalp = latest_kalp(s)
                if kalp is not None:
                    credit_factors.append(V2CreditFactor(
                        factor="KALP · stresstest 7 %",
                        detail=(
                            f"Lånebelopp {int(kalp.loan_amount):,} kr · "
                            f"kvar/mån {int(kalp.monthly_left_after_all):,}"
                        ).replace(",", " "),
                        value="passerad" if kalp.passed else "underkänd",
                        assessment=(
                            "Klarar månadskostnaden vid stress 7 %"
                            if kalp.passed
                            else "Klarar inte månadskostnaden — sök lägre belopp"
                        ),
                        severity="good" if kalp.passed else "bad",
                    ))
                # Betalningsanmärkningar — ALLTID med, även 0
                marks_text = (
                    f"{check.payment_marks_count} aktiv"
                    f"{'a' if check.payment_marks_count != 1 else ''}"
                    if check.payment_marks_count > 0 else "0"
                )
                credit_factors.append(V2CreditFactor(
                    factor="Betalningsanmärkningar",
                    detail="Aktiva i registret (ej utgångna)",
                    value=marks_text,
                    assessment=(
                        "Ren historik" if check.payment_marks_count == 0
                        else "Sänker UC-score · 3 år i registret"
                    ),
                    severity=(
                        "good" if check.payment_marks_count == 0 else "bad"
                    ),
                ))
                credit_factors.append(V2CreditFactor(
                    factor="UC-score",
                    detail="Senast räknad: " + check.computed_at.strftime("%Y-%m-%d"),
                    value=f"{check.uc_score_class} ({check.uc_score_value}/100)",
                    assessment=(
                        "Hög kreditvärdighet" if check.uc_score_class in ("A", "B")
                        else "Medel" if check.uc_score_class == "C"
                        else "Låg — dyra eller blockerade lån"
                    ),
                    severity=(
                        "good" if check.uc_score_class in ("A", "B")
                        else "warn" if check.uc_score_class == "C"
                        else "bad"
                    ),
                ))
    except Exception:
        # Scope-DB saknas eller fel — visa ändå profil-data
        pass

    debt_ratio_v = (
        float(total_debt) / annual_gross if annual_gross > 0 else 0.0
    )

    return V2LoanResponse(
        student_id=info.student_id,
        total_debt=float(total_debt),
        debt_ratio=round(debt_ratio_v, 2),
        annual_income=annual_gross,
        credit_class=credit_class,
        cards=cards,
        schedule=schedule,
        credit_factors=credit_factors,
    )


# === KALP-beräkning (elev kan begära) ===

class V2KALPRequest(BaseModel):
    loan_amount: float = Field(..., gt=0)
    loan_term_months: int = Field(default=300, ge=12, le=600)


class V2KALPResponse(BaseModel):
    id: int
    computed_at: datetime
    monthly_income_net: float
    monthly_housing: float
    monthly_consumer_schablon: float
    monthly_existing_debt_payments: float
    stress_test_rate: float
    loan_amount: float
    loan_term_months: int
    monthly_loan_payment_at_stress: float
    monthly_left_after_all: float
    passed: bool


@router.post("/lan/kalp", response_model=V2KALPResponse)
def post_kalp(
    body: V2KALPRequest,
    info: TokenInfo = Depends(require_token),
) -> V2KALPResponse:
    """Räkna KALP för ett tänkt lånebelopp och spara resultatet.

    Använder Finansinspektionens stresstest 7 % + Konsumentverkets
    levnadsschablon. Frontend pinger denna när eleven trycker "Räkna
    KALP" i kreditprövnings-panelen.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast elever kan räkna KALP för sin egen profil",
        )

    # Profilens fasta input
    with master_session() as mdb:
        profile = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == info.student_id)
            .first()
        )
        if not profile:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "Elev saknar profil — kör onboardingen först",
            )
        net_monthly = Decimal(profile.net_salary_monthly or 0)
        housing = Decimal(profile.housing_monthly or 0)
        family = profile.family_status or "ensam"

    from ..loans.credit import compute_kalp as _compute_kalp

    with session_scope() as s:
        kalp = _compute_kalp(
            s,
            monthly_income_net=net_monthly,
            family_status=family,
            monthly_housing=housing,
            loan_amount=Decimal(str(body.loan_amount)),
            loan_term_months=body.loan_term_months,
        )
        return V2KALPResponse(
            id=kalp.id,
            computed_at=kalp.computed_at,
            monthly_income_net=float(kalp.monthly_income_net),
            monthly_housing=float(kalp.monthly_housing),
            monthly_consumer_schablon=float(kalp.monthly_consumer_schablon),
            monthly_existing_debt_payments=float(
                kalp.monthly_existing_debt_payments,
            ),
            stress_test_rate=float(kalp.stress_test_rate),
            loan_amount=float(kalp.loan_amount),
            loan_term_months=kalp.loan_term_months,
            monthly_loan_payment_at_stress=float(
                kalp.monthly_loan_payment_at_stress,
            ),
            monthly_left_after_all=float(kalp.monthly_left_after_all),
            passed=kalp.passed,
        )


# === Lärar-endpoints för Lånegivaren (insyn + seed) ===

class V2LoanProductIn(BaseModel):
    lender: str
    name: str
    kind: Literal["csn", "bolan", "privatlan", "billan", "smslan"]
    interest_rate_min: float = Field(..., ge=0, le=1)
    interest_rate_max: float = Field(..., ge=0, le=1)
    max_amount: Optional[float] = None
    binding_required: bool = False
    description: Optional[str] = None
    risk_class: Literal["billig", "medel", "dyr"] = "medel"
    available: bool = True


class V2LoanProductOut(BaseModel):
    id: int
    lender: str
    name: str
    kind: str
    interest_rate_min: float
    interest_rate_max: float
    max_amount: Optional[float] = None
    binding_required: bool
    description: Optional[str] = None
    risk_class: str
    available: bool


class V2PaymentMarkIn(BaseModel):
    occurred_on: _date
    creditor: str
    amount: float = Field(..., ge=0)
    kind: Literal[
        "obetald-faktura", "kronofogden", "betalningsforelaggande",
    ]
    notes: Optional[str] = None
    expires_at: Optional[_date] = None


class V2PaymentMarkOut(BaseModel):
    id: int
    occurred_on: _date
    creditor: str
    amount: float
    kind: str
    notes: Optional[str] = None
    expires_at: Optional[_date] = None
    created_at: datetime


class V2TeacherCreditOverview(BaseModel):
    """Lärar-vyns sammanfattning av en elevs kreditprofil."""
    student_id: int
    student_name: str
    annual_income: float
    total_debt: float
    debt_ratio: float
    active_loans_count: int
    payment_marks: list[V2PaymentMarkOut]
    latest_credit_check: Optional[V2EmployerSatisfaction] = None  # placeholder, byts nedan
    loan_products_count: int
    available_products_count: int


class V2CreditCheckOut(BaseModel):
    id: int
    computed_at: datetime
    annual_income: float
    total_debt: float
    debt_ratio: float
    payment_marks_count: int
    running_applications: int
    uc_score_class: str
    uc_score_value: int


class V2TeacherCreditOverviewClean(BaseModel):
    student_id: int
    student_name: str
    annual_income: float
    total_debt: float
    debt_ratio: float
    active_loans_count: int
    payment_marks: list[V2PaymentMarkOut]
    latest_credit_check: Optional[V2CreditCheckOut] = None
    kalp_history: list[V2KALPResponse]
    loan_products_count: int
    available_products_count: int


def _scope_for_student(student_id: int):
    """Ladda scope-context för en specifik elev (via student-id i master)."""
    from ..school.engines import master_session as _ms, scope_context, scope_for_student
    with _ms() as m:
        st = m.get(Student, student_id)
        if not st:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Elev hittades inte",
            )
        return scope_context(scope_for_student(st)), st


@router.post(
    "/teacher/students/{student_id}/loan-products/seed-default",
    response_model=dict,
)
def teacher_seed_default_products(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Seedа default-katalogen (5 produkter) i en elevs scope-DB.

    Idempotent: redan seedade produkter hoppas över.
    """
    teacher_id = _require_teacher(info)

    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Elev hittades inte",
            )
        if st.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Du kan bara hantera dina egna elever",
            )

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            created = seed_default_loan_products(s)
    return {"student_id": student_id, "products_created": created}


@router.post(
    "/teacher/students/{student_id}/loan-products",
    response_model=V2LoanProductOut,
)
def teacher_create_loan_product(
    student_id: int,
    body: V2LoanProductIn,
    info: TokenInfo = Depends(require_token),
) -> V2LoanProductOut:
    """Skapa en låneprodukt i en specifik elevs scope-DB."""
    teacher_id = _require_teacher(info)

    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Elev hittades inte",
            )
        if st.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Endast egen elev",
            )

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            p = LoanProduct(
                lender=body.lender,
                name=body.name,
                kind=body.kind,
                interest_rate_min=Decimal(str(body.interest_rate_min)),
                interest_rate_max=Decimal(str(body.interest_rate_max)),
                max_amount=(
                    Decimal(str(body.max_amount)) if body.max_amount else None
                ),
                binding_required=body.binding_required,
                description=body.description,
                risk_class=body.risk_class,
                available=body.available,
            )
            s.add(p)
            s.flush()
            return V2LoanProductOut(
                id=p.id,
                lender=p.lender,
                name=p.name,
                kind=p.kind,
                interest_rate_min=float(p.interest_rate_min),
                interest_rate_max=float(p.interest_rate_max),
                max_amount=float(p.max_amount) if p.max_amount else None,
                binding_required=p.binding_required,
                description=p.description,
                risk_class=p.risk_class,
                available=p.available,
            )


@router.post(
    "/teacher/students/{student_id}/payment-marks",
    response_model=V2PaymentMarkOut,
)
def teacher_create_payment_mark(
    student_id: int,
    body: V2PaymentMarkIn,
    info: TokenInfo = Depends(require_token),
) -> V2PaymentMarkOut:
    """Lägg till en betalningsanmärkning på elevens kreditprofil.

    Triggar omberäkning av wellbeing nästa gång calculate_wellbeing
    körs (sker automatiskt via /v2/hub).
    """
    teacher_id = _require_teacher(info)

    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from datetime import timedelta as _td2
    expires_at = body.expires_at
    if expires_at is None:
        # Default: 3 år (Skatteverkets/UC-regel)
        expires_at = body.occurred_on + _td2(days=365 * 3)

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            mark = PaymentMark(
                occurred_on=body.occurred_on,
                creditor=body.creditor,
                amount=Decimal(str(body.amount)),
                kind=body.kind,
                notes=body.notes,
                expires_at=expires_at,
            )
            s.add(mark)
            s.flush()
            # Räkna ny CreditCheck så frontend ser ändringen direkt
            with master_session() as mdb2:
                profile = (
                    mdb2.query(StudentProfile)
                    .filter(StudentProfile.student_id == student_id)
                    .first()
                )
                annual_gross = (
                    Decimal(profile.gross_salary_monthly) * 12
                    if profile and profile.gross_salary_monthly
                    else Decimal("0")
                )
            if annual_gross > 0:
                compute_credit_check(s, annual_gross)

            return V2PaymentMarkOut(
                id=mark.id,
                occurred_on=mark.occurred_on,
                creditor=mark.creditor,
                amount=float(mark.amount),
                kind=mark.kind,
                notes=mark.notes,
                expires_at=mark.expires_at,
                created_at=mark.created_at,
            )


@router.delete(
    "/teacher/students/{student_id}/payment-marks/{mark_id}",
    status_code=204,
)
def teacher_delete_payment_mark(
    student_id: int,
    mark_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    """Ta bort en betalningsanmärkning (lärare kan justera scenarier)."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            mark = s.get(PaymentMark, mark_id)
            if mark is not None:
                s.delete(mark)
                s.flush()


@router.get(
    "/teacher/students/{student_id}/credit-overview",
    response_model=V2TeacherCreditOverviewClean,
)
def teacher_credit_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherCreditOverviewClean:
    """Lärar-vy: full insyn i elevens kreditprofil.

    Returnerar:
    - Inkomst + total skuld + skuldkvot
    - Aktiva betalningsanmärkningar
    - Senaste CreditCheck
    - KALP-historik (alla beräkningar eleven gjort)
    - Antal låneprodukter (totalt + tillgängliga)
    """
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        profile = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        annual_gross = (
            float(profile.gross_salary_monthly) * 12
            if profile and profile.gross_salary_monthly else 0.0
        )
        student_name = st.display_name

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            matcher = LoanMatcher(s)
            active_loans = s.query(Loan).filter(Loan.active.is_(True)).all()
            total_debt = float(sum(
                (matcher.outstanding_balance(loan) for loan in active_loans),
                Decimal("0"),
            ))
            debt_ratio = total_debt / annual_gross if annual_gross > 0 else 0.0

            from datetime import date as _d_today
            today = _d_today.today()
            marks = (
                s.query(PaymentMark)
                .filter(
                    (PaymentMark.expires_at.is_(None)) |
                    (PaymentMark.expires_at >= today)
                )
                .order_by(PaymentMark.occurred_on.desc())
                .all()
            )
            marks_out = [
                V2PaymentMarkOut(
                    id=m_.id,
                    occurred_on=m_.occurred_on,
                    creditor=m_.creditor,
                    amount=float(m_.amount),
                    kind=m_.kind,
                    notes=m_.notes,
                    expires_at=m_.expires_at,
                    created_at=m_.created_at,
                )
                for m_ in marks
            ]

            check = latest_credit_check(s)
            check_out: Optional[V2CreditCheckOut] = None
            if check is not None:
                check_out = V2CreditCheckOut(
                    id=check.id,
                    computed_at=check.computed_at,
                    annual_income=float(check.annual_income),
                    total_debt=float(check.total_debt),
                    debt_ratio=float(check.debt_ratio),
                    payment_marks_count=check.payment_marks_count,
                    running_applications=check.running_applications,
                    uc_score_class=check.uc_score_class,
                    uc_score_value=check.uc_score_value,
                )

            kalp_rows = (
                s.query(KALPCalculation)
                .order_by(KALPCalculation.computed_at.desc())
                .limit(20)
                .all()
            )
            kalp_history = [
                V2KALPResponse(
                    id=k.id,
                    computed_at=k.computed_at,
                    monthly_income_net=float(k.monthly_income_net),
                    monthly_housing=float(k.monthly_housing),
                    monthly_consumer_schablon=float(k.monthly_consumer_schablon),
                    monthly_existing_debt_payments=float(
                        k.monthly_existing_debt_payments,
                    ),
                    stress_test_rate=float(k.stress_test_rate),
                    loan_amount=float(k.loan_amount),
                    loan_term_months=k.loan_term_months,
                    monthly_loan_payment_at_stress=float(
                        k.monthly_loan_payment_at_stress,
                    ),
                    monthly_left_after_all=float(k.monthly_left_after_all),
                    passed=k.passed,
                )
                for k in kalp_rows
            ]

            products_total = s.query(LoanProduct).count()
            products_available = (
                s.query(LoanProduct)
                .filter(LoanProduct.available.is_(True))
                .count()
            )

    return V2TeacherCreditOverviewClean(
        student_id=student_id,
        student_name=student_name,
        annual_income=annual_gross,
        total_debt=total_debt,
        debt_ratio=round(debt_ratio, 3),
        active_loans_count=len(active_loans),
        payment_marks=marks_out,
        latest_credit_check=check_out,
        kalp_history=kalp_history,
        loan_products_count=products_total,
        available_products_count=products_available,
    )


# === Skatten · elev + lärar-endpoints (Fas 2B) ===

class V2TaxDeductionIn(BaseModel):
    year: int = Field(..., ge=2020, le=2100)
    kind: Literal[
        "rese", "bolane-ranta", "csn-ranta", "dubbel-bosattning",
        "rot", "rut", "fackavgift", "ovrig",
    ]
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    amount: float = Field(..., ge=0)


class V2TaxProposalIn(BaseModel):
    year: int = Field(..., ge=2020, le=2100)
    kind: Literal[
        "rese", "bolane-ranta", "csn-ranta", "dubbel-bosattning",
        "rot", "rut", "fackavgift", "ovrig",
    ]
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    suggested_amount: float = Field(..., ge=0)


class V2TaxSubmitResponse(BaseModel):
    return_id: int
    year: int
    submitted_at: datetime
    locked: bool
    final_tax: float
    diff: float


@router.post("/skatten/deductions", response_model=V2TaxDeductionRow)
def post_tax_deduction(
    body: V2TaxDeductionIn,
    info: TokenInfo = Depends(require_token),
) -> V2TaxDeductionRow:
    """Eleven registrerar ett deklarations-avdrag (rese, fackavgift osv).

    Avdraget är BRUTTO. Skatte-effekten räknas som amount × 0,30
    vid GET /v2/skatten.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Endast elever kan registrera avdrag",
        )

    with session_scope() as s:
        d = TaxDeduction(
            year=body.year,
            kind=body.kind,
            name=body.name,
            description=body.description,
            amount=Decimal(str(body.amount)),
            source="manual",
        )
        s.add(d)
        s.flush()
        return V2TaxDeductionRow(
            id=d.id, year=d.year, kind=d.kind,
            name=d.name, description=d.description,
            amount=float(d.amount), source=d.source,
            created_at=d.created_at,
        )


@router.delete("/skatten/deductions/{deduction_id}", status_code=204)
def delete_tax_deduction(
    deduction_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    """Eleven tar bort sitt egna avdrag."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Endast elever kan ta bort avdrag",
        )
    with session_scope() as s:
        d = s.get(TaxDeduction, deduction_id)
        if d is not None:
            # Om den är kopplad till en TaxProposal: nolla deduction_id
            prop = (
                s.query(TaxProposal)
                .filter(TaxProposal.deduction_id == deduction_id)
                .first()
            )
            if prop is not None:
                prop.deduction_id = None
                # Återställ till pending så det dyker upp igen som förslag
                prop.status = "pending"
                prop.decided_at = None
            s.delete(d)
            s.flush()


@router.post(
    "/skatten/proposals/{proposal_id}/decision",
    response_model=V2TaxProposalRow,
)
def post_tax_proposal_decision(
    proposal_id: int,
    body: dict,
    info: TokenInfo = Depends(require_token),
) -> V2TaxProposalRow:
    """Eleven godkänner eller avvisar ett förslag.

    body = {"decision": "approve" | "reject"}.
    Approve → skapar matchande TaxDeduction.
    Reject → markerar status=rejected, tar bort ev. tidigare deduction.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elev")
    decision = (body or {}).get("decision")
    if decision not in ("approve", "reject"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "decision måste vara 'approve' eller 'reject'",
        )

    with session_scope() as s:
        proposal = (
            approve_proposal(s, proposal_id) if decision == "approve"
            else reject_proposal(s, proposal_id)
        )
        if proposal is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Förslag hittades inte",
            )
        return V2TaxProposalRow(
            id=proposal.id, year=proposal.year, kind=proposal.kind,
            name=proposal.name, description=proposal.description,
            suggested_amount=float(proposal.suggested_amount),
            status=proposal.status, decided_at=proposal.decided_at,
            deduction_id=proposal.deduction_id, source=proposal.source,
            created_at=proposal.created_at,
        )


@router.post("/skatten/{year}/submit", response_model=V2TaxSubmitResponse)
def post_submit_tax_year(
    year: int,
    info: TokenInfo = Depends(require_token),
) -> V2TaxSubmitResponse:
    """Eleven lämnar in deklarationen — låser året.

    Sparar TaxYearReturn med snapshot av siffrorna. Wellbeing-
    beräkningen plockar upp denna och ger +3 economy om i tid +
    bonus/penalty på diff.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elev")

    with master_session() as mdb:
        profile = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == info.student_id)
            .first()
        )
        if not profile:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Elev saknar profil",
            )
        gross_monthly = (
            Decimal(profile.gross_salary_monthly)
            if profile.gross_salary_monthly else None
        )
        tax_rate = (
            Decimal(str(profile.tax_rate_effective))
            if profile.tax_rate_effective else None
        )

    with session_scope() as s:
        ret = submit_tax_year(s, year, gross_monthly, tax_rate)
        return V2TaxSubmitResponse(
            return_id=ret.id,
            year=ret.year,
            submitted_at=ret.submitted_at,
            locked=ret.locked,
            final_tax=float(ret.final_tax),
            diff=float(ret.diff),
        )


# Lärar-endpoints
@router.post(
    "/teacher/students/{student_id}/tax-proposals",
    response_model=V2TaxProposalRow,
)
def teacher_create_tax_proposal(
    student_id: int,
    body: V2TaxProposalIn,
    info: TokenInfo = Depends(require_token),
) -> V2TaxProposalRow:
    """Lärare skapar ett TaxProposal för en specifik elev."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            p = TaxProposal(
                year=body.year,
                kind=body.kind,
                name=body.name,
                description=body.description,
                suggested_amount=Decimal(str(body.suggested_amount)),
                status="pending",
                source="manual",
            )
            s.add(p)
            s.flush()
            return V2TaxProposalRow(
                id=p.id, year=p.year, kind=p.kind,
                name=p.name, description=p.description,
                suggested_amount=float(p.suggested_amount),
                status=p.status, decided_at=p.decided_at,
                deduction_id=p.deduction_id, source=p.source,
                created_at=p.created_at,
            )


@router.post(
    "/teacher/students/{student_id}/tax-proposals/auto-generate",
    response_model=dict,
)
def teacher_auto_generate_tax_proposals(
    student_id: int,
    year: Optional[int] = None,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Lärare ber systemet auto-generera förslag baserat på riktig
    data (Loan-räntor, ISK-schablon). Idempotent — befintliga förslag
    skapas inte igen."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    target_year = year or _date.today().year
    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            n = auto_generate_proposals(s, target_year)
    return {"student_id": student_id, "year": target_year, "created": n}


@router.delete(
    "/teacher/students/{student_id}/tax-proposals/{proposal_id}",
    status_code=204,
)
def teacher_delete_tax_proposal(
    student_id: int,
    proposal_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    """Lärare tar bort ett TaxProposal."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            p = s.get(TaxProposal, proposal_id)
            if p is None:
                return
            # Om approved: ta även bort kopplad deduction
            if p.deduction_id:
                d = s.get(TaxDeduction, p.deduction_id)
                if d:
                    s.delete(d)
            s.delete(p)
            s.flush()


class V2TeacherTaxOverview(BaseModel):
    student_id: int
    student_name: str
    year: int
    gross_income: float
    prelim_tax_paid: float
    deductions_total: float
    final_tax: float
    diff: float
    deductions: list[V2TaxDeductionRow]
    proposals: list[V2TaxProposalRow]
    submitted: Optional[V2TaxYearReturnOut] = None


@router.get(
    "/teacher/students/{student_id}/tax-overview",
    response_model=V2TeacherTaxOverview,
)
def teacher_tax_overview(
    student_id: int,
    year: Optional[int] = None,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherTaxOverview:
    """Lärar-vy · full insyn i elevens deklaration för året."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        student_name = st.display_name
        profile = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        gross_monthly = (
            Decimal(profile.gross_salary_monthly)
            if profile and profile.gross_salary_monthly else None
        )
        tax_rate = (
            Decimal(str(profile.tax_rate_effective))
            if profile and profile.tax_rate_effective else None
        )

    target_year = year or _date.today().year
    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            # Auto-genera proposals så lärar-vyn alltid är aktuell
            auto_generate_proposals(s, target_year)
            summary = compute_tax_summary(
                s, target_year, gross_monthly, tax_rate,
            )
            ded_rows = (
                s.query(TaxDeduction)
                .filter(TaxDeduction.year == target_year)
                .order_by(TaxDeduction.created_at.asc())
                .all()
            )
            prop_rows = (
                s.query(TaxProposal)
                .filter(TaxProposal.year == target_year)
                .order_by(TaxProposal.created_at.asc())
                .all()
            )
            ret = latest_tax_year_return(s, target_year)

            ded_out = [
                V2TaxDeductionRow(
                    id=d.id, year=d.year, kind=d.kind,
                    name=d.name, description=d.description,
                    amount=float(d.amount), source=d.source,
                    created_at=d.created_at,
                )
                for d in ded_rows
            ]
            prop_out = [
                V2TaxProposalRow(
                    id=p.id, year=p.year, kind=p.kind,
                    name=p.name, description=p.description,
                    suggested_amount=float(p.suggested_amount),
                    status=p.status, decided_at=p.decided_at,
                    deduction_id=p.deduction_id, source=p.source,
                    created_at=p.created_at,
                )
                for p in prop_rows
            ]
            ret_out = (
                V2TaxYearReturnOut(
                    id=ret.id, year=ret.year,
                    submitted_at=ret.submitted_at, locked=ret.locked,
                    gross_income=float(ret.gross_income),
                    prelim_tax_paid=float(ret.prelim_tax_paid),
                    deductions_total=float(ret.deductions_total),
                    final_tax=float(ret.final_tax),
                    diff=float(ret.diff),
                ) if ret else None
            )

    return V2TeacherTaxOverview(
        student_id=student_id,
        student_name=student_name,
        year=target_year,
        gross_income=summary["gross_income"],
        prelim_tax_paid=summary["prelim_tax_paid"],
        deductions_total=summary["deductions_total"],
        final_tax=summary["final_tax"],
        diff=summary["diff"],
        deductions=ded_out,
        proposals=prop_out,
        submitted=ret_out,
    )


# === Arbetsgivaren · lärar-endpoints (Fas 2C) ===

class V2AgreementBenefitIn(BaseModel):
    agreement_id: int
    kind: Literal[
        "pension", "friskvard", "ob_tillagg", "lonerevision",
        "semester", "sjuklon", "tjanstebil", "ovrig",
    ]
    name: str = Field(..., min_length=1, max_length=120)
    detail: Optional[str] = None
    value: str = Field(..., min_length=1, max_length=120)
    sort_order: int = 100


class V2AgreementBenefitOut(BaseModel):
    id: int
    agreement_id: int
    kind: str
    name: str
    detail: Optional[str] = None
    value: str
    sort_order: int


class V2MarketSalaryRangeIn(BaseModel):
    profession: str
    city: str
    year: int = Field(..., ge=2020, le=2100)
    experience_band: str = "alla"
    low: float = Field(..., ge=0)
    high: float = Field(..., ge=0)
    median: Optional[float] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class V2MarketSalaryRangeOut(BaseModel):
    id: int
    profession: str
    city: str
    year: int
    experience_band: str
    low: float
    high: float
    median: Optional[float] = None
    source: Optional[str] = None


class V2CollectiveAgreementOut(BaseModel):
    id: int
    code: str
    name: str
    union: str
    employer_org: str


@router.get(
    "/teacher/agreements", response_model=list[V2CollectiveAgreementOut],
)
def teacher_list_agreements(
    info: TokenInfo = Depends(require_token),
) -> list[V2CollectiveAgreementOut]:
    """Lista alla CollectiveAgreement (master-DB) för UI:n. Lärare
    behöver veta vilka agreement_id de kan koppla AgreementBenefit
    till."""
    _require_teacher(info)
    with master_session() as mdb:
        rows = mdb.query(CollectiveAgreement).order_by(CollectiveAgreement.code).all()
        return [
            V2CollectiveAgreementOut(
                id=a.id, code=a.code, name=a.name,
                union=a.union, employer_org=a.employer_org,
            )
            for a in rows
        ]


@router.get(
    "/teacher/agreements/{agreement_id}/benefits",
    response_model=list[V2AgreementBenefitOut],
)
def teacher_list_agreement_benefits(
    agreement_id: int,
    info: TokenInfo = Depends(require_token),
) -> list[V2AgreementBenefitOut]:
    """Lista alla förmåner för ett kollektivavtal."""
    _require_teacher(info)
    with master_session() as mdb:
        rows = (
            mdb.query(AgreementBenefit)
            .filter(AgreementBenefit.agreement_id == agreement_id)
            .order_by(AgreementBenefit.sort_order, AgreementBenefit.id)
            .all()
        )
        return [
            V2AgreementBenefitOut(
                id=b.id, agreement_id=b.agreement_id, kind=b.kind,
                name=b.name, detail=b.detail, value=b.value,
                sort_order=b.sort_order,
            )
            for b in rows
        ]


@router.post(
    "/teacher/agreement-benefits",
    response_model=V2AgreementBenefitOut,
)
def teacher_create_agreement_benefit(
    body: V2AgreementBenefitIn,
    info: TokenInfo = Depends(require_token),
) -> V2AgreementBenefitOut:
    """Skapa en ny strukturerad kollektivavtals-förmån (master-DB).
    Synlig för alla elever som har det avtalet via ProfessionAgreement."""
    _require_teacher(info)
    with master_session() as mdb:
        agr = mdb.get(CollectiveAgreement, body.agreement_id)
        if not agr:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Avtalet hittades inte",
            )
        b = AgreementBenefit(
            agreement_id=body.agreement_id,
            kind=body.kind,
            name=body.name,
            detail=body.detail,
            value=body.value,
            sort_order=body.sort_order,
        )
        mdb.add(b)
        mdb.flush()
        mdb.refresh(b)
        return V2AgreementBenefitOut(
            id=b.id, agreement_id=b.agreement_id, kind=b.kind,
            name=b.name, detail=b.detail, value=b.value,
            sort_order=b.sort_order,
        )


@router.delete(
    "/teacher/agreement-benefits/{benefit_id}", status_code=204,
)
def teacher_delete_agreement_benefit(
    benefit_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    _require_teacher(info)
    with master_session() as mdb:
        b = mdb.get(AgreementBenefit, benefit_id)
        if b is not None:
            mdb.delete(b)
            mdb.flush()


@router.post("/teacher/agreement-benefits/seed-default", response_model=dict)
def teacher_seed_default_agreement_benefits(
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Seedа default-katalogen för alla CollectiveAgreement-koder
    som finns. Idempotent."""
    _require_teacher(info)
    with master_session() as mdb:
        n = seed_default_agreement_benefits(mdb)
    return {"created": n}


@router.get(
    "/teacher/market-salary-ranges",
    response_model=list[V2MarketSalaryRangeOut],
)
def teacher_list_market_ranges(
    profession: Optional[str] = None,
    info: TokenInfo = Depends(require_token),
) -> list[V2MarketSalaryRangeOut]:
    _require_teacher(info)
    with master_session() as mdb:
        q = mdb.query(MarketSalaryRange)
        if profession:
            q = q.filter(MarketSalaryRange.profession == profession)
        rows = q.order_by(
            MarketSalaryRange.profession, MarketSalaryRange.city,
            MarketSalaryRange.year.desc(),
        ).all()
        return [
            V2MarketSalaryRangeOut(
                id=r.id, profession=r.profession, city=r.city,
                year=r.year, experience_band=r.experience_band,
                low=float(r.low), high=float(r.high),
                median=float(r.median) if r.median else None,
                source=r.source,
            )
            for r in rows
        ]


@router.post(
    "/teacher/market-salary-ranges", response_model=V2MarketSalaryRangeOut,
)
def teacher_create_market_range(
    body: V2MarketSalaryRangeIn,
    info: TokenInfo = Depends(require_token),
) -> V2MarketSalaryRangeOut:
    _require_teacher(info)
    if body.high < body.low:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "high måste vara >= low",
        )
    with master_session() as mdb:
        # Idempotent: om (profession, city, year, band) redan finns,
        # uppdatera istället
        existing = (
            mdb.query(MarketSalaryRange)
            .filter(
                MarketSalaryRange.profession == body.profession,
                MarketSalaryRange.city == body.city,
                MarketSalaryRange.year == body.year,
                MarketSalaryRange.experience_band == body.experience_band,
            )
            .first()
        )
        if existing is not None:
            existing.low = Decimal(str(body.low))
            existing.high = Decimal(str(body.high))
            existing.median = (
                Decimal(str(body.median)) if body.median is not None else None
            )
            existing.source = body.source
            existing.notes = body.notes
            r = existing
        else:
            r = MarketSalaryRange(
                profession=body.profession,
                city=body.city,
                year=body.year,
                experience_band=body.experience_band,
                low=Decimal(str(body.low)),
                high=Decimal(str(body.high)),
                median=(
                    Decimal(str(body.median)) if body.median is not None else None
                ),
                source=body.source,
                notes=body.notes,
            )
            mdb.add(r)
        mdb.flush()
        mdb.refresh(r)
        return V2MarketSalaryRangeOut(
            id=r.id, profession=r.profession, city=r.city,
            year=r.year, experience_band=r.experience_band,
            low=float(r.low), high=float(r.high),
            median=float(r.median) if r.median else None,
            source=r.source,
        )


@router.delete(
    "/teacher/market-salary-ranges/{range_id}", status_code=204,
)
def teacher_delete_market_range(
    range_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    _require_teacher(info)
    with master_session() as mdb:
        r = mdb.get(MarketSalaryRange, range_id)
        if r is not None:
            mdb.delete(r)
            mdb.flush()


@router.post("/teacher/market-salary-ranges/seed-default", response_model=dict)
def teacher_seed_default_market_ranges(
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Seedа default-katalogen för svenska 2026 (SCB-snitt). Idempotent."""
    _require_teacher(info)
    with master_session() as mdb:
        n = seed_default_market_salary_ranges(mdb)
    return {"created": n}


# Lärar-vy: full insyn i en elevs arbetsgivar-aktör
class V2TeacherEmployerOverview(BaseModel):
    student_id: int
    student_name: str
    profession: str
    employer: str
    agreement_name: Optional[str] = None
    agreement_id: Optional[int] = None
    pension_pct: Optional[float] = None
    gross_salary_monthly: float
    market_low: Optional[float] = None
    market_high: Optional[float] = None
    benefits: list[V2EmployerAgreementBenefit]
    satisfaction_score: int
    satisfaction_trend: str
    satisfaction_delta_4w: int
    salary_negotiations: list[V2EmployerNegotiation]
    questions_answered_count: int
    questions_pending_count: int


@router.get(
    "/teacher/students/{student_id}/employer-overview",
    response_model=V2TeacherEmployerOverview,
)
def teacher_employer_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherEmployerOverview:
    """Lärar-vy · full insyn i elevens arbetsgivar-aktör."""
    teacher_id = _require_teacher(info)

    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

        profile = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        if not profile:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Elev saknar profil",
            )

        prof_agr = (
            mdb.query(ProfessionAgreement)
            .filter(ProfessionAgreement.profession == profile.profession)
            .first()
        )
        agreement = None
        if prof_agr:
            agreement = mdb.get(CollectiveAgreement, prof_agr.agreement_id)

        pension_pct = (
            float(prof_agr.pension_rate_pct)
            if prof_agr and prof_agr.pension_rate_pct is not None
            else None
        )

        from datetime import date as _d_t
        ml, mh = _market_range_from_db(
            mdb, profile.profession, profile.city, _d_t.today().year,
        )

        benefits = _agreement_benefits_from_db(mdb, agreement)

        # Satisfaction
        sat_row = (
            mdb.query(EmployerSatisfaction)
            .filter(EmployerSatisfaction.student_id == student_id)
            .first()
        )
        sat_score = sat_row.score if sat_row else 70
        sat_trend = sat_row.trend if sat_row else "stable"

        from datetime import timedelta as _td3
        cutoff = datetime.utcnow() - _td3(days=28)
        delta_4w = int(
            mdb.query(_func.coalesce(_func.sum(EmployerSatisfactionEvent.delta_score), 0))
            .filter(EmployerSatisfactionEvent.student_id == student_id)
            .filter(EmployerSatisfactionEvent.ts >= cutoff)
            .scalar() or 0
        )

        # Lönesamtal-historik
        neg_rows = (
            mdb.query(SalaryNegotiation)
            .filter(SalaryNegotiation.student_id == student_id)
            .order_by(SalaryNegotiation.started_at.desc())
            .limit(10)
            .all()
        )
        negs_out: list[V2EmployerNegotiation] = []
        for n in neg_rows:
            last_round = (
                mdb.query(NegotiationRound)
                .filter(NegotiationRound.negotiation_id == n.id)
                .order_by(NegotiationRound.round_no.desc())
                .first()
            )
            negs_out.append(V2EmployerNegotiation(
                id=n.id,
                status=n.status,
                round_no=last_round.round_no if last_round else 0,
                max_rounds=5,
                starting_salary=float(n.starting_salary),
                requested_salary=None,
                proposed_pct=(
                    float(last_round.proposed_pct)
                    if last_round and last_round.proposed_pct is not None
                    else None
                ),
                avtal_norm_pct=n.avtal_norm_pct,
                final_salary=(
                    float(n.final_salary) if n.final_salary is not None else None
                ),
                final_pct=n.final_pct,
                started_at=n.started_at,
                completed_at=n.completed_at,
            ))

        questions_answered = (
            mdb.query(WorkplaceQuestionAnswer)
            .filter(WorkplaceQuestionAnswer.student_id == student_id)
            .count()
        )
        # Pending = totalt antal frågor minus besvarade
        total_questions = mdb.query(WorkplaceQuestion).count()
        questions_pending = max(0, total_questions - questions_answered)

        return V2TeacherEmployerOverview(
            student_id=student_id,
            student_name=st.display_name,
            profession=profile.profession,
            employer=profile.employer,
            agreement_name=agreement.name if agreement else None,
            agreement_id=agreement.id if agreement else None,
            pension_pct=pension_pct,
            gross_salary_monthly=float(profile.gross_salary_monthly or 0),
            market_low=ml,
            market_high=mh,
            benefits=benefits,
            satisfaction_score=sat_score,
            satisfaction_trend=sat_trend,
            satisfaction_delta_4w=delta_4w,
            salary_negotiations=negs_out,
            questions_answered_count=questions_answered,
            questions_pending_count=questions_pending,
        )


# === Försäkringar (/v2/forsakringar) — Fas 2D ===

class V2InsurancePolicyOut(BaseModel):
    id: int
    provider: str
    name: str
    kind: str
    premium_monthly: float
    coverage_amount: Optional[float] = None
    deductible: Optional[float] = None
    autogiro: bool
    status: str
    started_on: Optional[_date] = None
    ended_on: Optional[_date] = None
    notes: Optional[str] = None


class V2InsuranceClaimOut(BaseModel):
    id: int
    occurred_on: _date
    policy_id: Optional[int] = None
    policy_name: Optional[str] = None
    kind: str
    title: str
    description: Optional[str] = None
    amount_claimed: Optional[float] = None
    amount_paid: Optional[float] = None
    status: str
    paid_at: Optional[_date] = None
    no_policy: bool
    notes: Optional[str] = None
    created_at: datetime


class V2InsuranceSummary(BaseModel):
    active_count: int
    considered_count: int
    cancelled_count: int
    total_premium_monthly: float
    total_coverage: float
    claims_paid_12m: int
    claims_paid_amount_12m: float
    claims_unprotected_12m: int
    coverage_gaps: list[str]


class V2InsuranceResponse(BaseModel):
    student_id: int
    summary: V2InsuranceSummary
    policies: list[V2InsurancePolicyOut]
    claims: list[V2InsuranceClaimOut]


def _empty_insurance(student_id: int) -> V2InsuranceResponse:
    return V2InsuranceResponse(
        student_id=student_id,
        summary=V2InsuranceSummary(
            active_count=0, considered_count=0, cancelled_count=0,
            total_premium_monthly=0, total_coverage=0,
            claims_paid_12m=0, claims_paid_amount_12m=0,
            claims_unprotected_12m=0, coverage_gaps=[],
        ),
        policies=[],
        claims=[],
    )


@router.get("/forsakringar", response_model=V2InsuranceResponse)
def get_insurance(
    info: TokenInfo = Depends(require_token),
) -> V2InsuranceResponse:
    """Aggregat för försäkringar /v2/forsakringar (Aktör 06).

    Riktig data — ingen mockup:
    - InsurancePolicy från scope-DB (active / considered / cancelled)
    - InsuranceClaim från scope-DB (12 senaste mån)
    - Coverage_gaps räknas dynamiskt från StudentProfile (har bostadsrätt
      utan försäkring → "saknar bostadsrättsförsäkring")
    """
    if info.role != "student" or info.student_id is None:
        return _empty_insurance(0)

    coverage_gaps: list[str] = []
    has_bostadsratt = False
    has_car = False
    has_children = False
    family_status = "ensam"

    with master_session() as mdb:
        profile = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == info.student_id)
            .first()
        )
        if profile:
            has_bostadsratt = profile.housing_type in (
                "bostadsratt", "villa",
            )
            has_car = bool(getattr(profile, "has_car_loan", False))
            family_status = profile.family_status or "ensam"
            ages = (
                profile.children_ages if profile.children_ages else []
            )
            has_children = bool(ages and len(ages) > 0)

    try:
        with session_scope() as s:
            policies = (
                s.query(InsurancePolicy)
                .order_by(InsurancePolicy.status, InsurancePolicy.kind)
                .all()
            )

            policies_out: list[V2InsurancePolicyOut] = []
            policy_by_id: dict[int, InsurancePolicy] = {}
            active = []
            considered = []
            cancelled = []
            total_premium = Decimal("0")
            total_coverage = Decimal("0")
            active_kinds: set[str] = set()

            for p in policies:
                policy_by_id[p.id] = p
                policies_out.append(V2InsurancePolicyOut(
                    id=p.id, provider=p.provider, name=p.name,
                    kind=p.kind,
                    premium_monthly=float(p.premium_monthly),
                    coverage_amount=(
                        float(p.coverage_amount)
                        if p.coverage_amount else None
                    ),
                    deductible=(
                        float(p.deductible) if p.deductible else None
                    ),
                    autogiro=p.autogiro,
                    status=p.status,
                    started_on=p.started_on,
                    ended_on=p.ended_on,
                    notes=p.notes,
                ))
                if p.status == "active":
                    active.append(p)
                    active_kinds.add(p.kind)
                    total_premium += p.premium_monthly
                    if p.coverage_amount:
                        total_coverage += p.coverage_amount
                elif p.status == "considered":
                    considered.append(p)
                else:
                    cancelled.append(p)

            # Coverage gaps — vad saknar eleven baserat på sin profil?
            if "hem" not in active_kinds:
                coverage_gaps.append(
                    "Saknar hemförsäkring — bohag och ansvar oskyddade."
                )
            if has_bostadsratt and "bostadsrattsforsakring" not in active_kinds:
                coverage_gaps.append(
                    "Bor i bostadsrätt men saknar bostadsrättsförsäkring."
                )
            if has_car and "bilforsakring" not in active_kinds:
                coverage_gaps.append(
                    "Har billån men saknar bilförsäkring."
                )
            if (
                family_status in ("sambo", "familj_med_barn")
                and "liv" not in active_kinds
            ):
                coverage_gaps.append(
                    "Har sambo/familj men ingen livförsäkring."
                )
            if has_children and "barnforsakring" not in active_kinds:
                coverage_gaps.append(
                    "Har barn men saknar barnförsäkring."
                )

            # Skadehändelser (12 senaste mån)
            from datetime import date as _d_ic, timedelta as _td_ic
            cutoff = _d_ic.today() - _td_ic(days=365)
            claim_rows = (
                s.query(InsuranceClaim)
                .filter(InsuranceClaim.occurred_on >= cutoff)
                .order_by(InsuranceClaim.occurred_on.desc())
                .all()
            )
            claims_out: list[V2InsuranceClaimOut] = []
            paid_count = 0
            paid_amount = Decimal("0")
            unprotected = 0
            for c in claim_rows:
                pol = policy_by_id.get(c.policy_id) if c.policy_id else None
                claims_out.append(V2InsuranceClaimOut(
                    id=c.id,
                    occurred_on=c.occurred_on,
                    policy_id=c.policy_id,
                    policy_name=pol.name if pol else None,
                    kind=c.kind,
                    title=c.title,
                    description=c.description,
                    amount_claimed=(
                        float(c.amount_claimed) if c.amount_claimed else None
                    ),
                    amount_paid=(
                        float(c.amount_paid) if c.amount_paid else None
                    ),
                    status=c.status,
                    paid_at=c.paid_at,
                    no_policy=c.no_policy,
                    notes=c.notes,
                    created_at=c.created_at,
                ))
                if c.status == "paid" and c.amount_paid:
                    paid_count += 1
                    paid_amount += c.amount_paid
                if c.no_policy:
                    unprotected += 1

            return V2InsuranceResponse(
                student_id=info.student_id,
                summary=V2InsuranceSummary(
                    active_count=len(active),
                    considered_count=len(considered),
                    cancelled_count=len(cancelled),
                    total_premium_monthly=float(total_premium),
                    total_coverage=float(total_coverage),
                    claims_paid_12m=paid_count,
                    claims_paid_amount_12m=float(paid_amount),
                    claims_unprotected_12m=unprotected,
                    coverage_gaps=coverage_gaps,
                ),
                policies=policies_out,
                claims=claims_out,
            )
    except Exception:
        return _empty_insurance(info.student_id)


class V2InsurancePolicyIn(BaseModel):
    provider: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    kind: Literal[
        "hem", "olycksfall", "liv", "barnforsakring",
        "bostadsrattsforsakring", "bilforsakring", "djur", "ovrig",
    ]
    premium_monthly: float = Field(..., ge=0)
    coverage_amount: Optional[float] = None
    deductible: Optional[float] = None
    autogiro: bool = True
    status: Literal["active", "considered", "cancelled"] = "considered"
    started_on: Optional[_date] = None
    notes: Optional[str] = None


class V2InsurancePolicyStatusIn(BaseModel):
    status: Literal["active", "considered", "cancelled"]


@router.post("/forsakringar/policies", response_model=V2InsurancePolicyOut)
def post_insurance_policy(
    body: V2InsurancePolicyIn,
    info: TokenInfo = Depends(require_token),
) -> V2InsurancePolicyOut:
    """Eleven skapar/lägger till en försäkring."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Endast elev",
        )
    with session_scope() as s:
        p = InsurancePolicy(
            provider=body.provider,
            name=body.name,
            kind=body.kind,
            premium_monthly=Decimal(str(body.premium_monthly)),
            coverage_amount=(
                Decimal(str(body.coverage_amount))
                if body.coverage_amount is not None else None
            ),
            deductible=(
                Decimal(str(body.deductible))
                if body.deductible is not None else None
            ),
            autogiro=body.autogiro,
            status=body.status,
            started_on=body.started_on,
            notes=body.notes,
        )
        s.add(p)
        s.flush()
        return V2InsurancePolicyOut(
            id=p.id, provider=p.provider, name=p.name, kind=p.kind,
            premium_monthly=float(p.premium_monthly),
            coverage_amount=(
                float(p.coverage_amount) if p.coverage_amount else None
            ),
            deductible=(
                float(p.deductible) if p.deductible else None
            ),
            autogiro=p.autogiro,
            status=p.status, started_on=p.started_on,
            ended_on=p.ended_on, notes=p.notes,
        )


@router.patch(
    "/forsakringar/policies/{policy_id}/status",
    response_model=V2InsurancePolicyOut,
)
def patch_insurance_policy_status(
    policy_id: int,
    body: V2InsurancePolicyStatusIn,
    info: TokenInfo = Depends(require_token),
) -> V2InsurancePolicyOut:
    """Eleven ändrar status (overväger → aktiv → avbryter).
    När status går till active sätts started_on (om saknas).
    När status går till cancelled sätts ended_on."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elev")
    with session_scope() as s:
        p = s.get(InsurancePolicy, policy_id)
        if p is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Försäkring hittades inte",
            )
        from datetime import date as _d_now
        old_status = p.status
        p.status = body.status
        if body.status == "active" and p.started_on is None:
            p.started_on = _d_now.today()
        if body.status == "cancelled" and old_status == "active":
            p.ended_on = _d_now.today()
        s.flush()
        return V2InsurancePolicyOut(
            id=p.id, provider=p.provider, name=p.name, kind=p.kind,
            premium_monthly=float(p.premium_monthly),
            coverage_amount=(
                float(p.coverage_amount) if p.coverage_amount else None
            ),
            deductible=(
                float(p.deductible) if p.deductible else None
            ),
            autogiro=p.autogiro,
            status=p.status, started_on=p.started_on,
            ended_on=p.ended_on, notes=p.notes,
        )


@router.delete("/forsakringar/policies/{policy_id}", status_code=204)
def delete_insurance_policy(
    policy_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elev")
    with session_scope() as s:
        p = s.get(InsurancePolicy, policy_id)
        if p is not None:
            s.delete(p)
            s.flush()


# Lärar-endpoints
@router.post(
    "/teacher/students/{student_id}/insurance/seed-default",
    response_model=dict,
)
def teacher_seed_default_insurance(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Seedа default-katalogen (6 försäkringar) i en elevs scope-DB."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            n = seed_default_insurance_policies(s)
    return {"student_id": student_id, "policies_created": n}


class V2InsuranceClaimIn(BaseModel):
    occurred_on: _date
    policy_id: Optional[int] = None
    kind: Literal[
        "stold", "olycka", "skada", "vattenskada", "brand",
        "info", "premiehojning", "bytte_bolag",
    ]
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    amount_claimed: Optional[float] = None
    amount_paid: Optional[float] = None
    status: Literal[
        "submitted", "approved", "partial", "denied", "paid", "info",
    ] = "submitted"
    paid_at: Optional[_date] = None
    no_policy: bool = False
    notes: Optional[str] = None


@router.post(
    "/teacher/students/{student_id}/insurance/claims",
    response_model=V2InsuranceClaimOut,
)
def teacher_create_insurance_claim(
    student_id: int,
    body: V2InsuranceClaimIn,
    info: TokenInfo = Depends(require_token),
) -> V2InsuranceClaimOut:
    """Lärare lägger in en skadehändelse (simulera scenario)."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            c = InsuranceClaim(
                occurred_on=body.occurred_on,
                policy_id=body.policy_id,
                kind=body.kind,
                title=body.title,
                description=body.description,
                amount_claimed=(
                    Decimal(str(body.amount_claimed))
                    if body.amount_claimed is not None else None
                ),
                amount_paid=(
                    Decimal(str(body.amount_paid))
                    if body.amount_paid is not None else None
                ),
                status=body.status,
                paid_at=body.paid_at,
                no_policy=body.no_policy,
                notes=body.notes,
            )
            s.add(c)
            s.flush()
            pol = (
                s.get(InsurancePolicy, c.policy_id)
                if c.policy_id else None
            )
            return V2InsuranceClaimOut(
                id=c.id, occurred_on=c.occurred_on,
                policy_id=c.policy_id,
                policy_name=pol.name if pol else None,
                kind=c.kind, title=c.title,
                description=c.description,
                amount_claimed=(
                    float(c.amount_claimed) if c.amount_claimed else None
                ),
                amount_paid=(
                    float(c.amount_paid) if c.amount_paid else None
                ),
                status=c.status, paid_at=c.paid_at,
                no_policy=c.no_policy, notes=c.notes,
                created_at=c.created_at,
            )


@router.delete(
    "/teacher/students/{student_id}/insurance/claims/{claim_id}",
    status_code=204,
)
def teacher_delete_insurance_claim(
    student_id: int,
    claim_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            c = s.get(InsuranceClaim, claim_id)
            if c is not None:
                s.delete(c)
                s.flush()


class V2TeacherInsuranceOverview(BaseModel):
    student_id: int
    student_name: str
    summary: V2InsuranceSummary
    policies: list[V2InsurancePolicyOut]
    claims: list[V2InsuranceClaimOut]


@router.get(
    "/teacher/students/{student_id}/insurance-overview",
    response_model=V2TeacherInsuranceOverview,
)
def teacher_insurance_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherInsuranceOverview:
    """Lärar-vy · full insyn i elevens försäkringar."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        student_name = st.display_name

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    # Återanvänd get_insurance-logiken via scope-context
    with scope_context(scope_key):
        _outer_sid = student_id

        class _Info:
            role = "student"
            student_id = _outer_sid

        ins = get_insurance(_Info())  # type: ignore[arg-type]

    return V2TeacherInsuranceOverview(
        student_id=student_id,
        student_name=student_name,
        summary=ins.summary,
        policies=ins.policies,
        claims=ins.claims,
    )


# === Förbrukning (/v2/forbrukning) — Fas 2E ===

class V2UtilitySubscriptionOut(BaseModel):
    id: int
    supplier: str
    name: str
    category: Literal[
        "electricity", "broadband", "mobile", "streaming",
        "transport", "water", "heating", "ovrig",
    ]
    monthly_cost: float
    grid_fee_monthly: Optional[float]
    spot_pricing: bool
    binding_end: Optional[_date]
    notice_days: int
    invoice_day: Optional[int]
    status: Literal["active", "cancelled", "considered"]
    included_in_rent: bool
    started_on: Optional[_date]
    ended_on: Optional[_date]
    notes: Optional[str]


class V2UtilityReadingOut(BaseModel):
    id: int
    supplier: str
    meter_type: str
    meter_role: str
    period_start: _date
    period_end: _date
    consumption: Optional[float]
    consumption_unit: Optional[str]
    cost_kr: float
    source: str
    notes: Optional[str]


class V2UtilitySummary(BaseModel):
    active_count: int
    total_monthly_cost: float
    total_grid_fee: float
    has_spot_pricing: bool
    binding_expiring_soon: int  # antal aktiva med binding_end inom 30 dgr
    last_month_cost: float  # summerad cost_kr för senaste 30 dgr i readings
    last_month_kwh: float  # summerad kWh för senaste el-faktura
    suggested_savings_monthly: float  # uppskattad besparingspotential


class V2UtilityResponse(BaseModel):
    student_id: int
    summary: V2UtilitySummary
    subscriptions: list[V2UtilitySubscriptionOut]
    readings: list[V2UtilityReadingOut]


def _empty_utility(student_id: int) -> V2UtilityResponse:
    return V2UtilityResponse(
        student_id=student_id,
        summary=V2UtilitySummary(
            active_count=0, total_monthly_cost=0, total_grid_fee=0,
            has_spot_pricing=False, binding_expiring_soon=0,
            last_month_cost=0, last_month_kwh=0,
            suggested_savings_monthly=0,
        ),
        subscriptions=[],
        readings=[],
    )


def _compute_savings(subs: list[UtilitySubscription]) -> float:
    """Uppskattad besparingspotential per månad.

    Heuristik (samma som prototyp):
    - Bredband > 350 kr/mån + bindning slutar < 90 dgr → -80 kr (omförhandling)
    - Mobil > 99 kr/mån utan bindning → -50 kr (byt till Comviq)
    - Spotify Premium privat (utan familj-prenum) → -20 kr (familj-konto)
    - Spotpris-el utan natttid-styrning → -50 kr (timer)
    """
    saving = 0.0
    for u in subs:
        if u.status != "active":
            continue
        cost = float(u.monthly_cost or 0)
        if u.category == "broadband" and cost > 350:
            saving += 80
        if u.category == "mobile" and cost > 99 and u.binding_end is None:
            saving += 50
        if (
            u.category == "streaming"
            and "amilj" not in (u.notes or "").lower()
            and cost >= 100
        ):
            saving += 20
        if u.category == "electricity" and u.spot_pricing:
            saving += 50
    return saving


@router.get("/forbrukning", response_model=V2UtilityResponse)
def get_utility(
    info: TokenInfo = Depends(require_token),
) -> V2UtilityResponse:
    """Aggregat för förbrukning /v2/forbrukning (Aktör 07).

    Riktig data:
    - UtilitySubscription (active/cancelled/considered) i scope-DB
    - UtilityReading (12 senaste mån) per supplier + meter_type
    - Beräknad besparing från heuristik (bindning, mobil, streaming)
    """
    if info.role != "student" or info.student_id is None:
        return _empty_utility(0)

    from datetime import timedelta as _td

    with session_scope() as s:
        subs = (
            s.query(UtilitySubscription)
            .order_by(
                UtilitySubscription.status,
                UtilitySubscription.category,
                UtilitySubscription.supplier,
            )
            .all()
        )
        active = [u for u in subs if u.status == "active"]
        total_cost = sum(
            float(u.monthly_cost or 0) for u in active
            if not u.included_in_rent
        )
        total_grid = sum(float(u.grid_fee_monthly or 0) for u in active)
        has_spot = any(u.spot_pricing for u in active)
        soon = _date.today() + _td(days=30)
        expiring = sum(
            1 for u in active
            if u.binding_end is not None and u.binding_end <= soon
        )

        # Senaste 12 mån utility readings
        cutoff = _date.today() - _td(days=365)
        readings = (
            s.query(UtilityReading)
            .filter(UtilityReading.period_end >= cutoff)
            .order_by(
                UtilityReading.period_end.desc(),
                UtilityReading.id.desc(),
            )
            .all()
        )

        # Senaste månadens kostnad + kWh
        last30 = _date.today() - _td(days=45)
        last_month_readings = [
            r for r in readings if r.period_end >= last30
        ]
        last_month_cost = sum(
            float(r.cost_kr or 0) for r in last_month_readings
        )
        last_month_kwh = sum(
            float(r.consumption or 0) for r in last_month_readings
            if r.meter_type == "electricity"
            and r.meter_role in ("energy", "total")
        )

        readings_out = [
            V2UtilityReadingOut(
                id=r.id, supplier=r.supplier,
                meter_type=r.meter_type, meter_role=r.meter_role,
                period_start=r.period_start, period_end=r.period_end,
                consumption=(
                    float(r.consumption) if r.consumption is not None else None
                ),
                consumption_unit=r.consumption_unit,
                cost_kr=float(r.cost_kr),
                source=r.source, notes=r.notes,
            )
            for r in readings
        ]

        subs_out = [
            V2UtilitySubscriptionOut(
                id=u.id, supplier=u.supplier, name=u.name,
                category=u.category,  # type: ignore[arg-type]
                monthly_cost=float(u.monthly_cost),
                grid_fee_monthly=(
                    float(u.grid_fee_monthly)
                    if u.grid_fee_monthly is not None else None
                ),
                spot_pricing=bool(u.spot_pricing),
                binding_end=u.binding_end,
                notice_days=int(u.notice_days),
                invoice_day=u.invoice_day,
                status=u.status,  # type: ignore[arg-type]
                included_in_rent=bool(u.included_in_rent),
                started_on=u.started_on,
                ended_on=u.ended_on,
                notes=u.notes,
            )
            for u in subs
        ]

        savings = _compute_savings(subs)

        return V2UtilityResponse(
            student_id=info.student_id,
            summary=V2UtilitySummary(
                active_count=len(active),
                total_monthly_cost=total_cost,
                total_grid_fee=total_grid,
                has_spot_pricing=has_spot,
                binding_expiring_soon=expiring,
                last_month_cost=last_month_cost,
                last_month_kwh=last_month_kwh,
                suggested_savings_monthly=savings,
            ),
            subscriptions=subs_out,
            readings=readings_out,
        )


# Elev-endpoints
class V2UtilitySubscriptionIn(BaseModel):
    supplier: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    category: Literal[
        "electricity", "broadband", "mobile", "streaming",
        "transport", "water", "heating", "ovrig",
    ]
    monthly_cost: float = Field(..., ge=0)
    grid_fee_monthly: Optional[float] = None
    spot_pricing: bool = False
    binding_end: Optional[_date] = None
    notice_days: int = 30
    invoice_day: Optional[int] = Field(None, ge=1, le=28)
    status: Literal["active", "cancelled", "considered"] = "active"
    included_in_rent: bool = False
    started_on: Optional[_date] = None
    notes: Optional[str] = None


class V2UtilitySubscriptionPatch(BaseModel):
    monthly_cost: Optional[float] = None
    status: Optional[Literal["active", "cancelled", "considered"]] = None
    binding_end: Optional[_date] = None
    notes: Optional[str] = None


def _sub_to_out(u: UtilitySubscription) -> V2UtilitySubscriptionOut:
    return V2UtilitySubscriptionOut(
        id=u.id, supplier=u.supplier, name=u.name,
        category=u.category,  # type: ignore[arg-type]
        monthly_cost=float(u.monthly_cost),
        grid_fee_monthly=(
            float(u.grid_fee_monthly)
            if u.grid_fee_monthly is not None else None
        ),
        spot_pricing=bool(u.spot_pricing),
        binding_end=u.binding_end,
        notice_days=int(u.notice_days),
        invoice_day=u.invoice_day,
        status=u.status,  # type: ignore[arg-type]
        included_in_rent=bool(u.included_in_rent),
        started_on=u.started_on, ended_on=u.ended_on,
        notes=u.notes,
    )


@router.post(
    "/forbrukning/subscriptions",
    response_model=V2UtilitySubscriptionOut,
)
def post_utility_subscription(
    body: V2UtilitySubscriptionIn,
    info: TokenInfo = Depends(require_token),
) -> V2UtilitySubscriptionOut:
    """Eleven skapar en ny abonnemang."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")

    with session_scope() as s:
        u = UtilitySubscription(
            supplier=body.supplier,
            name=body.name,
            category=body.category,
            monthly_cost=Decimal(str(body.monthly_cost)),
            grid_fee_monthly=(
                Decimal(str(body.grid_fee_monthly))
                if body.grid_fee_monthly is not None else None
            ),
            spot_pricing=body.spot_pricing,
            binding_end=body.binding_end,
            notice_days=body.notice_days,
            invoice_day=body.invoice_day,
            status=body.status,
            included_in_rent=body.included_in_rent,
            started_on=body.started_on,
            notes=body.notes,
        )
        s.add(u)
        s.flush()
        return _sub_to_out(u)


@router.patch(
    "/forbrukning/subscriptions/{sub_id}",
    response_model=V2UtilitySubscriptionOut,
)
def patch_utility_subscription(
    sub_id: int,
    body: V2UtilitySubscriptionPatch,
    info: TokenInfo = Depends(require_token),
) -> V2UtilitySubscriptionOut:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")

    with session_scope() as s:
        u = s.get(UtilitySubscription, sub_id)
        if u is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Saknas")
        if body.monthly_cost is not None:
            u.monthly_cost = Decimal(str(body.monthly_cost))
        if body.status is not None:
            u.status = body.status
            if body.status == "cancelled" and u.ended_on is None:
                u.ended_on = _date.today()
        if body.binding_end is not None:
            u.binding_end = body.binding_end
        if body.notes is not None:
            u.notes = body.notes
        s.flush()
        return _sub_to_out(u)


@router.delete(
    "/forbrukning/subscriptions/{sub_id}",
    status_code=204,
)
def delete_utility_subscription(
    sub_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    with session_scope() as s:
        u = s.get(UtilitySubscription, sub_id)
        if u is not None:
            s.delete(u)
            s.flush()


# Lärar-endpoints
@router.post(
    "/teacher/students/{student_id}/utility/seed-default",
    response_model=dict,
)
def teacher_seed_default_utility(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Seedа default-katalogen (6 svenska abonnemang) i scope-DB."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            n = seed_default_utility_subscriptions(s)
    return {"student_id": student_id, "subscriptions_created": n}


class V2UtilityReadingIn(BaseModel):
    supplier: str = Field(..., min_length=1, max_length=60)
    meter_type: Literal[
        "electricity", "broadband", "water", "heating", "district_heating",
    ]
    meter_role: Literal["grid", "energy", "total"] = "total"
    period_start: _date
    period_end: _date
    consumption: Optional[float] = None
    consumption_unit: Optional[str] = None
    cost_kr: float = Field(..., ge=0)
    notes: Optional[str] = None


@router.post(
    "/teacher/students/{student_id}/utility/readings",
    response_model=V2UtilityReadingOut,
)
def teacher_create_utility_reading(
    student_id: int,
    body: V2UtilityReadingIn,
    info: TokenInfo = Depends(require_token),
) -> V2UtilityReadingOut:
    """Lärare lägger in månadsfaktura/avläsning för simulering."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            r = UtilityReading(
                supplier=body.supplier,
                meter_type=body.meter_type,
                meter_role=body.meter_role,
                period_start=body.period_start,
                period_end=body.period_end,
                consumption=(
                    Decimal(str(body.consumption))
                    if body.consumption is not None else None
                ),
                consumption_unit=body.consumption_unit,
                cost_kr=Decimal(str(body.cost_kr)),
                source="manual",
                notes=body.notes,
            )
            s.add(r)
            s.flush()
            return V2UtilityReadingOut(
                id=r.id, supplier=r.supplier,
                meter_type=r.meter_type, meter_role=r.meter_role,
                period_start=r.period_start, period_end=r.period_end,
                consumption=(
                    float(r.consumption) if r.consumption is not None else None
                ),
                consumption_unit=r.consumption_unit,
                cost_kr=float(r.cost_kr),
                source=r.source, notes=r.notes,
            )


@router.delete(
    "/teacher/students/{student_id}/utility/readings/{reading_id}",
    status_code=204,
)
def teacher_delete_utility_reading(
    student_id: int,
    reading_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            r = s.get(UtilityReading, reading_id)
            if r is not None:
                s.delete(r)
                s.flush()


class V2TeacherUtilityOverview(BaseModel):
    student_id: int
    student_name: str
    summary: V2UtilitySummary
    subscriptions: list[V2UtilitySubscriptionOut]
    readings: list[V2UtilityReadingOut]


@router.get(
    "/teacher/students/{student_id}/utility-overview",
    response_model=V2TeacherUtilityOverview,
)
def teacher_utility_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherUtilityOverview:
    """Lärar-vy · full insyn i elevens förbruknings-portfölj."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        student_name = st.display_name

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        _outer_sid = student_id

        class _Info:
            role = "student"
            student_id = _outer_sid

        util = get_utility(_Info())  # type: ignore[arg-type]

    return V2TeacherUtilityOverview(
        student_id=student_id,
        student_name=student_name,
        summary=util.summary,
        subscriptions=util.subscriptions,
        readings=util.readings,
    )


# === Hyresvärden (/v2/hyresvarden) — Fas 2F ===


class V2RentalContractOut(BaseModel):
    id: int
    landlord: str
    address: str
    rooms_label: str
    area_sqm: float
    city: Optional[str]
    district: Optional[str]
    contract_type: Literal[
        "forsta_hand", "andra_hand", "inneboende", "bostadsratt",
    ]
    duration_type: Literal["tillsvidare", "tidsbegransad"]
    monthly_rent: float
    deposit: Optional[float]
    ocr_reference: Optional[str]
    autogiro: bool
    notice_period_months: int
    started_on: Optional[_date]
    ended_on: Optional[_date]
    queue_years: Optional[int]
    queue_priority: Optional[str]
    market_price_per_sqm: Optional[float]
    status: Literal["active", "terminated", "considered"]
    notes: Optional[str]


class V2RentalNoticeOut(BaseModel):
    id: int
    contract_id: Optional[int]
    occurred_on: _date
    notice_type: Literal[
        "hyresavi", "underhall", "hyreshojning", "trapphusrenovering",
        "forhandling", "brand", "andrahand_ansokan", "ovrig",
    ]
    title: str
    description: Optional[str]
    amount: Optional[float]
    change_pct: Optional[float]
    status: Literal[
        "info", "action_required", "paid", "acknowledged", "denied",
    ]
    notes: Optional[str]
    created_at: datetime


class V2RentalSummary(BaseModel):
    has_active_contract: bool
    monthly_rent: float
    rent_per_sqm_yearly: float
    rent_share_of_net_pct: Optional[float]
    notices_open: int  # action_required eller info <30 dgr
    notices_paid_12m: int
    biggest_hike_pct_12m: Optional[float]
    market_diff_pct: Optional[float]  # rent vs marknadshyra (proxy)
    market_buy_estimate: Optional[float]  # area * market_price_per_sqm


class V2RentalResponse(BaseModel):
    student_id: int
    summary: V2RentalSummary
    contract: Optional[V2RentalContractOut]
    notices: list[V2RentalNoticeOut]


def _empty_rental(student_id: int) -> V2RentalResponse:
    return V2RentalResponse(
        student_id=student_id,
        summary=V2RentalSummary(
            has_active_contract=False,
            monthly_rent=0,
            rent_per_sqm_yearly=0,
            rent_share_of_net_pct=None,
            notices_open=0,
            notices_paid_12m=0,
            biggest_hike_pct_12m=None,
            market_diff_pct=None,
            market_buy_estimate=None,
        ),
        contract=None,
        notices=[],
    )


def _contract_to_out(c: RentalContract) -> V2RentalContractOut:
    return V2RentalContractOut(
        id=c.id, landlord=c.landlord, address=c.address,
        rooms_label=c.rooms_label, area_sqm=float(c.area_sqm),
        city=c.city, district=c.district,
        contract_type=c.contract_type,  # type: ignore[arg-type]
        duration_type=c.duration_type,  # type: ignore[arg-type]
        monthly_rent=float(c.monthly_rent),
        deposit=float(c.deposit) if c.deposit is not None else None,
        ocr_reference=c.ocr_reference,
        autogiro=bool(c.autogiro),
        notice_period_months=int(c.notice_period_months),
        started_on=c.started_on, ended_on=c.ended_on,
        queue_years=c.queue_years, queue_priority=c.queue_priority,
        market_price_per_sqm=(
            float(c.market_price_per_sqm)
            if c.market_price_per_sqm is not None else None
        ),
        status=c.status,  # type: ignore[arg-type]
        notes=c.notes,
    )


def _notice_to_out(n: RentalNotice) -> V2RentalNoticeOut:
    return V2RentalNoticeOut(
        id=n.id, contract_id=n.contract_id,
        occurred_on=n.occurred_on,
        notice_type=n.notice_type,  # type: ignore[arg-type]
        title=n.title, description=n.description,
        amount=float(n.amount) if n.amount is not None else None,
        change_pct=(
            float(n.change_pct) if n.change_pct is not None else None
        ),
        status=n.status,  # type: ignore[arg-type]
        notes=n.notes, created_at=n.created_at,
    )


@router.get("/hyresvarden", response_model=V2RentalResponse)
def get_rental(
    info: TokenInfo = Depends(require_token),
) -> V2RentalResponse:
    """Aggregat för hyresvärden /v2/hyresvarden (Aktör 08).

    Riktig data:
    - RentalContract (active) i scope-DB — primary contract
    - RentalNotice (12 mån) sorterade nyast först
    - Hyresandel av netto från StudentProfile
    - market_diff_pct = (rent_per_sqm_yearly - marknad_avg) (proxy)
    - market_buy_estimate = area * market_price_per_sqm (köp-jämförelse)
    """
    if info.role != "student" or info.student_id is None:
        return _empty_rental(0)

    # Hämta StudentProfile (master-DB) för netto-jämförelse
    net_salary = None
    with master_session() as mdb:
        prof = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == info.student_id)
            .first()
        )
        if prof and prof.net_salary_monthly:
            net_salary = float(prof.net_salary_monthly)

    from datetime import timedelta as _td_r

    with session_scope() as s:
        contract = (
            s.query(RentalContract)
            .filter(RentalContract.status == "active")
            .order_by(RentalContract.id.desc())
            .first()
        )
        cutoff = _date.today() - _td_r(days=365)
        notices = (
            s.query(RentalNotice)
            .filter(RentalNotice.occurred_on >= cutoff)
            .order_by(
                RentalNotice.occurred_on.desc(),
                RentalNotice.id.desc(),
            )
            .all()
        )

        notices_out = [_notice_to_out(n) for n in notices]
        notices_open = sum(
            1 for n in notices
            if n.status in ("action_required", "info")
            and n.occurred_on >= _date.today() - _td_r(days=30)
        )
        notices_paid_12m = sum(1 for n in notices if n.status == "paid")
        hikes = [
            float(n.change_pct) for n in notices
            if n.notice_type == "hyreshojning"
            and n.change_pct is not None
        ]
        biggest_hike = max(hikes) if hikes else None

        contract_out: Optional[V2RentalContractOut] = None
        rent = 0.0
        rent_per_sqm_year = 0.0
        share_pct: Optional[float] = None
        market_diff_pct: Optional[float] = None
        market_buy_estimate: Optional[float] = None

        if contract is not None:
            contract_out = _contract_to_out(contract)
            rent = float(contract.monthly_rent or 0)
            area = float(contract.area_sqm or 0)
            if area > 0:
                rent_per_sqm_year = (rent * 12) / area
            if net_salary and net_salary > 0:
                share_pct = round(rent / net_salary * 100, 1)
            mps = (
                float(contract.market_price_per_sqm)
                if contract.market_price_per_sqm is not None else None
            )
            if mps and area > 0:
                market_buy_estimate = round(area * mps, 0)
                # Jämför hyran/m² med Sthlm-snitt 2026
                # ≈ 1900 kr/m²/år för förstahand i ytterstad.
                sthlm_avg = 1900.0
                if rent_per_sqm_year > 0:
                    market_diff_pct = round(
                        (rent_per_sqm_year - sthlm_avg) / sthlm_avg * 100,
                        1,
                    )

        return V2RentalResponse(
            student_id=info.student_id,
            summary=V2RentalSummary(
                has_active_contract=contract is not None,
                monthly_rent=rent,
                rent_per_sqm_yearly=round(rent_per_sqm_year, 0),
                rent_share_of_net_pct=share_pct,
                notices_open=notices_open,
                notices_paid_12m=notices_paid_12m,
                biggest_hike_pct_12m=biggest_hike,
                market_diff_pct=market_diff_pct,
                market_buy_estimate=market_buy_estimate,
            ),
            contract=contract_out,
            notices=notices_out,
        )


# Elev-endpoints
class V2RentalContractIn(BaseModel):
    landlord: str = Field(..., min_length=1, max_length=120)
    address: str = Field(..., min_length=1, max_length=200)
    rooms_label: str = Field(..., min_length=1, max_length=40)
    area_sqm: float = Field(..., gt=0)
    city: Optional[str] = None
    district: Optional[str] = None
    contract_type: Literal[
        "forsta_hand", "andra_hand", "inneboende", "bostadsratt",
    ] = "forsta_hand"
    duration_type: Literal["tillsvidare", "tidsbegransad"] = "tillsvidare"
    monthly_rent: float = Field(..., ge=0)
    deposit: Optional[float] = None
    ocr_reference: Optional[str] = None
    autogiro: bool = True
    notice_period_months: int = 3
    started_on: Optional[_date] = None
    queue_years: Optional[int] = None
    queue_priority: Optional[str] = None
    market_price_per_sqm: Optional[float] = None
    notes: Optional[str] = None


class V2RentalContractPatch(BaseModel):
    monthly_rent: Optional[float] = None
    autogiro: Optional[bool] = None
    status: Optional[Literal["active", "terminated", "considered"]] = None
    ended_on: Optional[_date] = None
    notes: Optional[str] = None


@router.post("/hyresvarden/contracts", response_model=V2RentalContractOut)
def post_rental_contract(
    body: V2RentalContractIn,
    info: TokenInfo = Depends(require_token),
) -> V2RentalContractOut:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    with session_scope() as s:
        c = RentalContract(
            landlord=body.landlord,
            address=body.address,
            rooms_label=body.rooms_label,
            area_sqm=Decimal(str(body.area_sqm)),
            city=body.city,
            district=body.district,
            contract_type=body.contract_type,
            duration_type=body.duration_type,
            monthly_rent=Decimal(str(body.monthly_rent)),
            deposit=(
                Decimal(str(body.deposit))
                if body.deposit is not None else None
            ),
            ocr_reference=body.ocr_reference,
            autogiro=body.autogiro,
            notice_period_months=body.notice_period_months,
            started_on=body.started_on,
            queue_years=body.queue_years,
            queue_priority=body.queue_priority,
            market_price_per_sqm=(
                Decimal(str(body.market_price_per_sqm))
                if body.market_price_per_sqm is not None else None
            ),
            status="active",
            notes=body.notes,
        )
        s.add(c)
        s.flush()
        return _contract_to_out(c)


@router.patch(
    "/hyresvarden/contracts/{contract_id}",
    response_model=V2RentalContractOut,
)
def patch_rental_contract(
    contract_id: int,
    body: V2RentalContractPatch,
    info: TokenInfo = Depends(require_token),
) -> V2RentalContractOut:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    with session_scope() as s:
        c = s.get(RentalContract, contract_id)
        if c is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Saknas")
        if body.monthly_rent is not None:
            c.monthly_rent = Decimal(str(body.monthly_rent))
        if body.autogiro is not None:
            c.autogiro = body.autogiro
        if body.status is not None:
            c.status = body.status
            if body.status == "terminated" and c.ended_on is None:
                c.ended_on = _date.today()
        if body.ended_on is not None:
            c.ended_on = body.ended_on
        if body.notes is not None:
            c.notes = body.notes
        s.flush()
        return _contract_to_out(c)


@router.delete("/hyresvarden/contracts/{contract_id}", status_code=204)
def delete_rental_contract(
    contract_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    with session_scope() as s:
        c = s.get(RentalContract, contract_id)
        if c is not None:
            s.delete(c)
            s.flush()


# Lärar-endpoints
@router.post(
    "/teacher/students/{student_id}/rental/seed-default",
    response_model=dict,
)
def teacher_seed_default_rental(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Seedа Stockholmshem 2 r o k Hökarängen + 4 standard-notiser."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            contracts, notices = seed_default_rental(s)
    return {
        "student_id": student_id,
        "contracts_created": contracts,
        "notices_created": notices,
    }


class V2RentalNoticeIn(BaseModel):
    contract_id: Optional[int] = None
    occurred_on: _date
    notice_type: Literal[
        "hyresavi", "underhall", "hyreshojning", "trapphusrenovering",
        "forhandling", "brand", "andrahand_ansokan", "ovrig",
    ]
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    amount: Optional[float] = None
    change_pct: Optional[float] = None
    status: Literal[
        "info", "action_required", "paid", "acknowledged", "denied",
    ] = "info"
    notes: Optional[str] = None


@router.post(
    "/teacher/students/{student_id}/rental/notices",
    response_model=V2RentalNoticeOut,
)
def teacher_create_rental_notice(
    student_id: int,
    body: V2RentalNoticeIn,
    info: TokenInfo = Depends(require_token),
) -> V2RentalNoticeOut:
    """Lärare lägger in brev/notis från värden (simulera scenario)."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            n = RentalNotice(
                contract_id=body.contract_id,
                occurred_on=body.occurred_on,
                notice_type=body.notice_type,
                title=body.title,
                description=body.description,
                amount=(
                    Decimal(str(body.amount))
                    if body.amount is not None else None
                ),
                change_pct=(
                    Decimal(str(body.change_pct))
                    if body.change_pct is not None else None
                ),
                status=body.status,
                notes=body.notes,
            )
            s.add(n)
            s.flush()
            return _notice_to_out(n)


@router.delete(
    "/teacher/students/{student_id}/rental/notices/{notice_id}",
    status_code=204,
)
def teacher_delete_rental_notice(
    student_id: int,
    notice_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            n = s.get(RentalNotice, notice_id)
            if n is not None:
                s.delete(n)
                s.flush()


class V2TeacherRentalOverview(BaseModel):
    student_id: int
    student_name: str
    summary: V2RentalSummary
    contract: Optional[V2RentalContractOut]
    notices: list[V2RentalNoticeOut]


@router.get(
    "/teacher/students/{student_id}/rental-overview",
    response_model=V2TeacherRentalOverview,
)
def teacher_rental_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherRentalOverview:
    """Lärar-vy · full insyn i elevens hyreskontrakt + notiser."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        student_name = st.display_name

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        _outer_sid = student_id

        class _Info:
            role = "student"
            student_id = _outer_sid

        rent = get_rental(_Info())  # type: ignore[arg-type]

    return V2TeacherRentalOverview(
        student_id=student_id,
        student_name=student_name,
        summary=rent.summary,
        contract=rent.contract,
        notices=rent.notices,
    )


# === Pension (/v2/pension) — Fas 2G ===


class V2PensionPillar(BaseModel):
    label: str
    name: str
    detail: str
    monthly_at_retire: float
    source: Literal["auto", "agreement", "isk", "missing"]


class V2PensionScenarios(BaseModel):
    age_65_early: float
    age_67_target: float
    age_70_late: float


class V2PensionAssumptionsOut(BaseModel):
    retire_age: int
    real_return_pct: float
    ibb_yearly: float
    delningstal: float
    custom_isk_monthly: float
    itp1_low_pct: float
    itp1_high_pct: float
    notes: Optional[str]


class V2PensionResponse(BaseModel):
    student_id: int
    assumptions: V2PensionAssumptionsOut
    years_to_retire: int
    pillars: list[V2PensionPillar]
    total_monthly_at_retire: float
    scenarios: V2PensionScenarios
    isk_current_value: float
    has_collective_agreement: bool
    age: Optional[int]
    gross_salary_monthly: Optional[float]


def _empty_pension(student_id: int) -> V2PensionResponse:
    return V2PensionResponse(
        student_id=student_id,
        assumptions=V2PensionAssumptionsOut(
            retire_age=67, real_return_pct=2.0,
            ibb_yearly=80600, delningstal=17.0,
            custom_isk_monthly=0, itp1_low_pct=4.5,
            itp1_high_pct=30.0, notes=None,
        ),
        years_to_retire=0,
        pillars=[],
        total_monthly_at_retire=0,
        scenarios=V2PensionScenarios(
            age_65_early=0, age_67_target=0, age_70_late=0,
        ),
        isk_current_value=0,
        has_collective_agreement=False,
        age=None,
        gross_salary_monthly=None,
    )


def _detect_collective_agreement(profile: Optional[StudentProfile]) -> bool:
    """Heuristik: hög-lönade vita yrken + offentlig sektor har ofta
    kollektivavtal. Undersköterska/lärare/sjuksköterska/utvecklare = ja.
    Egenföretagare = nej.
    """
    if profile is None or not profile.profession:
        return False
    p = profile.profession.lower()
    if "egenföret" in p or "frilans" in p or "soloentr" in p:
        return False
    return True


@router.get("/pension", response_model=V2PensionResponse)
def get_pension(
    info: TokenInfo = Depends(require_token),
) -> V2PensionResponse:
    """Aggregat för pension /v2/pension (Aktör 09).

    Riktig data: hämtar lön + ålder från StudentProfile (master-DB),
    ISK-värde från FundHolding + StockHolding (scope-DB) +
    PensionAssumption (lärar-justerbar singleton i scope-DB), beräknar
    4 pelare + scenarier.
    """
    if info.role != "student" or info.student_id is None:
        return _empty_pension(0)

    age: Optional[int] = None
    salary: Optional[float] = None
    has_agreement = False
    with master_session() as mdb:
        prof = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == info.student_id)
            .first()
        )
        if prof:
            age = int(prof.age) if prof.age is not None else None
            salary = (
                float(prof.gross_salary_monthly)
                if prof.gross_salary_monthly is not None else None
            )
            has_agreement = _detect_collective_agreement(prof)

    with session_scope() as s:
        a = _get_pension_assumptions(s)
        forecast = compute_pension_forecast(
            s,
            age=age,
            gross_salary_monthly=salary,
            has_collective_agreement=has_agreement,
        )
        return V2PensionResponse(
            student_id=info.student_id,
            assumptions=V2PensionAssumptionsOut(
                retire_age=int(a.retire_age),
                real_return_pct=float(a.real_return_pct),
                ibb_yearly=float(a.ibb_yearly),
                delningstal=float(a.delningstal),
                custom_isk_monthly=float(a.custom_isk_monthly),
                itp1_low_pct=float(a.itp1_low_pct),
                itp1_high_pct=float(a.itp1_high_pct),
                notes=a.notes,
            ),
            years_to_retire=forecast["years_to_retire"],
            pillars=[
                V2PensionPillar(**p) for p in forecast["pillars"]
            ],
            total_monthly_at_retire=forecast["total_monthly_at_retire"],
            scenarios=V2PensionScenarios(**forecast["scenarios"]),
            isk_current_value=forecast["isk_current_value"],
            has_collective_agreement=has_agreement,
            age=age,
            gross_salary_monthly=salary,
        )


class V2PensionAssumptionsPatch(BaseModel):
    retire_age: Optional[int] = Field(None, ge=60, le=80)
    real_return_pct: Optional[float] = Field(None, ge=-2, le=15)
    custom_isk_monthly: Optional[float] = Field(None, ge=0)
    itp1_low_pct: Optional[float] = Field(None, ge=0, le=15)
    itp1_high_pct: Optional[float] = Field(None, ge=0, le=50)
    notes: Optional[str] = None


@router.patch(
    "/pension/assumptions",
    response_model=V2PensionAssumptionsOut,
)
def patch_pension_assumptions(
    body: V2PensionAssumptionsPatch,
    info: TokenInfo = Depends(require_token),
) -> V2PensionAssumptionsOut:
    """Eleven uppdaterar t.ex. custom_isk_monthly (vad jag sparar /mån)."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    with session_scope() as s:
        a = _get_pension_assumptions(s)
        if body.retire_age is not None:
            a.retire_age = body.retire_age
        if body.real_return_pct is not None:
            a.real_return_pct = Decimal(str(body.real_return_pct))
        if body.custom_isk_monthly is not None:
            a.custom_isk_monthly = Decimal(str(body.custom_isk_monthly))
        if body.itp1_low_pct is not None:
            a.itp1_low_pct = Decimal(str(body.itp1_low_pct))
        if body.itp1_high_pct is not None:
            a.itp1_high_pct = Decimal(str(body.itp1_high_pct))
        if body.notes is not None:
            a.notes = body.notes
        s.flush()
        return V2PensionAssumptionsOut(
            retire_age=int(a.retire_age),
            real_return_pct=float(a.real_return_pct),
            ibb_yearly=float(a.ibb_yearly),
            delningstal=float(a.delningstal),
            custom_isk_monthly=float(a.custom_isk_monthly),
            itp1_low_pct=float(a.itp1_low_pct),
            itp1_high_pct=float(a.itp1_high_pct),
            notes=a.notes,
        )


# Lärar-endpoints för pension
@router.post(
    "/teacher/students/{student_id}/pension/seed-default",
    response_model=dict,
)
def teacher_seed_default_pension(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Skapa singleton PensionAssumption om saknas i elevens scope."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            n = seed_default_pension(s)
    return {"student_id": student_id, "created": n}


@router.patch(
    "/teacher/students/{student_id}/pension/assumptions",
    response_model=V2PensionAssumptionsOut,
)
def teacher_patch_pension_assumptions(
    student_id: int,
    body: V2PensionAssumptionsPatch,
    info: TokenInfo = Depends(require_token),
) -> V2PensionAssumptionsOut:
    """Lärare justerar elevens pension-antaganden (riktålder, real
    avkastning, ITP1-procent)."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        with session_scope() as s:
            a = _get_pension_assumptions(s)
            if body.retire_age is not None:
                a.retire_age = body.retire_age
            if body.real_return_pct is not None:
                a.real_return_pct = Decimal(str(body.real_return_pct))
            if body.custom_isk_monthly is not None:
                a.custom_isk_monthly = Decimal(
                    str(body.custom_isk_monthly),
                )
            if body.itp1_low_pct is not None:
                a.itp1_low_pct = Decimal(str(body.itp1_low_pct))
            if body.itp1_high_pct is not None:
                a.itp1_high_pct = Decimal(str(body.itp1_high_pct))
            if body.notes is not None:
                a.notes = body.notes
            s.flush()
            return V2PensionAssumptionsOut(
                retire_age=int(a.retire_age),
                real_return_pct=float(a.real_return_pct),
                ibb_yearly=float(a.ibb_yearly),
                delningstal=float(a.delningstal),
                custom_isk_monthly=float(a.custom_isk_monthly),
                itp1_low_pct=float(a.itp1_low_pct),
                itp1_high_pct=float(a.itp1_high_pct),
                notes=a.notes,
            )


class V2TeacherPensionOverview(BaseModel):
    student_id: int
    student_name: str
    forecast: V2PensionResponse


@router.get(
    "/teacher/students/{student_id}/pension-overview",
    response_model=V2TeacherPensionOverview,
)
def teacher_pension_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherPensionOverview:
    """Lärar-vy · full insyn i elevens pension (samma forecast som elev)."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        student_name = st.display_name

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        _outer_sid = student_id

        class _Info:
            role = "student"
            student_id = _outer_sid

        forecast = get_pension(_Info())  # type: ignore[arg-type]

    return V2TeacherPensionOverview(
        student_id=student_id,
        student_name=student_name,
        forecast=forecast,
    )


# === Avanza · ISK + aktiehandel (/v2/avanza) — Fas 2G ===


class V2AvanzaFundOut(BaseModel):
    id: int
    fund_name: str
    units: Optional[float]
    market_value: float
    last_price: Optional[float]
    change_pct: Optional[float]
    day_change_pct: Optional[float]
    last_update_date: _date


class V2AvanzaStockOut(BaseModel):
    id: int
    ticker: str
    quantity: int
    avg_cost: float
    last_price: Optional[float]
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: Optional[float]


class V2AvanzaTradeRow(BaseModel):
    id: int
    ticker: str
    side: str
    quantity: int
    price: float
    courtage: float
    total_amount: float
    realized_pnl: Optional[float]
    student_rationale: Optional[str]
    executed_at: datetime


class V2AvanzaSummary(BaseModel):
    isk_account_id: Optional[int]
    isk_account_name: Optional[str]
    cash_balance: float
    funds_value: float
    stocks_value: float
    total_value: float
    schablonskatt_estimate: float  # 0.89 % av kapitalunderlag (proxy)
    fund_count: int
    stock_count: int
    monthly_savings: float  # från PensionAssumption.custom_isk_monthly


class V2AvanzaResponse(BaseModel):
    student_id: int
    summary: V2AvanzaSummary
    funds: list[V2AvanzaFundOut]
    stocks: list[V2AvanzaStockOut]
    recent_trades: list[V2AvanzaTradeRow]


def _empty_avanza(student_id: int) -> V2AvanzaResponse:
    return V2AvanzaResponse(
        student_id=student_id,
        summary=V2AvanzaSummary(
            isk_account_id=None, isk_account_name=None,
            cash_balance=0, funds_value=0, stocks_value=0,
            total_value=0, schablonskatt_estimate=0,
            fund_count=0, stock_count=0, monthly_savings=0,
        ),
        funds=[], stocks=[], recent_trades=[],
    )


def _isk_cash_balance(s, account_id: int) -> Decimal:
    """Cash-saldo för ett ISK-konto = opening_balance + sum(transactions)."""
    acc = s.get(Account, account_id)
    if acc is None:
        return Decimal("0")
    base = Decimal(str(acc.opening_balance or 0))
    from sqlalchemy import func as _sa_func_local
    total = (
        s.query(_sa_func_local.coalesce(
            _sa_func_local.sum(Transaction.amount), 0,
        ))
        .filter(Transaction.account_id == account_id)
        .scalar()
    )
    return base + Decimal(str(total or 0))


@router.get("/avanza", response_model=V2AvanzaResponse)
def get_avanza(
    info: TokenInfo = Depends(require_token),
) -> V2AvanzaResponse:
    """Aggregat för Avanza ISK /v2/avanza (Aktör 05).

    Hittar första ISK-kontot, listar fonder + aktier + senaste trades,
    beräknar schablonskatt ≈ 0,89 % av kapitalunderlaget.
    """
    if info.role != "student" or info.student_id is None:
        return _empty_avanza(0)

    with session_scope() as s:
        isk = (
            s.query(Account)
            .filter(Account.type == "isk")
            .order_by(Account.id.asc())
            .first()
        )
        if isk is None:
            # Inget ISK-konto än — men visa ändå månads-spar-intentionen
            # från PensionAssumption (eleven kan ha satt det innan kontot
            # är skapat)
            pa = _get_pension_assumptions(s)
            empty = _empty_avanza(info.student_id)
            empty.summary.monthly_savings = float(pa.custom_isk_monthly)
            return empty

        funds_q = (
            s.query(FundHolding)
            .filter(FundHolding.account_id == isk.id)
            .order_by(FundHolding.market_value.desc())
            .all()
        )
        funds_total = sum(
            float(f.market_value or 0) for f in funds_q
        )

        stocks_q = (
            s.query(StockHolding)
            .filter(StockHolding.account_id == isk.id)
            .all()
        )

        # Hämta senaste kurser för innehaven
        from ..school.stock_models import LatestStockQuote
        tickers = list({h.ticker for h in stocks_q})
        price_by_ticker: dict[str, float] = {}
        if tickers:
            with master_session() as msdb:
                quotes = (
                    msdb.query(LatestStockQuote)
                    .filter(LatestStockQuote.ticker.in_(tickers))
                    .all()
                )
                price_by_ticker = {
                    q.ticker: float(q.last) for q in quotes
                }

        stocks_out: list[V2AvanzaStockOut] = []
        stocks_total = 0.0
        for h in stocks_q:
            last = price_by_ticker.get(h.ticker)
            avg = float(h.avg_cost)
            qty = int(h.quantity)
            mv = (last if last is not None else avg) * qty
            stocks_total += mv
            pnl = mv - avg * qty
            pnl_pct = (pnl / (avg * qty) * 100.0) if avg > 0 else None
            stocks_out.append(V2AvanzaStockOut(
                id=h.id, ticker=h.ticker, quantity=qty,
                avg_cost=avg, last_price=last,
                market_value=round(mv, 2),
                unrealized_pnl=round(pnl, 2),
                unrealized_pnl_pct=(
                    round(pnl_pct, 2) if pnl_pct is not None else None
                ),
            ))

        cash = float(_isk_cash_balance(s, isk.id))
        total = funds_total + stocks_total + cash
        # Schablonskatt 2026 ≈ 0.89 % av snitt-kapital (proxy: nuvärde)
        sk = round(total * 0.0089, 0)

        # Senaste 10 trades
        trades = (
            s.query(StockTransaction)
            .filter(StockTransaction.account_id == isk.id)
            .order_by(StockTransaction.executed_at.desc())
            .limit(10)
            .all()
        )

        # Lärar-månads-spar (från PensionAssumption)
        pa = _get_pension_assumptions(s)
        monthly_save = float(pa.custom_isk_monthly)

        return V2AvanzaResponse(
            student_id=info.student_id,
            summary=V2AvanzaSummary(
                isk_account_id=isk.id,
                isk_account_name=isk.name,
                cash_balance=round(cash, 2),
                funds_value=round(funds_total, 2),
                stocks_value=round(stocks_total, 2),
                total_value=round(total, 2),
                schablonskatt_estimate=sk,
                fund_count=len(funds_q),
                stock_count=len(stocks_q),
                monthly_savings=monthly_save,
            ),
            funds=[
                V2AvanzaFundOut(
                    id=f.id, fund_name=f.fund_name,
                    units=(
                        float(f.units) if f.units is not None else None
                    ),
                    market_value=float(f.market_value),
                    last_price=(
                        float(f.last_price)
                        if f.last_price is not None else None
                    ),
                    change_pct=f.change_pct,
                    day_change_pct=f.day_change_pct,
                    last_update_date=f.last_update_date,
                )
                for f in funds_q
            ],
            stocks=stocks_out,
            recent_trades=[
                V2AvanzaTradeRow(
                    id=t.id, ticker=t.ticker, side=t.side,
                    quantity=t.quantity, price=float(t.price),
                    courtage=float(t.courtage),
                    total_amount=float(t.total_amount),
                    realized_pnl=(
                        float(t.realized_pnl)
                        if t.realized_pnl is not None else None
                    ),
                    student_rationale=t.student_rationale,
                    executed_at=t.executed_at,
                )
                for t in trades
            ],
        )


class V2StockMarketRow(BaseModel):
    ticker: str
    name: str
    sector: Optional[str]
    currency: str
    last: float
    change_pct: Optional[float]
    bid: Optional[float]
    ask: Optional[float]


class V2StockMarketResponse(BaseModel):
    stocks: list[V2StockMarketRow]
    count: int
    market_open: bool


@router.get("/aktier/market", response_model=V2StockMarketResponse)
def get_stock_market(
    info: TokenInfo = Depends(require_token),
) -> V2StockMarketResponse:
    """Hela aktieuniversumet (StockMaster + LatestStockQuote) — för
    aktiehandel-vyn. Tillgängligt för alla autentiserade användare
    (även lärare) eftersom det är masterdata utan elev-koppling."""
    from ..school.stock_models import StockMaster, LatestStockQuote
    with master_session() as msdb:
        masters = msdb.query(StockMaster).all()
        latest = {
            q.ticker: q
            for q in msdb.query(LatestStockQuote).all()
        }
        rows: list[V2StockMarketRow] = []
        for m in masters:
            q = latest.get(m.ticker)
            if q is None:
                continue
            rows.append(V2StockMarketRow(
                ticker=m.ticker,
                name=getattr(m, "name", m.ticker),
                sector=getattr(m, "sector", None),
                currency=getattr(m, "currency", "SEK"),
                last=float(q.last),
                change_pct=q.change_pct,
                bid=float(q.bid) if q.bid is not None else None,
                ask=float(q.ask) if q.ask is not None else None,
            ))
        # Marknad öppen = senaste quote inom 30 min
        from datetime import datetime as _dt_market, timedelta as _td_market
        now = _dt_market.utcnow()
        market_open = any(
            q.ts and (now - q.ts) < _td_market(minutes=30)
            for q in latest.values()
        )
        return V2StockMarketResponse(
            stocks=rows, count=len(rows), market_open=market_open,
        )


class V2TeacherAvanzaOverview(BaseModel):
    student_id: int
    student_name: str
    avanza: V2AvanzaResponse


@router.get(
    "/teacher/students/{student_id}/avanza-overview",
    response_model=V2TeacherAvanzaOverview,
)
def teacher_avanza_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherAvanzaOverview:
    """Lärar-vy · full insyn i elevens ISK + fonder + aktier + ledger."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        student_name = st.display_name

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        _outer_sid = student_id

        class _Info:
            role = "student"
            student_id = _outer_sid

        avanza = get_avanza(_Info())  # type: ignore[arg-type]

    return V2TeacherAvanzaOverview(
        student_id=student_id,
        student_name=student_name,
        avanza=avanza,
    )


# === Bokföring (/v2/bokforing) — Fas 2H ===
#
# Verktyg 02 · Bokföring · "Transaktioner — där pengar talar".
# Återanvänder Transaction + Category-modeller (existerar sen v1) och
# CategorizationEngine för bulk-klass via regelmotor + history + LLM.


class V2BookkeepingTxRow(BaseModel):
    id: int
    date: _date
    account_id: int
    account_name: str
    amount: float
    raw_description: str
    normalized_merchant: Optional[str]
    category_id: Optional[int]
    category_name: Optional[str]
    ai_confidence: Optional[float]
    user_verified: bool
    is_transfer: bool
    notes: Optional[str]


class V2BookkeepingCategoryRef(BaseModel):
    id: int
    name: str
    parent_id: Optional[int]
    color: Optional[str]


class V2BookkeepingSummary(BaseModel):
    period_label: str
    period_start: _date
    period_end: _date
    total_transactions: int
    auto_classified: int  # rule + history + ai_confidence > 0.7
    manual_classified: int  # user_verified = True
    unclassified: int  # category_id IS NULL
    classification_rate_pct: float  # (total - unclassified) / total
    income_total: float
    expense_total: float  # absolute value
    saved_total: float  # income - expense
    saved_pct: float  # saved / income
    last_classified_at: Optional[datetime]


class V2BookkeepingResponse(BaseModel):
    student_id: int
    summary: V2BookkeepingSummary
    unclassified: list[V2BookkeepingTxRow]
    classified: list[V2BookkeepingTxRow]
    categories: list[V2BookkeepingCategoryRef]


def _empty_bokforing(student_id: int, today: _date) -> V2BookkeepingResponse:
    start = today.replace(day=1)
    return V2BookkeepingResponse(
        student_id=student_id,
        summary=V2BookkeepingSummary(
            period_label=today.strftime("%B %Y"),
            period_start=start, period_end=today,
            total_transactions=0,
            auto_classified=0, manual_classified=0,
            unclassified=0, classification_rate_pct=0,
            income_total=0, expense_total=0,
            saved_total=0, saved_pct=0,
            last_classified_at=None,
        ),
        unclassified=[], classified=[], categories=[],
    )


def _tx_to_row(
    t: Transaction,
    accounts_by_id: dict[int, str],
    cats_by_id: dict[int, str],
) -> V2BookkeepingTxRow:
    return V2BookkeepingTxRow(
        id=t.id,
        date=t.date,
        account_id=t.account_id,
        account_name=accounts_by_id.get(t.account_id, "—"),
        amount=float(t.amount),
        raw_description=t.raw_description,
        normalized_merchant=t.normalized_merchant,
        category_id=t.category_id,
        category_name=(
            cats_by_id.get(t.category_id) if t.category_id else None
        ),
        ai_confidence=t.ai_confidence,
        user_verified=bool(t.user_verified),
        is_transfer=bool(t.is_transfer),
        notes=t.notes,
    )


@router.get("/bokforing", response_model=V2BookkeepingResponse)
def get_bokforing(
    period: Optional[str] = None,
    info: TokenInfo = Depends(require_token),
) -> V2BookkeepingResponse:
    """Aggregat för Bokföring /v2/bokforing (Verktyg 02).

    Period default = innevarande månad. Format "YYYY-MM" eller "all".
    Returnerar:
    - summary med klassningsgrad + inkomster/utgifter/sparat
    - unclassified (top 50, sorted by date desc)
    - classified (top 100)
    - alla categories
    """
    today = _date.today()
    if info.role != "student" or info.student_id is None:
        return _empty_bokforing(0, today)

    # Beräkna period
    if period == "all":
        period_start = _date(2000, 1, 1)
        period_end = today
        period_label = "Hela perioden"
    else:
        if period:
            try:
                year, month = map(int, period.split("-"))
                period_start = _date(year, month, 1)
            except (ValueError, AttributeError):
                period_start = today.replace(day=1)
        else:
            period_start = today.replace(day=1)
        # period_end = sista dagen i månaden
        if period_start.month == 12:
            next_month = _date(period_start.year + 1, 1, 1)
        else:
            next_month = _date(
                period_start.year, period_start.month + 1, 1,
            )
        from datetime import timedelta as _td_b
        period_end = next_month - _td_b(days=1)
        period_label = period_start.strftime("%B %Y")

    with session_scope() as s:
        # Hämta alla konton + kategorier för lookup
        accounts = s.query(Account).all()
        accounts_by_id = {a.id: a.name for a in accounts}
        categories = s.query(Category).order_by(Category.name).all()
        cats_by_id = {c.id: c.name for c in categories}

        # Alla transaktioner i perioden
        txs_query = (
            s.query(Transaction)
            .filter(Transaction.date >= period_start)
            .filter(Transaction.date <= period_end)
        )
        all_txs = txs_query.all()
        total = len(all_txs)
        unclassified_txs = [
            t for t in all_txs if t.category_id is None
        ]
        classified_txs = [
            t for t in all_txs if t.category_id is not None
        ]
        manual_count = sum(1 for t in classified_txs if t.user_verified)
        auto_count = len(classified_txs) - manual_count

        # Inkomster/utgifter exkl. transfers
        income_total = sum(
            float(t.amount) for t in all_txs
            if not t.is_transfer and float(t.amount) > 0
        )
        expense_total = sum(
            -float(t.amount) for t in all_txs
            if not t.is_transfer and float(t.amount) < 0
        )
        saved = income_total - expense_total
        saved_pct = (
            (saved / income_total * 100) if income_total > 0 else 0
        )
        rate = (
            (len(classified_txs) / total * 100) if total > 0 else 0
        )

        # Senaste klassning
        last_class = (
            s.query(Transaction)
            .filter(Transaction.category_id.isnot(None))
            .filter(Transaction.user_verified.is_(True))
            .order_by(Transaction.id.desc())
            .first()
        )

        # Sortera nyast först + begränsa
        unclassified_txs.sort(
            key=lambda t: (t.date, t.id), reverse=True,
        )
        classified_txs.sort(
            key=lambda t: (t.date, t.id), reverse=True,
        )

        return V2BookkeepingResponse(
            student_id=info.student_id,
            summary=V2BookkeepingSummary(
                period_label=period_label,
                period_start=period_start,
                period_end=period_end,
                total_transactions=total,
                auto_classified=auto_count,
                manual_classified=manual_count,
                unclassified=len(unclassified_txs),
                classification_rate_pct=round(rate, 1),
                income_total=round(income_total, 2),
                expense_total=round(expense_total, 2),
                saved_total=round(saved, 2),
                saved_pct=round(saved_pct, 1),
                last_classified_at=(
                    last_class.date if last_class else None
                ),
            ),
            unclassified=[
                _tx_to_row(t, accounts_by_id, cats_by_id)
                for t in unclassified_txs[:50]
            ],
            classified=[
                _tx_to_row(t, accounts_by_id, cats_by_id)
                for t in classified_txs[:100]
            ],
            categories=[
                V2BookkeepingCategoryRef(
                    id=c.id, name=c.name,
                    parent_id=c.parent_id, color=c.color,
                )
                for c in categories
            ],
        )


class V2ClassifyTxIn(BaseModel):
    category_id: Optional[int] = None
    notes: Optional[str] = None


@router.patch(
    "/bokforing/transactions/{tx_id}",
    response_model=V2BookkeepingTxRow,
)
def patch_bookkeeping_transaction(
    tx_id: int,
    body: V2ClassifyTxIn,
    info: TokenInfo = Depends(require_token),
) -> V2BookkeepingTxRow:
    """Eleven klassar en transaktion · sätter category_id manuellt."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    with session_scope() as s:
        t = s.get(Transaction, tx_id)
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Saknas")
        if body.category_id is not None:
            cat = s.get(Category, body.category_id)
            if cat is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "Ogiltig kategori",
                )
            t.category_id = body.category_id
            t.user_verified = True
        if body.notes is not None:
            t.notes = body.notes
        s.flush()
        # Bygg row
        accounts_by_id = {
            a.id: a.name for a in s.query(Account).all()
        }
        cats_by_id = {
            c.id: c.name for c in s.query(Category).all()
        }
        return _tx_to_row(t, accounts_by_id, cats_by_id)


class V2BulkClassifyIn(BaseModel):
    transaction_ids: Optional[list[int]] = None
    period: Optional[str] = None


class V2BulkClassifyResult(BaseModel):
    processed: int
    classified: int
    via_rule: int
    via_history: int
    via_llm: int
    still_unclassified: int


@router.post(
    "/bokforing/classify-bulk",
    response_model=V2BulkClassifyResult,
)
def classify_bulk(
    body: V2BulkClassifyIn,
    info: TokenInfo = Depends(require_token),
) -> V2BulkClassifyResult:
    """Kör categorize_batch på alla unclassified transaktioner i
    perioden (eller på en lista). Använder regelmotor + history (LLM
    bara om aktiverat — annars hoppas det)."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")

    from ..categorize.engine import CategorizationEngine
    today = _date.today()

    with session_scope() as s:
        # Hitta unclassified
        q = s.query(Transaction).filter(Transaction.category_id.is_(None))
        if body.transaction_ids:
            q = q.filter(Transaction.id.in_(body.transaction_ids))
        elif body.period and body.period != "all":
            try:
                year, month = map(int, body.period.split("-"))
                from datetime import timedelta as _td_bb
                start = _date(year, month, 1)
                if month == 12:
                    end = _date(year + 1, 1, 1) - _td_bb(days=1)
                else:
                    end = _date(year, month + 1, 1) - _td_bb(days=1)
                q = q.filter(
                    Transaction.date >= start,
                    Transaction.date <= end,
                )
            except (ValueError, AttributeError):
                pass
        else:
            # Default: innevarande månad
            from datetime import timedelta as _td_bb2
            start = today.replace(day=1)
            if today.month == 12:
                end = _date(today.year + 1, 1, 1) - _td_bb2(days=1)
            else:
                end = _date(today.year, today.month + 1, 1) - _td_bb2(days=1)
            q = q.filter(
                Transaction.date >= start,
                Transaction.date <= end,
            )

        unclassified = q.all()
        if not unclassified:
            return V2BulkClassifyResult(
                processed=0, classified=0, via_rule=0,
                via_history=0, via_llm=0, still_unclassified=0,
            )

        engine = CategorizationEngine(s, llm=None)
        results = engine.categorize_batch(unclassified)

        applied_rule = 0
        applied_history = 0
        applied_llm = 0
        still_none = 0
        for tx, res in zip(unclassified, results):
            if res.category_id is not None:
                tx.category_id = res.category_id
                tx.normalized_merchant = res.merchant
                tx.ai_confidence = res.confidence
                # OBS: user_verified blir False — det är auto-klass
                if res.source == "rule":
                    applied_rule += 1
                elif res.source == "history":
                    applied_history += 1
                elif res.source == "llm":
                    applied_llm += 1
            else:
                still_none += 1

        s.flush()

        return V2BulkClassifyResult(
            processed=len(unclassified),
            classified=applied_rule + applied_history + applied_llm,
            via_rule=applied_rule,
            via_history=applied_history,
            via_llm=applied_llm,
            still_unclassified=still_none,
        )


# Lärar-overview
class V2TeacherBookkeepingOverview(BaseModel):
    student_id: int
    student_name: str
    bokforing: V2BookkeepingResponse


@router.get(
    "/teacher/students/{student_id}/bokforing-overview",
    response_model=V2TeacherBookkeepingOverview,
)
def teacher_bokforing_overview(
    student_id: int,
    period: Optional[str] = None,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherBookkeepingOverview:
    """Lärar-vy · klassningsgrad + alla transaktioner per period."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        student_name = st.display_name

    from ..school.engines import scope_context, scope_for_student
    with master_session() as m:
        st = m.get(Student, student_id)
        scope_key = scope_for_student(st)

    with scope_context(scope_key):
        _outer_sid = student_id
        _outer_period = period

        class _Info:
            role = "student"
            student_id = _outer_sid

        bok = get_bokforing(
            period=_outer_period, info=_Info(),  # type: ignore[arg-type]
        )

    return V2TeacherBookkeepingOverview(
        student_id=student_id,
        student_name=student_name,
        bokforing=bok,
    )


# === Endpoints ===

@router.get("/status", response_model=V2StatusResponse)
def get_v2_status(
    info: TokenInfo = Depends(require_token),
) -> V2StatusResponse:
    """Hämta nuvarande användares v2-status.

    Frontend pollar denna vid login för att avgöra om eleven ska
    redirectas till /v2/onboarding eller /v2/hub. Super-admins är
    alltid v2-eligible (men kan se v1 också om de väljer det).
    """
    if info.role == "demo":
        return V2StatusResponse(
            role="demo",
            v2_eligible=True,
            v2_onboarding_completed=False,
            v2_level=1,
            v2_spend_profile="sparsam",
            v2_partner_model="solo",
            is_super_admin=False,
        )

    if info.role == "teacher":
        if info.teacher_id is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Teacher token utan teacher_id",
            )
        with master_session() as db:
            teacher = db.get(Teacher, info.teacher_id)
            if not teacher:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, "Teacher hittades inte",
                )
            is_super = bool(getattr(teacher, "is_super_admin", False))
            return V2StatusResponse(
                role="teacher",
                v2_eligible=True,  # Lärare har alltid access
                v2_onboarding_completed=True,  # Lärare har ingen elev-onboarding
                v2_level=1,
                v2_spend_profile="sparsam",
                v2_partner_model="solo",
                is_super_admin=is_super,
            )

    # role == "student"
    if info.student_id is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Student token utan student_id",
        )
    with master_session() as db:
        student = db.get(Student, info.student_id)
        if not student:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Student hittades inte",
            )
        completed = student.v2_onboarding_completed_at is not None
        # v2_eligible: bara True om läraren explicit aktiverat v2 för
        # eleven. Default False — alla får v1 tills opt-in.
        eligible = bool(getattr(student, "v2_enabled", False))
        return V2StatusResponse(
            role="student",
            v2_eligible=eligible,
            v2_onboarding_completed=completed,
            v2_level=getattr(student, "v2_level", None) or 1,
            v2_spend_profile=getattr(student, "v2_spend_profile", None) or "sparsam",
            v2_fairness_choice=getattr(student, "v2_fairness_choice", None),
            v2_partner_model=getattr(student, "v2_partner_model", None) or "solo",
            is_super_admin=False,
        )


@router.post("/onboarding/complete", response_model=OnboardingCompleteResponse)
def complete_v2_onboarding(
    body: OnboardingCompleteRequest,
    info: TokenInfo = Depends(require_token),
) -> OnboardingCompleteResponse:
    """Spara v2-onboarding-svar. Idempotent: kan köras igen för att
    uppdatera värdering eller profil (men nivån kan bara läraren ändra).

    Super-admin / demo / teacher får 200 utan att skriva — endast för
    studenter sparas resultatet i master-DB:n.
    """
    now = datetime.utcnow()

    if info.role in ("demo", "teacher"):
        # Demo/teacher har ingen elev-profil att spara mot. Returnera
        # ändå 200 så frontend-flödet är enhetligt.
        return OnboardingCompleteResponse(
            student_id=0,
            completed_at=now,
            v2_level=1,
            redirect_to="/v2/hub",
        )

    if info.student_id is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Student token utan student_id",
        )

    with master_session() as db:
        student = db.get(Student, info.student_id)
        if not student:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Student hittades inte",
            )
        student.v2_onboarding_completed_at = now
        student.v2_spend_profile = body.spend_profile
        student.v2_fairness_choice = body.fairness_choice
        student.v2_partner_model = body.partner_model
        # v2_level rörs INTE här. Bara läraren får ändra via en
        # separat endpoint (kommer i nästa PR).
        db.commit()

        return OnboardingCompleteResponse(
            student_id=student.id,
            completed_at=now,
            v2_level=student.v2_level,
            redirect_to="/v2/hub",
        )


# === Onboarding-event-tracking (per-stegs-loggning) ===

class OnboardingEventRequest(BaseModel):
    step: int = Field(ge=1, le=8, description="Vilket onboarding-steg (1-8)")
    event_type: Literal["viewed", "back", "next", "completed", "abandoned"]
    duration_ms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Hur länge eleven var på det föregående steget (ms)",
    )
    payload: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Fri-text/JSON, t.ex. fairness-val i steg 7",
    )


class OnboardingEventResponse(BaseModel):
    event_id: int
    student_id: int


@router.post(
    "/onboarding/event",
    response_model=OnboardingEventResponse,
)
def log_onboarding_event(
    body: OnboardingEventRequest,
    info: TokenInfo = Depends(require_token),
) -> OnboardingEventResponse:
    """Logga en händelse i elevens onboarding-flöde.

    Frontend pingar denna vid varje stegväxling, plus vid completed/
    abandoned. Endast eleven själv får logga events för sig.
    Demo/teacher får 200 utan att skriva.
    """
    if info.role in ("demo", "teacher"):
        return OnboardingEventResponse(event_id=0, student_id=0)

    if info.student_id is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Student token utan student_id",
        )

    with master_session() as db:
        ev = V2OnboardingEvent(
            student_id=info.student_id,
            step=body.step,
            event_type=body.event_type,
            duration_ms=body.duration_ms,
            payload=body.payload,
        )
        db.add(ev)
        db.flush()
        return OnboardingEventResponse(
            event_id=ev.id,
            student_id=info.student_id,
        )


class OnboardingEventRow(BaseModel):
    event_id: int
    step: int
    event_type: str
    duration_ms: Optional[int]
    payload: Optional[str]
    created_at: datetime


@router.get(
    "/teacher/students/{student_id}/onboarding-events",
    response_model=list[OnboardingEventRow],
)
def get_onboarding_events(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> list[OnboardingEventRow]:
    """Lärar-vy: komplett event-historik för en elevs onboarding.

    Returneras kronologiskt (äldsta först). Lärare kan bara se sina
    egna elever.
    """
    if info.role != "teacher" or info.teacher_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast lärare kan se onboarding-historik.",
        )

    with master_session() as db:
        student = db.get(Student, student_id)
        if not student:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Student hittades inte",
            )
        if student.teacher_id != info.teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Du kan bara se dina egna elever.",
            )

        events = (
            db.query(V2OnboardingEvent)
            .filter(V2OnboardingEvent.student_id == student_id)
            .order_by(V2OnboardingEvent.created_at.asc())
            .all()
        )
        return [
            OnboardingEventRow(
                event_id=e.id,
                step=e.step,
                event_type=e.event_type,
                duration_ms=e.duration_ms,
                payload=e.payload,
                created_at=e.created_at,
            )
            for e in events
        ]


# === Lärar-endpoints för att hantera v2-aktivering per elev ===

class V2ToggleRequest(BaseModel):
    enabled: bool


class V2ToggleResponse(BaseModel):
    student_id: int
    v2_enabled: bool
    display_name: str


class V2BulkRequest(BaseModel):
    enabled: bool
    student_ids: Optional[list[int]] = Field(
        default=None,
        description=(
            "Lista av elev-ID:n. Om None: alla elever som tillhör denna "
            "lärare påverkas (t.ex. 'aktivera v2 för hela klassen')."
        ),
    )


class V2BulkResponse(BaseModel):
    affected: int
    enabled: bool


def _require_teacher(info: TokenInfo) -> int:
    if info.role != "teacher" or info.teacher_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast lärare kan hantera v2-aktivering.",
        )
    return info.teacher_id


@router.post(
    "/teacher/students/{student_id}/v2-toggle",
    response_model=V2ToggleResponse,
)
def toggle_v2_for_student(
    student_id: int,
    body: V2ToggleRequest,
    info: TokenInfo = Depends(require_token),
) -> V2ToggleResponse:
    """Sätt v2_enabled=True/False för en specifik elev.

    Bara elevens egen lärare får göra detta. När läraren aktiverar v2
    för en elev, hamnar eleven på /v2/onboarding vid nästa inloggning.
    """
    teacher_id = _require_teacher(info)

    with master_session() as db:
        student = db.get(Student, student_id)
        if not student:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Student hittades inte",
            )
        if student.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Du kan bara hantera dina egna elever.",
            )
        student.v2_enabled = body.enabled
        # När v2 aktiveras: markera v1-onboarding som "klar" så App.tsx
        # inte visar v1-onboardingen för en v2-elev. v2-onboardingen
        # ligger på /v2/onboarding och triggas av DashboardV2Guard.
        if body.enabled and not student.onboarding_completed:
            student.onboarding_completed = True
        db.commit()
        return V2ToggleResponse(
            student_id=student.id,
            v2_enabled=student.v2_enabled,
            display_name=student.display_name,
        )


@router.post("/teacher/students/v2-bulk", response_model=V2BulkResponse)
def bulk_toggle_v2(
    body: V2BulkRequest,
    info: TokenInfo = Depends(require_token),
) -> V2BulkResponse:
    """Aktivera/inaktivera v2 för flera elever på en gång.

    Om student_ids saknas: alla lärarens elever påverkas.
    Annars: bara de specifika ID:na (inom lärarens egen elev-pool).
    """
    teacher_id = _require_teacher(info)

    with master_session() as db:
        q = db.query(Student).filter(Student.teacher_id == teacher_id)
        if body.student_ids:
            q = q.filter(Student.id.in_(body.student_ids))
        students = q.all()
        for s in students:
            s.v2_enabled = body.enabled
            # När v2 aktiveras: markera v1-onboarding som "klar" så
            # App.tsx-blocket för v1-onboarding skippas.
            if body.enabled and not s.onboarding_completed:
                s.onboarding_completed = True
        db.commit()
        return V2BulkResponse(affected=len(students), enabled=body.enabled)


class V2RosterRow(BaseModel):
    student_id: int
    display_name: str
    class_label: Optional[str] = None
    v2_enabled: bool
    v2_onboarding_completed: bool
    v2_level: int


@router.get("/teacher/students/v2-roster", response_model=list[V2RosterRow])
def v2_roster(
    info: TokenInfo = Depends(require_token),
) -> list[V2RosterRow]:
    """Lärar-vy: lista alla elever med deras v2-status.

    Frontend använder detta för att visa toggles per elev + en
    bulk-knapp 'Aktivera v2 för alla'.
    """
    teacher_id = _require_teacher(info)

    with master_session() as db:
        students = (
            db.query(Student)
            .filter(Student.teacher_id == teacher_id)
            .order_by(Student.display_name)
            .all()
        )
        return [
            V2RosterRow(
                student_id=s.id,
                display_name=s.display_name,
                class_label=s.class_label,
                v2_enabled=bool(getattr(s, "v2_enabled", False)),
                v2_onboarding_completed=s.v2_onboarding_completed_at is not None,
                v2_level=getattr(s, "v2_level", None) or 1,
            )
            for s in students
        ]
