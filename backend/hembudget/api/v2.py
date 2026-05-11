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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from datetime import date as _date
from decimal import Decimal

from ..db.base import session_scope
from ..db.models import (
    Account, Transaction, FundHolding, UpcomingTransaction, Goal,
    MailItem, Loan, LoanPayment, LoanProduct, LoanScheduleEntry,
    CreditApplication,
    PaymentMark, CreditCheck, KALPCalculation,
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


# === Realtid-projektion · spel-tid → real-tid ===
#
# Seed-flödet sätter `released_at` på MailItem + Transaction så
# events sprids över 5 real-dagar (= en spelmånad). Frontend ser
# bara objekt vars `released_at <= NOW() OR released_at IS NULL`.
# Helpern nedan används i alla list-endpoints så samma princip
# håller överallt.


def _released_filter(model_class):
    """Filter-uttryck: är synlig nu?

    `released_at IS NULL` betyder ingen projektion (ex. legacy-data,
    manuella imports) → alltid synlig. Annars `released_at <= NOW()`.
    """
    return or_(
        model_class.released_at.is_(None),
        model_class.released_at <= datetime.utcnow(),
    )


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
    # Seed-livscykel · "pending" tills BackgroundTask har seedat lön,
    # postlådan, försäkringar etc. Frontend visar en pedagogisk overlay
    # tills "complete" så eleven aldrig ser tomma vyer pga race mot
    # async seed. "failed" → lärar-detaljvyn auto-reseedar.
    seed_status: Literal["pending", "complete", "failed"] = "complete"


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
    # None när inkomst = 0 (division-by-zero-fall). Frontend visar "—"
    # för att inte påstå "0 % sparkvot" när vi faktiskt inte vet.
    save_rate_pct: Optional[float] = None
    transactions_count: int
    # Saldo i början av månaden = totalt saldo nu MINUS denna månads
    # netto-flöde (income - expenses). Pedagogiskt viktigt: eleven
    # ser kontinuiteten "förra månadsslut → flöde i mån → saldo nu".
    # Annars verkar det som magi att saldo är 15k när "denna mån = -748".
    start_of_month_balance: float = 0.0


class HubEventItem(BaseModel):
    """Pending social event eller klasskompis-bjudning på Hub-feed."""
    id: int
    kind: Literal["event", "invite"]
    title: str
    category: str
    cost: float
    deadline: _date
    source: str  # "system" | "classmate_invite" | "teacher_triggered"
    from_name: Optional[str] = None  # bara för invites
    days_until_deadline: int
    declinable: bool


class HubGameTime(BaseModel):
    """Spel-tid · 1 real-timme = 1 spel-vecka. Synkat med biz-tick."""
    iso_date: str  # "2026-05-07"
    weekday_label: str  # "Torsdag"
    full_label: str  # "Torsdag 7 maj 2026"
    short_label: str  # "7 maj"
    year_month: str  # "2026-05"
    real_anchor_at: str  # student.created_at ISO
    # Real-tid sekunder · för UI-countdown och progress-bar
    seconds_per_game_day: int = 514  # SECONDS_PER_GAME_DAY
    seconds_into_current_day: int = 0  # 0..seconds_per_game_day-1
    seconds_until_next_day: int = 514  # countdown till nästa spel-dag


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
    pending_events: list[HubEventItem] = Field(default_factory=list)
    game_time: Optional[HubGameTime] = None


def _current_year_month() -> str:
    """Returnerar elevens nuvarande SPEL-månad (synkat med privat-tid).

    Tidigare returnerade detta real-tid (date.today()) → pentagon-axel,
    bokföring och postlåda visade "2026-05" trots att eleven är på
    "2026-02" i spel-tiden. Vi använder business.game_clock.current_game_date
    som löser nuvarande elev från ContextVar och faller tillbaka till
    real-tid om scope saknas (test/kickstart).
    """
    try:
        from ..business.game_clock import current_game_date
        d = current_game_date()
    except Exception:
        d = _date.today()
    return f"{d.year:04d}-{d.month:02d}"


@router.get("/game-time", response_model=HubGameTime)
def get_game_time(info: TokenInfo = Depends(require_token)) -> HubGameTime:
    """Lättviktigt endpoint som returnerar elevens nuvarande spel-tid.
    Används av sidor som vill defaulta till spel-månad (Bokföring,
    Postlådan, etc.) utan att behöva hämta hela /v2/hub."""
    target_sid: Optional[int] = None
    if info.role == "student" and info.student_id is not None:
        target_sid = info.student_id
    elif info.role == "teacher" and info.teacher_id is not None:
        from ..school.engines import get_current_actor_student
        target_sid = get_current_actor_student()
    if target_sid is None:
        # Fallback: anchor-datum
        from ..game_engine.release_schedule import GAME_ANCHOR_DATE
        return HubGameTime(
            iso_date=GAME_ANCHOR_DATE.isoformat(),
            weekday_label="Torsdag",
            full_label="Torsdag 1 januari 2026",
            short_label="1 januari",
            year_month=GAME_ANCHOR_DATE.strftime("%Y-%m"),
            real_anchor_at=datetime.utcnow().isoformat() + "Z",
        )
    from ..game_engine.release_schedule import game_date_for
    with master_session() as ms:
        stu = ms.get(Student, target_sid)
        if stu is None or stu.created_at is None:
            from ..game_engine.release_schedule import GAME_ANCHOR_DATE
            return HubGameTime(
                iso_date=GAME_ANCHOR_DATE.isoformat(),
                weekday_label="Torsdag",
                full_label="Torsdag 1 januari 2026",
                short_label="1 januari",
                year_month=GAME_ANCHOR_DATE.strftime("%Y-%m"),
                real_anchor_at=datetime.utcnow().isoformat() + "Z",
            )
        gy, gm, gd = game_date_for(stu.created_at)
        gd = max(1, min(28, gd))
        game_d = _date(gy, gm, gd)
        weekdays = ["Måndag", "Tisdag", "Onsdag", "Torsdag",
                    "Fredag", "Lördag", "Söndag"]
        months = [
            "januari", "februari", "mars", "april", "maj",
            "juni", "juli", "augusti", "september", "oktober",
            "november", "december",
        ]
        wd = weekdays[game_d.weekday()]
        mn = months[gm - 1]
        # Sekunder in i nuvarande spel-dag · för UI-countdown
        from ..game_engine.release_schedule import SECONDS_PER_GAME_DAY
        elapsed_real = max(
            0.0, (datetime.utcnow() - stu.created_at).total_seconds(),
        )
        sec_into_day = int(elapsed_real % SECONDS_PER_GAME_DAY)
        sec_until_next = SECONDS_PER_GAME_DAY - sec_into_day
        return HubGameTime(
            iso_date=game_d.isoformat(),
            weekday_label=wd,
            full_label=f"{wd} {gd} {mn} {gy}",
            short_label=f"{gd} {mn}",
            year_month=f"{gy:04d}-{gm:02d}",
            real_anchor_at=stu.created_at.isoformat() + "Z",
            seconds_per_game_day=SECONDS_PER_GAME_DAY,
            seconds_into_current_day=sec_into_day,
            seconds_until_next_day=sec_until_next,
        )


@router.get("/hub", response_model=HubResponse)
def get_hub(info: TokenInfo = Depends(require_token)) -> HubResponse:
    """Aggregerar all data hubben behöver i ett anrop.

    Hämtar från:
    - master-DB: Student, StudentProfile (karaktär, v2-fält)
    - scope-DB: transactions, accounts (månads-summa, saldon)
    - wellbeing-modulen (5 axlar)

    Demo får tom payload. Lärare med x-as-student-impersonation ser
    elevens vy (för förhandsvisning från v2-elev-detaljen).

    Cache · 20s TTL per student. Sparar 5-10 master_session-anrop +
    pentagon-beräkning per request. Mutationer (markera-paid,
    export-to-bank, transfer m.fl.) bustar cache via
    invalidate_hub_cache(sid) så stale-staleness max ~20s.
    """
    # === Cache-check innan vi gör nåt jobb ============================
    target_sid_for_cache: Optional[int] = None
    if info.role == "student" and info.student_id is not None:
        target_sid_for_cache = info.student_id
    elif info.role == "teacher" and info.teacher_id is not None:
        from ..school.engines import get_current_actor_student
        target_sid_for_cache = get_current_actor_student()

    if target_sid_for_cache is not None:
        try:
            from ..cache import get_cache as _gc_hub
            cache_key = f"hub:s_{target_sid_for_cache}:v1"
            cached = _gc_hub().get(cache_key)
            if cached is not None:
                return HubResponse.model_validate_json(cached)
        except Exception:
            # Cache-fel är aldrig fatalt · fortsätt med live-bygge
            import logging
            logging.getLogger(__name__).debug(
                "hub-cache: read failed · fortsätter live", exc_info=True,
            )

    response = _build_hub_response(info)

    # === Cache-skriv om vi har en student-id =========================
    if target_sid_for_cache is not None and response.student_id != 0:
        try:
            from ..cache import get_cache as _gc_hub_w
            cache_key_w = f"hub:s_{target_sid_for_cache}:v1"
            _gc_hub_w().set(
                cache_key_w,
                response.model_dump_json().encode("utf-8"),
                ttl=20,
            )
        except Exception:
            pass
    return response


def invalidate_hub_cache(student_id: Optional[int]) -> None:
    """Bust hub-cachen för en elev. Anropas från endpoints som
    muterar elev-data (mark paid, transfer, accept event etc.) så
    eleven omedelbart ser uppdaterat tillstånd istället för att
    vänta TTL ut."""
    if student_id is None:
        return
    try:
        from ..cache import get_cache as _gc_inv
        _gc_inv().delete(f"hub:s_{student_id}:v1")
    except Exception:
        pass


def _build_hub_response(info: TokenInfo) -> HubResponse:
    """Live-bygge av hub-svaret · ingen caching här. Brukade vara
    body:n i get_hub() innan vi extraherade en cache-wrapper."""
    # Resolva target-student-id · stöd både egen-elev och lärar-impersonation
    target_sid: Optional[int] = None
    if info.role == "student" and info.student_id is not None:
        target_sid = info.student_id
    elif info.role == "teacher" and info.teacher_id is not None:
        from ..school.engines import get_current_actor_student
        target_sid = get_current_actor_student()

    # Garantera att eleven har data när hubben laddas (auto-recovery
    # för stuck students som missat seed). Idempotent: gör inget om data
    # redan finns. Bara för v2-aktiverade elever — v1-elever ska inte
    # få sin manuellt-satta StudentProfile överskriven av game_engine.
    #
    # OBS: vi läser ut värdena ur master_session-contexten och stänger
    # den INNAN vi kallar _ensure_student_has_initial_data — annars
    # nestar vi master_session-contexter, vilket ger SQLite-deadlock
    # i tester.
    if target_sid is not None and info.role == "student":
        try:
            recovery_args: Optional[dict] = None
            with master_session() as _ms:
                _stu = _ms.get(Student, target_sid)
                if _stu is not None and _stu.v2_enabled:
                    recovery_args = dict(
                        student_id=target_sid,
                        student_name=_stu.display_name,
                        spend_profile=(
                            _stu.v2_spend_profile or "balanserad"
                        ),
                        starting_level=_stu.v2_level or 1,
                        partner_model=_stu.v2_partner_model or "solo",
                    )
            if recovery_args is not None:
                _ensure_student_has_initial_data(**recovery_args)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "get_hub: auto-recovery seed failed för %s",
                target_sid,
            )

        # Auto-tick · eskalera obetalda fakturor + tick fram nya
        # spel-månader + släpp Skatteverket-deklaration-events när
        # spel-tiden passerar SKV:s årliga datum. Cachat per elev,
        # idempotent. Tysta fel — får aldrig påverka hub-vyn.
        try:
            _auto_tick_private_months_if_due(target_sid)
        except Exception:
            pass
        try:
            # Drag pengar från signerade autogiro-fakturor när
            # förfallodag passerat (i spel-tid). Annars syns de
            # som '1 d sen' i bank trots att eleven signerat.
            _auto_debit_signed_upcomings_if_due(target_sid)
        except Exception:
            pass
        try:
            _seed_skv_deklaration_events(target_sid)
        except Exception:
            pass
        try:
            _run_dunning_for_student(target_sid)
        except Exception:
            pass

    if target_sid is None:
        return HubResponse(
            student_id=0,
            character=HubCharacter(display_name="—"),
            v2_level=1,
            v2_spend_profile="sparsam",
            v2_partner_model="solo",
            month_summary=HubMonthSummary(
                income=0, expenses=0, saved=0,
                save_rate_pct=None, transactions_count=0,
            ),
            total_balance=0,
            accounts_count=0,
        )

    # 1. Karaktär från master-DB
    with master_session() as mdb:
        student = mdb.get(Student, target_sid)
        if not student:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Student hittades inte",
            )
        profile = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == target_sid)
            .one_or_none()
        )
        # Heal stale net_salary · om en gammal profil har orealistisk
        # nettolön (< 55 % av brutto, det är teoretiskt omöjligt med
        # svensk skatt) räknar vi om från gross via compute_net_salary
        # och uppdaterar permanent. Vanligast scenariot: tidiga
        # game_engine-profiler där monthly_net råkat sparas som ett
        # delningsbelopp eller decimal-procentsats.
        if (
            profile is not None
            and profile.gross_salary_monthly
            and (
                not profile.net_salary_monthly
                or float(profile.net_salary_monthly)
                < 0.55 * float(profile.gross_salary_monthly)
            )
        ):
            try:
                from ..school.tax import compute_net_salary as _heal_net
                heal = _heal_net(int(profile.gross_salary_monthly))
                profile.net_salary_monthly = heal.net_monthly
                profile.tax_rate_effective = heal.effective_rate
                mdb.commit()
            except Exception:
                pass

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
        income=0, expenses=0, saved=0,
        save_rate_pct=None, transactions_count=0,
    )
    total_balance = 0.0
    accounts_count = 0
    pending_events: list[HubEventItem] = []

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

            # 3. Månads-summa från transactions
            # Använd senaste NON-TRANSFER tx-datum som anchor — annars
            # hamnar man på fel månad om bara pension-spar-transfern
            # körts (då blir summary 0/0 även om föregående månad har
            # full data).
            today = _date.today()
            latest_tx = (
                s.query(Transaction)
                .filter(_released_filter(Transaction))
                .filter(
                    (Transaction.is_transfer.is_(False))
                    | (Transaction.is_transfer.is_(None))
                )
                .order_by(Transaction.date.desc())
                .first()
            )
            if latest_tx is not None:
                month_anchor = latest_tx.date
            else:
                # Fallback: senaste tx oavsett typ (kan vara transfer)
                fallback_tx = (
                    s.query(Transaction)
                    .filter(_released_filter(Transaction))
                    .order_by(Transaction.date.desc())
                    .first()
                )
                month_anchor = (
                    fallback_tx.date if fallback_tx is not None else today
                )
            month_start = _date(month_anchor.year, month_anchor.month, 1)
            if month_anchor.month == 12:
                month_end = _date(month_anchor.year + 1, 1, 1)
            else:
                month_end = _date(
                    month_anchor.year, month_anchor.month + 1, 1,
                )
            from datetime import timedelta as _td_h
            month_end_inclusive = month_end - _td_h(days=1)
            txs = (
                s.query(Transaction)
                .filter(_released_filter(Transaction))
                .filter(Transaction.date >= month_start)
                .filter(Transaction.date <= month_end_inclusive)
                .all()
            )
            # Exkludera transfers (mellan egna konton, pension-spar)
            # från inkomst/utgift — annars räknas pension-transferns
            # 1500 kr som BÅDE inkomst (på ISK) och utgift (från lön)
            # och hub säger '+5000/-5000 = sparat 0' vilket är fel.
            income = sum(
                float(t.amount) for t in txs
                if float(t.amount) > 0
                and not bool(getattr(t, "is_transfer", False))
            )
            expenses = sum(
                -float(t.amount) for t in txs
                if float(t.amount) < 0
                and not bool(getattr(t, "is_transfer", False))
            )
            saved = income - expenses
            save_rate: Optional[float] = (
                round(saved / income * 100, 1) if income > 0 else None
            )
            month_summary = HubMonthSummary(
                income=round(income, 2),
                expenses=round(expenses, 2),
                saved=round(saved, 2),
                save_rate_pct=save_rate,
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
                ).filter(_released_filter(Transaction))
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
            # Saldo i början av månaden = saldo nu MINUS netto-flöde
            # i denna månad. Visas i hub-kortet "Underskott/Sparat denna
            # mån" så eleven förstår kontinuiteten över månadsskiftet.
            month_summary.start_of_month_balance = round(
                total_balance - month_summary.saved, 2,
            )

            # Pending sociala events i scope-DB (max 5 visas på Hub)
            # Filtrera bort events vars deadline redan passerat — seed-
            # flödet skapar historiska events (jan-april) som annars
            # syns som 'pending' i flera månader efter student-skapandet.
            from ..db.models import StudentEvent as _SE_hub
            pending_se = (
                s.query(_SE_hub)
                .filter(
                    _SE_hub.status == "pending",
                    _SE_hub.deadline >= today,
                )
                .order_by(_SE_hub.deadline.asc())
                .limit(5)
                .all()
            )
            for ev in pending_se:
                pending_events.append(HubEventItem(
                    id=ev.id,
                    kind="event",
                    title=ev.title,
                    category=ev.category,
                    cost=float(ev.cost),
                    deadline=ev.deadline,
                    source=ev.source,
                    from_name=None,
                    days_until_deadline=(ev.deadline - today).days,
                    declinable=ev.declinable,
                ))
    except Exception:
        # Scope-DB saknas eller wellbeing failar — returnera minimal
        # data så hubben inte blir vit. Eleven kan fortfarande se
        # karaktär + v2-fält från master.
        pass

    # Inkomna klasskompis-bjudningar (master-DB) — bara för v2-elever
    try:
        from ..school.social_models import ClassEventInvite as _CEI_hub
        with master_session() as ms2:
            invites = (
                ms2.query(_CEI_hub)
                .filter(
                    _CEI_hub.to_student_id == target_sid,
                    _CEI_hub.status == "pending",
                    _CEI_hub.deadline >= _date.today(),
                )
                .order_by(_CEI_hub.deadline.asc())
                .limit(5)
                .all()
            )
            for inv in invites:
                from_name = None
                from_st = ms2.get(Student, inv.from_student_id)
                if from_st is not None:
                    from_name = from_st.display_name
                pending_events.append(HubEventItem(
                    id=inv.id,
                    kind="invite",
                    title=inv.event_title,
                    category="social",
                    cost=float(inv.swish_amount or 0),
                    deadline=inv.deadline,
                    source="classmate_invite",
                    from_name=from_name,
                    days_until_deadline=(
                        inv.deadline - _date.today()
                    ).days,
                    declinable=True,
                ))
    except Exception:
        pass
    pending_events.sort(key=lambda e: e.days_until_deadline)

    # === Spel-tid · 1 real-timme = 1 spel-vecka =================
    # Beräkna nuvarande spel-datum baserat på student.created_at och
    # real-tid. Frontend visar det stort i hub-headern.
    game_time = None
    try:
        from ..game_engine.release_schedule import game_date_for
        with master_session() as _ms_gt:
            _stu_gt = _ms_gt.get(Student, target_sid)
            if _stu_gt is not None and _stu_gt.created_at is not None:
                # game_date_for använder GAME_ANCHOR_DATE som start
                gy, gm, gd = game_date_for(_stu_gt.created_at)
                gd = max(1, min(28, gd))  # safety för Python-date
                from datetime import date as _d_gt
                game_d = _d_gt(gy, gm, gd)
                weekdays = ["Måndag", "Tisdag", "Onsdag", "Torsdag",
                            "Fredag", "Lördag", "Söndag"]
                months = [
                    "januari", "februari", "mars", "april", "maj",
                    "juni", "juli", "augusti", "september", "oktober",
                    "november", "december",
                ]
                wd = weekdays[game_d.weekday()]
                mn = months[gm - 1]
                from ..game_engine.release_schedule import (
                    SECONDS_PER_GAME_DAY,
                )
                elapsed_real = max(
                    0.0,
                    (datetime.utcnow() - _stu_gt.created_at).total_seconds(),
                )
                sec_into_day = int(elapsed_real % SECONDS_PER_GAME_DAY)
                sec_until_next = SECONDS_PER_GAME_DAY - sec_into_day
                game_time = HubGameTime(
                    iso_date=game_d.isoformat(),
                    weekday_label=wd,
                    full_label=f"{wd} {gd} {mn} {gy}",
                    short_label=f"{gd} {mn}",
                    year_month=f"{gy:04d}-{gm:02d}",
                    real_anchor_at=_stu_gt.created_at.isoformat() + "Z",
                    seconds_per_game_day=SECONDS_PER_GAME_DAY,
                    seconds_into_current_day=sec_into_day,
                    seconds_until_next_day=sec_until_next,
                )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "get_hub: game_time-beräkning misslyckades",
        )

    return HubResponse(
        student_id=target_sid,
        character=char,
        v2_level=v2_level,
        v2_spend_profile=v2_spend,
        v2_fairness_choice=v2_fair,
        v2_partner_model=v2_partner,
        pentagon=pentagon,
        month_summary=month_summary,
        total_balance=total_balance,
        pending_events=pending_events,
        accounts_count=accounts_count,
        game_time=game_time,
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
    # Länk till brev som triggade upcoming (om det finns) — låter
    # frontenden navigera till mail-detalj från bank-tabellen.
    mail_id: Optional[int] = None
    # True när dragningen är schemalagd via autogiro/BankID. False =
    # eleven har exporterat fakturan från postlådan men ännu inte
    # signerat den (BankID-signering eller markera-betald).
    is_signed: bool = False
    # Antal SPEL-dagar tills förfall · negativa = förfluten. Beräknas
    # backend-side mot current_game_date() så frontend slipper räkna
    # mot real-tid (= maj 2026 medan spel-tid är jan).
    days_until_expected: int = 0


class BankSummary(BaseModel):
    total_balance: float
    accounts_count: int
    upcoming_open_total: float
    upcoming_open_count: int
    income_this_month: float
    expenses_this_month: float
    transactions_count: int
    # Realtid-projektion · när nästa pending tx släpps till banken.
    # None = inga pending. Frontend kan visa "Nästa transaktion om 2 h".
    next_release_at: Optional[datetime] = None
    pending_count: int = 0
    # Spel-tid · ISO-datum (synkat med privat). Frontend använder
    # detta för "dagar kvar"-beräkningar istället för new Date().
    today_game: Optional[_date] = None


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

    # Drag pengar från signerade autogiro-fakturor först · annars
    # syns banken med upcoming "1 d sen" trots att eleven signerat.
    # Cache-gated 60s så billigt att köra inline.
    try:
        _auto_debit_signed_upcomings_if_due(info.student_id)
    except Exception:
        pass

    try:
        with session_scope() as s:
            # Spel-tid · synkat med privat-tid via business.game_clock.
            # Tidigare användes _date.today() (= maj 2026 real-tid)
            # vilket gjorde att osignerade fakturor med spel-januari-
            # förfallodag försvann ur bank-vyn (filtret 'expected_date
            # >= today' matchade inget) och nyexporterade fakturor
            # auto-flyttades till maj 22 istället för spel-tid + 7 d.
            from ..business.game_clock import current_game_date as _cgd_bank
            today = _cgd_bank()
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
                ).filter(_released_filter(Transaction))
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
                .filter(_released_filter(Transaction))
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
            # Visa kommande dragningar (>= today) PLUS obetalda historiska
            # (< today men inte matchade mot transaktion) — så fakturor som
            # exporterats till banken med due-date i förfluten
            # fortfarande syns och kan signeras.
            from datetime import timedelta as _td_filter
            upcoming_rows = (
                s.query(UpcomingTransaction)
                .filter(
                    (
                        (UpcomingTransaction.expected_date >= today)
                        | (
                            (UpcomingTransaction.matched_transaction_id.is_(None))
                            & (UpcomingTransaction.expected_date >= today - _td_filter(days=60))
                        )
                    )
                )
                .order_by(UpcomingTransaction.expected_date.asc())
                .all()
            )
            upcoming: list[BankUpcoming] = []
            upcoming_open_total = Decimal("0")
            upcoming_open_count = 0
            # Hämta länk upcoming → mail för drill-down från bank-tabellen
            mail_by_upcoming: dict[int, int] = {}
            if upcoming_rows:
                upcoming_ids = [u.id for u in upcoming_rows]
                mail_rows = (
                    s.query(MailItem.upcoming_id, MailItem.id)
                    .filter(MailItem.upcoming_id.in_(upcoming_ids))
                    .all()
                )
                for up_id, m_id in mail_rows:
                    if up_id is not None:
                        mail_by_upcoming[up_id] = m_id
            for u in upcoming_rows:
                # En upcoming räknas som "betald" när den är matchad mot
                # en faktisk transaktion. Mer nyanserad delbetalnings-
                # status finns i /upcoming-endpointen — för v2/bank
                # räcker is_paid=True/False.
                paid = u.matched_transaction_id is not None
                if not paid:
                    upcoming_open_total += u.amount
                    upcoming_open_count += 1
                # is_signed = autogiro satt = signerat via BankID
                # eller pre-konfigurerat. False = exporterat från
                # postlådan men ännu inte signerat (visas som
                # 'Osignerade' i banken).
                days_until_exp = (
                    (u.expected_date - today).days
                    if u.expected_date else 0
                )
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
                    mail_id=mail_by_upcoming.get(u.id),
                    is_signed=bool(u.autogiro) or paid,
                    days_until_expected=days_until_exp,
                ))

            # 4. Månads-summa
            month_txs = (
                s.query(Transaction)
                .filter(_released_filter(Transaction))
                .filter(Transaction.date >= month_start)
                .filter(Transaction.date <= today)
                .all()
            )
            # Exkludera transfers så bank-summary inte räknar
            # interna flytt mellan egna konton som inkomst/utgift.
            income = sum(
                float(t.amount) for t in month_txs
                if float(t.amount) > 0
                and not bool(getattr(t, "is_transfer", False))
            )
            expenses = sum(
                -float(t.amount) for t in month_txs
                if float(t.amount) < 0
                and not bool(getattr(t, "is_transfer", False))
            )

            # Realtid-projektion · nästa pending tx-release
            now_utc = datetime.utcnow()
            next_pending_tx = (
                s.query(Transaction.released_at)
                .filter(Transaction.released_at.isnot(None))
                .filter(Transaction.released_at > now_utc)
                .order_by(Transaction.released_at.asc())
                .first()
            )
            pending_tx_count = (
                s.query(Transaction.id)
                .filter(Transaction.released_at.isnot(None))
                .filter(Transaction.released_at > now_utc)
                .count()
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
                    next_release_at=(
                        next_pending_tx[0] if next_pending_tx else None
                    ),
                    pending_count=int(pending_tx_count or 0),
                    today_game=today,
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
    # None när income_total = 0 — frontend visar "—" istället för 0 %.
    save_rate_pct: Optional[float] = None
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
            save_rate_pct=None,
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
            save_rate: Optional[float] = (
                round(saved / income_total * 100, 1)
                if income_total > 0 else None
            )
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
                    save_rate_pct=save_rate,
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

        # === Sprint 5b post-analys · pentagon-delta vid budget-violation ===
        # Om eleven sänker en kategori under Konsumentverket-minimum loggas
        # det DIREKT som WellbeingEvent (snarare än vänta på nästa
        # wellbeing-recompute). Pedagogiskt: eleven ser konsekvensen direkt
        # i pentagon-historiken. Familje-aware (sambo/barn) via student-
        # profile-lookup mot master-DB.
        if not body.is_income:
            from ..wellbeing.minimums import check_against_minimum
            _kv_profile = None
            try:
                from ..school.models import StudentProfile as _SP_kv
                with master_session() as _msdb_kv:
                    _kv_profile = (
                        _msdb_kv.query(_SP_kv)
                        .filter(_SP_kv.student_id == info.student_id)
                        .first()
                    )
                    if _kv_profile is not None:
                        # Detacha så vi kan använda fältvärdena
                        class _Snap:
                            pass
                        _snap = _Snap()
                        for f in (
                            "age", "family_status", "children_ages",
                            "housing_type",
                        ):
                            setattr(_snap, f, getattr(_kv_profile, f, None))
                        _kv_profile = _snap
            except Exception:
                _kv_profile = None
            check = check_against_minimum(
                cat.name, int(body.planned_amount), profile=_kv_profile,
            )
            if check.is_violation:
                try:
                    from ..game_engine.pentagon import apply_pentagon_delta
                    delta = -5 if check.severity == "subexistens" else -2
                    apply_pentagon_delta(
                        info.student_id,
                        axis="health",
                        requested_delta=delta,
                        reason_kind="decision",
                        reason_id=category_id,
                        reason_table="categories",
                        explanation=(
                            f"sänkt budget för {cat.name} till "
                            f"{int(body.planned_amount)} kr (minimum "
                            f"{check.minimum} kr) · {check.severity}"
                        ),
                        year_month=ym,
                    )
                except Exception:
                    # Pentagon-loggning får inte bryta budget-update
                    pass

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


class V2BudgetResetResponse(BaseModel):
    month: str
    rows_updated: int
    rows_created: int
    categories_with_reference: int


@router.post(
    "/budget/reset-to-konsumentverket",
    response_model=V2BudgetResetResponse,
)
def reset_budget_to_konsumentverket(
    month: Optional[str] = None,
    info: TokenInfo = Depends(require_token),
) -> V2BudgetResetResponse:
    """Sätt alla kategoriers planerade belopp till Konsumentverkets
    referens-värden för perioden. Kategorier utan referens-värde
    lämnas orörda. Idempotent."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast elever kan återställa budgeten.",
        )

    from ..wellbeing.minimums import (
        lookup_minimum, CATEGORY_MINIMUMS_SEK_MONTH,
    )
    from ..db.models import Budget as _Bd

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

    ym = month or _current_year_month()
    rows_updated = 0
    rows_created = 0
    cats_with_ref = 0

    with session_scope() as s:
        cats = s.query(Category).all()
        for cat in cats:
            ref = _fuzzy_minimum(cat.name)
            if ref is None or ref <= 0:
                continue
            cats_with_ref += 1
            existing = (
                s.query(_Bd)
                .filter(_Bd.month == ym, _Bd.category_id == cat.id)
                .first()
            )
            if existing is None:
                s.add(_Bd(
                    month=ym,
                    category_id=cat.id,
                    planned_amount=Decimal(str(ref)),
                ))
                rows_created += 1
            else:
                existing.planned_amount = Decimal(str(ref))
                rows_updated += 1
        s.flush()

    return V2BudgetResetResponse(
        month=ym,
        rows_updated=rows_updated,
        rows_created=rows_created,
        categories_with_reference=cats_with_ref,
    )


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
                # Om mål är kopplat till ett konto: läs verkligt saldo
                # från transaktioner istället för statisk g.current_amount
                # (som annars aldrig uppdateras automatiskt). Eleven
                # ser då sin verkliga sparprogress.
                if g.account_id is not None:
                    from sqlalchemy import func as _fn
                    base_open = (
                        s.query(Account.opening_balance)
                        .filter(Account.id == g.account_id)
                        .scalar()
                    ) or Decimal("0")
                    tx_sum = (
                        s.query(_fn.coalesce(
                            _fn.sum(Transaction.amount), 0,
                        ))
                        .filter(Transaction.account_id == g.account_id)
                        .filter(_released_filter(Transaction))
                        .scalar() or Decimal("0")
                    )
                    if not isinstance(tx_sum, Decimal):
                        tx_sum = Decimal(str(tx_sum))
                    current = base_open + tx_sum
                    if current < 0:
                        current = Decimal("0")
                    # Synca tillbaka för historik (men inte krav)
                    g.current_amount = current
                else:
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


class V2GoalCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    target_amount: float = Field(..., gt=0)
    target_date: Optional[_date] = None
    account_id: Optional[int] = None
    initial_amount: float = 0


class V2GoalUpdateRequest(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[float] = None
    target_date: Optional[_date] = None
    current_amount: Optional[float] = None
    account_id: Optional[int] = None


class V2GoalSimpleResponse(BaseModel):
    id: int
    name: str
    target_amount: float
    current_amount: float
    target_date: Optional[_date]
    account_id: Optional[int]


@router.post("/mal", response_model=V2GoalSimpleResponse)
def create_goal(
    body: V2GoalCreateRequest,
    info: TokenInfo = Depends(require_token),
) -> V2GoalSimpleResponse:
    """Eleven skapar ett nytt sparmål."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(403, "Endast elever")
    with session_scope() as s:
        g = Goal(
            name=body.name.strip(),
            target_amount=Decimal(str(body.target_amount)),
            current_amount=Decimal(str(body.initial_amount)),
            target_date=body.target_date,
            account_id=body.account_id,
        )
        s.add(g)
        s.flush()
        return V2GoalSimpleResponse(
            id=g.id,
            name=g.name,
            target_amount=float(g.target_amount),
            current_amount=float(g.current_amount),
            target_date=g.target_date,
            account_id=g.account_id,
        )


@router.patch("/mal/{goal_id}", response_model=V2GoalSimpleResponse)
def update_goal(
    goal_id: int,
    body: V2GoalUpdateRequest,
    info: TokenInfo = Depends(require_token),
) -> V2GoalSimpleResponse:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(403, "Endast elever")
    with session_scope() as s:
        g = s.get(Goal, goal_id)
        if g is None:
            raise HTTPException(404, "Målet finns inte")
        if body.name is not None:
            g.name = body.name.strip()
        if body.target_amount is not None:
            g.target_amount = Decimal(str(body.target_amount))
        if body.target_date is not None:
            g.target_date = body.target_date
        if body.current_amount is not None:
            g.current_amount = Decimal(str(body.current_amount))
        if body.account_id is not None:
            g.account_id = body.account_id
        s.flush()
        return V2GoalSimpleResponse(
            id=g.id,
            name=g.name,
            target_amount=float(g.target_amount),
            current_amount=float(g.current_amount),
            target_date=g.target_date,
            account_id=g.account_id,
        )


@router.delete("/mal/{goal_id}", status_code=204)
def delete_goal(
    goal_id: int,
    info: TokenInfo = Depends(require_token),
) -> None:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(403, "Endast elever")
    with session_scope() as s:
        g = s.get(Goal, goal_id)
        if g is not None:
            s.delete(g)
            s.flush()


# === Postlådan (MailItem-tabellen) ===

MailType = Literal["invoice", "salary_slip", "authority", "reminder", "info"]
MailStatus = Literal[
    "unhandled", "viewed", "exported", "paid", "expired", "handled",
]
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
    body: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[_date] = None
    received_at: datetime
    status: MailStatus
    upcoming_id: Optional[int] = None
    transaction_id: Optional[int] = None
    is_recurring: bool
    ocr_reference: Optional[str] = None
    bankgiro: Optional[str] = None
    notes: Optional[str] = None


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
    # Realtid-projektion: när nästa pending event "släpps" till postlådan.
    # Frontend kan visa "nästa brev kommer 14:32" eller liknande.
    next_release_at: Optional[datetime] = None
    pending_count: int = 0


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
    # Auto-tick · eskalera obetalda fakturor innan vi listar mail
    # så eleven ser nya reminder-mail i samma load. Cachat 60s.
    # Plus auto-tick nya privata månader (1 real-timme = 1 spel-vecka)
    # — när eleven driver karaktären framåt seedar vi nästa månad så
    # postlådan fortsätter fyllas.
    # Plus släpp Skatteverket-deklaration-mail per spel-år.
    if info.role == "student" and info.student_id is not None:
        try:
            _auto_tick_private_months_if_due(info.student_id)
        except Exception:
            pass
        try:
            # Drag pengar från signerade autogiro-fakturor som
            # förfaller i spel-tid · markerar mailet som paid.
            _auto_debit_signed_upcomings_if_due(info.student_id)
        except Exception:
            pass
        # Migrationsfix · äldre mail stämplades med utcnow → "7 maj"
        # överallt. Normaliserar received_at till spel-tid baserat på
        # due_date. Cache-gated 10 min så billig.
        try:
            _normalize_mail_received_at_if_seed_stamped(info.student_id)
        except Exception:
            pass
        try:
            _seed_skv_deklaration_events(info.student_id)
        except Exception:
            pass
        try:
            # Pipeline · släpp slutskattebesked + utbetalningar/kvarskatt
            # för deklarationer som hunnit passerat besked_due_on resp.
            # payout_due_on i spel-tid.
            from .skatten_pipeline import process_for_student_if_due
            process_for_student_if_due(info.student_id)
        except Exception:
            pass
        try:
            _run_dunning_for_student(info.student_id)
        except Exception:
            pass

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
            q = (
                s.query(MailItem)
                .filter(_released_filter(MailItem))
                .order_by(
                    MailItem.received_at.desc(), MailItem.id.desc()
                )
            )
            if filter == "unhandled":
                # 'Ohanterade' = både unhandled OCH viewed.
                # Brev som eleven läst men inte aktivt hanterat
                # (betalat/exporterat/ignorerat) räknas som ohanterade
                # tills explicit val gjorts. Annars känns det som om
                # öppning = hantering, vilket användaren inte vill.
                q = q.filter(
                    MailItem.status.in_(["unhandled", "viewed"])
                )
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
            # Filtrera även här på released_at så pending-events inte
            # smyger in i counts innan de är synliga.
            all_mails = (
                s.query(MailItem)
                .filter(_released_filter(MailItem))
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
                # 'Ohanterad' = både unhandled OCH viewed (läst men
                # ej hanterat). Räknas som need-action tills eleven
                # exporterar, betalar eller ignorerar explicit.
                if m.status in ("unhandled", "viewed"):
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
                ))

            # Realtid-projektion: hitta tidigaste pending mail som
            # ännu inte är synlig (released_at > NOW). Frontend
            # visar countdown till nästa "leverans".
            now_utc = datetime.utcnow()
            next_pending = (
                s.query(MailItem.released_at)
                .filter(MailItem.released_at.isnot(None))
                .filter(MailItem.released_at > now_utc)
                .order_by(MailItem.released_at.asc())
                .first()
            )
            pending_count = (
                s.query(MailItem.id)
                .filter(MailItem.released_at.isnot(None))
                .filter(MailItem.released_at > now_utc)
                .count()
            )

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
                    next_release_at=(
                        next_pending[0] if next_pending else None
                    ),
                    pending_count=int(pending_count or 0),
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
        old_status = m.status
        m.status = body.status
        s.flush()

        # Pentagon-koppling · faktura går till "expired" (eleven hann inte
        # hantera den) → safety-dipp, och om belopp > 1000 kr även economy.
        if (
            body.status == "expired"
            and old_status != "expired"
            and m.mail_type == "invoice"
        ):
            try:
                from ..game_engine.pentagon import apply_pentagon_delta
                amt = float(m.amount or 0)
                apply_pentagon_delta(
                    info.student_id,
                    axis="safety",
                    requested_delta=-3,
                    reason_kind="event",
                    reason_id=m.id,
                    reason_table="mail_items",
                    explanation=(
                        f"missade faktura: {m.subject} "
                        f"({int(abs(amt))} kr förfallen)"
                    ),
                )
                if abs(amt) >= 1000:
                    apply_pentagon_delta(
                        info.student_id,
                        axis="economy",
                        requested_delta=-2,
                        reason_kind="event",
                        reason_id=m.id,
                        reason_table="mail_items",
                        explanation=(
                            f"obetald faktura {int(abs(amt))} kr — "
                            f"riskerar inkasso"
                        ),
                    )
            except Exception:
                pass

        result = V2MailItemRow(
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
    # Bust hub-cachen så ohanterade-räknaren uppdateras direkt
    invalidate_hub_cache(info.student_id)
    return result


# === Exportera brev till banken (skapar UpcomingTransaction) ===


class V2MailExportRequest(BaseModel):
    """Eleven exporterar en faktura från postlådan till banken.

    Skapar en UpcomingTransaction så fakturan dyker upp i bankens
    'kommande dragningar'-tabell. Läraren kan därefter signera via
    BankID-flödet."""
    debit_account_id: Optional[int] = None
    expected_date: Optional[_date] = None
    autogiro: bool = False


class V2MailExportResponse(BaseModel):
    mail_id: int
    upcoming_id: int
    expected_date: _date
    amount: float


@router.post(
    "/postladan/{mail_id}/export-to-bank",
    response_model=V2MailExportResponse,
)
def export_mail_to_bank(
    mail_id: int,
    body: V2MailExportRequest,
    info: TokenInfo = Depends(require_token),
) -> V2MailExportResponse:
    """Konverterar ett invoice-brev till en bokad UpcomingTransaction.

    - Sätter mail.status='exported' så postlådan visar "Exporterad".
    - Skapar UpcomingTransaction med rätt belopp + förfallodatum + OCR.
    - Kopplar mail.upcoming_id för cross-länk (banken → postlådan).

    Idempotent: om brevet redan har upcoming_id returneras den utan
    att skapa duplicat.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast eleven själv kan exportera fakturor.",
        )

    with session_scope() as s:
        m = s.get(MailItem, mail_id)
        if m is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Brevet hittades inte"
            )
        if m.mail_type not in ("invoice", "reminder"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Bara fakturor/påminnelser kan exporteras till banken.",
            )
        if m.amount is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Brevet saknar belopp — inget att exportera.",
            )

        # Idempotent · returnera befintlig om redan exporterad
        if m.upcoming_id is not None:
            existing = s.get(UpcomingTransaction, m.upcoming_id)
            if existing is not None:
                return V2MailExportResponse(
                    mail_id=m.id,
                    upcoming_id=existing.id,
                    expected_date=existing.expected_date,
                    amount=float(existing.amount),
                )

        expected = body.expected_date or m.due_date
        if expected is None:
            from ..business.game_clock import current_game_date as _cgd_exp
            expected = _cgd_exp()
        # Om eleven exporterar en faktura med förfluten due-date,
        # flytta auto till spel-idag + 7 dagar så banken hinner signera
        # och autogiro fungerar (annars hamnar den i 'past' och
        # försvinner från bankens upcoming-vy).
        from ..business.game_clock import current_game_date as _cgd_today
        today_game = _cgd_today()
        if expected < today_game:
            from datetime import timedelta as _td_exp
            expected = today_game + _td_exp(days=7)
        amount_abs = abs(Decimal(str(m.amount)))

        upc = UpcomingTransaction(
            kind="bill",
            name=m.sender,
            amount=amount_abs,
            expected_date=expected,
            ocr_reference=m.ocr_reference,
            bankgiro=m.bankgiro,
            autogiro=body.autogiro,
            debit_account_id=body.debit_account_id,
            recurring_monthly=bool(m.is_recurring),
            invoice_date=m.received_at.date() if m.received_at else None,
        )
        s.add(upc)
        s.flush()

        m.upcoming_id = upc.id
        m.status = "exported"
        s.flush()
        export_result = V2MailExportResponse(
            mail_id=m.id,
            upcoming_id=upc.id,
            expected_date=upc.expected_date,
            amount=float(upc.amount),
        )
    invalidate_hub_cache(info.student_id)
    return export_result


# === Överföring mellan elevens egna konton ===


class V2TransferRequest(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: float = Field(..., gt=0)
    description: Optional[str] = None
    transfer_date: Optional[_date] = None


class V2TransferResponse(BaseModel):
    source_tx_id: int
    destination_tx_id: int
    amount: float
    transfer_date: _date


@router.post("/banken/transfer", response_model=V2TransferResponse)
def create_v2_transfer(
    body: V2TransferRequest,
    info: TokenInfo = Depends(require_token),
) -> V2TransferResponse:
    """Eleven flyttar pengar mellan sina egna konton (lönekonto →
    sparkonto, ISK osv.). Skapar två transaktioner med
    is_transfer=True och paret kopplat via transfer_pair_id.

    Pedagogisk regel: sparkonto/ISK/pension får inte gå minus.
    Eleven kan alltså inte 'fylla' sparkontot från ett tomt konto.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Endast elever",
        )
    if body.from_account_id == body.to_account_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Från- och till-konto måste vara olika",
        )

    with session_scope() as s:
        src = s.get(Account, body.from_account_id)
        dst = s.get(Account, body.to_account_id)
        if src is None:
            raise HTTPException(404, "Avsändarkonto saknas")
        if dst is None:
            raise HTTPException(404, "Mottagarkonto saknas")

        amount = Decimal(str(body.amount))

        # Sparkonto/ISK/pension får inte gå minus
        NEVER_NEG = {"savings", "isk", "pension"}
        if src.type in NEVER_NEG:
            from sqlalchemy import func as _func
            opening = src.opening_balance or Decimal("0")
            tx_sum = (
                s.query(_func.coalesce(_func.sum(Transaction.amount), 0))
                .filter(Transaction.account_id == src.id)
                .filter(_released_filter(Transaction))
                .scalar() or Decimal("0")
            )
            if not isinstance(tx_sum, Decimal):
                tx_sum = Decimal(str(tx_sum))
            balance = opening + tx_sum
            if balance - amount < 0:
                kind_sv = {
                    "savings": "Sparkontot",
                    "isk": "ISK-kontot",
                    "pension": "Pensionskontot",
                }.get(src.type, src.name)
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"{kind_sv} skulle gå minus. Tillgängligt: "
                    f"{int(balance)} kr.",
                )

        # Spel-tid · annars stämplas överföringar med real-tid (=
        # maj 2026) trots att eleven är på spel-januari.
        if body.transfer_date is not None:
            tx_date = body.transfer_date
        else:
            from ..business.game_clock import current_game_date as _cgd_v2tr
            tx_date = _cgd_v2tr()
        descr = (body.description or "").strip() \
            or f"Överföring till {dst.name}"
        # Idempotency-hash: säker även om eleven trycker två gånger
        idem_raw = (
            f"v2-tx-{body.from_account_id}-{body.to_account_id}-"
            f"{tx_date.isoformat()}-{amount}"
        )
        out_hash = f"transfer-{idem_raw}-out"
        in_hash = f"transfer-{idem_raw}-in"

        existing = (
            s.query(Transaction)
            .filter(Transaction.hash == out_hash)
            .first()
        )
        if existing is not None:
            pair_id = existing.transfer_pair_id
            return V2TransferResponse(
                source_tx_id=existing.id,
                destination_tx_id=pair_id or 0,
                amount=float(amount),
                transfer_date=tx_date,
            )

        out_tx = Transaction(
            account_id=src.id,
            date=tx_date,
            amount=-amount,
            raw_description=descr,
            is_transfer=True,
            user_verified=True,
            hash=out_hash,
        )
        in_tx = Transaction(
            account_id=dst.id,
            date=tx_date,
            amount=amount,
            raw_description=f"Överföring från {src.name}",
            is_transfer=True,
            user_verified=True,
            hash=in_hash,
        )
        s.add_all([out_tx, in_tx])
        s.flush()
        out_tx.transfer_pair_id = in_tx.id
        in_tx.transfer_pair_id = out_tx.id
        s.flush()
        transfer_result = V2TransferResponse(
            source_tx_id=out_tx.id,
            destination_tx_id=in_tx.id,
            amount=float(amount),
            transfer_date=tx_date,
        )
    invalidate_hub_cache(info.student_id)
    return transfer_result


