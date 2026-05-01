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

from datetime import datetime, timedelta
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
    Category, Scenario,
    BankIDSession,
    Rule,
)
from ..school.employer_models import (
    SalaryNegotiation as _SalaryNegotiation,
    NegotiationRound as _NegotiationRound,
    NegotiationConfig as _NegotiationConfig,
)
from ..school.models import (
    Module as _SchoolModule,
    ModuleStep as _SchoolModuleStep,
    StudentModule as _SchoolStudentModule,
    StudentStepProgress as _SchoolStepProgress,
    StudentStepHeartbeat as _SchoolStepHB,
    Message as _SchoolMessage,
    Assignment as _SchoolAssignment,
    FeedbackRead as _SchoolFeedbackRead,
    Competency as _SchoolCompetency,
    ModuleStepCompetency as _SchoolMSC,
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
from sqlalchemy import func as _func, or_


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


# === Moduler (/v2/moduler) — Fas 2I (Skola 09) ===
#
# Skola · Mina moduler · "3 i arbete, 7 möjliga". Återanvänder
# Module + ModuleStep + StudentModule + StudentStepProgress (master-DB).
# All data finns redan från v1 — v2-endpoint är aggregat-vy.


class V2ModuleStepRef(BaseModel):
    id: int
    sort_order: int
    kind: Literal["read", "watch", "reflect", "task", "quiz"]
    title: str
    completed: bool


class V2ModuleProgressOut(BaseModel):
    """Modul som eleven har påbörjat (eller fått tilldelad)."""
    student_module_id: int
    module_id: int
    title: str
    summary: Optional[str]
    is_template: bool
    teacher_owned: bool  # True om läraren skapade modulen specifikt
    sort_order: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    assigned_at: datetime
    step_count: int
    completed_step_count: int
    progress_pct: float  # 0–100
    current_step_no: Optional[int]  # 1-baserad position i kvarvarande
    estimated_minutes_left: Optional[int]


class V2ModuleAvailableOut(BaseModel):
    """Mall (system eller lärar-egen) som eleven kan starta."""
    module_id: int
    title: str
    summary: Optional[str]
    is_template: bool
    teacher_owned: bool
    step_count: int
    estimated_total_minutes: int  # ~5 min per steg som proxy


class V2ModulerSummary(BaseModel):
    in_progress_count: int
    completed_count: int
    available_count: int
    avg_progress_pct: float  # snitt över in_progress
    last_activity_at: Optional[datetime]


class V2ModulerResponse(BaseModel):
    student_id: int
    summary: V2ModulerSummary
    in_progress: list[V2ModuleProgressOut]
    completed: list[V2ModuleProgressOut]
    available: list[V2ModuleAvailableOut]


def _empty_moduler(student_id: int) -> V2ModulerResponse:
    return V2ModulerResponse(
        student_id=student_id,
        summary=V2ModulerSummary(
            in_progress_count=0, completed_count=0,
            available_count=0, avg_progress_pct=0,
            last_activity_at=None,
        ),
        in_progress=[], completed=[], available=[],
    )


@router.get("/moduler", response_model=V2ModulerResponse)
def get_moduler(
    info: TokenInfo = Depends(require_token),
) -> V2ModulerResponse:
    """Aggregat för Mina moduler /v2/moduler (Skola 09).

    Returnerar:
    - in_progress: tilldelade moduler där minst 1 steg startat OCH inte
      alla klara
    - completed: alla steg klara (ELLER completed_at satt)
    - available: system-mallar + lärarens egna mallar som eleven INTE
      redan har som StudentModule
    """
    if info.role != "student" or info.student_id is None:
        return _empty_moduler(0)

    sid = info.student_id
    out_progress: list[V2ModuleProgressOut] = []
    out_completed: list[V2ModuleProgressOut] = []
    out_available: list[V2ModuleAvailableOut] = []
    last_activity: Optional[datetime] = None
    progress_sum = 0.0
    progress_n = 0

    with master_session() as s:
        # Hämta studentens lärare för "lärar-mallar"
        student = s.get(Student, sid)
        teacher_id = student.teacher_id if student else None

        # Tilldelade moduler
        assigned = (
            s.query(_SchoolStudentModule)
            .filter(_SchoolStudentModule.student_id == sid)
            .order_by(_SchoolStudentModule.sort_order)
            .all()
        )
        assigned_module_ids = set()
        for sm in assigned:
            m = s.get(_SchoolModule, sm.module_id)
            if not m:
                continue
            assigned_module_ids.add(m.id)
            steps = (
                s.query(_SchoolModuleStep)
                .filter(_SchoolModuleStep.module_id == m.id)
                .order_by(_SchoolModuleStep.sort_order)
                .all()
            )
            step_ids = [st.id for st in steps]
            completed_progress = (
                s.query(_SchoolStepProgress)
                .filter(
                    _SchoolStepProgress.student_id == sid,
                    _SchoolStepProgress.step_id.in_(step_ids),
                    _SchoolStepProgress.completed_at.isnot(None),
                )
                .all()
                if step_ids else []
            )
            completed_count = len(completed_progress)
            step_count = len(steps)
            pct = (
                (completed_count / step_count * 100)
                if step_count > 0 else 0
            )
            # Track senaste aktivitet
            for cp in completed_progress:
                if cp.completed_at and (
                    last_activity is None
                    or cp.completed_at > last_activity
                ):
                    last_activity = cp.completed_at

            # Current step = första steg utan completed_at
            completed_step_ids = {
                cp.step_id for cp in completed_progress
            }
            current_step_no: Optional[int] = None
            for idx, st in enumerate(steps):
                if st.id not in completed_step_ids:
                    current_step_no = idx + 1
                    break

            # Estimera ~5 min per steg
            est_left = (
                (step_count - completed_count) * 5
                if step_count > 0 else 0
            )

            row = V2ModuleProgressOut(
                student_module_id=sm.id,
                module_id=m.id,
                title=m.title,
                summary=m.summary,
                is_template=bool(m.is_template),
                teacher_owned=(
                    teacher_id is not None
                    and m.teacher_id == teacher_id
                    and not m.is_template
                ),
                sort_order=sm.sort_order,
                started_at=sm.started_at,
                completed_at=sm.completed_at,
                assigned_at=sm.assigned_at,
                step_count=step_count,
                completed_step_count=completed_count,
                progress_pct=round(pct, 1),
                current_step_no=current_step_no,
                estimated_minutes_left=est_left,
            )

            is_done = (
                sm.completed_at is not None
                or (step_count > 0 and completed_count >= step_count)
            )
            if is_done:
                out_completed.append(row)
            else:
                out_progress.append(row)
                progress_sum += pct
                progress_n += 1

        # Tillgängliga (mallar som inte är tilldelade)
        templates_q = s.query(_SchoolModule).filter(
            _SchoolModule.is_template.is_(True),
        )
        if teacher_id is not None:
            # Inkludera även lärarens egna icke-mall-moduler som inte
            # tilldelats än
            templates_q = s.query(_SchoolModule).filter(
                or_(
                    _SchoolModule.is_template.is_(True),
                    _SchoolModule.teacher_id == teacher_id,
                ),
            )
        templates = templates_q.all()
        for m in templates:
            if m.id in assigned_module_ids:
                continue
            steps = (
                s.query(_SchoolModuleStep)
                .filter(_SchoolModuleStep.module_id == m.id)
                .all()
            )
            est = len(steps) * 5
            out_available.append(V2ModuleAvailableOut(
                module_id=m.id,
                title=m.title,
                summary=m.summary,
                is_template=bool(m.is_template),
                teacher_owned=(
                    teacher_id is not None
                    and m.teacher_id == teacher_id
                ),
                step_count=len(steps),
                estimated_total_minutes=est,
            ))

    avg_progress = (
        round(progress_sum / progress_n, 1) if progress_n > 0 else 0
    )

    # Sort
    out_progress.sort(key=lambda r: -r.progress_pct)
    out_completed.sort(
        key=lambda r: r.completed_at or datetime.min, reverse=True,
    )
    out_available.sort(key=lambda r: r.title)

    return V2ModulerResponse(
        student_id=info.student_id,
        summary=V2ModulerSummary(
            in_progress_count=len(out_progress),
            completed_count=len(out_completed),
            available_count=len(out_available),
            avg_progress_pct=avg_progress,
            last_activity_at=last_activity,
        ),
        in_progress=out_progress,
        completed=out_completed,
        available=out_available,
    )


# Lärar-overview
class V2TeacherModulerOverview(BaseModel):
    student_id: int
    student_name: str
    moduler: V2ModulerResponse


@router.get(
    "/teacher/students/{student_id}/moduler-overview",
    response_model=V2TeacherModulerOverview,
)
def teacher_moduler_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherModulerOverview:
    """Lärar-vy · alla elevens moduler + tillgängliga + framsteg."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        student_name = st.display_name

    # OBS: Module-data ligger i master-DB, inte scope-DB. Vi behöver
    # bara köra get_moduler med en låtsas-info som har student_id.
    _outer_sid = student_id

    class _Info:
        role = "student"
        student_id = _outer_sid

    moduler = get_moduler(_Info())  # type: ignore[arg-type]

    return V2TeacherModulerOverview(
        student_id=student_id,
        student_name=student_name,
        moduler=moduler,
    )


# === Investeringssimulator + Lånekalkylator (/v2/simulator) — Fas 2J ===
#
# Verktyg 05 · Investeringssimulator + Verktyg 06 · Lånekalkylator.
# Två rena kalkylatorer. Anropas stateless, men resultatet kan sparas
# som Scenario (existerande modell, kind="invest" eller "loan").


class V2InvestSimIn(BaseModel):
    start_amount: float = Field(..., ge=0)
    monthly_save: float = Field(..., ge=0, le=100000)
    return_pct: float = Field(..., ge=-5, le=20)  # årlig real avkastning
    years: int = Field(..., ge=1, le=80)
    schablonskatt_pct: float = Field(default=0.89, ge=0, le=5)
    is_isk: bool = True  # True=ISK schablon, False=depå 30% på vinst
    save_as_scenario: bool = False
    scenario_name: Optional[str] = None
    # Andra scenariot för jämförelse (valfritt)
    compare: Optional[dict] = None  # {monthly_save, years} — samma övriga


class V2InvestSimResult(BaseModel):
    start_amount: float
    monthly_save: float
    return_pct: float
    years: int
    is_isk: bool
    schablonskatt_pct: float
    total_invested: float  # start + monthly × 12 × years
    final_value: float
    total_growth: float  # final - total_invested
    total_taxes: float  # uppskattad skatt över hela perioden
    yearly_balances: list[float]  # snapshot per år (årets slut)
    saved_scenario_id: Optional[int] = None
    # Comparison (om compare specat)
    compare: Optional[dict] = None  # samma struktur, plus diff


def _compute_invest(
    start: float,
    monthly: float,
    pct: float,
    years: int,
    is_isk: bool,
    schablon_pct: float,
) -> dict:
    """Räkna investerings-tillväxt år för år.

    ISK: schablon på snitt-kapital varje år (ingen skatt på vinst).
    Depå: 30 % skatt på total vinst vid utbetalning (slutet).
    Returnerar dict med final_value, total_growth, total_taxes,
    yearly_balances.
    """
    r = pct / 100.0
    yearly_balances: list[float] = []
    balance = start
    total_taxes_isk = 0.0
    for _y in range(years):
        avg_during_year = balance + (monthly * 12) / 2  # snitt under året
        for _m in range(12):
            balance += monthly
            balance *= (1 + r / 12)  # månads-räntemetod
        if is_isk:
            tax = avg_during_year * (schablon_pct / 100.0)
            balance -= tax
            total_taxes_isk += tax
        yearly_balances.append(round(balance, 2))

    total_invested = start + monthly * 12 * years
    growth = balance - total_invested

    if is_isk:
        total_taxes = round(total_taxes_isk, 2)
        final = balance
    else:
        # Depå: 30 % på vinst vid uttag
        if growth > 0:
            tax = growth * 0.30
            final = balance - tax
            total_taxes = round(tax, 2)
        else:
            final = balance
            total_taxes = 0.0

    return {
        "total_invested": round(total_invested, 2),
        "final_value": round(final, 2),
        "total_growth": round(final - total_invested, 2),
        "total_taxes": total_taxes,
        "yearly_balances": yearly_balances,
    }


@router.post("/simulator/investment", response_model=V2InvestSimResult)
def simulate_investment(
    body: V2InvestSimIn,
    info: TokenInfo = Depends(require_token),
) -> V2InvestSimResult:
    """Räkna investerings-scenario (ISK eller depå)."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")

    res = _compute_invest(
        body.start_amount, body.monthly_save, body.return_pct,
        body.years, body.is_isk, body.schablonskatt_pct,
    )

    compare_out: Optional[dict] = None
    if body.compare:
        c_monthly = float(body.compare.get("monthly_save", 0))
        c_years = int(body.compare.get("years", body.years))
        c_start = float(body.compare.get("start_amount", body.start_amount))
        c_pct = float(body.compare.get("return_pct", body.return_pct))
        c_isk = bool(body.compare.get("is_isk", body.is_isk))
        c_res = _compute_invest(
            c_start, c_monthly, c_pct, c_years, c_isk, body.schablonskatt_pct,
        )
        compare_out = {
            "start_amount": c_start,
            "monthly_save": c_monthly,
            "return_pct": c_pct,
            "years": c_years,
            "is_isk": c_isk,
            **c_res,
            "diff_final": round(
                res["final_value"] - c_res["final_value"], 2,
            ),
        }

    saved_id: Optional[int] = None
    if body.save_as_scenario:
        with session_scope() as s:
            sc = Scenario(
                name=body.scenario_name or (
                    f"{int(body.monthly_save)} kr/mån i "
                    f"{body.years} år"
                ),
                kind="invest",
                params={
                    "start_amount": body.start_amount,
                    "monthly_save": body.monthly_save,
                    "return_pct": body.return_pct,
                    "years": body.years,
                    "is_isk": body.is_isk,
                    "schablonskatt_pct": body.schablonskatt_pct,
                    "compare": body.compare,
                },
                result={**res, "compare": compare_out},
            )
            s.add(sc)
            s.flush()
            saved_id = sc.id

    return V2InvestSimResult(
        start_amount=body.start_amount,
        monthly_save=body.monthly_save,
        return_pct=body.return_pct,
        years=body.years,
        is_isk=body.is_isk,
        schablonskatt_pct=body.schablonskatt_pct,
        **res,
        saved_scenario_id=saved_id,
        compare=compare_out,
    )


class V2LoanSimIn(BaseModel):
    principal: float = Field(..., ge=1, le=100000000)
    interest_rate_pct: float = Field(..., ge=0, le=30)
    term_months: int = Field(..., ge=1, le=600)
    extra_amortization_monthly: float = Field(default=0, ge=0)
    amortization_type: Literal["annuity", "straight"] = "annuity"
    save_as_scenario: bool = False
    scenario_name: Optional[str] = None


class V2LoanSimResult(BaseModel):
    principal: float
    interest_rate_pct: float
    term_months: int
    amortization_type: str
    extra_amortization_monthly: float
    monthly_payment_baseline: float  # utan extra-amortering
    total_paid_baseline: float
    total_interest_baseline: float
    monthly_payment_with_extra: float
    total_paid_with_extra: float
    total_interest_with_extra: float
    payoff_months_with_extra: int
    interest_savings: float  # baseline - with_extra
    months_saved: int
    schedule_first_12: list[dict]  # [{month, interest, principal, balance}]
    saved_scenario_id: Optional[int] = None


def _compute_loan_schedule(
    principal: float,
    rate_pct: float,
    term_months: int,
    amort_type: str,
    extra: float = 0.0,
) -> dict:
    """Räkna amorteringsplan. Returnerar dict med monthly_payment,
    total_paid, total_interest, payoff_months, schedule_first_12."""
    r_month = rate_pct / 100.0 / 12
    balance = principal
    total_interest = 0.0
    schedule: list[dict] = []
    months = 0
    if amort_type == "annuity":
        if r_month > 0:
            base_payment = (
                principal * r_month / (1 - (1 + r_month) ** -term_months)
            )
        else:
            base_payment = principal / term_months
    else:  # straight
        base_payment = principal / term_months  # bara amort, ränta tillkommer

    while balance > 0.005 and months < term_months + 600:
        months += 1
        interest = balance * r_month
        if amort_type == "annuity":
            principal_part = base_payment - interest
        else:
            principal_part = principal / term_months
        principal_part += extra
        if principal_part > balance:
            principal_part = balance
        payment = interest + principal_part
        balance -= principal_part
        total_interest += interest
        if months <= 12:
            schedule.append({
                "month": months,
                "payment": round(payment, 2),
                "interest": round(interest, 2),
                "principal": round(principal_part, 2),
                "balance": round(max(0.0, balance), 2),
            })
        if balance < 0.005:
            break

    return {
        "monthly_payment": round(base_payment + extra, 2),
        "total_paid": round(principal + total_interest, 2),
        "total_interest": round(total_interest, 2),
        "payoff_months": months,
        "schedule_first_12": schedule,
    }


