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
    listings_for_city,
    market_price_for,
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


# === Elev-endpoints ===


@router.get("/listings", response_model=CityListingsOut)
def get_listings(
    ym: str = "2026-01",
    n: int = 6,
    info: TokenInfo = Depends(require_token),
):
    """Listings i elevens stad för given spelmånad."""
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

    city = STAD_BY_KEY.get(city_key) or STAD_BY_KEY["medelstad"]
    listings = listings_for_city(city_key, ym, n=max(1, min(n, 12)))
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