# === Retry-betalning efter misslyckat autogiro (SKV-5) ===

class V2RetryPaymentResponse(BaseModel):
    """Resultat av 'Försök igen' på en misslyckad betalning."""
    status: Literal["paid", "rescheduled", "still_insufficient"]
    message: str
    new_expected_date: Optional[str] = None
    shortfall_kr: Optional[int] = None


@router.post(
    "/postladan/{mail_id}/retry-payment",
    response_model=V2RetryPaymentResponse,
)
def retry_failed_payment(
    mail_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2RetryPaymentResponse:
    """Eleven trycker 'Försök igen' på en misslyckad autogiro-betalning.

    Flöde:
      1. Hittar MailItem(status='failed') + dess UpcomingTransaction
      2. Räknar saldot på det avsedda kontot (samma logik som
         _auto_debit_signed_upcomings_if_due använder)
      3. Om saldot räcker → drar direkt + flippar mail till 'paid'
      4. Om INTE → schemalägger upcoming till 1 spel-dag fram,
         autogiro=True igen så nästa auto-debit-körning fångar den
         (om eleven fyller på under tiden)
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast eleven själv kan försöka betala igen.",
        )

    from datetime import datetime as _dt_ret, timedelta as _td_ret
    from decimal import Decimal as _Dec_ret
    from hashlib import sha256 as _sha_ret
    from sqlalchemy import func as _sf_ret, or_ as _sor_ret
    from ..business.game_clock import current_game_date_for_student

    today_game = current_game_date_for_student(info.student_id)

    with session_scope() as s:
        m = s.get(MailItem, mail_id)
        if m is None:
            raise HTTPException(404, "Mail saknas")
        if m.status != "failed":
            raise HTTPException(
                409,
                "Den här fakturan har inte misslyckats — inget att "
                "försöka igen.",
            )
        if m.upcoming_id is None:
            raise HTTPException(
                409,
                "Fakturan saknar kopplad betalning · exportera först "
                "till banken.",
            )

        u = s.get(UpcomingTransaction, m.upcoming_id)
        if u is None:
            raise HTTPException(404, "Betalningsrad saknas")

        acc_id = u.debit_account_id
        if acc_id is None:
            # Default till första checking
            default_acc = (
                s.query(Account)
                .filter(Account.type == "checking")
                .order_by(Account.id.asc())
                .first()
            )
            if default_acc is None:
                raise HTTPException(409, "Inget lönekonto hittades")
            acc_id = default_acc.id

        # Saldo-räkning · SAMMA filter som auto-debit
        bal_q = (
            s.query(_sf_ret.coalesce(_sf_ret.sum(Transaction.amount), 0))
            .filter(
                Transaction.account_id == acc_id,
                Transaction.date <= today_game,
                _sor_ret(
                    Transaction.released_at.is_(None),
                    Transaction.released_at <= _dt_ret.utcnow(),
                ),
            )
        )
        base = s.get(Account, acc_id)
        bal = (
            _Dec_ret(str(base.opening_balance or 0))
            + _Dec_ret(str(bal_q.scalar() or 0))
        )

        if bal < u.amount:
            shortfall = int(u.amount - bal)
            # Schemalägg framåt · auto-debit-cykeln kör nästa GET
            u.expected_date = today_game + _td_ret(days=1)
            u.autogiro = True
            # Behåll mail som failed tills dragningen faktiskt går
            return V2RetryPaymentResponse(
                status="still_insufficient",
                message=(
                    f"Saldot räcker fortfarande inte · saknas "
                    f"{shortfall} kr. Försöker igen automatiskt "
                    f"{u.expected_date.isoformat()} (spel-tid). "
                    "Fyll på kontot under tiden."
                ),
                new_expected_date=u.expected_date.isoformat(),
                shortfall_kr=shortfall,
            )

        # Saldot räcker · dra DIREKT (idempotent hash matchar auto-debit-
        # mönstret så om något redan har dragit den får vi inte
        # duplicate).
        raw = (
            f"autogiro|{info.student_id}|{u.id}|"
            f"{today_game.isoformat()}|{u.amount}|retry"
        )
        tx_hash = _sha_ret(raw.encode()).hexdigest()[:32]
        existing_tx = (
            s.query(Transaction).filter(Transaction.hash == tx_hash).first()
        )
        if existing_tx is None:
            tx = Transaction(
                account_id=acc_id,
                date=today_game,
                amount=-_Dec_ret(str(u.amount)),
                currency="SEK",
                raw_description=f"Autogiro · {u.name} (retry)",
                normalized_merchant=u.name,
                hash=tx_hash,
                is_transfer=False,
                user_verified=True,
            )
            s.add(tx)
            s.flush()
            u.matched_transaction_id = tx.id

        u.expected_date = today_game
        u.autogiro = True
        m.status = "paid"

        return V2RetryPaymentResponse(
            status="paid",
            message=(
                f"Betalningen genomfördes · {int(u.amount)} kr dras "
                f"från lönekontot idag ({today_game.isoformat()})."
            ),
            new_expected_date=today_game.isoformat(),
            shortfall_kr=0,
        )


# === Upcoming-uppdatering (V2 · /upcoming-V1 är gateblockad i school) ===

class V2UpcomingUpdateRequest(BaseModel):
    """Eleven flyttar förfallodag eller byter debiterande konto.

    Signerade dragningar (autogiro=True) blockeras → eleven måste
    avsigna och signera om för att ändra datum (matchar verkliga
    bankavtal: en signerad autogiro-fullmakt kan inte godtyckligt
    ändras utan ny signering).
    """
    expected_date: Optional[_date] = None
    debit_account_id: Optional[int] = None


class V2UpcomingUpdateResponse(BaseModel):
    id: int
    expected_date: _date
    debit_account_id: Optional[int]
    autogiro: bool
    is_paid: bool


@router.patch(
    "/upcoming/{upcoming_id}",
    response_model=V2UpcomingUpdateResponse,
)
def update_upcoming_v2(
    upcoming_id: int,
    body: V2UpcomingUpdateRequest,
    info: TokenInfo = Depends(require_token),
) -> V2UpcomingUpdateResponse:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Endast elever",
        )
    with session_scope() as s:
        u = s.get(UpcomingTransaction, upcoming_id)
        if u is None:
            raise HTTPException(404, "Upcoming hittades inte")
        is_paid = u.matched_transaction_id is not None
        if is_paid:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Fakturan är redan betald — datum kan inte ändras.",
            )
        # Pedagogisk regel: signerad autogiro är ett bindande avtal med
        # banken. Eleven måste avsigna fakturan i postlådan först om
        # förfallodatum behöver ändras.
        if (
            body.expected_date is not None
            and bool(u.autogiro)
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Fakturan är signerad via BankID. Avsigna i "
                "postlådan först om du behöver flytta datumet — "
                "sedan signerar du om med nytt datum.",
            )
        if body.expected_date is not None:
            u.expected_date = body.expected_date
            # debit_date följer expected_date om den inte explicit satts
            if u.debit_date is None or u.debit_date == u.expected_date:
                u.debit_date = body.expected_date
        if body.debit_account_id is not None:
            # Validera att kontot finns + tillhör eleven
            acc = s.get(Account, body.debit_account_id)
            if acc is None:
                raise HTTPException(
                    400, f"Konto {body.debit_account_id} hittades inte",
                )
            u.debit_account_id = body.debit_account_id
        s.flush()
        return V2UpcomingUpdateResponse(
            id=u.id,
            expected_date=u.expected_date,
            debit_account_id=u.debit_account_id,
            autogiro=bool(u.autogiro),
            is_paid=is_paid,
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

    # Lönespecar · läses från MailItem.mail_type='salary_slip' istället
    # för Transaction-likhetssökning på 'lön'. Raw_description-LIKE
    # fångade fel transaktioner (skatteåterbäring, andra bidrag) och
    # räknade `tax = gross - net` som inkluderade sjukavdrag — visade
    # därför 'skatt 26 908' (84 %) för en månad med sjukfrånvaro.
    salary_slips: list[V2EmployerSalarySlip] = []
    try:
        from ..school.tax import compute_net_salary as _emp_net
        with session_scope() as s:
            today = _date.today()
            from datetime import timedelta as _td
            cutoff_d = today - _td(days=120)

            # Primär källa: MailItem.mail_type='salary_slip' (game_engine-
            # genererade lönespec). Då har vi explicit period + brutto/
            # netto utan att behöva substring-matcha 'lön' i tx.
            mail_rows = (
                s.query(MailItem)
                .filter(_released_filter(MailItem))
                .filter(MailItem.mail_type == "salary_slip")
                .filter(MailItem.due_date >= cutoff_d)
                .order_by(MailItem.due_date.desc())
                .limit(4)
                .all()
            )
            seen_months: set[str] = set()
            for m in mail_rows:
                if m.due_date is None:
                    continue
                month_str = (
                    f"{m.due_date.year:04d}-{m.due_date.month:02d}"
                )
                gross_amt = (
                    float(profile.gross_salary_monthly)
                    if profile.gross_salary_monthly else None
                )
                if gross_amt:
                    real = _emp_net(int(gross_amt))
                    tax_amt = float(real.total_tax)
                else:
                    tax_amt = None
                net_paid = (
                    float(m.amount) if m.amount is not None else 0.0
                )
                pension_amt = (
                    round(gross_amt * (pension_pct / 100), 2)
                    if gross_amt and pension_pct else None
                )
                salary_slips.append(V2EmployerSalarySlip(
                    id=m.id,
                    month=month_str,
                    date=m.due_date,
                    net_amount=net_paid,
                    gross_amount=gross_amt,
                    tax_amount=tax_amt,
                    pension_amount=pension_amt,
                    description=m.subject or "Lönespec",
                ))
                seen_months.add(month_str)

            # Fallback (för v1-stilade scope:s utan MailItem-salary_slip):
            # läs Transaction där description börjar med 'Lön ' så vi
            # bevarar bakåtkompat med tester som seedar transactions
            # direkt utan mail-rader.
            if len(salary_slips) < 4:
                tx_rows = (
                    s.query(Transaction)
                    .filter(_released_filter(Transaction))
                    .filter(Transaction.amount > 0)
                    .filter(Transaction.date >= cutoff_d)
                    .filter(
                        _func.lower(Transaction.raw_description)
                        .like("lön %"),
                    )
                    .order_by(Transaction.date.desc())
                    .limit(4)
                    .all()
                )
                for t in tx_rows:
                    month_str = (
                        f"{t.date.year:04d}-{t.date.month:02d}"
                    )
                    if month_str in seen_months:
                        continue
                    net_amt = float(t.amount)
                    gross_amt = (
                        float(profile.gross_salary_monthly)
                        if profile.gross_salary_monthly else None
                    )
                    if gross_amt:
                        real = _emp_net(int(gross_amt))
                        tax_amt = float(real.total_tax)
                    else:
                        tax_amt = None
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
                    seen_months.add(month_str)
    except Exception:
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


class V2TaxCommuteHint(BaseModel):
    """Pedagogisk reseavdrag-hint baserat på StudentProfile.commute_km.

    Vi fyller INTE i avdraget åt eleven. Hen ska själv beräkna och
    mata in det · läromoment. Vi visar bara underlaget + grundnivån.
    """
    has_car: bool
    fuel_type: Optional[str] = None
    commute_km_one_way: int
    workdays_per_year: int = 220
    # Beräknat: km × 2 × workdays × 18,5 öre/km
    estimated_annual_cost: int
    # Grundnivå · 11 000 kr · bara över räknas som avdrag
    threshold_kr: int = 11_000
    # Eleven kan deklarera (estimated - threshold) om positivt
    suggested_deduction_kr: int


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
    # SKV-3 · pedagogisk hint för reseavdrag · eleven fyller in själv
    commute_hint: Optional[V2TaxCommuteHint] = None


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

    # Skatteverket-fönster · läge för att titta på sidan måste vara
    # granska eller senare (off-season = låst).
    _gate_skatten_for_read(info.student_id)

    # Pipeline · process ev. pending besked/utbetalningar innan vi
    # listar (eleven ser nya mail i samma load). Cachat 1 min.
    try:
        from .skatten_pipeline import process_for_student_if_due
        process_for_student_if_due(info.student_id)
    except Exception:
        pass

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
                .filter(_released_filter(Transaction))
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

    # SKV-3 · pedagogisk reseavdrags-hint. Vi BERÄKNAR underlaget
    # baserat på StudentProfile.commute_km men fyller INTE i avdraget
    # automatiskt — eleven måste själv mata in det. Pedagogisk poäng:
    # eleven får syn på 18,50 öre/km × 2 × 220 arbetsdagar och kan
    # själv räkna ut om hen kvalar över 11 000 kr grundnivå.
    commute_hint: Optional[V2TaxCommuteHint] = None
    try:
        with master_session() as ms_hint:
            sp_hint = (
                ms_hint.query(StudentProfile)
                .filter(StudentProfile.student_id == info.student_id)
                .first()
            )
            if sp_hint is not None:
                ck = int(getattr(sp_hint, "commute_km", 0) or 0)
                has_car_h = bool(getattr(sp_hint, "has_car", False))
                fuel_h = getattr(sp_hint, "car_fuel_type", None)
                if ck > 0:
                    annual_km = ck * 2 * 220
                    annual_cost = int(annual_km * 0.185)  # 18,5 öre/km
                    above_threshold = max(0, annual_cost - 11_000)
                    commute_hint = V2TaxCommuteHint(
                        has_car=has_car_h,
                        fuel_type=fuel_h,
                        commute_km_one_way=ck,
                        estimated_annual_cost=annual_cost,
                        suggested_deduction_kr=above_threshold,
                    )
    except Exception:
        pass

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
        commute_hint=commute_hint,
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
                    .filter(_released_filter(Transaction))
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
            # Räkna alltid om om vi inte har student_id/profile-data
            # i existerande cache (gamla rader använde formel utan
            # ålder/familj/boende = base 100, gav alla A).
            stale = (
                check is None
                or (datetime.utcnow() - check.computed_at) > _td(days=7)
                or check.uc_score_value == 100
            )
            if stale and annual_gross_dec > 0:
                check = compute_credit_check(
                    s, annual_gross_dec,
                    student_id=info.student_id,
                )

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


class V2ExtraAmortRequest(BaseModel):
    """Eleven gör en extra amortering på ett befintligt lån."""
    amount: float = Field(..., gt=0)
    debit_account_id: int


class V2ExtraAmortResponse(BaseModel):
    loan_id: int
    transaction_id: int
    payment_id: int
    amount: float
    new_principal_estimate: float


@router.post(
    "/lan/{loan_id}/extra-amortering",
    response_model=V2ExtraAmortResponse,
)
def extra_amortering(
    loan_id: int,
    body: V2ExtraAmortRequest,
    info: TokenInfo = Depends(require_token),
) -> V2ExtraAmortResponse:
    """Eleven gör en extra amortering · skapar Transaction (negativt
    belopp på debit_account) + LoanPayment (positivt, payment_type=
    'amortization'). Banksaldot dras automatiskt eftersom
    Account-saldot räknas live ur Transaction-summan.

    Pedagogiskt: extra amortering är 'garanterad avkastning lika hög
    som lånets räntenivå'. Konton räknas korrekt; nästa månads ränta
    blir lägre.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Endast elever",
        )

    with session_scope() as s:
        loan = s.get(Loan, loan_id)
        if loan is None:
            raise HTTPException(404, "Lånet hittades inte")
        acc = s.get(Account, body.debit_account_id)
        if acc is None:
            raise HTTPException(404, "Debit-kontot hittades inte")

        amount = Decimal(str(body.amount))

        # Kontrollera att kontot inte går minus (utöver lönekonto/credit)
        from sqlalchemy import func as _f
        opening = acc.opening_balance or Decimal("0")
        tx_sum = (
            s.query(_f.coalesce(_f.sum(Transaction.amount), 0))
            .filter(Transaction.account_id == acc.id)
            .filter(_released_filter(Transaction))
            .scalar() or Decimal("0")
        )
        if not isinstance(tx_sum, Decimal):
            tx_sum = Decimal(str(tx_sum))
        balance = opening + tx_sum
        if acc.type in ("savings", "isk", "pension"):
            if balance - amount < 0:
                raise HTTPException(
                    400,
                    f"Kontot {acc.name} har bara {int(balance)} kr — "
                    "kan inte amortera så mycket.",
                )

        today = _date.today()
        idem = (
            f"v2-extra-amort-{loan_id}-{acc.id}-"
            f"{today.isoformat()}-{amount}"
        )
        existing = (
            s.query(Transaction)
            .filter(Transaction.hash == idem)
            .first()
        )
        if existing is not None:
            pay = (
                s.query(LoanPayment)
                .filter(LoanPayment.transaction_id == existing.id)
                .first()
            )
            return V2ExtraAmortResponse(
                loan_id=loan.id,
                transaction_id=existing.id,
                payment_id=pay.id if pay else 0,
                amount=float(amount),
                new_principal_estimate=float(
                    (loan.current_balance_at_creation
                     or loan.principal_amount) - amount
                ),
            )

        tx = Transaction(
            account_id=acc.id,
            date=today,
            amount=-amount,
            raw_description=f"Extra amortering · {loan.name}",
            user_verified=True,
            hash=idem,
        )
        s.add(tx)
        s.flush()

        pay = LoanPayment(
            loan_id=loan.id,
            transaction_id=tx.id,
            date=today,
            amount=amount,
            payment_type="amortization",
        )
        s.add(pay)
        s.flush()

        # Beräkna nytt principal-estimate (kvarstående principal -
        # alla amorteringar). Loan.current_balance_at_creation
        # eller principal_amount är basen.
        base = loan.current_balance_at_creation or loan.principal_amount
        all_amort = (
            s.query(_f.coalesce(_f.sum(LoanPayment.amount), 0))
            .filter(
                LoanPayment.loan_id == loan.id,
                LoanPayment.payment_type == "amortization",
            )
            .scalar() or Decimal("0")
        )
        if not isinstance(all_amort, Decimal):
            all_amort = Decimal(str(all_amort))
        new_principal = base - all_amort

        return V2ExtraAmortResponse(
            loan_id=loan.id,
            transaction_id=tx.id,
            payment_id=pay.id,
            amount=float(amount),
            new_principal_estimate=float(max(new_principal, Decimal("0"))),
        )


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


# === Eleven ansöker själv om lån · /v2/lan/apply ===
#
# Verklighetstrogen lånesimulering. Eleven kan ansöka om fyra lånetyper:
# privatlån, billån, bolån, SMS-lån. Varje lånetyp har:
#   - Eget belopp/löptid-spann (verklighetsbaserat)
#   - Egen ränta-bana (baseras på elevens UC-score)
#   - Egen godkännande-tröskel (UC + KALP)
#   - Egen pedagogisk wellbeing-impact (SMS-lån varnar safety; bolån
#     är "stort beslut" → safety-)
#
# Hela flödet är spårbart för läraren via StudentActivity + lagras
# alltid i CreditApplication (även avslag/abandon).

LoanKind = Literal["privatlan", "billan", "bolan", "smslan"]


# Specs per lånetyp — verklighetstrogna ranges (2024 svenska marknaden)
_LOAN_KIND_SPECS: dict[str, dict] = {
    "privatlan": {
        "min_amount": 10_000,
        "max_amount": 500_000,
        "min_term": 12,
        "max_term": 144,  # 12 år
        "min_score": 500,  # C+
        "rate_at_min_score": 0.12,  # 12 %
        "rate_at_max_score": 0.045,  # 4.5 %
        "lenders": ["Avanza", "SEB", "Marginalen", "Resurs"],
        "label": "Privatlån",
        "category_hint": "Privatlån",
        "wellbeing": {
            "economy": -3,
            "safety": -2,
        },
        "deposit": True,  # pengarna går in på lönekontot
    },
    "billan": {
        "min_amount": 50_000,
        "max_amount": 500_000,
        "min_term": 36,
        "max_term": 84,  # 7 år
        "min_score": 600,  # B+
        "rate_at_min_score": 0.08,
        "rate_at_max_score": 0.04,
        "lenders": [
            "Volkswagen Finans", "Toyota Financial",
            "Marginalen Bank", "Nordea Finans",
        ],
        "label": "Billån",
        "category_hint": "Billån",
        "wellbeing": {
            "economy": -2,
            "safety": +1,  # bil ger trygghet/mobilitet
        },
        "deposit": False,  # pengarna går till bilförsäljaren — inte synligt
    },
    "bolan": {
        "min_amount": 200_000,
        "max_amount": 5_000_000,
        "min_term": 120,  # 10 år
        "max_term": 600,  # 50 år
        "min_score": 600,
        "rate_at_min_score": 0.055,
        "rate_at_max_score": 0.025,
        "lenders": ["SBAB", "Handelsbanken", "Swedbank", "SEB"],
        "label": "Bolån",
        "category_hint": "Bolån",
        "wellbeing": {
            "economy": -2,
            "safety": +3,  # eget hem ökar trygghet
        },
        "deposit": False,  # går till säljaren
    },
    "smslan": {
        "min_amount": 1_000,
        "max_amount": 30_000,
        "min_term": 1,
        "max_term": 12,
        "min_score": 0,  # ingen tröskel — det är poängen, det är en fälla
        "rate_at_min_score": 0.50,  # 50 % effektiv årsränta
        "rate_at_max_score": 0.30,  # 30 % effektiv årsränta minimum
        "lenders": ["Folkia", "Klarna Express", "Trustbuddy", "MobilLån"],
        "label": "SMS-lån",
        "category_hint": "Privatlån",
        "wellbeing": {
            "economy": -5,
            "safety": -8,  # tydlig pedagogisk varningssignal
        },
        "deposit": True,
        "high_cost": True,
    },
}