@router.post("/simulator/loan", response_model=V2LoanSimResult)
def simulate_loan(
    body: V2LoanSimIn,
    info: TokenInfo = Depends(require_token),
) -> V2LoanSimResult:
    """Räkna låne-scenario (annuitet eller rak amortering)."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")

    baseline = _compute_loan_schedule(
        body.principal, body.interest_rate_pct, body.term_months,
        body.amortization_type, extra=0.0,
    )
    with_extra = _compute_loan_schedule(
        body.principal, body.interest_rate_pct, body.term_months,
        body.amortization_type, extra=body.extra_amortization_monthly,
    )

    interest_savings = (
        baseline["total_interest"] - with_extra["total_interest"]
    )
    months_saved = baseline["payoff_months"] - with_extra["payoff_months"]

    saved_id: Optional[int] = None
    if body.save_as_scenario:
        with session_scope() as s:
            sc = Scenario(
                name=body.scenario_name or (
                    f"{int(body.principal):,} kr · "
                    f"{body.interest_rate_pct:.1f} % · "
                    f"{body.term_months} mån"
                ).replace(",", " "),
                kind="loan",
                params={
                    "principal": body.principal,
                    "interest_rate_pct": body.interest_rate_pct,
                    "term_months": body.term_months,
                    "amortization_type": body.amortization_type,
                    "extra_amortization_monthly":
                        body.extra_amortization_monthly,
                },
                result={
                    "baseline": baseline,
                    "with_extra": with_extra,
                    "interest_savings": interest_savings,
                    "months_saved": months_saved,
                },
            )
            s.add(sc)
            s.flush()
            saved_id = sc.id

    return V2LoanSimResult(
        principal=body.principal,
        interest_rate_pct=body.interest_rate_pct,
        term_months=body.term_months,
        amortization_type=body.amortization_type,
        extra_amortization_monthly=body.extra_amortization_monthly,
        monthly_payment_baseline=baseline["monthly_payment"],
        total_paid_baseline=baseline["total_paid"],
        total_interest_baseline=baseline["total_interest"],
        monthly_payment_with_extra=with_extra["monthly_payment"],
        total_paid_with_extra=with_extra["total_paid"],
        total_interest_with_extra=with_extra["total_interest"],
        payoff_months_with_extra=with_extra["payoff_months"],
        interest_savings=round(interest_savings, 2),
        months_saved=months_saved,
        schedule_first_12=with_extra["schedule_first_12"],
        saved_scenario_id=saved_id,
    )


# Sparade scenarier
class V2SimulatorScenarioRow(BaseModel):
    id: int
    name: str
    kind: Literal["invest", "loan"]
    params: dict
    result: Optional[dict]
    created_at: datetime


@router.get(
    "/simulator/scenarios",
    response_model=list[V2SimulatorScenarioRow],
)
def list_simulator_scenarios(
    kind: Optional[Literal["invest", "loan"]] = None,
    info: TokenInfo = Depends(require_token),
) -> list[V2SimulatorScenarioRow]:
    """Lista sparade scenarier i scope-DB."""
    if info.role != "student" or info.student_id is None:
        return []
    with session_scope() as s:
        q = s.query(Scenario).filter(Scenario.kind.in_(["invest", "loan"]))
        if kind:
            q = q.filter(Scenario.kind == kind)
        rows = q.order_by(Scenario.id.desc()).all()
        return [
            V2SimulatorScenarioRow(
                id=r.id, name=r.name, kind=r.kind,  # type: ignore[arg-type]
                params=r.params or {}, result=r.result,
                created_at=r.created_at,
            )
            for r in rows
        ]


@router.delete("/simulator/scenarios/{scenario_id}", status_code=204)
def delete_simulator_scenario(
    scenario_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    with session_scope() as s:
        sc = s.get(Scenario, scenario_id)
        if sc is not None and sc.kind in ("invest", "loan"):
            s.delete(sc)
            s.flush()


# Lärar-overview
class V2TeacherSimulatorOverview(BaseModel):
    student_id: int
    student_name: str
    invest_count: int
    loan_count: int
    longest_horizon_years: int  # från sparade invest-scenarier
    biggest_principal: float  # från sparade loan-scenarier
    scenarios: list[V2SimulatorScenarioRow]


@router.get(
    "/teacher/students/{student_id}/simulator-overview",
    response_model=V2TeacherSimulatorOverview,
)
def teacher_simulator_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherSimulatorOverview:
    """Lärar-vy · alla elevens sparade scenarier (invest + loan)."""
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
        with session_scope() as s:
            rows = (
                s.query(Scenario)
                .filter(Scenario.kind.in_(["invest", "loan"]))
                .order_by(Scenario.id.desc())
                .all()
            )
            invest_rows = [r for r in rows if r.kind == "invest"]
            loan_rows = [r for r in rows if r.kind == "loan"]
            longest = max(
                (
                    int((r.params or {}).get("years", 0))
                    for r in invest_rows
                ),
                default=0,
            )
            biggest = max(
                (
                    float((r.params or {}).get("principal", 0))
                    for r in loan_rows
                ),
                default=0.0,
            )
            scenarios = [
                V2SimulatorScenarioRow(
                    id=r.id, name=r.name, kind=r.kind,  # type: ignore[arg-type]
                    params=r.params or {}, result=r.result,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    return V2TeacherSimulatorOverview(
        student_id=student_id,
        student_name=student_name,
        invest_count=len(invest_rows),
        loan_count=len(loan_rows),
        longest_horizon_years=longest,
        biggest_principal=biggest,
        scenarios=scenarios,
    )


# === Lärar-feedback (/v2/feedback) — Fas 2K (Skola) ===
#
# Aggregator-vy: lärar-feedback från 3 källor (master-DB):
# - Message (sender_role="teacher") — chat
# - StudentStepProgress.teacher_feedback — modul-steg
# - Assignment.teacher_feedback — uppdrag
#
# Lästa items spåras via FeedbackRead. Olästa-räknare uppdateras live.


class V2FeedbackKind(str):
    pass


class V2FeedbackItem(BaseModel):
    kind: Literal[
        "message", "module_step", "module_step_quiz",
        "module_step_done", "assignment",
    ]
    source_id: int  # ID i ursprungs-tabellen
    title: str  # Kort rubrik
    body: str  # Själva feedback-texten
    created_at: datetime
    is_unread: bool
    teacher_name: Optional[str]
    # Kontext för UI
    context_type: Optional[str]  # "module_id" | "assignment_kind" | osv
    context_id: Optional[int]
    context_label: Optional[str]  # T.ex. modul-titel
    link_target: Optional[str]  # T.ex. /modules/4 eller /v2/postladan


class V2FeedbackSummary(BaseModel):
    total_count: int
    unread_count: int
    message_count: int
    module_step_count: int
    assignment_count: int
    last_received_at: Optional[datetime]


class V2FeedbackResponse(BaseModel):
    student_id: int
    summary: V2FeedbackSummary
    items: list[V2FeedbackItem]


def _empty_feedback(student_id: int) -> V2FeedbackResponse:
    return V2FeedbackResponse(
        student_id=student_id,
        summary=V2FeedbackSummary(
            total_count=0, unread_count=0,
            message_count=0, module_step_count=0,
            assignment_count=0, last_received_at=None,
        ),
        items=[],
    )


def _aggregate_feedback_for_student(
    sid: int,
    period_days: Optional[int] = 90,
) -> V2FeedbackResponse:
    """Bygg feedback-list från 3 källor + FeedbackRead-tabell."""
    from datetime import timedelta as _td_fb
    cutoff = (
        datetime.utcnow() - _td_fb(days=period_days)
        if period_days else None
    )

    items: list[V2FeedbackItem] = []
    teacher_name_cache: dict[int, str] = {}

    with master_session() as s:
        # 0. Hämta alla read-poster för denna elev en gång
        reads = (
            s.query(_SchoolFeedbackRead)
            .filter(_SchoolFeedbackRead.student_id == sid)
            .all()
        )
        read_keys: set[tuple[str, int]] = {
            (r.kind, r.source_id) for r in reads
        }

        # Helper: hitta lärar-namn via teacher_id
        def _t_name(tid: Optional[int]) -> Optional[str]:
            if tid is None:
                return None
            if tid in teacher_name_cache:
                return teacher_name_cache[tid]
            t = s.get(Teacher, tid)
            n = t.name if t else None
            teacher_name_cache[tid] = n  # type: ignore[assignment]
            return n

        # 1. Messages (sender_role=teacher)
        msgs_q = (
            s.query(_SchoolMessage)
            .filter(_SchoolMessage.student_id == sid)
            .filter(_SchoolMessage.sender_role == "teacher")
            .order_by(_SchoolMessage.created_at.desc())
        )
        if cutoff:
            msgs_q = msgs_q.filter(_SchoolMessage.created_at >= cutoff)
        for m in msgs_q.all():
            # Message har eget read_at — kombinera med FeedbackRead
            is_unread = (
                m.read_at is None
                and ("message", m.id) not in read_keys
            )
            short = (
                (m.body or "").replace("\n", " ").strip()[:80]
                + ("…" if len(m.body or "") > 80 else "")
            )
            items.append(V2FeedbackItem(
                kind="message",
                source_id=m.id,
                title=short or "Chat-meddelande",
                body=m.body,
                created_at=m.created_at,
                is_unread=is_unread,
                teacher_name=_t_name(m.teacher_id),
                context_type=m.context_type,
                context_id=m.context_id,
                context_label=None,
                link_target="/v2/postladan",
            ))

        # 2. StudentStepProgress.teacher_feedback (modul-steg)
        prog_q = (
            s.query(_SchoolStepProgress)
            .filter(_SchoolStepProgress.student_id == sid)
            .filter(_SchoolStepProgress.teacher_feedback.isnot(None))
            .order_by(_SchoolStepProgress.feedback_at.desc().nullslast())
        )
        if cutoff:
            prog_q = prog_q.filter(
                or_(
                    _SchoolStepProgress.feedback_at >= cutoff,
                    _SchoolStepProgress.feedback_at.is_(None),
                ),
            )
        for p in prog_q.all():
            step = s.get(_SchoolModuleStep, p.step_id)
            module = (
                s.get(_SchoolModule, step.module_id)
                if step else None
            )
            step_kind = step.kind if step else "—"
            # Bestäm "kind"
            if step_kind == "quiz":
                k = "module_step_quiz"
            elif p.completed_at is not None and p.feedback_at is not None:
                k = "module_step_done"
            else:
                k = "module_step"
            ctx_label = (
                f"{module.title} · {step.title}"
                if step and module
                else (step.title if step else "Modul-steg")
            )
            items.append(V2FeedbackItem(
                kind=k,  # type: ignore[arg-type]
                source_id=p.id,
                title=ctx_label,
                body=p.teacher_feedback or "",
                created_at=p.feedback_at or p.created_at,
                is_unread=("module_step", p.id) not in read_keys,
                teacher_name=None,  # Step-feedback har inte teacher_id
                context_type="module_id",
                context_id=module.id if module else None,
                context_label=module.title if module else None,
                link_target=(
                    f"/modules/{module.id}" if module else None
                ),
            ))

        # 3. Assignment.teacher_feedback (uppdrag)
        ass_q = (
            s.query(_SchoolAssignment)
            .filter(_SchoolAssignment.student_id == sid)
            .filter(_SchoolAssignment.teacher_feedback.isnot(None))
            .order_by(
                _SchoolAssignment.teacher_feedback_at.desc().nullslast(),
            )
        )
        if cutoff:
            ass_q = ass_q.filter(
                or_(
                    _SchoolAssignment.teacher_feedback_at >= cutoff,
                    _SchoolAssignment.teacher_feedback_at.is_(None),
                ),
            )
        for a in ass_q.all():
            items.append(V2FeedbackItem(
                kind="assignment",
                source_id=a.id,
                title=a.title,
                body=a.teacher_feedback or "",
                created_at=a.teacher_feedback_at or datetime.utcnow(),
                is_unread=("assignment", a.id) not in read_keys,
                teacher_name=None,
                context_type="assignment_kind",
                context_id=a.id,
                context_label=a.kind,
                link_target=None,
            ))

    items.sort(key=lambda i: i.created_at, reverse=True)
    unread = sum(1 for i in items if i.is_unread)
    last = items[0].created_at if items else None
    msg_n = sum(1 for i in items if i.kind == "message")
    step_n = sum(1 for i in items if i.kind.startswith("module_step"))
    ass_n = sum(1 for i in items if i.kind == "assignment")
    return V2FeedbackResponse(
        student_id=sid,
        summary=V2FeedbackSummary(
            total_count=len(items),
            unread_count=unread,
            message_count=msg_n,
            module_step_count=step_n,
            assignment_count=ass_n,
            last_received_at=last,
        ),
        items=items,
    )


@router.get("/feedback", response_model=V2FeedbackResponse)
def get_feedback(
    period_days: int = 90,
    info: TokenInfo = Depends(require_token),
) -> V2FeedbackResponse:
    """Aggregat för Lärar-feedback /v2/feedback (Skola).

    Sammanställer alla feedback-typer från läraren senaste N dagar.
    """
    if info.role != "student" or info.student_id is None:
        return _empty_feedback(0)
    return _aggregate_feedback_for_student(info.student_id, period_days)


class V2FeedbackMarkReadIn(BaseModel):
    items: list[dict]  # [{kind, source_id}, ...]


class V2FeedbackMarkReadResult(BaseModel):
    marked: int
    already_read: int


@router.post(
    "/feedback/mark-read",
    response_model=V2FeedbackMarkReadResult,
)
def mark_feedback_read(
    body: V2FeedbackMarkReadIn,
    info: TokenInfo = Depends(require_token),
) -> V2FeedbackMarkReadResult:
    """Markera feedback-items som lästa. Idempotent."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    sid = info.student_id
    valid_kinds = {
        "message", "module_step",
        "module_step_quiz", "module_step_done",
        "assignment",
    }
    marked = 0
    already = 0
    with master_session() as s:
        for item in body.items:
            kind = item.get("kind")
            source_id = item.get("source_id")
            if (
                not isinstance(kind, str)
                or kind not in valid_kinds
                or not isinstance(source_id, int)
            ):
                continue
            # Normalisera modul-steg-varianter till "module_step"
            stored_kind = (
                "module_step"
                if kind.startswith("module_step")
                else kind
            )
            existing = (
                s.query(_SchoolFeedbackRead)
                .filter(
                    _SchoolFeedbackRead.student_id == sid,
                    _SchoolFeedbackRead.kind == stored_kind,
                    _SchoolFeedbackRead.source_id == source_id,
                )
                .first()
            )
            if existing is not None:
                already += 1
                continue
            s.add(_SchoolFeedbackRead(
                student_id=sid,
                kind=stored_kind,
                source_id=source_id,
            ))
            marked += 1
            # För Message-typ — uppdatera även Message.read_at för
            # konsekvent beteende mot v1-Postlådan
            if kind == "message":
                m = s.get(_SchoolMessage, source_id)
                if m is not None and m.read_at is None:
                    m.read_at = datetime.utcnow()
        s.commit()
    return V2FeedbackMarkReadResult(marked=marked, already_read=already)


# Lärar-overview
class V2TeacherFeedbackOverview(BaseModel):
    student_id: int
    student_name: str
    feedback: V2FeedbackResponse


@router.get(
    "/teacher/students/{student_id}/feedback-overview",
    response_model=V2TeacherFeedbackOverview,
)
def teacher_feedback_overview(
    student_id: int,
    period_days: int = 90,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherFeedbackOverview:
    """Lärar-vy · all feedback man gett eleven (samma data som elev)."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        student_name = st.display_name

    fb = _aggregate_feedback_for_student(student_id, period_days)
    return V2TeacherFeedbackOverview(
        student_id=student_id,
        student_name=student_name,
        feedback=fb,
    )


# === MariaV2 (Maria-AI lönesamtal) — Fas 2L ===
#
# Wrappar existerande /employer/negotiation/* med v2-style summary.
# Återanvänder SalaryNegotiation + NegotiationRound (master-DB).


class V2MariaRound(BaseModel):
    round_no: int
    student_message: str
    employer_response: str
    proposed_pct: Optional[float]
    created_at: datetime


class V2MariaNegotiation(BaseModel):
    id: int
    profession: str
    employer: str
    starting_salary: float
    avtal_norm_pct: Optional[float]
    avtal_code: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    status: Literal["active", "completed", "abandoned"]
    final_salary: Optional[float]
    final_pct: Optional[float]
    teacher_summary_md: Optional[str]
    rounds: list[V2MariaRound]
    max_rounds: int
    is_disabled: bool


class V2MariaResponse(BaseModel):
    student_id: int
    has_active: bool
    active: Optional[V2MariaNegotiation]
    history: list[V2MariaNegotiation]


def _negotiation_to_v2(
    n: _SalaryNegotiation,
    rounds: list[_NegotiationRound],
    max_rounds: int,
    is_disabled: bool,
) -> V2MariaNegotiation:
    return V2MariaNegotiation(
        id=n.id,
        profession=n.profession,
        employer=n.employer,
        starting_salary=float(n.starting_salary),
        avtal_norm_pct=n.avtal_norm_pct,
        avtal_code=n.avtal_code,
        started_at=n.started_at,
        completed_at=n.completed_at,
        status=n.status,  # type: ignore[arg-type]
        final_salary=(
            float(n.final_salary) if n.final_salary is not None else None
        ),
        final_pct=n.final_pct,
        teacher_summary_md=n.teacher_summary_md,
        rounds=[
            V2MariaRound(
                round_no=r.round_no,
                student_message=r.student_message,
                employer_response=r.employer_response,
                proposed_pct=r.proposed_pct,
                created_at=r.created_at,
            )
            for r in sorted(rounds, key=lambda x: x.round_no)
        ],
        max_rounds=max_rounds,
        is_disabled=is_disabled,
    )


@router.get("/maria", response_model=V2MariaResponse)
def get_maria(
    info: TokenInfo = Depends(require_token),
) -> V2MariaResponse:
    """Aktivt lönesamtal + historik. Återanvänder /employer/-modeller."""
    if info.role != "student" or info.student_id is None:
        return V2MariaResponse(
            student_id=0, has_active=False,
            active=None, history=[],
        )
    sid = info.student_id
    with master_session() as s:
        cfg = s.query(_NegotiationConfig).first()
        max_r = cfg.max_rounds if cfg else 5
        is_disabled = bool(cfg.disabled) if cfg else False
        all_n = (
            s.query(_SalaryNegotiation)
            .filter(_SalaryNegotiation.student_id == sid)
            .order_by(_SalaryNegotiation.started_at.desc())
            .all()
        )
        active_n = next((n for n in all_n if n.status == "active"), None)
        active_out: Optional[V2MariaNegotiation] = None
        if active_n is not None:
            rounds = (
                s.query(_NegotiationRound)
                .filter(
                    _NegotiationRound.negotiation_id == active_n.id,
                )
                .all()
            )
            active_out = _negotiation_to_v2(
                active_n, rounds, max_r, is_disabled,
            )
        history_out: list[V2MariaNegotiation] = []
        for n in all_n:
            if active_n and n.id == active_n.id:
                continue
            rounds = (
                s.query(_NegotiationRound)
                .filter(_NegotiationRound.negotiation_id == n.id)
                .all()
            )
            history_out.append(
                _negotiation_to_v2(n, rounds, max_r, is_disabled),
            )

        return V2MariaResponse(
            student_id=sid,
            has_active=active_n is not None,
            active=active_out,
            history=history_out,
        )


class V2TeacherMariaOverview(BaseModel):
    student_id: int
    student_name: str
    maria: V2MariaResponse


@router.get(
    "/teacher/students/{student_id}/maria-overview",
    response_model=V2TeacherMariaOverview,
)
def teacher_maria_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherMariaOverview:
    """Lärar-vy · alla elevens lönesamtal med fullständiga rondsvar."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        student_name = st.display_name

    _outer_sid = student_id

    class _Info:
        role = "student"
        student_id = _outer_sid

    maria = get_maria(_Info())  # type: ignore[arg-type]
    return V2TeacherMariaOverview(
        student_id=student_id,
        student_name=student_name,
        maria=maria,
    )


# === BankIDV2 (signering-simulator) — Fas 2L ===


class V2BankIDInvoiceRow(BaseModel):
    upcoming_id: int
    name: str
    amount: float
    due_date: _date
    is_recurring: bool
    is_anomaly: bool  # T.ex. tandläkare = ovanlig


class V2BankIDSessionOut(BaseModel):
    id: int
    upcoming_ids: list[int]
    total_amount: float
    invoice_count: int
    status: Literal["pending", "signed", "cancelled"]
    current_step: int
    signed_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    duration_seconds: Optional[int]
    invoices: list[V2BankIDInvoiceRow]
    notes: Optional[str]
    created_at: datetime


class V2BankIDStartIn(BaseModel):
    upcoming_ids: list[int]


@router.post("/bankid/sessions", response_model=V2BankIDSessionOut)
def start_bankid_session(
    body: V2BankIDStartIn,
    info: TokenInfo = Depends(require_token),
) -> V2BankIDSessionOut:
    """Skapa ny signerings-session från lista av upcoming-IDs."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    if not body.upcoming_ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Minst 1 faktura krävs",
        )

    with session_scope() as s:
        ups = (
            s.query(UpcomingTransaction)
            .filter(UpcomingTransaction.id.in_(body.upcoming_ids))
            .all()
        )
        if len(ups) != len(set(body.upcoming_ids)):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Vissa upcoming-IDs hittades inte",
            )
        total = sum(float(u.amount or 0) for u in ups)
        sess = BankIDSession(
            upcoming_ids=list({u.id for u in ups}),
            total_amount=Decimal(str(total)),
            invoice_count=len(ups),
            status="pending",
            current_step=4,
        )
        s.add(sess)
        s.flush()
        return _bankid_to_out(sess, ups)


def _bankid_to_out(
    sess: BankIDSession,
    ups: list[UpcomingTransaction],
) -> V2BankIDSessionOut:
    return V2BankIDSessionOut(
        id=sess.id,
        upcoming_ids=list(sess.upcoming_ids or []),
        total_amount=float(sess.total_amount),
        invoice_count=sess.invoice_count,
        status=sess.status,  # type: ignore[arg-type]
        current_step=sess.current_step,
        signed_at=sess.signed_at,
        cancelled_at=sess.cancelled_at,
        duration_seconds=sess.duration_seconds,
        notes=sess.notes,
        created_at=sess.created_at,
        invoices=[
            V2BankIDInvoiceRow(
                upcoming_id=u.id,
                name=u.name or "Faktura",
                amount=float(u.amount or 0),
                due_date=u.expected_date,
                is_recurring=bool(u.recurring_monthly),
                is_anomaly=False,  # framtida heuristik
            )
            for u in ups
        ],
    )


@router.get(
    "/bankid/sessions/{session_id}",
    response_model=V2BankIDSessionOut,
)
def get_bankid_session(
    session_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2BankIDSessionOut:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    with session_scope() as s:
        sess = s.get(BankIDSession, session_id)
        if sess is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Saknas")
        ups = (
            s.query(UpcomingTransaction)
            .filter(
                UpcomingTransaction.id.in_(sess.upcoming_ids or []),
            )
            .all()
        )
        return _bankid_to_out(sess, ups)


class V2BankIDSignIn(BaseModel):
    duration_seconds: Optional[int] = None  # från frontend-timer


@router.post(
    "/bankid/sessions/{session_id}/sign",
    response_model=V2BankIDSessionOut,
)
def sign_bankid_session(
    session_id: int,
    body: V2BankIDSignIn,
    info: TokenInfo = Depends(require_token),
) -> V2BankIDSessionOut:
    """Eleven signerar — markerar fakturor autogiro=True."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    with session_scope() as s:
        sess = s.get(BankIDSession, session_id)
        if sess is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Saknas")
        if sess.status != "pending":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Sessionen är {sess.status}",
            )
        sess.status = "signed"
        sess.signed_at = datetime.utcnow()
        sess.current_step = 6
        if body.duration_seconds is not None:
            sess.duration_seconds = body.duration_seconds
        # Markera relaterade upcomings som autogiro
        ups = (
            s.query(UpcomingTransaction)
            .filter(
                UpcomingTransaction.id.in_(sess.upcoming_ids or []),
            )
            .all()
        )
        for u in ups:
            if hasattr(u, "autogiro"):
                u.autogiro = True
        s.flush()
        return _bankid_to_out(sess, ups)


