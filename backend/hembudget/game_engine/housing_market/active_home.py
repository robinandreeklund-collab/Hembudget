"""Sprint 5b · ActiveHome-tjänst — källa-av-sanning för "var bor eleven nu".

Spec: dev/game-motor/06-boendemarknaden.md (Sälj-flöde · Flytt-flöde)

Funktioner:
  ensure_active_home(profile, ym)
      Om scope-DB saknar aktiv ActiveHome → skapa en från Profile
      Generator-data. Idempotent.

  give_notice_on_rental(s, sid, ym)
      Sätt status="notice_given" + termination_date = entered_on +
      3 månader. Pentagon-effekt: -2 safety (osäkerhet).

  move_to_rental(s, sid, listing, ym)
      Säg upp gamla hyresrätten + skapa ny ActiveHome direkt med
      ny adress/storlek. Pentagon: + leisure om bättre, -economy om
      dyrare, -2 social (flytt = stressig).

  promote_listing_to_active_home(s, sid, listing, loan_id, ym)
      Vid lyckat köp: markera gamla ActiveHome som selling/terminated
      och skapa ny ActiveHome från listing.

  household_size_for(profile)
      1 + ev. partner + barn.

  min_kvm_for_household(family_status, n_persons)
      Konsumentverkets normer för rimlig storlek per hushållstyp.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ...db.models import ActiveHome
from ..pentagon import apply_pentagon_delta
from ..profile_generator.schema import GeneratedProfile
from .listings import HousingListing

log = logging.getLogger(__name__)


# Konsumentverkets norm + svensk hyresrätt-praxis
MIN_KVM_PER_PERSON = {
    "ensam": 28,
    "sambo": 22,
    "familj_med_barn": 20,
}
RENTAL_NOTICE_MONTHS = 3
SALE_HORIZON_MONTHS = 4


def household_size_for(profile: GeneratedProfile) -> int:
    n = 1
    if profile.family.partner_yrke_key:
        n += 1
    n += profile.family.children_count
    return n


def min_kvm_for_household(family_status: str, n_persons: int) -> int:
    per_p = MIN_KVM_PER_PERSON.get(family_status, 25)
    return max(22, per_p * n_persons)


def get_active_home(s: Session) -> Optional[ActiveHome]:
    return (
        s.query(ActiveHome)
        .filter(ActiveHome.status.in_(("active", "notice_given", "selling")))
        .order_by(ActiveHome.id.desc())
        .first()
    )


def _ym_first_day(ym: str) -> date:
    y, m = map(int, ym.split("-"))
    return date(y, m, 1)


def _add_months(d: date, n: int) -> date:
    total = d.year * 12 + (d.month - 1) + n
    new_y, new_m = divmod(total, 12)
    new_m += 1
    # Klamp till 28 så vi aldrig overflowar februari
    return date(new_y, new_m, min(d.day, 28))


def _termination_date_from(notice_date: date, months: int) -> date:
    """Beräkna uppsägningens sista dag enligt svensk hyreslag.

    Tillsvidareavtal: 3 månaders uppsägningstid räknat från
    NÄRMAST FÖLJANDE MÅNADSSKIFTE.

    Exempel: säg upp 7 jan 2026 → uppsägningen startar 1 feb 2026 →
    3 hela månader → sista dagen är 30 april 2026.

    Vi returnerar sista dagen i den 3:e månaden efter följande
    månadsskifte (dvs notice_start + 3 mån − 1 dag).
    """
    # Närmast följande månadsskifte
    if notice_date.month == 12:
        notice_start = date(notice_date.year + 1, 1, 1)
    else:
        notice_start = date(notice_date.year, notice_date.month + 1, 1)
    # Slutdatum = första dagen i (notice_start + months) − 1 dag
    end_y = notice_start.year + (notice_start.month - 1 + months) // 12
    end_m = (notice_start.month - 1 + months) % 12 + 1
    next_first = date(end_y, end_m, 1)
    from datetime import timedelta as _td_term
    return next_first - _td_term(days=1)


def ensure_active_home(
    s: Session,
    *,
    profile: GeneratedProfile,
    year_month: str,
) -> ActiveHome:
    """Säkerställ att eleven har en ActiveHome i scope-DB:n.

    Om en finns (active/notice_given/selling) → returnera den.
    Annars: skapa en från profile.housing.
    """
    existing = get_active_home(s)
    if existing is not None:
        return existing

    # entered_on i spel-tid · year_month-hint kan vara real-tid
    try:
        from ...business.game_clock import current_game_date as _cgd_ea
        entered = _cgd_ea()
    except Exception:
        entered = _ym_first_day(year_month)

    h = profile.housing
    home = ActiveHome(
        home_type=h.type,
        status="active",
        city_key=profile.city_key,
        address=None,
        size_kvm=h.size_kvm,
        rooms=max(1, h.size_kvm // 30),
        monthly_cost=Decimal(h.monthly_cost),
        monthly_avgift=(
            Decimal(h.monthly_avgift) if h.monthly_avgift else None
        ),
        purchase_price=(
            Decimal(h.purchase_price) if h.purchase_price else None
        ),
        loan_id=None,
        listing_id=None,
        entered_on=entered,
        household_size_when_chosen=household_size_for(profile),
    )
    s.add(home)
    s.flush()
    return home


def give_notice_on_rental(
    s: Session,
    *,
    student_id: int,
    year_month: str,
) -> ActiveHome:
    """Säg upp aktiv hyresrätt med 3 månaders uppsägning.

    Returnerar uppdaterad ActiveHome.

    OBS: year_month är en advisory hint — vi använder ALLTID
    current_game_date() som bas för termination_date eftersom
    frontend ibland skickar real-tid YYYY-MM istället för spel-tid.
    Tidigare fick eleven termination_date = real-tid + 3 mån vilket
    landade i framtiden av spel-tid.
    """
    home = get_active_home(s)
    if home is None:
        raise ValueError("Du har inget aktivt boende att säga upp.")
    if home.home_type != "hyresratt":
        raise ValueError(
            "Endast hyresrätter kan sägas upp så här. "
            "Bostadsrätt/villa måste säljas via /v2/boendemarknad/sell.",
        )
    if home.status == "notice_given":
        return home  # Idempotent

    # Använd spel-tid · year_month-hint ignoreras
    try:
        from ...business.game_clock import current_game_date as _cgd_gn
        notice_start = _cgd_gn()
    except Exception:
        notice_start = _ym_first_day(year_month)
    home.status = "notice_given"
    home.termination_date = _termination_date_from(
        notice_start, RENTAL_NOTICE_MONTHS,
    )
    s.flush()

    try:
        apply_pentagon_delta(
            student_id,
            axis="safety",
            requested_delta=-2,
            reason_kind="decision",
            reason_id=home.id,
            reason_table="active_homes",
            explanation="sa upp hyreskontraktet · 3 mån kvar",
            year_month=year_month,
        )
    except Exception:
        log.exception("Failed to log pentagon delta for notice")

    return home


def move_to_rental(
    s: Session,
    *,
    student_id: int,
    student_scope: str,
    new_listing: HousingListing,
    year_month: str,
) -> ActiveHome:
    """Flytta från en hyresrätt till en annan (mindre/billigare/större).

    Stänger gamla, skapar ny. Pentagon-effekter beror på storleksbyte
    + kostnadsbyte. Bara hyra→hyra för MVP — köp har egen flow.
    """
    if new_listing.type != "bostadsratt" and new_listing.type != "hyresratt":
        # Vi tillåter nu bara hyresrätt-flytt — köp via buy_listing
        if new_listing.type != "hyresratt":
            raise ValueError(
                "move_to_rental hanterar bara hyresrätter. "
                "Använd buy_listing för bostadsrätt/villa.",
            )
    old = get_active_home(s)
    if old is None:
        raise ValueError("Inget aktivt boende att flytta från.")
    if old.home_type != "hyresratt":
        raise ValueError(
            "move_to_rental: gamla boendet måste vara hyresrätt. "
            "Sälj BR/villa via /sell först.",
        )

    # 3 månaders uppsägningstid räknat från SPEL-tid — eleven är
    # skyldig att betala hyran på gamla bostaden under övergångs-
    # perioden även om man flyttat in i ny lägenhet. termination_date
    # = spel-tid + 90 dgr så HubV2-bannerns 'uppsägningstid till X'
    # och hyresavi-serien stämmer.
    try:
        from ...business.game_clock import current_game_date as _cgd_mvr
        notice_start = _cgd_mvr()
    except Exception:
        notice_start = _ym_first_day(year_month)
    old.status = "notice_given"
    old.termination_date = _termination_date_from(
        notice_start, RENTAL_NOTICE_MONTHS,
    )

    # Skapa ny rental ActiveHome från listing.
    # Listing är tekniskt "till salu" men vi behandlar hyresrätt-listings
    # som "ledig hyresrätt att hyra" i Sprint 5b. asking_price ignoreras
    # (hyresrätter har ingen köpeskilling), monthly_avgift = månadshyra.
    # entered_on i SPEL-tid · year_month-hint från frontend kan vara
    # real-tid och då blir 'tillträtt'-datum fel i UI.
    new_home = ActiveHome(
        home_type="hyresratt",
        status="active",
        city_key=new_listing.city_key,
        address=new_listing.address,
        size_kvm=new_listing.size_kvm,
        rooms=new_listing.rooms,
        monthly_cost=Decimal(new_listing.monthly_avgift),
        monthly_avgift=None,
        purchase_price=None,
        loan_id=None,
        listing_id=new_listing.listing_id,
        entered_on=notice_start,
        household_size_when_chosen=old.household_size_when_chosen,
    )
    s.add(new_home)
    s.flush()

    # Pentagon: +2 leisure om större, -2 economy om dyrare, +economy om
    # billigare (sweet spot om större OCH billigare)
    size_diff = new_listing.size_kvm - old.size_kvm
    cost_diff = int(new_listing.monthly_avgift) - int(old.monthly_cost)
    deltas: dict[str, int] = {"social": -2}  # flytt = lite stress
    if size_diff > 5:
        deltas["leisure"] = +2
    elif size_diff < -5:
        deltas["leisure"] = -1
    if cost_diff < -1000:
        deltas["economy"] = deltas.get("economy", 0) + 3
    elif cost_diff > 1000:
        deltas["economy"] = deltas.get("economy", 0) - 2

    for axis, delta in deltas.items():
        try:
            apply_pentagon_delta(
                student_id,
                axis=axis,
                requested_delta=delta,
                reason_kind="decision",
                reason_id=new_home.id,
                reason_table="active_homes",
                explanation=(
                    f"flyttade till {new_listing.address} "
                    f"({new_listing.size_kvm} kvm, "
                    f"{new_listing.monthly_avgift:,} kr/mån)"
                ).replace(",", " "),
                year_month=year_month,
            )
        except Exception:
            log.exception("Failed pentagon delta for rental move")

    return new_home


def promote_listing_to_active_home(
    s: Session,
    *,
    listing: HousingListing,
    loan_id: Optional[int],
    year_month: str,
    household_size: int = 1,
    monthly_cost: Optional[int] = None,
) -> ActiveHome:
    """Vid köp: gör listing till elevens nya ActiveHome.

    Markerar gamla ActiveHome:
      - hyresrätt → status="terminated" med termination_date = +3 mån
      - bostadsrätt/villa → status="selling" med estimated_sale_date

    Skapar ny ActiveHome från listing.
    """
    # SPEL-tid · year_month-hint kan vara real-tid
    try:
        from ...business.game_clock import current_game_date as _cgd_pr
        today_g = _cgd_pr()
    except Exception:
        today_g = _ym_first_day(year_month)

    old = get_active_home(s)
    if old is not None:
        if old.home_type == "hyresratt":
            old.status = "notice_given"
            old.termination_date = _termination_date_from(
                today_g, RENTAL_NOTICE_MONTHS,
            )
        else:
            old.status = "selling"
            old.estimated_sale_date = _add_months(
                today_g, SALE_HORIZON_MONTHS,
            )

    new_home = ActiveHome(
        home_type=listing.type,
        status="active",
        city_key=listing.city_key,
        address=listing.address,
        size_kvm=listing.size_kvm,
        rooms=listing.rooms,
        monthly_cost=Decimal(monthly_cost or listing.monthly_avgift),
        monthly_avgift=Decimal(listing.monthly_avgift),
        purchase_price=Decimal(listing.asking_price),
        loan_id=loan_id,
        listing_id=listing.listing_id,
        entered_on=today_g,
        household_size_when_chosen=household_size,
    )
    s.add(new_home)
    s.flush()
    return new_home