def _annuity_monthly(
    principal: Decimal, annual_rate: float, months: int,
) -> Decimal:
    """Annuitetsmånadsbetalning. annual_rate är decimaltal (0.05 = 5 %)."""
    if months <= 0:
        return Decimal("0")
    if annual_rate <= 0:
        return (principal / Decimal(months)).quantize(Decimal("0.01"))
    r = Decimal(str(annual_rate)) / Decimal("12")
    n = months
    factor = (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    return (principal * factor).quantize(Decimal("0.01"))


def _rate_for_score(spec: dict, score: int) -> float:
    """Linjär interpolering av ränta utifrån score.

    Score >= 800 → bästa räntan. Score <= spec['min_score'] → sämsta.
    SMS-lån: även "bra" score får 30 % — det är inneboende högkostnad.
    """
    min_score = spec["min_score"]
    rate_low = spec["rate_at_max_score"]
    rate_high = spec["rate_at_min_score"]
    if score >= 800:
        return rate_low
    if score <= min_score:
        return rate_high
    # Lerp
    frac = (score - min_score) / (800 - min_score)
    return round(rate_high - (rate_high - rate_low) * frac, 4)


def _pick_lender(spec: dict, student_id: int, amount: int) -> str:
    """Deterministiskt val av bank baserat på elev + belopp."""
    import hashlib as _hl
    key = f"{student_id}-{amount}-{spec['label']}".encode()
    h = int(_hl.sha256(key).hexdigest()[:8], 16)
    return spec["lenders"][h % len(spec["lenders"])]


def _compute_uc_for_apply(
    scope_session: Session,
    student_id: int,
) -> "ScoreResult":  # noqa: F821 — typed via import inside func
    """Räkna fram aktuell UC-score för en elev. Reutiliserar
    bank.py:_compute_credit_for_student-logiken med v2-indata.
    """
    from ..school.credit_scoring import compute_score
    from ..db.models import PaymentReminder, ScheduledPayment

    late_payments = scope_session.query(PaymentReminder).count()
    reminders_high = (
        scope_session.query(PaymentReminder)
        .filter(PaymentReminder.reminder_no >= 3)
        .count()
    )
    failed_payments = (
        scope_session.query(ScheduledPayment)
        .filter(ScheduledPayment.status == "failed_no_funds")
        .count()
    )
    debt_total = Decimal("0")
    for L in scope_session.query(Loan).filter(Loan.active.is_(True)).all():
        debt_total += Decimal(L.principal_amount or 0)

    # Sparbuffer = (sparkonto + ISK) / snittutgifter senaste 3 mån
    savings_balance = Decimal("0")
    for acc in scope_session.query(Account).filter(
        Account.type.in_(("savings", "isk")),
    ).all():
        ob = acc.opening_balance or Decimal("0")
        from sqlalchemy import func as _sf
        mv = scope_session.query(
            _sf.coalesce(_sf.sum(Transaction.amount), 0),
        ).filter(Transaction.account_id == acc.id).scalar() or Decimal("0")
        savings_balance += ob + Decimal(str(mv))

    today = _date.today()
    cutoff = today - timedelta(days=90)
    from sqlalchemy import func as _sf2
    expenses = scope_session.query(
        _sf2.coalesce(_sf2.sum(Transaction.amount), 0),
    ).filter(
        Transaction.amount < 0,
        Transaction.date >= cutoff,
    ).scalar() or 0
    avg_monthly_expense = abs(Decimal(str(expenses))) / 3 or Decimal("1")
    savings_buffer_months = (
        float(savings_balance / avg_monthly_expense)
        if avg_monthly_expense > 0 else 0.0
    )

    # Master-DB: profil + employer-satisfaction + ålder
    with master_session() as ms:
        profile = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        from ..school.employer_models import EmployerSatisfaction
        sat = (
            ms.query(EmployerSatisfaction)
            .filter(EmployerSatisfaction.student_id == student_id)
            .first()
        )
        sat_score = sat.score if sat else 70

        gross_annual = (
            Decimal(profile.gross_salary_monthly * 12)
            if profile else Decimal("1")
        )
        debt_ratio = (
            float(debt_total / gross_annual) if gross_annual > 0 else 0.0
        )

        st = ms.get(Student, student_id)
        months_on_platform = 0
        if st and st.created_at:
            months_on_platform = (datetime.utcnow() - st.created_at).days // 30

        return compute_score(
            late_payments=late_payments,
            failed_payments=failed_payments,
            reminders_l3_or_higher=reminders_high,
            debt_ratio=debt_ratio,
            savings_buffer_months=savings_buffer_months,
            satisfaction_score=sat_score,
            months_on_platform=months_on_platform,
            age=profile.age if profile else None,
            monthly_net_income=(
                profile.net_salary_monthly if profile else None
            ),
            family_status=profile.family_status if profile else None,
            housing_type=profile.housing_type if profile else None,
        )


class V2LoanApplyRequest(BaseModel):
    loan_kind: LoanKind
    amount: float = Field(..., gt=0)
    term_months: int = Field(..., gt=0, le=600)
    purpose: Optional[str] = Field(None, max_length=200)
    debit_account_id: Optional[int] = None  # konto pengarna utbetalas till
    accept_offer: bool = Field(
        default=False,
        description=(
            "False = bara prövning, ingen Loan skapas. True = eleven "
            "har sett offerten och vill genomföra (skapar Loan + tx)."
        ),
    )


class V2WellbeingImpact(BaseModel):
    axis: str
    delta: int
    explanation: str


class V2LoanApplyResponse(BaseModel):
    application_id: int
    approved: bool
    decline_reason: Optional[str] = None
    loan_kind: str
    score: int
    grade: str
    score_components: dict
    kalp_passed: bool
    kalp_left_after_all: float
    offered_rate: Optional[float] = None
    offered_monthly_payment: Optional[float] = None
    offered_total_repay: Optional[float] = None
    lender: Optional[str] = None
    loan_id: Optional[int] = None
    wellbeing_impact: list[V2WellbeingImpact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@router.post("/lan/apply", response_model=V2LoanApplyResponse)
def post_loan_apply(
    body: V2LoanApplyRequest,
    info: TokenInfo = Depends(require_token),
) -> V2LoanApplyResponse:
    """Eleven ansöker själv om lån. Verklighetstrogen flöde:

    1. Validera att kind + belopp + löptid ligger inom verkliga ramar.
    2. Räkna UC-score (via samma formel som /bank/credit-score).
    3. Räkna KALP (Finansinspektionens stresstest 7 %).
    4. Beslut:
       - Beloppet utanför kind-ramar → avslag (för stort/litet/lång löptid)
       - SMS-lån: alltid godkänt men markerad high-cost; varningar
       - Andra: kräver score >= kind.min_score OCH KALP passed
    5. Om accept_offer=True OCH godkänd: skapa Loan + utbetalningstx +
       LoanScheduleEntry + wellbeing-delta + log_activity.
    6. Annars: bara CreditApplication-rad (audit) + score+ränta-info.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast elever kan ansöka om lån",
        )
    student_id = info.student_id

    spec = _LOAN_KIND_SPECS.get(body.loan_kind)
    if spec is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Okänd lånetyp: {body.loan_kind}",
        )

    amount_dec = Decimal(str(body.amount))
    warnings: list[str] = []

    # Hård validering av belopp + löptid (banken skulle aldrig gå med på
    # 5 mkr SMS-lån eller 10 års bolån, så avslå direkt här)
    if amount_dec < spec["min_amount"]:
        return _loan_apply_decline(
            student_id, body, spec,
            reason=(
                f"Minsta belopp för {spec['label']} är "
                f"{spec['min_amount']:,} kr".replace(",", " ")
            ),
        )
    if amount_dec > spec["max_amount"]:
        return _loan_apply_decline(
            student_id, body, spec,
            reason=(
                f"Högsta belopp för {spec['label']} är "
                f"{spec['max_amount']:,} kr".replace(",", " ")
            ),
        )
    if body.term_months < spec["min_term"]:
        return _loan_apply_decline(
            student_id, body, spec,
            reason=(
                f"Kortaste löptid för {spec['label']} är "
                f"{spec['min_term']} mån"
            ),
        )
    if body.term_months > spec["max_term"]:
        return _loan_apply_decline(
            student_id, body, spec,
            reason=(
                f"Längsta löptid för {spec['label']} är "
                f"{spec['max_term']} mån"
            ),
        )

    # Räkna UC + KALP
    with session_scope() as s:
        score_result = _compute_uc_for_apply(s, student_id)

        # KALP
        with master_session() as ms:
            profile = (
                ms.query(StudentProfile)
                .filter(StudentProfile.student_id == student_id)
                .first()
            )
            net_monthly = (
                Decimal(profile.net_salary_monthly or 0) if profile
                else Decimal("0")
            )
            housing = (
                Decimal(profile.housing_monthly or 0) if profile
                else Decimal("0")
            )
            family = profile.family_status if profile else "ensam"

        from ..loans.credit import compute_kalp
        kalp = compute_kalp(
            s,
            monthly_income_net=net_monthly,
            family_status=family,
            monthly_housing=housing,
            loan_amount=amount_dec,
            loan_term_months=body.term_months,
        )

        # Beslut
        offered_rate = _rate_for_score(spec, score_result.score)
        monthly_payment = _annuity_monthly(
            amount_dec, offered_rate, body.term_months,
        )
        total_repay = monthly_payment * body.term_months

        # SMS-lån: alltid godkänt (med varning); andra kräver UC + KALP
        is_sms = body.loan_kind == "smslan"
        approved: bool
        decline_reason: Optional[str] = None
        if is_sms:
            approved = True
            warnings.append(
                "VARNING: SMS-lån har effektiv årsränta över 30 %. "
                "Du betalar tillbaka mer än dubbla beloppet om du "
                "inte är försiktig."
            )
            if not kalp.passed:
                warnings.append(
                    "KALP visar att du inte har råd med betalningarna "
                    "— lånet godkänns ändå (SMS-banker kollar inte) "
                    "men du riskerar betalningsanmärkningar."
                )
        else:
            if score_result.score < spec["min_score"]:
                approved = False
                decline_reason = (
                    f"Din kreditscore är {score_result.score} "
                    f"(grad {score_result.grade}). "
                    f"{spec['label']} kräver minst {spec['min_score']} "
                    f"(grad {_grade_for_threshold(spec['min_score'])})."
                )
            elif not kalp.passed:
                approved = False
                decline_reason = (
                    "KALP-kalkylen visar att du inte har råd med "
                    "månadsbetalningen efter levnadskostnader. "
                    f"Du saknar {abs(int(kalp.monthly_left_after_all)):,} "
                    "kr/mån".replace(",", " ")
                )
            else:
                approved = True

        # Bolån: kontantinsats-info (varning men inte avslag)
        if body.loan_kind == "bolan" and approved:
            min_kontantinsats = float(amount_dec) * 0.15
            warnings.append(
                f"Bolån kräver normalt minst 15 % kontantinsats. "
                f"För detta belopp: minst "
                f"{int(min_kontantinsats):,} kr".replace(",", " ")
                + " (informativt — vi simulerar inte krav här)"
            )

        # Skapa CreditApplication-rad (audit alltid)
        application = CreditApplication(
            kind=body.loan_kind,
            requested_amount=amount_dec,
            requested_months=body.term_months,
            purpose=body.purpose,
            result="approved" if approved else "declined",
            score_value=score_result.score,
            decline_reason=decline_reason,
            simulated_lender=_pick_lender(
                spec, student_id, int(body.amount),
            ),
            offered_rate=offered_rate if approved else None,
            offered_monthly_payment=(
                monthly_payment if approved else None
            ),
            decided_at=datetime.utcnow(),
        )
        s.add(application)
        s.flush()

        loan_id: Optional[int] = None
        wb_impacts: list[V2WellbeingImpact] = []

        if approved and body.accept_offer:
            # Skapa Loan + utbetalningstx + schema
            loan = Loan(
                name=f"{spec['label']} · {application.simulated_lender}",
                lender=application.simulated_lender,
                principal_amount=amount_dec,
                start_date=_date.today(),
                interest_rate=offered_rate,
                binding_type="rörlig",
                amortization_monthly=monthly_payment,
                loan_kind=_map_kind_to_db(body.loan_kind),
                is_high_cost_credit=bool(spec.get("high_cost")),
                applied_at=datetime.utcnow(),
                score_at_application=score_result.score,
                active=True,
                notes=body.purpose,
            )
            s.add(loan)
            s.flush()
            application.resulting_loan_id = loan.id
            application.result = "accepted"

            # Utbetalningstransaktion (om kind har deposit + konto specat)
            if spec.get("deposit") and body.debit_account_id:
                acc = s.get(Account, body.debit_account_id)
                if acc is not None:
                    import hashlib as _hl_loan
                    tx_hash = _hl_loan.sha256(
                        f"loan-deposit|{loan.id}|{amount_dec}".encode(),
                    ).hexdigest()[:32]
                    deposit_tx = Transaction(
                        account_id=acc.id,
                        date=_date.today(),
                        amount=amount_dec,  # positivt
                        currency="SEK",
                        raw_description=(
                            f"Utbetalning {spec['label']} · "
                            f"{application.simulated_lender}"
                        ),
                        normalized_merchant=application.simulated_lender,
                        hash=tx_hash,
                        user_verified=True,
                    )
                    s.add(deposit_tx)

            # Schedule-rader för hela löptiden — en interest-rad +
            # en amortization-rad per månad (matcher räknar ihop dem
            # mot bankens transaktion automatiskt).
            from datetime import date as _ds
            today = _ds.today()
            balance = amount_dec
            monthly_rate = Decimal(str(offered_rate)) / Decimal("12")
            day_of_month = min(today.day, 28)
            for i in range(1, body.term_months + 1):
                # Beräkna förfallodag: samma dag i månad N
                total_months = today.month + i
                year = today.year + (total_months - 1) // 12
                month_n = (total_months - 1) % 12 + 1
                from datetime import date as _dt
                try:
                    due = _dt(year, month_n, day_of_month)
                except ValueError:
                    continue
                interest_amt = (
                    balance * monthly_rate
                ).quantize(Decimal("0.01"))
                amort_amt = (
                    monthly_payment - interest_amt
                ).quantize(Decimal("0.01"))
                if interest_amt > 0:
                    s.add(LoanScheduleEntry(
                        loan_id=loan.id, due_date=due,
                        amount=interest_amt, payment_type="interest",
                    ))
                if amort_amt > 0:
                    s.add(LoanScheduleEntry(
                        loan_id=loan.id, due_date=due,
                        amount=amort_amt, payment_type="amortization",
                    ))
                    balance -= amort_amt

            loan_id = loan.id

        s.commit()

    # === Wellbeing-deltas (master-DB) ===
    if approved:
        wb_spec = spec["wellbeing"]
        for axis in ("economy", "safety"):
            d = wb_spec.get(axis, 0)
            if d != 0:
                from ..game_engine.pentagon import apply_pentagon_delta
                apply_pentagon_delta(
                    student_id,
                    axis=axis,
                    requested_delta=d,
                    reason_kind="loan_applied",
                    reason_id=application.id,
                    reason_table="credit_applications",
                    explanation=(
                        f"{spec['label']} · "
                        f"{int(amount_dec):,} kr".replace(",", " ")
                    ),
                )
                wb_impacts.append(V2WellbeingImpact(
                    axis=axis, delta=d,
                    explanation=(
                        f"{spec['label']} påverkar {axis} med {d:+d}"
                    ),
                ))
    else:
        # Avslag → liten negativ economy (besviken) + safety -1 (osäkerhet)
        from ..game_engine.pentagon import apply_pentagon_delta
        apply_pentagon_delta(
            student_id, axis="economy", requested_delta=-1,
            reason_kind="loan_declined",
            reason_id=application.id,
            reason_table="credit_applications",
            explanation=f"Avslag på {spec['label']}",
        )

    # === Lärar-spårning ===
    from ..school.activity import log_activity
    if approved and body.accept_offer:
        log_activity(
            kind="loan.created",
            summary=(
                f"Tog {spec['label']} {int(amount_dec):,} kr · "
                f"{body.term_months} mån".replace(",", " ")
            ),
            payload={
                "loan_id": loan_id,
                "loan_kind": body.loan_kind,
                "amount": float(amount_dec),
                "term_months": body.term_months,
                "rate": offered_rate,
                "score": score_result.score,
                "lender": application.simulated_lender,
            },
        )
    elif approved:
        log_activity(
            kind="loan.offer_received",
            summary=(
                f"Fick offert på {spec['label']} {int(amount_dec):,} kr"
            ).replace(",", " "),
            payload={
                "application_id": application.id,
                "loan_kind": body.loan_kind,
                "score": score_result.score,
                "offered_rate": offered_rate,
            },
        )
    else:
        log_activity(
            kind="loan.declined",
            summary=(
                f"Avslag på {spec['label']} "
                f"{int(amount_dec):,} kr".replace(",", " ")
            ),
            payload={
                "application_id": application.id,
                "loan_kind": body.loan_kind,
                "score": score_result.score,
                "reason": decline_reason,
            },
        )

    return V2LoanApplyResponse(
        application_id=application.id,
        approved=approved,
        decline_reason=decline_reason,
        loan_kind=body.loan_kind,
        score=score_result.score,
        grade=score_result.grade,
        score_components=score_result.factors.get("_score_components", {}),
        kalp_passed=kalp.passed,
        kalp_left_after_all=float(kalp.monthly_left_after_all),
        offered_rate=offered_rate if approved else None,
        offered_monthly_payment=(
            float(monthly_payment) if approved else None
        ),
        offered_total_repay=(
            float(total_repay) if approved else None
        ),
        lender=application.simulated_lender if approved else None,
        loan_id=loan_id,
        wellbeing_impact=wb_impacts,
        warnings=warnings,
    )


def _grade_for_threshold(min_score: int) -> str:
    """Vilken grad krävs minst för en viss poängtröskel."""
    from ..school.credit_scoring import _grade_from_score
    return _grade_from_score(min_score)


def _map_kind_to_db(api_kind: str) -> str:
    """Mappa API-namn till Loan.loan_kind-enum."""
    return {
        "privatlan": "private",
        "billan": "car",
        "bolan": "mortgage",
        "smslan": "sms",
    }.get(api_kind, "other")


def _loan_apply_decline(
    student_id: int,
    body: V2LoanApplyRequest,
    spec: dict,
    *,
    reason: str,
) -> V2LoanApplyResponse:
    """Snabb-avslag (utan UC-räkning) för felaktiga indata."""
    with session_scope() as s:
        application = CreditApplication(
            kind=body.loan_kind,
            requested_amount=Decimal(str(body.amount)),
            requested_months=body.term_months,
            purpose=body.purpose,
            result="declined",
            decline_reason=reason,
            simulated_lender=_pick_lender(spec, student_id, int(body.amount)),
            decided_at=datetime.utcnow(),
        )
        s.add(application)
        s.commit()
        from ..school.activity import log_activity
        log_activity(
            kind="loan.declined",
            summary=f"Avslag {spec['label']} · {reason[:60]}",
            payload={
                "application_id": application.id,
                "loan_kind": body.loan_kind,
                "reason": reason,
            },
        )
        return V2LoanApplyResponse(
            application_id=application.id,
            approved=False,
            decline_reason=reason,
            loan_kind=body.loan_kind,
            score=0,
            grade="—",
            score_components={},
            kalp_passed=False,
            kalp_left_after_all=0.0,
            warnings=[],
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
                compute_credit_check(
                    s, annual_gross, student_id=student_id,
                )

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
    # SKV-2-fönster · fördröjt besked + utbetalningsvågar
    status: Optional[str] = None             # 'submitted' direkt efter
    besked_due_on: Optional[str] = None      # spel-datum för besked
    payout_wave: Optional[int] = None        # 1=april, 2=juni, 0=sen
    payout_due_on: Optional[str] = None      # spel-datum för utbetalning
    late_fee: Optional[float] = None         # 0 om i tid
    wave_message: Optional[str] = None       # pedagogisk klartext
    case_no: Optional[str] = None            # ärendenummer


# === Tidsfönster-gate (Skatteverket är inte alltid öppen) ===
#
# Skatteverket-aktören har EN deklarationsperiod per inkomstår, baserat
# på riktiga Skatteverkets kalender (jan-maj av året efter inkomståret).
# Eleven kan därmed inte "deklarera när som helst" — själva pedagogiken
# bygger på att deadlinen är fast.
#
# Alla `/v2/skatten/*`-POST-endpoints filtrerar via _gate_skatten_for_*
# och returnerar 403 (off-season/stängd) eller 409 (granska-läge ·
# inlämning ännu inte öppen).
#
# Helper finns i api/skatten_window.py.

class V2SkattenWindowOut(BaseModel):
    """Status för Skatteverket-fönstret för aktuell elev."""
    phase: Literal["off_season", "granska", "inlamna", "stangd"]
    tax_year: int
    can_read: bool
    submit_open: bool
    today_game: str
    opens_on: Optional[str]
    closes_on: Optional[str]
    description: str


def _gate_skatten_for_read(student_id: int) -> None:
    """Kasta 403 om eleven inte ens får titta på Skatteverket-aktören.
    Off-season (jan-1 mars) är aktören helt låst — pedagogiskt budskap:
    'kom tillbaka 2 mars'."""
    from .skatten_window import current_window_for_student
    state = current_window_for_student(student_id)
    if not state.can_read:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            (
                f"Skatteverket är låst tills 2 mars · {state.description} "
                f"Spel-datum just nu: {state.today_game.isoformat()}."
            ),
        )


def _gate_skatten_for_edit(student_id: int, *, action: str) -> None:
    """Tillåt redigering (avdrag, förslag) under granska + inlamna-fas.
    Blockar off-season och stängd. Eleven kan börja förbereda avdrag
    så snart granska öppnar 2 mars, men submit är fortfarande spärrad
    tills 17 mars (use `_gate_skatten_for_submit`).
    """
    from .skatten_window import current_window_for_student
    state = current_window_for_student(student_id)
    if state.phase == "off_season":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            (
                f"Du kan inte {action} ännu · Skatteverket öppnar "
                f"{state.opens_on.isoformat() if state.opens_on else '?'} "
                "(spel-tid)."
            ),
        )
    if state.phase == "stangd":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            (
                f"Deadline för {state.tax_year} har passerats (4 maj). "
                "Sen inlämning ger förseningsavgift och kräver kontakt "
                f"med Skatteverket. Aktören öppnar igen "
                f"{state.opens_on.isoformat() if state.opens_on else '?'}."
            ),
        )


def _gate_skatten_for_submit(student_id: int) -> None:
    """Bara fasen 'inlamna' (17 mars-4 maj) tillåter submit.
    Granska-läget får 409 med tydligt 'öppnar 17 mars'-budskap."""
    from .skatten_window import current_window_for_student
    state = current_window_for_student(student_id)
    if state.phase == "off_season":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            (
                f"Skatteverket öppnar 2 mars (granska-läge), inlämning "
                f"17 mars. Spel-datum just nu: "
                f"{state.today_game.isoformat()}."
            ),
        )
    if state.phase == "granska":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            (
                "Inlämningen öppnar 17 mars i spel-tid. Just nu är "
                "aktören i LÄS-/förbered-läge — granska förtryckta "
                "uppgifter och lägg till avdrag innan dess."
            ),
        )
    if state.phase == "stangd":
        # Sen inlämning · tillåt MEN flagga för förseningsavgift.
        # Vi kastar inte här — submit_tax_year-flödet lägger på
        # förseningsavgift istället så eleven får konkret konsekvens.
        return


@router.get("/skatten/window", response_model=V2SkattenWindowOut)
def get_skatten_window(
    info: TokenInfo = Depends(require_token),
) -> V2SkattenWindowOut:
    """Returnera nuvarande Skatteverket-fönsterstatus.

    Frontend hämtar detta vid mount av /v2/skatten för att rendera
    locked-view, granska-banner, eller normalt UI med inlämnings-knappen
    aktiverad.

    Lärare/demo: returnerar 'inlamna' med dagens datum så testning
    fungerar.
    """
    if info.role != "student" or info.student_id is None:
        # Lärar-/demo-läge: bypass fönstret · alltid 'inlamna' så lärare
        # kan visa flödet i sin demo.
        from datetime import date as _d
        return V2SkattenWindowOut(
            phase="inlamna",
            tax_year=_d.today().year - 1,
            can_read=True,
            submit_open=True,
            today_game=_d.today().isoformat(),
            opens_on=None,
            closes_on=None,
            description="Lärar-/demo-läge · alltid öppet.",
        )
    from .skatten_window import current_window_for_student
    state = current_window_for_student(info.student_id)
    return V2SkattenWindowOut(
        phase=state.phase,
        tax_year=state.tax_year,
        can_read=state.can_read,
        submit_open=state.submit_open,
        today_game=state.today_game.isoformat(),
        opens_on=state.opens_on.isoformat() if state.opens_on else None,
        closes_on=state.closes_on.isoformat() if state.closes_on else None,
        description=state.description,
    )


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
    # Avdrag får läggas till under granska + inlämna-fasen — INTE
    # off-season eller efter stängning. Eleven måste alltså vänta
    # till 2 mars för att börja skriva.
    _gate_skatten_for_edit(
        info.student_id, action="lägga till avdrag",
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
    _gate_skatten_for_edit(info.student_id, action="ta bort avdrag")
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
    _gate_skatten_for_edit(info.student_id, action="besluta om förslag")
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

    Bug #11 · efter submit körs Rudolf-AI (Skatteverkets handläggare)
    via separat endpoint /v2/skatten/rudolf-review som granskar
    avdragen och returnerar GODKÄND eller AVSLAG med motivering.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elev")

    # Skatteverket-fönster · submit får bara ske i inlamna-fasen,
    # eller efter stängning (då med förseningsavgift). Off-season +
    # granska blockas med 403/409.
    _gate_skatten_for_submit(info.student_id)

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

    # Submit + setup pipelinen i samma transaktion så besked_due_on
    # m.fl. fält commits atomiskt.
    from ..business.game_clock import current_game_date_for_student
    today_game = current_game_date_for_student(info.student_id)
    from .skatten_pipeline import setup_after_submit
    with session_scope() as s:
        ret = submit_tax_year(s, year, gross_monthly, tax_rate)
        pipeline_info = setup_after_submit(
            s, tax_return=ret, today_game=today_game,
        )

    # Pentagon-koppling · skattedeklaration är ett ekonomi-event.
    # +3 economy bara för att lämna in i tid; diff > 0 (kvarskatt) ger
    # en liten extra penalty på safety, diff < 0 (återbäring) ger bonus.
    try:
        from ..game_engine.pentagon import apply_pentagon_delta
        apply_pentagon_delta(
            info.student_id,
            axis="economy",
            requested_delta=3,
            reason_kind="decision",
            reason_id=ret.id,
            reason_table="tax_year_returns",
            explanation=f"deklaration {ret.year} inlämnad",
            year_month=f"{ret.year}-04",
        )
        if float(ret.diff) > 5000:
            apply_pentagon_delta(
                info.student_id,
                axis="safety",
                requested_delta=-2,
                reason_kind="decision",
                reason_id=ret.id,
                reason_table="tax_year_returns",
                explanation=(
                    f"kvarskatt {int(ret.diff)} kr — "
                    f"oväntad utgift som påverkar trygghet"
                ),
                year_month=f"{ret.year}-04",
            )
        elif float(ret.diff) < -3000:
            apply_pentagon_delta(
                info.student_id,
                axis="economy",
                requested_delta=2,
                reason_kind="decision",
                reason_id=ret.id,
                reason_table="tax_year_returns",
                explanation=(
                    f"skatteåterbäring {int(-ret.diff)} kr"
                ),
                year_month=f"{ret.year}-04",
            )
    except Exception:
        # Pentagon-loggning får inte bryta inlämning
        pass

    return V2TaxSubmitResponse(
        return_id=ret.id,
        year=ret.year,
        submitted_at=ret.submitted_at,
        locked=ret.locked,
        final_tax=float(ret.final_tax),
        diff=float(ret.diff),
        status=pipeline_info.get("status"),
        besked_due_on=pipeline_info.get("besked_due_on"),
        payout_wave=pipeline_info.get("payout_wave"),
        payout_due_on=pipeline_info.get("payout_due_on"),
        late_fee=pipeline_info.get("late_fee"),
        wave_message=pipeline_info.get("wave_message"),
        case_no=pipeline_info.get("case_no"),
    )


# Bug #11 · Rudolf-AI · Skatteverkets handläggare granskar deklarationen
class RudolfReviewIn(BaseModel):
    year: int


class RudolfReviewOut(BaseModel):
    verdict: Literal["godkand", "avslag", "kontroll"]
    rudolf_message: str
    flagged_deductions: list[dict] = []
    score: int  # 0-100, hur trovärdig deklarationen är
    next_steps: list[str] = []


@router.post("/skatten/rudolf-review", response_model=RudolfReviewOut)
def rudolf_review(
    body: RudolfReviewIn,
    info: TokenInfo = Depends(require_token),
) -> RudolfReviewOut:
    """Rudolf — Skatteverkets handläggare — granskar elevens deklaration.

    Deterministisk (ingen LLM krävs) regelmotor som flaggar:
    - Avdrag > 25 000 kr utan beskrivning
    - Avdrag-summa > 30 % av brutto-årslön
    - Resemål-avdrag på orealistiska sträckor
    - Hemarbetsdagar > 220
    - Helt saknade avdrag trots > 50k brutto

    Returnerar verdict + Rudolf-message + flagged_deductions + score.
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
        annual_gross = (
            int(profile.gross_salary_monthly) * 12
            if profile.gross_salary_monthly else 0
        )

    flags: list[dict] = []
    score = 100
    next_steps: list[str] = []

    with session_scope() as s:
        deductions = (
            s.query(TaxDeduction)
            .filter(TaxDeduction.year == body.year)
            .all()
        )
        total_deductions = sum(
            int(d.amount or 0) for d in deductions
        )

        for d in deductions:
            amt = int(d.amount or 0)
            if amt > 25000 and not (d.description or "").strip():
                flags.append({
                    "deduction_id": d.id,
                    "category": d.category,
                    "amount": amt,
                    "reason": "Stort avdrag utan beskrivning",
                })
                score -= 10
            if amt > 50000:
                flags.append({
                    "deduction_id": d.id,
                    "category": d.category,
                    "amount": amt,
                    "reason": "Mycket stort avdrag — kan kräva underlag",
                })
                score -= 5

        if annual_gross > 0 and total_deductions > annual_gross * 0.30:
            flags.append({
                "category": "TOTALT",
                "amount": total_deductions,
                "reason": (
                    f"Avdrag-summa {total_deductions:,} kr är "
                    f"{int(total_deductions / annual_gross * 100)}% av "
                    f"brutto-lön — Skatteverket granskar normalt > 30%"
                ).replace(",", " "),
            })
            score -= 25
            next_steps.append(
                "Kontrollera att alla avdrag har kvitto/bilaga."
            )

        if not deductions and annual_gross > 600_000:
            score -= 5
            next_steps.append(
                "Hög lön utan avdrag — har du missat reseavdrag eller "
                "fackavgift?"
            )

    score = max(0, min(100, score))

    if len(flags) >= 3 or score < 50:
        verdict = "avslag"
        msg = (
            f"Hej, det här är Rudolf på Skatteverket. Jag har granskat "
            f"din deklaration och hittade {len(flags)} punkter som inte "
            f"stämmer. Trovärdighetsbedömning: {score}/100. Du behöver "
            f"komplettera eller justera innan jag kan godkänna."
        )
        next_steps.insert(
            0, "Gå igenom flaggade avdrag och korrigera eller ta bort dem.",
        )
    elif len(flags) >= 1 or score < 80:
        verdict = "kontroll"
        msg = (
            f"Hej, det här är Rudolf. Deklarationen ser i huvudsak OK ut "
            f"men jag har {len(flags)} punkt(er) som behöver verifieras. "
            f"Score: {score}/100. Tillsänd underlag inom 30 dagar så "
            f"avslutar vi ärendet."
        )
    else:
        verdict = "godkand"
        msg = (
            f"Hej, det här är Rudolf på Skatteverket. Din deklaration är "
            f"GODKÄND utan anmärkningar. Score: {score}/100. Eventuell "
            f"återbäring/kvarskatt visas i ditt slutskattebesked."
        )

    return RudolfReviewOut(
        verdict=verdict,
        rudolf_message=msg,
        flagged_deductions=flags,
        score=score,
        next_steps=next_steps,
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

            # Skadehändelser (12 senaste spel-mån) · bara redan inträffade
            # händelser. Tidigare användes _d_ic.today() (= maj 7 real-tid)
            # vilket dels betyder att 12 mån bakåt är fel period (jämfört
            # med spel-tid jan), dels att framtida seedade events (t.ex.
            # 'Bilen behöver reparation 6 jan' när eleven är på Jan 2)
            # syntes innan spel-dagen passerats.
            from datetime import timedelta as _td_ic
            from ..business.game_clock import current_game_date as _cgd_ic
            today_game = _cgd_ic()
            cutoff = today_game - _td_ic(days=365)
            claim_rows = (
                s.query(InsuranceClaim)
                .filter(
                    InsuranceClaim.occurred_on >= cutoff,
                    InsuranceClaim.occurred_on <= today_game,
                )
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
        "bostadsrattsforsakring", "bilforsakring", "djur",
        "frisktandvard",
        "ovrig",
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

        # Pentagon-koppling · att teckna en aktiv försäkring höjer trygghet.
        if body.status == "active":
            try:
                from ..game_engine.pentagon import apply_pentagon_delta
                apply_pentagon_delta(
                    info.student_id,
                    axis="safety",
                    requested_delta=2,
                    reason_kind="decision",
                    reason_id=p.id,
                    reason_table="insurance_policies",
                    explanation=f"tecknade {p.name} ({p.kind})",
                )
            except Exception:
                pass

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


# === Frisktandvård-offert (SKV-4) ===

class V2FrisktandvardOffer(BaseModel):
    """Personlig offert för frisktandvård baserad på elevens tier.

    Vid karaktärsskapande sätts elevens tier 1-10 i StudentProfile
    baserat på simulerad tandhälsa. Den här endpointen returnerar
    den faktiska premien (justerad för ålder · ATB/normal) så
    eleven kan se det riktiga priset INNAN hen tecknar avtalet.

    Saknas tier i profilen (gammal data) → returnera default grupp 4.
    """
    tier: int                  # 1-10
    age_category: str          # 'atb' (20-23 eller 67+) | 'normal'
    premium_monthly: int       # kr/mån
    explanation: str           # pedagogisk klartext
    # Hela pristabellen så UI kan visa "din grupp vs övriga"
    tier_prices_atb: dict[int, int]
    tier_prices_normal: dict[int, int]
    already_active: bool       # om policy redan finns


@router.get(
    "/forsakringar/frisktandvard-offert",
    response_model=V2FrisktandvardOffer,
)
def get_frisktandvard_offer(
    info: TokenInfo = Depends(require_token),
) -> V2FrisktandvardOffer:
    """Hämta elevens personliga frisktandvård-offert.

    Pris baseras på elevens tier (slumpat vid karaktärsskapande från
    simulerad tandhälsa) och ålders-kategori (ATB-rabatt för
    20-23 år och 67+).
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Endast elev",
        )

    from ..game_engine.profile_generator.dental_picker import (
        PREMIUM_WITH_ATB, PREMIUM_NORMAL, _is_atb_age,
    )
    from ..school.models import StudentProfile

    # Default · grupp 4 normalpris om saknas
    tier = 4
    age = 30
    age_cat = "normal"
    with master_session() as ms:
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == info.student_id)
            .first()
        )
        if prof is not None:
            age = int(getattr(prof, "age", 30) or 30)
            saved_tier = getattr(prof, "frisktandvard_tier", None)
            if saved_tier is not None:
                tier = int(saved_tier)
            saved_cat = getattr(prof, "frisktandvard_age_category", None)
            if saved_cat:
                age_cat = saved_cat
            else:
                age_cat = "atb" if _is_atb_age(age) else "normal"

    premium = (
        PREMIUM_WITH_ATB[tier] if age_cat == "atb"
        else PREMIUM_NORMAL[tier]
    )

    # Kollar om eleven redan har aktiv policy
    already_active = False
    with session_scope() as s:
        existing = (
            s.query(InsurancePolicy)
            .filter(
                InsurancePolicy.kind == "frisktandvard",
                InsurancePolicy.status == "active",
            )
            .first()
        )
        if existing is not None:
            already_active = True

    if age_cat == "atb":
        cat_explain = (
            "Du får ATB-rabatt (Allmänt tandvårdsbidrag) eftersom du "
            "är 20-23 år eller 67+. Lägre premie än vanligt."
        )
    else:
        cat_explain = (
            "Du betalar normalpris (24-66 år). ATB-rabatt gäller bara "
            "för 20-23 år och 67+."
        )

    explanation = (
        f"Din senaste tandkontroll placerade dig i prisgrupp {tier}. "
        f"{cat_explain}\n\n"
        f"Det här ger en månadspremie på {premium} kr (autogiro). "
        "Avtalet täcker all tandvård (kontroll, lagning, rotfyllning, "
        "tandstensborttagning) hos Folktandvården i 3 år. "
        "Vid avtalsslut görs ny kontroll och du kan hamna i annan grupp."
    )

    return V2FrisktandvardOffer(
        tier=tier,
        age_category=age_cat,
        premium_monthly=premium,
        explanation=explanation,
        tier_prices_atb=dict(PREMIUM_WITH_ATB),
        tier_prices_normal=dict(PREMIUM_NORMAL),
        already_active=already_active,
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

        # Pentagon-koppling · försäkrings-status-byten
        try:
            from ..game_engine.pentagon import apply_pentagon_delta
            if old_status != "active" and body.status == "active":
                apply_pentagon_delta(
                    info.student_id,
                    axis="safety",
                    requested_delta=2,
                    reason_kind="decision",
                    reason_id=p.id,
                    reason_table="insurance_policies",
                    explanation=f"aktiverade {p.name} ({p.kind})",
                )
            elif old_status == "active" and body.status == "cancelled":
                apply_pentagon_delta(
                    info.student_id,
                    axis="safety",
                    requested_delta=-3,
                    reason_kind="decision",
                    reason_id=p.id,
                    reason_table="insurance_policies",
                    explanation=(
                        f"avslutade {p.name} — minskat skyddsnät"
                    ),
                )
        except Exception:
            pass

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
        # Spel-tid · annars filtreras readings ut för att de ligger
        # i jan 2025-26 medan today=maj 2026 (cutoff=maj 2025).
        from ..business.game_clock import current_game_date as _cgd_uti
        today_game = _cgd_uti()
        soon = today_game + _td(days=30)
        expiring = sum(
            1 for u in active
            if u.binding_end is not None and u.binding_end <= soon
        )

        # Senaste 12 mån utility readings (spel-tid)
        cutoff = today_game - _td(days=365)
        readings = (
            s.query(UtilityReading)
            .filter(UtilityReading.period_end >= cutoff)
            .order_by(
                UtilityReading.period_end.desc(),
                UtilityReading.id.desc(),
            )
            .all()
        )

        # Senaste månadens kostnad + kWh (spel-tid)
        last30 = today_game - _td(days=45)
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
        old_isk = float(a.custom_isk_monthly or 0)
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

        # Pentagon-koppling · höjt månatligt eget pensionssparande är ett
        # ekonomi-positivt long-term-event. Sänkning är inte negativt
        # (eleven kan ha goda skäl), så bara höjning ger delta.
        try:
            new_isk = float(a.custom_isk_monthly or 0)
            if body.custom_isk_monthly is not None and new_isk > old_isk + 200:
                from ..game_engine.pentagon import apply_pentagon_delta
                # Skala efter storleken på höjningen, men cap vid +3.
                bump = min(3, max(1, int((new_isk - old_isk) // 500)))
                apply_pentagon_delta(
                    info.student_id,
                    axis="economy",
                    requested_delta=bump,
                    reason_kind="decision",
                    reason_table="pension_assumptions",
                    explanation=(
                        f"höjt eget pensionssparande "
                        f"{int(old_isk)} → {int(new_isk)} kr/mån"
                    ),
                )
        except Exception:
            pass

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
        .filter(_released_filter(Transaction))
        .scalar()
    )
    return base + Decimal(str(total or 0))


class V2FundBuyRequest(BaseModel):
    """Eleven köper en fond · cash dras från konto, FundHolding skapas/ökar."""
    account_id: int
    fund_name: str = Field(..., min_length=1, max_length=200)
    amount: float = Field(..., gt=0)


class V2FundBuyResponse(BaseModel):
    fund_holding_id: int
    fund_name: str
    new_market_value: float
    cash_remaining: float


@router.post("/avanza/fund-buy", response_model=V2FundBuyResponse)
def buy_fund(
    body: V2FundBuyRequest,
    info: TokenInfo = Depends(require_token),
) -> V2FundBuyResponse:
    """Eleven köper fond på ISK/sparkonto · skapar Transaction (negativt
    cash) + ökar/skapar FundHolding-rad. Pedagogiskt: cash försvinner,
    market_value växer — totalvärdet är samma direkt efter köp."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(403, "Endast elever")

    with session_scope() as s:
        acc = s.get(Account, body.account_id)
        if acc is None:
            raise HTTPException(404, "Kontot hittades inte")
        if acc.type not in ("isk", "savings", "checking"):
            raise HTTPException(
                400, f"Kan inte köpa fonder från konto-typ {acc.type}",
            )

        amount = Decimal(str(body.amount))
        cash = _isk_cash_balance(s, acc.id)
        # Cash check (för ISK/sparkonto), men inte för checking
        # eftersom användaren kan välja att gå minus där
        if acc.type in ("isk", "savings") and cash < amount:
            raise HTTPException(
                400,
                f"Inte tillräckligt med cash på {acc.name}: "
                f"{int(cash)} kr (försökte köpa för {int(amount)} kr).",
            )

        today = _date.today()
        idem = (
            f"v2-fund-buy-{acc.id}-{body.fund_name[:40]}-"
            f"{today.isoformat()}-{amount}"
        )
        existing_tx = (
            s.query(Transaction)
            .filter(Transaction.hash == idem)
            .first()
        )
        if existing_tx is not None:
            holding = (
                s.query(FundHolding)
                .filter(
                    FundHolding.account_id == acc.id,
                    FundHolding.fund_name == body.fund_name,
                )
                .first()
            )
            return V2FundBuyResponse(
                fund_holding_id=holding.id if holding else 0,
                fund_name=body.fund_name,
                new_market_value=float(
                    holding.market_value if holding else 0,
                ),
                cash_remaining=float(cash),
            )

        # 1. Cash-uttag · markera som transfer (kapital-omflyttning,
        # inte konsumtion) så hub inte räknar fond-köp som utgift.
        tx = Transaction(
            account_id=acc.id,
            date=today,
            amount=-amount,
            raw_description=f"Köp fond · {body.fund_name}",
            user_verified=True,
            is_transfer=True,
            hash=idem,
        )
        s.add(tx)
        s.flush()

        # 2. Öka eller skapa FundHolding
        holding = (
            s.query(FundHolding)
            .filter(
                FundHolding.account_id == acc.id,
                FundHolding.fund_name == body.fund_name,
            )
            .first()
        )
        if holding is None:
            holding = FundHolding(
                account_id=acc.id,
                fund_name=body.fund_name,
                market_value=amount,
                units=Decimal("1.0"),  # placeholder · kurs uppdateras nattligen
            )
            s.add(holding)
        else:
            holding.market_value = (
                Decimal(str(holding.market_value or 0)) + amount
            )
            if holding.units is not None:
                holding.units = Decimal(str(holding.units)) + Decimal("1.0")
        s.flush()

        return V2FundBuyResponse(
            fund_holding_id=holding.id,
            fund_name=holding.fund_name,
            new_market_value=float(holding.market_value),
            cash_remaining=float(cash - amount),
        )


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
    # Synthetic category-namn för system-tx som saknar Category-rad
    # men ändå är 'klassificerade' (transfers, lön, pension-spar).
    cat_name: Optional[str] = None
    if t.category_id is not None:
        cat_name = cats_by_id.get(t.category_id)
    elif bool(getattr(t, "is_transfer", False)):
        desc = (t.raw_description or "").lower()
        if "pension-spar" in desc:
            cat_name = "Pension-sparande"
        else:
            cat_name = "Överföring"
    else:
        desc = (t.raw_description or "").lower()
        if desc.startswith("lön ") or " · lön " in desc:
            cat_name = "Lön"
    return V2BookkeepingTxRow(
        id=t.id,
        date=t.date,
        account_id=t.account_id,
        account_name=accounts_by_id.get(t.account_id, "—"),
        amount=float(t.amount),
        raw_description=t.raw_description,
        normalized_merchant=t.normalized_merchant,
        category_id=t.category_id,
        category_name=cat_name,
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
        # Filtrera på released_at så pending realtid-projektion inte
        # smyger in i bokföringen innan den är synlig i banken.
        txs_query = (
            s.query(Transaction)
            .filter(_released_filter(Transaction))
            .filter(Transaction.date >= period_start)
            .filter(Transaction.date <= period_end)
        )
        all_txs = txs_query.all()
        total = len(all_txs)
        # Transfers (mellan egna konton, pension-spar, lön-utbetalning)
        # räknas som självklassificerade — eleven behöver inte
        # manuellt klassa dem. is_transfer=True OR description som
        # innehåller 'Lön ' (lönen från arbetsgivaren) räknas som
        # auto-klassificerade så de hamnar inte i ovettade-listan.
        def _is_auto_class(t) -> bool:
            if t.category_id is not None:
                return True
            if bool(getattr(t, "is_transfer", False)):
                return True
            desc = (t.raw_description or "").lower()
            if desc.startswith("lön ") or " · lön " in desc:
                return True
            if "pension-spar" in desc:
                return True
            return False

        unclassified_txs = [t for t in all_txs if not _is_auto_class(t)]
        classified_txs = [t for t in all_txs if _is_auto_class(t)]
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
        # Hitta unclassified — endast bland synliga transaktioner
        # (realtid-projektion: pending tx släpps inte för klassning än).
        q = (
            s.query(Transaction)
            .filter(Transaction.category_id.is_(None))
            .filter(_released_filter(Transaction))
        )
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
    confirm_token: Optional[str] = None  # för QR-länken
    student_id: Optional[int] = None  # för QR-URL ?sid=N


class V2BankIDStartIn(BaseModel):
    upcoming_ids: list[int]


@router.post("/bankid/sessions", response_model=V2BankIDSessionOut)
def start_bankid_session(
    body: V2BankIDStartIn,
    info: TokenInfo = Depends(require_token),
) -> V2BankIDSessionOut:
    """Skapa ny signerings-session från lista av upcoming-IDs.

    Sätter ett confirm_token (32 tecken url-safe) som används av
    mobil-confirm-endpoint POST /v2/bankid/confirm/{token}. Token
    visas via QR-koden på desktop · scannas med mobil → mobil PIN-form.
    Samma security-modell som v1 BankSession.token.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    if not body.upcoming_ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Minst 1 faktura krävs",
        )

    import secrets as _sec
    confirm_token = _sec.token_urlsafe(24)

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
            confirm_token=confirm_token,
            student_id_for_confirm=info.student_id,
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
        confirm_token=sess.confirm_token,
        student_id=sess.student_id_for_confirm,
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
    pin: Optional[str] = None  # 4-siffrig pin · krävs för signering


class V2BankIDPinStatus(BaseModel):
    has_pin: bool


@router.get("/bankid/pin-status", response_model=V2BankIDPinStatus)
def get_bankid_pin_status(
    info: TokenInfo = Depends(require_token),
) -> V2BankIDPinStatus:
    """Kollar om eleven har satt sin 4-siffriga BankID-PIN."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    with master_session() as mdb:
        st = mdb.get(Student, info.student_id)
        if st is None:
            raise HTTPException(404, "Student saknas")
        return V2BankIDPinStatus(has_pin=bool(st.bank_pin_hash))


class V2SetPinRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=4)


@router.post("/bankid/set-pin")
def set_bankid_pin(
    body: V2SetPinRequest,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Eleven sätter sin 4-siffriga BankID-PIN.

    Pedagogiskt: PIN är 'något du vet' som binder dig till sessionen.
    Återanvänder bank_pin_hash från master-DB (samma som v1 BankID).
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")
    import re as _re_pin
    if not _re_pin.match(r"^\d{4}$", body.pin):
        raise HTTPException(400, "PIN måste vara exakt 4 siffror")
    from ..security.crypto import hash_password
    with master_session() as mdb:
        st = mdb.get(Student, info.student_id)
        if st is None:
            raise HTTPException(404, "Student saknas")
        st.bank_pin_hash = hash_password(body.pin)
        mdb.commit()
        return {"ok": True}


@router.post(
    "/bankid/sessions/{session_id}/sign",
    response_model=V2BankIDSessionOut,
)
def sign_bankid_session(
    session_id: int,
    body: V2BankIDSignIn,
    info: TokenInfo = Depends(require_token),
) -> V2BankIDSessionOut:
    """Eleven signerar — markerar fakturor autogiro=True.

    PIN-verifiering · graceful:
    - Om eleven har satt PIN → kräv korrekt PIN i body (matchas mot
      Student.bank_pin_hash, samma security-modell som v1 BankID).
    - Om eleven inte har PIN → tillåt signering utan (första-gång-
      flow eller bakåtkompat). Frontend triggar set-pin först om
      pin-status=false.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Endast elever")

    from ..security.crypto import verify_password as _vp
    with master_session() as mdb:
        st = mdb.get(Student, info.student_id)
        if st is not None and st.bank_pin_hash:
            # Eleven har en PIN → kräv den
            if (
                not body.pin
                or len(body.pin) != 4
                or not body.pin.isdigit()
            ):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "PIN måste vara exakt 4 siffror",
                )
            if not _vp(st.bank_pin_hash, body.pin):
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED,
                    "Fel PIN",
                )

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


# === MOBIL-CONFIRM-FLÖDET (no auth · token-baserad) ===
# Eleven scannar QR-koden på desktop med mobilen → mobil hamnar på
# /v2/bankid/confirm/:token → POST hit med PIN för att bekräfta
# sessionen. Samma security-modell som v1 /bank/session/{token}/confirm.

class V2BankIDConfirmInfo(BaseModel):
    """Info om sessionen som mobilen visar innan PIN-prompt."""
    session_id: int
    invoice_count: int
    total_amount: float
    status: Literal["pending", "signed", "cancelled"]
    invoices: list[V2BankIDInvoiceRow]
    has_pin: bool


@router.get(
    "/bankid/confirm-info/{token}",
    response_model=V2BankIDConfirmInfo,
)
def get_bankid_confirm_info(
    token: str, sid: Optional[int] = None,
) -> V2BankIDConfirmInfo:
    """Mobilen hämtar sammanfattning av sessionen via token.

    INTE authenticated · samma som v1 /bank/session/{token}/confirm.
    Token + bankid_session-rad räcker som security (session_id_for_confirm
    binder den till student vars PIN behövs).
    """
    # Måste söka utanför scope-context eftersom mobilen inte är inloggad
    # som elev. Vi joinar via student_id_for_confirm + tenant_id för att
    # hitta sessionen oavsett scope.
    from sqlalchemy import or_ as _or
    from ..school.engines import (
        master_session as _ms_local,
        get_scope_session as _gss,
        scope_for_student as _sfs,
        scope_context as _sctx,
    )
    from ..school.models import Student as _Stu

    # Steg 1: hitta vilken student tokenen tillhör.
    # Optimerat: om sid-query-param skickas (från QR-koden) slår vi
    # direkt mot den scopen istället för att loopa alla. Tidigare
    # loop-implementation var O(n_students × scope-DB-queries) vilket
    # gjorde att mobilen timeoutade på instanser med många elever.
    with _ms_local() as mdb:
        if sid is not None:
            students = mdb.query(_Stu).filter(
                _Stu.id == sid, _Stu.active.is_(True),
            ).all()
        else:
            students = mdb.query(_Stu).filter(_Stu.active.is_(True)).all()
        target_sid: Optional[int] = None
        target_session: Optional[BankIDSession] = None
        for stu in students:
            scope_key = _sfs(stu)
            try:
                with _sctx(scope_key):
                    with _gss(scope_key)() as ss:
                        sess = (
                            ss.query(BankIDSession)
                            .filter(
                                BankIDSession.confirm_token == token,
                            )
                            .first()
                        )
                        if sess is not None:
                            target_sid = stu.id
                            # Hämta upcoming inom samma session-context
                            ups = (
                                ss.query(UpcomingTransaction)
                                .filter(
                                    UpcomingTransaction.id.in_(
                                        sess.upcoming_ids or [],
                                    ),
                                )
                                .all()
                            )
                            target_session = sess
                            invoices_out = [
                                V2BankIDInvoiceRow(
                                    upcoming_id=u.id,
                                    name=u.name or "Faktura",
                                    amount=float(u.amount or 0),
                                    due_date=u.expected_date,
                                    is_recurring=bool(u.recurring_monthly),
                                    is_anomaly=False,
                                )
                                for u in ups
                            ]
                            sess_status = sess.status
                            sess_id = sess.id
                            sess_count = sess.invoice_count
                            sess_total = float(sess.total_amount)
                            break
            except Exception:
                continue

        if target_session is None or target_sid is None:
            raise HTTPException(404, "Sessionen hittades inte")

        st = mdb.get(_Stu, target_sid)
        has_pin = bool(st and st.bank_pin_hash)

    return V2BankIDConfirmInfo(
        session_id=sess_id,
        invoice_count=sess_count,
        total_amount=sess_total,
        status=sess_status,  # type: ignore[arg-type]
        invoices=invoices_out,
        has_pin=has_pin,
    )


class V2BankIDConfirmIn(BaseModel):
    pin: str = Field(..., min_length=4, max_length=4)


@router.post("/bankid/confirm-info/{token}", response_model=V2BankIDConfirmInfo)
def post_bankid_confirm(
    token: str,
    body: V2BankIDConfirmIn,
    sid: Optional[int] = None,
) -> V2BankIDConfirmInfo:
    """Mobilen bekräftar sessionen genom att ange PIN.

    INTE authenticated. Token bundlar sig till en specifik elev (via
    student_id_for_confirm), PIN matchas mot Student.bank_pin_hash.
    Samma security-modell som v1 /bank/session/{token}/confirm.

    Vid lyckad confirm: session.status='signed', alla relaterade
    UpcomingTransactions sätts till autogiro=True. Desktop-vyn pollar
    GET /v2/bankid/sessions/{id} och ser uppdateringen.
    """
    if not body.pin or len(body.pin) != 4 or not body.pin.isdigit():
        raise HTTPException(400, "PIN måste vara exakt 4 siffror")

    from ..security.crypto import verify_password as _vp
    from ..school.engines import (
        master_session as _ms_local,
        get_scope_session as _gss,
        scope_for_student as _sfs,
        scope_context as _sctx,
    )
    from ..school.models import Student as _Stu

    with _ms_local() as mdb:
        # Optimerat: om sid-query-param finns, hoppa loop:en
        if sid is not None:
            students = mdb.query(_Stu).filter(
                _Stu.id == sid, _Stu.active.is_(True),
            ).all()
        else:
            students = mdb.query(_Stu).filter(_Stu.active.is_(True)).all()
        target_sid: Optional[int] = None
        target_session_data: Optional[dict] = None
        for stu in students:
            scope_key = _sfs(stu)
            try:
                with _sctx(scope_key):
                    with _gss(scope_key)() as ss:
                        sess = (
                            ss.query(BankIDSession)
                            .filter(
                                BankIDSession.confirm_token == token,
                            )
                            .first()
                        )
                        if sess is None:
                            continue
                        target_sid = stu.id
                        if sess.status != "pending":
                            raise HTTPException(
                                400,
                                f"Sessionen är {sess.status}",
                            )

                        # Verifiera PIN mot master-DB
                        st = mdb.get(_Stu, target_sid)
                        if st is None or not st.bank_pin_hash:
                            raise HTTPException(
                                400,
                                "Du har inte satt en BankID-PIN. "
                                "Sätt en i banken först.",
                            )
                        if not _vp(st.bank_pin_hash, body.pin):
                            raise HTTPException(401, "Fel PIN")

                        # Signera sessionen + sätt autogiro på upcoming
                        sess.status = "signed"
                        sess.signed_at = datetime.utcnow()
                        sess.current_step = 6
                        ups = (
                            ss.query(UpcomingTransaction)
                            .filter(
                                UpcomingTransaction.id.in_(
                                    sess.upcoming_ids or [],
                                ),
                            )
                            .all()
                        )
                        for u in ups:
                            if hasattr(u, "autogiro"):
                                u.autogiro = True
                        ss.flush()
                        ss.commit()

                        invoices_out = [
                            V2BankIDInvoiceRow(
                                upcoming_id=u.id,
                                name=u.name or "Faktura",
                                amount=float(u.amount or 0),
                                due_date=u.expected_date,
                                is_recurring=bool(u.recurring_monthly),
                                is_anomaly=False,
                            )
                            for u in ups
                        ]
                        target_session_data = {
                            "id": sess.id,
                            "status": sess.status,
                            "count": sess.invoice_count,
                            "total": float(sess.total_amount),
                            "invoices": invoices_out,
                        }
                        break
            except HTTPException:
                raise
            except Exception:
                continue

        if target_session_data is None:
            raise HTTPException(404, "Sessionen hittades inte")

    return V2BankIDConfirmInfo(
        session_id=target_session_data["id"],
        invoice_count=target_session_data["count"],
        total_amount=target_session_data["total"],
        status=target_session_data["status"],
        invoices=target_session_data["invoices"],
        has_pin=True,
    )



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
                .filter(_released_filter(Transaction))
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
                .filter(_released_filter(Transaction))
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


_LEVEL_LABEL_MAP: dict[str, str] = {
    "B": "BASIS", "G": "GRUND", "F": "FÖRDJUPNING",
}


def _competency_overrides_for(student_id: int) -> dict[int, str]:
    """Returnerar {competency_id: level_short} för elevens overrides."""
    from ..school.models import StudentCompetencyOverride as _SCO
    out: dict[int, str] = {}
    try:
        with master_session() as s:
            rows = (
                s.query(_SCO)
                .filter(_SCO.student_id == student_id)
                .all()
            )
            for r in rows:
                out[r.competency_id] = r.level
    except Exception:
        pass
    return out


def _apply_override(
    cid: int,
    mastery_level: str,
    overrides: dict[int, str],
) -> tuple[str, str, bool]:
    """Returnerar (level_short, level_label, is_override)."""
    if cid in overrides:
        lvl = overrides[cid]
        return (lvl, _LEVEL_LABEL_MAP.get(lvl, lvl), True)
    return (
        mastery_level,
        _LEVEL_LABEL_MAP.get(mastery_level, mastery_level),
        False,
    )


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

    overrides = _competency_overrides_for(sid)
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
            mastery_short, _ = _mastery_to_level(mastery)
            level_short, level_label, _is_over = _apply_override(
                c.id, mastery_short, overrides,
            )
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


class V2InvoiceRow(BaseModel):
    """En rad i en strukturerad faktura."""
    label: str
    qty: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    amount: float


class V2InvoiceData(BaseModel):
    """Strukturerad fakturadata · matchar invoice_data JSON i MailItem.

    Renderas i MailDetailV2.InvoiceLayout med fakturarader, moms,
    OCR och payment-info — analogt med SalarySlipLayout.
    """
    kind: str  # el|mobil|bredband|hyra|brf_avgift|bolan|drift_villa|forsakring|lokaltrafik|annan
    invoice_number: str
    period_start: Optional[_date] = None
    period_end: Optional[_date] = None
    rows: list[V2InvoiceRow]
    subtotal: float
    moms: float
    moms_rate: float
    total: float
    ocr: Optional[str] = None
    bankgiro: Optional[str] = None
    extra: dict = Field(default_factory=dict)


class V2MailDetailResponse(BaseModel):
    mail: V2MailItemRow
    cc_invoice: Optional[V2CcInvoiceData]  # endast för cred-invoice
    salary_slip: Optional[V2SalarySlipData]  # endast för salary_slip
    invoice: Optional[V2InvoiceData] = None  # för game_engine-fakturor


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
        .filter(_released_filter(Transaction))
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
        .filter(_released_filter(Transaction))
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

        # Realtid-projektion: brevet finns men inte synligt än.
        # Returnera 404 så frontend behandlar det som ett brev som
        # ännu inte dykt upp i postlådan.
        if m.released_at is not None and m.released_at > datetime.utcnow():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Saknas")

        # Markera viewed om unhandled
        if m.status == "unhandled":
            m.status = "viewed"
            s.flush()

        cc_data: Optional[V2CcInvoiceData] = None
        salary_data: Optional[V2SalarySlipData] = None
        invoice_data: Optional[V2InvoiceData] = None

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
        elif m.mail_type in ("invoice", "reminder"):
            raw = m.invoice_data
            try:
                if raw:
                    # Strukturerad invoice_data finns
                    invoice_data = V2InvoiceData(
                        kind=str(raw.get("kind", "annan")),
                        invoice_number=str(raw.get("invoice_number", "—")),
                        period_start=(
                            _date.fromisoformat(raw["period_start"])
                            if raw.get("period_start") else None
                        ),
                        period_end=(
                            _date.fromisoformat(raw["period_end"])
                            if raw.get("period_end") else None
                        ),
                        rows=[
                            V2InvoiceRow(
                                label=str(r.get("label", "")),
                                qty=r.get("qty"),
                                unit=r.get("unit"),
                                unit_price=r.get("unit_price"),
                                amount=float(r.get("amount", 0)),
                            )
                            for r in (raw.get("rows") or [])
                        ],
                        subtotal=float(raw.get("subtotal", 0)),
                        moms=float(raw.get("moms", 0)),
                        moms_rate=float(raw.get("moms_rate", 0)),
                        total=float(raw.get("total", 0)),
                        ocr=raw.get("ocr"),
                        bankgiro=raw.get("bankgiro"),
                        extra=raw.get("extra") or {},
                    )
                elif m.amount is not None:
                    # Fallback för gamla mail utan invoice_data ·
                    # bygg minimal struktur från body_meta + amount så
                    # InvoiceLayout fortfarande renderas (1 rad, ingen
                    # moms-uppdelning). Bättre än text-only-fallback.
                    amount_abs = abs(float(m.amount))
                    invoice_data = V2InvoiceData(
                        kind="annan",
                        invoice_number=(
                            m.ocr_reference or f"FAK-{m.id:06d}"
                        ),
                        period_start=None,
                        period_end=None,
                        rows=[
                            V2InvoiceRow(
                                label=m.body_meta or m.subject,
                                qty=None,
                                unit=None,
                                unit_price=None,
                                amount=amount_abs,
                            ),
                        ],
                        subtotal=amount_abs,
                        moms=0,
                        moms_rate=0,
                        total=amount_abs,
                        ocr=m.ocr_reference,
                        bankgiro=m.bankgiro,
                        extra={
                            "moms_note": (
                                "Strukturerad fakturadata saknas — "
                                "fakturan visar bara totalbelopp."
                            ),
                        },
                    )
            except Exception:
                # Robust mot felaktig JSON-data — visa bara body
                invoice_data = None

        return V2MailDetailResponse(
            mail=_mail_to_row(m),
            cc_invoice=cc_data,
            salary_slip=salary_data,
            invoice=invoice_data,
        )


# === PDF-rendering av strukturerade fakturor ===

@router.get("/postladan/{mail_id}/pdf")
def get_mail_pdf(
    mail_id: int,
    info: TokenInfo = Depends(require_token),
) -> Response:
    """Rendera fakturan som riktig PDF (reportlab) · ladda ner via
    knapp i mail-detalj-vyn.

    För invoice-mail med invoice_data: använder render_v2_invoice_pdf
    med strukturerad faktura-layout (header, mottagare, specifikation
    med moms, betalningsinfo, pedagogisk info-ruta).

    För salary_slip: vi har redan render_lonespec i v1 — TODO i nästa
    iteration. För andra typer returnerar vi 400.
    """
    if info.role != "student" or info.student_id is None:
        raise HTTPException(403, "Endast elever")

    # Hämta studentens namn + adress för PDF-rubrik
    student_name = "Eleven"
    student_address: Optional[str] = None
    with master_session() as mdb:
        sp = (
            mdb.query(StudentProfile)
            .filter(StudentProfile.student_id == info.student_id)
            .first()
        )
        if sp is not None:
            first = getattr(sp, "character_first_name", None) or ""
            last = getattr(sp, "character_last_name", None) or ""
            full = f"{first} {last}".strip()
            student_name = full or "Eleven"
            if sp.city:
                student_address = sp.city

    with session_scope() as s:
        m = s.get(MailItem, mail_id)
        if m is None:
            raise HTTPException(404, "Brevet hittades inte")
        # Använd strukturerad invoice_data om den finns, annars
        # bygg minimal fallback så även gamla mail kan PDF-renderas.
        inv = m.invoice_data
        if not inv and m.amount is not None:
            amount_abs = abs(float(m.amount))
            inv = {
                "kind": "annan",
                "invoice_number": m.ocr_reference or f"FAK-{m.id:06d}",
                "period_start": None,
                "period_end": None,
                "rows": [{
                    "label": m.body_meta or m.subject,
                    "amount": amount_abs,
                }],
                "subtotal": amount_abs,
                "moms": 0,
                "moms_rate": 0,
                "total": amount_abs,
                "ocr": m.ocr_reference,
                "bankgiro": m.bankgiro,
                "extra": {},
            }
        if not inv:
            raise HTTPException(
                400, "Brevet saknar belopp — kan inte renderas som PDF.",
            )

        from ..teacher.v2_invoices import render_v2_invoice_pdf
        try:
            pdf_bytes = render_v2_invoice_pdf(
                inv,
                sender=m.sender,
                subject=m.subject,
                due_date=m.due_date,
                student_name=student_name,
                student_address=student_address,
            )
        except Exception as e:
            raise HTTPException(500, f"PDF-rendering misslyckades: {e}")

        kind = str(inv.get("kind", "faktura"))
        filename = f"{kind}-{inv.get('invoice_number', 'x')}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
            },
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
        seed_status = getattr(student, "seed_status", None) or "complete"
        if seed_status not in ("pending", "complete", "failed"):
            seed_status = "complete"
        return V2StatusResponse(
            role="student",
            v2_eligible=eligible,
            v2_onboarding_completed=completed,
            v2_level=getattr(student, "v2_level", None) or 1,
            v2_spend_profile=getattr(student, "v2_spend_profile", None) or "sparsam",
            v2_fairness_choice=getattr(student, "v2_fairness_choice", None),
            v2_partner_model=getattr(student, "v2_partner_model", None) or "solo",
            is_super_admin=False,
            seed_status=seed_status,  # type: ignore[arg-type]
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

        # Snapshot för seed-flow utanför sessionen
        sid = student.id
        sname = student.display_name
        v2_level = student.v2_level
        spend = student.v2_spend_profile or "balanserad"
        partner = student.v2_partner_model or "solo"

    # === Garantera att eleven har data efter onboarding ===
    # Eleven har just slutfört onboarding och ska se hub-vyn med fylld
    # postlåda, konton, fakturor. Om seed inte körts (gammal student
    # eller failed seed) körs den nu. Idempotent: gör inget om data
    # redan finns.
    try:
        _ensure_student_has_initial_data(
            student_id=sid,
            student_name=sname,
            spend_profile=spend,
            starting_level=v2_level,
            partner_model=partner,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "complete_v2_onboarding: seed failed för student %s — "
            "eleven har slutfört onboarding men kan sakna initial data",
            sid,
        )

    return OnboardingCompleteResponse(
        student_id=sid,
        completed_at=now,
        v2_level=v2_level,
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


class V2TimelineSkipResponse(BaseModel):
    student_id: int
    mail_updated: int
    tx_updated: int


@router.post(
    "/teacher/students/{student_id}/timeline-skip",
    response_model=V2TimelineSkipResponse,
)
def timeline_skip(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2TimelineSkipResponse:
    """Lärar-control: släpp HELA spelmånaden direkt för en elev.

    Sätter `released_at = NOW()` på alla pending MailItem + Transaction
    så lektionen kan kunna avancera utan att vänta 5 real-dagar. Använd
    sparsamt — det förstör realtid-känslan, men är värdefullt under
    demo eller när läraren vill köra igenom hela cykeln på en lektion.
    """
    teacher_id = _require_teacher(info)

    with master_session() as db:
        st = db.get(Student, student_id)
        if st is None or st.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Eleven hittades inte",
            )

    from ..school.engines import scope_context, scope_for_student
    scope_key = scope_for_student(st)
    now = datetime.utcnow()
    mail_updated = 0
    tx_updated = 0
    with scope_context(scope_key):
        with session_scope() as s:
            mail_updated = (
                s.query(MailItem)
                .filter(MailItem.released_at.isnot(None))
                .filter(MailItem.released_at > now)
                .update(
                    {MailItem.released_at: now},
                    synchronize_session=False,
                )
            )
            tx_updated = (
                s.query(Transaction)
                .filter(Transaction.released_at.isnot(None))
                .filter(Transaction.released_at > now)
                .update(
                    {Transaction.released_at: now},
                    synchronize_session=False,
                )
            )
            s.commit()
    return V2TimelineSkipResponse(
        student_id=student_id,
        mail_updated=int(mail_updated),
        tx_updated=int(tx_updated),
    )


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

        # Mastery för aktuell elev (override vinner vid manual höjning)
        mastery_by_cid = _compute_mastery_for_student(s, student_id)
        mastery, count, last = mastery_by_cid.get(
            competency_id, (0.0, 0, None),
        )
        overrides = _competency_overrides_for(student_id)
        mastery_short, _ = _mastery_to_level(mastery)
        level_short, level_label, _is_over = _apply_override(
            competency_id, mastery_short, overrides,
        )
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


# Per-process TTL-cache för dyra per-elev-beräkningar i lärar-hubben.
# Klass-överblicken itererar 20-30 elever och varje wellbeing-beräkning
# gör ~20 DB-queries i scope-DB. Utan cache → 60-120 s laddtid per klick.
# 5 min freshness är OK för en lärar-dashboard; alternativet (eventer som
# invaliderar exakt) är komplext och behövs inte här.
_TEACHER_METRICS_TTL_SECONDS = 300.0
# Hur färska persisterade WellbeingScore-rader får vara för att
# återanvändas i klass-prefetch utan att räkna om wellbeing.
_WELLBEING_SNAPSHOT_FRESH_SECONDS = 600.0
# scope_key → (expires_at, (total, eco, safe, health, social, leisure))
_wellbeing_cache: dict[
    str, tuple[float, tuple[int, int, int, int, int, int]]
] = {}
# scope_key → (expires_at, (unhandled_count, oldest_days, has_authority))
_mailcount_cache: dict[
    str, tuple[float, tuple[int, Optional[int], bool]]
] = {}


def _cache_get(cache: dict, key: str):
    import time
    entry = cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if expires_at < time.monotonic():
        cache.pop(key, None)
        return None
    return value


def _cache_set(cache: dict, key: str, value) -> None:
    import time
    cache[key] = (time.monotonic() + _TEACHER_METRICS_TTL_SECONDS, value)


def invalidate_teacher_metrics_cache(scope_key: Optional[str] = None) -> None:
    """Töm TTL-cachen — anropas av tester och kan användas av endpoints
    som vet att en elevs scope-data ändrats kraftigt."""
    if scope_key is None:
        _wellbeing_cache.clear()
        _mailcount_cache.clear()
    else:
        _wellbeing_cache.pop(scope_key, None)
        _mailcount_cache.pop(scope_key, None)


def _collect_student_metrics(
    student: Student,
) -> tuple[
    Optional[tuple[int, int, int, int, int, int]],
    tuple[int, Optional[int], bool],
]:
    """Hämtar wellbeing + ohanterad-post i ETT scope-context per elev.

    Tidigare gjordes detta i två separata helpers, var och en med eget
    `scope_context` + `session_scope`. Klass-hubben med 28 elever
    triggade då 56 session-öppningar mot scope-DB:n. Här delar de en
    OCH persisterar wellbeing-snapshoten så framtida klass-overviews
    kan batch-läsa istället för att räkna om.
    """
    from ..school.engines import scope_context, scope_for_student

    scope_key = scope_for_student(student)
    cached_wb = _cache_get(_wellbeing_cache, scope_key)
    cached_mail = _cache_get(_mailcount_cache, scope_key)
    if cached_wb is not None and cached_mail is not None:
        return cached_wb, cached_mail

    wb_tuple: Optional[tuple[int, int, int, int, int, int]] = cached_wb
    mail_tuple: tuple[int, Optional[int], bool] = cached_mail or (
        0, None, False,
    )

    try:
        with scope_context(scope_key):
            with session_scope() as s:
                if cached_wb is None:
                    try:
                        from ..wellbeing.calculator import (
                            persist_wellbeing as _persist_wb,
                        )
                        ym = _current_year_month()
                        wb = calculate_wellbeing(s, ym)
                        wb_tuple = (
                            wb.total_score, wb.economy, wb.safety,
                            wb.health, wb.social, wb.leisure,
                        )
                        # Persistera snapshoten i scope-DB:n så
                        # _prefetch_klass_metrics kan batch-läsa
                        # nästa gång istället för att räkna om
                        # wellbeing för samma elev.
                        try:
                            _persist_wb(s, wb)
                        except Exception:
                            pass
                    except Exception:
                        wb_tuple = None
                if cached_mail is None:
                    try:
                        items = (
                            s.query(
                                MailItem.received_at, MailItem.mail_type,
                            )
                            .filter(MailItem.status == "unhandled")
                            .order_by(MailItem.received_at.asc())
                            .all()
                        )
                        unhandled_count = len(items)
                        oldest_days: Optional[int] = None
                        has_authority = False
                        if items:
                            oldest = items[0][0]
                            if oldest is not None:
                                delta = datetime.utcnow() - oldest
                                oldest_days = max(0, delta.days)
                            has_authority = any(
                                row[1] == "authority" for row in items
                            )
                        mail_tuple = (
                            unhandled_count, oldest_days, has_authority,
                        )
                    except Exception:
                        mail_tuple = (0, None, False)
    except Exception:
        # Hela scope-öppningen failade — returnera defaults så hubben
        # inte kraschar för en enskild elev.
        if wb_tuple is None and cached_wb is None:
            wb_tuple = None
        if cached_mail is None:
            mail_tuple = (0, None, False)

    if wb_tuple is not None:
        _cache_set(_wellbeing_cache, scope_key, wb_tuple)
    _cache_set(_mailcount_cache, scope_key, mail_tuple)
    return wb_tuple, mail_tuple


def _prefetch_klass_metrics(
    scope_keys: list[str], year_month: str,
) -> None:
    """Förladda TTL-cachen med en handfull batched queries istället för
    28+ scope_context-öppningar.

    Postgres-läge: alla elev-scopes ligger i samma DB med tenant_id-
    isolering. Vi kan därför läsa över hela klassen i:
    - 1 query för WellbeingScore (senaste snapshot per scope för
      aktuell månad, om < 10 min gammal)
    - 1 query för MailItem (count + min(received_at) + bool authority
      per scope, GROUP BY tenant_id)

    SQLite-läge (pytest + dev): varje scope = egen fil, ingen batching
    möjlig → no-op, fall-back till per-scope-loopen.
    """
    import os
    if not os.environ.get("HEMBUDGET_DATABASE_URL", "").strip():
        return
    if not scope_keys:
        return

    # Bara nycklar som inte redan ligger i cachen behöver hämtas.
    missing_wb = [
        k for k in scope_keys
        if _cache_get(_wellbeing_cache, k) is None
    ]
    missing_mail = [
        k for k in scope_keys
        if _cache_get(_mailcount_cache, k) is None
    ]
    if not missing_wb and not missing_mail:
        return

    try:
        from ..school.engines import _init_shared_scope_engine
        from sqlalchemy import func as _sa_func, case as _sa_case
        from ..db.models import WellbeingScore as _WS, MailItem as _MI

        _, session_maker = _init_shared_scope_engine()
        # OBS: ingen scope_context aktiv → tenant-filter är AV, vi
        # ser tvärs över alla tenants. Måste själva filtrera på
        # tenant_id.in_(scope_keys).
        with session_maker() as s:
            if missing_wb:
                fresh_after = (
                    datetime.utcnow()
                    - timedelta(seconds=_WELLBEING_SNAPSHOT_FRESH_SECONDS)
                )
                rows = (
                    s.query(
                        _WS.tenant_id, _WS.total_score, _WS.economy,
                        _WS.safety, _WS.health, _WS.social, _WS.leisure,
                    )
                    .filter(
                        _WS.year_month == year_month,
                        _WS.tenant_id.in_(missing_wb),
                        _WS.computed_at >= fresh_after,
                    )
                    .all()
                )
                for (
                    tenant, total, eco, safe, health, social, leisure,
                ) in rows:
                    if tenant is None:
                        continue
                    _cache_set(
                        _wellbeing_cache, tenant,
                        (total, eco, safe, health, social, leisure),
                    )

            if missing_mail:
                # GROUP BY tenant_id med aggregerings-sub-query.
                authority_case = _sa_case(
                    (_MI.mail_type == "authority", 1), else_=0,
                )
                mail_rows = (
                    s.query(
                        _MI.tenant_id,
                        _sa_func.count(_MI.id),
                        _sa_func.min(_MI.received_at),
                        _sa_func.max(authority_case),
                    )
                    .filter(
                        _MI.status == "unhandled",
                        _MI.tenant_id.in_(missing_mail),
                    )
                    .group_by(_MI.tenant_id)
                    .all()
                )
                seen: set[str] = set()
                now = datetime.utcnow()
                for tenant, cnt, oldest, has_auth in mail_rows:
                    if tenant is None:
                        continue
                    seen.add(tenant)
                    oldest_days: Optional[int] = None
                    if oldest is not None:
                        oldest_days = max(0, (now - oldest).days)
                    _cache_set(
                        _mailcount_cache, tenant,
                        (int(cnt or 0), oldest_days, bool(has_auth)),
                    )
                # Scopes utan ohanterad post → tomma rader.
                for k in missing_mail:
                    if k not in seen:
                        _cache_set(
                            _mailcount_cache, k, (0, None, False),
                        )
    except Exception:
        # Prefetchen är en optimering — om den failar fortsätter
        # vi via per-scope-loopen i klass-overview.
        import logging
        logging.getLogger(__name__).exception(
            "klass-prefetch failed — fortsätter via per-scope-loopen",
        )


def _safe_calc_wellbeing_for(
    student: Student,
) -> Optional[tuple[int, int, int, int, int, int]]:
    """Returnerar (total, economy, safety, health, social, leisure) eller
    None om wellbeing inte kan beräknas (fallar tyst — lärar-hub får
    inte krascha för en enskild elev). Cachead 60 s per scope-key."""
    from ..school.engines import scope_for_student

    scope_key = scope_for_student(student)
    cached = _cache_get(_wellbeing_cache, scope_key)
    if cached is not None:
        return cached

    wb_tuple, _ = _collect_student_metrics(student)
    return wb_tuple


def _safe_count_unhandled_mail(student: Student) -> tuple[
    int, Optional[int], bool,
]:
    """Returnerar (unhandled_count, oldest_days, has_authority).
    Cachead 60 s per scope-key."""
    from ..school.engines import scope_for_student

    scope_key = scope_for_student(student)
    cached = _cache_get(_mailcount_cache, scope_key)
    if cached is not None:
        return cached

    _, mail_tuple = _collect_student_metrics(student)
    return mail_tuple


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
    class_label: Optional[str] = None,
) -> V2KlassOverview:
    """Klass-dashboard · aggregerad data för lärar-hubben.

    Itererar lärarens elever, beräknar wellbeing per elev (i scope-context),
    aggregerar till klass-pentagon (snitt), identifierar elever som behöver
    stöd, listar pågående lönesamtal + olästa reflektioner + topp-postlådor.

    Bug 7 · `class_label` filtrerar på elevernas Student.class_label.
    None / tomt → visa alla elever (gamla beteendet).
    """
    teacher_id = _require_teacher(info)
    today = datetime.utcnow()

    with master_session() as mdb:
        teacher = mdb.get(Teacher, teacher_id)
        teacher_name = teacher.name if teacher else "Lärare"

        students_q = (
            mdb.query(Student)
            .filter(
                Student.teacher_id == teacher_id,
                Student.active.is_(True),
            )
        )
        if class_label and class_label.strip():
            students_q = students_q.filter(
                Student.class_label == class_label.strip(),
            )
        students = students_q.order_by(Student.display_name).all()
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

    # Pre-fetch hela klassens wellbeing+mail på 2 queries (Postgres-läge)
    # innan vi går in i per-elev-loopen. Tomt på SQLite-läge.
    try:
        from ..school.engines import scope_for_student as _sfs_pre
        prefetch_keys = [
            _sfs_pre(d["obj"]) for d in students_data
        ]
        _prefetch_klass_metrics(prefetch_keys, _current_year_month())
    except Exception:
        pass  # prefetch är best-effort

    # Beräkna wellbeing per elev (i scope-context — kan ej ligga inom
    # master_session ovan eftersom scope-engine är separat)
    pents: list[tuple[int, int, int, int, int, int]] = []
    mini_pentagons: list[V2KlassMiniPentagon] = []
    needs_help: list[V2KlassNeedsHelpItem] = []
    mailbox_items: list[V2KlassMailboxItem] = []
    mailbox_total_unhandled = 0

    for d in students_data:
        st = d["obj"]
        # Hämta wellbeing + post i ETT scope-context-pass, cachat 60 s.
        wb, mail_tuple = _collect_student_metrics(st)
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
        unhandled, oldest_days, has_auth = mail_tuple
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
            # Batcha alla rundor i en enda query istället för en per
            # förhandling. För varje förhandling håller vi den högsta
            # round_no (senaste budet).
            neg_ids = [n.id for n in negs]
            last_round_by_neg: dict[
                int, tuple[int, Optional[float]]
            ] = {}
            if neg_ids:
                rounds = (
                    ms.query(
                        _NegotiationRound.negotiation_id,
                        _NegotiationRound.round_no,
                        _NegotiationRound.proposed_pct,
                    )
                    .filter(
                        _NegotiationRound.negotiation_id.in_(neg_ids),
                    )
                    .all()
                )
                for neg_id, round_no, proposed_pct in rounds:
                    existing = last_round_by_neg.get(neg_id)
                    if existing is None or round_no > existing[0]:
                        last_round_by_neg[neg_id] = (
                            round_no, proposed_pct,
                        )
            for neg in negs:
                last = last_round_by_neg.get(neg.id)
                # NegotiationRound har proposed_pct (delta), bygg
                # konkret SEK-bud genom starting_salary × (1 + pct/100).
                last_proposed: Optional[float] = None
                round_no = 0
                if last is not None:
                    round_no, proposed_pct = last
                    if (
                        proposed_pct is not None
                        and neg.starting_salary is not None
                    ):
                        last_proposed = float(
                            neg.starting_salary,
                        ) * (1.0 + (proposed_pct / 100.0))
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
    business_mode_enabled: bool = False


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

    overrides = _competency_overrides_for(student_id)
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
            mastery_short, _ = _mastery_to_level(mastery)
            level_short, level_label, _is_over = _apply_override(
                c.id, mastery_short, overrides,
            )
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
    background_tasks: BackgroundTasks,
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

    # Auto-recovery · om eleven inte har en SINGLE WeekTickRun med
    # status='completed' så har den aldrig fått sin initial data.
    # Trigga seed i BAKGRUNDEN så lärar-vyn kan renderas direkt
    # (~200 ms i stället för 3-4 s synkron seed).
    #
    # Tidigare körde detta synkront → varje klick på en elev som
    # saknar data tog 3-4 s vilket är oacceptabelt UX. Nu schemaläggs
    # det som BackgroundTask: lärar-vyn renderar omedelbart med tom
    # data, och nästa request till samma elev (efter att seed klar)
    # ger full data.
    #
    # Vi gör en SNABB check för completed_runs här för att avgöra
    # om bakgrunds-task behövs, så vi inte schemalägger seed för
    # alla elever (bara de som faktiskt saknar data).
    try:
        from ..school.game_engine_models import WeekTickRun as _WTR_q
        with master_session() as _s_q:
            _completed_runs = (
                _s_q.query(_WTR_q)
                .filter(
                    _WTR_q.student_id == student_id,
                    _WTR_q.status == "completed",
                )
                .count()
            )
        if _completed_runs == 0:
            background_tasks.add_task(
                _seed_initial_student_data_safe,
                student_id,
                spend_profile or "balanserad",
                v2_level,
                partner or "solo",
            )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "auto-recovery check failed för student %s — vyn "
            "renderas ändå, seed försöks nästa gång",
            student_id,
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
        business_mode_enabled=bool(getattr(student, "business_mode_enabled", False)),
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


# === TeacherStudentHistoryV2 (p-historik · Fas 2Y) ===
#
# Speglar prototypens larare.html#p-historik: komplett aktivitets-
# tidslinje för en elev — alla events från signup till idag,
# grupperade på datum, filtrerbart på kind. Aggregerar:
# - StudentActivity (master) — tx, budget, lån, transfers, batches
# - StudentStepProgress.completed_at — modul-steg klart
# - BankIDSession.signed_at — BankID-signering
# - NegotiationRound — Maria-rundor
# - Assignment.manually_completed_at — uppdrag klart
# - V2OnboardingEvent — onboarding-stegen


HistoryEventKind = Literal[
    "onboarding", "module_step", "module_completed", "maria_round",
    "bankid", "assignment", "transaction", "budget", "loan",
    "transfer", "import", "competency_raised", "system",
]


class V2HistoryEvent(BaseModel):
    occurred_at: datetime
    kind: HistoryEventKind
    title: str
    detail: Optional[str] = None
    badge: str
    color: str  # hex eller css-var
    source_id: Optional[int] = None
    payload: Optional[dict] = None


class V2HistoryStats(BaseModel):
    total_events: int
    onboarding_count: int  # 0 eller 1 (klar?)
    transactions_count: int
    module_steps_count: int
    reflections_count: int
    bankid_count: int
    maria_rounds_count: int
    days_since_signup: Optional[int]


class V2HistoryResponse(BaseModel):
    student_id: int
    student_name: str
    signup_at: Optional[datetime]
    onboarding_completed_at: Optional[datetime]
    stats: V2HistoryStats
    events: list[V2HistoryEvent]


def _kind_to_visual(kind: HistoryEventKind) -> tuple[str, str]:
    """Returnerar (badge, color) för en event-kind."""
    table: dict[HistoryEventKind, tuple[str, str]] = {
        "onboarding": ("ONBOARDING", "#c7d2fe"),
        "module_step": ("MODUL-STEG", "var(--warm)"),
        "module_completed": ("MODUL-KLAR", "var(--warm)"),
        "maria_round": ("MARIA-RUNDA", "var(--accent)"),
        "bankid": ("BANKID", "#6ee7b7"),
        "assignment": ("UPPDRAG", "var(--accent)"),
        "transaction": ("BOKFÖRING", "rgba(255,255,255,0.5)"),
        "budget": ("BUDGET", "#fbbf24"),
        "loan": ("LÅN", "#fda594"),
        "transfer": ("ÖVERFÖRING", "#93c5fd"),
        "import": ("IMPORT", "#a5b4fc"),
        "competency_raised": ("KOMP-HÖJN", "#6ee7b7"),
        "system": ("SYSTEM", "#c084fc"),
    }
    return table.get(kind, ("EVENT", "rgba(255,255,255,0.5)"))


def _activity_kind_to_history_kind(
    activity_kind: str,
) -> HistoryEventKind:
    if activity_kind.startswith("transaction."):
        return "transaction"
    if activity_kind.startswith("budget."):
        return "budget"
    if activity_kind.startswith("loan."):
        return "loan"
    if activity_kind.startswith("transfer."):
        return "transfer"
    if activity_kind.startswith("batch."):
        return "import"
    return "system"


@router.get(
    "/teacher/students/{student_id}/activity-log",
    response_model=V2HistoryResponse,
)
def teacher_student_history(
    student_id: int,
    limit: int = 100,
    info: TokenInfo = Depends(require_token),
) -> V2HistoryResponse:
    """Komplett aktivitets-tidslinje för en specifik elev (lärar-vy).

    Aggregerar events från flera tabeller. limit begränsar antal
    returnerade events (sortering nyast först)."""
    teacher_id = _require_teacher(info)

    with master_session() as mdb:
        student = mdb.get(Student, student_id)
        if not student or student.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Endast egen elev",
            )
        student_name = student.display_name
        signup_at = student.created_at
        onboarded_at = getattr(
            student, "v2_onboarding_completed_at", None,
        )

    events: list[V2HistoryEvent] = []

    # 1. Onboarding-events
    with master_session() as ms:
        from ..school.models import StudentActivity as _SA
        ob_events = (
            ms.query(V2OnboardingEvent)
            .filter(V2OnboardingEvent.student_id == student_id)
            .order_by(V2OnboardingEvent.created_at.asc())
            .all()
        )
        for ev in ob_events:
            badge, color = _kind_to_visual("onboarding")
            if ev.event_type == "completed":
                title = "Onboarding klar"
                detail = f"steg {ev.step} · sista steget"
            elif ev.event_type == "abandoned":
                title = "Onboarding avbruten"
                detail = f"steg {ev.step} · stängde fönstret"
                color = "var(--accent)"
            elif ev.event_type == "back":
                title = f"Onboarding · gick tillbaka från steg {ev.step}"
                detail = "klickade ← Tillbaka"
            elif ev.event_type == "viewed":
                title = f"Onboarding · steg {ev.step} visat"
                detail = (
                    f"{ev.duration_ms} ms"
                    if ev.duration_ms else None
                )
            else:
                title = f"Onboarding · steg {ev.step} ({ev.event_type})"
                detail = None
            events.append(V2HistoryEvent(
                occurred_at=ev.created_at,
                kind="onboarding",
                title=title,
                detail=detail,
                badge=badge,
                color=color,
                source_id=ev.id,
            ))

        # 2. StudentActivity
        sa_rows = (
            ms.query(_SA)
            .filter(_SA.student_id == student_id)
            .order_by(_SA.occurred_at.desc())
            .limit(200)
            .all()
        )
        for sa in sa_rows:
            kind = _activity_kind_to_history_kind(sa.kind)
            badge, color = _kind_to_visual(kind)
            events.append(V2HistoryEvent(
                occurred_at=sa.occurred_at,
                kind=kind,
                title=sa.summary,
                detail=sa.kind,
                badge=badge,
                color=color,
                source_id=sa.id,
                payload=sa.payload,
            ))

        # 3. StudentStepProgress
        progress_rows = (
            ms.query(
                _SchoolStepProgress, _SchoolModuleStep, _SchoolModule,
            )
            .join(
                _SchoolModuleStep,
                _SchoolStepProgress.step_id == _SchoolModuleStep.id,
            )
            .join(
                _SchoolModule,
                _SchoolModuleStep.module_id == _SchoolModule.id,
            )
            .filter(
                _SchoolStepProgress.student_id == student_id,
                _SchoolStepProgress.completed_at.is_not(None),
            )
            .order_by(_SchoolStepProgress.completed_at.desc())
            .limit(60)
            .all()
        )
        for prog, step, module in progress_rows:
            badge, color = _kind_to_visual("module_step")
            events.append(V2HistoryEvent(
                occurred_at=prog.completed_at,  # type: ignore[arg-type]
                kind="module_step",
                title=f'Steg "{step.title}" klart',
                detail=f"Modul: {module.title} · {step.kind}",
                badge=badge,
                color=color,
                source_id=prog.id,
            ))

        # 4. Module completion
        sm_rows = (
            ms.query(_SchoolStudentModule, _SchoolModule)
            .join(
                _SchoolModule,
                _SchoolStudentModule.module_id == _SchoolModule.id,
            )
            .filter(
                _SchoolStudentModule.student_id == student_id,
                _SchoolStudentModule.completed_at.is_not(None),
            )
            .order_by(_SchoolStudentModule.completed_at.desc())
            .all()
        )
        for sm, module in sm_rows:
            badge, color = _kind_to_visual("module_completed")
            events.append(V2HistoryEvent(
                occurred_at=sm.completed_at,  # type: ignore[arg-type]
                kind="module_completed",
                title=f'Modulen "{module.title}" klar',
                detail=None,
                badge=badge,
                color=color,
                source_id=sm.id,
            ))

        # 5. NegotiationRound
        neg_rounds = (
            ms.query(_NegotiationRound, _SalaryNegotiation)
            .join(
                _SalaryNegotiation,
                _NegotiationRound.negotiation_id == _SalaryNegotiation.id,
            )
            .filter(_SalaryNegotiation.student_id == student_id)
            .order_by(_NegotiationRound.created_at.desc())
            .all()
        )
        for r, neg in neg_rounds:
            badge, color = _kind_to_visual("maria_round")
            proposed: Optional[float] = None
            if r.proposed_pct is not None and neg.starting_salary is not None:
                proposed = float(neg.starting_salary) * (
                    1.0 + (r.proposed_pct / 100.0)
                )
            events.append(V2HistoryEvent(
                occurred_at=r.created_at,
                kind="maria_round",
                title=(
                    f"Maria-lönesamtal · runda {r.round_no}"
                    + (
                        f" · bud {round(proposed):,} kr".replace(",", " ")
                        if proposed else ""
                    )
                ),
                detail=neg.profession,
                badge=badge,
                color=color,
                source_id=r.id,
            ))

        # 6. Assignment.manually_completed_at
        assignments_done = (
            ms.query(_SchoolAssignment)
            .filter(
                _SchoolAssignment.student_id == student_id,
                _SchoolAssignment.manually_completed_at.is_not(None),
            )
            .all()
        )
        for a in assignments_done:
            badge, color = _kind_to_visual("assignment")
            events.append(V2HistoryEvent(
                occurred_at=a.manually_completed_at,  # type: ignore[arg-type]
                kind="assignment",
                title=f'Uppdrag "{a.title}" klart',
                detail=None,
                badge=badge,
                color=color,
                source_id=a.id,
            ))

    # 7. BankID-sessioner (i scope-DB)
    from ..school.engines import scope_context, scope_for_student
    bankid_count = 0
    try:
        with master_session() as mdb:
            st_obj = mdb.get(Student, student_id)
        scope_key = scope_for_student(st_obj)
        with scope_context(scope_key):
            with session_scope() as s:
                bankid_rows = (
                    s.query(BankIDSession)
                    .order_by(BankIDSession.created_at.desc())
                    .limit(30)
                    .all()
                )
                for b in bankid_rows:
                    if b.signed_at is not None:
                        badge, color = _kind_to_visual("bankid")
                        events.append(V2HistoryEvent(
                            occurred_at=b.signed_at,
                            kind="bankid",
                            title=(
                                f"BankID-signering · "
                                f"{len(b.upcoming_ids or [])} fakturor"
                            ),
                            detail=None,
                            badge=badge,
                            color=color,
                            source_id=b.id,
                        ))
                        bankid_count += 1
    except Exception:
        pass

    # Räkningar för stats
    transactions_count = sum(1 for e in events if e.kind == "transaction")
    module_steps_count = sum(1 for e in events if e.kind == "module_step")
    reflections_count = 0
    # Reflektioner är progress-rader där step.kind='reflect' — räkna separat
    with master_session() as ms:
        reflections_count = (
            ms.query(_SchoolStepProgress)
            .join(
                _SchoolModuleStep,
                _SchoolStepProgress.step_id == _SchoolModuleStep.id,
            )
            .filter(
                _SchoolStepProgress.student_id == student_id,
                _SchoolModuleStep.kind == "reflect",
                _SchoolStepProgress.completed_at.is_not(None),
            )
            .count()
        )
    maria_rounds_count = sum(
        1 for e in events if e.kind == "maria_round"
    )

    days_since_signup = (
        (datetime.utcnow() - signup_at).days
        if signup_at else None
    )

    # Sortera nyast först
    events.sort(key=lambda e: e.occurred_at, reverse=True)
    events = events[:limit]

    stats = V2HistoryStats(
        total_events=len(events),
        onboarding_count=1 if onboarded_at else 0,
        transactions_count=transactions_count,
        module_steps_count=module_steps_count,
        reflections_count=reflections_count,
        bankid_count=bankid_count,
        maria_rounds_count=maria_rounds_count,
        days_since_signup=days_since_signup,
    )

    return V2HistoryResponse(
        student_id=student_id,
        student_name=student_name,
        signup_at=signup_at,
        onboarding_completed_at=onboarded_at,
        stats=stats,
        events=events,
    )


# === TeacherCreateStudentV2 (p-skapa · Fas 2X) ===
#
# Speglar prototypens larare.html#p-skapa: snabb-create-formulär med
# karaktärs-arketyp + spend_profile + partner-modell + level + auto-
# generering av login-kod. Aktiverar v2 direkt så eleven hamnar på
# /v2/onboarding vid första inloggning. Lärare kan skicka koden via
# vårdnadshavar-mail (lagras men mailing implementeras senare).


CharacterArchetype = Literal[
    "random", "vard_underskoterska", "it_konsult_junior",
    "butiksbitrade", "kassorska", "lar_vikarie",
    "anstalld_kommun", "studerande_gymnasium",
]


class V2CreateStudentIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_initial: Optional[str] = Field(default=None, max_length=2)
    archetype: CharacterArchetype = "random"
    spend_profile: Optional[SpendProfile] = None  # None → slumpa
    partner_model: Optional[PartnerModel] = None  # None → slumpa
    starting_level: int = Field(default=1, ge=1, le=3)
    guardian_email: Optional[str] = Field(default=None, max_length=160)
    family_id: Optional[int] = None


class V2CreatedStudentRow(BaseModel):
    student_id: int
    student_name: str
    login_code: str
    archetype: CharacterArchetype
    spend_profile: Optional[str]
    partner_model: Optional[str]
    starting_level: int
    guardian_email: Optional[str]
    created_at: datetime
    last_login_at: Optional[datetime]
    activated: bool  # has logged in at least once


def _resolve_archetype(
    archetype: CharacterArchetype,
) -> tuple[str, str]:
    """Returnerar (profession, employer) för en arketyp.

    Random → väljer en av 7 fasta arketyper deterministiskt baserat på
    timestamp. Det här är pedagogisk randomness — kan upprepas.
    """
    import random as _random
    table: dict[CharacterArchetype, tuple[str, str]] = {
        "vard_underskoterska": ("Undersköterska", "Vården"),
        "it_konsult_junior": ("IT-konsult", "Konsultföretag"),
        "butiksbitrade": ("Butiksbiträde", "Restaurang/butik"),
        "kassorska": ("Kassörska", "Detaljhandel"),
        "lar_vikarie": ("Lärar-vikarie", "Skolan"),
        "anstalld_kommun": ("Anställd", "Kommun"),
        "studerande_gymnasium": ("Studerande", "Gymnasium"),
    }
    if archetype == "random":
        keys = list(table.keys())
        return table[_random.choice(keys)]
    return table[archetype]


def _resolve_spend_profile(
    profile: Optional[SpendProfile], level: int,
) -> SpendProfile:
    """Default per nivå: 1=sparsam, 2=balanserad, 3=slosa."""
    if profile is not None:
        return profile
    return {1: "sparsam", 2: "balanserad", 3: "slosa"}.get(
        level, "sparsam",
    )


def _resolve_partner_model(
    partner: Optional[PartnerModel],
) -> PartnerModel:
    """Default-fördelning · 60% solo, 35% AI, 5% klasskompis."""
    if partner is not None:
        return partner
    import random as _random
    pick = _random.random()
    if pick < 0.60:
        return "solo"
    if pick < 0.95:
        return "ai"
    return "klasskompis"


@router.post(
    "/teacher/students/create", response_model=V2CreatedStudentRow,
)
def v2_create_student(
    payload: V2CreateStudentIn,
    background_tasks: BackgroundTasks,
    info: TokenInfo = Depends(require_token),
) -> V2CreatedStudentRow:
    """Skapa elev med v2-karaktär · auto-aktiverad v2 + login-kod.

    Sätter v2_spend_profile, v2_partner_model, v2_level på Student-
    raden. Login-koden är 8-tecken alfanumerisk (samma format som
    school.create_student använder).
    """
    from ..api.school import _gen_login_code, _create_profile_for_student
    from ..school.engines import get_scope_engine, scope_for_student

    teacher_id = _require_teacher(info)

    display = payload.first_name.strip()
    if payload.last_initial:
        suffix = payload.last_initial.strip().rstrip(".")
        if suffix:
            display = f"{display} {suffix}."
    profession, employer = _resolve_archetype(payload.archetype)
    spend = _resolve_spend_profile(
        payload.spend_profile, payload.starting_level,
    )
    partner = _resolve_partner_model(payload.partner_model)

    with master_session() as s:
        # Validera familj
        if payload.family_id is not None:
            from ..school.models import Family as _F
            fam = (
                s.query(_F)
                .filter(
                    _F.id == payload.family_id,
                    _F.teacher_id == teacher_id,
                )
                .first()
            )
            if not fam:
                raise HTTPException(404, "Familjen hittades inte")

        # Generera unik login_code
        code = None
        for _ in range(5):
            candidate = _gen_login_code()
            if (
                not s.query(Student)
                .filter(Student.login_code == candidate)
                .first()
            ):
                code = candidate
                break
        if code is None:
            raise HTTPException(500, "Kunde inte generera login-kod")

        student = Student(
            teacher_id=teacher_id,
            family_id=payload.family_id,
            display_name=display,
            login_code=code,
        )
        s.add(student); s.flush()

        # V2-fält
        student.v2_enabled = True
        student.v2_spend_profile = spend
        student.v2_partner_model = partner
        student.v2_level = payload.starting_level
        # Markera seed som pågående · BackgroundTask sätter complete/failed.
        # Frontend visar "Bygger upp ditt liv..."-overlay tills complete så
        # eleven inte ser tomma vyer medan tick_month + insurance/pension/
        # rental/event-seed pågår i bakgrunden (3-5 s).
        student.seed_status = "pending"
        # När level > 1 → onboarding redan klar (eleven börjar på högre nivå)
        if payload.starting_level > 1:
            student.onboarding_completed = True
        s.flush()

        # Defensivt: profile-create kan fail på Postgres om en NOT NULL-
        # kolumn saknas i prod-schema. Då sparar vi student-raden ändå
        # och låter profile skapas senare via auto-recovery.
        try:
            _create_profile_for_student(s, student)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "v2_create_student: _create_profile_for_student failed "
                "för student %s — student sparas ändå utan profile",
                student.id,
            )
            # Rollback för att rensa partiellt failed insert
            s.rollback()
            # Återskapa student-raden eftersom rollback nuked den
            student = Student(
                teacher_id=teacher_id,
                family_id=payload.family_id,
                display_name=display,
                login_code=code,
            )
            s.add(student)
            s.flush()
            student.v2_enabled = True
            student.v2_spend_profile = spend
            student.v2_partner_model = partner
            student.v2_level = payload.starting_level
            student.seed_status = "pending"
            if payload.starting_level > 1:
                student.onboarding_completed = True
            s.flush()
        # Skapa scope-DB direkt så kategorier seedas (defensivt)
        try:
            get_scope_engine(scope_for_student(student))
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "v2_create_student: scope-engine init failed — eleven "
                "skapas ändå, scope-init försöks igen vid första request",
            )

        # Guardian-mail returneras till klienten men persisteras inte
        # i master-DB (kräver schema-tillägg). Mailar vi till föräldern
        # senare så loggar vi till audit-trail då.
        s.flush()
        s.refresh(student)
        sid = student.id
        created_at = student.created_at
        last_login = student.last_login_at
        # Detacha innan session stängs · vi behöver objektet utanför
        # transaktionen för seed-funktionerna nedan.
        s.expunge(student)
        student_obj = student

    # === Initial-seed så eleven har data att jobba med från dag 1 ===
    #
    # Seed:en gör 2 × tick_month (~150-450 INSERTs) + insurance/utility/
    # pension/rental — totalt ~3-4 sekunder. Tidigare körde vi det
    # SYNKRONT före response → läraren satt och väntade i 4 s per
    # skapad elev. Nu schemaläggs det som BackgroundTask: response
    # returneras direkt med login-koden, seed:en rullar i samma
    # Cloud-Run-instans (max-instances=1 säkerställer att det är
    # samma process).
    #
    # Edge case: om eleven loggar in INNAN seed:en hunnit klart ser
    # hen tomma vyer. _ensure_student_has_initial_data i
    # teacher_student_detail (auto-recovery) städar upp om något
    # failade. För eleven själv finns ingen explicit "förbereder
    # data..."-state ännu — för 4 s extra första gången är det OK.
    background_tasks.add_task(
        _seed_initial_student_data_safe,
        sid,
        spend,
        payload.starting_level,
        partner,
    )

    return V2CreatedStudentRow(
        student_id=sid,
        student_name=display,
        login_code=code,
        archetype=payload.archetype,
        spend_profile=spend,
        partner_model=partner,
        starting_level=payload.starting_level,
        guardian_email=payload.guardian_email,
        created_at=created_at,
        last_login_at=last_login,
        activated=last_login is not None,
    )


# === Lärar-endpoint · manuell reseed (om auto-recovery av någon
#     anledning inte räcker) ===

class V2ReseedResponse(BaseModel):
    student_id: int
    seeded: bool
    success: bool
    message: str
    error_detail: Optional[str] = None
    last_failed_run: Optional[dict] = None


@router.delete(
    "/teacher/students/{student_id}",
    status_code=204,
)
def v2_delete_student(
    student_id: int,
    background_tasks: BackgroundTasks,
    info: TokenInfo = Depends(require_token),
) -> Response:
    """Radera en elev permanent · scope-DB + master-rader + cascade.

    Flöde (Cloud Run --max-instances=1):
    1. Sync · markera Student.active=False så eleven försvinner från
       lärarens lista omedelbart (UI känns responsiv).
    2. Async · bakgrundstask gör scope-DB-wipe, master-FK-cleanup,
       file-removal och s.delete(st). Serialiseras via globalt lock
       så två parallella tryck inte kraschar Cloud Run-instansen.

    Tidigare körde hela raderingen synkront. För en fully-seedad
    elev kunde det ta 30-60 s eftersom scope-DB har 50+ tabeller +
    master har 25+ FK:s. Cloud Run med --max-instances=1 blev då
    blockerad och nästa request fick 'Failed to fetch' i browser.

    Status spåras i _delete_jobs · GET /v2/teacher/delete-jobs ger
    UI:t feedback om vilka raderingar som pågår.
    """
    teacher_id = _require_teacher(info)
    with master_session() as s:
        st = s.get(Student, student_id)
        if st is None or st.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Eleven hittades inte",
            )
        # Idempotens: om eleven redan håller på att raderas, skicka
        # inte en ny bakgrundstask (skulle annars köa upp dubbla jobb).
        existing_job = _delete_jobs.get(student_id)
        if existing_job and existing_job.get("status") in (
            "queued", "running",
        ):
            return Response(status_code=204)

        # Sync · soft-delete så eleven försvinner direkt från listan.
        # Den fulla raderingen (scope + master-FK:s) körs i bakgrunden.
        st.active = False
        student_name = st.display_name or f"Elev {student_id}"
        s.commit()

    # Spåra status så UI kan visa "Raderar…" och informera när klart.
    import time as _t_d
    _delete_jobs[student_id] = {
        "student_id": student_id,
        "student_name": student_name,
        "teacher_id": teacher_id,
        "status": "queued",
        "started_at": _t_d.time(),
        "finished_at": None,
        "error": None,
    }
    background_tasks.add_task(
        _hard_delete_student_worker, student_id, teacher_id,
    )
    return Response(status_code=204)


# In-memory status-tracker för enskilda student-deletions. Visar
# raderings-progress i UI:n. Lever bara i nuvarande Cloud Run-
# instansen — om instansen restartar förlorar vi historik, men det
# är OK eftersom soft-delete redan har tagit bort eleven från listan.
# {student_id: {status, started_at, finished_at, error, ...}}
_delete_jobs: dict[int, dict] = {}

# Serialisera de tunga bakgrunds-raderingarna · max 1 åt gången per
# instans. Undviker att två parallella deletes utmattar master-DB-
# poolen eller råkar i lock-konflikter på samma scope-DB.
import threading as _threading_d
_hard_delete_lock = _threading_d.Semaphore(1)


def _hard_delete_student_worker(
    student_id: int, teacher_id: int,
) -> None:
    """Bakgrunds-worker · gör den fulla student-raderingen.

    Serialiseras via _hard_delete_lock så bara EN tung radering
    körs åt gången per instans. Best-effort: fel loggas och skrivs
    till _delete_jobs så UI kan visa dem; eleven står kvar med
    active=False (osynlig för läraren) om något går fel — då kan
    läraren trycka radera igen utan duplicering.
    """
    import logging as _log_d
    import time as _t_d
    log = _log_d.getLogger(__name__)
    job = _delete_jobs.get(student_id)
    if job is None:
        # Inte spårat (skulle inte hända) — skapa en bakåtkompatibel post
        job = {
            "student_id": student_id, "teacher_id": teacher_id,
            "status": "queued", "started_at": _t_d.time(),
            "finished_at": None, "error": None,
        }
        _delete_jobs[student_id] = job

    # Vänta på lock (max 1 åt gången). Andra deletes köar upp utan
    # att slå ut Cloud Run-instansen.
    with _hard_delete_lock:
        job["status"] = "running"
        job["running_at"] = _t_d.time()
        try:
            _do_hard_delete_student(student_id, teacher_id)
            job["status"] = "done"
            job["finished_at"] = _t_d.time()
            log.info(
                "_hard_delete_student_worker: %s raderad på %.1fs",
                student_id, job["finished_at"] - job["started_at"],
            )
        except Exception as e:
            log.exception(
                "_hard_delete_student_worker: outer failure för %s",
                student_id,
            )
            job["status"] = "failed"
            job["finished_at"] = _t_d.time()
            job["error"] = f"{type(e).__name__}: {str(e)[:200]}"


def _do_hard_delete_student(student_id: int, teacher_id: int) -> None:
    """Den faktiska raderings-logiken · separat så den är testbar och
    så _hard_delete_student_worker bara hanterar lock + status."""
    import logging as _log_d
    log = _log_d.getLogger(__name__)
    with master_session() as s:
        st = s.get(Student, student_id)
        if st is None:
            log.info(
                "_do_hard_delete_student: %s redan borttagen",
                student_id,
            )
            return
        if st.teacher_id != teacher_id:
            log.warning(
                "_do_hard_delete_student: teacher-id mismatch för %s",
                student_id,
            )
            return

        from ..school.engines import (
            scope_for_student as _sfs_d, scope_context as _sctx_d,
            get_scope_session as _gss_d,
        )
        scope_key = _sfs_d(st)
        if not scope_key or not isinstance(scope_key, str):
            log.error(
                "_do_hard_delete_student: saknar scope_key för %s",
                student_id,
            )
            return

        # Scope-DB-wipe
        try:
            with _sctx_d(scope_key):
                with _gss_d(scope_key)() as ss:
                    from ..db.base import Base, TenantMixin
                    for table in reversed(Base.metadata.sorted_tables):
                        cls = next(
                            (
                                c.class_ for c in Base.registry.mappers
                                if c.local_table is table
                            ),
                            None,
                        )
                        if cls is None or not issubclass(cls, TenantMixin):
                            continue
                        try:
                            ss.query(cls).filter(
                                cls.tenant_id == scope_key,
                            ).delete(synchronize_session=False)
                        except Exception:
                            log.exception(
                                "_do_hard_delete_student: delete %s "
                                "för tenant %s failade",
                                cls.__name__, scope_key,
                            )
                    ss.commit()
        except Exception:
            log.exception(
                "_do_hard_delete_student: scope-cleanup failed för %s",
                student_id,
            )

        # SQLite-fil-läge: radera filen från disk
        try:
            import os as _os_d
            from ..school.engines import _scope_db_path
            path = _scope_db_path(scope_key)
            if path and _os_d.path.exists(path):
                _os_d.remove(path)
        except Exception:
            pass

        # Master · CASCADE-snabbväg först
        from sqlalchemy.exc import IntegrityError as _IE_d
        try:
            s.delete(st)
            s.commit()
            return
        except _IE_d:
            log.warning(
                "_do_hard_delete_student: CASCADE failade för %s — "
                "kör fallback-cleanup",
                student_id,
            )
            try:
                s.rollback()
            except Exception:
                pass

        # Fallback · enumerera alla master-tabeller med FK till students.id
        from ..school.models import MasterBase
        tables_with_student_fk = []
        for table in MasterBase.metadata.sorted_tables:
            for fk in table.foreign_keys:
                if (
                    fk.column.table.name == "students"
                    and fk.column.name == "id"
                ):
                    tables_with_student_fk.append(
                        (table, fk.parent.name),
                    )
                    break
        for table, fk_col in reversed(tables_with_student_fk):
            if table.name == "students":
                continue
            try:
                s.execute(
                    table.delete().where(
                        table.c[fk_col] == student_id,
                    ),
                )
            except Exception:
                log.exception(
                    "_do_hard_delete_student: cleanup av %s "
                    "(FK %s) failade",
                    table.name, fk_col,
                )
        st_retry = s.get(Student, student_id)
        if st_retry is not None:
            s.delete(st_retry)
        s.commit()


class V2DeleteJobRow(BaseModel):
    student_id: int
    student_name: str
    status: Literal["queued", "running", "done", "failed"]
    started_at: float
    finished_at: Optional[float]
    error: Optional[str]


class V2DeleteJobsResponse(BaseModel):
    rows: list[V2DeleteJobRow]
    pending_count: int


@router.get(
    "/teacher/delete-jobs",
    response_model=V2DeleteJobsResponse,
)
def v2_list_delete_jobs(
    info: TokenInfo = Depends(require_token),
) -> V2DeleteJobsResponse:
    """UI-feedback · returnerar status för pågående och nyligen klara
    student-raderingar för aktuell lärare. Frontend pollar denna under
    pågående delete för att visa 'Raderar…' / 'Klar' / 'Fel' i kolumnen
    där eleven låg innan klick.

    Jobb äldre än 5 min städas bort så listan inte växer obegränsat.
    """
    teacher_id = _require_teacher(info)
    import time as _t_l
    now = _t_l.time()
    # GC: ta bort gamla klara/failed-jobb äldre än 5 min
    stale_cutoff = now - 300
    for sid in list(_delete_jobs.keys()):
        j = _delete_jobs[sid]
        if (
            j.get("status") in ("done", "failed")
            and (j.get("finished_at") or 0) < stale_cutoff
        ):
            del _delete_jobs[sid]

    rows: list[V2DeleteJobRow] = []
    pending = 0
    for sid, j in _delete_jobs.items():
        if j.get("teacher_id") != teacher_id:
            continue
        rows.append(V2DeleteJobRow(
            student_id=sid,
            student_name=j.get("student_name") or f"Elev {sid}",
            status=j.get("status", "queued"),  # type: ignore[arg-type]
            started_at=float(j.get("started_at") or now),
            finished_at=j.get("finished_at"),
            error=j.get("error"),
        ))
        if j.get("status") in ("queued", "running"):
            pending += 1
    rows.sort(key=lambda r: -r.started_at)
    return V2DeleteJobsResponse(rows=rows, pending_count=pending)


class V2BulkDeleteResponse(BaseModel):
    deleted_count: int
    failed_count: int
    failed_ids: list[int] = Field(default_factory=list)


# In-memory job-tracker för bulk-delete. Async så frontend inte hänger
# på 30+ sekunder (Postgres CASCADE kan ta tid med många FK).
# {teacher_id: {"status": "running"|"done"|"failed", "deleted_count": N, ...}}
_bulk_delete_jobs: dict[int, dict] = {}


def _bulk_delete_worker(teacher_id: int) -> None:
    """Bakgrunds-task som faktiskt utför raderingen. Skriver
    progress till _bulk_delete_jobs[teacher_id]."""
    import logging as _logging_b
    log = _logging_b.getLogger(__name__)
    job = _bulk_delete_jobs.setdefault(teacher_id, {})
    job.update(status="running", deleted_count=0, failed_count=0)
    try:
        from ..db.base import Base, TenantMixin

        # Hämta scope-keys
        with master_session() as ms:
            student_rows = (
                ms.query(Student.id, Student.family_id)
                .filter(Student.teacher_id == teacher_id)
                .all()
            )
            if not student_rows:
                job.update(status="done", deleted_count=0)
                return
            scope_keys = list({
                f"f_{fid}" if fid else f"s_{sid}"
                for sid, fid in student_rows
            })
            student_ids = [r[0] for r in student_rows]

        log.info(
            "bulk-delete-worker: teacher=%s, %d elever, %d scopes",
            teacher_id, len(student_ids), len(scope_keys),
        )

        # Batch-DELETE per tabell
        try:
            from ..school.engines import _init_shared_scope_engine
            import os as _os_pg
            if _os_pg.environ.get("HEMBUDGET_DATABASE_URL", "").strip():
                _, session_maker = _init_shared_scope_engine()
                with session_maker() as ss:
                    for table in reversed(Base.metadata.sorted_tables):
                        cls = next(
                            (
                                c.class_ for c in Base.registry.mappers
                                if c.local_table is table
                            ),
                            None,
                        )
                        if (cls is None
                                or not issubclass(cls, TenantMixin)):
                            continue
                        try:
                            ss.query(cls).filter(
                                cls.tenant_id.in_(scope_keys),
                            ).delete(synchronize_session=False)
                        except Exception:
                            log.exception(
                                "bulk-delete-worker: %s failed",
                                cls.__name__,
                            )
                    ss.commit()
            else:
                from ..school.engines import _scope_db_path
                for scope_key in scope_keys:
                    try:
                        path = _scope_db_path(scope_key)
                        if path and path.exists():
                            path.unlink()
                    except Exception:
                        pass
        except Exception:
            log.exception(
                "bulk-delete-worker: scope-cleanup phase failed",
            )

        # Master-radering
        deleted = 0
        try:
            with master_session() as s:
                n = (
                    s.query(Student)
                    .filter(Student.teacher_id == teacher_id)
                    .delete(synchronize_session=False)
                )
                s.commit()
                deleted = int(n)
        except Exception:
            log.exception(
                "bulk-delete-worker: master-delete failed för "
                "teacher %s",
                teacher_id,
            )
            job.update(
                status="failed",
                deleted_count=deleted,
                failed_count=len(student_ids),
                failed_ids=student_ids,
                error="Master delete failed (se Cloud Logging)",
            )
            return

        job.update(
            status="done",
            deleted_count=deleted,
            failed_count=0,
        )
        log.info(
            "bulk-delete-worker: KLART teacher=%s, deleted=%d",
            teacher_id, deleted,
        )
    except Exception as e:
        log.exception(
            "bulk-delete-worker: total failure för teacher %s",
            teacher_id,
        )
        job.update(status="failed", error=str(e)[:300])


@router.delete(
    "/teacher/bulk-delete-all-my-students",
)
def v2_delete_all_my_students(
    background_tasks: BackgroundTasks,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Starta bakgrunds-radering av alla teachers elever.

    Returnerar OMEDELBART (inom ms) med job_id. Frontend pollar
    /v2/teacher/bulk-delete-status för progress.

    Tidigare körde detta synkront — Postgres CASCADE på 30+ tabeller
    kunde ta 30-60 s, frontend hängde och såg ut som om inget hände.
    Nu schemaläggs som BackgroundTask + status-endpoint.
    """
    teacher_id = _require_teacher(info)
    # Reset job state
    _bulk_delete_jobs[teacher_id] = {
        "status": "queued",
        "deleted_count": 0,
        "failed_count": 0,
    }
    background_tasks.add_task(_bulk_delete_worker, teacher_id)
    return {"status": "queued", "teacher_id": teacher_id}


@router.get("/teacher/bulk-delete-status")
def v2_bulk_delete_status(
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Polla för status på pågående bulk-delete."""
    teacher_id = _require_teacher(info)
    job = _bulk_delete_jobs.get(teacher_id)
    if job is None:
        return {"status": "idle"}
    return job



@router.post(
    "/teacher/students/{student_id}/reseed-initial-data",
    response_model=V2ReseedResponse,
)
def teacher_reseed_initial_data(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2ReseedResponse:
    """Lärare triggar OM seed för en elev.

    Använder samma flöde som auto-recovery vid student-detail. Idempotent
    — om eleven redan har data svarar vi seeded=False utan fel.

    Bug-fix för 'seed failed': om en elev har stuck failed runs kan
    läraren trigga reseed manuellt från UI-knappen i spelmotor-panelen.

    Vid fel returneras error_detail + last_failed_run så vi kan se
    rotorsaken direkt i UI:t.
    """
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        student = mdb.get(Student, student_id)
        if not student or student.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Endast egen elev",
            )
        student_name = student.display_name
        v2_level = getattr(student, "v2_level", None) or 1
        spend_profile = (
            getattr(student, "v2_spend_profile", None) or "balanserad"
        )
        partner = getattr(student, "v2_partner_model", None) or "solo"

    # Försök seed:a · fångas exception:s så vi kan returnera diagnostik
    seed_error: Optional[str] = None
    try:
        seeded = _ensure_student_has_initial_data(
            student_id=student_id,
            student_name=student_name,
            spend_profile=spend_profile,
            starting_level=v2_level,
            partner_model=partner,
        )
    except Exception as exc:
        seeded = False
        seed_error = f"{type(exc).__name__}: {exc}"
        import logging
        logging.getLogger(__name__).exception(
            "reseed-initial-data failed för student %s", student_id,
        )

    # Hämta senaste failed run för diagnostik
    last_failed: Optional[dict] = None
    from ..school.game_engine_models import WeekTickRun
    with master_session() as s:
        completed_count = (
            s.query(WeekTickRun)
            .filter(
                WeekTickRun.student_id == student_id,
                WeekTickRun.status == "completed",
            )
            .count()
        )
        if completed_count == 0:
            failed = (
                s.query(WeekTickRun)
                .filter(
                    WeekTickRun.student_id == student_id,
                    WeekTickRun.status == "failed",
                )
                .order_by(WeekTickRun.started_at.desc())
                .first()
            )
            if failed:
                last_failed = {
                    "year_month": failed.year_month,
                    "seed": failed.seed_used,
                    "error": failed.error_message,
                }

    success = seeded or completed_count > 0
    if success and seeded:
        message = (
            "Seed kördes. Eleven har nu lön, fakturor, försäkringar "
            "och pension."
        )
    elif success:
        message = "Eleven hade redan data — ingen reseed behövdes."
    else:
        message = (
            f"Seed misslyckades: {seed_error or 'okänt fel'}. "
            f"Se error_detail nedan för detaljer."
        )

    return V2ReseedResponse(
        student_id=student_id,
        seeded=seeded,
        success=success,
        message=message,
        error_detail=seed_error
        or (last_failed.get("error") if last_failed else None),
        last_failed_run=last_failed,
    )


def _ensure_student_has_initial_data(
    *,
    student_id: int,
    student_name: str,
    spend_profile: str,
    starting_level: int,
    partner_model: str,
) -> bool:
    """Auto-recovery · garanterar att en elev har initial data.

    Bug-fix för 'seed failed' på gamla elever:
    Om eleven inte har EN ENDA WeekTickRun med status='completed',
    så har den aldrig fått initial-data (eller alla försök har failat).
    Kör seed-flödet igen.

    Returnerar True om seed kördes, False om eleven redan har data.

    Idempotent: säker att anropa flera gånger. _check_and_create_run i
    tick_month rensar partial state innan retry.
    """
    from ..school.game_engine_models import WeekTickRun
    from ..school.models import Student as _Stu

    with master_session() as s:
        completed_runs = (
            s.query(WeekTickRun)
            .filter(
                WeekTickRun.student_id == student_id,
                WeekTickRun.status == "completed",
            )
            .count()
        )
        if completed_runs > 0:
            return False  # Eleven har redan data
        student = s.get(_Stu, student_id)
        if student is None:
            return False
        s.expunge(student)

    # Eleven saknar data → kör seed
    import logging
    logging.getLogger(__name__).info(
        "auto-recovery: seed initial data för student %s (%s) "
        "eftersom WeekTickRun completed = 0",
        student_id, student_name,
    )
    _seed_initial_student_data(
        student,
        spend_profile=spend_profile,
        starting_level=starting_level,
        partner_model=partner_model,
    )
    # Sätt seed_status='complete' så frontend-overlayn lyfts om eleven
    # var pending eller stuck i 'failed' tidigare. Auto-recovery har just
    # garanterat att data finns → eleven kan rendera vyer normalt.
    try:
        with master_session() as s_done:
            stu_done = s_done.get(_Stu, student_id)
            if stu_done is not None and stu_done.seed_status != "complete":
                stu_done.seed_status = "complete"
                s_done.flush()
    except Exception:
        logging.getLogger(__name__).exception(
            "auto-recovery: kunde inte uppdatera seed_status='complete' "
            "för student %s — seedat ok men overlayn kan hänga",
            student_id,
        )
    return True


def _auto_pay_historical_invoices(
    student: "Student", year_month: str,
    cutoff_date: Optional[_date] = None,
) -> None:
    """Markera alla fakturor från en historisk månad som BETALDA via
    autogiro + skapa motsvarande Transaction från lönekonto.

    Pedagogiskt: förra månaden HAR redan hänt — fakturor som
    seedats av fixed_expenses ska inte ligga som "ohanterade" i
    postlådan. Vi simulerar att autogiro drog dem på due_date.

    Idempotent via stable hash. year_month = "YYYY-MM".

    `cutoff_date` (valfritt): Om satt, betala bara fakturor där
    due_date < cutoff_date. Används för innevarande månad så bara
    redan-förfallna fakturor auto-betalas (= "i dag är 6 maj och
    hyran för 1 maj är förfallen, ska redan vara dragen").
    """
    from datetime import date as _d_pay
    from hashlib import sha256 as _sha
    from ..db.models import Account, MailItem, Transaction
    from ..school.engines import (
        scope_context as _sctx_p, scope_for_student as _sfs_p,
    )

    try:
        y, m = map(int, year_month.split("-"))
        period_start = _d_pay(y, m, 1)
        period_end = (
            _d_pay(y + 1, 1, 1) if m == 12 else _d_pay(y, m + 1, 1)
        )
    except Exception:
        return

    # Cutoff: inom innevarande månad vill vi bara dra det som
    # faktiskt redan förfallit, inte allt som ska komma framöver.
    effective_end = period_end
    if cutoff_date is not None and cutoff_date < period_end:
        effective_end = cutoff_date

    scope_key = _sfs_p(student)
    with _sctx_p(scope_key):
        with session_scope() as s:
            lonekonto = (
                s.query(Account)
                .filter(Account.type == "checking")
                .order_by(Account.id.asc())
                .first()
            )
            if lonekonto is None:
                return
            mails = (
                s.query(MailItem)
                .filter(
                    # Salary_slip OCH invoice tas båda — lönespec från
                    # förra månaden är också "historik" och ska inte
                    # ligga som ohanterad i postlådan när månaden är slut.
                    MailItem.mail_type.in_(["invoice", "salary_slip"]),
                    MailItem.status.in_(["unhandled", "viewed"]),
                    MailItem.due_date >= period_start,
                    MailItem.due_date < effective_end,
                )
                .all()
            )
            for m_inv in mails:
                if m_inv.amount is None:
                    continue
                # Stabilt idempotent-hash baserat på mail_id + period
                raw = f"autopaid|{student.id}|{year_month}|{m_inv.id}"
                tx_hash = _sha(raw.encode()).hexdigest()[:32]
                existing = (
                    s.query(Transaction)
                    .filter(Transaction.hash == tx_hash)
                    .first()
                )
                # För invoice: skapa autogiro-transaktion (utgift).
                # För salary_slip: lönen är redan transakterad av
                # salary_phase.py (en separat Transaction-rad), så vi
                # markerar bara mailet som hanterat — ingen extra tx.
                if existing is None and m_inv.mail_type == "invoice":
                    tx = Transaction(
                        account_id=lonekonto.id,
                        date=m_inv.due_date or period_start,
                        amount=m_inv.amount,  # negativt = utgift
                        currency="SEK",
                        raw_description=(
                            f"Autogiro · {m_inv.sender}"
                        ),
                        normalized_merchant=m_inv.sender,
                        hash=tx_hash,
                        is_transfer=False,
                        user_verified=True,
                    )
                    s.add(tx)
                m_inv.status = "paid"
            s.commit()


# Bounded parallelism för seed-jobb. Tidigare kunde 20+ background-
# seeds köra parallellt när läraren batch-skapade elever, vilket
# spräckte både Cloud SQL-poolen (varje seed öppnar 5+ scope-sessions)
# och 1 GiB-minnesgränsen. Med max 2 samtidiga seeds får vi naturlig
# back-pressure utan att blockera UI:t.
import threading as _threading_seed
_SEED_CONCURRENCY = 2
_seed_semaphore = _threading_seed.Semaphore(_SEED_CONCURRENCY)


# === Dunning · automatisk eskalering av obetalda fakturor =========
#
# Verkligt svenskt påminnelse-flöde:
#   5 dgr efter förfall  → Påminnelse  (60 kr avgift, lagstadgat max)
#   14 dgr efter förfall → Sista påminnelsen (60 kr nytt avgift)
#   30 dgr efter förfall → Inkassokrav (180 kr, lagstadgat max enligt
#                                       inkassolagen § 5)
#   60 dgr efter förfall → Kronofogden · betalningsföreläggande
#                          (600 kr ansökan + betalningsanmärkning)
#
# Triggers vid varje GET /v2/hub och GET /v2/postladan, cachat 60s
# per elev så vi inte kör helpern flera gånger på rad. En MailItem
# räknas som BETALD (= ingen reminder triggas) när:
#   1. mail.status == "paid", ELLER
#   2. mail.upcoming_id är satt och tillhörande UpcomingTransaction
#      har matched_transaction_id != NULL (autogiro/manuell tx matchade)
#
# Att bara EXPORTERA en faktura räcker INTE — pengarna måste faktiskt
# ha lämnat kontot. Path 2 (eleven gjorde inget alls, ingen Upcoming)
# eskaleras också via mail-fältet direkt.

_dunning_cache: dict[int, float] = {}  # student_id → last-run-ts
_DUNNING_CACHE_TTL = 60.0  # sekunder


# === Skatteverket · deklaration-events =====================
#
# När spel-tiden passerar 2 mars/17 mars/31 mars/4 maj varje år
# triggar vi mail från Skatteverket som följer SKV:s riktiga tids-
# linje. Eleven ser deklaration-fönstret öppna och stänga, kan
# lämna in i tid och få återbäring i april — eller missa deadline
# och få förseningsavgift.
#
# Spel-tiden börjar 2026-01-01. Första deklarationen (för 2026)
# blir tillgänglig 2027-03-02 = 14.5 real-dagar in. Förstaårs-
# studenter hinner se ETT helt deklaration-flöde inom 4 veckors
# elev-tid.

_SKV_EVENTS_CACHE: dict[int, float] = {}
_SKV_EVENTS_TTL = 300.0  # 5 min


def _seed_skv_deklaration_events(student_id: int) -> int:
    """Skapa Skatteverket-deklaration-mail när spel-tiden passerar
    SKV:s tidslinje. Idempotent · cache-gated (5 min). Tysta fel.

    Trigger-datum per spel-år Y (deklaration för år Y-1):
        Y mars 2:  Din deklaration finns i digital brevlåda
        Y mars 17: Du kan deklarera nu
        Y mars 31: Sista dag för digital deklaration + ev. återbäring
        Y maj 4:   Sista dag att deklarera

    Returnerar antal nya mail.
    """
    import time as _t_skv
    last_run = _SKV_EVENTS_CACHE.get(student_id, 0.0)
    if _t_skv.time() - last_run < _SKV_EVENTS_TTL:
        return 0
    _SKV_EVENTS_CACHE[student_id] = _t_skv.time()

    try:
        from datetime import date as _d_skv
        from ..game_engine.release_schedule import (
            GAME_ANCHOR_DATE,
            game_date_for,
        )
        from ..school.engines import (
            scope_context as _sctx_skv,
            scope_for_student as _sfs_skv,
        )
        from ..db.models import MailItem as _MI_skv

        with master_session() as ms:
            stu = ms.get(Student, student_id)
            if stu is None or stu.created_at is None:
                return 0

        gy, gm, gd = game_date_for(stu.created_at)
        try:
            current_game_d = _d_skv(gy, gm, max(1, min(28, gd)))
        except Exception:
            return 0

        # Bygg list av alla SKV-milstolpar som passerats sedan anchor.
        # 7 händelser totalt enligt riktiga Skatteverkets kalender.
        skv_steps = [
            (
                "skv_brevlada", _d_skv.fromisoformat,
                "Din deklaration finns i digital brevlåda",
                "Hej. Din inkomstdeklaration för {prev_year} ligger nu "
                "i digitala brevlådan. Du kan börja granska direkt — "
                "själva inlämningen öppnar 17 mars. Kontrollera "
                "förtryckta uppgifter, ev. ROT/RUT-arbeten, ränteavdrag.",
                3, 2,  # mars 2
            ),
            (
                "skv_kvarskatt",
                _d_skv.fromisoformat,
                "Påminnelse · sista dag att betala kvarskatt",
                "Idag är sista dagen att betala eventuell kvarskatt "
                "från slutskattebesked {prev_prev_year}. Sen betalning "
                "ger kostnadsränta. Om du inte hade kvarskatt: bortse "
                "från detta mail.",
                3, 12,  # mars 12
            ),
            (
                "skv_open", _d_skv.fromisoformat,
                "Du kan deklarera nu",
                "Inlämningstjänsten är öppen. Lämna in senast 31 mars "
                "om du vill ha eventuell skatteåterbäring i april. "
                "Sista dag totalt är 4 maj.",
                3, 17,
            ),
            (
                "skv_digital_deadline",
                _d_skv.fromisoformat,
                "Digital deadline · skatteåterbäring i april",
                "Idag är sista dag att deklarera digitalt för att "
                "garantera skatteåterbäring i april. Efter detta "
                "betalas eventuell återbäring i juni–augusti.",
                3, 31,
            ),
            (
                "skv_wave1",
                _d_skv.fromisoformat,
                "Skatteåterbäring · våg 1",
                "Idag–10 april betalas årets första våg av "
                "skatteåterbäring ut till dig som godkänt din "
                "deklaration utan att ändra något. Kontrollera ditt "
                "lönekonto. Om du fortfarande inte deklarerat — gör "
                "det senast 4 maj.",
                4, 7,  # april 7
            ),
            (
                "skv_final_deadline",
                _d_skv.fromisoformat,
                "Sista dag att deklarera",
                "Idag är ALLRA SISTA dagen att lämna in deklarationen. "
                "Missar du deadline blir det förseningsavgift "
                "(1 250 kr första gången, 6 250 kr om du fortsatt "
                "inte deklarerar).",
                5, 4,
            ),
            (
                "skv_wave2",
                _d_skv.fromisoformat,
                "Skatteåterbäring · våg 2",
                "Idag–12 juni betalas årets andra våg av "
                "skatteåterbäring ut till dig som deklarerat senast "
                "4 maj. Kontrollera ditt lönekonto. Detta är sista "
                "ordinarie utbetalningsvåg för i år.",
                6, 9,  # juni 9
            ),
        ]

        # För varje passerat SKV-fönster (varje år sedan ANCHOR-året)
        scope_key = _sfs_skv(stu)
        n_created = 0
        with _sctx_skv(scope_key):
            with session_scope() as s:
                # Loopa år från ANCHOR_YEAR + 1 (första deklaration)
                # till current_game_year. För varje år: kolla varje
                # SKV-step och skapa mail om datumet passerats och
                # mailet inte finns redan.
                for tax_year in range(
                    GAME_ANCHOR_DATE.year + 1, gy + 1,
                ):
                    prev_year = tax_year - 1
                    for (
                        kind, _parse, subject, body_tmpl, mm, dd,
                    ) in skv_steps:
                        try:
                            milestone_d = _d_skv(tax_year, mm, dd)
                        except Exception:
                            continue
                        if milestone_d > current_game_d:
                            continue  # inte passerat än
                        # Idempotens · samma year+kind = en mail
                        unique_subj = (
                            f"{subject} · {prev_year}"
                        )
                        existing = (
                            s.query(_MI_skv)
                            .filter(_MI_skv.subject == unique_subj)
                            .first()
                        )
                        if existing is not None:
                            continue
                        body = (
                            body_tmpl
                            .replace("{prev_year}", str(prev_year))
                            .replace(
                                "{prev_prev_year}", str(prev_year - 1),
                            )
                        )
                        s.add(_MI_skv(
                            sender="Skatteverket",
                            sender_short="SKV",
                            sender_kind="agency",
                            sender_meta=(
                                f"Deklaration {prev_year}"
                            ),
                            mail_type="authority",
                            subject=unique_subj,
                            body_meta=f"Deklaration · {prev_year}",
                            body=body,
                            amount=None,
                            due_date=milestone_d if kind in (
                                "skv_digital_deadline",
                                "skv_final_deadline",
                            ) else None,
                            status="unhandled",
                            released_at=None,
                        ))
                        n_created += 1
                if n_created > 0:
                    s.commit()
        return n_created
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_seed_skv_deklaration_events failed för student %s",
            student_id,
        )
        return 0

# Auto-tick-månader · cacha 5 min så vi inte tickar samma månad
# flera gånger per request-burst.
_auto_tick_month_cache: dict[int, float] = {}
_AUTO_TICK_MONTH_TTL = 300.0  # 5 min


def _auto_tick_private_months_if_due(student_id: int) -> int:
    """Tick fram saknade privat-månader baserat på speltid sedan
    student.created_at. Eleven driver karaktären framåt: 1 real-timme
    = 1 spel-vecka, så efter ~4 real-timmar har en ny månad startat.

    Idempotent · cachat så endast 1 körning per 5 min/elev. Tysta
    fel — får aldrig ta ner request:en.

    Returnerar antal månader som tickats.
    """
    import time as _t_at
    last = _auto_tick_month_cache.get(student_id, 0.0)
    if _t_at.time() - last < _AUTO_TICK_MONTH_TTL:
        return 0
    _auto_tick_month_cache[student_id] = _t_at.time()

    try:
        from datetime import datetime as _dt_at, timedelta as _td_at
        from ..game_engine.release_schedule import game_year_month
        from ..game_engine.profile_generator import generate_profile
        from ..game_engine.monthly_engine import tick_month
        from ..school.engines import (
            scope_context as _sctx_at, scope_for_student as _sfs_at,
        )
        from ..db.models import MailItem as _MI_at

        with master_session() as ms:
            stu = ms.get(Student, student_id)
            if stu is None:
                return 0
            created_at = stu.created_at
            display_name = stu.display_name or "Elev"
            sp = (
                ms.query(StudentProfile)
                .filter(StudentProfile.student_id == student_id)
                .first()
            )
            starting_level = (
                getattr(stu, "v2_level", None) or 1
            )
            partner_model = (
                getattr(stu, "v2_partner_model", None) or "solo"
            )
            spend_profile = (
                getattr(stu, "v2_spend_profile", None) or "balanserad"
            )

        if created_at is None:
            return 0
        # game_year_month använder GAME_ANCHOR_DATE (2026-01-01) som
        # spel-startpunkt. Andra argumentet är legacy och ignoreras.
        current_game_ym = game_year_month(created_at)

        # Hitta senast tickade ym = senaste COMPLETED WeekTickRun för
        # eleven. Tidigare läste vi MAX(MailItem.due_date) som proxy,
        # men due_date är FRAMTIDA (en faktura med förfallodag 2026-12)
        # gjorde att auto-tick stannade redan vid första seedade
        # månaden — alla efterföljande månader skippades och eleven
        # fick aldrig nya fakturor/lönespecs efter ungefär den
        # första spel-månaden.
        from ..school.game_engine_models import WeekTickRun
        latest_ym: Optional[str] = None
        with master_session() as ms_run:
            latest_run = (
                ms_run.query(WeekTickRun.year_month)
                .filter(
                    WeekTickRun.student_id == student_id,
                    WeekTickRun.status == "completed",
                )
                .order_by(WeekTickRun.year_month.desc())
                .first()
            )
            if latest_run is not None and latest_run[0]:
                latest_ym = latest_run[0]

        if latest_ym is None:
            # BOOTSTRAP-FIX: ingen completed run än (seed misslyckades
            # eller städades). Ticka från månaden FÖRE anchor så
            # historiska månader fylls + anchor-månaden seedas.
            from ..game_engine.release_schedule import (
                GAME_ANCHOR_DATE,
            )
            if GAME_ANCHOR_DATE.month == 1:
                latest_ym = (
                    f"{GAME_ANCHOR_DATE.year - 1:04d}-12"
                )
            else:
                latest_ym = (
                    f"{GAME_ANCHOR_DATE.year:04d}-"
                    f"{GAME_ANCHOR_DATE.month - 1:02d}"
                )

        # Tick alla månader mellan latest_ym+1 och current_game_ym
        if latest_ym >= current_game_ym:
            return 0  # inget nytt att ticka

        # Bygg list över year_months att ticka (max 12 per körning så
        # vi inte hänger en request om en elev varit borta länge)
        ly, lm = (int(p) for p in latest_ym.split("-"))
        cy, cm = (int(p) for p in current_game_ym.split("-"))
        to_tick: list[str] = []
        ny, nm = ly, lm
        while True:
            nm += 1
            if nm > 12:
                nm = 1
                ny += 1
            if (ny, nm) > (cy, cm):
                break
            to_tick.append(f"{ny:04d}-{nm:02d}")
            if len(to_tick) >= 12:
                break

        if not to_tick:
            return 0

        # Bygg profile (samma seed som vid skapandet)
        profile = generate_profile(
            seed=student_id,
            archetype="random",
            starting_level=starting_level,
            name=display_name,
            partner_model=partner_model,
        )

        # Hämta student-objektet i master för tick_month
        with master_session() as ms2:
            stu_full = ms2.get(Student, student_id)
            if stu_full is None:
                return 0

            for ym in to_tick:
                try:
                    tick_month(
                        stu_full,
                        profile,
                        ym,
                        spend_profile=spend_profile,
                        starting_level=starting_level,
                    )
                    # Auto-betala fakturor i den månaden — eleven har
                    # passerat den i speltid, så autogiro har hunnit dra
                    # alla löpande utgifter
                    _auto_pay_historical_invoices(stu_full, ym)
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception(
                        "_auto_tick_private_months_if_due: tick %s "
                        "failed för student %s",
                        ym, student_id,
                    )
                    break

        return len(to_tick)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_auto_tick_private_months_if_due failed för student %s",
            student_id,
        )
        return 0


_AUTOGIRO_DEBIT_CACHE: dict[int, float] = {}
_AUTOGIRO_DEBIT_TTL = 60.0  # cache-gated 60s · billig nog att köra ofta


def _auto_debit_signed_upcomings_if_due(student_id: int) -> int:
    """Drag pengar från signerade UpcomingTransaction:s vars
    expected_date passerat (i spel-tid).

    Vid signering (autogiro=True via BankID) markerar vi en upcoming
    som auktoriserad. När förfallodagen kommer SKA banken dra pengarna
    automatiskt. Tidigare buggen: ingen auto-debit fanns → eleven
    signerade på Jan 1, dag 2 visade banken '1 d sen' istället för
    'drogs Jan 1'.

    Skapar Transaction(amount=−belopp, account_id=debit_account_id),
    sätter UpcomingTransaction.matched_transaction_id. Om saldo
    saknas → markerar UpcomingTransaction.autogiro=False och låter
    raden bli osignerad igen så eleven måste betala manuellt eller
    fylla på lönekontot. Idempotent: dedup via tx.hash.

    Cache-gated 60s/elev. Tysta fel — får inte ta ner request.
    """
    import time as _t_ad
    last = _AUTOGIRO_DEBIT_CACHE.get(student_id, 0.0)
    if _t_ad.time() - last < _AUTOGIRO_DEBIT_TTL:
        return 0
    _AUTOGIRO_DEBIT_CACHE[student_id] = _t_ad.time()

    try:
        from datetime import datetime as _dt_ad
        from decimal import Decimal as _Dec_ad
        from hashlib import sha256 as _sha_ad
        from ..business.game_clock import (
            current_game_date_for_student as _cgdfs,
        )
        from ..school.engines import (
            scope_context as _sctx_ad, scope_for_student as _sfs_ad,
        )
        from ..school.models import Student as _Stu_ad

        with master_session() as ms:
            stu = ms.get(_Stu_ad, student_id)
            if stu is None:
                return 0
            scope_key = _sfs_ad(stu)

        today_game = _cgdfs(student_id)
        n_debited = 0
        with _sctx_ad(scope_key):
            with session_scope() as s:
                # Hitta signerade upcomings vars förfallodag passerat
                # och som ännu inte är matchade mot Transaction.
                due = (
                    s.query(UpcomingTransaction)
                    .filter(
                        UpcomingTransaction.autogiro.is_(True),
                        UpcomingTransaction.matched_transaction_id.is_(None),
                        UpcomingTransaction.expected_date <= today_game,
                    )
                    .all()
                )
                if not due:
                    return 0

                # Default-konto för debit · första checking om upcoming
                # inte explicit pekar på ett.
                default_acc = (
                    s.query(Account)
                    .filter(Account.type == "checking")
                    .order_by(Account.id.asc())
                    .first()
                )
                if default_acc is None:
                    return 0

                for u in due:
                    acc_id = u.debit_account_id or default_acc.id
                    # Saldo-kontroll · matchar UI:s _released_filter
                    # (Transaction.released_at <= NOW eller NULL) plus
                    # cappar mot u.expected_date så framtida planerade
                    # lönen INTE räknas som "tillgänglig nu". Tidigare
                    # bug: bal_q summerade ALLA tx oavsett released_at
                    # → backend trodde 6 434 kr fanns medan UI:t visade
                    # 5 798 → faktura drogs och saldo blev -691.
                    from sqlalchemy import func as _sql_func, or_ as _sql_or
                    bal_q = (
                        s.query(
                            _sql_func.coalesce(
                                _sql_func.sum(Transaction.amount), 0,
                            )
                        )
                        .filter(
                            Transaction.account_id == acc_id,
                            Transaction.date <= u.expected_date,
                            _sql_or(
                                Transaction.released_at.is_(None),
                                Transaction.released_at <= _dt_ad.utcnow(),
                            ),
                        )
                    )
                    base = s.get(Account, acc_id)
                    bal = (
                        (_Dec_ad(str(base.opening_balance or 0)))
                        + (_Dec_ad(str(bal_q.scalar() or 0)))
                    )
                    if bal < u.amount:
                        # Otillräckligt saldo · släpp signaturen så
                        # raden blir osignerad och eleven kan agera.
                        u.autogiro = False
                        # Markera ev. relaterat MailItem som FAILED
                        # så eleven ser fakturan i "Misslyckade"-flik
                        # och kan trycka 'Försök igen' efter påfyllning.
                        related_fail = (
                            s.query(MailItem)
                            .filter(MailItem.upcoming_id == u.id)
                            .first()
                        )
                        sender_name = (
                            related_fail.sender if related_fail else u.name
                        )
                        if related_fail is not None:
                            related_fail.status = "failed"
                        # Pedagogiskt failed-mail från Spelbanken
                        shortfall = int(u.amount - bal)
                        fail_subj = (
                            f"Betalning misslyckades · {sender_name} "
                            f"{int(u.amount)} kr"
                        )
                        # Idempotent · skapa inte dubbletter om
                        # auto-debit kallas flera gånger för samma upcoming
                        existing_fail = (
                            s.query(MailItem)
                            .filter(MailItem.subject == fail_subj)
                            .first()
                        )
                        if existing_fail is None:
                            s.add(MailItem(
                                sender="Spelbanken",
                                sender_short="BNK",
                                sender_kind="financial",
                                sender_meta=(
                                    f"Autogiro-retur · {u.expected_date.isoformat()}"
                                ),
                                mail_type="info",
                                subject=fail_subj,
                                body_meta=(
                                    f"Saknades {shortfall} kr · "
                                    f"saldo {int(bal)} kr"
                                ),
                                body=(
                                    f"Hej! Vi försökte dra "
                                    f"{int(u.amount)} kr till "
                                    f"{sender_name} idag "
                                    f"({u.expected_date.isoformat()}) "
                                    f"men kontot hade bara {int(bal)} kr "
                                    f"— du saknade {shortfall} kr.\n\n"
                                    f"Vad händer nu?\n"
                                    f"• Fakturan ligger kvar som "
                                    f"OBETALD i postlådan.\n"
                                    f"• Fyll på lönekontot (t.ex. flytta "
                                    f"från sparkontot via 'Ny överföring' "
                                    f"i bankvyn).\n"
                                    f"• Gå tillbaka till fakturan och "
                                    f"klicka 'Försök igen' så drar vi "
                                    f"om i nästa spel-vecka.\n"
                                    f"• Om du inte agerar börjar "
                                    f"leverantören skicka påminnelser "
                                    f"(60 kr extra avgift första gången, "
                                    f"sen 60 kr, sen inkasso).\n\n"
                                    f"Vänliga hälsningar,\n"
                                    f"Spelbanken"
                                ),
                                amount=u.amount,
                                due_date=u.expected_date,
                                status="unhandled",
                                released_at=None,
                            ))
                        continue

                    # Idempotent hash · samma signering får aldrig
                    # skapa två transaktioner.
                    raw = (
                        f"autogiro|{student_id}|{u.id}|"
                        f"{u.expected_date.isoformat()}|{u.amount}"
                    )
                    tx_hash = _sha_ad(raw.encode()).hexdigest()[:32]
                    existing = (
                        s.query(Transaction)
                        .filter(Transaction.hash == tx_hash)
                        .first()
                    )
                    if existing is not None:
                        # Redan dragen tidigare körning · matcha
                        u.matched_transaction_id = existing.id
                        continue

                    tx = Transaction(
                        account_id=acc_id,
                        date=u.expected_date,
                        amount=-_Dec_ad(str(u.amount)),
                        currency="SEK",
                        raw_description=f"Autogiro · {u.name}",
                        normalized_merchant=u.name,
                        hash=tx_hash,
                        is_transfer=False,
                        user_verified=True,
                    )
                    s.add(tx)
                    s.flush()
                    u.matched_transaction_id = tx.id

                    # Om upcoming länkar till en MailItem → markera
                    # mailet som paid också (annars dyker faktura
                    # upp som ohanterad i postlådan trots dragning).
                    related_mail = (
                        s.query(MailItem)
                        .filter(MailItem.upcoming_id == u.id)
                        .first()
                    )
                    if related_mail is not None:
                        related_mail.status = "paid"
                    n_debited += 1
                s.commit()
        return n_debited
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_auto_debit_signed_upcomings_if_due failed för student %s",
            student_id,
        )
        return 0


_RECEIVED_AT_NORMALIZED: dict[int, float] = {}
_RECEIVED_AT_NORMALIZE_TTL = 600.0  # 10 min · idempotent


def _normalize_mail_received_at_if_seed_stamped(student_id: int) -> int:
    """Migrationsfix · stäm ihop MailItem.received_at med spel-tid.

    Kontext: tidigare seed-flöden stämplade alla MailItems med
    server_default=func.now() (= real-tid när seed kördes). Resultatet
    blev att postlådan visade "Senaste utskick 7 maj 19:39" och
    fakturadatum "7 maj 2026" på ALLA mail trots att de gällde januari.

    Två normaliseringsfall:
    A. due_date satt → sätt received_at = due_date - 14d (3d för lönespec)
       så fakturadatum/lönespec-datum visas i samma månad som due_date.
    B. due_date saknas (info-mail) → konvertera real-tid → spel-tid via
       real_to_game_datetime(student.created_at, m.received_at). Då
       hamnar info-mail som "Du kan nu driva eget" på rätt spel-vecka.

    Idempotent · normaliserar bara om received_at är "far off" (>60d
    från due_date eller >30d efter aktuell spel-tid). Cache-gated 10 min.
    """
    import time as _t_norm
    last = _RECEIVED_AT_NORMALIZED.get(student_id, 0.0)
    if _t_norm.time() - last < _RECEIVED_AT_NORMALIZE_TTL:
        return 0
    _RECEIVED_AT_NORMALIZED[student_id] = _t_norm.time()

    try:
        from datetime import (
            datetime as _dt_n, timedelta as _td_n, time as _time_n,
        )
        from ..db.models import MailItem as _MI_n
        from ..school.engines import (
            scope_context as _sctx_n, scope_for_student as _sfs_n,
        )
        from ..game_engine.release_schedule import (
            real_to_game_datetime as _r2g_n, game_date_for as _gdf_n,
        )

        with master_session() as ms:
            stu = ms.get(Student, student_id)
            if stu is None or stu.created_at is None:
                return 0
            scope_key = _sfs_n(stu)
            stu_created_at = stu.created_at

        # Beräkna nuvarande spel-tid · för cutoff i fall B
        try:
            gy_now, gm_now, gd_now = _gdf_n(stu_created_at)
            now_game = _dt_n(gy_now, gm_now, max(1, min(28, gd_now)))
        except Exception:
            now_game = None

        n_normalized = 0
        with _sctx_n(scope_key):
            with session_scope() as s:
                rows = s.query(_MI_n).all()
                for m in rows:
                    if m.received_at is None:
                        continue
                    if m.due_date is not None:
                        # Fall A · faktura/lönespec
                        diff_days = abs(
                            (m.received_at.date() - m.due_date).days
                        )
                        if diff_days <= 60:
                            continue
                        offset_days = (
                            3 if m.mail_type == "salary_slip" else 14
                        )
                        arrival_d = m.due_date - _td_n(days=offset_days)
                        m.received_at = _dt_n.combine(
                            arrival_d, _time_n(8, 30),
                        )
                        n_normalized += 1
                    else:
                        # Fall B · info-mail utan due_date
                        if now_game is None:
                            continue
                        # Är received_at i framtiden enligt spel-tid?
                        if m.received_at <= now_game + _td_n(days=30):
                            continue
                        try:
                            game_dt = _r2g_n(stu_created_at, m.received_at)
                            m.received_at = game_dt
                            n_normalized += 1
                        except Exception:
                            continue
        return n_normalized
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_normalize_mail_received_at: failed för student %s",
            student_id,
        )
        return 0


# Eskaleringssteg · (min_days_overdue, level, kind, fee, label, pent_safety, pent_economy)
_DUNNING_STEPS = [
    (5,  1, "påminnelse",  60,  "Påminnelse",                       -2, 0),
    (14, 2, "påminnelse2", 60,  "Sista påminnelsen",                -3, -1),
    (30, 3, "inkasso",     180, "Inkassokrav",                      -5, -3),
    (60, 4, "kronofogden", 600, "Kronofogden · betalningsföreläggande", -10, -8),
]


def _run_dunning_for_student(
    student_id: int, *, force_run: bool = False,
) -> None:
    """Eskalera obetalda fakturor för en elev. Idempotent + cache-gated.
    Kallas från /v2/hub och /v2/postladan. Tysta fel — får aldrig ta
    ner request:en eftersom det är "live"-uppdatering, inte kärndata.

    Sätter scope-ContextVar internt så helpern fungerar både via
    request-flödet (där middleware sätter den) och vid direkt-anrop
    från tester / batch-jobb.

    `force_run`: kringgår både 60s-cache och 12h-spärren för nya elever.
    Avsedd för tester som verifierar dunning-logik utan att behöva
    backdatera student.created_at.
    """
    import time as _t_dun
    from datetime import date as _d_dun, datetime as _dt_dun, timedelta as _td_dun
    if not force_run:
        last = _dunning_cache.get(student_id, 0.0)
        if _t_dun.time() - last < _DUNNING_CACHE_TTL:
            return
    _dunning_cache[student_id] = _t_dun.time()

    # Resolva scope-key från student_id om ContextVar:n inte är satt
    from ..school.engines import (
        scope_for_student as _sfs_dun, scope_context as _sctx_dun,
        get_current_scope as _gcs_dun,
    )
    from ..school.models import Student as _Stu_dun

    # Spärr · skippa dunning för helt nya elever. Seed-flödet skapar
    # 4 mån historiska fakturor som auto-betalas, men sker async via
    # bakgrundsjobb — ifall eleven hinner öppna postlådan innan
    # seed-sweepen klar skulle dunning eskalera oseedade-betalda
    # invoices till inkasso/kronofogden direkt → eleven startar med
    # massa anmärkningar. 12 timmars buffer ger seed-jobbet tid.
    if not force_run:
        try:
            with master_session() as _ms_dun:
                stu_dun = _ms_dun.get(_Stu_dun, student_id)
                if stu_dun is not None and stu_dun.created_at is not None:
                    age_h = (
                        _dt_dun.utcnow() - stu_dun.created_at
                    ).total_seconds() / 3600.0
                    if age_h < 12.0:
                        return
        except Exception:
            pass

    scope_key = _gcs_dun()
    if not scope_key:
        with master_session() as ms:
            stu = ms.get(_Stu_dun, student_id)
            if stu is None:
                return
            scope_key = _sfs_dun(stu)

    try:
        with _sctx_dun(scope_key), session_scope() as s:
            today = _d_dun.today()
            # Hämta alla potentiellt overdue fakturor + påminnelser
            # som inte är betalda/förfallna.
            candidates = (
                s.query(MailItem)
                .filter(
                    MailItem.mail_type.in_(("invoice", "reminder")),
                    MailItem.status.in_(("unhandled", "viewed", "exported")),
                    MailItem.due_date.isnot(None),
                    MailItem.due_date <= today - _td_dun(days=5),
                )
                .all()
            )
            for orig in candidates:
                # Kolla om den är BETALD via matchad upcoming
                if _is_paid_via_upcoming(s, orig):
                    orig.status = "paid"
                    s.flush()
                    continue

                days_overdue = (today - orig.due_date).days
                # Hitta högsta lämpliga eskaleringsnivå
                target_step = None
                for step in _DUNNING_STEPS:
                    if days_overdue >= step[0]:
                        target_step = step
                if target_step is None:
                    continue

                # Idempotens: kolla om reminder för samma original +
                # nivå redan finns i postlådan
                existing = (
                    s.query(MailItem)
                    .filter(
                        MailItem.mail_type == "reminder",
                        MailItem.parent_mail_id == orig.id,
                        MailItem.reminder_level == target_step[1],
                    )
                    .first()
                )
                if existing is not None:
                    continue

                _create_dunning_mail(s, orig, target_step, student_id)

                # Vid kronofogden-nivå: skapa betalningsanmärkning
                if target_step[1] == 4:
                    _create_payment_mark(s, orig, target_step)

                # Pentagon-delta
                _, _, _, _, _, pent_safety, pent_economy = target_step
                if pent_safety != 0 or pent_economy != 0:
                    try:
                        from ..game_engine.pentagon import apply_pentagon_delta
                        if pent_safety != 0:
                            apply_pentagon_delta(
                                student_id, axis="safety",
                                requested_delta=pent_safety,
                                reason_kind=f"dunning_level_{target_step[1]}",
                                reason_id=orig.id,
                                reason_table="mail_items",
                                explanation=f"{target_step[4]} · {orig.sender}",
                            )
                        if pent_economy != 0:
                            apply_pentagon_delta(
                                student_id, axis="economy",
                                requested_delta=pent_economy,
                                reason_kind=f"dunning_level_{target_step[1]}",
                                reason_id=orig.id,
                                reason_table="mail_items",
                                explanation=f"{target_step[4]} · {orig.sender}",
                            )
                    except Exception:
                        import logging
                        logging.getLogger(__name__).exception(
                            "dunning: pentagon-delta misslyckades",
                        )

                # Vid level 3+ markera original som "expired" (ses inte
                # längre som ohanterad i postlådans active-counter)
                if target_step[1] >= 3:
                    orig.status = "expired"
                    s.flush()

                # Lärar-spårning
                try:
                    from ..school.activity import log_activity
                    log_activity(
                        kind=f"dunning.{target_step[2]}",
                        summary=f"{target_step[4]} skapad: {orig.sender}",
                        payload={
                            "original_mail_id": orig.id,
                            "level": target_step[1],
                            "fee": target_step[3],
                            "days_overdue": days_overdue,
                        },
                    )
                except Exception:
                    pass
            s.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "dunning: helper failed för student=%s — sväljer", student_id,
        )


def _is_paid_via_upcoming(s, mail) -> bool:
    """Är fakturan betald? Via mail.status='paid' ELLER kopplad
    UpcomingTransaction har matched_transaction_id satt."""
    if mail.status == "paid":
        return True
    if mail.upcoming_id is not None:
        upc = s.get(UpcomingTransaction, mail.upcoming_id)
        if upc is not None and upc.matched_transaction_id is not None:
            return True
    return False


def _create_dunning_mail(s, orig, step, student_id: int) -> None:
    """Skapa ny MailItem(mail_type='reminder') i postlådan + en
    UpcomingTransaction för avgiften."""
    from datetime import date as _d_dun, timedelta as _td_dun
    import hashlib as _hl_dun
    from decimal import Decimal as _Dec
    _, level, _kind, fee, label, _, _ = step
    today = _d_dun.today()
    fee_due = today + _td_dun(days=14)

    # Sender · "Inkasso AB" på inkasso-nivå, "Kronofogden" på level 4
    if level == 4:
        sender = "Kronofogdemyndigheten"
        sender_short = "KFM"
        sender_kind = "skv"
    elif level == 3:
        sender = f"Inkasso · {orig.sender}"
        sender_short = "INK"
        sender_kind = "other"
    else:
        sender = orig.sender
        sender_short = orig.sender_short
        sender_kind = orig.sender_kind

    body = _build_dunning_body(orig, step)
    new_mail = MailItem(
        sender=sender,
        sender_short=sender_short,
        sender_kind=sender_kind,
        sender_meta=f"påminnelse · nivå {level}",
        mail_type="reminder",
        subject=f"{label} · {orig.subject}",
        body_meta=(
            f"Avgift {fee} kr · ursprung {orig.subject}"
        ),
        body=body,
        amount=_Dec(-fee),
        due_date=fee_due,
        status="unhandled",
        is_recurring=False,
        parent_mail_id=orig.id,
        reminder_level=level,
    )
    s.add(new_mail)
    s.flush()


def _build_dunning_body(orig, step) -> str:
    """Mänsklig text-body för reminder-mailet — pedagogiskt + realistiskt."""
    _, level, _kind, fee, label, _, _ = step
    orig_amt = abs(float(orig.amount or 0))
    if level == 1:
        return (
            f"Hej,\n\nVi har inte tagit emot din betalning för "
            f"{orig.subject} på {orig_amt:.0f} kr.\n\n"
            f"Vänligen betala omgående. För denna påminnelse "
            f"tillkommer en avgift på {fee} kr (lagstadgat max).\n\n"
            f"Använd OCR + bankgiro från ursprungsfakturan."
        )
    if level == 2:
        return (
            f"Sista påminnelsen.\n\n"
            f"Vi har fortfarande inte tagit emot din betalning för "
            f"{orig.subject} på {orig_amt:.0f} kr.\n\n"
            f"Om vi inte ser betalning inom 14 dagar lämnas ärendet "
            f"till inkasso. En ny avgift på {fee} kr har lagts till."
        )
    if level == 3:
        return (
            f"INKASSOKRAV\n\n"
            f"Ärendet har överlämnats till inkassobolag för indrivning.\n\n"
            f"Skuld: {orig_amt:.0f} kr (ursprung: {orig.subject})\n"
            f"Inkassoavgift: {fee} kr (max enl. inkassolagen § 5)\n"
            f"Dröjsmålsränta tickar dagligen.\n\n"
            f"Betala omgående för att undvika att ärendet lämnas till "
            f"Kronofogden — det skulle ge en betalningsanmärkning på "
            f"din kreditprofil i 3 år."
        )
    # level 4 — Kronofogden
    return (
        f"BETALNINGSFÖRELÄGGANDE — KRONOFOGDEMYNDIGHETEN\n\n"
        f"Ett betalningsföreläggande har utfärdats mot dig.\n\n"
        f"Skuld: {orig_amt:.0f} kr (ursprung: {orig.subject})\n"
        f"Ansökningsavgift: {fee} kr\n\n"
        f"En betalningsanmärkning har registrerats hos UC. "
        f"Anmärkningen påverkar din möjlighet att få lån, hyra "
        f"bostad och teckna abonnemang i 3 år.\n\n"
        f"Bestrid eller betala inom 10 dagar."
    )


def _create_payment_mark(s, orig, step) -> None:
    """Skapa PaymentMark för UC-score-effekt vid kronofogden-eskalering."""
    from datetime import date as _d_dun
    from decimal import Decimal as _Dec
    from ..db.models import PaymentMark
    today = _d_dun.today()
    expires = _d_dun(today.year + 3, today.month, min(today.day, 28))
    s.add(PaymentMark(
        occurred_on=today,
        creditor=orig.sender,
        amount=abs(_Dec(str(orig.amount or 0))),
        kind="kronofogden",
        notes=(
            f"Auto-skapad via dunning-flödet. "
            f"Ursprung: {orig.subject} · {step[4]}"
        ),
        expires_at=expires,
    ))
    s.flush()


def _seed_initial_student_data_safe(
    student_id: int,
    spend_profile: str,
    starting_level: int,
    partner_model: str,
) -> None:
    """Bakgrunds-säker wrapper kring _seed_initial_student_data.

    Serializerad via _seed_semaphore (max 2 samtidiga) så batch-create
    inte spränger connection-pool eller minne. Hämtar Student-raden
    från master och delegerar. Tystas helt mot exceptioner — det här
    körs som FastAPI BackgroundTask och en exception skulle förloras
    tyst ändå, men loggas här så vi ser misslyckanden i Cloud Logging.
    """
    with _seed_semaphore:
        try:
            with master_session() as s:
                stu = s.get(Student, student_id)
                if stu is None:
                    return
                s.expunge(stu)
            _seed_initial_student_data(
                stu,
                spend_profile=spend_profile,
                starting_level=starting_level,
                partner_model=partner_model,
            )
            # Seed klar · markera complete så frontend-overlayn lyfts.
            try:
                with master_session() as s2:
                    stu2 = s2.get(Student, student_id)
                    if stu2 is not None:
                        stu2.seed_status = "complete"
                        s2.flush()
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "BackgroundTask: seed_status='complete' update failed "
                    "för student %s — eleven kan fastna i 'Bygger upp...'-"
                    "overlay tills auto-recovery städar upp",
                    student_id,
                )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "BackgroundTask: _seed_initial_student_data failed "
                "för student %s — eleven kan ha tomma vyer tills "
                "auto-recovery i student-detail kör",
                student_id,
            )
            # Markera failed så lärar-detalj-vyn vet att reseed behövs
            # och frontend-overlayn kan visa felmeddelande istället för
            # att snurra evigt.
            try:
                with master_session() as s_err:
                    stu_err = s_err.get(Student, student_id)
                    if stu_err is not None:
                        stu_err.seed_status = "failed"
                        s_err.flush()
            except Exception:
                # Sista utvägen · loggar bara så vi ser i Cloud Logging
                pass


def _seed_initial_student_data(
    student: "Student",
    *,
    spend_profile: str,
    starting_level: int,
    partner_model: str,
) -> None:
    """Seedar lön + utgifter + events + försäkring + pension för en ny
    elev så hen har data att jobba med från första inloggningen.

    Anropas direkt efter student-skapandet i v2_create_student OCH
    när lärare öppnar elev-detalj-vyn för en elev som saknar data
    (gamla failed-stuck-students från tidigare deploys).
    """
    from datetime import date as _d
    from decimal import Decimal as _Dec
    from ..db.models import RentalContract
    from ..game_engine.monthly_engine import tick_month
    from ..game_engine.profile_generator import generate_profile
    from ..insurance import seed_default_insurance_policies
    from ..pension import seed_default_pension
    from ..school.engines import scope_context, scope_for_student

    # === Steg 1: tick förra månaden via game_engine ===
    today = _d.today()
    if today.month == 1:
        prev_year = today.year - 1
        prev_month = 12
    else:
        prev_year = today.year
        prev_month = today.month - 1
    year_month = f"{prev_year:04d}-{prev_month:02d}"

    profile = generate_profile(
        seed=student.id,
        archetype="random",
        starting_level=starting_level,
        name=student.display_name or "Elev",
        partner_model=partner_model,  # type: ignore[arg-type]
    )

    # === Sync · master-DB:ns StudentProfile MÅSTE matcha den faktiska
    # game_engine-profilen, annars säger HubV2 "Hyran på 15 500 kr"
    # medan postlådan visar bolån + villa-drift för 6 255 kr/mån.
    # Tidigare buggen kom av att profile_fixtures.generate_profile
    # och game_engine.profile_generator.generate_profile kör helt
    # olika RNG/pooler. ===
    try:
        with master_session() as mdb:
            sp = (
                mdb.query(StudentProfile)
                .filter(StudentProfile.student_id == student.id)
                .first()
            )
            if sp is not None:
                sp.housing_type = profile.housing.type
                sp.housing_monthly = int(profile.housing.monthly_cost)
                sp.gross_salary_monthly = int(profile.monthly_gross)
                sp.net_salary_monthly = int(profile.monthly_net)
                # Synca yrke + arbetsgivare så hub-character-kortet
                # ('Klara · Elektriker') matchar löne-transaktionen
                # ('Lön 2025-10 · Polis'). Tidigare buggen kom av att
                # school.profile_fixtures slumpade ett yrke med sin RNG
                # medan game_engine.profile_generator slumpade ETT ANNAT
                # → eleven såg två olika yrken på samma karaktär.
                # game_engine är source-of-truth.
                sp.profession = profile.yrke_display
                # Arbetsgivaren finns på AnstallningsAvtal (master)
                # men sätts via en separat synk i Sprint 7. Här fyller
                # vi i ett rimligt default så hub inte blir tomt.
                if not sp.employer:
                    sp.employer = profile.yrke_display + " AB"
                sp.has_mortgage = profile.housing.type in (
                    "bostadsratt", "villa", "radhus",
                )
                # Synca staden så hub-character-kort + postlåda-fakturor
                # ("Umeå Bostäder", "Umeå kommun") matchar. school-
                # profile_fixtures.generate_profile och game_engine-
                # profile_generator.generate_profile delar inte RNG, så
                # samma seed gav olika städer i de två systemen → eleven
                # bodde i Umeå enligt hub men fick Stockholm Bostäder i
                # postlådan. game_engine är source-of-truth eftersom det
                # är det som driver postlåda + bank + tick.
                sp.city = profile.city_display
                # Synca också familje-status så insurance-coverage-gaps,
                # KALP, hub-text använder samma värde som game_engine.
                # Annars kan profile_fixtures säga "sambo" medan game_
                # engine säger "ensam" → 'Har sambo/familj men ingen
                # livförsäkring' visas felaktigt.
                if profile.family is not None:
                    sp.family_status = profile.family.status
                    if profile.family.partner_gross_monthly:
                        if hasattr(sp, "partner_gross_salary"):
                            sp.partner_gross_salary = (
                                profile.family.partner_gross_monthly
                            )
                    # Children — game_engine har children_count men inte
                    # ages. Ge n placeholder-åldrar 5+i*2 så has_children-
                    # checken fungerar konsistent.
                    cc = int(profile.family.children_count or 0)
                    sp.children_ages = (
                        [5 + i * 2 for i in range(cc)] if cc > 0 else []
                    )
                # has_car_loan / has_credit_card · synca från
                # profile.facts. Singel-elever utan billån ska inte
                # trigga 'Saknar bilförsäkring'-coverage-gap.
                facts = profile.facts or {}
                if "has_high_cost_credit" in facts:
                    sp.has_credit_card = bool(facts["has_high_cost_credit"])
                # Game_engine har inte has_car_loan i profile_generator
                # (det är level-3-feature). Sätt False för låg-nivå-elever.
                if hasattr(sp, "has_car_loan"):
                    sp.has_car_loan = False
                mdb.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_seed_initial_student_data: profile sync failed för %s",
            student.id,
        )

    # === Steg 2 (FÖRE tick): seed försäkringar så fixed_expenses
    # kan generera korrekta försäkrings-fakturor från InsurancePolicy.
    # Tidigare ordning: tick → insurance, vilket gjorde att fixed_expenses
    # såg en tom InsurancePolicy-tabell och skapade INGA försäkrings-
    # fakturor (eller hårdkodade dem felaktigt). ===
    scope_key = scope_for_student(student)
    has_partner = (
        bool(profile.family.partner_gross_monthly)
        if profile.family else False
    )
    with scope_context(scope_key):
        with session_scope() as s:
            try:
                seed_default_insurance_policies(
                    s,
                    housing_type=profile.housing.type,
                    has_partner=has_partner,
                )
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "_seed_initial_student_data: insurance seed failed för %s",
                    student.id,
                )
            try:
                # Seedа Tibber/Bahnhof/Telia/SL som UtilitySubscription
                # så /v2/forbrukning visar dem som aktiva abonnemang
                # istället för 'Inga abonnemang seedade'-tom-state.
                # Matchar fakturorna som fixed_expenses.py genererar
                # för el/bredband/mobil — så bara EN sanning om vad
                # eleven har.
                from ..utility import seed_default_utility_subscriptions
                seed_default_utility_subscriptions(s)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "_seed_initial_student_data: utility seed failed för %s",
                    student.id,
                )

    # === Steg 2 (HISTORISKA MÅNADER) ===
    # Spel-tiden börjar på GAME_ANCHOR_DATE (2026-01-01). Vi seedar
    # 3 månader BAKÅT från anchor (okt/nov/dec 2025) som "redan har
    # hänt" — eleven ser etablerad bankhistorik + 3 lönespec-rader
    # i Arbetsgivar-widgeten vid första inloggningen.
    from ..game_engine.release_schedule import GAME_ANCHOR_DATE
    anchor_y, anchor_m = GAME_ANCHOR_DATE.year, GAME_ANCHOR_DATE.month
    historical_months: list[str] = []
    for back in range(3, 0, -1):  # 3, 2, 1 mån bakåt från anchor
        ty = anchor_y
        tm = anchor_m - back
        while tm <= 0:
            tm += 12
            ty -= 1
        historical_months.append(f"{ty:04d}-{tm:02d}")

    for hist_ym in historical_months:
        try:
            tick_month(
                student,
                profile,
                hist_ym,
                spend_profile=spend_profile,
                starting_level=starting_level,
            )
            _auto_pay_historical_invoices(student, hist_ym)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "_seed_initial_student_data: tick_month (%s) failed "
                "för %s",
                hist_ym, student.id,
            )

    # === Steg 2b (NUVARANDE SPEL-MÅNAD = anchor 2026-01) ===
    # Spelaren börjar i anchor-månaden. Ticka den med release_base =
    # student.created_at så hyra dag 1 dyker upp direkt, lönespec
    # dag 22 efter ~3 h och lön dag 25 efter ~3.5 h. Tick_month auto-
    # detect gör fel jämförelse (lex 2026-01 < 2026-05 = real-ym)
    # och skulle markera anchor som historik.
    current_ym = f"{anchor_y:04d}-{anchor_m:02d}"
    if current_ym not in historical_months:
        try:
            tick_month(
                student,
                profile,
                current_ym,
                spend_profile=spend_profile,
                starting_level=starting_level,
                release_base=student.created_at,
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "_seed_initial_student_data: tick_month (innevarande) "
                "failed för %s",
                student.id,
            )

    # === Steg 2d · CATCH-ALL · säkerställ att INGA seedade invoices
    # eller reminders är överliggande. Eleven får ALDRIG starta med
    # betalningsanmärkningar/inkasso/kronofogden som triggades av seed-
    # data. Three-step belt-and-suspenders:
    #   1. Markera ALLA overdue invoice/reminder-mail som paid/handled
    #      (sweepar både fakturor från fixed_expenses-seed och dunning-
    #      skapade reminders som hängde på dem).
    #   2. Radera alla PaymentMark från seed-perioden (kronofogden-
    #      skapade marks ska inte följa med en helt ny karaktär).
    #   3. Skapa autogiro-transaktioner så bankkontot stämmer.
    try:
        from ..db.models import (
            MailItem as _MI_sweep,
            Account as _Acc_sweep,
            Transaction as _Tx_sweep,
            PaymentMark as _PM_sweep,
        )
        from hashlib import sha256 as _sha_sweep
        with scope_context(scope_key):
            with session_scope() as s:
                # SPEL-TID, inte real-tid · annars markeras alla
                # januari-fakturor som paid eftersom Jan 5 < May 7
                # (real-tid när seed kör). Det resulterade i att
                # postlådan visade "betald" på fakturor från senare
                # i januari trots att eleven är på Jan 2 i spel-tid.
                #
                # Vi använder current_game_date_for_student() (inte
                # current_game_date()) eftersom seed körs i bakgrunds-
                # jobb utan actor-ContextVar satt. Variant-funktionen
                # tar student-id direkt och slår upp created_at.
                from ..business.game_clock import (
                    current_game_date_for_student,
                )
                today_sweep = current_game_date_for_student(student.id)
                lonekonto = (
                    s.query(_Acc_sweep)
                    .filter(_Acc_sweep.type == "checking")
                    .order_by(_Acc_sweep.id.asc())
                    .first()
                )
                # Sweep både invoice OCH reminder-mail (dunning genererar
                # reminders med mail_type="reminder" — de stannade kvar
                # som "Övrigt" → eleven började med inkasso/kronofogden)
                stuck = (
                    s.query(_MI_sweep)
                    .filter(
                        _MI_sweep.mail_type.in_(["invoice", "reminder"]),
                        _MI_sweep.status.in_(
                            ["unhandled", "viewed", "exported"],
                        ),
                    )
                    .all()
                )
                for m in stuck:
                    # Reminders saknar amount eller har påminnelseavgift
                    # (60/180/600 kr); de bokför vi INTE (det betyder
                    # att läraren kan se historiken men eleven är
                    # 'handled' utan kontoavdrag — fail-safe).
                    if m.mail_type == "reminder":
                        m.status = "handled"
                        # Säkerställ omedelbar synlighet
                        m.released_at = None
                        continue
                    # Endast invoices vars due_date passerats betalas
                    # här (fakturor som ska komma framöver behåller
                    # sin status så friktion finns kvar).
                    if (
                        m.due_date is not None
                        and m.due_date >= today_sweep
                    ):
                        continue
                    # Säkerställ att historiska mails är synliga direkt
                    # — annars gömmer _released_filter dem tills release_
                    # at-tiden passerats (t.ex. lönespec dag 22 efter
                    # student-skapandet i bakgrunden).
                    m.released_at = None
                    if m.amount is None:
                        m.status = "paid"
                        continue
                    # Använd SAMMA hash-format som _auto_pay_historical_
                    # invoices så båda funktionerna dedupliceras mot
                    # varandra. Tidigare hade catch-all-sweepen sitt
                    # eget 'seedsweep|...' format → samma faktura fick
                    # två autogiro-transaktioner (en per format).
                    ym_for_hash = (
                        f"{m.due_date.year:04d}-{m.due_date.month:02d}"
                        if m.due_date else "na"
                    )
                    raw = f"autopaid|{student.id}|{ym_for_hash}|{m.id}"
                    tx_hash = _sha_sweep(raw.encode()).hexdigest()[:32]
                    existing = (
                        s.query(_Tx_sweep)
                        .filter(_Tx_sweep.hash == tx_hash)
                        .first()
                    )
                    if (
                        existing is None
                        and lonekonto is not None
                        and m.due_date is not None
                    ):
                        # Skippa autogiro-tx för mails utan due_date —
                        # Transaction.date är NOT NULL och vi vill inte
                        # crasha hela sweepen för en konstig rad.
                        s.add(_Tx_sweep(
                            account_id=lonekonto.id,
                            date=m.due_date,
                            amount=m.amount,
                            currency="SEK",
                            raw_description=f"Autogiro · {m.sender}",
                            normalized_merchant=m.sender,
                            hash=tx_hash,
                            is_transfer=False,
                            user_verified=True,
                        ))
                    m.status = "paid"

                # Radera ALLA PaymentMark som dunning eventuellt skapade
                # under seed-flödet. En helt ny karaktär ska inte ha
                # betalningsanmärkningar — om läraren vill simulera det
                # konfigurerar de explicit via lärar-verktyget.
                s.query(_PM_sweep).delete()
                s.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_seed_initial_student_data: catch-all seed-sweep failed "
            "för %s — eleven kan starta med en kvarliggande overdue "
            "invoice (icke-kritiskt)",
            student.id,
        )

    # === Steg 2c · KV-startbudget (Sprint 7) ===
    # Pedagogiskt: eleven ska INTE öppna /v2/budget och se en tom
    # tabell. Onboarding-uppdrag #1 är "Skapa din budget" — vi seedar
    # KV-schablonerna som utgångsläge så eleven kan justera dem nedåt
    # eller uppåt och direkt se konsekvenserna i pentagon.
    # Familje-aware via suggest_budget(profile.family.*).
    try:
        from ..budget.seed import seed_initial_budget_for_months
        with scope_context(scope_key):
            with session_scope() as s:
                # Budget för senaste historiska månaden + innevarande.
                # Att seeda alla 4 historiska gör budgeten brusig och
                # adderar lite värde — eleven justerar bara framåt.
                months_to_seed = [historical_months[-1]]
                if current_ym not in months_to_seed:
                    months_to_seed.append(current_ym)
                seed_initial_budget_for_months(
                    s, profile=profile, year_months=months_to_seed,
                )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_seed_initial_student_data: budget seed failed för %s",
            student.id,
        )

    # === Steg 3-4: pension + boende ===
    with scope_context(scope_key):
        with session_scope() as s:
            try:
                seed_default_pension(s)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "_seed_initial_student_data: pension seed failed för %s",
                    student.id,
                )

            # === Boende-kontrakt · matcha postlådans fakturor ===
            # Om eleven har hyresrätt enligt game-engine-profilen,
            # seeda ett RentalContract med rätt belopp + stad. Annars
            # är hyresvärden-vyn tom och eleven ser "Inget registrerat
            # boende" trots att hyran dras varje månad i postlådan.
            try:
                if profile.housing.type == "hyresratt":
                    existing = s.query(RentalContract).first()
                    if existing is None:
                        rooms_label = (
                            f"{max(1, profile.housing.size_kvm // 25)} r o k"
                        )
                        contract = RentalContract(
                            landlord=(
                                f"{profile.city_display} Bostäder"
                            ),
                            address=f"Centralvägen {profile.seed % 99 + 1}",
                            rooms_label=rooms_label,
                            area_sqm=_Dec(str(profile.housing.size_kvm)),
                            city=profile.city_display,
                            district=None,
                            contract_type="forsta_hand",
                            duration_type="tillsvidare",
                            monthly_rent=_Dec(
                                str(profile.housing.monthly_cost),
                            ),
                            deposit=_Dec("0"),
                            ocr_reference=None,
                            autogiro=True,
                            notice_period_months=3,
                            queue_years=None,
                            queue_priority=None,
                            market_price_per_sqm=None,
                            status="active",
                            notes=None,
                        )
                        s.add(contract)
                        s.flush()
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "_seed_initial_student_data: rental seed failed för %s",
                    student.id,
                )


class V2CreatedStudentsResponse(BaseModel):
    total_count: int
    pending_activation_count: int
    rows: list[V2CreatedStudentRow]


@router.get(
    "/teacher/students/created", response_model=V2CreatedStudentsResponse,
)
def v2_list_created_students(
    info: TokenInfo = Depends(require_token),
) -> V2CreatedStudentsResponse:
    """Lista alla skapade elever (med login-kod) för läraren.

    Senast skapade först. Visar v2-fält + om eleven aktiverats
    (loggat in minst en gång)."""
    teacher_id = _require_teacher(info)
    with master_session() as s:
        students = (
            s.query(Student)
            .filter(
                Student.teacher_id == teacher_id,
                Student.active.is_(True),
            )
            .order_by(
                Student.created_at.desc(),
                Student.id.desc(),
            )
            .all()
        )
        rows: list[V2CreatedStudentRow] = []
        pending = 0
        for st in students:
            row = V2CreatedStudentRow(
                student_id=st.id,
                student_name=st.display_name,
                login_code=st.login_code or "",
                archetype="random",
                spend_profile=getattr(st, "v2_spend_profile", None),
                partner_model=getattr(st, "v2_partner_model", None),
                starting_level=getattr(st, "v2_level", None) or 1,
                guardian_email=None,
                created_at=st.created_at,
                last_login_at=st.last_login_at,
                activated=st.last_login_at is not None,
            )
            rows.append(row)
            if not row.activated:
                pending += 1
    return V2CreatedStudentsResponse(
        total_count=len(rows),
        pending_activation_count=pending,
        rows=rows,
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


# Bug #19 · Bulk-mark-read endpoint
@router.post("/teacher/reflections/{progress_id}/mark-read", status_code=204)
def teacher_reflection_mark_read_v2(
    progress_id: int,
    info: TokenInfo = Depends(require_token),
):
    """Markera en reflektion som 'läst' utan att skriva feedback."""
    teacher_id = _require_teacher(info)
    with master_session() as s:
        progress = s.get(_SchoolStepProgress, progress_id)
        if progress is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Progress saknas.")
        # Markera teacher_feedback som tomt-string så filter visar som läst
        if not (progress.teacher_feedback or "").strip():
            progress.teacher_feedback = "(läst)"
            from datetime import datetime as _dt
            progress.teacher_feedback_at = _dt.utcnow()
            s.commit()
    return None


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


# === Pentagon Axis-Detail (Fas 2Z · flip-card) ===
#
# När eleven (eller läraren) klickar på en axel i pentagonen flippas
# kortet och visar exakt vilka faktorer som påverkat just den axeln —
# scenarierna, transaktionerna, kompetens-höjningarna, etc. Drivs av
# WellbeingFactor-listan från calculator.py + senaste relevanta
# transaktioner från scope-DB.


PentAxis = Literal["economy", "safety", "health", "social", "leisure"]


_AXIS_LABELS: dict[str, str] = {
    "economy": "Ekonomi",
    "safety": "Karriär",
    "health": "Hälsa",
    "social": "Relation",
    "leisure": "Fritid",
}

_AXIS_NUMBER: dict[str, str] = {
    "economy": "01",
    "safety": "02",
    "health": "03",
    "social": "04",
    "leisure": "05",
}


class V2PentAxisFactor(BaseModel):
    explanation: str
    points: int
    delta_label: str  # "+5", "-3", "±0"


class V2PentAxisEvent(BaseModel):
    occurred_at: Optional[datetime]
    date_label: str  # "29 apr"
    title: str
    detail: Optional[str] = None
    delta: Optional[int] = None
    delta_label: str  # "+5", "-3", "±0", ""


class V2PentAxisDetail(BaseModel):
    axis: PentAxis
    axis_label: str
    axis_number: str
    score: int
    year_month: str
    factors: list[V2PentAxisFactor]
    events: list[V2PentAxisEvent]
    summary_text: str


def _delta_label(points: Optional[int]) -> str:
    if points is None:
        return ""
    if points > 0:
        return f"+{points}"
    if points < 0:
        return str(points)
    return "±0"


def _gather_axis_events_for(
    student: Student, axis: PentAxis,
) -> list[V2PentAxisEvent]:
    """Hämta senaste konkreta händelser kopplade till en axel.

    economy → senaste transaktioner + sparmål-överföringar
    safety  → modul-completion + lärar-feedback + lönesamtal
    health  → vårdfakturor + reflektioner + 0 alkohol-tx (heuristik)
    social  → meddelanden från lärare + peer-feedback
    leisure → fritid-transaktioner (restaurang, nöje)

    Fail-soft per scope-DB.
    """
    from ..school.engines import scope_context, scope_for_student
    from ..school.models import StudentActivity as _SA

    events: list[V2PentAxisEvent] = []
    cutoff = datetime.utcnow() - timedelta(days=45)

    # === Master-DB events ===
    with master_session() as ms:
        if axis == "safety":
            # Lönesamtals-rundor
            negs = (
                ms.query(_NegotiationRound, _SalaryNegotiation)
                .join(
                    _SalaryNegotiation,
                    _NegotiationRound.negotiation_id
                    == _SalaryNegotiation.id,
                )
                .filter(
                    _SalaryNegotiation.student_id == student.id,
                    _NegotiationRound.created_at >= cutoff,
                )
                .order_by(_NegotiationRound.created_at.desc())
                .limit(5)
                .all()
            )
            for r, neg in negs:
                events.append(V2PentAxisEvent(
                    occurred_at=r.created_at,
                    date_label=_short_date_label(r.created_at),
                    title=f"Lönesamtal R{r.round_no} · {neg.profession}",
                    detail=(
                        f"Maria-bud {round(float(neg.starting_salary) * (1 + (r.proposed_pct or 0) / 100)):,} kr"
                        .replace(",", " ")
                        if r.proposed_pct is not None
                        else "ingen procent"
                    ),
                    delta=2,
                    delta_label="+2",
                ))
            # Modul-step-completion → safety/karriär bonus
            steps_done = (
                ms.query(_SchoolStepProgress, _SchoolModuleStep, _SchoolModule)
                .join(_SchoolModuleStep,
                      _SchoolStepProgress.step_id == _SchoolModuleStep.id)
                .join(_SchoolModule,
                      _SchoolModuleStep.module_id == _SchoolModule.id)
                .filter(
                    _SchoolStepProgress.student_id == student.id,
                    _SchoolStepProgress.completed_at >= cutoff,
                )
                .order_by(_SchoolStepProgress.completed_at.desc())
                .limit(5)
                .all()
            )
            for prog, step, mod in steps_done:
                events.append(V2PentAxisEvent(
                    occurred_at=prog.completed_at,
                    date_label=_short_date_label(prog.completed_at),
                    title=f'Modul-steg "{step.title}" klart',
                    detail=f"Modul: {mod.title}",
                    delta=1,
                    delta_label="+1",
                ))

        if axis == "social":
            from ..school.models import Message as _M
            msgs = (
                ms.query(_M)
                .filter(
                    _M.student_id == student.id,
                    _M.created_at >= cutoff,
                )
                .order_by(_M.created_at.desc())
                .limit(5)
                .all()
            )
            for m in msgs:
                sender = "lärare" if m.sender_role == "teacher" else "du"
                events.append(V2PentAxisEvent(
                    occurred_at=m.created_at,
                    date_label=_short_date_label(m.created_at),
                    title=f"Meddelande från {sender}",
                    detail=(m.body[:80] + "…")
                    if m.body and len(m.body) > 80 else m.body,
                    delta=1 if m.sender_role == "teacher" else None,
                    delta_label="+1" if m.sender_role == "teacher" else "",
                ))

        # StudentActivity som matchar axel
        sa_rows = (
            ms.query(_SA)
            .filter(
                _SA.student_id == student.id,
                _SA.occurred_at >= cutoff,
            )
            .order_by(_SA.occurred_at.desc())
            .limit(20)
            .all()
        )
        for sa in sa_rows:
            kind = sa.kind
            relevant = False
            delta = 0
            if axis == "economy" and (
                kind.startswith("transaction.")
                or kind.startswith("budget.")
                or kind.startswith("transfer.")
            ):
                relevant = True
                delta = 1 if "save" in kind or "transfer" in kind else 0
            if axis == "safety" and kind.startswith("loan."):
                relevant = True
                delta = -1
            if not relevant:
                continue
            events.append(V2PentAxisEvent(
                occurred_at=sa.occurred_at,
                date_label=_short_date_label(sa.occurred_at),
                title=sa.summary,
                detail=kind,
                delta=delta if delta != 0 else None,
                delta_label=_delta_label(delta) if delta != 0 else "±0",
            ))

    # === Scope-DB events (transaktioner) ===
    if axis == "economy" or axis == "leisure":
        try:
            scope_key = scope_for_student(student)
            with scope_context(scope_key):
                with session_scope() as s:
                    txs = (
                        s.query(Transaction)
                        .filter(_released_filter(Transaction))
                        .order_by(Transaction.date.desc())
                        .limit(15)
                        .all()
                    )
                    for tx in txs:
                        amt = float(tx.amount) if tx.amount is not None else 0
                        # leisure-axel: bara restaurang/nöje
                        if axis == "leisure":
                            cat_name: Optional[str] = None
                            if tx.category_id:
                                cat = s.get(Category, tx.category_id)
                                cat_name = cat.name.lower() if cat else None
                            if cat_name and any(
                                kw in cat_name
                                for kw in (
                                    "restaurang", "nöje", "fritid", "kultur",
                                )
                            ):
                                events.append(V2PentAxisEvent(
                                    occurred_at=None,
                                    date_label=tx.date.strftime("%-d %b")
                                    if tx.date else "—",
                                    title=tx.description or "Transaktion",
                                    detail=f"{cat.name} · {amt:,.0f} kr".replace(
                                        ",", " ",
                                    ),
                                    delta=-1 if amt < -200 else None,
                                    delta_label="-1" if amt < -200 else "±0",
                                ))
                        elif axis == "economy":
                            sign = "+" if amt > 0 else ""
                            events.append(V2PentAxisEvent(
                                occurred_at=None,
                                date_label=tx.date.strftime("%-d %b")
                                if tx.date else "—",
                                title=tx.description or "Transaktion",
                                detail=f"{sign}{amt:,.0f} kr".replace(
                                    ",", " ",
                                ),
                                delta=2 if amt > 1000 else (
                                    -1 if amt < -2000 else None
                                ),
                                delta_label=(
                                    "+2" if amt > 1000
                                    else "-1" if amt < -2000
                                    else "±0"
                                ),
                            ))
        except Exception:
            pass

    # Sortera nyast först · max 8 visas
    events.sort(
        key=lambda e: e.occurred_at or datetime.min, reverse=True,
    )
    return events[:8]


def _short_date_label(dt: Optional[datetime]) -> str:
    """Formattera real-tid-datetime som SPEL-tid-label ('14 jan').

    Pentagon-händelser, lärar-tick-historik och liknande lagrar dt
    som datetime.utcnow() (real-tid) men eleven förväntar sig spel-tid
    eftersom hela appen agerar som om "nu" är jan/feb 2026, inte maj.

    Konvertering: 1 real-timme = 1 spel-vecka sedan student.created_at.
    Faller tillbaka till real-tid-formatering om scope/elev saknas.
    """
    if dt is None:
        return "—"
    months = [
        "jan", "feb", "mar", "apr", "maj", "jun",
        "jul", "aug", "sep", "okt", "nov", "dec",
    ]
    # Försök konvertera real-tid → spel-tid via student.created_at
    try:
        from ..school.engines import (
            get_current_actor_student as _gcas_sd,
        )
        from ..game_engine.release_schedule import (
            real_to_game_datetime as _r2g,
        )
        sid = _gcas_sd()
        if sid is not None:
            with master_session() as _ms_sd:
                _stu_sd = _ms_sd.get(Student, sid)
                if _stu_sd is not None and _stu_sd.created_at is not None:
                    g_dt = _r2g(_stu_sd.created_at, dt)
                    return f"{g_dt.day} {months[g_dt.month - 1]}"
    except Exception:
        pass
    return f"{dt.day} {months[dt.month - 1]}"


def _build_pent_axis_detail(
    student: Student, axis: PentAxis,
) -> V2PentAxisDetail:
    from ..school.engines import scope_context, scope_for_student

    score = 50
    factors_for_axis: list[V2PentAxisFactor] = []
    ym = _current_year_month()
    try:
        scope_key = scope_for_student(student)
        with scope_context(scope_key):
            with session_scope() as s:
                wb = calculate_wellbeing(s, ym)
                score = getattr(wb, axis)
                ym = wb.year_month
                for f in wb.factors:
                    if f.dimension == axis:
                        factors_for_axis.append(V2PentAxisFactor(
                            explanation=f.explanation,
                            points=f.points,
                            delta_label=_delta_label(f.points),
                        ))
    except Exception:
        pass

    events = _gather_axis_events_for(student, axis)

    # Sorted factors: most-impact first
    factors_for_axis.sort(key=lambda f: -abs(f.points))

    if factors_for_axis:
        top = factors_for_axis[0]
        sign = "höjt" if top.points > 0 else "sänkt" if top.points < 0 else "påverkat"
        summary = (
            f"{score}/100 i {_AXIS_LABELS[axis].lower()}. "
            f"Största enskilda bidraget har {sign} med {abs(top.points)} p: "
            f'"{top.explanation}".'
        )
    else:
        summary = (
            f"{score}/100 i {_AXIS_LABELS[axis].lower()}. "
            f"Inga registrerade faktorer än — gör mer i appen så ser du "
            f"vad som påverkar."
        )

    return V2PentAxisDetail(
        axis=axis,
        axis_label=_AXIS_LABELS[axis],
        axis_number=_AXIS_NUMBER[axis],
        score=score,
        year_month=ym,
        factors=factors_for_axis,
        events=events,
        summary_text=summary,
    )


@router.get(
    "/pentagon/axis/{axis}", response_model=V2PentAxisDetail,
)
def get_pentagon_axis_detail(
    axis: PentAxis,
    info: TokenInfo = Depends(require_token),
) -> V2PentAxisDetail:
    """Per-axel-detalj för flip-card. Fungerar för elev (egen pentagon)."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Endast elever",
        )
    with master_session() as mdb:
        student = mdb.get(Student, info.student_id)
        if not student:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Elev hittades inte",
            )
    return _build_pent_axis_detail(student, axis)


class V2TeacherPentAxisDetail(BaseModel):
    student_id: int
    student_name: str
    detail: V2PentAxisDetail


@router.get(
    "/teacher/students/{student_id}/pentagon/axis/{axis}",
    response_model=V2TeacherPentAxisDetail,
)
def teacher_get_pentagon_axis_detail(
    student_id: int,
    axis: PentAxis,
    info: TokenInfo = Depends(require_token),
) -> V2TeacherPentAxisDetail:
    """Lärar-version · samma data men för specifik elev."""
    teacher_id = _require_teacher(info)
    with master_session() as mdb:
        student = mdb.get(Student, student_id)
        if not student or student.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Endast egen elev",
            )
        student_name = student.display_name
    detail = _build_pent_axis_detail(student, axis)
    return V2TeacherPentAxisDetail(
        student_id=student_id,
        student_name=student_name,
        detail=detail,
    )


# === V2 Notifications (Fas 2AB · live-notiser) ===
#
# Speglar prototypens elev.html .notif-drawer + .notif-toast. Aggregerar
# alla händelser som behöver elevens uppmärksamhet i en enhetlig
# notif-stream:
# - Lärar-uppdrag (nya / försenade)
# - Lärar-feedback (ej läst)
# - Lärar-meddelanden (ej läst)
# - Postlådan (myndighet / påminnelser ohanterade)
# - Modul-rekommendationer (nytilldelade)
# - Klasskompis-förfrågningar (peer review · placeholder)
#
# Polling: frontend pollar /v2/notifications var 30 sek för "live".


NotifKind = Literal[
    "teacher", "uppdrag", "echo", "modul",
    "bank", "social", "system",
]


class V2Notification(BaseModel):
    id: str  # stabil för read-state ("uppdrag-42", "msg-17"...)
    kind: NotifKind
    icon: str  # 1-2 tecken
    occurred_at: datetime
    time_label: str  # "14:08 idag" / "i går 18:42"
    title: str
    body: str
    unread: bool
    target_route: Optional[str] = None  # "/v2/uppdrag" etc


class V2NotificationsSummary(BaseModel):
    total_count: int
    unread_count: int
    new_today_count: int
    by_kind: dict[str, int]


class V2NotificationsResponse(BaseModel):
    summary: V2NotificationsSummary
    items: list[V2Notification]


# In-memory TTL-cache för /v2/notifications-svar.
# Frontend pollar var 30:e sekund från NotifBell + Sidebar → med 15 s TTL
# fångar vi ena pollen ur två som cache-hit. Per-process-cache är OK
# eftersom Cloud Run kör --max-instances=1 i school-läge.
_NOTIF_CACHE_TTL_SECONDS = 15.0
_notif_cache: dict[
    tuple[str, int], tuple[float, "V2NotificationsResponse"]
] = {}


def _notif_cache_get(
    key: tuple[str, int],
) -> Optional["V2NotificationsResponse"]:
    import time as _t_n
    entry = _notif_cache.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if expires_at < _t_n.monotonic():
        _notif_cache.pop(key, None)
        return None
    return value


def _notif_cache_set(
    key: tuple[str, int], value: "V2NotificationsResponse",
) -> None:
    import time as _t_n
    _notif_cache[key] = (
        _t_n.monotonic() + _NOTIF_CACHE_TTL_SECONDS, value,
    )


def invalidate_notif_cache(
    role: Optional[str] = None, target_id: Optional[int] = None,
) -> None:
    """Töm notis-cachen — anropas av endpoints som ändrar notif-state
    (t.ex. mark-all-read, ny lärarmeddelande)."""
    if role is None or target_id is None:
        _notif_cache.clear()
        return
    _notif_cache.pop((role, target_id), None)


def _time_label_for(dt: datetime) -> str:
    now = datetime.utcnow()
    delta = now - dt
    h = int(delta.total_seconds() // 3600)
    if h < 1:
        return "just nu"
    if delta.days == 0:
        return dt.strftime("%H:%M") + " idag"
    if delta.days == 1:
        return "i går " + dt.strftime("%H:%M")
    if delta.days < 7:
        return f"{delta.days} dgr sedan"
    months = [
        "jan", "feb", "mar", "apr", "maj", "jun",
        "jul", "aug", "sep", "okt", "nov", "dec",
    ]
    return f"{dt.day} {months[dt.month - 1]}"


@router.get(
    "/notifications", response_model=V2NotificationsResponse,
)
def get_v2_notifications(
    info: TokenInfo = Depends(require_token),
) -> V2NotificationsResponse:
    """Live-notiser · aggregerade från flera källor.

    Frontend pollar denna var 30-60:e sekund från NotifBell + Sidebar.
    Per-användare-cachat 15 s in-memory så samma poll inte triggar
    samma 5+ master-DB-queries två gånger inom poll-intervallet.
    """
    if info.role == "teacher" and info.teacher_id is not None:
        cache_key = ("teacher", info.teacher_id)
        cached = _notif_cache_get(cache_key)
        if cached is not None:
            return cached
        result = _build_teacher_notifications(info.teacher_id)
        _notif_cache_set(cache_key, result)
        return result

    if info.role != "student" or info.student_id is None:
        # Tom payload för demo / okänd roll
        return V2NotificationsResponse(
            summary=V2NotificationsSummary(
                total_count=0, unread_count=0,
                new_today_count=0, by_kind={},
            ),
            items=[],
        )

    cache_key = ("student", info.student_id)
    cached = _notif_cache_get(cache_key)
    if cached is not None:
        return cached
    result = _build_student_notifications(info.student_id)
    _notif_cache_set(cache_key, result)
    return result


def _build_student_notifications(
    sid: int,
) -> V2NotificationsResponse:
    """Aggregator för elev-notiser. Kallas från GET /v2/notifications
    (cachat 15 s) och kan kallas direkt av andra endpoints som vill
    ha samma vy."""
    notifs: list[V2Notification] = []
    now = datetime.utcnow()
    cutoff = now - timedelta(days=14)

    with master_session() as ms:
        student = ms.get(Student, sid)
        if student is None:
            return V2NotificationsResponse(
                summary=V2NotificationsSummary(
                    total_count=0, unread_count=0,
                    new_today_count=0, by_kind={},
                ),
                items=[],
            )

        # 1. Lärar-meddelanden (olästa = sender_role=teacher + read_at=None)
        from ..school.models import Message as _M
        msgs = (
            ms.query(_M)
            .filter(
                _M.student_id == sid,
                _M.sender_role == "teacher",
                _M.created_at >= cutoff,
            )
            .order_by(_M.created_at.desc())
            .limit(10)
            .all()
        )
        for m in msgs:
            body = (m.body or "")[:140]
            if len(m.body or "") > 140:
                body += "…"
            notifs.append(V2Notification(
                id=f"msg-{m.id}",
                kind="teacher",
                icon="AL",
                occurred_at=m.created_at,
                time_label=_time_label_for(m.created_at),
                title="Meddelande från läraren",
                body=body,
                unread=m.read_at is None,
                target_route="/v2/meddelanden",
            ))

        # 2. Nya uppdrag (skapade senaste 14 dgr · ej manuellt klara)
        teacher_name = "din lärare"
        if student.teacher_id is not None:
            t_obj = ms.get(Teacher, student.teacher_id)
            if t_obj is not None:
                teacher_name = t_obj.name or teacher_name
        assignments = (
            ms.query(_SchoolAssignment)
            .filter(
                _SchoolAssignment.student_id == sid,
                _SchoolAssignment.created_at >= cutoff,
            )
            .order_by(_SchoolAssignment.created_at.desc())
            .limit(10)
            .all()
        )
        for a in assignments:
            if a.manually_completed_at is not None:
                continue
            unread = (now - a.created_at).total_seconds() < 7 * 24 * 3600
            notifs.append(V2Notification(
                id=f"uppdrag-{a.id}",
                kind="uppdrag",
                icon="▷",
                occurred_at=a.created_at,
                time_label=_time_label_for(a.created_at),
                title=f"NYTT UPPDRAG · {teacher_name}",
                body=(
                    f"<em>{a.title}</em>"
                    + (
                        f". Förfaller {a.due_date.strftime('%-d %b')}"
                        if a.due_date else ""
                    )
                ),
                unread=unread,
                target_route="/v2/uppdrag",
            ))

        # 3. Lärar-feedback på reflektioner (senaste 14 dgr · oläst)
        from ..school.models import FeedbackRead as _FR
        fb_progress = (
            ms.query(_SchoolStepProgress)
            .filter(
                _SchoolStepProgress.student_id == sid,
                _SchoolStepProgress.teacher_feedback.is_not(None),
                _SchoolStepProgress.feedback_at.is_not(None),
                _SchoolStepProgress.feedback_at >= cutoff,
            )
            .order_by(_SchoolStepProgress.feedback_at.desc())
            .limit(10)
            .all()
        )
        # Batcha FeedbackRead-lookups i ETT query istället för en
        # per progress-rad. Tidigare N+1: med 10 reflektioner blev
        # det 11 queries per notif-poll, och frontend pollar var
        # 30:e sekund per användare → konstant overhead.
        progress_ids = [p.id for p in fb_progress if p.id is not None]
        read_progress_ids: set[int] = set()
        if progress_ids:
            read_rows = (
                ms.query(_FR.source_id)
                .filter(
                    _FR.student_id == sid,
                    _FR.kind == "module_step",
                    _FR.source_id.in_(progress_ids),
                )
                .all()
            )
            read_progress_ids = {row[0] for row in read_rows}
        for prog in fb_progress:
            if prog.feedback_at is None:
                continue
            unread = prog.id not in read_progress_ids
            notifs.append(V2Notification(
                id=f"fb-{prog.id}",
                kind="teacher",
                icon="AL",
                occurred_at=prog.feedback_at,
                time_label=_time_label_for(prog.feedback_at),
                title="Feedback på reflektion",
                body=(
                    (prog.teacher_feedback or "")[:140]
                    + ("…" if len(prog.teacher_feedback or "") > 140 else "")
                ),
                unread=unread,
                target_route="/v2/feedback",
            ))

    # 4. Postlådan · myndighetspost / påminnelser ohanterade
    try:
        from ..school.engines import scope_context, scope_for_student
        scope_key = scope_for_student(student)
        with scope_context(scope_key):
            with session_scope() as s:
                authorities = (
                    s.query(MailItem)
                    .filter(
                        MailItem.status == "unhandled",
                        MailItem.mail_type.in_(("authority", "reminder")),
                    )
                    .order_by(MailItem.received_at.desc())
                    .limit(5)
                    .all()
                )
                for m in authorities:
                    icon = "!" if m.mail_type == "reminder" else "★"
                    title = (
                        "PÅMINNELSE · ohanterad räkning"
                        if m.mail_type == "reminder"
                        else "MYNDIGHETSPOST"
                    )
                    notifs.append(V2Notification(
                        id=f"mail-{m.id}",
                        kind="bank",
                        icon=icon,
                        occurred_at=m.received_at or now,
                        time_label=_time_label_for(m.received_at or now),
                        title=title,
                        body=(
                            f"{m.sender}: <em>{m.subject}</em>"
                            + (
                                f" · {round(float(m.amount))} kr"
                                if m.amount is not None else ""
                            )
                        ),
                        unread=True,
                        target_route="/v2/postladan",
                    ))

                # 5. Pending sociala events (StudentEvent · pending status)
                # Filtrera deadline >= today så historiska seed-events
                # (jan-apr) inte triggar notiser som leder till tom
                # Händelser-vy. Konsistent med /v2/events/pending.
                from ..db.models import StudentEvent as _SE_notif
                pending_events = (
                    s.query(_SE_notif)
                    .filter(
                        _SE_notif.status == "pending",
                        _SE_notif.deadline >= now.date(),
                    )
                    .order_by(_SE_notif.deadline.asc())
                    .limit(8)
                    .all()
                )
                for ev in pending_events:
                    icon_map = {
                        "social": "♥", "family": "✦", "culture": "♪",
                        "sport": "▲", "mat": "◉", "lifestyle": "✧",
                        "opportunity": "★", "unexpected": "!",
                    }
                    icon_e = icon_map.get(ev.category, "●")
                    days_left = (ev.deadline - now.date()).days
                    deadline_str = (
                        f"deadline {ev.deadline.strftime('%-d %b')}"
                        if days_left > 1
                        else (
                            "deadline imorgon" if days_left == 1
                            else "deadline IDAG"
                        )
                    )
                    body_parts = [
                        f"<em>{ev.title}</em>",
                        f"{int(float(ev.cost))} kr" if ev.cost > 0 else "",
                        deadline_str,
                    ]
                    body_e = " · ".join(p for p in body_parts if p)
                    src_prefix = (
                        "BJUDNING · " if ev.source == "classmate_invite"
                        else "HÄNDELSE · "
                    )
                    notifs.append(V2Notification(
                        id=f"event-{ev.id}",
                        kind="social",
                        icon=icon_e,
                        occurred_at=ev.created_at or now,
                        time_label=_time_label_for(ev.created_at or now),
                        title=f"{src_prefix}{ev.category.upper()}",
                        body=body_e,
                        unread=True,
                        target_route="/v2/handelser",
                    ))
    except Exception:
        pass

    # 6. Inkomna klasskompis-bjudningar (master-DB · ClassEventInvite)
    try:
        from ..school.social_models import ClassEventInvite as _CEI
        from ..school.models import Student as _Stu_inv
        invites = (
            ms.query(_CEI)
            .filter(
                _CEI.to_student_id == sid,
                _CEI.status == "pending",
                _CEI.deadline >= now.date(),
            )
            .order_by(_CEI.deadline.asc())
            .limit(8)
            .all()
        )
        for inv in invites:
            from_name = "klasskompis"
            from_st = ms.get(_Stu_inv, inv.from_student_id)
            if from_st is not None:
                from_name = from_st.display_name or from_name
            cost_str = (
                f"{int(float(inv.swish_amount))} kr"
                if inv.swish_amount and inv.swish_amount > 0
                else "gratis"
            )
            notifs.append(V2Notification(
                id=f"invite-{inv.id}",
                kind="social",
                icon="♥",
                occurred_at=inv.created_at or now,
                time_label=_time_label_for(inv.created_at or now),
                title=f"BJUDNING · {from_name}",
                body=(
                    f"<em>{inv.event_title}</em> · {cost_str} · "
                    f"deadline {inv.deadline.strftime('%-d %b')}"
                ),
                unread=True,
                target_route="/v2/handelser",
            ))
    except Exception:
        pass

    # Sortera nyast först
    notifs.sort(key=lambda n: n.occurred_at, reverse=True)

    today_count = sum(
        1 for n in notifs if (now - n.occurred_at).days == 0
    )
    unread_count = sum(1 for n in notifs if n.unread)
    by_kind: dict[str, int] = {}
    for n in notifs:
        by_kind[n.kind] = by_kind.get(n.kind, 0) + 1

    summary = V2NotificationsSummary(
        total_count=len(notifs),
        unread_count=unread_count,
        new_today_count=today_count,
        by_kind=by_kind,
    )
    return V2NotificationsResponse(summary=summary, items=notifs)


# === Lärar-notiser (Fas 2AE) ===
#
# Aggregerar notiser för läraren · samma format som elev-notiser men
# källor är klass-aktivitet:
# - Nya reflektioner att läsa (utan teacher_feedback)
# - Flaggade reflektioner (heuristik · "behöver hjälp")
# - Försenade uppdrag (due_date passerat, ej klart)
# - Elever som behöver stöd (pent < 40 / 7 d inaktiv / 3+ röda axlar)
# - Aktiva lönesamtal nära smärtgräns (proposed_pct ≥ 6,0)
# - Olästa elev-meddelanden (från elev till lärare)


def _build_teacher_notifications(
    teacher_id: int,
) -> V2NotificationsResponse:
    notifs: list[V2Notification] = []
    now = datetime.utcnow()
    cutoff = now - timedelta(days=14)

    with master_session() as ms:
        students = (
            ms.query(Student)
            .filter(
                Student.teacher_id == teacher_id,
                Student.active.is_(True),
            )
            .all()
        )
        student_ids = [s.id for s in students]
        name_by_id = {s.id: s.display_name for s in students}

        if not student_ids:
            return V2NotificationsResponse(
                summary=V2NotificationsSummary(
                    total_count=0, unread_count=0,
                    new_today_count=0, by_kind={},
                ),
                items=[],
            )

        # 1. Nya reflektioner (klar senaste 14 d, ingen feedback än)
        new_reflections = (
            ms.query(_SchoolStepProgress, _SchoolModuleStep)
            .join(
                _SchoolModuleStep,
                _SchoolStepProgress.step_id == _SchoolModuleStep.id,
            )
            .filter(
                _SchoolStepProgress.student_id.in_(student_ids),
                _SchoolModuleStep.kind == "reflect",
                _SchoolStepProgress.completed_at.is_not(None),
                _SchoolStepProgress.completed_at >= cutoff,
                _SchoolStepProgress.teacher_feedback.is_(None),
            )
            .order_by(_SchoolStepProgress.completed_at.desc())
            .limit(10)
            .all()
        )
        for prog, step in new_reflections:
            if prog.completed_at is None:
                continue
            sname = name_by_id.get(prog.student_id, "Okänd elev")
            text = ""
            if prog.data and isinstance(prog.data, dict):
                text = str(prog.data.get("reflection", "")).strip()
            flagged = _flagged_for_help(text)
            preview = text[:120] + ("…" if len(text) > 120 else "")
            notifs.append(V2Notification(
                id=f"refl-{prog.id}",
                kind="social" if not flagged else "uppdrag",
                icon="✦" if not flagged else "⚠",
                occurred_at=prog.completed_at,
                time_label=_time_label_for(prog.completed_at),
                title=(
                    f"⚠ {sname} flaggar stöd-behov"
                    if flagged else
                    f"Ny reflektion · {sname}"
                ),
                body=(
                    f"<em>{step.title}</em>: \"{preview}\""
                    if preview else f"<em>{step.title}</em>"
                ),
                unread=True,
                target_route="/teacher/v2/reflektioner",
            ))

        # 2. Försenade uppdrag (due_date passerat, ej klart)
        overdue_assignments = (
            ms.query(_SchoolAssignment)
            .filter(
                _SchoolAssignment.teacher_id == teacher_id,
                _SchoolAssignment.student_id.in_(student_ids),
                _SchoolAssignment.due_date.is_not(None),
                _SchoolAssignment.due_date < now,
                _SchoolAssignment.manually_completed_at.is_(None),
            )
            .order_by(_SchoolAssignment.due_date.desc())
            .limit(5)
            .all()
        )
        for a in overdue_assignments:
            sname = name_by_id.get(a.student_id, "Okänd elev")
            days_late = (now - a.due_date).days if a.due_date else 0
            notifs.append(V2Notification(
                id=f"overdue-{a.id}",
                kind="uppdrag",
                icon="▷",
                occurred_at=a.due_date or now,
                time_label=_time_label_for(a.due_date or now),
                title=f"FÖRSENAT UPPDRAG · {sname}",
                body=(
                    f"<em>{a.title}</em> · "
                    f"{days_late} d försenat"
                ),
                unread=True,
                target_route=f"/teacher/v2/uppdrag/{a.student_id}",
            ))

        # 3. Pågående lönesamtal nära smärtgräns
        active_negs = (
            ms.query(_SalaryNegotiation)
            .filter(
                _SalaryNegotiation.student_id.in_(student_ids),
                _SalaryNegotiation.status == "active",
            )
            .order_by(_SalaryNegotiation.started_at.desc())
            .all()
        )
        for neg in active_negs:
            last_round = (
                ms.query(_NegotiationRound)
                .filter(_NegotiationRound.negotiation_id == neg.id)
                .order_by(_NegotiationRound.round_no.desc())
                .first()
            )
            if last_round is None or last_round.proposed_pct is None:
                continue
            if last_round.proposed_pct < 6.0:
                continue
            sname = name_by_id.get(neg.student_id, "Okänd elev")
            notifs.append(V2Notification(
                id=f"maria-pain-{neg.id}",
                kind="modul",
                icon="M",
                occurred_at=last_round.created_at,
                time_label=_time_label_for(last_round.created_at),
                title=f"⚠ Maria nära smärtgräns · {sname}",
                body=(
                    f"R{last_round.round_no} · "
                    f"{last_round.proposed_pct:.1f} % bud · "
                    f"{neg.profession}"
                ),
                unread=True,
                target_route=f"/teacher/v2/maria/{neg.student_id}",
            ))

        # 4. Olästa elev-meddelanden (sender_role=student)
        from ..school.models import Message as _M
        unread_msgs = (
            ms.query(_M)
            .filter(
                _M.student_id.in_(student_ids),
                _M.sender_role == "student",
                _M.read_at.is_(None),
                _M.created_at >= cutoff,
            )
            .order_by(_M.created_at.desc())
            .limit(10)
            .all()
        )
        for m in unread_msgs:
            sname = name_by_id.get(m.student_id, "Okänd elev")
            preview = (m.body or "")[:120]
            if len(m.body or "") > 120:
                preview += "…"
            notifs.append(V2Notification(
                id=f"stu-msg-{m.id}",
                kind="teacher",
                icon=sname[:2].upper() if sname else "??",
                occurred_at=m.created_at,
                time_label=_time_label_for(m.created_at),
                title=f"Meddelande från {sname}",
                body=preview,
                unread=True,
                target_route=f"/teacher/v2/messages/{m.student_id}",
            ))

    # 5. Elever som behöver stöd (pent < 40 eller 7+ d inaktiv)
    needs_help_count = 0
    for st in students:
        wb = _safe_calc_wellbeing_for(st)
        if wb is None:
            continue
        total, eco, safe, health, social, leisure = wb
        red_axes = sum(
            1 for v in (eco, safe, health, social, leisure) if v < 40
        )
        days_inactive = _days_since(st.last_login_at)
        if (
            total < 40
            or (days_inactive is not None and days_inactive >= 7)
            or red_axes >= 3
        ):
            needs_help_count += 1
    if needs_help_count > 0:
        notifs.append(V2Notification(
            id=f"needs-help-{needs_help_count}",
            kind="uppdrag",
            icon="!",
            occurred_at=now - timedelta(minutes=1),
            time_label="just nu",
            title=f"{needs_help_count} elev{'er' if needs_help_count != 1 else ''} behöver stöd",
            body=(
                "Pentagon &lt; 40, inaktiv 7+ d eller "
                "3+ röda axlar — se klass-hubben."
            ),
            unread=True,
            target_route="/teacher/v2",
        ))

    notifs.sort(key=lambda n: n.occurred_at, reverse=True)
    today_count = sum(
        1 for n in notifs if (now - n.occurred_at).days == 0
    )
    unread_count = sum(1 for n in notifs if n.unread)
    by_kind: dict[str, int] = {}
    for n in notifs:
        by_kind[n.kind] = by_kind.get(n.kind, 0) + 1

    summary = V2NotificationsSummary(
        total_count=len(notifs),
        unread_count=unread_count,
        new_today_count=today_count,
        by_kind=by_kind,
    )
    return V2NotificationsResponse(summary=summary, items=notifs)


# === Skapa uppdrag (Fas 2AF) ===
#
# Lärare kan skapa uppdrag direkt från v2-elev-detaljen utan att gå
# via v1-flödet. Stöder både kind="free_text" (manuell-bedömt) och
# automatiska kinds via existerande evaluate()-motor.


class V2CreateAssignmentIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=2, max_length=2000)
    kind: str = Field(default="free_text", min_length=2, max_length=30)
    target_year_month: Optional[str] = Field(
        default=None, pattern=r"^\d{4}-\d{2}$",
    )
    due_date: Optional[datetime] = None
    params: Optional[dict] = None


class V2CreateAssignmentResult(BaseModel):
    assignment_id: int
    student_id: int
    title: str
    kind: str
    due_date: Optional[datetime]
    created_at: datetime


@router.post(
    "/teacher/students/{student_id}/uppdrag",
    response_model=V2CreateAssignmentResult,
)
def teacher_create_assignment_v2(
    student_id: int,
    body: V2CreateAssignmentIn,
    info: TokenInfo = Depends(require_token),
) -> V2CreateAssignmentResult:
    """Skapa ett uppdrag direkt från lärar-elev-detaljen."""
    teacher_id = _require_teacher(info)

    with master_session() as ms:
        student = ms.get(Student, student_id)
        if not student or student.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Endast egen elev",
            )
        a = _SchoolAssignment(
            teacher_id=teacher_id,
            student_id=student_id,
            title=body.title.strip(),
            description=body.description.strip(),
            kind=body.kind,
            target_year_month=body.target_year_month,
            due_date=body.due_date,
            params=body.params,
        )
        ms.add(a); ms.flush()
        aid = a.id
        created_at = a.created_at
        ms.commit()

    return V2CreateAssignmentResult(
        assignment_id=aid,
        student_id=student_id,
        title=body.title.strip(),
        kind=body.kind,
        due_date=body.due_date,
        created_at=created_at,
    )


# === Nivå-promotion + kompetens-override (Fas 2AG) ===
#
# Lärar-actions som direkt påverkar elevens v2-läge:
# - Aktivera Nivå 2/3 → bumpar v2_level + spend_profile + skapar
#   StudentActivity-event för spårbarhet
# - Höj/sänk kompetens manuellt → skapar StudentCompetencyOverride
#   som vinner över mastery-beräkning


class V2LevelPromoteIn(BaseModel):
    target_level: int = Field(ge=2, le=3)
    new_spend_profile: Optional[SpendProfile] = None
    motivation: Optional[str] = Field(default=None, max_length=2000)


class V2LevelPromoteResult(BaseModel):
    student_id: int
    student_name: str
    previous_level: int
    new_level: int
    new_spend_profile: Optional[str]


@router.post(
    "/teacher/students/{student_id}/level-promote",
    response_model=V2LevelPromoteResult,
)
def teacher_promote_student_level(
    student_id: int,
    body: V2LevelPromoteIn,
    info: TokenInfo = Depends(require_token),
) -> V2LevelPromoteResult:
    """Bumpa elevens v2_level (max 3). Default ny spend_profile speglar
    nivån (1=sparsam, 2=balanserad, 3=slosa) — kan överridas av lärare.
    Skapar StudentActivity-event så promotionen syns i historik."""
    from ..school.models import StudentActivity as _SA

    teacher_id = _require_teacher(info)
    with master_session() as ms:
        student = ms.get(Student, student_id)
        if not student or student.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Endast egen elev",
            )
        prev_level = getattr(student, "v2_level", None) or 1
        if body.target_level <= prev_level:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Eleven är redan på Nivå {prev_level}",
            )
        student.v2_level = body.target_level
        spend = body.new_spend_profile or _resolve_spend_profile(
            None, body.target_level,
        )
        student.v2_spend_profile = spend
        # Logga som aktivitet
        summary = (
            f"Lärare aktiverade Nivå {body.target_level} "
            f"({_level_label(body.target_level)})"
        )
        if body.motivation:
            summary += f" · motivering: {body.motivation[:120]}"
        ms.add(_SA(
            student_id=student_id,
            kind="level.promoted",
            summary=summary,
            payload={
                "from_level": prev_level,
                "to_level": body.target_level,
                "new_spend_profile": spend,
                "motivation": body.motivation,
                "teacher_id": teacher_id,
            },
        ))
        ms.commit()
        ms.refresh(student)
        sname = student.display_name

    return V2LevelPromoteResult(
        student_id=student_id,
        student_name=sname,
        previous_level=prev_level,
        new_level=body.target_level,
        new_spend_profile=spend,
    )


class V2CompetencyOverrideIn(BaseModel):
    level: Literal["B", "G", "F"]
    motivation: str = Field(min_length=2, max_length=2000)


class V2CompetencyOverrideRow(BaseModel):
    competency_id: int
    competency_key: str
    competency_name: str
    level: Literal["B", "G", "F"]
    motivation: str
    updated_at: datetime
    teacher_id: int


@router.post(
    "/teacher/students/{student_id}/kompetens/{competency_id}/override",
    response_model=V2CompetencyOverrideRow,
)
def teacher_override_competency(
    student_id: int,
    competency_id: int,
    body: V2CompetencyOverrideIn,
    info: TokenInfo = Depends(require_token),
) -> V2CompetencyOverrideRow:
    """Skapa eller uppdatera lärar-overriden för en kompetens på en elev.

    Vinner över mastery-beräknad nivå. Frontend visar overriden i
    portfolio + kompetens-detalj med "(höjd manuellt av lärare)"-tag.
    """
    from ..school.models import (
        StudentCompetencyOverride as _SCO,
        StudentActivity as _SA,
    )

    teacher_id = _require_teacher(info)
    with master_session() as ms:
        student = ms.get(Student, student_id)
        if not student or student.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Endast egen elev",
            )
        comp = ms.get(_SchoolCompetency, competency_id)
        if comp is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Kompetensen finns ej",
            )
        existing = (
            ms.query(_SCO)
            .filter(
                _SCO.student_id == student_id,
                _SCO.competency_id == competency_id,
            )
            .first()
        )
        if existing is None:
            row = _SCO(
                student_id=student_id,
                competency_id=competency_id,
                level=body.level,
                motivation=body.motivation.strip(),
                teacher_id=teacher_id,
            )
            ms.add(row)
        else:
            row = existing
            row.level = body.level
            row.motivation = body.motivation.strip()
            row.teacher_id = teacher_id
            row.updated_at = datetime.utcnow()
        ms.flush()
        ms.add(_SA(
            student_id=student_id,
            kind="competency.override",
            summary=(
                f"Lärare satte {comp.name} → {body.level} manuellt"
            ),
            payload={
                "competency_id": competency_id,
                "competency_key": comp.key,
                "level": body.level,
                "motivation": body.motivation,
                "teacher_id": teacher_id,
            },
        ))
        ms.commit()
        ms.refresh(row)

    return V2CompetencyOverrideRow(
        competency_id=competency_id,
        competency_key=comp.key,
        competency_name=comp.name,
        level=body.level,
        motivation=body.motivation,
        updated_at=row.updated_at,
        teacher_id=teacher_id,
    )