@router.post(
    "/bankid/sessions/{session_id}/cancel",
    response_model=V2BankIDSessionOut,
)
def cancel_bankid_session(
    session_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2BankIDSessionOut:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    with session_scope() as s:
        sess = s.get(BankIDSession, session_id)
        if sess is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Saknas")
        if sess.status != "pending":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Sessionen är {sess.status}",
            )
        sess.status = "cancelled"
        sess.cancelled_at = datetime.utcnow()
        s.flush()
        ups = (
            s.query(UpcomingTransaction)
            .filter(
                UpcomingTransaction.id.in_(sess.upcoming_ids or []),
            )
            .all()
        )
        return _bankid_to_out(sess, ups)


class V2BankIDListResponse(BaseModel):
    student_id: int
    sessions: list[V2BankIDSessionOut]
    pending_count: int
    signed_count: int
    cancelled_count: int
    total_signed_amount: float


@router.get("/bankid/sessions", response_model=V2BankIDListResponse)
def list_bankid_sessions(
    info: TokenInfo = Depends(require_token),
) -> V2BankIDListResponse:
    if info.role != "student" or info.student_id is None:
        return V2BankIDListResponse(
            student_id=0, sessions=[],
            pending_count=0, signed_count=0,
            cancelled_count=0, total_signed_amount=0,
        )
    with session_scope() as s:
        sessions = (
            s.query(BankIDSession)
            .order_by(BankIDSession.id.desc())
            .all()
        )
        # Hämta upcoming-info per session
        all_ids: set[int] = set()
        for sess in sessions:
            all_ids.update(sess.upcoming_ids or [])
        ups_by_id: dict[int, UpcomingTransaction] = {}
        if all_ids:
            for u in (
                s.query(UpcomingTransaction)
                .filter(UpcomingTransaction.id.in_(all_ids))
                .all()
            ):
                ups_by_id[u.id] = u
        out: list[V2BankIDSessionOut] = []
        for sess in sessions:
            sess_ups = [
                ups_by_id[uid]
                for uid in (sess.upcoming_ids or [])
                if uid in ups_by_id
            ]
            out.append(_bankid_to_out(sess, sess_ups))
        return V2BankIDListResponse(
            student_id=info.student_id,
            sessions=out,
            pending_count=sum(
                1 for s_ in out if s_.status == "pending"
            ),
            signed_count=sum(
                1 for s_ in out if s_.status == "signed"
            ),
            cancelled_count=sum(
                1 for s_ in out if s_.status == "cancelled"
            ),
            total_signed_amount=sum(
                s_.total_amount for s_ in out if s_.status == "signed"
            ),
        )


class V2TeacherBankIDOverview(BaseModel):
    student_id: int
    student_name: str
    bankid: V2BankIDListResponse


@router.get(
    "/teacher/students/{student_id}/bankid-overview",
    response_model=V2TeacherBankIDOverview,
)
def teacher_bankid_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherBankIDOverview:
    """Lärar-vy · alla elevens BankID-signeringar."""
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

        bankid = list_bankid_sessions(_Info())  # type: ignore[arg-type]

    return V2TeacherBankIDOverview(
        student_id=student_id,
        student_name=student_name,
        bankid=bankid,
    )


# === TxV2 (transaktion-detalj /v2/tx/{id}) — Fas 2M ===
#
# Drill-down från BokforingV2: visa enskild transaktion med kategori-
# select, sammanhangsfält, återkommande-mönster, och möjlighet att
# skapa Rule "merchant → kategori". Speglar prototypens p-tx.


class V2TxRecurringRow(BaseModel):
    id: int
    date: _date
    amount: float
    description: str
    is_self: bool  # True om detta är "denna" transaktion


class V2TxDetailResponse(BaseModel):
    id: int
    date: _date
    amount: float
    raw_description: str
    normalized_merchant: Optional[str]
    account_id: int
    account_name: str
    category_id: Optional[int]
    category_name: Optional[str]
    subcategory_id: Optional[int]
    subcategory_name: Optional[str]
    ai_confidence: Optional[float]
    user_verified: bool
    is_transfer: bool
    notes: Optional[str]
    tags: Optional[list]
    # Återkommande-mönster (samma normalized_merchant senaste 90 dgr)
    recurring: list[V2TxRecurringRow]
    recurring_total_30d: float  # snitt-summa per månad
    recurring_count_30d: int
    # Tillgängliga val
    categories: list[V2BookkeepingCategoryRef]
    accounts: list[dict]  # [{id, name, type}]
    # Befintlig regel som matchar denna merchant?
    existing_rule_id: Optional[int]


@router.get("/tx/{tx_id}", response_model=V2TxDetailResponse)
def get_tx_detail(
    tx_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TxDetailResponse:
    """Drill-down på en enskild transaktion med fullständig kontext."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")

    from datetime import timedelta as _td_tx
    today = _date.today()
    cutoff_90 = today - _td_tx(days=90)
    cutoff_30 = today - _td_tx(days=30)

    with session_scope() as s:
        t = s.get(Transaction, tx_id)
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Saknas")

        accounts = s.query(Account).all()
        accounts_by_id = {a.id: a.name for a in accounts}
        cats = s.query(Category).order_by(Category.name).all()
        cats_by_id = {c.id: c for c in cats}

        # Återkommande-mönster: matcha på normalized_merchant
        recurring: list[V2TxRecurringRow] = []
        recurring_30d_total = 0.0
        recurring_30d_count = 0
        if t.normalized_merchant:
            rec_rows = (
                s.query(Transaction)
                .filter(
                    Transaction.normalized_merchant == t.normalized_merchant,
                    Transaction.date >= cutoff_90,
                )
                .order_by(Transaction.date.desc())
                .limit(20)
                .all()
            )
            for r in rec_rows:
                recurring.append(V2TxRecurringRow(
                    id=r.id,
                    date=r.date,
                    amount=float(r.amount),
                    description=r.raw_description,
                    is_self=(r.id == t.id),
                ))
                if r.date >= cutoff_30 and r.id != t.id:
                    recurring_30d_count += 1
                    recurring_30d_total += abs(float(r.amount))

        # Existerande regel?
        existing_rule_id: Optional[int] = None
        if t.normalized_merchant:
            er = (
                s.query(Rule)
                .filter(
                    Rule.merchant == t.normalized_merchant,
                )
                .first()
            )
            if er is None:
                # Kolla också mot raw_description
                er = (
                    s.query(Rule)
                    .filter(Rule.pattern == t.raw_description)
                    .first()
                )
            existing_rule_id = er.id if er else None

        cat = cats_by_id.get(t.category_id) if t.category_id else None
        sub = cats_by_id.get(t.subcategory_id) if t.subcategory_id else None

        return V2TxDetailResponse(
            id=t.id,
            date=t.date,
            amount=float(t.amount),
            raw_description=t.raw_description,
            normalized_merchant=t.normalized_merchant,
            account_id=t.account_id,
            account_name=accounts_by_id.get(t.account_id, "—"),
            category_id=t.category_id,
            category_name=cat.name if cat else None,
            subcategory_id=t.subcategory_id,
            subcategory_name=sub.name if sub else None,
            ai_confidence=t.ai_confidence,
            user_verified=bool(t.user_verified),
            is_transfer=bool(t.is_transfer),
            notes=t.notes,
            tags=t.tags,
            recurring=recurring,
            recurring_total_30d=round(recurring_30d_total, 2),
            recurring_count_30d=recurring_30d_count,
            categories=[
                V2BookkeepingCategoryRef(
                    id=c.id, name=c.name,
                    parent_id=c.parent_id, color=c.color,
                )
                for c in cats
            ],
            accounts=[
                {"id": a.id, "name": a.name, "type": a.type}
                for a in accounts
            ],
            existing_rule_id=existing_rule_id,
        )


class V2TxClassifyIn(BaseModel):
    category_id: Optional[int] = None
    subcategory_id: Optional[int] = None
    account_id: Optional[int] = None
    notes: Optional[str] = None


@router.patch("/tx/{tx_id}", response_model=V2TxDetailResponse)
def patch_tx_detail(
    tx_id: int,
    body: V2TxClassifyIn,
    info: TokenInfo = Depends(require_token),
) -> V2TxDetailResponse:
    """Uppdatera kategori/underkategori/konto/anteckning på transaktion."""
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
        if body.subcategory_id is not None:
            t.subcategory_id = body.subcategory_id
        if body.account_id is not None:
            acc = s.get(Account, body.account_id)
            if acc is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "Ogiltigt konto",
                )
            t.account_id = body.account_id
        if body.notes is not None:
            t.notes = body.notes
        s.flush()
    return get_tx_detail(tx_id, info)


class V2TxCreateRuleIn(BaseModel):
    category_id: int
    pattern: Optional[str] = None  # default = transaction.normalized_merchant
    apply_to_existing: bool = True


class V2TxCreateRuleResult(BaseModel):
    rule_id: int
    pattern: str
    category_id: int
    applied_count: int  # antal tx som klassades om
    already_existed: bool


@router.post(
    "/tx/{tx_id}/create-rule",
    response_model=V2TxCreateRuleResult,
)
def create_rule_from_tx(
    tx_id: int,
    body: V2TxCreateRuleIn,
    info: TokenInfo = Depends(require_token),
) -> V2TxCreateRuleResult:
    """Skapa en kategoriserings-regel från en transaktion.

    "Foodora → Restaurang" — pattern matchar på raw_description (substring).
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    with session_scope() as s:
        t = s.get(Transaction, tx_id)
        if t is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Saknas")
        cat = s.get(Category, body.category_id)
        if cat is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Ogiltig kategori",
            )
        pattern = body.pattern or t.normalized_merchant or t.raw_description
        merchant = t.normalized_merchant

        # Existerar redan?
        existing = (
            s.query(Rule)
            .filter(Rule.pattern == pattern)
            .first()
        )
        if existing is not None:
            return V2TxCreateRuleResult(
                rule_id=existing.id,
                pattern=existing.pattern,
                category_id=existing.category_id,
                applied_count=0,
                already_existed=True,
            )

        rule = Rule(
            pattern=pattern,
            is_regex=False,
            merchant=merchant,
            category_id=body.category_id,
            priority=200,  # Användar-skapade > seed-regler
            source="user",
        )
        s.add(rule)
        s.flush()

        applied = 0
        if body.apply_to_existing:
            # Klassa alla okategoriserade tx med samma normalized_merchant
            ucat = (
                s.query(Transaction)
                .filter(Transaction.category_id.is_(None))
                .filter(
                    or_(
                        Transaction.normalized_merchant == merchant,
                        Transaction.raw_description.contains(pattern),
                    ),
                )
                .all()
            )
            for tx in ucat:
                tx.category_id = body.category_id
                tx.ai_confidence = 1.0  # rule-match
                applied += 1
            s.flush()

        return V2TxCreateRuleResult(
            rule_id=rule.id,
            pattern=rule.pattern,
            category_id=rule.category_id,
            applied_count=applied,
            already_existed=False,
        )


# === MeddelandenV2 (lärar-chat /v2/messages) — Fas 2M ===


class V2MessageRow(BaseModel):
    id: int
    sender_role: Literal["student", "teacher"]
    body: str
    context_type: Optional[str]
    context_id: Optional[int]
    created_at: datetime
    read_at: Optional[datetime]
    is_unread: bool


class V2MessagesResponse(BaseModel):
    student_id: int
    teacher_name: Optional[str]
    teacher_id: Optional[int]
    messages: list[V2MessageRow]
    unread_count: int
    last_received_at: Optional[datetime]


@router.get("/messages", response_model=V2MessagesResponse)
def get_messages(
    info: TokenInfo = Depends(require_token),
) -> V2MessagesResponse:
    """Tråd mellan elev och hennes lärare. Sorterad på datum."""
    if info.role != "student" or info.student_id is None:
        return V2MessagesResponse(
            student_id=0, teacher_name=None, teacher_id=None,
            messages=[], unread_count=0, last_received_at=None,
        )
    sid = info.student_id
    with master_session() as s:
        student = s.get(Student, sid)
        teacher_id = student.teacher_id if student else None
        teacher_name = None
        if teacher_id is not None:
            t = s.get(Teacher, teacher_id)
            teacher_name = t.name if t else None

        rows = (
            s.query(_SchoolMessage)
            .filter(_SchoolMessage.student_id == sid)
            .order_by(_SchoolMessage.created_at.asc())
            .all()
        )
        msgs = [
            V2MessageRow(
                id=m.id,
                sender_role=m.sender_role,  # type: ignore[arg-type]
                body=m.body,
                context_type=m.context_type,
                context_id=m.context_id,
                created_at=m.created_at,
                read_at=m.read_at,
                is_unread=(
                    m.sender_role == "teacher" and m.read_at is None
                ),
            )
            for m in rows
        ]
        unread = sum(1 for m in msgs if m.is_unread)
        last = next(
            (
                m.created_at for m in reversed(msgs)
                if m.sender_role == "teacher"
            ),
            None,
        )
        return V2MessagesResponse(
            student_id=sid,
            teacher_name=teacher_name,
            teacher_id=teacher_id,
            messages=msgs,
            unread_count=unread,
            last_received_at=last,
        )


class V2SendMessageIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)
    context_type: Optional[str] = None
    context_id: Optional[int] = None


