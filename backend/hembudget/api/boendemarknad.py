"""Boendemarknad-API · /v2/boendemarknad/*

Spec: dev/game-motor/06-boendemarknaden.md (Endpoints)

Endpoints (eleven):
  GET  /v2/boendemarknad/listings?ym=YYYY-MM&n=6
  GET  /v2/boendemarknad/my-home/valuation?ym=YYYY-MM
  POST /v2/boendemarknad/buy/{listing_id}
  POST /v2/boendemarknad/sell

Endpoints (lärare):
  GET  /v2/teacher/boendemarknad/listings?city=stockholm&ym=YYYY-MM&n=6
       — för förhandsvisning utan att vara inloggad som elev
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date as _date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..db.base import session_scope
from ..db.models import Account, Loan, Transaction
from ..game_engine.housing_market import (
    HomeValuation,
    HousingListing,
    buy_listing,
    ensure_active_home,
    get_active_home,
    give_notice_on_rental,
    household_size_for,
    listings_for_city,
    market_price_for,
    min_kvm_for_household,
    move_to_rental,
    sell_current_home,
    valuate_current_home,
)
from ..game_engine.profile_generator.schema import (
    FamilyChoice,
    GeneratedProfile,
    HousingChoice,
    PentagonInit,
)
from ..game_engine.pools.stadspool import STAD_BY_KEY, STADSPOOL
from ..school.engines import master_session
from ..school.models import Student, StudentProfile
from .deps import TokenInfo, require_token

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/boendemarknad", tags=["boendemarknad"])
teacher_router = APIRouter(
    prefix="/v2/teacher/boendemarknad",
    tags=["teacher-boendemarknad"],
)


# === Schemas ===


class ListingOut(BaseModel):
    listing_id: str
    city_key: str
    city_display: str
    type: str
    address: str
    size_kvm: int
    rooms: int
    asking_price: int
    monthly_avgift: int
    description: str
    quality_score: int


class ValuationOut(BaseModel):
    has_owned_home: bool
    purchase_price: Optional[int]
    current_value: Optional[int]
    unrealized_gain: Optional[int]
    loan_balance: Optional[int]
    equity: Optional[int]
    city_key: Optional[str]
    note: Optional[str] = None


class BuyIn(BaseModel):
    year_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    listing_id: str


class BuyOut(BaseModel):
    listing_id: str
    accepted: bool
    loan_id: Optional[int]
    monthly_cost: int
    cash_required: int
    pentagon_delta: dict[str, int]
    error: Optional[str]


class SellOut(BaseModel):
    estimated_value: int
    estimated_proceeds_after_costs: int
    sell_horizon_months: int
    capital_gain_estimate: int
    pentagon_delta: dict[str, int]


class CityListingsOut(BaseModel):
    city_key: str
    city_display: str
    year_month: str
    market_price_per_kvm: int
    listings: list[ListingOut]


# === Sprint 5b · ActiveHome-schemas ===


class ActiveHomeOut(BaseModel):
    """Status för elevens nuvarande boende (Sprint 5b)."""
    id: int
    home_type: str
    status: str
    city_key: str
    address: Optional[str]
    size_kvm: int
    rooms: int
    monthly_cost: int
    purchase_price: Optional[int]
    loan_id: Optional[int]
    listing_id: Optional[str]
    entered_on: str
    termination_date: Optional[str]
    estimated_sale_date: Optional[str]
    household_size_when_chosen: int


class TerminateIn(BaseModel):
    year_month: str = Field(pattern=r"^\d{4}-\d{2}$")


class TerminateOut(BaseModel):
    home_id: int
    status: str
    termination_date: str
    months_until_termination: int


class MoveRentalIn(BaseModel):
    year_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    listing_id: str
    listing_size_kvm: int
    listing_address: str
    listing_monthly_cost: int


# === Helpers ===


def _city_key_from_display(display: Optional[str]) -> Optional[str]:
    """StudentProfile.city är display-namn ('Stockholm', 'Medelstor stad'...).
    Vi mappar tillbaka till stadspoolens key.
    """
    if not display:
        return None
    norm = display.strip().lower()
    for key, stad in STAD_BY_KEY.items():
        if stad.display.lower() == norm:
            return key
        if key == norm:
            return key
    return None


def _profile_from_studentprofile(sp: StudentProfile) -> GeneratedProfile:
    """Bygg en minimal GeneratedProfile från en lagrad StudentProfile.

    Räcker för housing_market.valuate_current_home + buy_listing — vi
    behöver bara housing + city. Pentagon, family etc. fylls med
    defaults; de används inte i housing_market-flödet.
    """
    city_key = _city_key_from_display(sp.city) or "medelstad"
    city = STAD_BY_KEY.get(city_key) or STAD_BY_KEY["medelstad"]
    h = HousingChoice(
        type=sp.housing_type if sp.housing_type in (
            "hyresratt", "bostadsratt", "villa", "radhus",
        ) else "hyresratt",
        size_kvm=max(22, sp.housing_monthly // 100),  # rough proxy
        monthly_cost=sp.housing_monthly,
    )
    return GeneratedProfile(
        seed=sp.student_id or 0,
        name="Eleven",
        yrke_key="okand",
        yrke_display="Okänd",
        yrke_ssyk="0000",
        monthly_gross=sp.gross_salary_monthly,
        monthly_net=sp.net_salary_monthly,
        city_key=city_key,
        city_display=city.display,
        region=city.region,
        housing=h,
        family=FamilyChoice(status=sp.family_status, partner_model="solo"),
        household_gross_monthly=sp.gross_salary_monthly,
        household_net_monthly=sp.net_salary_monthly,
        pentagon=PentagonInit(
            economy=60, safety=60, health=60, social=60, leisure=60,
        ),
        facts={"age": sp.age},
    )


def _require_student(info: TokenInfo) -> int:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast elev-konto kan använda boendemarknaden.",
        )
    return info.student_id


def _checking_balance() -> int:
    """Summera elevens checking-konto-saldo (inom scope-context).

    Anropas inuti session_scope så scope auto-filter på tenant_id.
    """
    with session_scope() as s:
        accs = s.query(Account).filter(Account.type == "checking").all()
        total = Decimal(0)
        for a in accs:
            base = a.opening_balance or Decimal(0)
            txs = s.query(Transaction).filter(
                Transaction.account_id == a.id,
            ).all()
            total += base + sum(
                ((t.amount or Decimal(0)) for t in txs), Decimal(0),
            )
        return int(total)


def _create_termination_notice(
    s,
    *,
    home_address: Optional[str],
    home_size_kvm: int,
    home_monthly_cost: int,
    termination_date: date,
    today_g: date,
    reason: str,
    city_key: Optional[str] = None,
) -> None:
    """Skapa bekräftelsebrev (MailItem) + RentalNotice när hyresrätt
    sägs upp. Pedagogiskt: ger eleven en formell handling med alla
    villkor + lägger en rad i 'Hyresnotiser & brev från värden'-
    sektionen i Boendemarknadens Hyresavtal-tab."""
    from ..db.models import MailItem as _MI_t, RentalNotice as _RN_t
    landlord = (
        f"{city_key.title()} Bostäder"
        if city_key else "Hyresvärden"
    )
    addr = home_address or "din bostad"
    body = (
        f"Uppsägning bekräftad\n\n"
        f"Vi har tagit emot din uppsägning av hyreskontraktet för "
        f"{addr} ({home_size_kvm} kvm).\n\n"
        f"Anledning: {reason}\n\n"
        f"Villkor enligt hyresavtalet:\n"
        f"· Uppsägningstid: 3 månader\n"
        f"· Sista anställningsdag: {termination_date.isoformat()}\n"
        f"· Hyra ska betalas månadsvis under uppsägningstiden "
        f"({home_monthly_cost:,} kr/mån)\n".replace(",", " ")
        + f"· Avflyttningsbesiktning bokas inom 14 dagar före "
        + f"avflyttning\n· Eventuell deposition återbetalas efter "
        + f"slutbesiktning\n\n"
        + f"Tre vanliga månadshyror (en per kvarvarande uppsägnings-"
        + f"månad) kommer som separata avier i din postlåda.\n\n"
        + f"Mvh, {landlord}"
    )
    s.add(_MI_t(
        sender=landlord,
        sender_short="HYR",
        sender_kind="land",
        sender_meta="uppsägning · bekräftelse",
        mail_type="info",
        subject=(
            f"Uppsägning bekräftad · sista dag {termination_date.isoformat()}"
        ),
        body_meta=(
            f"3 mån uppsägningstid · {home_monthly_cost:,} kr/mån"
            .replace(",", " ")
        ),
        body=body,
        amount=None,
        due_date=None,
        status="unhandled",
        received_at=datetime.combine(
            today_g, datetime.min.time(),
        ).replace(hour=10),
    ))
    # Synas i 'Hyresnotiser & brev från värden'-sektionen
    s.add(_RN_t(
        contract_id=None,  # virtuellt — ingen RentalContract-koppling
        occurred_on=today_g,
        notice_type="ovrig",
        title=f"Uppsägning bekräftad · {addr}",
        description=(
            f"Uppsägning av {addr} bekräftad. Sista dag "
            f"{termination_date.isoformat()}. Anledning: {reason}."
        ),
        amount=None,
        change_pct=None,
        status="acknowledged",
    ))


# === Elev-endpoints ===


@router.get("/listings", response_model=CityListingsOut)
def get_listings(
    ym: str = "2026-01",
    n: int = 6,
    only_household_fit: bool = True,
    info: TokenInfo = Depends(require_token),
):
    """Listings i elevens stad för given spelmånad.

    `only_household_fit=True` (default) filtrerar bort listings för
    små för elevens hushåll (Konsumentverkets norm).
    """
    sid = _require_student(info)
    with master_session() as s:
        sp = (
            s.query(StudentProfile)
            .filter(StudentProfile.student_id == sid)
            .first()
        )
        if sp is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "Elevens profil saknas — kan inte avgöra stad.",
            )
        city_key = _city_key_from_display(sp.city) or "medelstad"

        # Räkna ut min-kvm för hushållet
        n_persons = 1
        if sp.partner_age:
            n_persons += 1
        if sp.children_ages:
            n_persons += len(sp.children_ages)
        min_kvm = (
            min_kvm_for_household(sp.family_status, n_persons)
            if only_household_fit else 0
        )

    city = STAD_BY_KEY.get(city_key) or STAD_BY_KEY["medelstad"]
    listings = listings_for_city(
        city_key, ym, n=max(1, min(n, 12)), min_size_kvm=min_kvm,
    )
    return CityListingsOut(
        city_key=city_key,
        city_display=city.display,
        year_month=ym,
        market_price_per_kvm=market_price_for(city_key, ym),
        listings=[ListingOut(**asdict(l)) for l in listings],
    )


@router.get("/my-home/valuation", response_model=ValuationOut)
def get_my_valuation(
    ym: str = "2026-01",
    info: TokenInfo = Depends(require_token),
):
    """Aktuell värdering av elevens nuvarande boende."""
    sid = _require_student(info)
    with master_session() as s:
        sp = (
            s.query(StudentProfile)
            .filter(StudentProfile.student_id == sid)
            .first()
        )
        if sp is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Elevens profil saknas.",
            )

    profile = _profile_from_studentprofile(sp)
    with session_scope() as s:
        valuation = valuate_current_home(s, profile=profile, year_month=ym)
    return ValuationOut(**asdict(valuation))


@router.post("/buy/{listing_id}", response_model=BuyOut)
def buy(
    listing_id: str,
    body: BuyIn,
    info: TokenInfo = Depends(require_token),
):
    """Köp en listing. Elevens checking-saldo måste täcka kontantinsats."""
    sid = _require_student(info)
    with master_session() as s:
        sp = (
            s.query(StudentProfile)
            .filter(StudentProfile.student_id == sid)
            .first()
        )
        if sp is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Elevens profil saknas.",
            )
        student = s.get(Student, sid)
        if student is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Elev saknas.")
        from ..school.engines import scope_for_student
        scope_key = scope_for_student(student)
        s.expunge(student)

    profile = _profile_from_studentprofile(sp)
    if profile.city_key != listing_id.split("-")[0]:
        # Listing-id format: {city}-{ym}-{idx}
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Du kan bara köpa bostäder i din stad.",
        )

    # Hämta listings för rätt month + hitta exakt id
    listings = listings_for_city(
        profile.city_key, body.year_month, n=12,
    )
    listing = next((l for l in listings if l.listing_id == listing_id), None)
    if listing is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Listing finns inte denna månad.",
        )

    cash = _checking_balance()
    with session_scope() as s:
        result = buy_listing(
            s,
            student_id=sid,
            student_scope=scope_key,
            listing=listing,
            available_cash=cash,
            year_month=body.year_month,
        )
    return BuyOut(
        listing_id=result.listing_id,
        accepted=result.accepted,
        loan_id=result.loan_id,
        monthly_cost=result.monthly_cost,
        cash_required=result.cash_required,
        pentagon_delta=result.pentagon_delta,
        error=result.error,
    )


class SellIn(BaseModel):
    year_month: str = Field(pattern=r"^\d{4}-\d{2}$")


@router.post("/sell", response_model=SellOut)
def sell(
    body: SellIn,
    info: TokenInfo = Depends(require_token),
):
    """Lägg ut elevens nuvarande bostad till försäljning."""
    sid = _require_student(info)
    with master_session() as s:
        sp = (
            s.query(StudentProfile)
            .filter(StudentProfile.student_id == sid)
            .first()
        )
        if sp is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Elevens profil saknas.",
            )
        student = s.get(Student, sid)
        from ..school.engines import scope_for_student
        scope_key = scope_for_student(student) if student else f"s_{sid}"
        if student is not None:
            s.expunge(student)

    profile = _profile_from_studentprofile(sp)
    with session_scope() as scope_s:
        valuation = valuate_current_home(
            scope_s, profile=profile, year_month=body.year_month,
        )
        if not valuation.has_owned_home or valuation.current_value is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Du äger ingen bostad att sälja.",
            )
        result = sell_current_home(
            scope_s,
            student_id=sid,
            student_scope=scope_key,
            home_value=valuation.current_value,
            purchase_price=valuation.purchase_price or valuation.current_value,
            loan_balance=valuation.loan_balance or 0,
            year_month=body.year_month,
        )
    return SellOut(
        estimated_value=result.estimated_value,
        estimated_proceeds_after_costs=result.estimated_proceeds_after_costs,
        sell_horizon_months=result.sell_horizon_months,
        capital_gain_estimate=result.capital_gain_estimate,
        pentagon_delta=result.pentagon_delta,
    )


# === Sprint 5b · ActiveHome-endpoints ===


@router.get("/my-home", response_model=Optional[ActiveHomeOut])
def get_my_home(
    ym: str = "2026-01",
    info: TokenInfo = Depends(require_token),
):
    """Hämta elevens nuvarande aktiva boende (ActiveHome).

    Skapas automatiskt vid första anrop baserat på StudentProfile-data.
    """
    sid = _require_student(info)
    with master_session() as s:
        sp = (
            s.query(StudentProfile)
            .filter(StudentProfile.student_id == sid)
            .first()
        )
        if sp is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Elevens profil saknas.",
            )
    profile = _profile_from_studentprofile(sp)

    with session_scope() as s:
        home = get_active_home(s)
        if home is None:
            home = ensure_active_home(s, profile=profile, year_month=ym)
            s.flush()
        return ActiveHomeOut(
            id=home.id,
            home_type=home.home_type,
            status=home.status,
            city_key=home.city_key,
            address=home.address,
            size_kvm=home.size_kvm,
            rooms=home.rooms,
            monthly_cost=int(home.monthly_cost or 0),
            purchase_price=int(home.purchase_price) if home.purchase_price else None,
            loan_id=home.loan_id,
            listing_id=home.listing_id,
            entered_on=home.entered_on.isoformat(),
            termination_date=(
                home.termination_date.isoformat()
                if home.termination_date else None
            ),
            estimated_sale_date=(
                home.estimated_sale_date.isoformat()
                if home.estimated_sale_date else None
            ),
            household_size_when_chosen=home.household_size_when_chosen,
        )


@router.post("/terminate-rental", response_model=TerminateOut)
def terminate_rental(
    body: TerminateIn,
    info: TokenInfo = Depends(require_token),
):
    """Säg upp aktivt hyreskontrakt med 3 månaders uppsägning."""
    sid = _require_student(info)
    with master_session() as s:
        sp = (
            s.query(StudentProfile)
            .filter(StudentProfile.student_id == sid)
            .first()
        )
        if sp is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Profil saknas.")
    profile = _profile_from_studentprofile(sp)

    with session_scope() as s:
        # Säkerställ att eleven har en ActiveHome
        ensure_active_home(s, profile=profile, year_month=body.year_month)
        try:
            home = give_notice_on_rental(
                s, student_id=sid, year_month=body.year_month,
            )
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

        # Bekräftelsebrev + RentalNotice för "Hyresnotiser"-sektionen
        try:
            from ..business.game_clock import current_game_date as _cgd_t
            _create_termination_notice(
                s,
                home_address=home.address,
                home_size_kvm=int(home.size_kvm),
                home_monthly_cost=int(home.monthly_cost or 0),
                termination_date=home.termination_date,
                today_g=_cgd_t(),
                reason="Egen uppsägning",
                city_key=home.city_key,
            )
        except Exception:
            log.exception(
                "terminate_rental: kunde inte skapa bekräftelsebrev",
            )

        # Räkna månader kvar grovt
        from datetime import date as _d
        today = _d.fromisoformat(f"{body.year_month}-01")
        months = max(0, (
            (home.termination_date.year - today.year) * 12
            + (home.termination_date.month - today.month)
        ))
        return TerminateOut(
            home_id=home.id,
            status=home.status,
            termination_date=home.termination_date.isoformat(),
            months_until_termination=months,
        )


@router.post("/move-rental", response_model=ActiveHomeOut)
def move_rental(
    body: MoveRentalIn,
    info: TokenInfo = Depends(require_token),
):
    """Flytta från en hyresrätt till en annan (mindre/billigare/större).

    `listing_*` fälten beskriver det nya boendet — frontend skickar
    värden från en hyresrätt-listing eller manuellt valda värden.
    """
    sid = _require_student(info)
    with master_session() as s:
        sp = (
            s.query(StudentProfile)
            .filter(StudentProfile.student_id == sid)
            .first()
        )
        if sp is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Profil saknas.")
        student = s.get(Student, sid)
        from ..school.engines import scope_for_student
        scope_key = scope_for_student(student) if student else f"s_{sid}"
        if student is not None:
            s.expunge(student)

    profile = _profile_from_studentprofile(sp)

    # Bygg HousingListing-stub från body
    from ..game_engine.housing_market.listings import HousingListing as HL
    from ..game_engine.pools.stadspool import STAD_BY_KEY as _STAD
    new_listing = HL(
        listing_id=body.listing_id,
        city_key=profile.city_key,
        city_display=_STAD.get(profile.city_key, _STAD["medelstad"]).display,
        type="hyresratt",
        address=body.listing_address,
        size_kvm=body.listing_size_kvm,
        rooms=max(1, body.listing_size_kvm // 30),
        asking_price=0,
        monthly_avgift=body.listing_monthly_cost,
        description="Ny hyresrätt",
        quality_score=5,
    )

    with session_scope() as s:
        ensure_active_home(s, profile=profile, year_month=body.year_month)
        try:
            home = move_to_rental(
                s,
                student_id=sid,
                student_scope=scope_key,
                new_listing=new_listing,
                year_month=body.year_month,
            )
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
        return ActiveHomeOut(
            id=home.id,
            home_type=home.home_type,
            status=home.status,
            city_key=home.city_key,
            address=home.address,
            size_kvm=home.size_kvm,
            rooms=home.rooms,
            monthly_cost=int(home.monthly_cost or 0),
            purchase_price=None,
            loan_id=None,
            listing_id=home.listing_id,
            entered_on=home.entered_on.isoformat(),
            termination_date=None,
            estimated_sale_date=None,
            household_size_when_chosen=home.household_size_when_chosen,
        )


# ===========================================================
# Rental marketplace (Fas 3) · hyra istället för köpa
# ===========================================================


class RentalListingOut(BaseModel):
    listing_id: str
    city_key: str
    city_display: str
    tier: int
    tier_label: str
    address: str
    size_kvm: int
    rooms: int
    monthly_rent: int
    deposit: int
    first_hand: bool
    queue_months: int
    quality_score: int
    description: str


class RentalsListOut(BaseModel):
    city_key: str
    city_display: str
    year_month: str
    listings: list[RentalListingOut]


class RentalMoveInOut(BaseModel):
    home: ActiveHomeOut
    pentagon_deltas: dict
    deposit_charged: int
    welcome_message: str


class RentalApplicationOut(BaseModel):
    id: int
    listing_id: str
    city_key: str
    address: str
    tier: int
    tier_label: str
    size_kvm: int
    rooms: int
    monthly_rent: int
    deposit: int
    quality_score: int
    first_hand: bool
    applied_on: str
    ready_on: str
    status: str
    days_left: int  # Spel-dagar tills man kan flytta in (0 om ready)


class RentalApplicationsOut(BaseModel):
    applications: list[RentalApplicationOut]


def _application_to_out(r) -> RentalApplicationOut:
    from ..business.game_clock import current_game_date
    today_g = current_game_date()
    days_left = max(0, (r.ready_on - today_g).days)
    # Auto-promote status om ready_on passerat
    effective_status = r.status
    if r.status == "queued" and days_left == 0:
        effective_status = "ready"
    return RentalApplicationOut(
        id=r.id,
        listing_id=r.listing_id,
        city_key=r.city_key,
        address=r.address,
        tier=r.tier,
        tier_label=r.tier_label,
        size_kvm=r.size_kvm,
        rooms=r.rooms,
        monthly_rent=r.monthly_rent,
        deposit=r.deposit,
        quality_score=r.quality_score,
        first_hand=r.first_hand,
        applied_on=r.applied_on.isoformat(),
        ready_on=r.ready_on.isoformat(),
        status=effective_status,
        days_left=days_left,
    )


@router.get("/rentals", response_model=RentalsListOut)
def list_rentals(
    ym: str = "2026-01",
    min_tier: int = 1,
    max_tier: int = 4,
    info: TokenInfo = Depends(require_token),
):
    """Lista hyresrätt-listings i elevens stad. 4 tiers:
      1 · korridor/akut       · 12-18 kvm, 3500-5000 kr/mån
      2 · liten lägenhet      · 25-45 kvm, 5500-8500 kr/mån
      3 · familjelägenhet     · 50-85 kvm, 9000-13000 kr/mån
      4 · lyx                 · 90-130 kvm, 14000-22000 kr/mån
    """
    from ..game_engine.housing_market.rentals import list_rentals_for_city
    sid = _require_student(info)
    with master_session() as s:
        sp = (
            s.query(StudentProfile)
            .filter(StudentProfile.student_id == sid)
            .first()
        )
        if sp is None:
            raise HTTPException(404, "Profil saknas.")
    profile = _profile_from_studentprofile(sp)
    city_key = profile.city_key
    listings = list_rentals_for_city(
        city_key=city_key,
        year_month=ym,
        n=12,
        min_tier=min_tier,
        max_tier=max_tier,
    )
    return RentalsListOut(
        city_key=city_key,
        city_display=STAD_BY_KEY.get(
            city_key, STAD_BY_KEY["medelstad"],
        ).display,
        year_month=ym,
        listings=[
            RentalListingOut(**asdict(l)) for l in listings
        ],
    )


@router.get("/rentals/applications", response_model=RentalApplicationsOut)
def list_rental_applications(
    info: TokenInfo = Depends(require_token),
):
    """Lista alla pending rental-applications (kö-ansökningar) för
    inloggade eleven. Frontend visar dessa som "Du står i kö" tills
    days_left = 0, då knappen blir "Flytta in nu"."""
    from ..db.models import RentalApplication
    sid = _require_student(info)
    _ = sid
    with session_scope() as s:
        rows = (
            s.query(RentalApplication)
            .filter(RentalApplication.status.in_(("queued", "ready")))
            .order_by(RentalApplication.ready_on.asc())
            .all()
        )
        return RentalApplicationsOut(
            applications=[_application_to_out(r) for r in rows],
        )


@router.post(
    "/rentals/{listing_id}/apply",
    response_model=RentalApplicationOut,
)
def rental_apply(
    listing_id: str,
    ym: str = "2026-01",
    info: TokenInfo = Depends(require_token),
):
    """Ställ dig i kö för en hyresrätt. Skapar en RentalApplication-
    rad som blir 'ready' när queue_months passerat i spel-tid.

    Om listing.queue_months == 0 kan eleven hoppa kön och direkt
    anropa /move-in istället för att applicera först.
    """
    from ..db.models import RentalApplication
    from ..game_engine.housing_market.rentals import find_rental
    from ..business.game_clock import current_game_date
    from datetime import timedelta as _td_app

    sid = _require_student(info)
    _ = sid
    listing = find_rental(listing_id)
    if listing is None:
        raise HTTPException(404, "Listing hittades inte")

    today_g = current_game_date()
    # Spel-tid: 1 spel-månad = ~4.3 real-timmar. För kö-systemet
    # räknar vi 30 spel-dagar per månad.
    ready_on = today_g + _td_app(days=30 * listing.queue_months)

    with session_scope() as s:
        # Kolla om eleven redan har en pending ansökan för samma listing
        existing = (
            s.query(RentalApplication)
            .filter(
                RentalApplication.listing_id == listing_id,
                RentalApplication.status.in_(("queued", "ready")),
            )
            .first()
        )
        if existing is not None:
            raise HTTPException(
                409, "Du står redan i kö för denna lägenhet",
            )

        app = RentalApplication(
            listing_id=listing.listing_id,
            city_key=listing.city_key,
            address=listing.address,
            tier=listing.tier,
            tier_label=listing.tier_label,
            size_kvm=listing.size_kvm,
            rooms=listing.rooms,
            monthly_rent=listing.monthly_rent,
            deposit=listing.deposit,
            quality_score=listing.quality_score,
            first_hand=listing.first_hand,
            applied_on=today_g,
            ready_on=ready_on,
            status="ready" if listing.queue_months == 0 else "queued",
        )
        s.add(app)
        s.flush()

        # Aktivitetslog
        try:
            from ..school.activity import log_activity
            log_activity(
                kind="private.rental_applied",
                summary=(
                    f"Ställde mig i kö för {listing.address} · "
                    f"{listing.queue_months} mån kö"
                ),
                payload={
                    "listing_id": listing.listing_id,
                    "tier": listing.tier,
                    "queue_months": listing.queue_months,
                    "monthly_rent": listing.monthly_rent,
                },
                student_id=sid,
            )
        except Exception:
            pass

        return _application_to_out(app)


@router.delete(
    "/rentals/applications/{application_id}",
    status_code=204,
)
def cancel_rental_application(
    application_id: int,
    info: TokenInfo = Depends(require_token),
):
    """Avbryt en pending kö-ansökan."""
    from ..db.models import RentalApplication
    sid = _require_student(info)
    _ = sid
    with session_scope() as s:
        row = s.get(RentalApplication, application_id)
        if row is None:
            raise HTTPException(404, "Ansökan hittades inte")
        if row.status not in ("queued", "ready"):
            raise HTTPException(
                400, f"Ansökan har redan status '{row.status}'",
            )
        row.status = "cancelled"
        s.flush()
    return None


@router.post(
    "/rentals/{listing_id}/move-in",
    response_model=RentalMoveInOut,
)
def rental_move_in(
    listing_id: str,
    ym: str = "2026-01",
    info: TokenInfo = Depends(require_token),
):
    """Flytta in i en hyresrätt-listing.

    Effekter:
    - Uppdaterar ActiveHome (status=active, ny address/size/rent)
    - Drar deposition från lönekonto direkt
    - Pentagon-event per tier (se rentals.tier_pentagon_deltas)
    - Skickar välkomstbrev från hyresvärd
    """
    from ..game_engine.housing_market.rentals import (
        find_rental, tier_pentagon_deltas,
    )
    from ..db.models import RentalApplication
    from ..business.game_clock import current_game_date as _cgd_mv
    sid = _require_student(info)
    listing = find_rental(listing_id)
    if listing is None:
        raise HTTPException(404, "Listing hittades inte")

    # Kö-gate: om listing.queue_months > 0 krävs en READY (ej queued)
    # RentalApplication för denna listing. Eleven måste först
    # /apply och vänta tills ready_on passerat. queue_months=0
    # tillåter direkt inflytt utan ansökan.
    pending_app = None
    if listing.queue_months > 0:
        with session_scope() as s_chk:
            today_g = _cgd_mv()
            pending_app = (
                s_chk.query(RentalApplication)
                .filter(
                    RentalApplication.listing_id == listing_id,
                    RentalApplication.status.in_(("queued", "ready")),
                )
                .first()
            )
            if pending_app is None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    (
                        f"Denna lägenhet har {listing.queue_months} mån "
                        "kö. Ställ dig i kön först via /apply."
                    ),
                )
            if pending_app.ready_on > today_g:
                days_left = (pending_app.ready_on - today_g).days
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    (
                        f"Du står i kö men har {days_left} spel-dagar kvar. "
                        f"Kom tillbaka när köandet är klart."
                    ),
                )

    with master_session() as ms:
        sp = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == sid)
            .first()
        )
        if sp is None:
            raise HTTPException(404, "Profil saknas.")
        student = ms.get(Student, sid)
        from ..school.engines import scope_for_student
        scope_key = scope_for_student(student) if student else f"s_{sid}"
        if student is not None:
            ms.expunge(student)
    profile = _profile_from_studentprofile(sp)

    # Validera att eleven har råd med depositionen
    deposit = listing.deposit
    bal = _checking_balance()
    if bal < deposit:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"För lite på lönekontot för deposition: behöver {deposit} kr, "
            f"har {bal} kr",
        )

    from ..game_engine.housing_market.listings import HousingListing as HL
    new_listing = HL(
        listing_id=listing.listing_id,
        city_key=listing.city_key,
        city_display=listing.city_display,
        type="hyresratt",
        address=listing.address,
        size_kvm=listing.size_kvm,
        rooms=listing.rooms,
        asking_price=0,
        monthly_avgift=listing.monthly_rent,
        description=listing.description,
        quality_score=listing.quality_score,
    )

    with session_scope() as s:
        ensure_active_home(s, profile=profile, year_month=ym)
        # Snapshot:a gamla hyran INNAN move_to_rental ändrar status →
        # vi behöver beloppet till uppsägnings-slutfakturan.
        from ..game_engine.housing_market.active_home import (
            get_active_home as _get_active_home,
        )
        prev_home = _get_active_home(s)
        prev_rent = int(prev_home.monthly_cost) if prev_home else 0
        prev_address = prev_home.address if prev_home else None
        try:
            home = move_to_rental(
                s,
                student_id=sid,
                student_scope=scope_key,
                new_listing=new_listing,
                year_month=ym,
            )
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

        # Sync · alla aktiva RentalContract-rader sätts till
        # 'terminated' eftersom eleven har flyttat. Utan detta visar
        # /v2/hyresvarden gamla kontraktet kvar (det query:as före
        # ActiveHome-fallbacken). Ended_on = today_g + 3 mån
        # (uppsägningstid).
        from ..business.game_clock import current_game_date as _cgd_mvi
        from datetime import timedelta as _td_mvi
        today_g_mv = _cgd_mvi()
        ended_on_mv = today_g_mv + _td_mvi(days=90)
        try:
            from ..db.models import RentalContract as _RC_mv
            active_contracts = (
                s.query(_RC_mv)
                .filter(_RC_mv.status == "active")
                .all()
            )
            for c in active_contracts:
                c.status = "terminated"
                if c.ended_on is None:
                    c.ended_on = ended_on_mv
            s.flush()
        except Exception:
            log.exception(
                "rental_move_in: kunde inte synca RentalContract",
            )

        # Bekräftelsebrev + RentalNotice för auto-terminerade gamla
        # lägenheten · syns i Hyresavtal-tabbens 'Hyresnotiser & brev
        # från värden'-sektion.
        if prev_rent > 0 and prev_home and prev_home.id != home.id:
            try:
                _create_termination_notice(
                    s,
                    home_address=prev_address,
                    home_size_kvm=int(prev_home.size_kvm),
                    home_monthly_cost=prev_rent,
                    termination_date=ended_on_mv,
                    today_g=today_g_mv,
                    reason=(
                        f"Flytt till nytt boende · {listing.address}"
                    ),
                    city_key=prev_home.city_key,
                )
            except Exception:
                log.exception(
                    "rental_move_in: kunde inte skapa bekräftelsebrev",
                )

        # Generera 3 vanliga månadshyror för gamla bostaden under
        # uppsägningstiden. I Sverige fungerar det så att hyresgästen
        # är skyldig att betala normal hyra MÅNADSVIS under hela
        # uppsägningsperioden — det finns ingen "slutfaktura" på
        # 3 × hyran. Hyresvärden skickar avier som vanligt.
        #
        # Varje hyresavi får released_at så den dyker upp i postlådan
        # på sin riktiga månad (matchar real-tid-projektionen).
        if prev_rent > 0 and prev_home and prev_home.id != home.id:
            try:
                from ..db.models import MailItem as _MI_avi
                from ..business.game_clock import current_game_date
                from ..game_engine.release_schedule import (
                    release_at_for_day,
                )
                from datetime import datetime as _dt_avi
                today_g = current_game_date()
                base_real = _dt_avi.utcnow()
                landlord = (
                    f"{profile.city_key.title()} Bostäder"
                    if profile.city_key else "Hyresvärden"
                )
                for offset_month in range(1, 4):
                    # Spel-månadens första dag · target_month år/månad
                    target_y = today_g.year
                    target_m = today_g.month + offset_month
                    while target_m > 12:
                        target_m -= 12
                        target_y += 1
                    target_d = date(target_y, target_m, 1)
                    target_ym = f"{target_y:04d}-{target_m:02d}"
                    # released_at: efter offset_month spel-månader
                    # = 30 spel-dagar per offset → real-tid via day mapping
                    released_at = release_at_for_day(
                        base_real, day_in_month=1 + (offset_month - 1) * 30,
                    )
                    s.add(_MI_avi(
                        sender=landlord,
                        sender_short="HYR",
                        sender_kind="land",
                        sender_meta=(
                            f"hyresavi · uppsägningstid · {target_ym}"
                        ),
                        mail_type="invoice",
                        subject=(
                            f"Hyresavi {target_ym} · "
                            f"{prev_address or 'gamla bostaden'}"
                        ),
                        body_meta=(
                            f"Uppsägningstid · "
                            f"{prev_rent:,} kr".replace(",", " ")
                        ),
                        body=(
                            f"Hyresavi för {target_ym}\n\n"
                            f"Trots att du flyttat ut är du skyldig att "
                            f"betala hyra under uppsägningstiden enligt "
                            f"hyresavtalet (LH § 5).\n\n"
                            f"Bostad: {prev_address or 'gamla bostaden'}\n"
                            f"Månadshyra: {prev_rent:,} kr\n".replace(",", " ")
                            + f"Förfaller: {target_d.isoformat()} (den 1:a)\n\n"
                            + f"Detta är månad {offset_month} av 3 i "
                            + f"uppsägningstiden."
                        ),
                        amount=Decimal(-prev_rent),
                        due_date=target_d,
                        status="unhandled",
                        received_at=_dt_avi.combine(
                            target_d, _dt_avi.min.time(),
                        ).replace(hour=9),
                        released_at=released_at,
                    ))
            except Exception:
                log.exception(
                    "rental_move_in: kunde inte skapa hyresavi-serie",
                )

        # Sync StudentProfile (master-DB) så HubV2 + dashboard visar
        # rätt hyra direkt efter inflyttning. Annars säger banner-
        # texten kvar "Hyran på 6 975 kr dras varje månad" trots att
        # eleven har flyttat till en 16 338 kr/mån-lägenhet.
        try:
            with master_session() as ms:
                sp_master = (
                    ms.query(StudentProfile)
                    .filter(StudentProfile.student_id == sid)
                    .first()
                )
                if sp_master is not None:
                    sp_master.housing_type = "hyresratt"
                    sp_master.housing_monthly = listing.monthly_rent
                    ms.commit()
        except Exception:
            log.exception(
                "rental_move_in: kunde inte synca StudentProfile.housing",
            )

        # Dra deposition · Transaction på lönekontot
        acc = (
            s.query(Account)
            .filter(Account.type == "checking")
            .order_by(Account.id.asc())
            .first()
        )
        if acc is not None:
            import hashlib
            tx_hash = hashlib.sha256(
                f"rental-deposit-{listing.listing_id}-{ym}".encode(),
            ).hexdigest()[:32]
            existing = (
                s.query(Transaction)
                .filter(Transaction.hash == tx_hash)
                .first()
            )
            if existing is None:
                from ..business.game_clock import current_game_date
                today_g = current_game_date()
                s.add(Transaction(
                    account_id=acc.id,
                    date=today_g,
                    amount=Decimal(-deposit),
                    currency="SEK",
                    raw_description=(
                        f"Deposition · hyresrätt {listing.address}"
                    ),
                    normalized_merchant="Hyresvärd",
                    hash=tx_hash,
                    user_verified=True,
                ))

        home_out = ActiveHomeOut(
            id=home.id,
            home_type=home.home_type,
            status=home.status,
            city_key=home.city_key,
            address=home.address,
            size_kvm=home.size_kvm,
            rooms=home.rooms,
            monthly_cost=int(home.monthly_cost or 0),
            purchase_price=None,
            loan_id=None,
            listing_id=home.listing_id,
            entered_on=home.entered_on.isoformat(),
            termination_date=None,
            estimated_sale_date=None,
            household_size_when_chosen=home.household_size_when_chosen,
        )

    # Pentagon-event per tier
    deltas = tier_pentagon_deltas(listing.tier)
    try:
        from ..game_engine.pentagon import apply_pentagon_delta
        for axis, delta in deltas.items():
            if delta == 0:
                continue
            apply_pentagon_delta(
                sid,
                axis=axis,
                requested_delta=delta,
                reason_kind="rental_move_in",
                reason_id=home.id,
                reason_table="active_homes",
                explanation=(
                    f"Flyttade in i {listing.tier_label}-lägenhet "
                    f"({listing.size_kvm} kvm, {listing.rooms} rok) · "
                    f"{listing.address}"
                ),
            )
    except Exception:
        log.exception("rental_move_in: pentagon-delta misslyckades")

    # Aktivitetslog
    try:
        from ..school.activity import log_activity
        log_activity(
            kind="private.rental_move_in",
            summary=(
                f"Flyttade in · tier {listing.tier} "
                f"({listing.tier_label}) · "
                f"{listing.size_kvm} kvm, {listing.monthly_rent} kr/mån"
            ),
            payload={
                "listing_id": listing.listing_id,
                "tier": listing.tier,
                "address": listing.address,
                "monthly_rent": listing.monthly_rent,
                "deposit": listing.deposit,
            },
            student_id=sid,
        )
    except Exception:
        pass

    welcome = (
        f"Välkommen till din nya lägenhet på {listing.address}!\n"
        f"{listing.size_kvm} kvm · {listing.rooms} rok · "
        f"{listing.monthly_rent:,} kr/mån".replace(",", " ")
    )

    # Markera rental-application som moved_in (om kö användes)
    if pending_app is not None:
        try:
            with session_scope() as s_done:
                app_row = s_done.get(RentalApplication, pending_app.id)
                if app_row is not None and app_row.status in ("queued", "ready"):
                    app_row.status = "moved_in"
                    s_done.flush()
        except Exception:
            log.exception(
                "rental_move_in: kunde inte uppdatera applikationsstatus",
            )

    return RentalMoveInOut(
        home=home_out,
        pentagon_deltas=deltas,
        deposit_charged=deposit,
        welcome_message=welcome,
    )


# === Lärar-endpoints (test/preview) ===


@teacher_router.get("/listings", response_model=CityListingsOut)
def teacher_get_listings(
    city: str = "stockholm",
    ym: str = "2026-01",
    n: int = 6,
    info: TokenInfo = Depends(require_token),
):
    """Lista listings för valfri stad (lärar-preview).

    Kräver bara valfri token — listings är inte känslig data och
    underlättar lärar-debug + UI-test.
    """
    if info.role not in ("teacher", "student"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Token saknar lärar/elev-roll.",
        )
    if city not in STAD_BY_KEY:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Okänd stad: {city}. Tillgängliga: "
            + ", ".join(sorted(STAD_BY_KEY.keys())),
        )
    listings = listings_for_city(city, ym, n=max(1, min(n, 12)))
    stad = STAD_BY_KEY[city]
    return CityListingsOut(
        city_key=city,
        city_display=stad.display,
        year_month=ym,
        market_price_per_kvm=market_price_for(city, ym),
        listings=[ListingOut(**asdict(l)) for l in listings],
    )


class CityPriceOut(BaseModel):
    city_key: str
    city_display: str
    year_month: str
    price_per_kvm: int


@teacher_router.get("/market-prices", response_model=list[CityPriceOut])
def teacher_market_prices(
    ym: str = "2026-01",
    info: TokenInfo = Depends(require_token),
):
    """Returnera snittpris per stad för en spelmånad."""
    if info.role not in ("teacher", "student"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Saknar roll.")
    return [
        CityPriceOut(
            city_key=stad.key,
            city_display=stad.display,
            year_month=ym,
            price_per_kvm=market_price_for(stad.key, ym),
        )
        for stad in STADSPOOL
    ]
