"""B3+B4 · Köp- och sälj-flöden.

Spec: dev/game-motor/06-boendemarknaden.md (Köp-flödet, Sälj-flödet)

Köp-flöde (`buy_listing`):
  1. Kontant-insats-check (max LTV 85 % för bostadsrätt, 75 % för villa
     förstgångs-köpare 2026)
  2. Skapa Loan i scope-DB (loan_kind="mortgage", property_value=asking)
  3. Markera den gamla bostaden för uppsägning (om hyresrätt) eller
     starta en sälj-transaktion (om bostadsrätt)
  4. Skicka MailItem("info", "Bolån beviljat") till postlådan
  5. Returnera PurchaseResult

Sälj-flöde (`sell_current_home`):
  1. Värdera elevens nuvarande bostad
  2. Skapa SellTransaction-state (lagras som MailItem-info eller
     scope-DB-tabell — för MVP använder vi MailItem som proxy)
  3. Returnera SellResult med estimerat värde + tidshorisont

Pentagon-effekter sätts via WellbeingEvent (apply_pentagon_delta).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ...db.models import Loan, MailItem
from ..pentagon import apply_pentagon_delta
from ..pools.stadspool import STAD_BY_KEY
from .active_home import promote_listing_to_active_home
from .listings import HousingListing


LTV_BR = 0.85   # Bostadsrätt
LTV_VILLA_FIRST_TIME = 0.75   # Villa förstagångs-köpare 2026
INTEREST_RATE_DEFAULT = 0.039  # Bolåne-snitt 2026
AMORT_RATE_DEFAULT = 0.02      # 2 % per år


@dataclass
class PurchaseResult:
    listing_id: str
    accepted: bool
    loan_id: Optional[int]
    monthly_cost: int
    cash_required: int
    pentagon_delta: dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class SellResult:
    estimated_value: int
    estimated_proceeds_after_costs: int
    sell_horizon_months: int
    capital_gain_estimate: int
    pentagon_delta: dict[str, int] = field(default_factory=dict)


def _ltv_for(housing_type: str) -> float:
    if housing_type == "villa":
        return LTV_VILLA_FIRST_TIME
    return LTV_BR


def _monthly_loan_cost(principal: int) -> tuple[int, int]:
    interest_m = int(principal * INTEREST_RATE_DEFAULT / 12)
    amort_m = int(principal * AMORT_RATE_DEFAULT / 12)
    return interest_m, amort_m


def _stable_loan_number(student_scope: str, listing_id: str) -> str:
    raw = f"{student_scope}|{listing_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12].upper()


def buy_listing(
    s: Session,
    *,
    student_id: int,
    student_scope: str,
    listing: HousingListing,
    available_cash: int,
    year_month: str,
) -> PurchaseResult:
    """Försök köpa en listing. Validerar kontantinsats, skapar Loan +
    bekräftelse-MailItem.

    Pentagon-effekt: +5 safety (eget boende), -10 economy (kontantinsats).
    """
    ltv = _ltv_for(listing.type)
    loan_amount = int(listing.asking_price * ltv)
    cash_required = listing.asking_price - loan_amount

    if available_cash < cash_required:
        return PurchaseResult(
            listing_id=listing.listing_id,
            accepted=False,
            loan_id=None,
            monthly_cost=0,
            cash_required=cash_required,
            error=(
                f"Kontantinsats {cash_required:,} kr krävs · du har "
                f"{available_cash:,} kr tillgängligt".replace(",", " ")
            ),
        )

    interest_m, amort_m = _monthly_loan_cost(loan_amount)
    monthly_cost = interest_m + amort_m + listing.monthly_avgift

    # Skapa Loan
    y, m = map(int, year_month.split("-"))
    loan = Loan(
        name=f"Bolån {listing.address}",
        lender="Spelbanken Bolån",
        loan_number=_stable_loan_number(student_scope, listing.listing_id),
        principal_amount=Decimal(loan_amount),
        start_date=date(y, m, 1),
        interest_rate=INTEREST_RATE_DEFAULT,
        binding_type="rörlig",
        amortization_monthly=Decimal(amort_m),
        property_value=Decimal(listing.asking_price),
        notes=(
            f"Köp av {listing.type} {listing.size_kvm} kvm i "
            f"{listing.city_display}. Listing {listing.listing_id}."
        ),
        active=True,
    )
    s.add(loan)
    s.flush()

    # Bekräftelse i postlådan
    confirm = MailItem(
        sender="Spelbanken Bolån",
        sender_short="BANK",
        sender_kind="bank",
        sender_meta=f"bolåne-bekräftelse · {listing.address}",
        mail_type="info",
        subject=f"Bolån beviljat · {listing.size_kvm} kvm i {listing.city_display}",
        body_meta=(
            f"Kontantinsats {cash_required:,} kr · lån "
            f"{loan_amount:,} kr".replace(",", " ")
        ),
        body=(
            f"Grattis till nya bostaden!\n\n"
            f"Adress: {listing.address}\n"
            f"Storlek: {listing.size_kvm} kvm, {listing.rooms} rum\n"
            f"Köpeskilling: {listing.asking_price:,} kr\n"
            f"Lån: {loan_amount:,} kr (LTV {int(ltv*100)} %)\n"
            f"Kontantinsats: {cash_required:,} kr\n"
            f"Månadskostnad: {monthly_cost:,} kr "
            f"(ränta {interest_m} + amort {amort_m} + avgift {listing.monthly_avgift})\n"
        ).replace(",", " "),
        amount=None,
        status="unhandled",
    )
    s.add(confirm)
    s.flush()

    # Promote listing till ny ActiveHome (Sprint 5b · konsoliderar
    # gamla boendet till "selling" eller "terminated").
    try:
        promote_listing_to_active_home(
            s,
            listing=listing,
            loan_id=loan.id,
            year_month=year_month,
            monthly_cost=monthly_cost,
        )
    except Exception:
        # ActiveHome får inte bryta köpet (logget i caller)
        pass

    # Pentagon-effekter (B3 spec)
    pentagon_delta = {"safety": +5, "economy": -10}
    if listing.type == "villa":
        # Större drift, ung köpare → även -3 leisure
        pentagon_delta["leisure"] = -3
    for axis, requested in pentagon_delta.items():
        try:
            apply_pentagon_delta(
                student_id,
                axis=axis,
                requested_delta=requested,
                reason_kind="decision",
                reason_id=loan.id,
                reason_table="loans",
                explanation=f"köpte {listing.type} i {listing.city_display}",
                year_month=year_month,
            )
        except Exception:
            # Pentagon-loggning får inte bryta köpet
            pass

    return PurchaseResult(
        listing_id=listing.listing_id,
        accepted=True,
        loan_id=loan.id,
        monthly_cost=monthly_cost,
        cash_required=cash_required,
        pentagon_delta=pentagon_delta,
    )


def sell_current_home(
    s: Session,
    *,
    student_id: int,
    student_scope: str,
    home_value: int,
    purchase_price: int,
    loan_balance: int,
    year_month: str,
    sell_horizon_months: int = 4,
) -> SellResult:
    """Lägg ut elevens nuvarande bostad till försäljning.

    MVP: skapar bekräftelse-MailItem + applicerar pentagon-delta direkt
    (i full implementation skulle detta ta 2-6 sim-månader).
    """
    # Mäklarkostnad ~3% + reavinstskatt 22% av vinst
    broker_cost = int(home_value * 0.03)
    capital_gain = max(0, home_value - purchase_price)
    capital_gain_tax = int(capital_gain * 0.22)
    proceeds = home_value - broker_cost - capital_gain_tax - loan_balance

    confirm = MailItem(
        sender="Mäklarbyrån Norra",
        sender_short="MKL",
        sender_kind="other",
        sender_meta=f"försäljnings-uppdrag · {year_month}",
        mail_type="info",
        subject="Bostaden ute till försäljning",
        body_meta=f"Värdering {home_value:,} kr · estimerade pengar {proceeds:,} kr".replace(",", " "),
        body=(
            f"Värdering: {home_value:,} kr\n"
            f"Köppris (då): {purchase_price:,} kr\n"
            f"Reavinst: {capital_gain:,} kr\n"
            f"Mäklarkostnad: {broker_cost:,} kr\n"
            f"Reavinstskatt: {capital_gain_tax:,} kr\n"
            f"Lån att lösa: {loan_balance:,} kr\n"
            f"Estimerade pengar efter försäljning: {proceeds:,} kr\n"
            f"Förväntad försäljningstid: ca {sell_horizon_months} mån.\n"
        ).replace(",", " "),
        amount=None,
        status="unhandled",
    )
    s.add(confirm)
    s.flush()

    # Pentagon
    if capital_gain > 0:
        pentagon_delta = {"economy": +8}
    else:
        pentagon_delta = {"economy": -8, "safety": -2}
    for axis, requested in pentagon_delta.items():
        try:
            apply_pentagon_delta(
                student_id,
                axis=axis,
                requested_delta=requested,
                reason_kind="decision",
                reason_table="mail_items",
                explanation=(
                    "sålde bostad med vinst" if capital_gain > 0
                    else "sålde bostad med förlust"
                ),
                year_month=year_month,
            )
        except Exception:
            pass

    return SellResult(
        estimated_value=home_value,
        estimated_proceeds_after_costs=proceeds,
        sell_horizon_months=sell_horizon_months,
        capital_gain_estimate=capital_gain,
        pentagon_delta=pentagon_delta,
    )