@router.post("/messages", response_model=V2MessageRow)
def post_message(
    body: V2SendMessageIn,
    info: TokenInfo = Depends(require_token),
) -> V2MessageRow:
    """Eleven skickar meddelande till sin lärare."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    sid = info.student_id
    with master_session() as s:
        student = s.get(Student, sid)
        if student is None or student.teacher_id is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Ingen lärare kopplad",
            )
        m = _SchoolMessage(
            student_id=sid,
            teacher_id=student.teacher_id,
            sender_role="student",
            body=body.body.strip(),
            context_type=body.context_type,
            context_id=body.context_id,
        )
        s.add(m)
        s.commit()
        s.refresh(m)
        return V2MessageRow(
            id=m.id,
            sender_role="student",
            body=m.body,
            context_type=m.context_type,
            context_id=m.context_id,
            created_at=m.created_at,
            read_at=m.read_at,
            is_unread=False,
        )


@router.post(
    "/messages/{message_id}/mark-read",
    status_code=204,
)
def mark_message_read(
    message_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    with master_session() as s:
        m = s.get(_SchoolMessage, message_id)
        if m is None or m.student_id != info.student_id:
            return
        if m.read_at is None:
            m.read_at = datetime.utcnow()
            s.commit()


# === PortfolioV2 (kompetens-portfolio /v2/portfolio) — Fas 2M ===


class V2CompetencyEntry(BaseModel):
    competency_id: int
    key: str
    name: str
    description: Optional[str]
    is_system: bool
    mastery: float  # 0.0 – 1.0
    completed_steps: int
    last_event_at: Optional[datetime]
    level: Literal["B", "G", "F"]  # Basis | Grund | Fördjupning
    level_label: str


class V2PortfolioSummary(BaseModel):
    total_competencies: int
    basis_count: int
    grund_count: int
    fordjup_count: int
    last_event_at: Optional[datetime]


class V2PortfolioResponse(BaseModel):
    student_id: int
    summary: V2PortfolioSummary
    competencies: list[V2CompetencyEntry]


def _mastery_to_level(m: float) -> tuple[str, str]:
    if m >= 0.66:
        return ("F", "FÖRDJUPNING")
    if m >= 0.33:
        return ("G", "GRUND")
    return ("B", "BASIS")


@router.get("/portfolio", response_model=V2PortfolioResponse)
def get_portfolio(
    info: TokenInfo = Depends(require_token),
) -> V2PortfolioResponse:
    """14 systemkompetenser med B/G/F-nivå per elev."""
    if info.role != "student" or info.student_id is None:
        return V2PortfolioResponse(
            student_id=0,
            summary=V2PortfolioSummary(
                total_competencies=0,
                basis_count=0, grund_count=0, fordjup_count=0,
                last_event_at=None,
            ),
            competencies=[],
        )
    sid = info.student_id

    # Återanvänd existerande mastery-beräkning från api/modules
    from .modules import _compute_mastery_for_student

    with master_session() as s:
        mastery_by_cid = _compute_mastery_for_student(s, sid)
        comps = s.query(_SchoolCompetency).all()
        # Visa både system + lärar-egna kompetenser
        out: list[V2CompetencyEntry] = []
        last_event: Optional[datetime] = None
        b = g = f = 0
        for c in comps:
            m_tuple = mastery_by_cid.get(c.id, (0.0, 0, None))
            mastery, count, last = m_tuple
            level_short, level_label = _mastery_to_level(mastery)
            if level_short == "B":
                b += 1
            elif level_short == "G":
                g += 1
            else:
                f += 1
            if last is not None and (
                last_event is None or last > last_event
            ):
                last_event = last
            out.append(V2CompetencyEntry(
                competency_id=c.id,
                key=c.key,
                name=c.name,
                description=c.description,
                is_system=bool(c.is_system),
                mastery=round(mastery, 3),
                completed_steps=count,
                last_event_at=last,
                level=level_short,  # type: ignore[arg-type]
                level_label=level_label,
            ))
        # Sortera: F först, sen G, sen B; inom varje på namn
        level_order = {"F": 0, "G": 1, "B": 2}
        out.sort(key=lambda e: (level_order[e.level], e.name))

        return V2PortfolioResponse(
            student_id=sid,
            summary=V2PortfolioSummary(
                total_competencies=len(out),
                basis_count=b,
                grund_count=g,
                fordjup_count=f,
                last_event_at=last_event,
            ),
            competencies=out,
        )


# === LÄRAR-OVERVIEWS (Fas 2M) ===


class V2TeacherMessagesOverview(BaseModel):
    student_id: int
    student_name: str
    messages: V2MessagesResponse
    student_unread_count: int  # vad eleven inte läst
    teacher_unread_count: int  # vad läraren inte läst (eleven har skickat)


@router.get(
    "/teacher/students/{student_id}/messages-overview",
    response_model=V2TeacherMessagesOverview,
)
def teacher_messages_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherMessagesOverview:
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        student_name = st.display_name

    _outer_sid = student_id

    class _Info:
        role = "student"
        student_id = _outer_sid

    msgs = get_messages(_Info())  # type: ignore[arg-type]

    # Beräkna lärarens olästa (msg från elev där read_at IS NULL)
    teacher_unread = 0
    with master_session() as mdb:
        teacher_unread = (
            mdb.query(_SchoolMessage)
            .filter(_SchoolMessage.student_id == student_id)
            .filter(_SchoolMessage.sender_role == "student")
            .filter(_SchoolMessage.read_at.is_(None))
            .count()
        )

    return V2TeacherMessagesOverview(
        student_id=student_id,
        student_name=student_name,
        messages=msgs,
        student_unread_count=msgs.unread_count,
        teacher_unread_count=teacher_unread,
    )


class V2TeacherSendMessageIn(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)
    context_type: Optional[str] = None
    context_id: Optional[int] = None


@router.post(
    "/teacher/students/{student_id}/messages",
    response_model=V2MessageRow,
)
def teacher_post_message(
    student_id: int,
    body: V2TeacherSendMessageIn,
    info: TokenInfo = Depends(require_token),
) -> V2MessageRow:
    """Lärare skickar meddelande till sin elev."""
    teacher_id = _require_teacher(info)
    with master_session() as s:
        st = s.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        m = _SchoolMessage(
            student_id=student_id,
            teacher_id=teacher_id,
            sender_role="teacher",
            body=body.body.strip(),
            context_type=body.context_type,
            context_id=body.context_id,
        )
        s.add(m)
        s.commit()
        s.refresh(m)
        return V2MessageRow(
            id=m.id,
            sender_role="teacher",
            body=m.body,
            context_type=m.context_type,
            context_id=m.context_id,
            created_at=m.created_at,
            read_at=m.read_at,
            is_unread=True,  # nyss skickat, eleven inte läst
        )


class V2TeacherPortfolioOverview(BaseModel):
    student_id: int
    student_name: str
    portfolio: V2PortfolioResponse


@router.get(
    "/teacher/students/{student_id}/portfolio-overview",
    response_model=V2TeacherPortfolioOverview,
)
def teacher_portfolio_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherPortfolioOverview:
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast egen elev")
        student_name = st.display_name

    _outer_sid = student_id

    class _Info:
        role = "student"
        student_id = _outer_sid

    portfolio = get_portfolio(_Info())  # type: ignore[arg-type]
    return V2TeacherPortfolioOverview(
        student_id=student_id,
        student_name=student_name,
        portfolio=portfolio,
    )


# === MailDetailV2 (/v2/postladan/{id}/detail) — Fas 2N ===
#
# Drill-down från Postlådan: full detalj för kreditkortsfaktura och
# lönespec. Speglar prototypens p-cc och p-lonespec.


class V2CcTxRow(BaseModel):
    id: int
    date: _date
    amount: float
    raw_description: str
    normalized_merchant: Optional[str]
    category_id: Optional[int]
    category_name: Optional[str]
    is_classified: bool
    user_verified: bool


class V2CcInvoiceData(BaseModel):
    period_start: _date
    period_end: _date
    total_amount: float
    tx_count: int
    classified_count: int
    unclassified_count: int
    auto_classified_count: int
    avg_amount: float
    profile_label: str  # "balanserad" / "sparsam" / "slösa"
    consumer_avg: float  # Konsumentverket-schablon
    profile_avg: float  # baserat på StudentProfile.personality
    transactions: list[V2CcTxRow]
    prev_month_amount: Optional[float]  # föregående månads CC-faktura
    diff_pct_vs_prev: Optional[float]


class V2SalarySlipBreakdownRow(BaseModel):
    label: str
    amount: float
    is_total: bool


class V2SalarySlipData(BaseModel):
    period_label: str  # "april 2026"
    gross_salary: float
    tax: float
    net_salary: float
    ob_total: float  # OB-tillägg total
    pension_adjustment: float  # allmän pensionsavgift
    employer_social: float  # 31.42 % sociala avgifter
    employer_itp1: float  # 4.5 % ITP1
    employer_friskvard: float  # 417 kr/mån
    total_employer_cost: float
    net_lines: list[V2SalarySlipBreakdownRow]  # Specifikation
    employer_lines: list[V2SalarySlipBreakdownRow]  # Arbetsgivaravgifter
    prev_month_net: Optional[float]
    diff_vs_prev: Optional[float]


class V2MailDetailResponse(BaseModel):
    mail: V2MailItemRow
    cc_invoice: Optional[V2CcInvoiceData]  # endast för cred-invoice
    salary_slip: Optional[V2SalarySlipData]  # endast för salary_slip


def _profile_to_avg(personality: Optional[str]) -> tuple[str, float]:
    """Map personality → label + avg-belopp per köp."""
    if not personality:
        return ("balanserad", 102.0)
    p = personality.lower()
    if "spara" in p or "sparsam" in p or "snål" in p:
        return ("sparsam", 76.0)
    if "slösa" in p or "spende" in p:
        return ("slösa", 142.0)
    return ("balanserad", 102.0)


def _build_cc_invoice_data(
    s, mail: MailItem, account_id: Optional[int],
    profile_personality: Optional[str],
) -> Optional[V2CcInvoiceData]:
    """Bygg CC-detalj för kreditkortsfaktura. Hittar transaktioner
    inom 30 dgr före due_date på det aktuella kontot."""
    from datetime import timedelta as _td_cc
    if mail.due_date is None:
        return None
    period_end = mail.due_date - _td_cc(days=1)
    period_start = period_end - _td_cc(days=30)

    txs_q = (
        s.query(Transaction)
        .filter(Transaction.date >= period_start)
        .filter(Transaction.date <= period_end)
    )
    if account_id is not None:
        txs_q = txs_q.filter(Transaction.account_id == account_id)
    txs = txs_q.order_by(Transaction.date.desc()).all()

    cats_by_id = {c.id: c.name for c in s.query(Category).all()}

    classified = [t for t in txs if t.category_id is not None]
    unclassified = [t for t in txs if t.category_id is None]
    user_verified = [t for t in classified if t.user_verified]
    auto = [t for t in classified if not t.user_verified]

    total = sum(abs(float(t.amount)) for t in txs if float(t.amount) < 0)
    avg = total / len(txs) if txs else 0.0

    label, profile_avg = _profile_to_avg(profile_personality)
    consumer_avg = 89.0  # Konsumentverket-schablon

    # Föregående månad-faktura (samma sender + 30 dgr earlier)
    prev_period_end = period_start - _td_cc(days=1)
    prev_period_start = prev_period_end - _td_cc(days=30)
    prev_q = (
        s.query(Transaction)
        .filter(Transaction.date >= prev_period_start)
        .filter(Transaction.date <= prev_period_end)
    )
    if account_id is not None:
        prev_q = prev_q.filter(Transaction.account_id == account_id)
    prev_txs = prev_q.all()
    prev_total = sum(
        abs(float(t.amount)) for t in prev_txs if float(t.amount) < 0
    )
    diff_pct = None
    if prev_total > 0:
        diff_pct = round((total - prev_total) / prev_total * 100, 1)

    rows = [
        V2CcTxRow(
            id=t.id,
            date=t.date,
            amount=float(t.amount),
            raw_description=t.raw_description,
            normalized_merchant=t.normalized_merchant,
            category_id=t.category_id,
            category_name=cats_by_id.get(t.category_id) if t.category_id else None,
            is_classified=t.category_id is not None,
            user_verified=bool(t.user_verified),
        )
        for t in txs
    ]

    return V2CcInvoiceData(
        period_start=period_start,
        period_end=period_end,
        total_amount=round(total, 2),
        tx_count=len(txs),
        classified_count=len(classified),
        unclassified_count=len(unclassified),
        auto_classified_count=len(auto),
        avg_amount=round(avg, 2),
        profile_label=label,
        consumer_avg=consumer_avg,
        profile_avg=profile_avg,
        transactions=rows,
        prev_month_amount=round(prev_total, 2) if prev_total > 0 else None,
        diff_pct_vs_prev=diff_pct,
    )


def _build_salary_slip_data(
    mail: MailItem, profile: Optional[StudentProfile],
) -> Optional[V2SalarySlipData]:
    """Bygg lönespec-data från StudentProfile + mail.amount (netto)."""
    if profile is None:
        # Fallback från bara mail-info
        net = float(mail.amount or 0)
        gross = round(net * 1.387, 0)  # rough reverse
        tax = gross - net
        return V2SalarySlipData(
            period_label=(mail.body_meta or "")[:60],
            gross_salary=gross,
            tax=tax,
            net_salary=net,
            ob_total=0,
            pension_adjustment=0,
            employer_social=round(gross * 0.3142, 2),
            employer_itp1=round(gross * 0.045, 2),
            employer_friskvard=417.0,
            total_employer_cost=round(
                gross * (1 + 0.3142 + 0.045) + 417, 2,
            ),
            net_lines=[
                V2SalarySlipBreakdownRow(label="Bruttolön", amount=gross, is_total=False),
                V2SalarySlipBreakdownRow(label="Preliminärskatt", amount=-tax, is_total=False),
                V2SalarySlipBreakdownRow(label="Netto till lönekontot", amount=net, is_total=True),
            ],
            employer_lines=[
                V2SalarySlipBreakdownRow(
                    label="Sociala avgifter (31,42 %)",
                    amount=round(gross * 0.3142, 2),
                    is_total=False,
                ),
                V2SalarySlipBreakdownRow(
                    label="ITP1 — tjänstepension (4,5 %)",
                    amount=round(gross * 0.045, 2),
                    is_total=False,
                ),
                V2SalarySlipBreakdownRow(
                    label="Friskvårdsbidrag (5 000 kr / 12)",
                    amount=417.0,
                    is_total=False,
                ),
                V2SalarySlipBreakdownRow(
                    label="Total kostnad för arbetsgivaren",
                    amount=round(
                        gross * (1 + 0.3142 + 0.045) + 417, 2,
                    ),
                    is_total=True,
                ),
            ],
            prev_month_net=None,
            diff_vs_prev=None,
        )

    gross = float(profile.gross_salary_monthly or 0)
    net = float(profile.net_salary_monthly or 0)
    tax = gross - net  # förenklat — verklig spec inkluderar pension-justering

    # OB-tillägg uppskattning: ~1,5 % av brutto för vård-/serviceyrken
    profession_lower = (profile.profession or "").lower()
    has_ob = any(
        kw in profession_lower
        for kw in ["sköt", "läk", "service", "kassa", "vård"]
    )
    ob_total = round(gross * 0.015, 0) if has_ob else 0.0
    pension_adj = round(gross * 0.004, 0)  # ~0.4 % allmän pensionsavg
    employer_social = round(gross * 0.3142, 2)
    employer_itp1 = round(gross * 0.045, 2)
    employer_friskvard = 417.0
    total_emp = round(
        gross + employer_social + employer_itp1 + employer_friskvard, 2,
    )

    grund = round(gross - ob_total, 0)

    net_lines: list[V2SalarySlipBreakdownRow] = []
    if profile.profession:
        emp_label = profile.employer or "arbetsgivare"
        pct = "80 % tjänst" if "80" in (profile.profession or "") else ""
        if pct:
            net_lines.append(V2SalarySlipBreakdownRow(
                label=f"Grundlön ({pct})",
                amount=grund, is_total=False,
            ))
        else:
            net_lines.append(V2SalarySlipBreakdownRow(
                label="Grundlön", amount=grund, is_total=False,
            ))
    else:
        net_lines.append(V2SalarySlipBreakdownRow(
            label="Grundlön", amount=grund, is_total=False,
        ))
    if ob_total > 0:
        net_lines.append(V2SalarySlipBreakdownRow(
            label="OB-tillägg · totalt",
            amount=ob_total, is_total=False,
        ))
    net_lines.extend([
        V2SalarySlipBreakdownRow(
            label="Bruttolön", amount=gross, is_total=False,
        ),
        V2SalarySlipBreakdownRow(
            label="Preliminärskatt (tabell)",
            amount=-(tax + pension_adj), is_total=False,
        ),
        V2SalarySlipBreakdownRow(
            label="Allmän pensionsavgift (justering)",
            amount=-pension_adj, is_total=False,
        ),
        V2SalarySlipBreakdownRow(
            label="Netto till lönekontot",
            amount=net, is_total=True,
        ),
    ])

    employer_lines = [
        V2SalarySlipBreakdownRow(
            label="Sociala avgifter (31,42 %)",
            amount=employer_social, is_total=False,
        ),
        V2SalarySlipBreakdownRow(
            label="ITP1 — tjänstepension (4,5 %)",
            amount=employer_itp1, is_total=False,
        ),
        V2SalarySlipBreakdownRow(
            label="Friskvårdsbidrag (årligt 5 000 kr / 12)",
            amount=employer_friskvard, is_total=False,
        ),
        V2SalarySlipBreakdownRow(
            label="Total kostnad för arbetsgivaren",
            amount=total_emp, is_total=True,
        ),
    ]

    return V2SalarySlipData(
        period_label=mail.body_meta or "",
        gross_salary=gross,
        tax=tax,
        net_salary=net,
        ob_total=ob_total,
        pension_adjustment=pension_adj,
        employer_social=employer_social,
        employer_itp1=employer_itp1,
        employer_friskvard=employer_friskvard,
        total_employer_cost=total_emp,
        net_lines=net_lines,
        employer_lines=employer_lines,
        prev_month_net=None,
        diff_vs_prev=None,
    )


def _mail_to_row(m: MailItem) -> V2MailItemRow:
    return V2MailItemRow(
        id=m.id,
        sender=m.sender,
        sender_short=m.sender_short,
        sender_kind=m.sender_kind,  # type: ignore[arg-type]
        sender_meta=m.sender_meta,
        mail_type=m.mail_type,  # type: ignore[arg-type]
        subject=m.subject,
        body_meta=m.body_meta,
        body=m.body,
        amount=float(m.amount) if m.amount is not None else None,
        due_date=m.due_date,
        received_at=m.received_at,
        status=m.status,  # type: ignore[arg-type]
        upcoming_id=m.upcoming_id,
        transaction_id=m.transaction_id,
        is_recurring=bool(m.is_recurring),
        ocr_reference=m.ocr_reference,
        bankgiro=m.bankgiro,
        notes=m.notes,
    )


@router.get(
    "/postladan/{mail_id}/detail",
    response_model=V2MailDetailResponse,
)
def get_mail_detail(
    mail_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2MailDetailResponse:
    """Drill-down för MailItem · returnerar utvidgad data per typ."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")

    profile: Optional[StudentProfile] = None
    with master_session() as mdb:
        profile = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == info.student_id)
            .first()
        )

    with session_scope() as s:
        m = s.get(MailItem, mail_id)
        if m is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Saknas")

        # Markera viewed om unhandled
        if m.status == "unhandled":
            m.status = "viewed"
            s.flush()

        cc_data: Optional[V2CcInvoiceData] = None
        salary_data: Optional[V2SalarySlipData] = None

        if m.mail_type == "invoice" and m.sender_kind == "cred":
            # Hitta CC-konto baserat på sender
            cc_account = (
                s.query(Account)
                .filter(Account.type == "credit")
                .order_by(Account.id.desc())
                .first()
            )
            account_id = cc_account.id if cc_account else None
            personality = profile.personality if profile else None
            cc_data = _build_cc_invoice_data(
                s, m, account_id, personality,
            )
        elif m.mail_type == "salary_slip":
            salary_data = _build_salary_slip_data(m, profile)

        return V2MailDetailResponse(
            mail=_mail_to_row(m),
            cc_invoice=cc_data,
            salary_slip=salary_data,
        )


# Lärar-overview för MailDetail — full insyn i specifikt brev
class V2TeacherMailDetailOverview(BaseModel):
    student_id: int
    student_name: str
    detail: V2MailDetailResponse


@router.get(
    "/teacher/students/{student_id}/mail/{mail_id}/detail",
    response_model=V2TeacherMailDetailOverview,
)
def teacher_mail_detail_overview(
    student_id: int,
    mail_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherMailDetailOverview:
    """Lärar-vy · full insyn i ett specifikt brev (utan att markera
    viewed)."""
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
        # Inline detail-build utan att markera viewed
        profile: Optional[StudentProfile] = None
        with master_session() as mdb:
            profile = (
                mdb.query(StudentProfile)
                .filter(StudentProfile.student_id == student_id)
                .first()
            )

        with session_scope() as s:
            mail = s.get(MailItem, mail_id)
            if mail is None:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, "Brevet hittades inte",
                )
            cc_data: Optional[V2CcInvoiceData] = None
            salary_data: Optional[V2SalarySlipData] = None
            if mail.mail_type == "invoice" and mail.sender_kind == "cred":
                cc_account = (
                    s.query(Account)
                    .filter(Account.type == "credit")
                    .order_by(Account.id.desc())
                    .first()
                )
                account_id = cc_account.id if cc_account else None
                personality = profile.personality if profile else None
                cc_data = _build_cc_invoice_data(
                    s, mail, account_id, personality,
                )
            elif mail.mail_type == "salary_slip":
                salary_data = _build_salary_slip_data(mail, profile)
            detail = V2MailDetailResponse(
                mail=_mail_to_row(mail),
                cc_invoice=cc_data,
                salary_slip=salary_data,
            )

    return V2TeacherMailDetailOverview(
        student_id=student_id,
        student_name=student_name,
        detail=detail,
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


# === UppdragV2 (Mina uppdrag · Fas 2P) ===
#
# Wrappar existerande Assignment + evaluate() med v2-style-summary.
# Speglar prototypens p-uppdrag: aktiva uppdrag (med deadline-urgency)
# + klara/godkända + lärar-feedback. Eleven kan självmarkera free_text
# som klart; lärare kan begära retry via existerande feedback-flow.


def _urgency_for_due(due: Optional[datetime]) -> tuple[Optional[int], str]:
    """Returnerar (days_until_due, urgency-label).

    urgency: 'overdue' | 'today' | 'tomorrow' | 'this_week' | 'later' | 'none'
    """
    if due is None:
        return None, "none"
    today = datetime.utcnow().date()
    diff = (due.date() - today).days
    if diff < 0:
        return diff, "overdue"
    if diff == 0:
        return 0, "today"
    if diff == 1:
        return 1, "tomorrow"
    if diff <= 7:
        return diff, "this_week"
    return diff, "later"


class V2UppdragRow(BaseModel):
    id: int
    teacher_id: int
    title: str
    description: str
    kind: str
    target_year_month: Optional[str]
    params: Optional[dict]
    due_date: Optional[datetime]
    created_at: datetime
    status: Literal["not_started", "in_progress", "completed"]
    progress: str
    detail: Optional[dict] = None
    teacher_feedback: Optional[str] = None
    teacher_feedback_at: Optional[datetime] = None
    manually_completed_at: Optional[datetime] = None
    days_until_due: Optional[int] = None
    urgency: Literal[
        "overdue", "today", "tomorrow", "this_week", "later", "none",
    ] = "none"


class V2UppdragSummary(BaseModel):
    active_count: int
    completed_count: int
    overdue_count: int
    nearest_due_date: Optional[datetime] = None
    nearest_due_label: Optional[str] = None
    completed_this_month: int = 0


class V2UppdragResponse(BaseModel):
    student_id: int
    teacher_name: Optional[str] = None
    active: list[V2UppdragRow]
    completed: list[V2UppdragRow]
    summary: V2UppdragSummary


def _evaluate_for_v2(a: _SchoolAssignment, student: Student) -> V2UppdragRow:
    from ..teacher.assignments import evaluate as _evaluate

    try:
        res = _evaluate(a, student)
        status_val = res.status
        progress = res.progress
        detail = res.detail
    except Exception:  # pragma: no cover — defensiv
        status_val = "in_progress"
        progress = "Kunde inte utvärdera uppdraget"
        detail = None
    days, urgency = _urgency_for_due(a.due_date)
    return V2UppdragRow(
        id=a.id,
        teacher_id=a.teacher_id,
        title=a.title,
        description=a.description,
        kind=a.kind,
        target_year_month=a.target_year_month,
        params=a.params,
        due_date=a.due_date,
        created_at=a.created_at,
        status=status_val,  # type: ignore[arg-type]
        progress=progress,
        detail=detail,
        teacher_feedback=a.teacher_feedback,
        teacher_feedback_at=a.teacher_feedback_at,
        manually_completed_at=a.manually_completed_at,
        days_until_due=days,
        urgency=urgency,  # type: ignore[arg-type]
    )


def _build_uppdrag_response(student_id: int) -> V2UppdragResponse:
    with master_session() as s:
        student = s.get(Student, student_id)
        if not student:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Eleven hittades inte",
            )
        teacher_name: Optional[str] = None
        if student.teacher_id is not None:
            t = s.get(Teacher, student.teacher_id)
            teacher_name = t.name if t else None
        rows = (
            s.query(_SchoolAssignment)
            .filter(_SchoolAssignment.student_id == student.id)
            .order_by(_SchoolAssignment.created_at.desc())
            .all()
        )
        evaluated = [_evaluate_for_v2(a, student) for a in rows]

    active: list[V2UppdragRow] = []
    completed: list[V2UppdragRow] = []
    overdue = 0
    nearest: Optional[V2UppdragRow] = None
    completed_this_month = 0
    today = datetime.utcnow()
    month_key = today.strftime("%Y-%m")

    for r in evaluated:
        if r.status == "completed":
            completed.append(r)
            mc = r.manually_completed_at
            if mc and mc.strftime("%Y-%m") == month_key:
                completed_this_month += 1
        else:
            active.append(r)
            if r.urgency == "overdue":
                overdue += 1
            if r.due_date is not None:
                if nearest is None or (
                    nearest.due_date is not None
                    and r.due_date < nearest.due_date
                ):
                    nearest = r

    # Sortera aktiva: först overdue, sen tidigast deadline, sen senast skapad
    def _sort_key(row: V2UppdragRow) -> tuple:
        urgency_rank = {
            "overdue": 0, "today": 1, "tomorrow": 2,
            "this_week": 3, "later": 4, "none": 5,
        }
        return (
            urgency_rank.get(row.urgency, 9),
            row.due_date or datetime.max,
            -row.created_at.timestamp(),
        )

    active.sort(key=_sort_key)
    # Klara: senast manuellt klar först
    completed.sort(
        key=lambda r: (r.manually_completed_at or r.created_at),
        reverse=True,
    )

    nearest_label: Optional[str] = None
    if nearest is not None and nearest.due_date is not None:
        d = nearest.days_until_due
        if d is None:
            nearest_label = nearest.due_date.strftime("%-d %b")
        elif d < 0:
            nearest_label = f"försenad {abs(d)} d"
        elif d == 0:
            nearest_label = "idag"
        elif d == 1:
            nearest_label = "imorgon"
        else:
            nearest_label = f"{d} dgr"

    summary = V2UppdragSummary(
        active_count=len(active),
        completed_count=len(completed),
        overdue_count=overdue,
        nearest_due_date=nearest.due_date if nearest else None,
        nearest_due_label=nearest_label,
        completed_this_month=completed_this_month,
    )
    return V2UppdragResponse(
        student_id=student_id,
        teacher_name=teacher_name,
        active=active,
        completed=completed,
        summary=summary,
    )