@router.delete(
    "/teacher/students/{student_id}/kompetens/{competency_id}/override",
)
def teacher_delete_competency_override(
    student_id: int,
    competency_id: int,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Ta bort overrid · mastery-beräkning återupptas."""
    from ..school.models import StudentCompetencyOverride as _SCO

    teacher_id = _require_teacher(info)
    with master_session() as ms:
        student = ms.get(Student, student_id)
        if not student or student.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Endast egen elev",
            )
        existing = (
            ms.query(_SCO)
            .filter(
                _SCO.student_id == student_id,
                _SCO.competency_id == competency_id,
            )
            .first()
        )
        if existing is None:
            return {"deleted": False}
        ms.delete(existing)
        ms.commit()
    return {"deleted": True}


# === Klass-pentagon flip-card (Fas 2AH) ===
#
# Klick på en axel på klass-hub-pentagon visar:
# - Klassens snitt på axeln
# - Sortering: elever som drar UPP snittet (top 3) + drar NER (top 3)
# - Pedagogisk text om axeln


class V2KlassAxisStudentRow(BaseModel):
    student_id: int
    student_name: str
    axis_value: int
    pent_total: int
    delta_from_avg: int  # +/-


class V2KlassAxisDetail(BaseModel):
    axis: PentAxis
    axis_label: str
    axis_number: str
    klass_avg: int
    klass_total_avg: int
    student_count: int
    distribution: dict[str, int]  # {"<40": N, "40-59": N, ...}
    top_contributors: list[V2KlassAxisStudentRow]  # drar upp
    bottom_contributors: list[V2KlassAxisStudentRow]  # drar ner
    summary_text: str


@router.get(
    "/teacher/klass-pentagon/axis/{axis}",
    response_model=V2KlassAxisDetail,
)
def teacher_klass_pentagon_axis(
    axis: PentAxis,
    info: TokenInfo = Depends(require_token),
) -> V2KlassAxisDetail:
    """Per-axel-detalj för klass-pentagon flip-card."""
    teacher_id = _require_teacher(info)

    with master_session() as ms:
        students = (
            ms.query(Student)
            .filter(
                Student.teacher_id == teacher_id,
                Student.active.is_(True),
            )
            .all()
        )

    if not students:
        return V2KlassAxisDetail(
            axis=axis,
            axis_label=_AXIS_LABELS[axis],
            axis_number=_AXIS_NUMBER[axis],
            klass_avg=50,
            klass_total_avg=50,
            student_count=0,
            distribution={},
            top_contributors=[],
            bottom_contributors=[],
            summary_text="Klassen har inga aktiva elever än.",
        )

    rows: list[tuple[Student, int, int]] = []  # (student, axis_value, total)
    for st in students:
        wb = _safe_calc_wellbeing_for(st)
        if wb is None:
            wb = (50, 50, 50, 50, 50, 50)
        total, eco, safe, health, social, leisure = wb
        axis_value = {
            "economy": eco, "safety": safe, "health": health,
            "social": social, "leisure": leisure,
        }[axis]
        rows.append((st, axis_value, total))

    klass_avg = round(sum(r[1] for r in rows) / len(rows))
    klass_total_avg = round(sum(r[2] for r in rows) / len(rows))

    # Distribution
    dist = {"<40": 0, "40-59": 0, "60-79": 0, "80+": 0}
    for _, val, _ in rows:
        if val < 40:
            dist["<40"] += 1
        elif val < 60:
            dist["40-59"] += 1
        elif val < 80:
            dist["60-79"] += 1
        else:
            dist["80+"] += 1

    # Top + bottom · 3 elever varje
    sorted_desc = sorted(rows, key=lambda r: -r[1])
    sorted_asc = sorted(rows, key=lambda r: r[1])
    top_count = min(3, len(rows))
    bottom_count = min(3, len(rows))

    top_contributors = [
        V2KlassAxisStudentRow(
            student_id=st.id,
            student_name=st.display_name,
            axis_value=val,
            pent_total=total,
            delta_from_avg=val - klass_avg,
        )
        for st, val, total in sorted_desc[:top_count]
    ]
    bottom_contributors = [
        V2KlassAxisStudentRow(
            student_id=st.id,
            student_name=st.display_name,
            axis_value=val,
            pent_total=total,
            delta_from_avg=val - klass_avg,
        )
        for st, val, total in sorted_asc[:bottom_count]
    ]

    spread = max(r[1] for r in rows) - min(r[1] for r in rows)
    if klass_avg >= 70:
        verdict = "stark"
    elif klass_avg >= 50:
        verdict = "OK"
    else:
        verdict = "svag"
    summary_text = (
        f"{_AXIS_LABELS[axis]} · klassens snitt {klass_avg}/100 "
        f"({verdict}). Spridning {spread} p mellan högsta och lägsta. "
        f"{dist['<40']} elev{'er' if dist['<40'] != 1 else ''} ligger "
        f"under 40 — bör få extra stöd."
    )

    return V2KlassAxisDetail(
        axis=axis,
        axis_label=_AXIS_LABELS[axis],
        axis_number=_AXIS_NUMBER[axis],
        klass_avg=klass_avg,
        klass_total_avg=klass_total_avg,
        student_count=len(rows),
        distribution=dist,
        top_contributors=top_contributors,
        bottom_contributors=bottom_contributors,
        summary_text=summary_text,
    )


# === Login-QR-kod (Fas 2AJ) ===
#
# Genererar QR-kod för en elev-login-kod som SVG (skalbar, fungerar
# i tryck). URL:en pekar på elevens login-sida med koden förifylld.


class V2LoginQrResponse(BaseModel):
    student_id: int
    student_name: str
    login_code: str
    login_url: str
    qr_svg: str  # Inbäddningsbar SVG-string


def _build_login_url(login_code: str, base_url: Optional[str] = None) -> str:
    """Bygg URL till student-login-sidan med koden förifylld.

    Använder konfigurerad PUBLIC_BASE_URL om satt, annars relativ
    URL — lärare kan klistra in basen själva i mailet.
    """
    from ..config import settings
    base = (
        getattr(settings, "public_base_url", None)
        or "https://ekonomilabbet.org"
    )
    return f"{base.rstrip('/')}/login?code={login_code}"


def _make_qr_svg(data: str, scale: int = 8) -> str:
    """Generera QR-kod som inline SVG-string. Pure-Python (ingen
    Pillow-dependency för SVG-faktor). Returneras som UTF-8 sträng."""
    import qrcode
    import qrcode.image.svg as qsvg
    factory = qsvg.SvgPathImage
    img = qrcode.make(
        data,
        image_factory=factory,
        box_size=scale,
        border=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    import io as _io
    buf = _io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


@router.get(
    "/teacher/students/{student_id}/login-qr",
    response_model=V2LoginQrResponse,
)
def teacher_get_login_qr(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> V2LoginQrResponse:
    """Returnerar elevens login-URL + QR-kod som SVG.

    Lärare kan visa QR:en direkt i klassrummet (eleven scannar med
    mobilen) eller skriva ut + dela.
    """
    teacher_id = _require_teacher(info)
    with master_session() as ms:
        student = ms.get(Student, student_id)
        if not student or student.teacher_id != teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Endast egen elev",
            )
        if not student.login_code:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Eleven saknar login-kod",
            )
        url = _build_login_url(student.login_code)
        svg = _make_qr_svg(url)
        return V2LoginQrResponse(
            student_id=student_id,
            student_name=student.display_name,
            login_code=student.login_code,
            login_url=url,
            qr_svg=svg,
        )


# === Bulk-QR (Fas 2AP) ===
#
# Lärare kan hämta alla elevers login-koder + QR i ett anrop, för att
# skriva ut allt på en gång. Per elev returneras login-kod, URL och
# inbäddad SVG.


class V2BulkLoginQrItem(BaseModel):
    student_id: int
    student_name: str
    login_code: str
    login_url: str
    qr_svg: str


class V2BulkLoginQrResponse(BaseModel):
    teacher_id: int
    teacher_name: str
    items: list[V2BulkLoginQrItem]


@router.get(
    "/teacher/students/login-qr-bulk",
    response_model=V2BulkLoginQrResponse,
)
def teacher_get_login_qr_bulk(
    info: TokenInfo = Depends(require_token),
) -> V2BulkLoginQrResponse:
    """Returnerar QR + login-kod för ALLA lärarens aktiva elever.

    Frontend använder detta för "Skriv ut alla koder"-funktionen.
    """
    teacher_id = _require_teacher(info)
    items: list[V2BulkLoginQrItem] = []
    teacher_name = "Lärare"
    with master_session() as ms:
        teacher = ms.get(Teacher, teacher_id)
        if teacher is not None:
            teacher_name = teacher.name or teacher_name
        students = (
            ms.query(Student)
            .filter(
                Student.teacher_id == teacher_id,
                Student.active.is_(True),
            )
            .order_by(Student.display_name)
            .all()
        )
        for st in students:
            if not st.login_code:
                continue
            url = _build_login_url(st.login_code)
            try:
                svg = _make_qr_svg(url)
            except Exception:
                continue
            items.append(V2BulkLoginQrItem(
                student_id=st.id,
                student_name=st.display_name,
                login_code=st.login_code,
                login_url=url,
                qr_svg=svg,
            ))
    return V2BulkLoginQrResponse(
        teacher_id=teacher_id,
        teacher_name=teacher_name,
        items=items,
    )
