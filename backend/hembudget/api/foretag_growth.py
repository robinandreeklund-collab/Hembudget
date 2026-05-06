"""Tillväxt-aktör · lokaler, utrustning, kapacitet, MCP, lån.

Spec: dev/feature-allabolag.md (Fas E+F)

Eleven driver aktivt tillväxten via:
- Större lokaler (max-anställda + max-jobs i tid)
- Bättre utrustning (speed-multiplier)
- MCP · inhyrd frilansare-vecka när snabb-kapacitet krävs
- Företagslån (med eller utan personlig borgen)

All UI-data hämtas via /v2/foretag/growth/*-endpoints.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .deps import TokenInfo, require_token
from ..business.models import (
    Company,
    CompanyEquipment,
    CompanyLoan,
    CompanyLocation,
    CompanyMcpRental,
    CompanyTransaction,
    Job,
)
from ..db.base import session_scope


log = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/foretag/growth", tags=["foretag-growth"])


def _require_student(info: TokenInfo) -> int:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(403, "Endast elever")
    return info.student_id


def _get_active_company(s) -> Optional[Company]:
    return s.query(Company).filter(Company.active.is_(True)).first()


# === Static catalog ===

LOCATION_CATALOG: dict[str, dict] = {
    "home": {
        "label": "Hemmakontor",
        "monthly_cost": 0,
        "max_employees": 0,
        "max_concurrent_jobs": 2,
        "purchase_price": None,
        "is_default": True,
    },
    "rented_1r": {
        "label": "Hyrd 1-rumslokal",
        "monthly_cost": 4000,
        "max_employees": 1,
        "max_concurrent_jobs": 4,
        "purchase_price": None,
    },
    "rented_2r": {
        "label": "Hyrd 2-rumslokal",
        "monthly_cost": 9000,
        "max_employees": 3,
        "max_concurrent_jobs": 8,
        "purchase_price": None,
    },
    "office_50": {
        "label": "Kontor 50 m²",
        "monthly_cost": 18000,
        "max_employees": 5,
        "max_concurrent_jobs": 14,
        "purchase_price": 480000,
    },
    "office_120": {
        "label": "Kontor 120 m²",
        "monthly_cost": 38000,
        "max_employees": 10,
        "max_concurrent_jobs": 28,
        "purchase_price": 1200000,
    },
}


EQUIPMENT_CATALOG: dict[str, dict] = {
    "standard": {
        "label": "Standard-utrustning",
        "purchase_price": 0,
        "speed_multiplier": 1.00,
        "breakdown_risk": 0.00,
        "is_default": True,
    },
    "second_hand": {
        "label": "Begagnad utrustning",
        "purchase_price": 12000,
        "speed_multiplier": 1.10,
        "breakdown_risk": 0.05,
    },
    "premium": {
        "label": "Premium-utrustning",
        "purchase_price": 45000,
        "speed_multiplier": 1.30,
        "breakdown_risk": 0.00,
    },
    "specialist": {
        "label": "Specialist-utrustning",
        "purchase_price": 120000,
        "speed_multiplier": 1.50,
        "breakdown_risk": 0.00,
    },
}


# Företagslån-villkor (förenklade, kan utvidgas via UC i fas G)
LOAN_TERMS: dict[str, dict] = {
    "startup_capital": {
        "label": "Startup-kapitallån (för aktiekapital)",
        "min": 25000, "max": 50000,
        "rate_no_guarantee": 0.12,
        "rate_with_guarantee": 0.07,
        "months": 60,
    },
    "growth": {
        "label": "Tillväxtlån (lokal/utrustning)",
        "min": 10000, "max": 500000,
        "rate_no_guarantee": 0.095,
        "rate_with_guarantee": 0.06,
        "months": 60,
    },
    "buffer": {
        "label": "Likviditetsbuffert",
        "min": 5000, "max": 100000,
        "rate_no_guarantee": 0.14,
        "rate_with_guarantee": 0.09,
        "months": 24,
    },
}


# === Helpers ===

def _annuity_payment(principal: int, annual_rate: float, months: int) -> int:
    """Annuitets-månadsbetalning · pmt formula."""
    r = annual_rate / 12.0
    if r <= 0:
        return principal // months
    return int(round(principal * r / (1 - (1 + r) ** -months)))


def _get_active_location(s, company_id: int) -> Optional[CompanyLocation]:
    return (
        s.query(CompanyLocation)
        .filter(
            CompanyLocation.company_id == company_id,
            CompanyLocation.is_active.is_(True),
        )
        .first()
    )


def _get_active_equipment(s, company_id: int) -> Optional[CompanyEquipment]:
    return (
        s.query(CompanyEquipment)
        .filter(
            CompanyEquipment.company_id == company_id,
            CompanyEquipment.is_active.is_(True),
        )
        .first()
    )


def _ensure_default_location_and_equipment(s, company: Company) -> None:
    """Säkerställ att bolaget har default 'home' + 'standard' om inget."""
    if _get_active_location(s, company.id) is None:
        loc_def = LOCATION_CATALOG["home"]
        s.add(CompanyLocation(
            company_id=company.id,
            location_kind="home",
            monthly_cost=loc_def["monthly_cost"],
            max_employees=loc_def["max_employees"],
            max_concurrent_jobs=loc_def["max_concurrent_jobs"],
            is_owned=False,
            is_active=True,
        ))
    if _get_active_equipment(s, company.id) is None:
        eq_def = EQUIPMENT_CATALOG["standard"]
        s.add(CompanyEquipment(
            company_id=company.id,
            equipment_kind="standard",
            purchase_price=0,
            speed_multiplier=Decimal(str(eq_def["speed_multiplier"])),
            breakdown_risk=Decimal(str(eq_def["breakdown_risk"])),
            is_active=True,
        ))
    s.flush()


def compute_capacity(s, company: Company) -> dict:
    """Räkna ut nuvarande kapacitet vs användning.

    used = antal jobs status='in_progress' + aktiva MCP-bonus
    max = lokal.max_concurrent_jobs × utrustning.speed_multiplier
    """
    _ensure_default_location_and_equipment(s, company)
    loc = _get_active_location(s, company.id)
    eq = _get_active_equipment(s, company.id)
    today = date.today()

    in_progress = (
        s.query(Job)
        .filter(
            Job.company_id == company.id,
            Job.status == "in_progress",
        )
        .count()
    )

    active_mcp = (
        s.query(CompanyMcpRental)
        .filter(
            CompanyMcpRental.company_id == company.id,
            CompanyMcpRental.status == "active",
            CompanyMcpRental.ends_on >= today,
        )
        .count()
    )

    base_max = loc.max_concurrent_jobs if loc else 2
    speed = float(eq.speed_multiplier) if eq else 1.0
    capacity_max = int(base_max * speed) + active_mcp

    return {
        "used": in_progress,
        "max": capacity_max,
        "base_max": base_max,
        "speed_multiplier": speed,
        "mcp_bonus": active_mcp,
        "location_kind": loc.location_kind if loc else "home",
        "location_label": (
            LOCATION_CATALOG.get(loc.location_kind, {}).get("label", "—")
            if loc else "—"
        ),
        "equipment_kind": eq.equipment_kind if eq else "standard",
        "equipment_label": (
            EQUIPMENT_CATALOG.get(eq.equipment_kind, {}).get("label", "—")
            if eq else "—"
        ),
        "is_overloaded": in_progress > capacity_max,
        "utilization_pct": int(
            (in_progress / capacity_max * 100) if capacity_max > 0 else 0
        ),
    }


# === Schemas ===

class GrowthOverviewOut(BaseModel):
    capacity: dict
    location: dict
    equipment: dict
    monthly_overhead: int
    kassa: int
    n_employees: int


class LocationCatalogOut(BaseModel):
    items: list[dict]
    can_afford_kassa: int  # företagets kassa


class EquipmentCatalogOut(BaseModel):
    items: list[dict]
    can_afford_kassa: int


class UpgradeLocationIn(BaseModel):
    location_kind: str
    is_purchase: bool = False  # köpa istället för hyra


class BuyEquipmentIn(BaseModel):
    equipment_kind: str


class RentMcpIn(BaseModel):
    weeks: int = Field(ge=1, le=4)


class LoanApplyIn(BaseModel):
    purpose: str = Field(..., pattern="^(startup_capital|growth|buffer)$")
    principal: int = Field(ge=1000, le=2000000)
    is_personal_guarantee: bool = False


class LoanOut(BaseModel):
    id: int
    purpose: str
    lender: str
    principal: int
    outstanding: int
    interest_rate: float
    monthly_payment: int
    months_total: int
    months_left: int
    is_personal_guarantee: bool
    status: str
    started_on: str


# === Helpers · Kassa ===

def _kassa(s, company: Company) -> int:
    """Approximation: alla company-tx + aktiekapital."""
    txs = (
        s.query(CompanyTransaction)
        .filter(CompanyTransaction.company_id == company.id)
        .all()
    )
    bal = 0
    for t in txs:
        amt = float(t.amount_excl_vat or 0)
        if t.kind == "income":
            bal += amt
        else:
            bal -= amt
    if company.share_capital:
        bal += float(company.share_capital)
    return int(bal)


# === Endpoints ===

@router.get("/overview", response_model=GrowthOverviewOut)
def growth_overview(info: TokenInfo = Depends(require_token)):
    """Översikt: kapacitet, lokal, utrustning, månadskostnad, kassa."""
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Inget aktivt bolag")
        _ensure_default_location_and_equipment(s, c)
        cap = compute_capacity(s, c)
        loc = _get_active_location(s, c.id)
        eq = _get_active_equipment(s, c.id)
        # Anställda räknas via master-DB
        from ..school.engines import master_session
        from ..school.models import (
            ClassCompanyShare, CompanyEmployment,
        )
        n_emp = 0
        try:
            with master_session() as ms:
                share = (
                    ms.query(ClassCompanyShare)
                    .filter(
                        ClassCompanyShare.company_id_in_scope == c.id,
                    )
                    .first()
                )
                if share:
                    n_emp = (
                        ms.query(CompanyEmployment)
                        .filter(
                            CompanyEmployment.company_share_id == share.id,
                            CompanyEmployment.status == "active",
                        )
                        .count()
                    )
        except Exception:
            pass

        # Månadsoverhead = lokal-hyra + lån-månadsbetalningar
        loan_pmts = sum(
            l.monthly_payment for l in (
                s.query(CompanyLoan)
                .filter(
                    CompanyLoan.company_id == c.id,
                    CompanyLoan.status == "active",
                )
                .all()
            )
        )
        overhead = (loc.monthly_cost if loc else 0) + loan_pmts

        return GrowthOverviewOut(
            capacity=cap,
            location={
                "kind": loc.location_kind,
                "label": LOCATION_CATALOG.get(loc.location_kind, {}).get("label", "—"),
                "monthly_cost": loc.monthly_cost,
                "max_employees": loc.max_employees,
                "max_concurrent_jobs": loc.max_concurrent_jobs,
                "is_owned": loc.is_owned,
            },
            equipment={
                "kind": eq.equipment_kind,
                "label": EQUIPMENT_CATALOG.get(eq.equipment_kind, {}).get("label", "—"),
                "speed_multiplier": float(eq.speed_multiplier),
                "breakdown_risk": float(eq.breakdown_risk),
            },
            monthly_overhead=overhead,
            kassa=_kassa(s, c),
            n_employees=n_emp,
        )


@router.get("/locations", response_model=LocationCatalogOut)
def list_locations(info: TokenInfo = Depends(require_token)):
    """Lokal-katalog för upgrade-vyn."""
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Inget aktivt bolag")
        kassa = _kassa(s, c)
        items = []
        current = _get_active_location(s, c.id)
        for kind, meta in LOCATION_CATALOG.items():
            items.append({
                "kind": kind,
                "label": meta["label"],
                "monthly_cost": meta["monthly_cost"],
                "max_employees": meta["max_employees"],
                "max_concurrent_jobs": meta["max_concurrent_jobs"],
                "purchase_price": meta.get("purchase_price"),
                "is_current": (current and current.location_kind == kind),
            })
        return LocationCatalogOut(items=items, can_afford_kassa=kassa)


@router.post("/locations/upgrade")
def upgrade_location(
    body: UpgradeLocationIn,
    info: TokenInfo = Depends(require_token),
):
    """Byt lokal · gamla blir is_active=False, ny blir aktiv.
    Köp drar purchase_price från kassan; hyra debiteras månadsvis."""
    _require_student(info)
    if body.location_kind not in LOCATION_CATALOG:
        raise HTTPException(400, "Okänd lokaltyp")
    meta = LOCATION_CATALOG[body.location_kind]
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Inget aktivt bolag")
        kassa = _kassa(s, c)
        cost = 0
        if body.is_purchase and meta.get("purchase_price"):
            cost = meta["purchase_price"]
            if kassa < cost:
                raise HTTPException(
                    400,
                    f"Otillräcklig kassa · {cost - kassa} kr saknas",
                )
            # Bokför som expense
            s.add(CompanyTransaction(
                company_id=c.id,
                occurred_on=date.today(),
                kind="expense",
                category="Lokal · köp",
                description=f"Köpte {meta['label']}",
                amount_excl_vat=Decimal(str(cost)),
                vat_rate=Decimal("0.0"),
                vat_amount=Decimal(0),
            ))
        # Inaktivera gammal
        existing = _get_active_location(s, c.id)
        if existing is not None:
            existing.is_active = False
            existing.ended_on = date.today()
        # Skapa ny
        s.add(CompanyLocation(
            company_id=c.id,
            location_kind=body.location_kind,
            monthly_cost=meta["monthly_cost"],
            max_employees=meta["max_employees"],
            max_concurrent_jobs=meta["max_concurrent_jobs"],
            is_owned=body.is_purchase,
            purchase_price=cost if body.is_purchase else None,
            is_active=True,
        ))
        s.commit()
        try:
            from ..school.activity import log_activity
            log_activity(
                kind="biz.location_upgraded",
                summary=(
                    f"Bytte lokal till {meta['label']}"
                    + (f" · köpte för {cost} kr" if body.is_purchase else "")
                ),
                payload={"location_kind": body.location_kind, "cost": cost},
            )
        except Exception:
            pass
    return {"ok": True}


@router.get("/equipment", response_model=EquipmentCatalogOut)
def list_equipment(info: TokenInfo = Depends(require_token)):
    """Utrustning-katalog."""
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Inget aktivt bolag")
        kassa = _kassa(s, c)
        items = []
        current = _get_active_equipment(s, c.id)
        for kind, meta in EQUIPMENT_CATALOG.items():
            items.append({
                "kind": kind,
                "label": meta["label"],
                "purchase_price": meta["purchase_price"],
                "speed_multiplier": meta["speed_multiplier"],
                "breakdown_risk": meta["breakdown_risk"],
                "is_current": (current and current.equipment_kind == kind),
            })
        return EquipmentCatalogOut(items=items, can_afford_kassa=kassa)


@router.post("/equipment/buy")
def buy_equipment(
    body: BuyEquipmentIn,
    info: TokenInfo = Depends(require_token),
):
    """Köp ny utrustning · ersätter gamla."""
    _require_student(info)
    if body.equipment_kind not in EQUIPMENT_CATALOG:
        raise HTTPException(400, "Okänd utrustning")
    meta = EQUIPMENT_CATALOG[body.equipment_kind]
    cost = meta["purchase_price"]
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Inget aktivt bolag")
        kassa = _kassa(s, c)
        if kassa < cost:
            raise HTTPException(
                400, f"Otillräcklig kassa · {cost - kassa} kr saknas",
            )
        if cost > 0:
            s.add(CompanyTransaction(
                company_id=c.id,
                occurred_on=date.today(),
                kind="expense",
                category="Utrustning",
                description=f"Köpte {meta['label']}",
                amount_excl_vat=Decimal(str(cost)),
                vat_rate=Decimal("0.25"),
                vat_amount=Decimal(str(round(cost * 0.25))),
            ))
        existing = _get_active_equipment(s, c.id)
        if existing is not None:
            existing.is_active = False
        s.add(CompanyEquipment(
            company_id=c.id,
            equipment_kind=body.equipment_kind,
            purchase_price=cost,
            speed_multiplier=Decimal(str(meta["speed_multiplier"])),
            breakdown_risk=Decimal(str(meta["breakdown_risk"])),
            is_active=True,
        ))
        s.commit()
    return {"ok": True}


@router.post("/mcp/rent")
def rent_mcp(
    body: RentMcpIn,
    info: TokenInfo = Depends(require_token),
):
    """Hyr in frilansare · kostar 48 000 kr/v · ger +1 kapacitet."""
    _require_student(info)
    cost_per_week = 48000
    total = cost_per_week * body.weeks
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Inget aktivt bolag")
        if _kassa(s, c) < total:
            raise HTTPException(400, "Otillräcklig kassa för MCP")
        today = date.today()
        ends = today + timedelta(weeks=body.weeks)
        s.add(CompanyMcpRental(
            company_id=c.id,
            weeks=body.weeks,
            cost_total=total,
            started_on=today,
            ends_on=ends,
            status="active",
        ))
        s.add(CompanyTransaction(
            company_id=c.id,
            occurred_on=today,
            kind="expense",
            category="Inhyrd konsult",
            description=f"MCP · frilans-konsult {body.weeks} v",
            amount_excl_vat=Decimal(str(total)),
            vat_rate=Decimal("0.25"),
            vat_amount=Decimal(str(round(total * 0.25))),
        ))
        s.commit()
    return {"ok": True, "cost": total, "ends_on": ends.isoformat()}


# === Loans ===

@router.get("/loans", response_model=list[LoanOut])
def list_loans(info: TokenInfo = Depends(require_token)):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            return []
        rows = (
            s.query(CompanyLoan)
            .filter(CompanyLoan.company_id == c.id)
            .order_by(CompanyLoan.started_on.desc())
            .all()
        )
        return [
            LoanOut(
                id=r.id,
                purpose=r.purpose,
                lender=r.lender,
                principal=r.principal,
                outstanding=r.outstanding,
                interest_rate=float(r.interest_rate),
                monthly_payment=r.monthly_payment,
                months_total=r.months_total,
                months_left=r.months_left,
                is_personal_guarantee=r.is_personal_guarantee,
                status=r.status,
                started_on=r.started_on.isoformat(),
            )
            for r in rows
        ]


@router.post("/loans/apply", response_model=LoanOut)
def apply_loan(
    body: LoanApplyIn,
    info: TokenInfo = Depends(require_token),
):
    """Ansök om företagslån.

    AI-bank godkänner baserat på principal vs limit + kassa-buffer +
    ev. personlig borgen. För Fas E är prövningen deterministisk.
    """
    _require_student(info)
    if body.purpose not in LOAN_TERMS:
        raise HTTPException(400, "Okänt lånesyfte")
    terms = LOAN_TERMS[body.purpose]
    if not (terms["min"] <= body.principal <= terms["max"]):
        raise HTTPException(
            400,
            f"Belopp utanför {terms['label']}: "
            f"{terms['min']}–{terms['max']} kr",
        )

    rate = (
        terms["rate_with_guarantee"] if body.is_personal_guarantee
        else terms["rate_no_guarantee"]
    )
    months = terms["months"]
    monthly = _annuity_payment(body.principal, rate, months)

    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Inget aktivt bolag")
        loan = CompanyLoan(
            company_id=c.id,
            purpose=body.purpose,
            lender="Företagsbanken AB",
            principal=body.principal,
            outstanding=body.principal,
            interest_rate=Decimal(str(rate)),
            monthly_payment=monthly,
            months_total=months,
            months_left=months,
            is_personal_guarantee=body.is_personal_guarantee,
            status="active",
            started_on=date.today(),
        )
        s.add(loan)
        # Pengar in på kassan som income (kategori = "Lån")
        s.add(CompanyTransaction(
            company_id=c.id,
            occurred_on=date.today(),
            kind="income",
            category="Lån",
            description=f"{terms['label']} · {body.principal} kr",
            amount_excl_vat=Decimal(str(body.principal)),
            vat_rate=Decimal("0.0"),
            vat_amount=Decimal(0),
        ))
        s.flush()
        s.refresh(loan)

        try:
            from ..school.activity import log_activity
            log_activity(
                kind="biz.loan_taken",
                summary=(
                    f"Tog {terms['label']} · {body.principal} kr · "
                    f"{int(rate * 100)}% ränta · {monthly} kr/mån"
                ),
                payload={
                    "purpose": body.purpose,
                    "principal": body.principal,
                    "rate": rate,
                    "monthly": monthly,
                    "personal_guarantee": body.is_personal_guarantee,
                },
            )
        except Exception:
            pass

        return LoanOut(
            id=loan.id,
            purpose=loan.purpose,
            lender=loan.lender,
            principal=loan.principal,
            outstanding=loan.outstanding,
            interest_rate=float(loan.interest_rate),
            monthly_payment=loan.monthly_payment,
            months_total=loan.months_total,
            months_left=loan.months_left,
            is_personal_guarantee=loan.is_personal_guarantee,
            status=loan.status,
            started_on=loan.started_on.isoformat(),
        )


@router.post("/loans/{loan_id}/pay")
def pay_loan(
    loan_id: int,
    info: TokenInfo = Depends(require_token),
):
    """Manuell betalning av en månads-rate. Tick-engine kommer också
    auto-debitera senare (Fas G)."""
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Inget aktivt bolag")
        loan = s.get(CompanyLoan, loan_id)
        if loan is None or loan.company_id != c.id:
            raise HTTPException(404, "Lån saknas")
        if loan.status != "active":
            raise HTTPException(409, "Lånet är inte aktivt")

        # Räkna ränta + amortering
        monthly_rate = float(loan.interest_rate) / 12.0
        interest_amt = int(round(loan.outstanding * monthly_rate))
        amort = max(0, loan.monthly_payment - interest_amt)
        if amort > loan.outstanding:
            amort = loan.outstanding
        total_payment = interest_amt + amort

        if _kassa(s, c) < total_payment:
            raise HTTPException(400, "Otillräcklig kassa för betalning")

        loan.outstanding -= amort
        loan.months_left = max(0, loan.months_left - 1)
        loan.last_payment_on = date.today()
        if loan.outstanding <= 0 or loan.months_left == 0:
            loan.status = "repaid"

        s.add(CompanyTransaction(
            company_id=c.id,
            occurred_on=date.today(),
            kind="expense",
            category="Lån · ränta",
            description=f"Ränta {loan.lender}",
            amount_excl_vat=Decimal(str(interest_amt)),
            vat_rate=Decimal("0.0"),
            vat_amount=Decimal(0),
        ))
        if amort > 0:
            s.add(CompanyTransaction(
                company_id=c.id,
                occurred_on=date.today(),
                kind="expense",
                category="Lån · amortering",
                description=f"Amortering {loan.lender}",
                amount_excl_vat=Decimal(str(amort)),
                vat_rate=Decimal("0.0"),
                vat_amount=Decimal(0),
            ))
        s.commit()
    return {"ok": True, "interest": interest_amt, "amortization": amort}