@router.get("/uppdrag", response_model=V2UppdragResponse)
def get_uppdrag(
    info: TokenInfo = Depends(require_token),
) -> V2UppdragResponse:
    """Elevens egna uppdrag · live-status från evaluate() · sorterat
    på deadline-urgency."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast elever har egna uppdrag",
        )
    return _build_uppdrag_response(info.student_id)


class V2UppdragSelfCompleteOut(BaseModel):
    ok: bool
    assignment_id: int
    manually_completed_at: datetime


@router.post(
    "/uppdrag/{assignment_id}/self-complete",
    response_model=V2UppdragSelfCompleteOut,
)
def self_complete_uppdrag(
    assignment_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2UppdragSelfCompleteOut:
    """Eleven markerar ett free_text-uppdrag som klart. Andra kind:s
    bedöms automatiskt och kan inte själv-klarmarkeras."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Endast elever",
        )
    with master_session() as s:
        a = (
            s.query(_SchoolAssignment)
            .filter(
                _SchoolAssignment.id == assignment_id,
                _SchoolAssignment.student_id == info.student_id,
            )
            .first()
        )
        if not a:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "Uppdraget finns ej eller tillhör inte dig",
            )
        if a.kind != "free_text":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                (
                    "Det här uppdraget bedöms automatiskt — gör klart "
                    "i rätt verktyg så uppdateras status."
                ),
            )
        now = datetime.utcnow()
        a.manually_completed_at = now
        return V2UppdragSelfCompleteOut(
            ok=True,
            assignment_id=a.id,
            manually_completed_at=now,
        )


# Lärar-overview · samma data men för elev under granskning
class V2TeacherUppdragOverview(BaseModel):
    student_id: int
    student_name: str
    uppdrag: V2UppdragResponse


@router.get(
    "/teacher/students/{student_id}/uppdrag-overview",
    response_model=V2TeacherUppdragOverview,
)
def teacher_uppdrag_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherUppdragOverview:
    """Lärar-vy · alla elevens uppdrag med live-status (ej impersonation)."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Endast egen elev",
            )
        student_name = st.display_name

    response = _build_uppdrag_response(student_id)
    return V2TeacherUppdragOverview(
        student_id=student_id,
        student_name=student_name,
        uppdrag=response,
    )


# === KompetensV2 (Kompetens-detalj · Fas 2Q) ===
#
# Speglar prototypens p-komp: full historik på en specifik kompetens
# — resa hittills, timeline, krav för nästa nivå, anslutna moduler.


class V2KompetensTimelineEvent(BaseModel):
    occurred_at: datetime
    event_type: Literal[
        "step_completed", "level_reached", "module_completed",
        "assigned",
    ]
    title: str
    detail: Optional[str] = None
    badge: Optional[str] = None
    module_id: Optional[int] = None
    step_id: Optional[int] = None


class V2KompetensModuleStatus(BaseModel):
    module_id: int
    title: str
    completed: bool
    completed_steps: int
    total_steps: int
    completed_at: Optional[datetime]


class V2KompetensRequirement(BaseModel):
    label: str
    description: Optional[str] = None
    met: bool
    value_label: str


class V2KompetensDetail(BaseModel):
    competency_id: int
    key: str
    name: str
    description: Optional[str]
    is_system: bool
    mastery: float
    level: Literal["B", "G", "F"]
    level_label: str
    next_level: Optional[Literal["G", "F"]] = None
    next_level_label: Optional[str] = None
    progress_to_next: float  # 0.0 – 1.0
    completed_steps: int
    total_steps: int
    earned_weight: float
    total_weight: float
    last_event_at: Optional[datetime]
    timeline: list[V2KompetensTimelineEvent]
    connected_modules: list[V2KompetensModuleStatus]
    requirements_for_next: list[V2KompetensRequirement]


def _next_level_for(level: Literal["B", "G", "F"]) -> tuple[
    Optional[Literal["G", "F"]], Optional[str], Optional[float],
]:
    """Returnerar (next_short, next_label, mastery_threshold)."""
    if level == "B":
        return ("G", "GRUND", 0.33)
    if level == "G":
        return ("F", "FÖRDJUPNING", 0.66)
    return (None, None, None)


def _build_kompetens_detail(
    student_id: int, competency_id: int,
) -> V2KompetensDetail:
    from .modules import _compute_mastery_for_student

    with master_session() as s:
        comp = s.get(_SchoolCompetency, competency_id)
        if comp is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Kompetensen finns ej",
            )

        # Mastery för aktuell elev
        mastery_by_cid = _compute_mastery_for_student(s, student_id)
        mastery, count, last = mastery_by_cid.get(
            competency_id, (0.0, 0, None),
        )
        level_short, level_label = _mastery_to_level(mastery)
        next_short, next_label, next_threshold = _next_level_for(
            level_short,  # type: ignore[arg-type]
        )

        # Hitta progress till nästa nivå
        if next_threshold is None:
            progress_to_next = 1.0
        else:
            current_floor = 0.0 if level_short == "B" else 0.33
            span = next_threshold - current_floor
            progress_to_next = max(
                0.0, min(1.0, (mastery - current_floor) / span if span > 0 else 1.0),
            )

        # Steg som är kopplade till denna kompetens (med vikt)
        msc_rows = (
            s.query(_SchoolMSC, _SchoolModuleStep, _SchoolModule)
            .join(
                _SchoolModuleStep,
                _SchoolMSC.step_id == _SchoolModuleStep.id,
            )
            .join(
                _SchoolModule,
                _SchoolModuleStep.module_id == _SchoolModule.id,
            )
            .filter(_SchoolMSC.competency_id == competency_id)
            .all()
        )
        step_ids = [s_.id for _msc, s_, _m in msc_rows]
        total_steps = len(step_ids)
        total_weight = sum(msc.weight for msc, _s, _m in msc_rows)

        # Elevens progress på dessa steg
        progress_rows = []
        if step_ids:
            progress_rows = (
                s.query(_SchoolStepProgress)
                .filter(
                    _SchoolStepProgress.student_id == student_id,
                    _SchoolStepProgress.step_id.in_(step_ids),
                    _SchoolStepProgress.completed_at.is_not(None),
                )
                .all()
            )
        completed_step_ids = {p.step_id for p in progress_rows}
        completed_steps = len(completed_step_ids)
        # earned_weight ≈ mastery * total_weight
        earned_weight = mastery * total_weight if total_weight > 0 else 0.0

        # Bygg timeline · step_completed-events
        step_meta: dict[int, tuple[_SchoolModuleStep, _SchoolModule]] = {
            s_.id: (s_, m_) for _msc, s_, m_ in msc_rows
        }
        timeline: list[V2KompetensTimelineEvent] = []
        for prog in progress_rows:
            meta = step_meta.get(prog.step_id)
            if meta is None or prog.completed_at is None:
                continue
            step, module = meta
            timeline.append(V2KompetensTimelineEvent(
                occurred_at=prog.completed_at,
                event_type="step_completed",
                title=f"Klarade steget {step.title}",
                detail=f"Modul: {module.title} · {step.kind}",
                badge="+ steg",
                module_id=module.id,
                step_id=step.id,
            ))

        # module_completed-events
        connected_modules: list[V2KompetensModuleStatus] = []
        seen_module_ids: set[int] = set()
        for _msc, _step, mod in msc_rows:
            if mod.id in seen_module_ids:
                continue
            seen_module_ids.add(mod.id)
            mod_step_ids = [
                _s.id for _m_, _s, _mm in msc_rows
                if _mm.id == mod.id
            ]
            mod_completed = sum(
                1 for sid in mod_step_ids if sid in completed_step_ids
            )
            mod_total = len(mod_step_ids)
            sm = (
                s.query(_SchoolStudentModule)
                .filter(
                    _SchoolStudentModule.student_id == student_id,
                    _SchoolStudentModule.module_id == mod.id,
                )
                .first()
            )
            mod_completed_at = sm.completed_at if sm else None
            connected_modules.append(V2KompetensModuleStatus(
                module_id=mod.id,
                title=mod.title,
                completed=bool(sm and sm.completed_at),
                completed_steps=mod_completed,
                total_steps=mod_total,
                completed_at=mod_completed_at,
            ))
            if sm and sm.completed_at:
                timeline.append(V2KompetensTimelineEvent(
                    occurred_at=sm.completed_at,
                    event_type="module_completed",
                    title=f'Modul "{mod.title}" klar',
                    detail=f"{mod_total}/{mod_total} steg",
                    badge="+ modul",
                    module_id=mod.id,
                ))

        # Sortera moduler · klara först (senast klar överst), sen
        # progressiva, sen ej startade
        def _mod_sort_key(
            m: V2KompetensModuleStatus,
        ) -> tuple[int, float]:
            if m.completed:
                rank = 0
                ts = -(m.completed_at.timestamp() if m.completed_at else 0)
            elif m.completed_steps > 0:
                rank = 1
                ts = -float(m.completed_steps) / max(m.total_steps, 1)
            else:
                rank = 2
                ts = 0.0
            return (rank, ts)

        connected_modules.sort(key=_mod_sort_key)

        # Sortera timeline · senast först
        timeline.sort(key=lambda e: e.occurred_at, reverse=True)

        # Krav för nästa nivå
        requirements: list[V2KompetensRequirement] = []
        if next_threshold is not None:
            mastery_pct = round(mastery * 100)
            target_pct = round(next_threshold * 100)
            requirements.append(V2KompetensRequirement(
                label=f"Mastery ≥ {target_pct} %",
                description=(
                    f"Du ligger på {mastery_pct} % nu — "
                    f"{max(0, target_pct - mastery_pct)} %-enheter kvar."
                ),
                met=mastery >= next_threshold,
                value_label=f"{mastery_pct} %",
            ))
            target_modules = 2 if next_short == "G" else 3
            mods_done = sum(1 for m in connected_modules if m.completed)
            requirements.append(V2KompetensRequirement(
                label=f"Klara {target_modules} kopplade moduler",
                description=(
                    "Modul-completions är konkret bevis "
                    "på fördjupad förståelse."
                ),
                met=mods_done >= target_modules,
                value_label=f"{mods_done}/{target_modules}",
            ))
            target_count = 5 if next_short == "G" else 10
            requirements.append(V2KompetensRequirement(
                label=f"≥ {target_count} klarade steg",
                description=(
                    "Steg räknas så fort de markeras som klara, "
                    "även från olika moduler."
                ),
                met=completed_steps >= target_count,
                value_label=f"{completed_steps}/{target_count}",
            ))

        return V2KompetensDetail(
            competency_id=comp.id,
            key=comp.key,
            name=comp.name,
            description=comp.description,
            is_system=bool(comp.is_system),
            mastery=round(mastery, 4),
            level=level_short,  # type: ignore[arg-type]
            level_label=level_label,
            next_level=next_short,
            next_level_label=next_label,
            progress_to_next=round(progress_to_next, 4),
            completed_steps=completed_steps,
            total_steps=total_steps,
            earned_weight=round(earned_weight, 4),
            total_weight=round(total_weight, 4),
            last_event_at=last,
            timeline=timeline,
            connected_modules=connected_modules,
            requirements_for_next=requirements,
        )


@router.get(
    "/kompetens/{competency_id}", response_model=V2KompetensDetail,
)
def get_kompetens_detail(
    competency_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2KompetensDetail:
    """Detaljvy · resa B → G → F för en specifik kompetens."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Endast elever",
        )
    return _build_kompetens_detail(info.student_id, competency_id)


class V2TeacherKompetensOverview(BaseModel):
    student_id: int
    student_name: str
    detail: V2KompetensDetail


