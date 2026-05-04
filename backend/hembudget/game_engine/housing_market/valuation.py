"""B5 · Valuation · värdera elevens nuvarande boende.

Spec: dev/game-motor/06-boendemarknaden.md (Köp-flödet steg 9)

Använder elevens senaste aktiva Loan (där `property_value` sattes vid
köp) + market_price_for(city, current_ym) för att räkna aktuell
värdering. Skillnad köppris vs nu = orealiserad reavinst.

För hyresgäster: ingen valuation, bara hyran. Vi returnerar 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ...db.models import Loan
from ..pools.stadspool import STAD_BY_KEY
from ..profile_generator.schema import GeneratedProfile
from .market_data import market_price_for


@dataclass
class HomeValuation:
    has_owned_home: bool
    purchase_price: Optional[int]
    current_value: Optional[int]
    unrealized_gain: Optional[int]
    loan_balance: Optional[int]
    equity: Optional[int]               # current_value - loan_balance
    city_key: Optional[str]
    note: Optional[str] = None


def _current_loan_balance(loan: Loan) -> int:
    """Förenklad: principal_amount minus all amortering hittills.

    Vi har inte en separat amortering-logg ännu (kommer i Sprint 6),
    så MVP returnerar principal_amount som proxy.
    """
    base = loan.current_balance_at_creation or loan.principal_amount or Decimal(0)
    return int(base)


def _newest_active_mortgage(s: Session) -> Optional[Loan]:
    """Senast skapade aktiva bolån (loan_kind="mortgage" eller där
    `property_value` är satt — för bakåtkompatibilitet)."""
    rows = (
        s.query(Loan)
        .filter(Loan.active.is_(True))
        .filter(Loan.property_value.isnot(None))
        .order_by(Loan.created_at.desc())
        .all()
    )
    return rows[0] if rows else None


def valuate_current_home(
    s: Session,
    *,
    profile: GeneratedProfile,
    year_month: str,
) -> HomeValuation:
    """Värdera elevens nuvarande bostad.

    Tre fall:
      1. Hyresgäst (profile.housing.type=hyresratt + ingen Loan) → ingen valuation
      2. Profil hade BR/villa redan vid skapelse (Profile Generator) →
         räknar baserat på profile.housing.purchase_price + market drift
      3. Eleven har köpt via housing_market.buy_listing → använder Loan
    """
    # Fall 3: eleven har Loan
    loan = _newest_active_mortgage(s)
    if loan is not None and loan.property_value:
        purchase = int(loan.property_value)
        balance = _current_loan_balance(loan)
        current_value = market_price_for(profile.city_key, year_month)
        # property_value sattes som total köpeskilling, inte per kvm —
        # vi räknar % förändring baserat på baseline_ym → year_month
        # och multiplicerar köppris med samma faktor.
        baseline = market_price_for(profile.city_key, "2026-01") or 1
        ratio = current_value / baseline if baseline else 1.0
        current_value_total = int(purchase * ratio)
        return HomeValuation(
            has_owned_home=True,
            purchase_price=purchase,
            current_value=current_value_total,
            unrealized_gain=current_value_total - purchase,
            loan_balance=balance,
            equity=current_value_total - balance,
            city_key=profile.city_key,
        )

    # Fall 2: Profil-genererat boende
    h = profile.housing
    if h.type in ("bostadsratt", "villa", "radhus") and h.purchase_price:
        baseline = market_price_for(profile.city_key, "2026-01") or 1
        current_per_kvm = market_price_for(profile.city_key, year_month)
        ratio = current_per_kvm / baseline if baseline else 1.0
        current_value = int(h.purchase_price * ratio)
        loan_balance = h.loan_amount or 0
        return HomeValuation(
            has_owned_home=True,
            purchase_price=h.purchase_price,
            current_value=current_value,
            unrealized_gain=current_value - h.purchase_price,
            loan_balance=loan_balance,
            equity=current_value - loan_balance,
            city_key=profile.city_key,
            note="Värdering baserad på initial profil-data + marknadsdrift.",
        )

    # Fall 1: Hyresgäst
    return HomeValuation(
        has_owned_home=False,
        purchase_price=None,
        current_value=None,
        unrealized_gain=None,
        loan_balance=None,
        equity=None,
        city_key=profile.city_key,
        note="Du hyr — ingen bostadsvärdering.",
    )