@router.get(
    "/teacher/students/{student_id}/kompetens/{competency_id}",
    response_model=V2TeacherKompetensOverview,
)
def teacher_kompetens_overview(
    student_id: int,
    competency_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherKompetensOverview:
    """Lärar-vy · samma kompetens-detalj men för specifik elev."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        st = mdb.get(Student, student_id)
        if not st or st.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Endast egen elev",
            )
        student_name = st.display_name

    detail = _build_kompetens_detail(student_id, competency_id)
    return V2TeacherKompetensOverview(
        student_id=student_id,
        student_name=student_name,
        detail=detail,
    )


# === KlassHubV2 (Lärar-hub · Fas 2R) ===
#
# Speglar prototypens larare.html#p-hub: aggregerad klass-pentagon,
# 5 stat-kort, side-stack med "behöver stöd nu" + pågående lönesamtal
# + reflektioner + nivå-progression + postlådor, + 28 mini-pentagoner.


class V2KlassStat(BaseModel):
    eye: str
    num_value: str
    sub: str
    accent: bool = False


class V2KlassPentagon(BaseModel):
    total_score: int
    economy: int
    safety: int
    health: int
    social: int
    leisure: int
    delta_total: int  # Skillnad sedan föregående månad (placeholder=0)


class V2KlassNeedsHelpItem(BaseModel):
    student_id: int
    student_name: str
    pent_total: int
    days_inactive: Optional[int]
    reason: str


class V2KlassNegotiationItem(BaseModel):
    negotiation_id: int
    student_id: int
    student_name: str
    round_no: int
    max_rounds: int
    profession: str
    starting_salary: float
    last_proposed_salary: Optional[float]
    status: str  # "active" | "completed"
    started_at: datetime


class V2KlassMailboxItem(BaseModel):
    student_id: int
    student_name: str
    unhandled_count: int
    oldest_days: Optional[int]
    has_authority: bool  # CSN/SKV brev oöppnat


class V2KlassReadyForLevel(BaseModel):
    student_id: int
    student_name: str
    weeks_at_level: int
    progress_pct: int
    current_level: int
    target_level: int


class V2KlassLevelDistribution(BaseModel):
    level_1_count: int
    level_2_count: int
    level_3_count: int
    ready_for_promotion: list[V2KlassReadyForLevel]


class V2KlassMiniPentagon(BaseModel):
    student_id: int
    student_name: str
    pent_total: int
    economy: int
    safety: int
    health: int
    social: int
    leisure: int
    level: int
    days_since_last_activity: Optional[int]


class V2KlassOverview(BaseModel):
    teacher_id: int
    teacher_name: str
    school_name: Optional[str] = None
    period_label: str  # "v18 · onsdag 29 april"
    total_students: int
    active_today: int
    reflections_unread_count: int
    klass_stats: list[V2KlassStat]
    klass_pentagon: V2KlassPentagon
    students_needing_help: list[V2KlassNeedsHelpItem]
    pending_negotiations: list[V2KlassNegotiationItem]
    mailbox_top: list[V2KlassMailboxItem]
    mailbox_total_unhandled: int
    level_distribution: V2KlassLevelDistribution
    mini_pentagons: list[V2KlassMiniPentagon]


def _safe_calc_wellbeing_for(
    student: Student,
) -> Optional[tuple[int, int, int, int, int, int]]:
    """Returnerar (total, economy, safety, health, social, leisure) eller
    None om wellbeing inte kan beräknas (fallar tyst — lärar-hub får
    inte krascha för en enskild elev)."""
    from ..school.engines import scope_context, scope_for_student

    scope_key = scope_for_student(student)
    try:
        with scope_context(scope_key):
            with session_scope() as s:
                ym = _current_year_month()
                wb = calculate_wellbeing(s, ym)
                return (
                    wb.total_score, wb.economy, wb.safety, wb.health,
                    wb.social, wb.leisure,
                )
    except Exception:
        return None


def _safe_count_unhandled_mail(student: Student) -> tuple[
    int, Optional[int], bool,
]:
    """Returnerar (unhandled_count, oldest_days, has_authority)."""
    from ..school.engines import scope_context, scope_for_student

    scope_key = scope_for_student(student)
    try:
        with scope_context(scope_key):
            with session_scope() as s:
                items = (
                    s.query(MailItem)
                    .filter(MailItem.status == "unhandled")
                    .order_by(MailItem.received_at.asc())
                    .all()
                )
                unhandled_count = len(items)
                oldest_days: Optional[int] = None
                has_authority = False
                if items:
                    oldest = items[0].received_at
                    if oldest is not None:
                        delta = datetime.utcnow() - oldest
                        oldest_days = max(0, delta.days)
                    has_authority = any(
                        m.mail_type == "authority" for m in items
                    )
                return unhandled_count, oldest_days, has_authority
    except Exception:
        return 0, None, False


def _days_since(dt: Optional[datetime]) -> Optional[int]:
    if dt is None:
        return None
    delta = datetime.utcnow() - dt
    return max(0, delta.days)


@router.get(
    "/teacher/klass-overview", response_model=V2KlassOverview,
)
def teacher_klass_overview(
    info: TokenInfo = Depends(require_token),
) -> V2KlassOverview:
    """Klass-dashboard · aggregerad data för lärar-hubben.

    Itererar lärarens elever, beräknar wellbeing per elev (i scope-context),
    aggregerar till klass-pentagon (snitt), identifierar elever som behöver
    stöd, listar pågående lönesamtal + olästa reflektioner + topp-postlådor.
    """
    teacher_id = _require_teacher(info)
    today = datetime.utcnow()

    with master_session() as mdb:
        teacher = mdb.get(Teacher, teacher_id)
        teacher_name = teacher.name if teacher else "Lärare"

        students = (
            mdb.query(Student)
            .filter(
                Student.teacher_id == teacher_id,
                Student.active.is_(True),
            )
            .order_by(Student.display_name)
            .all()
        )
        # Snapshot fält medan session är öppen
        students_data = [
            {
                "id": st.id,
                "name": st.display_name,
                "last_login_at": st.last_login_at,
                "v2_level": getattr(st, "v2_level", None) or 1,
                "obj": st,
            }
            for st in students
        ]

    total_students = len(students_data)
    active_today = sum(
        1 for d in students_data
        if d["last_login_at"] is not None
        and (today - d["last_login_at"]).days == 0
    )

    # Beräkna wellbeing per elev (i scope-context — kan ej ligga inom
    # master_session ovan eftersom scope-engine är separat)
    pents: list[tuple[int, int, int, int, int, int]] = []
    mini_pentagons: list[V2KlassMiniPentagon] = []
    needs_help: list[V2KlassNeedsHelpItem] = []
    mailbox_items: list[V2KlassMailboxItem] = []
    mailbox_total_unhandled = 0

    for d in students_data:
        st = d["obj"]
        wb = _safe_calc_wellbeing_for(st)
        if wb is None:
            wb = (50, 50, 50, 50, 50, 50)
        total, eco, safe, health, social, leisure = wb
        pents.append(wb)
        days_inactive = _days_since(d["last_login_at"])
        mini_pentagons.append(V2KlassMiniPentagon(
            student_id=d["id"],
            student_name=d["name"],
            pent_total=total,
            economy=eco,
            safety=safe,
            health=health,
            social=social,
            leisure=leisure,
            level=d["v2_level"],
            days_since_last_activity=days_inactive,
        ))
        # Behöver stöd: pent < 40 ELLER inaktiv > 7 dgr ELLER 3+ röda axlar
        red_axes = sum(
            1 for v in (eco, safe, health, social, leisure) if v < 40
        )
        reasons: list[str] = []
        if total < 40:
            reasons.append(f"pent {total}")
        if days_inactive is not None and days_inactive >= 7:
            reasons.append(f"inaktiv {days_inactive} dgr")
        if red_axes >= 3:
            reasons.append(f"{red_axes} röda axlar")
        if reasons:
            needs_help.append(V2KlassNeedsHelpItem(
                student_id=d["id"],
                student_name=d["name"],
                pent_total=total,
                days_inactive=days_inactive,
                reason=" · ".join(reasons),
            ))

        # Postlåda
        unhandled, oldest_days, has_auth = _safe_count_unhandled_mail(st)
        mailbox_total_unhandled += unhandled
        if unhandled > 0:
            mailbox_items.append(V2KlassMailboxItem(
                student_id=d["id"],
                student_name=d["name"],
                unhandled_count=unhandled,
                oldest_days=oldest_days,
                has_authority=has_auth,
            ))

    # Aggregera klass-pentagon (snitt över elever)
    if pents:
        n = len(pents)
        klass_pent = V2KlassPentagon(
            total_score=round(sum(p[0] for p in pents) / n),
            economy=round(sum(p[1] for p in pents) / n),
            safety=round(sum(p[2] for p in pents) / n),
            health=round(sum(p[3] for p in pents) / n),
            social=round(sum(p[4] for p in pents) / n),
            leisure=round(sum(p[5] for p in pents) / n),
            delta_total=0,
        )
    else:
        klass_pent = V2KlassPentagon(
            total_score=50, economy=50, safety=50,
            health=50, social=50, leisure=50, delta_total=0,
        )

    # Sortera: värsta pent först, sen mest inaktiv
    needs_help.sort(
        key=lambda h: (h.pent_total, -(h.days_inactive or 0)),
    )
    needs_help = needs_help[:6]

    # Postlådor topp 5 (mest ohanterade · äldsta först)
    mailbox_items.sort(
        key=lambda m: (-m.unhandled_count, -(m.oldest_days or 0)),
    )
    mailbox_top = mailbox_items[:5]

    # Pågående lönesamtal
    student_ids = [d["id"] for d in students_data]
    name_by_id = {d["id"]: d["name"] for d in students_data}
    pending_negotiations: list[V2KlassNegotiationItem] = []
    if student_ids:
        with master_session() as ms:
            negs = (
                ms.query(_SalaryNegotiation)
                .filter(
                    _SalaryNegotiation.student_id.in_(student_ids),
                    _SalaryNegotiation.status == "active",
                )
                .order_by(_SalaryNegotiation.started_at.desc())
                .all()
            )
            cfg = ms.query(_NegotiationConfig).first()
            max_rounds = cfg.max_rounds if cfg else 5
            for neg in negs:
                last_round = (
                    ms.query(_NegotiationRound)
                    .filter(_NegotiationRound.negotiation_id == neg.id)
                    .order_by(_NegotiationRound.round_no.desc())
                    .first()
                )
                # NegotiationRound har proposed_pct (delta), bygg
                # konkret SEK-bud genom starting_salary × (1 + pct/100).
                last_proposed: Optional[float] = None
                if (
                    last_round
                    and last_round.proposed_pct is not None
                    and neg.starting_salary is not None
                ):
                    last_proposed = float(
                        neg.starting_salary,
                    ) * (1.0 + (last_round.proposed_pct / 100.0))
                round_no = last_round.round_no if last_round else 0
                pending_negotiations.append(V2KlassNegotiationItem(
                    negotiation_id=neg.id,
                    student_id=neg.student_id,
                    student_name=name_by_id.get(
                        neg.student_id, "Okänd elev",
                    ),
                    round_no=round_no,
                    max_rounds=max_rounds,
                    profession=neg.profession,
                    starting_salary=float(neg.starting_salary),
                    last_proposed_salary=last_proposed,
                    status=neg.status,
                    started_at=neg.started_at,
                ))

    # Lönesamtals-stat baserat på antal pågående
    n_neg = len(pending_negotiations)

    # Pågående moduler · count
    pending_modules = 0
    if student_ids:
        with master_session() as ms:
            pending_modules = (
                ms.query(_SchoolStudentModule)
                .filter(
                    _SchoolStudentModule.student_id.in_(student_ids),
                    _SchoolStudentModule.completed_at.is_(None),
                    _SchoolStudentModule.started_at.is_not(None),
                )
                .count()
            )

    # Olästa reflektioner · approx via StudentStepProgress för reflect-kind
    # som har data men ingen teacher_feedback
    reflections_unread = 0
    if student_ids:
        from ..school.models import ModuleStep as _MS

        with master_session() as ms:
            reflections_unread = (
                ms.query(_SchoolStepProgress)
                .join(_MS, _SchoolStepProgress.step_id == _MS.id)
                .filter(
                    _SchoolStepProgress.student_id.in_(student_ids),
                    _MS.kind == "reflect",
                    _SchoolStepProgress.completed_at.is_not(None),
                    _SchoolStepProgress.teacher_feedback.is_(None),
                )
                .count()
            )

    # Klass-stats: 5 nyckeltal från prototypen
    save_rate_avg = 0  # placeholder — kräver inkomst+sparande per elev
    klass_stats = [
        V2KlassStat(
            eye="Klass-balans",
            num_value=f"{klass_pent.total_score}/100",
            sub=(
                f"{active_today} av {total_students} aktiva idag"
                if total_students > 0 else "ingen elev än"
            ),
        ),
        V2KlassStat(
            eye="Behöver stöd",
            num_value=str(len(needs_help)),
            sub=(
                "elever med pent < 40 / inaktiv / 3+ röda"
                if needs_help else "alla mår OK"
            ),
            accent=len(needs_help) > 0,
        ),
        V2KlassStat(
            eye="Pågående moduler",
            num_value=str(pending_modules),
            sub="elev × modul-instanser",
        ),
        V2KlassStat(
            eye="Lönesamtal i Maria",
            num_value=str(n_neg),
            sub="pågående AI-förhandlingar",
            accent=n_neg > 0,
        ),
        V2KlassStat(
            eye="Olästa reflektioner",
            num_value=str(reflections_unread),
            sub="väntar på din kommentar",
            accent=reflections_unread > 0,
        ),
    ]

    # Level-distribution
    l1 = sum(1 for d in students_data if d["v2_level"] == 1)
    l2 = sum(1 for d in students_data if d["v2_level"] == 2)
    l3 = sum(1 for d in students_data if d["v2_level"] == 3)
    # Ready-for-promotion: enkel heuristik · Nivå 1 + pent >= 65 + inte
    # inaktiv. Faktisk progression-modell kan komma senare.
    ready_for_promotion: list[V2KlassReadyForLevel] = []
    for d, mp in zip(students_data, mini_pentagons):
        if d["v2_level"] >= 3:
            continue
        if mp.pent_total < 65:
            continue
        if mp.days_since_last_activity is not None and mp.days_since_last_activity > 14:
            continue
        # Veckor på nivån = veckor sedan senaste login (proxy)
        weeks = max(1, ((mp.days_since_last_activity or 0) // 7) + 8)
        progress = min(95, 40 + mp.pent_total // 2)
        ready_for_promotion.append(V2KlassReadyForLevel(
            student_id=d["id"],
            student_name=d["name"],
            weeks_at_level=weeks,
            progress_pct=progress,
            current_level=d["v2_level"],
            target_level=d["v2_level"] + 1,
        ))
    ready_for_promotion.sort(
        key=lambda r: -r.progress_pct,
    )
    ready_for_promotion = ready_for_promotion[:5]

    level_dist = V2KlassLevelDistribution(
        level_1_count=l1,
        level_2_count=l2,
        level_3_count=l3,
        ready_for_promotion=ready_for_promotion,
    )

    # Period-label · "v18 · onsdag 29 april"
    week = today.isocalendar().week
    weekdays = [
        "måndag", "tisdag", "onsdag", "torsdag",
        "fredag", "lördag", "söndag",
    ]
    months = [
        "januari", "februari", "mars", "april", "maj", "juni",
        "juli", "augusti", "september", "oktober", "november", "december",
    ]
    period_label = (
        f"v{week} · {weekdays[today.weekday()]} "
        f"{today.day} {months[today.month - 1]}"
    )

    # Sortera mini-pentagonerna · värsta pent först (matchar prototypens
    # "klicka för att zooma" där läraren ser problembarn först)
    mini_pentagons.sort(key=lambda m: m.pent_total)

    return V2KlassOverview(
        teacher_id=teacher_id,
        teacher_name=teacher_name,
        period_label=period_label,
        total_students=total_students,
        active_today=active_today,
        reflections_unread_count=reflections_unread,
        klass_stats=klass_stats,
        klass_pentagon=klass_pent,
        students_needing_help=needs_help,
        pending_negotiations=pending_negotiations,
        mailbox_top=mailbox_top,
        mailbox_total_unhandled=mailbox_total_unhandled,
        level_distribution=level_dist,
        mini_pentagons=mini_pentagons,
    )


# === TeacherStudentDetailV2 (p-elev · Fas 2S) ===
#
# Speglar prototypens larare.html#p-elev: full elev-detalj-vy med
# pentagon, pågående moduler, senaste händelser, kompetens-grid,
# nivå-progression-card. Allt i ett anrop så lärar-detaljvyn kan
# laddas snabbt (ingen vattenfalls-sekvens).


class V2StudentDetailPentagon(BaseModel):
    total_score: int
    economy: int
    safety: int
    health: int
    social: int
    leisure: int
    delta_total: int
    tipped_towards: str  # max-axel namn


class V2StudentDetailModule(BaseModel):
    student_module_id: int
    module_id: int
    title: str
    summary: Optional[str]
    completed_steps: int
    total_steps: int
    progress_pct: int
    started_at: Optional[datetime]
    last_activity_at: Optional[datetime]
    next_step_title: Optional[str] = None


class V2StudentDetailEvent(BaseModel):
    occurred_at: datetime
    kind: str  # ex "tx.classified", "module.step_completed", "bankid.signed"
    summary: str
    badge: Optional[str] = None
    detail: Optional[str] = None


class V2StudentDetailCompetency(BaseModel):
    competency_id: int
    key: str
    name: str
    level: Literal["B", "G", "F"]
    level_label: str
    mastery: float


class V2StudentDetailLevelProgression(BaseModel):
    current_level: int
    target_level: Optional[int]
    weeks_at_level: int
    progress_pct: int
    requirements_met: int
    requirements_total: int
    ready_for_promotion: bool
    blockers: list[str]


class V2StudentDetailAssignmentSummary(BaseModel):
    active_count: int
    overdue_count: int
    completed_this_month: int


class V2TeacherStudentDetail(BaseModel):
    student_id: int
    student_name: str
    login_code_suffix: str  # bara sista 4 tecken (för identifiering, ej hela)
    last_login_at: Optional[datetime]
    days_since_last_login: Optional[int]
    onboarding_completed: bool
    v2_level: int
    v2_level_label: str
    spend_profile: Optional[str]
    fairness_choice: Optional[str]
    partner_model: Optional[str]
    pentagon: V2StudentDetailPentagon
    pentagon_explanation: str
    active_modules: list[V2StudentDetailModule]
    completed_modules_count: int
    recent_events: list[V2StudentDetailEvent]
    competencies: list[V2StudentDetailCompetency]
    level_progression: V2StudentDetailLevelProgression
    pending_negotiation: Optional[V2KlassNegotiationItem]
    assignments: V2StudentDetailAssignmentSummary
    mailbox_unhandled_count: int
    mailbox_oldest_days: Optional[int]


def _level_label(level: int) -> str:
    return {1: "Sparsam", 2: "Balanserad", 3: "Slösa"}.get(
        level, f"Nivå {level}",
    )


def _build_recent_events_for(
    student: Student, limit: int = 25,
) -> list[V2StudentDetailEvent]:
    """Aggregera senaste 30 dgr aktivitet · StudentActivity (master) +
    BankID-sessioner + signerade fakturor + assignment-events.

    Returnerar nyast först, max `limit` rader.
    """
    from ..school.engines import scope_context, scope_for_student
    from ..school.models import StudentActivity as _SA

    events: list[V2StudentDetailEvent] = []
    cutoff = datetime.utcnow() - timedelta(days=30)

    # Master-DB events (StudentActivity, Assignment-feedback,
    # BankID-sessioner)
    with master_session() as ms:
        acts = (
            ms.query(_SA)
            .filter(
                _SA.student_id == student.id,
                _SA.occurred_at >= cutoff,
            )
            .order_by(_SA.occurred_at.desc())
            .limit(limit * 2)
            .all()
        )
        for a in acts:
            events.append(V2StudentDetailEvent(
                occurred_at=a.occurred_at,
                kind=a.kind,
                summary=a.summary,
                badge=_summarize_kind_badge(a.kind),
            ))

        # Module step-progress (klarade steg senaste 30 dgr)
        progress_rows = (
            ms.query(_SchoolStepProgress, _SchoolModuleStep, _SchoolModule)
            .join(
                _SchoolModuleStep,
                _SchoolStepProgress.step_id == _SchoolModuleStep.id,
            )
            .join(
                _SchoolModule,
                _SchoolModuleStep.module_id == _SchoolModule.id,
            )
            .filter(
                _SchoolStepProgress.student_id == student.id,
                _SchoolStepProgress.completed_at.is_not(None),
                _SchoolStepProgress.completed_at >= cutoff,
            )
            .order_by(_SchoolStepProgress.completed_at.desc())
            .limit(limit)
            .all()
        )
        for prog, step, mod in progress_rows:
            if prog.completed_at is None:
                continue
            events.append(V2StudentDetailEvent(
                occurred_at=prog.completed_at,
                kind="module.step_completed",
                summary=f'Klarade steget "{step.title}"',
                detail=f"Modul: {mod.title} · {step.kind}",
                badge="+ steg",
            ))

    # Scope-DB events (BankID + Mail-viewed)
    scope_key = scope_for_student(student)
    try:
        with scope_context(scope_key):
            with session_scope() as s:
                bankid_rows = (
                    s.query(BankIDSession)
                    .filter(BankIDSession.created_at >= cutoff)
                    .order_by(BankIDSession.created_at.desc())
                    .limit(10)
                    .all()
                )
                for b in bankid_rows:
                    if b.signed_at is not None:
                        events.append(V2StudentDetailEvent(
                            occurred_at=b.signed_at,
                            kind="bankid.signed",
                            summary=(
                                f"Signerade {len(b.upcoming_ids or [])} "
                                f"fakturor via BankID"
                            ),
                            badge="+ signering",
                        ))
                    elif b.cancelled_at is not None:
                        events.append(V2StudentDetailEvent(
                            occurred_at=b.cancelled_at,
                            kind="bankid.cancelled",
                            summary="Avbröt BankID-signering",
                            badge="× avbruten",
                        ))
    except Exception:
        pass  # fail-soft

    events.sort(key=lambda e: e.occurred_at, reverse=True)
    return events[:limit]


def _summarize_kind_badge(kind: str) -> Optional[str]:
    if kind.startswith("transaction."):
        return "+ tx"
    if kind.startswith("budget."):
        return "+ budget"
    if kind.startswith("loan."):
        return "+ lån"
    if kind.startswith("transfer."):
        return "+ överföring"
    if kind.startswith("batch."):
        return "+ import"
    if kind.startswith("module."):
        return "+ modul"
    if kind.startswith("bankid."):
        return "+ signering"
    if kind.startswith("assignment."):
        return "+ uppdrag"
    return None


def _build_active_modules(
    student_id: int,
) -> tuple[list[V2StudentDetailModule], int]:
    """Returnerar (active_modules, completed_count)."""
    active: list[V2StudentDetailModule] = []
    completed = 0
    with master_session() as ms:
        sms = (
            ms.query(_SchoolStudentModule)
            .filter(_SchoolStudentModule.student_id == student_id)
            .all()
        )
        for sm in sms:
            if sm.completed_at is not None:
                completed += 1
                continue
            mod = ms.get(_SchoolModule, sm.module_id)
            if mod is None:
                continue
            steps = (
                ms.query(_SchoolModuleStep)
                .filter(_SchoolModuleStep.module_id == mod.id)
                .order_by(_SchoolModuleStep.sort_order)
                .all()
            )
            step_ids = [st.id for st in steps]
            total_steps = len(step_ids)
            progs = (
                ms.query(_SchoolStepProgress)
                .filter(
                    _SchoolStepProgress.student_id == student_id,
                    _SchoolStepProgress.step_id.in_(step_ids),
                    _SchoolStepProgress.completed_at.is_not(None),
                )
                .all()
            )
            done_ids = {p.step_id for p in progs}
            completed_steps = len(done_ids)
            last_activity = None
            for p in progs:
                if (
                    last_activity is None
                    or (
                        p.completed_at is not None
                        and p.completed_at > last_activity
                    )
                ):
                    last_activity = p.completed_at

            # Nästa-steg-titel
            next_step_title: Optional[str] = None
            for st in steps:
                if st.id not in done_ids:
                    next_step_title = st.title
                    break

            progress_pct = (
                round(completed_steps / total_steps * 100)
                if total_steps > 0 else 0
            )
            active.append(V2StudentDetailModule(
                student_module_id=sm.id,
                module_id=mod.id,
                title=mod.title,
                summary=mod.summary,
                completed_steps=completed_steps,
                total_steps=total_steps,
                progress_pct=progress_pct,
                started_at=sm.started_at,
                last_activity_at=last_activity,
                next_step_title=next_step_title,
            ))
    return active, completed


def _build_competencies_for_student(
    student_id: int,
) -> list[V2StudentDetailCompetency]:
    from .modules import _compute_mastery_for_student

    out: list[V2StudentDetailCompetency] = []
    with master_session() as s:
        mastery_by_cid = _compute_mastery_for_student(s, student_id)
        comps = (
            s.query(_SchoolCompetency)
            .order_by(_SchoolCompetency.name)
            .all()
        )
        for c in comps:
            mastery, _count, _last = mastery_by_cid.get(
                c.id, (0.0, 0, None),
            )
            level_short, level_label = _mastery_to_level(mastery)
            out.append(V2StudentDetailCompetency(
                competency_id=c.id,
                key=c.key,
                name=c.name,
                level=level_short,  # type: ignore[arg-type]
                level_label=level_label,
                mastery=round(mastery, 4),
            ))
    # Sortera: F först, sen G, sen B, sen på namn
    level_order = {"F": 0, "G": 1, "B": 2}
    out.sort(key=lambda c: (level_order[c.level], c.name))
    return out


@router.get(
    "/teacher/students/{student_id}/student-detail",
    response_model=V2TeacherStudentDetail,
)
def teacher_student_detail(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherStudentDetail:
    """Lärar-detaljvy · alla aspekter av en specifik elev.

    Speglar prototypens larare.html#p-elev: pentagon med delta,
    pågående moduler, senaste händelser, kompetens-grid,
    nivå-progression, pågående lönesamtal, uppdrag-summary, postlåda.
    """
    teacher_id = _require_teacher(info)

    with master_session() as mdb:
        student = mdb.get(Student, student_id)
        if not student or student.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Endast egen elev",
            )
        student_name = student.display_name
        login_code = student.login_code or ""
        last_login = student.last_login_at
        v2_level = getattr(student, "v2_level", None) or 1
        onboarding_done = getattr(student, "onboarding_completed", False)
        spend_profile = getattr(student, "v2_spend_profile", None)
        fairness = getattr(student, "v2_fairness_choice", None)
        partner = getattr(student, "v2_partner_model", None)
        v2_onboarded_at = getattr(
            student, "v2_onboarding_completed_at", None,
        )

    days_since_login = _days_since(last_login)

    # Pentagon
    wb = _safe_calc_wellbeing_for(student)
    if wb is None:
        wb = (50, 50, 50, 50, 50, 50)
    total, eco, safe, health, social, leisure = wb
    axes = [
        ("ekonomi", eco), ("karriär", safe), ("hälsa", health),
        ("relation", social), ("fritid", leisure),
    ]
    tipped = max(axes, key=lambda x: x[1])[0]
    pentagon = V2StudentDetailPentagon(
        total_score=total,
        economy=eco, safety=safe, health=health,
        social=social, leisure=leisure,
        delta_total=0,
        tipped_towards=tipped,
    )

    # Förklaring · samma logik som elev-vyns wellbeing-explanation
    pentagon_explanation = (
        f"Pent {total}/100 · ekonomi {eco} · karriär {safe} · "
        f"hälsa {health} · relation {social} · fritid {leisure}. "
        f"Tippad mot {tipped}."
    )

    active_modules, completed_count = _build_active_modules(student_id)
    competencies = _build_competencies_for_student(student_id)

    with master_session() as m:
        student_obj = m.get(Student, student_id)
        if student_obj is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Elev hittades inte",
            )
        recent_events = _build_recent_events_for(student_obj, limit=25)

    # Pågående lönesamtal
    pending_negotiation: Optional[V2KlassNegotiationItem] = None
    with master_session() as ms:
        neg = (
            ms.query(_SalaryNegotiation)
            .filter(
                _SalaryNegotiation.student_id == student_id,
                _SalaryNegotiation.status == "active",
            )
            .order_by(_SalaryNegotiation.started_at.desc())
            .first()
        )
        if neg is not None:
            cfg = ms.query(_NegotiationConfig).first()
            max_rounds = cfg.max_rounds if cfg else 5
            last_round = (
                ms.query(_NegotiationRound)
                .filter(_NegotiationRound.negotiation_id == neg.id)
                .order_by(_NegotiationRound.round_no.desc())
                .first()
            )
            last_proposed: Optional[float] = None
            if (
                last_round and last_round.proposed_pct is not None
                and neg.starting_salary is not None
            ):
                last_proposed = float(neg.starting_salary) * (
                    1.0 + (last_round.proposed_pct / 100.0)
                )
            pending_negotiation = V2KlassNegotiationItem(
                negotiation_id=neg.id,
                student_id=neg.student_id,
                student_name=student_name,
                round_no=last_round.round_no if last_round else 0,
                max_rounds=max_rounds,
                profession=neg.profession,
                starting_salary=float(neg.starting_salary),
                last_proposed_salary=last_proposed,
                status=neg.status,
                started_at=neg.started_at,
            )

    # Uppdrag-summary · samma motor som /v2/uppdrag
    upp_resp = _build_uppdrag_response(student_id)
    assignments_summary = V2StudentDetailAssignmentSummary(
        active_count=upp_resp.summary.active_count,
        overdue_count=upp_resp.summary.overdue_count,
        completed_this_month=upp_resp.summary.completed_this_month,
    )

    # Postlåda
    with master_session() as m:
        student_obj2 = m.get(Student, student_id)
    unhandled, oldest_days, _has_auth = _safe_count_unhandled_mail(
        student_obj2,
    )

    # Nivå-progression
    weeks_at_level = max(
        1, ((days_since_login or 0) // 7) + 8,
    ) if v2_onboarded_at is None else max(
        1, ((datetime.utcnow() - v2_onboarded_at).days // 7),
    )
    fordjup_count = sum(1 for c in competencies if c.level == "F")
    grund_count = sum(1 for c in competencies if c.level == "G")
    completed_steps_total = sum(
        m.completed_steps for m in active_modules
    )
    blockers: list[str] = []
    requirements_met = 0
    requirements_total = 4
    if total >= 65:
        requirements_met += 1
    else:
        blockers.append(f"Pent under 65 (är {total})")
    if grund_count + fordjup_count >= 1:
        requirements_met += 1
    else:
        blockers.append("Saknar minst 1 kompetens på G eller F")
    if completed_count >= 1:
        requirements_met += 1
    else:
        blockers.append("Saknar minst 1 avslutad modul")
    if days_since_login is None or days_since_login <= 14:
        requirements_met += 1
    else:
        blockers.append(f"Inaktiv {days_since_login} d (krav ≤ 14)")
    progress_pct = round(requirements_met / requirements_total * 100)
    ready = requirements_met == requirements_total and v2_level < 3
    level_progression = V2StudentDetailLevelProgression(
        current_level=v2_level,
        target_level=v2_level + 1 if v2_level < 3 else None,
        weeks_at_level=weeks_at_level,
        progress_pct=progress_pct,
        requirements_met=requirements_met,
        requirements_total=requirements_total,
        ready_for_promotion=ready,
        blockers=blockers,
    )

    # Login-code suffix · säkrare än hela koden i payload
    login_suffix = login_code[-4:] if len(login_code) >= 4 else login_code

    return V2TeacherStudentDetail(
        student_id=student_id,
        student_name=student_name,
        login_code_suffix=login_suffix,
        last_login_at=last_login,
        days_since_last_login=days_since_login,
        onboarding_completed=bool(onboarding_done),
        v2_level=v2_level,
        v2_level_label=_level_label(v2_level),
        spend_profile=spend_profile,
        fairness_choice=fairness,
        partner_model=partner,
        pentagon=pentagon,
        pentagon_explanation=pentagon_explanation,
        active_modules=active_modules,
        completed_modules_count=completed_count,
        recent_events=recent_events,
        competencies=competencies,
        level_progression=level_progression,
        pending_negotiation=pending_negotiation,
        assignments=assignments_summary,
        mailbox_unhandled_count=unhandled,
        mailbox_oldest_days=oldest_days,
    )


# === TeacherReflectionsV2 (p-refl · Fas 2T) ===
#
# Speglar prototypens larare.html#p-refl: lista över klassens
# reflektioner från reflect-steg, med oläst/kommenterad-filtrering
# och flagga för "elev mår inte bra"-mönster (heuristik på text).


# Heuristik · ord/fraser som indikerar att eleven kämpar / behöver stöd.
# Ger lärar-vyn röd flagga ("MÅR INTE BRA") så ingen reflektion flyger
# under radarn. Lågt false-positive-tröskel föredras — bättre att läraren
# tittar en gång för mycket än missar någon som faktiskt behöver hjälp.
_HELP_FLAG_PHRASES = (
    "vet inte hur",
    "förstår inte",
    "förstår ej",
    "behöver hjälp",
    "kan inte",
    "klarar inte",
    "ger upp",
    "ångest",
    "stress",
    "panik",
    "orolig",
    "hjälp innan",
    "boka",
)


def _flagged_for_help(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(phrase in lower for phrase in _HELP_FLAG_PHRASES)


def _word_count(text: str) -> int:
    if not text:
        return 0
    return len([t for t in text.split() if t.strip()])


class V2ReflectionItem(BaseModel):
    progress_id: int
    student_id: int
    student_name: str
    module_id: int
    module_title: str
    step_id: int
    step_title: str
    step_question: Optional[str]
    body: str
    word_count: int
    completed_at: Optional[datetime]
    teacher_feedback: Optional[str]
    feedback_at: Optional[datetime]
    flagged_for_help: bool
    rubric_label: Optional[str] = None  # AI-rubrik (tar modul-titeln)


class V2ReflectionsSummary(BaseModel):
    total_count: int
    unread_count: int
    flagged_count: int
    avg_word_count: int
    last_received_at: Optional[datetime]


class V2ReflectionsResponse(BaseModel):
    summary: V2ReflectionsSummary
    items: list[V2ReflectionItem]


@router.get(
    "/teacher/reflections", response_model=V2ReflectionsResponse,
)
def teacher_reflections_v2(
    filter: Literal["all", "unread", "flagged"] = "all",
    info: TokenInfo = Depends(require_token),
) -> V2ReflectionsResponse:
    """Alla reflektioner från lärarens elever · sorterat nyast först.

    filter:
      - all       (default) alla reflektioner senaste 90 dgr
      - unread    bara de utan teacher_feedback
      - flagged   bara de där eleven verkar behöva hjälp (heuristik
                  på text — "vet inte hur", "förstår inte" etc)
    """
    teacher_id = _require_teacher(info)
    cutoff = datetime.utcnow() - timedelta(days=90)

    items: list[V2ReflectionItem] = []
    with master_session() as s:
        rows = (
            s.query(_SchoolStepProgress, _SchoolModuleStep, Student)
            .join(
                _SchoolModuleStep,
                _SchoolStepProgress.step_id == _SchoolModuleStep.id,
            )
            .join(Student, _SchoolStepProgress.student_id == Student.id)
            .filter(
                Student.teacher_id == teacher_id,
                _SchoolModuleStep.kind == "reflect",
                _SchoolStepProgress.completed_at.is_not(None),
                _SchoolStepProgress.completed_at >= cutoff,
            )
            .order_by(_SchoolStepProgress.completed_at.desc())
            .all()
        )
        for prog, step, stu in rows:
            text = ""
            if prog.data and isinstance(prog.data, dict):
                text = str(prog.data.get("reflection", "")).strip()
            if not text:
                continue  # tomt reflect-svar — hoppa
            flagged = _flagged_for_help(text)
            wc = _word_count(text)
            module = (
                s.query(_SchoolModule)
                .filter(_SchoolModule.id == step.module_id)
                .first()
            )
            module_title = module.title if module else "—"
            items.append(V2ReflectionItem(
                progress_id=prog.id,
                student_id=stu.id,
                student_name=stu.display_name,
                module_id=step.module_id,
                module_title=module_title,
                step_id=step.id,
                step_title=step.title,
                step_question=step.content,
                body=text,
                word_count=wc,
                completed_at=prog.completed_at,
                teacher_feedback=prog.teacher_feedback,
                feedback_at=prog.feedback_at,
                flagged_for_help=flagged,
                rubric_label=module_title.upper(),
            ))

    # Filter
    filtered = items
    if filter == "unread":
        filtered = [i for i in items if i.teacher_feedback is None]
    elif filter == "flagged":
        filtered = [i for i in items if i.flagged_for_help]

    # Summary räknas över alla items (oavsett filter)
    avg_wc = (
        round(sum(i.word_count for i in items) / len(items))
        if items else 0
    )
    summary = V2ReflectionsSummary(
        total_count=len(items),
        unread_count=sum(1 for i in items if i.teacher_feedback is None),
        flagged_count=sum(1 for i in items if i.flagged_for_help),
        avg_word_count=avg_wc,
        last_received_at=items[0].completed_at if items else None,
    )
    return V2ReflectionsResponse(summary=summary, items=filtered)


# === TeacherMailboxV2 (p-mail · Fas 2U) ===
#
# Speglar prototypens larare.html#p-mail: tabell över alla elevers
# postlådor med status-kolumn (KLAR/I FAS/SLÄPER/RISK), klass-summary
# 5-stat (genererade, hanterade, försenade, påminnelser, profiler) +
# bulk-inject-endpoint för att skicka samma brev till flera elever.


class V2MailboxRow(BaseModel):
    student_id: int
    student_name: str
    spend_profile: Optional[str]
    total_count_period: int  # alla brev senaste 30 dgr (oavsett status)
    unhandled_count: int
    oldest_days: Optional[int]
    reminders_count: int
    has_authority_unhandled: bool
    status: Literal["klar", "i_fas", "släper", "risk"]


class V2MailboxClassSummary(BaseModel):
    total_students: int
    total_generated_period: int  # alla brev hos alla elever (30 dgr)
    handled_in_time: int  # status != unhandled
    handled_pct: int
    overdue_count: int  # unhandled MED due_date i förfluten
    reminders_total: int
    profile_distribution: dict[str, int]  # {"sparsam": 12, "balanserad": 11, "slosa": 5}


class V2MailboxResponse(BaseModel):
    summary: V2MailboxClassSummary
    rows: list[V2MailboxRow]


def _mailbox_status_for(
    unhandled: int, oldest_days: Optional[int], reminders: int,
) -> Literal["klar", "i_fas", "släper", "risk"]:
    if unhandled == 0:
        return "klar"
    if reminders > 0 or (oldest_days is not None and oldest_days >= 14):
        return "risk"
    if unhandled >= 4 or (oldest_days is not None and oldest_days >= 8):
        return "släper"
    return "i_fas"


def _mailbox_stats_for_student(
    student: Student,
) -> tuple[int, int, Optional[int], int, bool, int]:
    """Returnerar (total_period, unhandled, oldest_days, reminders,
    has_authority, overdue_count) — mailbox-stats för en elev.

    Fail-soft: returnerar nollor om scope-DB är otillgänglig.
    """
    from ..school.engines import scope_context, scope_for_student
    cutoff = datetime.utcnow() - timedelta(days=30)
    today = datetime.utcnow().date()
    try:
        scope_key = scope_for_student(student)
        with scope_context(scope_key):
            with session_scope() as s:
                all_period = (
                    s.query(MailItem)
                    .filter(MailItem.received_at >= cutoff)
                    .all()
                )
                unhandled = [
                    m for m in all_period if m.status == "unhandled"
                ]
                oldest_days: Optional[int] = None
                if unhandled:
                    sorted_unhandled = sorted(
                        unhandled, key=lambda m: m.received_at,
                    )
                    oldest = sorted_unhandled[0].received_at
                    if oldest is not None:
                        delta = datetime.utcnow() - oldest
                        oldest_days = max(0, delta.days)
                reminders = sum(
                    1 for m in unhandled if m.mail_type == "reminder"
                )
                has_authority = any(
                    m.mail_type == "authority" for m in unhandled
                )
                overdue = sum(
                    1 for m in unhandled
                    if m.due_date is not None and m.due_date < today
                )
                return (
                    len(all_period),
                    len(unhandled),
                    oldest_days,
                    reminders,
                    has_authority,
                    overdue,
                )
    except Exception:
        return (0, 0, None, 0, False, 0)


@router.get(
    "/teacher/mailboxes", response_model=V2MailboxResponse,
)
def teacher_mailboxes(
    info: TokenInfo = Depends(require_token),
) -> V2MailboxResponse:
    """Lärar-vy · alla 28 postlådor i klassen med status + summary."""
    teacher_id = _require_teacher(info)

    with master_session() as mdb:
        students = (
            mdb.query(Student)
            .filter(
                Student.teacher_id == teacher_id,
                Student.active.is_(True),
            )
            .order_by(Student.display_name)
            .all()
        )
        snapshots: list[dict] = []
        for st in students:
            spend_profile: Optional[str] = (
                getattr(st, "v2_spend_profile", None)
            )
            if spend_profile is None:
                # Fallback från StudentProfile
                prof = (
                    mdb.query(StudentProfile)
                    .filter(StudentProfile.student_id == st.id)
                    .first()
                )
                spend_profile = (
                    getattr(prof, "spend_profile", None) if prof else None
                )
            snapshots.append({
                "id": st.id,
                "name": st.display_name,
                "obj": st,
                "spend_profile": spend_profile,
            })

    total_generated = 0
    handled_in_time = 0
    overdue_total = 0
    reminders_total = 0
    rows: list[V2MailboxRow] = []
    profile_dist: dict[str, int] = {}
    for snap in snapshots:
        st = snap["obj"]
        total, unhandled, oldest_days, reminders, has_auth, overdue = (
            _mailbox_stats_for_student(st)
        )
        total_generated += total
        handled_in_time += max(0, total - unhandled)
        overdue_total += overdue
        reminders_total += reminders
        if snap["spend_profile"]:
            profile_dist[snap["spend_profile"]] = (
                profile_dist.get(snap["spend_profile"], 0) + 1
            )
        rows.append(V2MailboxRow(
            student_id=snap["id"],
            student_name=snap["name"],
            spend_profile=snap["spend_profile"],
            total_count_period=total,
            unhandled_count=unhandled,
            oldest_days=oldest_days,
            reminders_count=reminders,
            has_authority_unhandled=has_auth,
            status=_mailbox_status_for(unhandled, oldest_days, reminders),
        ))

    # Sortera: risk först, sen släpning, sen i fas, sen klar
    status_order = {"risk": 0, "släper": 1, "i_fas": 2, "klar": 3}
    rows.sort(
        key=lambda r: (
            status_order[r.status],
            -r.unhandled_count,
            -(r.oldest_days or 0),
        ),
    )

    handled_pct = (
        round(handled_in_time / total_generated * 100)
        if total_generated > 0 else 100
    )

    summary = V2MailboxClassSummary(
        total_students=len(snapshots),
        total_generated_period=total_generated,
        handled_in_time=handled_in_time,
        handled_pct=handled_pct,
        overdue_count=overdue_total,
        reminders_total=reminders_total,
        profile_distribution=profile_dist,
    )
    return V2MailboxResponse(summary=summary, rows=rows)


class V2MailboxBulkInjectIn(BaseModel):
    sender: str = Field(min_length=1, max_length=120)
    sender_kind: MailSenderKind = "other"
    sender_short: Optional[str] = None
    mail_type: MailType
    subject: str = Field(min_length=1, max_length=200)
    body: Optional[str] = None
    amount: Optional[float] = Field(default=None, ge=0)
    due_date: Optional[_date] = None
    target_student_ids: Optional[list[int]] = None  # None = alla aktiva


class V2MailboxBulkInjectResult(BaseModel):
    students_targeted: int
    mails_created: int


@router.post(
    "/teacher/mailboxes/bulk-inject",
    response_model=V2MailboxBulkInjectResult,
)
def bulk_inject_mail(
    body: V2MailboxBulkInjectIn,
    info: TokenInfo = Depends(require_token),
) -> V2MailboxBulkInjectResult:
    """Lärare skickar samma brev till flera elever på en gång.

    target_student_ids: None → alla aktiva elever till denna lärare.
    Annars endast eleverna i listan (måste tillhöra läraren).
    """
    from ..school.engines import scope_context, scope_for_student

    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        q = mdb.query(Student).filter(
            Student.teacher_id == teacher_id,
            Student.active.is_(True),
        )
        if body.target_student_ids is not None:
            q = q.filter(Student.id.in_(body.target_student_ids))
        students = q.all()
        student_snapshots = [
            (st.id, scope_for_student(st)) for st in students
        ]

    created = 0
    for sid, scope_key in student_snapshots:
        try:
            with scope_context(scope_key):
                with session_scope() as s:
                    amount = (
                        Decimal(str(body.amount))
                        if body.amount is not None else None
                    )
                    s.add(MailItem(
                        sender=body.sender,
                        sender_short=body.sender_short,
                        sender_kind=body.sender_kind,
                        mail_type=body.mail_type,
                        subject=body.subject,
                        body=body.body,
                        amount=amount,
                        due_date=body.due_date,
                        status="unhandled",
                    ))
                    created += 1
        except Exception:
            # Fail-soft per elev så en trasig scope-DB inte stoppar
            # bulk-injicering till resten av klassen.
            continue
    return V2MailboxBulkInjectResult(
        students_targeted=len(student_snapshots),
        mails_created=created,
    )


# === TeacherMariaListV2 (p-maria · Fas 2V) ===
#
# Speglar prototypens larare.html#p-maria: alla pågående och nyligen
# avslutade lönesamtal i klassen, med konversations-snutt för senaste
# rond + bud-historik + smärtgräns-flagga.


class V2MariaRoundCompact(BaseModel):
    round_no: int
    student_message: str
    employer_response: str
    proposed_pct: Optional[float]
    proposed_salary: Optional[float]
    created_at: datetime


class V2MariaListItem(BaseModel):
    negotiation_id: int
    student_id: int
    student_name: str
    profession: str
    employer: str
    starting_salary: float
    status: str  # "active" | "completed" | "abandoned"
    started_at: datetime
    completed_at: Optional[datetime]
    final_salary: Optional[float]
    final_pct: Optional[float]
    current_round_no: int
    max_rounds: int
    rounds: list[V2MariaRoundCompact]  # senaste 2 ronder för list-vy
    near_pain_threshold: bool  # heuristik: senaste proposed_pct >= 6.0
    avtal_norm_pct: Optional[float]


class V2MariaListSummary(BaseModel):
    total_count: int
    active_count: int
    completed_count: int
    abandoned_count: int
    avg_round_no: float  # bland aktiva
    near_pain_count: int


class V2MariaListResponse(BaseModel):
    summary: V2MariaListSummary
    active: list[V2MariaListItem]
    completed: list[V2MariaListItem]


def _build_maria_list_item(
    neg: _SalaryNegotiation,
    student_name: str,
    max_rounds: int,
    rounds: list[_NegotiationRound],
) -> V2MariaListItem:
    rounds_sorted = sorted(rounds, key=lambda r: r.round_no)
    compact: list[V2MariaRoundCompact] = []
    for r in rounds_sorted[-2:]:  # senaste 2 ronder
        proposed_salary: Optional[float] = None
        if r.proposed_pct is not None and neg.starting_salary is not None:
            proposed_salary = float(neg.starting_salary) * (
                1.0 + (r.proposed_pct / 100.0)
            )
        compact.append(V2MariaRoundCompact(
            round_no=r.round_no,
            student_message=r.student_message,
            employer_response=r.employer_response,
            proposed_pct=r.proposed_pct,
            proposed_salary=proposed_salary,
            created_at=r.created_at,
        ))
    current_round_no = rounds_sorted[-1].round_no if rounds_sorted else 0
    near_pain = (
        rounds_sorted[-1].proposed_pct is not None
        and rounds_sorted[-1].proposed_pct >= 6.0
    ) if rounds_sorted else False
    return V2MariaListItem(
        negotiation_id=neg.id,
        student_id=neg.student_id,
        student_name=student_name,
        profession=neg.profession,
        employer=neg.employer,
        starting_salary=float(neg.starting_salary)
        if neg.starting_salary is not None else 0.0,
        status=neg.status,
        started_at=neg.started_at,
        completed_at=neg.completed_at,
        final_salary=float(neg.final_salary)
        if neg.final_salary is not None else None,
        final_pct=neg.final_pct,
        current_round_no=current_round_no,
        max_rounds=max_rounds,
        rounds=compact,
        near_pain_threshold=near_pain,
        avtal_norm_pct=neg.avtal_norm_pct,
    )


@router.get(
    "/teacher/maria-list", response_model=V2MariaListResponse,
)
def teacher_maria_list(
    info: TokenInfo = Depends(require_token),
) -> V2MariaListResponse:
    """Lärar-vy · alla lönesamtal (aktiva + senaste klara) för klassen."""
    teacher_id = _require_teacher(info)

    with master_session() as mdb:
        students = (
            mdb.query(Student)
            .filter(
                Student.teacher_id == teacher_id,
                Student.active.is_(True),
            )
            .all()
        )
        name_by_id = {s.id: s.display_name for s in students}
        student_ids = list(name_by_id.keys())

    active: list[V2MariaListItem] = []
    completed: list[V2MariaListItem] = []
    abandoned_count = 0
    near_pain = 0

    if not student_ids:
        return V2MariaListResponse(
            summary=V2MariaListSummary(
                total_count=0, active_count=0,
                completed_count=0, abandoned_count=0,
                avg_round_no=0.0, near_pain_count=0,
            ),
            active=[], completed=[],
        )

    with master_session() as ms:
        cfg = ms.query(_NegotiationConfig).first()
        max_rounds = cfg.max_rounds if cfg else 5
        # Aktiva
        active_negs = (
            ms.query(_SalaryNegotiation)
            .filter(
                _SalaryNegotiation.student_id.in_(student_ids),
                _SalaryNegotiation.status == "active",
            )
            .order_by(_SalaryNegotiation.started_at.desc())
            .all()
        )
        # Klara · senaste 30 dgr
        cutoff = datetime.utcnow() - timedelta(days=30)
        completed_negs = (
            ms.query(_SalaryNegotiation)
            .filter(
                _SalaryNegotiation.student_id.in_(student_ids),
                _SalaryNegotiation.status.in_(("completed", "abandoned")),
                _SalaryNegotiation.completed_at.is_not(None),
                _SalaryNegotiation.completed_at >= cutoff,
            )
            .order_by(_SalaryNegotiation.completed_at.desc())
            .all()
        )

        for neg in active_negs:
            rounds = (
                ms.query(_NegotiationRound)
                .filter(_NegotiationRound.negotiation_id == neg.id)
                .all()
            )
            item = _build_maria_list_item(
                neg,
                name_by_id.get(neg.student_id, "Okänd elev"),
                max_rounds,
                rounds,
            )
            active.append(item)
            if item.near_pain_threshold:
                near_pain += 1

        for neg in completed_negs:
            rounds = (
                ms.query(_NegotiationRound)
                .filter(_NegotiationRound.negotiation_id == neg.id)
                .all()
            )
            item = _build_maria_list_item(
                neg,
                name_by_id.get(neg.student_id, "Okänd elev"),
                max_rounds,
                rounds,
            )
            completed.append(item)
            if neg.status == "abandoned":
                abandoned_count += 1

    avg_round = (
        sum(it.current_round_no for it in active) / len(active)
        if active else 0.0
    )
    summary = V2MariaListSummary(
        total_count=len(active) + len(completed),
        active_count=len(active),
        completed_count=sum(1 for it in completed if it.status == "completed"),
        abandoned_count=abandoned_count,
        avg_round_no=round(avg_round, 1),
        near_pain_count=near_pain,
    )
    return V2MariaListResponse(
        summary=summary, active=active, completed=completed,
    )


# === TeacherPedagogicsV2 (p-peda · Fas 2W) ===
#
# Speglar prototypens larare.html#p-peda: pedagogik-paket per aktör/
# verktyg/modul med exposure-räkning, kompetens-distribution över
# klassen och åtgärds-förslag (heuristik).


# Hård-kodad mappning av "concept-boxar" (aktör/verktyg/modul-mall) →
# begrepp. Speglar prototypens 8 sektioner. Strukturen kan i framtiden
# flyttas till en redigerbar tabell, men hård-kod räcker för v1.
_PEDA_CONCEPT_BOXES: list[dict] = [
    {
        "key": "banken",
        "kind": "actor",
        "title": "Aktör · Banken",
        "concepts": [
            "likviditet", "sparkvot", "buffert",
            "räntenetto", "disponibel inkomst",
        ],
        "exposure_via": "onboarded",
    },
    {
        "key": "arbetsgivaren",
        "kind": "actor",
        "title": "Aktör · Arbetsgivaren",
        "concepts": [
            "brutto", "netto", "ITP1",
            "kollektivavtal", "IBB", "marginalskatt",
        ],
        "exposure_via": "onboarded",
    },
    {
        "key": "maria",
        "kind": "actor",
        "title": "Aktör · Maria (lönesamtal)",
        "concepts": [
            "centralavtal", "marknadssnitt", "BATNA",
            "förhandlingsutrymme", "kompensation",
        ],
        "exposure_via": "negotiation",
    },
    {
        "key": "postladan",
        "kind": "actor",
        "title": "Aktör · Postlådan",
        "concepts": [
            "förfallodatum", "dröjsmålsränta", "bestrida",
            "betalningsanmärkning", "inkasso", "Kronofogden",
        ],
        "exposure_via": "mail_received",
    },
    {
        "key": "avanza",
        "kind": "actor",
        "title": "Aktör · Avanza",
        "concepts": [
            "ISK", "KF", "indexfond",
            "schablonskatt", "spridning", "TER",
        ],
        "exposure_via": "onboarded",
    },
    {
        "key": "skatteverket",
        "kind": "actor",
        "title": "Aktör · Skatteverket",
        "concepts": [
            "inkomstdeklaration", "förifyllt", "avdrag",
            "kvarskatt", "återbäring", "kontrolluppgift",
        ],
        "exposure_via": "module_skatt",
    },
    {
        "key": "modul_bolan",
        "kind": "module",
        "title": "Modul · Bolån",
        "concepts": [
            "KALP", "belåningsgrad", "skuldkvot",
            "amorteringskrav", "räntebindning", "bunden vs rörlig",
        ],
        "exposure_via": "module_bolan",
    },
    {
        "key": "bankid",
        "kind": "tool",
        "title": "Verktyg · BankID",
        "concepts": [
            "elektronisk signatur", "autogiro",
            "bankgiro", "förfallodatum", "OCR-nummer",
        ],
        "exposure_via": "bankid_session",
    },
]


class V2PedaConceptBox(BaseModel):
    key: str
    kind: Literal["actor", "tool", "module"]
    title: str
    concepts: list[str]
    student_count: int
    is_underexposed: bool
    is_critical: bool
    note: Optional[str] = None


class V2PedaCompetencyDist(BaseModel):
    competency_id: int
    key: str
    name: str
    basis_count: int
    grund_count: int
    fordjup_count: int
    is_concerning: bool  # majoritet på basis


class V2PedaSuggestion(BaseModel):
    title: str
    body: str
    cta_label: str
    cta_target: Optional[str] = None  # route där åtgärd kan tas


class V2PedagogicsSummary(BaseModel):
    total_concepts: int
    total_boxes: int
    most_seen_count: int  # boxes med ≥ 20 elever
    rarely_seen_count: int  # boxes med ≤ 5 elever
    underexposed_boxes: int


class V2PedagogicsResponse(BaseModel):
    summary: V2PedagogicsSummary
    concept_boxes: list[V2PedaConceptBox]
    competency_distribution: list[V2PedaCompetencyDist]
    suggestions: list[V2PedaSuggestion]


def _peda_exposure_count(
    box: dict,
    student_ids: list[int],
    onboarded_ids: set[int],
    negotiation_student_ids: set[int],
    mail_received_ids: set[int],
    bankid_student_ids: set[int],
    module_started_by_title: dict[str, set[int]],
) -> int:
    """Räkna antal elever som har stött på begreppen i en concept-box."""
    via = box["exposure_via"]
    if via == "onboarded":
        return len(onboarded_ids)
    if via == "negotiation":
        return len(negotiation_student_ids)
    if via == "mail_received":
        return len(mail_received_ids)
    if via == "bankid_session":
        return len(bankid_student_ids)
    if via == "module_bolan":
        # Hitta moduler vars titel innehåller "bolån" eller "kalp"
        seen: set[int] = set()
        for title, ids in module_started_by_title.items():
            t = title.lower()
            if "bolån" in t or "kalp" in t or "bostads" in t:
                seen.update(ids)
        return len(seen)
    if via == "module_skatt":
        seen: set[int] = set()
        for title, ids in module_started_by_title.items():
            t = title.lower()
            if "skatt" in t or "deklaration" in t:
                seen.update(ids)
        return len(seen)
    return 0


@router.get(
    "/teacher/pedagogics", response_model=V2PedagogicsResponse,
)
def teacher_pedagogics(
    info: TokenInfo = Depends(require_token),
) -> V2PedagogicsResponse:
    """Lärar-vy · pedagogik-paket med exposure och åtgärds-förslag."""
    teacher_id = _require_teacher(info)

    with master_session() as mdb:
        students = (
            mdb.query(Student)
            .filter(
                Student.teacher_id == teacher_id,
                Student.active.is_(True),
            )
            .all()
        )
        student_ids = [s.id for s in students]
        onboarded_ids = {
            s.id for s in students
            if getattr(s, "v2_onboarding_completed_at", None) is not None
            or getattr(s, "onboarding_completed", False)
        }

    if not student_ids:
        return V2PedagogicsResponse(
            summary=V2PedagogicsSummary(
                total_concepts=sum(
                    len(b["concepts"]) for b in _PEDA_CONCEPT_BOXES
                ),
                total_boxes=len(_PEDA_CONCEPT_BOXES),
                most_seen_count=0, rarely_seen_count=0,
                underexposed_boxes=0,
            ),
            concept_boxes=[
                V2PedaConceptBox(
                    key=b["key"], kind=b["kind"],
                    title=b["title"], concepts=b["concepts"],
                    student_count=0,
                    is_underexposed=True, is_critical=True,
                )
                for b in _PEDA_CONCEPT_BOXES
            ],
            competency_distribution=[],
            suggestions=[],
        )

    # Exposure-räkningar
    with master_session() as ms:
        # Pågående/avslutade förhandlingar
        neg_student_ids = {
            row[0] for row in ms.query(_SalaryNegotiation.student_id)
            .filter(_SalaryNegotiation.student_id.in_(student_ids))
            .all()
        }
        # Modul-progression per modul-titel
        module_started_by_title: dict[str, set[int]] = {}
        sm_rows = (
            ms.query(_SchoolStudentModule, _SchoolModule)
            .join(
                _SchoolModule,
                _SchoolStudentModule.module_id == _SchoolModule.id,
            )
            .filter(
                _SchoolStudentModule.student_id.in_(student_ids),
                _SchoolStudentModule.started_at.is_not(None),
            )
            .all()
        )
        for sm, mod in sm_rows:
            module_started_by_title.setdefault(
                mod.title, set(),
            ).add(sm.student_id)

    # Per-elev scope-data: mail_received + bankid_session
    mail_received_ids: set[int] = set()
    bankid_student_ids: set[int] = set()
    from ..school.engines import scope_context, scope_for_student
    with master_session() as mdb:
        for st in students:
            try:
                scope_key = scope_for_student(st)
                with scope_context(scope_key):
                    with session_scope() as s:
                        if s.query(MailItem).first() is not None:
                            mail_received_ids.add(st.id)
                        if s.query(BankIDSession).first() is not None:
                            bankid_student_ids.add(st.id)
            except Exception:
                continue

    # Bygg concept-boxar
    boxes: list[V2PedaConceptBox] = []
    most_seen = 0
    rarely_seen = 0
    underexposed = 0
    total_students = len(student_ids)
    for b in _PEDA_CONCEPT_BOXES:
        cnt = _peda_exposure_count(
            b, student_ids, onboarded_ids,
            neg_student_ids, mail_received_ids,
            bankid_student_ids, module_started_by_title,
        )
        is_under = cnt < 5
        # Kritiskt = under 5 elever har stött på OCH klassen är ≥ 10
        is_critical = is_under and total_students >= 10
        note: Optional[str] = None
        if is_under:
            note = "⚠ FÅ HAR STÖTT — överväg helklass-introduktion"
        if cnt >= 20:
            most_seen += 1
        if cnt <= 5:
            rarely_seen += 1
        if is_under:
            underexposed += 1
        boxes.append(V2PedaConceptBox(
            key=b["key"], kind=b["kind"],
            title=b["title"], concepts=b["concepts"],
            student_count=cnt,
            is_underexposed=is_under,
            is_critical=is_critical,
            note=note,
        ))

    # Kompetens-distribution
    from .modules import _compute_mastery_for_student
    competency_dist: list[V2PedaCompetencyDist] = []
    with master_session() as ms:
        comps = (
            ms.query(_SchoolCompetency)
            .filter(
                or_(
                    _SchoolCompetency.is_system.is_(True),
                    _SchoolCompetency.teacher_id == teacher_id,
                )
            )
            .order_by(_SchoolCompetency.name)
            .all()
        )
        for c in comps:
            b_cnt = g_cnt = f_cnt = 0
            for sid in student_ids:
                mastery_by_cid = _compute_mastery_for_student(ms, sid)
                mastery, _count, _last = mastery_by_cid.get(
                    c.id, (0.0, 0, None),
                )
                level_short, _label = _mastery_to_level(mastery)
                if level_short == "F":
                    f_cnt += 1
                elif level_short == "G":
                    g_cnt += 1
                else:
                    b_cnt += 1
            is_concerning = b_cnt > (g_cnt + f_cnt)
            competency_dist.append(V2PedaCompetencyDist(
                competency_id=c.id,
                key=c.key,
                name=c.name,
                basis_count=b_cnt,
                grund_count=g_cnt,
                fordjup_count=f_cnt,
                is_concerning=is_concerning,
            ))

    # Genererade åtgärds-förslag baserat på data
    suggestions: list[V2PedaSuggestion] = []
    # Under-exposed boxes → föreslå modul
    for box in boxes:
        if box.is_critical:
            suggestions.append(V2PedaSuggestion(
                title=f"Modul: {box.title}",
                body=(
                    f"Endast {box.student_count} elev"
                    f"{'er' if box.student_count != 1 else ''} har "
                    f"stött på pedagogik-boxen. "
                    f"Begrepp som behöver introduceras: "
                    f"{', '.join(box.concepts[:3])}…"
                ),
                cta_label="Skapa modul",
                cta_target="/teacher/v2",
            ))
    # Kompetens där > halva klassen ligger på basis
    for cd in competency_dist:
        if cd.is_concerning and cd.basis_count >= 5:
            total = cd.basis_count + cd.grund_count + cd.fordjup_count
            suggestions.append(V2PedaSuggestion(
                title=f"Kompetens-gap: {cd.name}",
                body=(
                    f"{cd.basis_count} av {total} elever ligger på BASIS "
                    f"i {cd.name}. Endast {cd.fordjup_count} har nått "
                    f"fördjupning. Riktad modul kan lyfta klassen."
                ),
                cta_label="Se modul-bibliotek",
                cta_target="/teacher/v2",
            ))

    summary = V2PedagogicsSummary(
        total_concepts=sum(len(b["concepts"]) for b in _PEDA_CONCEPT_BOXES),
        total_boxes=len(_PEDA_CONCEPT_BOXES),
        most_seen_count=most_seen,
        rarely_seen_count=rarely_seen,
        underexposed_boxes=underexposed,
    )
    return V2PedagogicsResponse(
        summary=summary,
        concept_boxes=boxes,
        competency_distribution=competency_dist,
        suggestions=suggestions[:6],  # max 6 förslag
    )


class V2ReflectionFeedbackIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


@router.post(
    "/teacher/reflections/{progress_id}/feedback",
    response_model=V2ReflectionItem,
)
def teacher_reflection_feedback_v2(
    progress_id: int,
    payload: V2ReflectionFeedbackIn,
    info: TokenInfo = Depends(require_token),
) -> V2ReflectionItem:
    """Lärare ger feedback på en reflektion · uppdaterar
    StudentStepProgress.teacher_feedback. Returnerar uppdaterad row."""
    teacher_id = _require_teacher(info)
    with master_session() as s:
        prog = (
            s.query(_SchoolStepProgress)
            .filter(_SchoolStepProgress.id == progress_id)
            .first()
        )
        if not prog:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Reflektionen hittades inte",
            )
        student = (
            s.query(Student)
            .filter(Student.id == prog.student_id)
            .first()
        )
        if not student or student.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Endast egen elev",
            )
        prog.teacher_feedback = payload.body.strip()
        prog.feedback_at = datetime.utcnow()
        s.flush()

        step = (
            s.query(_SchoolModuleStep)
            .filter(_SchoolModuleStep.id == prog.step_id)
            .first()
        )
        if step is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Steget saknas",
            )
        module = (
            s.query(_SchoolModule)
            .filter(_SchoolModule.id == step.module_id)
            .first()
        )
        text = ""
        if prog.data and isinstance(prog.data, dict):
            text = str(prog.data.get("reflection", "")).strip()
        return V2ReflectionItem(
            progress_id=prog.id,
            student_id=student.id,
            student_name=student.display_name,
            module_id=step.module_id,
            module_title=module.title if module else "—",
            step_id=step.id,
            step_title=step.title,
            step_question=step.content,
            body=text,
            word_count=_word_count(text),
            completed_at=prog.completed_at,
            teacher_feedback=prog.teacher_feedback,
            feedback_at=prog.feedback_at,
            flagged_for_help=_flagged_for_help(text),
            rubric_label=(module.title.upper() if module else None),
        )
