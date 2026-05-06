"""Företagsläget · /v2/foretag/* endpoints.

Bug #7-utbyggnad · komplett implementation.

Endpoints:
- GET    /v2/foretag                · översikt (mitt bolag eller null)
- POST   /v2/foretag                · skapa bolag
- PATCH  /v2/foretag/{id}           · uppdatera namn/sni/momsregistrering
- DELETE /v2/foretag/{id}           · stäng bolag
- POST   /v2/foretag/transactions   · lägg till intäkt/utgift
- GET    /v2/foretag/transactions   · lista
- DELETE /v2/foretag/transactions/{id}
- POST   /v2/foretag/customers      · skapa kund
- GET    /v2/foretag/customers
- POST   /v2/foretag/invoices       · skapa faktura
- GET    /v2/foretag/invoices
- POST   /v2/foretag/invoices/{id}/mark-paid
- POST   /v2/foretag/owner-salary   · ta ut lön (AB)
- GET    /v2/foretag/owner-salaries · lista
- POST   /v2/foretag/vat/file       · momsdeklarera period
- GET    /v2/foretag/vat/periods    · alla VAT-perioder
- GET    /v2/foretag/corporate-tax/{year} · bolagsskatt-prognos
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..business.models import (
    Company,
    CompanyCustomer,
    CompanyInvoice,
    CompanyOwnerSalary,
    CompanyTransaction,
    CompanyVatPeriod,
)
from ..business.service import (
    book_owner_salary,
    book_owner_withdrawal,
    compute_business_pentagon,
    compute_owner_salary,
    compute_period_vat,
    estimate_corporate_tax_for_year,
    file_vat_period,
)
from ..db.base import session_scope
from .deps import TokenInfo, require_token


router = APIRouter(prefix="/v2/foretag", tags=["foretag"])
teacher_router = APIRouter(
    prefix="/v2/teacher/foretag", tags=["teacher-foretag"],
)


# === Schemas ===


class CompanyOut(BaseModel):
    id: int
    name: str
    org_number: Optional[str]
    form: str
    started_on: str
    share_capital: Optional[int]
    vat_registered: bool
    vat_period: str
    sni_code: Optional[str]
    industry_label: Optional[str]
    industry_key: Optional[str]
    city_key: Optional[str]
    city_display: Optional[str]
    active: bool


class CompanyIn(BaseModel):
    """Skapa-bolag-payload.

    `industry_key` är obligatoriskt (en av de 10 fasta branscherna).
    `city_key` skickas INTE från klienten — det ärvs alltid från
    karaktärens StudentProfile.city. Om eleven försöker skicka
    custom city → ignoreras."""
    name: str = Field(min_length=2, max_length=160)
    form: str = Field(default="enskild_firma")
    org_number: Optional[str] = None
    industry_key: str = Field(
        min_length=2, max_length=40,
        description="En av de 10 fasta branscherna i industries.py",
    )
    vat_registered: bool = True       # Default på · pedagogiskt viktigt
    vat_period: str = "kvartal"
    share_capital: Optional[int] = None


class TransactionIn(BaseModel):
    occurred_on: str
    kind: str  # income/expense/salary/vat_payment/tax_payment
    category: str
    description: str
    amount_excl_vat: float
    vat_rate: float = 0.25
    notes: Optional[str] = None


class TransactionOut(BaseModel):
    id: int
    occurred_on: str
    kind: str
    category: str
    description: str
    amount_excl_vat: float
    vat_rate: float
    vat_amount: float
    total_incl_vat: float
    notes: Optional[str]


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    org_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    is_private: bool = False


class CustomerOut(BaseModel):
    id: int
    name: str
    org_number: Optional[str]
    email: Optional[str]
    address: Optional[str]
    is_private: bool


class InvoiceIn(BaseModel):
    customer_id: int
    issued_on: str
    due_on: str
    description: str
    amount_excl_vat: float
    vat_rate: float = 0.25
    rot_rut_kind: Optional[str] = None
    rot_rut_amount: Optional[float] = None


class InvoiceOut(BaseModel):
    id: int
    invoice_number: str
    customer_name: str
    issued_on: str
    due_on: str
    description: str
    amount_excl_vat: float
    vat_amount: float
    total_incl_vat: float
    status: str
    paid_on: Optional[str]
    rot_rut_kind: Optional[str]
    rot_rut_amount: Optional[float]


class OwnerSalaryIn(BaseModel):
    paid_on: str
    gross_salary: int = Field(ge=1)
    is_young: bool = False
    notes: Optional[str] = None


class OwnerSalaryOut(BaseModel):
    id: int
    paid_on: str
    gross_salary: float
    employer_fee_amount: float
    prel_tax_amount: float
    net_to_owner: float
    total_cost_to_company: float


class VatPeriodOut(BaseModel):
    id: int
    period_label: str
    start_date: str
    end_date: str
    due_date: str
    output_vat: float
    input_vat: float
    net_vat: float
    status: str
    filed_on: Optional[str]


class FileVatIn(BaseModel):
    period_label: str  # "2026-Q1" | "2026"
    start_date: str
    end_date: str
    due_date: str


class CorporateTaxOut(BaseModel):
    year: int
    income_total: float
    expense_total: float
    profit_before_tax: float
    corporate_tax_rate: float
    estimated_tax: float
    profit_after_tax: float
    n_transactions: int


# === Helpers ===


def _require_student(info: TokenInfo) -> int:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast elev-konto kan använda Företagsläget.",
        )
    return info.student_id


def _get_active_company(s) -> Optional[Company]:
    return (
        s.query(Company)
        .filter(Company.active.is_(True))
        .order_by(Company.id.desc())
        .first()
    )


def _to_company_out(c: Company) -> CompanyOut:
    # City-display från stadspool (Sthlm/Göteborg/Umeå-display-namn)
    city_display: Optional[str] = None
    try:
        from ..game_engine.pools.stadspool import STAD_BY_KEY
        if c.city_key:
            stad = STAD_BY_KEY.get(c.city_key)
            if stad is not None:
                city_display = stad.display
    except Exception:
        pass
    return CompanyOut(
        id=c.id,
        name=c.name,
        org_number=c.org_number,
        form=c.form,
        started_on=c.started_on.isoformat(),
        share_capital=c.share_capital,
        vat_registered=c.vat_registered,
        vat_period=c.vat_period,
        sni_code=c.sni_code,
        industry_label=c.industry_label,
        industry_key=c.industry_key,
        city_key=c.city_key,
        city_display=city_display,
        active=c.active,
    )


def _to_tx_out(t: CompanyTransaction) -> TransactionOut:
    total = float(t.amount_excl_vat) + float(t.vat_amount or 0)
    return TransactionOut(
        id=t.id,
        occurred_on=t.occurred_on.isoformat(),
        kind=t.kind,
        category=t.category,
        description=t.description,
        amount_excl_vat=float(t.amount_excl_vat),
        vat_rate=float(t.vat_rate or 0),
        vat_amount=float(t.vat_amount or 0),
        total_incl_vat=total,
        notes=t.notes,
    )


# === Endpoints: Industries (10 fasta branscher) ===


class IndustryOut(BaseModel):
    key: str
    label: str
    short_description: str
    sni_code: str
    hourly_rate_min: int
    hourly_rate_max: int
    margin_baseline_pct: int
    requires_lokal: bool
    monthly_lokal_cost_baseline: int
    equipment_cost_init: int
    pipeline_per_week_baseline: float
    learning_focus: str
    available_in_my_city: bool


@router.get("/industries", response_model=list[IndustryOut])
def list_industries_endpoint(info: TokenInfo = Depends(require_token)):
    """Lista de 10 fasta branscherna · markera vilka som funkar i
    elevens stad. Frontend renderar branscherna som klickbara kort i
    företagsstart-flödet."""
    student_id = _require_student(info)
    from ..business.industries import (
        list_industries, industry_available_in_city,
    )
    from ..school.engines import master_session
    from ..school.models import StudentProfile

    # Hämta elevens stad
    city_key: Optional[str] = None
    with master_session() as ms:
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        if prof is not None and prof.city:
            from ..game_engine.pools.stadspool import STADSPOOL
            display = prof.city.strip().lower()
            for stad in STADSPOOL:
                if stad.key == display or stad.display.lower() == display:
                    city_key = stad.key
                    break

    rows: list[IndustryOut] = []
    for ind in list_industries():
        avail = (
            industry_available_in_city(ind.key, city_key)
            if city_key else True
        )
        rows.append(IndustryOut(
            key=ind.key,
            label=ind.label,
            short_description=ind.short_description,
            sni_code=ind.sni_code,
            hourly_rate_min=ind.hourly_rate_min,
            hourly_rate_max=ind.hourly_rate_max,
            margin_baseline_pct=ind.margin_baseline_pct,
            requires_lokal=ind.requires_lokal,
            monthly_lokal_cost_baseline=ind.monthly_lokal_cost_baseline,
            equipment_cost_init=ind.equipment_cost_init,
            pipeline_per_week_baseline=ind.pipeline_per_week_baseline,
            learning_focus=ind.learning_focus,
            available_in_my_city=avail,
        ))
    return rows


# === Endpoints: Company ===


@router.get("", response_model=Optional[CompanyOut])
def get_company(info: TokenInfo = Depends(require_token)):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            return None
        # Auto-tick · drar fram veckor som passerat sedan senaste read.
        # Trigger:as även här eftersom BizHub fetchar /v2/foretag direkt
        # vid mount · innan opportunities-listan hämtas.
        try:
            from ..business.engine import auto_tick_if_due
            auto_tick_if_due(s, company=c)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "get_company: auto_tick_if_due misslyckades · returnerar "
                "ändå bolag (state hängar efter tills nästa endpoint).",
            )
        return _to_company_out(c)


@router.post("", response_model=CompanyOut)
def create_company(
    body: CompanyIn,
    info: TokenInfo = Depends(require_token),
):
    """Skapa elevens bolag.

    Reglerar:
    - industry_key måste vara en av de 10 fasta branscherna
    - city_key ärvs från karaktärens StudentProfile.city (kan ej
      ändras av eleven)
    - Om branschen kräver minst medel-stad och eleven bor i en
      mindre stad → 400 med pedagogiskt fel
    - sni_code + industry_label fylls automatiskt från industry_key
    """
    student_id = _require_student(info)

    # 1. Valider bransch
    from ..business.industries import (
        get_industry, industry_available_in_city,
    )
    try:
        industry = get_industry(body.industry_key)
    except ValueError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Okänd bransch · {e}",
        )

    # 2. Hämta karaktärens stad
    from ..school.engines import master_session
    from ..school.models import StudentProfile
    city_key: Optional[str] = None
    with master_session() as ms:
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        if prof is not None:
            # StudentProfile.city är display-namn ("Stockholm"); vi
            # mappar till key via stadspool
            city_display = (prof.city or "").strip().lower()
            if city_display:
                from ..game_engine.pools.stadspool import (
                    STAD_BY_KEY, STADSPOOL,
                )
                # Försök matcha mot key direkt eller mot display
                for stad in STADSPOOL:
                    if stad.key == city_display or stad.display.lower() == city_display:
                        city_key = stad.key
                        break
                if city_key is None and city_display in STAD_BY_KEY:
                    city_key = city_display

    # 3. Valider att branschen är meningsfull i karaktärens stad
    if city_key and not industry_available_in_city(industry.key, city_key):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Branschen '{industry.label}' kräver minst medel-stad. "
            f"Din karaktär bor i {city_key} — välj en annan bransch "
            "eller starta i en bransch som funkar lokalt.",
        )

    with session_scope() as s:
        existing = _get_active_company(s)
        if existing is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Du har redan ett aktivt bolag. Stäng det innan du skapar nytt.",
            )
        c = Company(
            name=body.name,
            org_number=body.org_number,
            form=body.form,
            started_on=date.today(),
            share_capital=body.share_capital,
            vat_registered=body.vat_registered,
            vat_period=body.vat_period,
            sni_code=industry.sni_code,
            industry_label=industry.label,
            industry_key=industry.key,
            city_key=city_key,
        )
        s.add(c)
        s.flush()
        result = _to_company_out(c)

        # Seed initiala vecko-tickar så bolaget inte är tomt direkt efter
        # skapande. Eleven ska se några första offerter/kunder att jobba
        # med · annars känns företagsdelen "död" tills nästa månadsskifte.
        # 2 veckor räcker för pipeline_generator att producera ~4-8
        # opportunities + första repuation_drift.
        try:
            from ..business.engine import run_business_week
            for _ in range(2):
                run_business_week(s, company=c)
            s.flush()
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "create_company: initial biz tick failed för company %s — "
                "bolaget är skapat men kommer initialt vara tomt; nästa "
                "vecko-tick fyller på.", c.id,
            )

        # Sync till Allabolag-cachen så företaget syns på klassens
        # scoreboard direkt efter skapande.
        try:
            from ..school.engines import master_session as _ms_share
            from ..school.models import Student as _Stu_share
            from .allabolag import sync_class_company_share
            with _ms_share() as _ms_s:
                stu_share = _ms_s.get(_Stu_share, student_id)
                if stu_share is not None:
                    sync_class_company_share(
                        s,
                        company=c,
                        teacher_id=stu_share.teacher_id,
                        student_id=student_id,
                        class_label=stu_share.class_label,
                    )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "create_company: Allabolag-sync misslyckades för company %s",
                c.id,
            )

    # Lärar-spårning · syns på lärar-dashboardens aktivitetsflöde
    try:
        from ..school.activity import log_activity
        log_activity(
            kind="biz.company_created",
            summary=f"Startade {industry.label.lower()}-bolag · {body.name}",
            payload={
                "company_id": result.id,
                "company_name": body.name,
                "form": body.form,
                "industry_key": industry.key,
                "city_key": city_key,
                "share_capital": body.share_capital,
                "vat_registered": body.vat_registered,
            },
        )
    except Exception:
        pass

    return result


@router.patch("/{company_id}", response_model=CompanyOut)
def patch_company(
    company_id: int,
    body: CompanyIn,
    info: TokenInfo = Depends(require_token),
):
    _require_student(info)
    with session_scope() as s:
        c = s.get(Company, company_id)
        if c is None or not c.active:
            raise HTTPException(404, "Bolag saknas")
        c.name = body.name
        c.form = body.form
        c.org_number = body.org_number
        c.sni_code = body.sni_code
        c.industry_label = body.industry_label
        c.vat_registered = body.vat_registered
        c.vat_period = body.vat_period
        c.share_capital = body.share_capital
        s.flush()
        return _to_company_out(c)


@router.delete("/{company_id}", status_code=204)
def close_company(
    company_id: int,
    info: TokenInfo = Depends(require_token),
):
    _require_student(info)
    with session_scope() as s:
        c = s.get(Company, company_id)
        if c is None:
            raise HTTPException(404, "Bolag saknas")
        c.active = False
        c.closed_on = date.today()
        s.flush()
    return None


# === Endpoints: Transactions ===


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    info: TokenInfo = Depends(require_token),
    limit: int = 100,
):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            return []
        rows = (
            s.query(CompanyTransaction)
            .filter(CompanyTransaction.company_id == c.id)
            .order_by(CompanyTransaction.occurred_on.desc())
            .limit(min(limit, 500))
            .all()
        )
        return [_to_tx_out(t) for t in rows]


@router.post("/transactions", response_model=TransactionOut)
def add_transaction(
    body: TransactionIn,
    info: TokenInfo = Depends(require_token),
):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Skapa ett bolag först")
        amount = Decimal(str(body.amount_excl_vat))
        vat_amount = (amount * Decimal(str(body.vat_rate))).quantize(
            Decimal("0.01"),
        )
        t = CompanyTransaction(
            company_id=c.id,
            occurred_on=date.fromisoformat(body.occurred_on),
            kind=body.kind,
            category=body.category,
            description=body.description,
            amount_excl_vat=amount,
            vat_rate=Decimal(str(body.vat_rate)),
            vat_amount=vat_amount,
            notes=body.notes,
        )
        s.add(t)
        s.flush()
        return _to_tx_out(t)


@router.delete("/transactions/{tx_id}", status_code=204)
def delete_transaction(
    tx_id: int,
    info: TokenInfo = Depends(require_token),
):
    _require_student(info)
    with session_scope() as s:
        t = s.get(CompanyTransaction, tx_id)
        if t is None:
            raise HTTPException(404, "Transaktion saknas")
        s.delete(t)
    return None


# === Endpoints: Customers ===


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(info: TokenInfo = Depends(require_token)):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            return []
        rows = (
            s.query(CompanyCustomer)
            .filter(CompanyCustomer.company_id == c.id)
            .order_by(CompanyCustomer.name)
            .all()
        )
        return [
            CustomerOut(
                id=r.id, name=r.name, org_number=r.org_number,
                email=r.email, address=r.address, is_private=r.is_private,
            )
            for r in rows
        ]


@router.post("/customers", response_model=CustomerOut)
def add_customer(
    body: CustomerIn,
    info: TokenInfo = Depends(require_token),
):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Skapa bolag först")
        cust = CompanyCustomer(
            company_id=c.id,
            name=body.name,
            org_number=body.org_number,
            email=body.email,
            address=body.address,
            is_private=body.is_private,
        )
        s.add(cust)
        s.flush()
        return CustomerOut(
            id=cust.id, name=cust.name, org_number=cust.org_number,
            email=cust.email, address=cust.address, is_private=cust.is_private,
        )


# === Endpoints: Invoices ===


def _invoice_to_out(inv: CompanyInvoice, customer_name: str) -> InvoiceOut:
    return InvoiceOut(
        id=inv.id,
        invoice_number=inv.invoice_number,
        customer_name=customer_name,
        issued_on=inv.issued_on.isoformat(),
        due_on=inv.due_on.isoformat(),
        description=inv.description,
        amount_excl_vat=float(inv.amount_excl_vat),
        vat_amount=float(inv.vat_amount or 0),
        total_incl_vat=float(inv.amount_excl_vat) + float(inv.vat_amount or 0),
        status=inv.status,
        paid_on=inv.paid_on.isoformat() if inv.paid_on else None,
        rot_rut_kind=inv.rot_rut_kind,
        rot_rut_amount=float(inv.rot_rut_amount) if inv.rot_rut_amount else None,
    )


@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(info: TokenInfo = Depends(require_token)):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            return []
        rows = (
            s.query(CompanyInvoice)
            .filter(CompanyInvoice.company_id == c.id)
            .order_by(CompanyInvoice.issued_on.desc())
            .all()
        )
        out = []
        for r in rows:
            cust = s.get(CompanyCustomer, r.customer_id)
            out.append(_invoice_to_out(r, cust.name if cust else "?"))
        return out


@router.post("/invoices", response_model=InvoiceOut)
def add_invoice(
    body: InvoiceIn,
    info: TokenInfo = Depends(require_token),
):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Skapa bolag först")
        cust = s.get(CompanyCustomer, body.customer_id)
        if cust is None or cust.company_id != c.id:
            raise HTTPException(404, "Kund saknas")

        # Stabilt fakturanummer · YYYY-NNNN
        n_existing = (
            s.query(CompanyInvoice)
            .filter(CompanyInvoice.company_id == c.id)
            .count()
        )
        invoice_number = f"{date.today().year}-{n_existing + 1:04d}"

        amount = Decimal(str(body.amount_excl_vat))
        vat_amount = (amount * Decimal(str(body.vat_rate))).quantize(
            Decimal("0.01"),
        )

        inv = CompanyInvoice(
            company_id=c.id,
            customer_id=cust.id,
            invoice_number=invoice_number,
            issued_on=date.fromisoformat(body.issued_on),
            due_on=date.fromisoformat(body.due_on),
            description=body.description,
            amount_excl_vat=amount,
            vat_rate=Decimal(str(body.vat_rate)),
            vat_amount=vat_amount,
            status="sent",
            rot_rut_kind=body.rot_rut_kind,
            rot_rut_amount=(
                Decimal(str(body.rot_rut_amount))
                if body.rot_rut_amount else None
            ),
        )
        s.add(inv)
        s.flush()
        out = _invoice_to_out(inv, cust.name)
        cust_name_for_log = cust.name
        amount_for_log = float(amount + vat_amount)

    try:
        from ..school.activity import log_activity
        log_activity(
            kind="biz.invoice_created",
            summary=(
                f"Skickade faktura {out.invoice_number} till "
                f"{cust_name_for_log} · {amount_for_log:.0f} kr"
            ),
            payload={
                "invoice_id": out.id,
                "invoice_number": out.invoice_number,
                "customer_id": body.customer_id,
                "amount_total": amount_for_log,
                "due_on": body.due_on,
                "rot_rut_kind": body.rot_rut_kind,
            },
        )
    except Exception:
        pass

    return out


@router.post("/invoices/{invoice_id}/mark-paid", response_model=InvoiceOut)
def mark_invoice_paid(
    invoice_id: int,
    info: TokenInfo = Depends(require_token),
):
    _require_student(info)
    with session_scope() as s:
        inv = s.get(CompanyInvoice, invoice_id)
        if inv is None:
            raise HTTPException(404, "Faktura saknas")
        if inv.status == "paid":
            cust = s.get(CompanyCustomer, inv.customer_id)
            return _invoice_to_out(inv, cust.name if cust else "?")

        inv.status = "paid"
        inv.paid_on = date.today()

        # Bokför som income-transaktion
        s.add(CompanyTransaction(
            company_id=inv.company_id,
            occurred_on=inv.paid_on,
            kind="income",
            category="Försäljning",
            description=f"Faktura {inv.invoice_number} betald",
            amount_excl_vat=inv.amount_excl_vat,
            vat_rate=inv.vat_rate,
            vat_amount=inv.vat_amount or Decimal(0),
        ))
        s.flush()
        cust = s.get(CompanyCustomer, inv.customer_id)
        out = _invoice_to_out(inv, cust.name if cust else "?")
        amount_paid_log = float(
            (inv.amount_excl_vat or Decimal(0))
            + (inv.vat_amount or Decimal(0))
        )
        cust_name_log = cust.name if cust else "?"

    try:
        from ..school.activity import log_activity
        log_activity(
            kind="biz.invoice_paid",
            summary=(
                f"Faktura {out.invoice_number} betald · {cust_name_log} · "
                f"{amount_paid_log:.0f} kr"
            ),
            payload={
                "invoice_id": out.id,
                "invoice_number": out.invoice_number,
                "amount_total": amount_paid_log,
            },
        )
    except Exception:
        pass

    return out


# === Endpoints: Owner Salary (AB) ===


@router.get("/owner-salaries", response_model=list[OwnerSalaryOut])
def list_owner_salaries(info: TokenInfo = Depends(require_token)):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            return []
        rows = (
            s.query(CompanyOwnerSalary)
            .filter(CompanyOwnerSalary.company_id == c.id)
            .order_by(CompanyOwnerSalary.paid_on.desc())
            .all()
        )
        return [
            OwnerSalaryOut(
                id=r.id,
                paid_on=r.paid_on.isoformat(),
                gross_salary=float(r.gross_salary),
                employer_fee_amount=float(r.employer_fee_amount),
                prel_tax_amount=float(r.prel_tax_amount),
                net_to_owner=float(r.net_to_owner),
                total_cost_to_company=float(r.total_cost_to_company),
            )
            for r in rows
        ]


@router.post("/owner-salary", response_model=OwnerSalaryOut)
def pay_owner_salary(
    body: OwnerSalaryIn,
    info: TokenInfo = Depends(require_token),
):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Skapa bolag först")
        if c.form != "ab":
            raise HTTPException(
                400,
                "Lön till ägare gäller bara aktiebolag. "
                "Enskild firma använder 'eget uttag' (skapa transaction).",
            )
        row = book_owner_salary(
            s,
            company=c,
            gross_salary=body.gross_salary,
            paid_on=date.fromisoformat(body.paid_on),
            is_young=body.is_young,
            notes=body.notes,
            student_id=info.student_id,
        )
        result = OwnerSalaryOut(
            id=row.id,
            paid_on=row.paid_on.isoformat(),
            gross_salary=float(row.gross_salary),
            employer_fee_amount=float(row.employer_fee_amount),
            prel_tax_amount=float(row.prel_tax_amount),
            net_to_owner=float(row.net_to_owner),
            total_cost_to_company=float(row.total_cost_to_company),
        )

    try:
        from ..school.activity import log_activity
        log_activity(
            kind="biz.owner_salary",
            summary=(
                f"Tog ut lön · brutto {result.gross_salary:.0f} kr · "
                f"netto {result.net_to_owner:.0f} kr · "
                f"AGI+sociala {result.employer_fee_amount:.0f} kr"
            ),
            payload={
                "gross_salary": result.gross_salary,
                "net_to_owner": result.net_to_owner,
                "employer_fee": result.employer_fee_amount,
                "prel_tax": result.prel_tax_amount,
                "total_cost": result.total_cost_to_company,
            },
        )
    except Exception:
        pass

    return result


class OwnerWithdrawalIn(BaseModel):
    paid_on: str
    amount: int = Field(ge=1)
    notes: Optional[str] = None


class OwnerWithdrawalOut(BaseModel):
    id: int
    paid_on: str
    amount: int


@router.post("/owner-withdrawal", response_model=OwnerWithdrawalOut)
def withdraw_owner(
    body: OwnerWithdrawalIn,
    info: TokenInfo = Depends(require_token),
):
    """Bug #7-utbyggnad · Eget uttag från enskild firma.

    Pengarna går från företagskontot till elevens privata lönekonto
    direkt. Eleven betalar privatskatt på överskottet vid årsdeklaration.
    """
    sid = _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Skapa bolag först")
        if c.form != "enskild_firma":
            raise HTTPException(
                400,
                "Eget uttag gäller bara enskild firma. AB använder lön.",
            )
        tx = book_owner_withdrawal(
            s,
            company=c,
            amount=body.amount,
            paid_on=date.fromisoformat(body.paid_on),
            notes=body.notes,
            student_id=sid,
        )
        return OwnerWithdrawalOut(
            id=tx.id,
            paid_on=tx.occurred_on.isoformat(),
            amount=int(tx.amount_excl_vat),
        )


@router.get("/owner-salary/preview")
def preview_owner_salary(
    gross_salary: int,
    is_young: bool = False,
    info: TokenInfo = Depends(require_token),
):
    _require_student(info)
    return compute_owner_salary(gross_salary=gross_salary, is_young=is_young)


# === Endpoints: VAT ===


@router.get("/vat/periods", response_model=list[VatPeriodOut])
def list_vat_periods(info: TokenInfo = Depends(require_token)):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            return []
        rows = (
            s.query(CompanyVatPeriod)
            .filter(CompanyVatPeriod.company_id == c.id)
            .order_by(CompanyVatPeriod.start_date.desc())
            .all()
        )
        return [
            VatPeriodOut(
                id=r.id,
                period_label=r.period_label,
                start_date=r.start_date.isoformat(),
                end_date=r.end_date.isoformat(),
                due_date=r.due_date.isoformat(),
                output_vat=float(r.output_vat or 0),
                input_vat=float(r.input_vat or 0),
                net_vat=float(r.net_vat or 0),
                status=r.status,
                filed_on=r.filed_on.isoformat() if r.filed_on else None,
            )
            for r in rows
        ]


@router.get("/vat/preview")
def preview_vat(
    start: str,
    end: str,
    info: TokenInfo = Depends(require_token),
):
    """Förhandsvisa moms för en period utan att lämna in deklarationen."""
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Skapa bolag först")
        return compute_period_vat(
            s, company=c,
            start=date.fromisoformat(start),
            end=date.fromisoformat(end),
        )


@router.post("/vat/file", response_model=VatPeriodOut)
def file_vat(
    body: FileVatIn,
    info: TokenInfo = Depends(require_token),
):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Skapa bolag först")
        if not c.vat_registered:
            raise HTTPException(
                400,
                "Bolaget är inte momsregistrerat. Slå på i bolagsinställningar.",
            )
        period = file_vat_period(
            s,
            company=c,
            period_label=body.period_label,
            start=date.fromisoformat(body.start_date),
            end=date.fromisoformat(body.end_date),
            due=date.fromisoformat(body.due_date),
        )
        result = VatPeriodOut(
            id=period.id,
            period_label=period.period_label,
            start_date=period.start_date.isoformat(),
            end_date=period.end_date.isoformat(),
            due_date=period.due_date.isoformat(),
            output_vat=float(period.output_vat or 0),
            input_vat=float(period.input_vat or 0),
            net_vat=float(period.net_vat or 0),
            status=period.status,
            filed_on=period.filed_on.isoformat() if period.filed_on else None,
        )

    try:
        from ..school.activity import log_activity
        log_activity(
            kind="biz.vat_filed",
            summary=(
                f"Lämnade in moms-deklaration {result.period_label} · "
                f"netto {result.net_vat:.0f} kr"
            ),
            payload={
                "period_label": result.period_label,
                "output_vat": result.output_vat,
                "input_vat": result.input_vat,
                "net_vat": result.net_vat,
            },
        )
    except Exception:
        pass

    return result


# === Endpoints: Bolagsskatt ===


@router.get("/corporate-tax/{year}", response_model=CorporateTaxOut)
def corporate_tax_estimate(
    year: int,
    info: TokenInfo = Depends(require_token),
):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Skapa bolag först")
        if c.form != "ab":
            raise HTTPException(
                400, "Bolagsskatt gäller bara AB. Enskild firma deklarerar "
                "via personlig inkomstskatt.",
            )
        return CorporateTaxOut(**estimate_corporate_tax_for_year(
            s, company=c, year=year,
        ))


class BusinessPentagonOut(BaseModel):
    axes: dict
    axes_prev: Optional[dict] = None
    total_score: int
    metrics: dict


BizAxis = Literal[
    "omsattning", "kundbas", "likviditet", "tidsatgang", "vinst",
]


class BizAxisFactor(BaseModel):
    explanation: str
    points: int          # +/- bidrag
    delta_label: str     # "+5", "-3", "±0"


class BizAxisEvent(BaseModel):
    occurred_at: Optional[date]
    date_label: str
    title: str
    detail: Optional[str] = None
    delta: Optional[int] = None
    delta_label: str


class BizAxisDetailOut(BaseModel):
    axis: BizAxis
    axis_label: str
    axis_number: str
    score: int
    factors: list[BizAxisFactor]
    events: list[BizAxisEvent]
    summary_text: str


_BIZ_AXIS_LABELS: dict[str, tuple[str, str]] = {
    "omsattning": ("Omsättning", "01"),
    "kundbas":    ("Kundbas",    "02"),
    "likviditet": ("Likviditet", "03"),
    "tidsatgang": ("Tidsåtgång", "04"),
    "vinst":      ("Vinst",      "05"),
}


def _short_iso_label(d: Optional[date]) -> str:
    if d is None:
        return "—"
    return d.isoformat()


def _delta_lbl(n: int) -> str:
    if n > 0:
        return f"+{n}"
    if n < 0:
        return str(n)
    return "±0"


def _build_biz_axis_detail(
    s, *, company: Company, axis: BizAxis,
) -> BizAxisDetailOut:
    """Räkna fram axel-detaljer för flip-kortets baksida.

    Speglar privat-flip-kortets struktur: faktorer (live-bidrag) +
    events (konkreta händelser) + summary_text (en mening).
    """
    from ..business.service import compute_business_pentagon
    pent = compute_business_pentagon(s, company=company)
    score = int(pent["axes"].get(axis, 50))
    metrics = pent["metrics"]
    label, number = _BIZ_AXIS_LABELS[axis]

    factors: list[BizAxisFactor] = []
    events: list[BizAxisEvent] = []

    cutoff = date.today() - __import__("datetime").timedelta(days=42)

    if axis == "omsattning":
        income_4w = float(metrics.get("income_4w", 0))
        if income_4w > 0:
            factors.append(BizAxisFactor(
                explanation=f"Intäkter senaste 4 v: {int(income_4w):,} kr".replace(",", " "),
                points=min(40, int(income_4w / 1000)),
                delta_label=_delta_lbl(min(40, int(income_4w / 1000))),
            ))
        else:
            factors.append(BizAxisFactor(
                explanation="Inga intäkter senaste 4 v.",
                points=-10,
                delta_label="−10",
            ))
        # Senaste betalda fakturor
        invs = (
            s.query(CompanyInvoice)
            .filter(
                CompanyInvoice.company_id == company.id,
                CompanyInvoice.paid_on.isnot(None),
                CompanyInvoice.paid_on >= cutoff,
            )
            .order_by(CompanyInvoice.paid_on.desc())
            .limit(6)
            .all()
        )
        for inv in invs:
            events.append(BizAxisEvent(
                occurred_at=inv.paid_on,
                date_label=_short_iso_label(inv.paid_on),
                title=f"{inv.customer_name or '—'} betald · F{inv.invoice_number or ''}",
                detail=f"{int(inv.total_incl_vat or 0):,} kr inkl moms".replace(",", " "),
                delta=int(min(8, max(1, (inv.amount_excl_vat or 0) / 1000))),
                delta_label=_delta_lbl(int(min(8, max(1, (inv.amount_excl_vat or 0) / 1000)))),
            ))
        summary = (
            f"Omsättningen är {int(income_4w):,} kr/4v"
            .replace(",", " ")
            + f" · marginal {metrics.get('margin_4w_pct', 0):.0f}%."
        )

    elif axis == "kundbas":
        n_active = int(metrics.get("n_invoices_active", 0))
        factors.append(BizAxisFactor(
            explanation=f"{n_active} aktiva fakturor senaste 4 v.",
            points=n_active * 8,
            delta_label=_delta_lbl(n_active * 8),
        ))
        # Senaste offert-aktivitet (CompanyOpportunity om den finns)
        try:
            from ..business.models import CompanyOpportunity, CompanyQuote
            opps = (
                s.query(CompanyOpportunity)
                .filter(
                    CompanyOpportunity.company_id == company.id,
                    CompanyOpportunity.received_on >= cutoff,
                )
                .order_by(CompanyOpportunity.received_on.desc())
                .limit(5)
                .all()
            )
            for o in opps:
                delta = (
                    3 if o.status == "won"
                    else -2 if o.status == "lost"
                    else 0
                )
                events.append(BizAxisEvent(
                    occurred_at=o.received_on,
                    date_label=_short_iso_label(o.received_on),
                    title=f"{o.customer_name} · {o.title}",
                    detail=f"Status: {o.status}",
                    delta=delta,
                    delta_label=_delta_lbl(delta),
                ))
            _ = CompanyQuote  # imported för framtid
        except Exception:
            pass
        summary = (
            f"Kundbasen står på {n_active} aktiva fakturor "
            "senaste perioden — ryktet driver pipeline-vikten."
        )

    elif axis == "likviditet":
        kassa = float(metrics.get("kassa", 0))
        if kassa < 0:
            factors.append(BizAxisFactor(
                explanation=f"Företagskontot ligger på {int(kassa):,} kr — minus räknas hårt.".replace(",", " "),
                points=-25,
                delta_label="−25",
            ))
        elif kassa < 5000:
            factors.append(BizAxisFactor(
                explanation=f"Kassa under 5 000 kr ({int(kassa):,} kr) — tunn marginal.".replace(",", " "),
                points=-10,
                delta_label="−10",
            ))
        else:
            factors.append(BizAxisFactor(
                explanation=f"Kassa {int(kassa):,} kr · stabil likviditet.".replace(",", " "),
                points=10,
                delta_label="+10",
            ))
        # Nästa moms-due
        from ..business.models import CompanyVatPeriod
        nv = (
            s.query(CompanyVatPeriod)
            .filter(
                CompanyVatPeriod.company_id == company.id,
                CompanyVatPeriod.status == "open",
            )
            .order_by(CompanyVatPeriod.due_date.asc())
            .first()
        )
        if nv:
            events.append(BizAxisEvent(
                occurred_at=nv.due_date,
                date_label=_short_iso_label(nv.due_date),
                title=f"Moms-period {nv.period_label} · förfaller",
                detail=f"Att betala: {int(nv.net_vat or 0):,} kr".replace(",", " "),
                delta=-3 if (nv.net_vat or 0) > kassa else -1,
                delta_label=_delta_lbl(-3 if (nv.net_vat or 0) > kassa else -1),
            ))
        # Senaste in/ut-rörelser
        recent = (
            s.query(CompanyTransaction)
            .filter(
                CompanyTransaction.company_id == company.id,
                CompanyTransaction.occurred_on >= cutoff,
            )
            .order_by(CompanyTransaction.occurred_on.desc())
            .limit(5)
            .all()
        )
        for t in recent:
            is_income = t.kind == "income"
            d = 2 if is_income else -1
            events.append(BizAxisEvent(
                occurred_at=t.occurred_on,
                date_label=_short_iso_label(t.occurred_on),
                title=t.description or t.category or t.kind,
                detail=f"{int(t.amount_excl_vat):,} kr · {t.kind}".replace(",", " "),
                delta=d,
                delta_label=_delta_lbl(d),
            ))
        summary = (
            f"Likviditet · {int(kassa):,} kr på företagskontot.".replace(",", " ")
            + (f" Moms {nv.due_date} kommer dra {int(nv.net_vat or 0):,} kr.".replace(",", " ") if nv else "")
        )

    elif axis == "tidsatgang":
        income_4w = float(metrics.get("income_4w", 0))
        factors.append(BizAxisFactor(
            explanation=(
                "Aktivt företag · debiterbar tid genererar omsättning."
                if income_4w > 0
                else "Inaktivt — ingen debiterbar tid registrerad."
            ),
            points=20 if income_4w > 0 else -10,
            delta_label=_delta_lbl(20 if income_4w > 0 else -10),
        ))
        # Pågående jobb om det finns Job-data
        try:
            from ..business.models import CompanyJob
            jobs = (
                s.query(CompanyJob)
                .filter(
                    CompanyJob.company_id == company.id,
                    CompanyJob.status.in_(("in_progress", "delivered")),
                )
                .order_by(CompanyJob.created_at.desc())
                .limit(5)
                .all()
            )
            for j in jobs:
                events.append(BizAxisEvent(
                    occurred_at=getattr(j, "delivered_on", None) or getattr(j, "created_at", None),
                    date_label=_short_iso_label(
                        getattr(j, "delivered_on", None) or (
                            getattr(j, "created_at", None).date()
                            if getattr(j, "created_at", None)
                            else None
                        ),
                    ),
                    title=f"{j.customer_name} · {j.title}",
                    detail=f"Status: {j.status}",
                    delta=1,
                    delta_label="+1",
                ))
        except Exception:
            pass
        summary = (
            "Tidsåtgång räknas förenklat 60/40 (debiterbar / admin) just nu. "
            "Pentagon-axeln stiger när du levererar jobb och hanterar fakturor "
            "snabbare än de strömmar in."
        )

    elif axis == "vinst":
        margin = float(metrics.get("margin_4w_pct", 0))
        profit = float(metrics.get("profit_4w", 0))
        if margin >= 30:
            factors.append(BizAxisFactor(
                explanation=f"Stark vinstmarginal {margin:.0f}% senaste 4 v.",
                points=40,
                delta_label="+40",
            ))
        elif margin >= 15:
            factors.append(BizAxisFactor(
                explanation=f"OK vinstmarginal {margin:.0f}% senaste 4 v.",
                points=20,
                delta_label="+20",
            ))
        elif margin >= 0:
            factors.append(BizAxisFactor(
                explanation=f"Marginalen är tunn ({margin:.0f}%) — överväg pris eller kostnader.",
                points=-5,
                delta_label="−5",
            ))
        else:
            factors.append(BizAxisFactor(
                explanation=f"Förlust {margin:.0f}% — företaget går back.",
                points=-25,
                delta_label="−25",
            ))
        # Senaste kostnads-tunga utgifter
        big_expenses = (
            s.query(CompanyTransaction)
            .filter(
                CompanyTransaction.company_id == company.id,
                CompanyTransaction.kind.in_(("expense", "salary")),
                CompanyTransaction.occurred_on >= cutoff,
            )
            .order_by(CompanyTransaction.amount_excl_vat.desc())
            .limit(5)
            .all()
        )
        for t in big_expenses:
            events.append(BizAxisEvent(
                occurred_at=t.occurred_on,
                date_label=_short_iso_label(t.occurred_on),
                title=t.description or t.category or "Utgift",
                detail=f"−{int(t.amount_excl_vat):,} kr · {t.kind}".replace(",", " "),
                delta=-1,
                delta_label="−1",
            ))
        summary = (
            f"Vinst {int(profit):,} kr/4v".replace(",", " ")
            + f" · marginal {margin:.0f}%."
        )

    else:
        summary = "Okänd axel."

    return BizAxisDetailOut(
        axis=axis,
        axis_label=label,
        axis_number=number,
        score=score,
        factors=factors,
        events=events,
        summary_text=summary,
    )


@router.get(
    "/pentagon/axis/{axis}",
    response_model=BizAxisDetailOut,
)
def biz_pentagon_axis_detail(
    axis: BizAxis,
    info: TokenInfo = Depends(require_token),
):
    """Detalj-vy för ett pentagon-axel (för flip-kortets baksida).

    Returnerar score + faktorer (live-bidrag) + senaste events
    (riktiga händelser från företagets transaktioner / fakturor /
    offerter) + en kort summary_text.
    """
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Skapa bolag först")
        return _build_biz_axis_detail(s, company=c, axis=axis)


class EmploymentDecisionStatusOut(BaseModel):
    pending: bool
    weekly_hours_business: int
    weekly_hours_employed: int
    consecutive_overload_weeks: int
    employment_status: str          # "employed"|"freelance_only"
    options: list[str]
    summary: str


class EmploymentDecisionIn(BaseModel):
    choice: Literal["keep_fulltime", "go_parttime", "resign"]


class EmploymentDecisionResultOut(BaseModel):
    choice: str
    summary: str
    weekly_hours_employed: int
    salary_change_pct: int
    salary_ends_in_months: Optional[int] = None


@router.get(
    "/employment-decision/status",
    response_model=EmploymentDecisionStatusOut,
)
def biz_employment_decision_status(info: TokenInfo = Depends(require_token)):
    """Status för säg-upp-prompten.

    Triggar 'pending=True' när företaget tar ≥ 25 h/v i 4 veckor i rad.
    Frontend kollar denna periodvis (eller efter combined-tick) och
    visar Maria-modalen om pending.
    """
    student_id = _require_student(info)
    from ..business.cross_pentagon import compute_weekly_business_hours
    from ..business.employment_decision import (
        evaluate_employment_decision,
    )
    from ..school.engines import master_session
    from ..school.models import StudentProfile

    weekly_h = 0
    with session_scope() as s:
        c = _get_active_company(s)
        if c is not None:
            in_progress = (
                s.query(__import__(
                    "hembudget.business.models", fromlist=["Job"],
                ).Job)
                .filter_by(company_id=c.id, status="in_progress")
                .all()
            )
            weekly_h = compute_weekly_business_hours(
                in_progress, industry_key=c.industry_key,
            )

    with master_session() as ms:
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        emp_status = (
            getattr(prof, "employment_status", "employed")
            if prof else "employed"
        )
        emp_hours = (
            int(getattr(prof, "weekly_hours_employed", 40) or 40)
            if prof else 40
        )
        overload_weeks = (
            int(getattr(prof, "consecutive_overload_weeks", 0) or 0)
            if prof else 0
        )

    trigger = evaluate_employment_decision(
        weekly_hours_business=weekly_h,
        consecutive_overload_weeks=overload_weeks,
        employment_status=emp_status,
    )

    return EmploymentDecisionStatusOut(
        pending=trigger.should_trigger,
        weekly_hours_business=weekly_h,
        weekly_hours_employed=emp_hours,
        consecutive_overload_weeks=overload_weeks,
        employment_status=emp_status,
        options=trigger.options,
        summary=trigger.reason,
    )


@router.post(
    "/employment-decision",
    response_model=EmploymentDecisionResultOut,
)
def biz_employment_decision(
    body: EmploymentDecisionIn,
    info: TokenInfo = Depends(require_token),
):
    """Eleven väljer · keep_fulltime / go_parttime / resign.

    Uppdaterar StudentProfile direkt. Lön-effekt syns nästa månadstick.
    """
    student_id = _require_student(info)
    from ..business.employment_decision import apply_employment_decision
    from ..school.engines import master_session
    from ..school.models import StudentProfile

    with master_session() as ms:
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        if prof is None:
            raise HTTPException(404, "StudentProfile saknas")
        result = apply_employment_decision(prof, body.choice)
        ms.commit()

    return EmploymentDecisionResultOut(
        choice=result["choice"],
        summary=result["summary"],
        weekly_hours_employed=result.get("weekly_hours_employed", 0),
        salary_change_pct=result.get("salary_change_pct", 0),
        salary_ends_in_months=result.get("salary_ends_in_months"),
    )


class BizPrivateSummaryOut(BaseModel):
    """Sammanfattning för privat-hubben · visar att eleven driver
    företag + status nu (vinst, omsättning, kassa). Asymmetrisk
    aggregation: positiva tal är dämpade, negativa förstärkta för
    pedagogisk effekt."""
    has_company: bool
    company_name: Optional[str] = None
    industry_label: Optional[str] = None
    city_display: Optional[str] = None
    week_no: int = 0
    income_4w: float = 0
    profit_4w: float = 0
    margin_pct: float = 0
    kassa: float = 0
    n_invoices_open: int = 0
    n_invoices_overdue: int = 0
    pentagon_score: int = 0
    # En kort copy som privat-hubben renderar
    summary_text: str = ""
    # Aktivitets-feed · pedagogiska räknare för "Nytt från företaget"-
    # sektionen på privat-hubbens BizSummaryCard. Räknar händelser från
    # senaste 7 spel-veckor (≈ senaste real-vecka med 1 vecka/timme).
    n_new_opportunities: int = 0
    n_quotes_pending: int = 0
    n_quotes_won_recent: int = 0
    n_quotes_lost_recent: int = 0


@router.get(
    "/private-summary",
    response_model=BizPrivateSummaryOut,
)
def biz_private_summary(info: TokenInfo = Depends(require_token)):
    """Aggregat-endpoint för privat-hub:s `<BizSummaryCard>`.

    Returnerar en kompakt sammanfattning av elevens företag · namn,
    bransch, omsättning, vinst, kassa, antal öppna fakturor + en
    pedagogisk one-liner ('Företaget går bra · vinst 34 %').
    """
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            return BizPrivateSummaryOut(has_company=False)
        # Auto-tick · privat-hubben är ofta första vyn eleven öppnar,
        # så biz-state ska hänga med i real-tid även om eleven aldrig
        # går in i biz-läget direkt.
        try:
            from ..business.engine import auto_tick_if_due
            auto_tick_if_due(s, company=c)
        except Exception:
            pass
        pent = compute_business_pentagon(s, company=c)
        metrics = pent["metrics"]
        # Räkna fakturor
        from datetime import date as _d
        today = _d.today()
        invs = (
            s.query(CompanyInvoice)
            .filter(CompanyInvoice.company_id == c.id)
            .all()
        )
        n_open = sum(1 for i in invs if i.status == "sent")
        n_overdue = sum(
            1 for i in invs
            if i.status == "sent" and i.due_on < today
        )

        # Aktivitets-feed · senaste 7 spel-veckor.
        from ..business.models import JobOpportunity as _JO, Quote as _Q
        recent_week_threshold = max(0, int(c.week_no or 0) - 6)
        n_new_opps = (
            s.query(_JO)
            .filter(
                _JO.company_id == c.id,
                _JO.status == "open",
                _JO.week_no >= recent_week_threshold,
            )
            .count()
        )
        n_quotes_pending = (
            s.query(_JO)
            .filter(
                _JO.company_id == c.id,
                _JO.status == "quoted",
            )
            .count()
        )
        n_quotes_won_recent = (
            s.query(_JO)
            .filter(
                _JO.company_id == c.id,
                _JO.status == "won",
                _JO.week_no >= recent_week_threshold,
            )
            .count()
        )
        n_quotes_lost_recent = (
            s.query(_JO)
            .filter(
                _JO.company_id == c.id,
                _JO.status == "lost",
                _JO.week_no >= recent_week_threshold,
            )
            .count()
        )
        # City-display
        city_display: Optional[str] = None
        if c.city_key:
            try:
                from ..game_engine.pools.stadspool import STAD_BY_KEY
                stad = STAD_BY_KEY.get(c.city_key)
                if stad is not None:
                    city_display = stad.display
            except Exception:
                pass

        # Pedagogisk one-liner
        margin = float(metrics.get("margin_4w_pct", 0))
        income = float(metrics.get("income_4w", 0))
        if income == 0:
            summary = "Företaget är just startat — ingen omsättning än."
        elif margin >= 30 and n_overdue == 0:
            summary = f"Företaget går bra · vinst {margin:.0f}% senaste 4 v."
        elif margin >= 15:
            summary = f"OK marginal {margin:.0f}% — håller kassan stadig."
        elif margin >= 0:
            summary = f"Tunn marginal ({margin:.0f}%) — håll koll på kostnader."
        else:
            summary = (
                f"Förlust ({margin:.0f}%) — företaget drar ner "
                "din ekonomiska trygghet."
            )
        if n_overdue > 0:
            summary += f" {n_overdue} kundfaktura förfaller idag."

        return BizPrivateSummaryOut(
            has_company=True,
            company_name=c.name,
            industry_label=c.industry_label,
            city_display=city_display,
            week_no=int(c.week_no or 0),
            income_4w=income,
            profit_4w=float(metrics.get("profit_4w", 0)),
            margin_pct=margin,
            kassa=float(metrics.get("kassa", 0)),
            n_invoices_open=n_open,
            n_invoices_overdue=n_overdue,
            pentagon_score=int(pent["total_score"]),
            summary_text=summary,
            n_new_opportunities=n_new_opps,
            n_quotes_pending=n_quotes_pending,
            n_quotes_won_recent=n_quotes_won_recent,
            n_quotes_lost_recent=n_quotes_lost_recent,
        )


@router.get("/pentagon", response_model=BusinessPentagonOut)
def business_pentagon(info: TokenInfo = Depends(require_token)):
    """Företagets pentagon (5 axlar). Räknas live från CompanyTransactions."""
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Skapa bolag först")
        return BusinessPentagonOut(**compute_business_pentagon(s, company=c))


# === BizBank-overview · matchar prototypen p-biz-bank ===


class BizBankAccountOut(BaseModel):
    """Pseudo-konto för UI:n. Företag har ett kombinerat företagskonto
    + skattekonto + buffert som syntetiseras från CompanyTransaction:s
    kassa-saldo."""
    eye: str
    name: str
    number: str
    balance: float
    balance_meta: str
    is_primary: bool


class BizBankTxOut(BaseModel):
    occurred_on: str
    name: str
    name_sub: Optional[str]
    category: str            # kategori-tag för UI: "Intäkt", "Drift", "Egen lön" m.fl.
    amount_signed: float     # +/- från företagskontots perspektiv
    is_income: bool
    is_owner_salary: bool


class BizBankOverviewOut(BaseModel):
    accounts: list[BizBankAccountOut]
    transactions: list[BizBankTxOut]
    f_skatt_due: Optional[str]   # ISO-datum eller None
    f_skatt_amount: float
    own_salary_this_month: float
    next_vat_due: Optional[str]
    next_vat_amount: float


@router.get("/bank-overview", response_model=BizBankOverviewOut)
def biz_bank_overview(info: TokenInfo = Depends(require_token)):
    """Aggregat-endpoint för p-biz-bank · returnerar:

    - 3 konton (företagskonto, skattekonto, buffert) som syntetiseras
      från company_transactions och vat_periods
    - Senaste 30 dagars kontoutdrag (signed amount + namn + kategori)
    - F-skatt-prognos (om Postgres har vat_periods · annars None)
    - Egen lön denna månad (summa av kind=salary för innevarande mån)
    - Nästa moms-due från vat_periods

    Designprincip: matchar prototypens 3-kolumns acct-grid exakt och
    pedagogiken om "separata bokföringsenheter".
    """
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Skapa bolag först")

        # === Företagskontots saldo (kassa) ===
        # Samma logik som i compute_business_pentagon: ack income -
        # ack expense/salary/vat_payment/tax_payment.
        all_txs = (
            s.query(CompanyTransaction)
            .filter(CompanyTransaction.company_id == c.id)
            .order_by(CompanyTransaction.occurred_on.desc())
            .all()
        )
        total_income = sum(
            (Decimal(t.amount_excl_vat or 0)
             for t in all_txs if t.kind == "income"),
            Decimal(0),
        )
        total_expense = sum(
            (Decimal(t.amount_excl_vat or 0)
             for t in all_txs
             if t.kind in ("expense", "salary", "vat_payment", "tax_payment")),
            Decimal(0),
        )
        kassa = total_income - total_expense

        # === Skattekonto-saldo: summa vat_payment + tax_payment ===
        skattekonto = sum(
            (Decimal(t.amount_excl_vat or 0)
             for t in all_txs
             if t.kind in ("vat_payment", "tax_payment")),
            Decimal(0),
        )

        # === Buffert-konto: pedagogisk, default 0 om inget separat sparkonto ===
        # Vi syntetiserar 0 om eleven inte har avsatt explicit till
        # buffert-kategori (kategori="buffert" markerar avsättning).
        buffert = sum(
            (Decimal(t.amount_excl_vat or 0)
             for t in all_txs
             if t.kind == "expense" and (t.category or "").lower() == "buffert"),
            Decimal(0),
        )

        accounts = [
            BizBankAccountOut(
                eye="Företagskonto",
                name=f"SEB Företag · {c.name}",
                number=c.org_number or "—",
                balance=float(kassa),
                balance_meta="Tillgängligt",
                is_primary=True,
            ),
            BizBankAccountOut(
                eye="Skattekonto",
                name="Skatteverket företag",
                number="SKV — F-skatt",
                balance=float(skattekonto),
                balance_meta="F-skatt-saldo",
                is_primary=False,
            ),
            BizBankAccountOut(
                eye="Buffert",
                name="Sparkonto biz",
                number="Avsatt för moms + F-skatt",
                balance=float(buffert),
                balance_meta="Mål: 3 mån-utgifter",
                is_primary=False,
            ),
        ]

        # === Kontoutdrag · senaste 30 dgr ===
        cutoff = date.today() - __import__("datetime").timedelta(days=30)
        recent = [t for t in all_txs if t.occurred_on >= cutoff][:25]
        tx_rows: list[BizBankTxOut] = []
        for t in recent:
            kind = t.kind
            is_inc = kind == "income"
            amount = float(t.amount_excl_vat or 0)
            signed = amount if is_inc else -amount
            if kind == "income":
                cat = "Intäkt"
            elif kind == "salary":
                cat = "Egen lön"
            elif kind == "vat_payment":
                cat = "Moms"
            elif kind == "tax_payment":
                cat = "Skatt"
            else:
                cat = (t.category or "Drift").capitalize()
            tx_rows.append(BizBankTxOut(
                occurred_on=t.occurred_on.isoformat(),
                name=t.description or f"Transaktion {t.id}",
                name_sub=t.notes,
                category=cat,
                amount_signed=signed,
                is_income=is_inc,
                is_owner_salary=kind == "salary",
            ))

        # === F-skatt + nästa moms-due ===
        from ..business.models import CompanyVatPeriod
        next_vat = (
            s.query(CompanyVatPeriod)
            .filter(
                CompanyVatPeriod.company_id == c.id,
                CompanyVatPeriod.status == "open",
            )
            .order_by(CompanyVatPeriod.due_date.asc())
            .first()
        )
        next_vat_due = (
            next_vat.due_date.isoformat() if next_vat else None
        )
        next_vat_amount = (
            float(next_vat.net_vat or 0) if next_vat else 0.0
        )

        # === Egen lön denna månad ===
        first_of_month = date.today().replace(day=1)
        salary_this = sum(
            (Decimal(t.amount_excl_vat or 0)
             for t in all_txs
             if t.kind == "salary"
             and t.occurred_on >= first_of_month),
            Decimal(0),
        )

        return BizBankOverviewOut(
            accounts=accounts,
            transactions=tx_rows,
            f_skatt_due=None,        # F-skatt-modulen ej fullt implementerad
            f_skatt_amount=0.0,
            own_salary_this_month=float(salary_this),
            next_vat_due=next_vat_due,
            next_vat_amount=next_vat_amount,
        )


# === Bug #7-utbyggnad · status-check (för CompanyMode-toggle) ===


class BusinessModeStatusOut(BaseModel):
    enabled: bool
    has_active_company: bool


@router.get("/mode-status", response_model=BusinessModeStatusOut)
def mode_status(info: TokenInfo = Depends(require_token)):
    """Säger om eleven får använda företagsläget (lärar-toggle) +
    om hen har ett aktivt bolag."""
    sid = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import Student
    with master_session() as ms:
        stu = ms.get(Student, sid)
        enabled = bool(stu and getattr(stu, "business_mode_enabled", False))
    has_company = False
    if enabled:
        with session_scope() as s:
            has_company = _get_active_company(s) is not None
    return BusinessModeStatusOut(
        enabled=enabled, has_active_company=has_company,
    )


# === Lärar-endpoint: toggla business-mode på elev ===


class TeacherToggleIn(BaseModel):
    enabled: bool


@teacher_router.post("/toggle/{student_id}", response_model=BusinessModeStatusOut)
def teacher_toggle_business_mode(
    student_id: int,
    body: TeacherToggleIn,
    info: TokenInfo = Depends(require_token),
):
    """Läraren aktiverar/avaktiverar företagsläget för en elev.

    Vid aktivering · skicka onboarding-mail till elevens postlåda så
    eleven får en pedagogisk inramning innan hen klickar på företag-
    toggle:n. Mail:et beskriver branschmarknaden i elevens stad och
    förklarar att mode-toggle dyker upp i topbaren.
    """
    if info.role != "teacher" or info.teacher_id is None:
        raise HTTPException(403, "Endast lärare")
    from ..school.engines import (
        master_session, scope_context, scope_for_student,
    )
    from ..school.models import Student, StudentProfile, Teacher
    with master_session() as ms:
        stu = ms.get(Student, student_id)
        if stu is None or stu.teacher_id != info.teacher_id:
            raise HTTPException(404, "Elev saknas")
        previously_enabled = bool(getattr(stu, "business_mode_enabled", False))
        stu.business_mode_enabled = body.enabled
        ms.commit()

        # Hämta elev-namn + stad + lärar-namn för mail-content
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        student_first = (stu.display_name or "").split(" ")[0] or "Eleven"
        city_display = (prof.city if prof else None) or "din stad"
        # Läraren som äger eleven (skapade den) signerar mailet
        teacher = ms.get(Teacher, info.teacher_id)
        teacher_name = (
            teacher.name if teacher and teacher.name
            else "Klassansvarig lärare"
        )
        scope_key = scope_for_student(stu)

    # Skicka onboarding-mail · bara vid första aktivering (inte vid re-toggle)
    if body.enabled and not previously_enabled:
        try:
            _send_business_onboarding_mail(
                scope_key=scope_key,
                student_first_name=student_first,
                city_display=city_display,
                teacher_name=teacher_name,
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "teacher_toggle_business_mode: kunde inte skicka "
                "onboarding-mail för %s", student_id,
            )

    # Lärar-spårning · syns på lärar-dashboardens aktivitetsflöde.
    # student_id passas explicit eftersom toggle körs i lärarens session
    # där ContextVar:n inte sätts av StudentScopeMiddleware.
    try:
        from ..school.activity import log_activity
        log_activity(
            kind=(
                "biz.mode_activated_by_teacher" if body.enabled
                else "biz.mode_deactivated_by_teacher"
            ),
            summary=(
                f"Lärare {teacher_name} aktiverade företagsläget"
                if body.enabled
                else f"Lärare {teacher_name} stängde av företagsläget"
            ),
            payload={
                "previously_enabled": previously_enabled,
                "now_enabled": body.enabled,
            },
            student_id=student_id,
        )
    except Exception:
        pass

    return BusinessModeStatusOut(
        enabled=body.enabled,
        has_active_company=False,
    )


def _send_business_onboarding_mail(
    *,
    scope_key: str,
    student_first_name: str,
    city_display: str,
    teacher_name: str,
) -> None:
    """Skapa ett MailItem i elevens postlåda som introducerar
    företagsläget. Mail:et är pedagogiskt och förklarar att eleven
    ska tänka på bransch-val + tidsåtgång + skatt + buffert.

    Signeras av den lärare som skapade eleven · `teacher_name`
    skickas in från caller (läses från Teacher.name)."""
    from ..db.models import MailItem
    from ..school.engines import scope_context, get_scope_session
    from datetime import datetime as _dt

    body_text = (
        f"Hej {student_first_name},\n\n"
        f"Din lärare har aktiverat företagsläget för dig. Det betyder "
        f"att du kan starta en enskild firma eller AB parallellt med "
        f"ditt vanliga jobb.\n\n"
        f"OBS · innan du klickar på 'Företag' i topbaren — läs detta "
        f"så du startar med rätt förutsättningar.\n\n"
        f"=== STAD-MARKNADEN · {city_display} ===\n\n"
        f"Du bor i {city_display} och företaget startar därifrån. Olika "
        f"branscher har olika täthet i olika städer. I storstad finns "
        f"t.ex. mer IT-konsult-uppdrag, i mindre stad är hantverk och "
        f"VVS oftare bra val.\n\n"
        f"När du klickar 'Starta bolag' får du välja mellan 10 fasta "
        f"branscher som passar svenska marknaden 2026:\n"
        f" · IT-konsult\n"
        f" · Webb- & grafisk designer\n"
        f" · Snickare / hantverkare\n"
        f" · Rörmokare / VVS\n"
        f" · Elektriker\n"
        f" · Frisör / barberare\n"
        f" · Coach / livsstilsexpert\n"
        f" · Personal Trainer / friskvård\n"
        f" · Fotograf\n"
        f" · Catering / kokerska\n\n"
        f"=== TÄNK PÅ ===\n\n"
        f"1. TID. Företaget tar timmar varje vecka. När det växer kan "
        f"du behöva gå ner i tid på det vanliga jobbet — eller säga "
        f"upp. Pentagon-axlarna 'fritid' och 'social' kan dippa när "
        f"du jobbar 60+ timmar.\n\n"
        f"2. KASSAFLÖDE. Företagets pengar är inte dina. Du tar ut "
        f"egen lön — och måste lämna kvar tillräckligt för moms + "
        f"F-skatt + leverantörs-fakturor.\n\n"
        f"3. PRIVAT vs FÖRETAG. Två separata bokföringar. När det går "
        f"bra — privatkontot får mer (egen lön upp). När det går "
        f"dåligt — privat-pentagon påverkas av oro/stress (men inte "
        f"1:1, det är en faktor).\n\n"
        f"När du är redo · klicka 'Byt till företag' i topbaren.\n\n"
        f"Lycka till.\n"
        f"— {teacher_name}, klassansvarig"
    )

    # Initialer för sender_short (max 4 tecken)
    name_initials = "".join(
        w[0] for w in teacher_name.split() if w
    )[:4].upper() or "LÄR"

    with scope_context(scope_key):
        with get_scope_session(scope_key)() as s:
            mail = MailItem(
                sender=f"{teacher_name} · klassansvarig",
                sender_short=name_initials,
                sender_kind="other",
                sender_meta="pedagogisk inramning · företagsläget",
                mail_type="info",
                subject=f"Du kan nu driva eget · {city_display}-marknaden",
                body_meta=(
                    "Företagsläget är aktiverat. Läs innan du startar — "
                    "10 branscher att välja på, tid är begränsad."
                ),
                body=body_text,
                amount=None,
                due_date=None,
                received_at=_dt.utcnow(),
                status="unhandled",
            )
            s.add(mail)
            s.commit()


# === Lärar-overview: full insyn i en elevs företag ===


class TeacherForetagOverviewOut(BaseModel):
    student_id: int
    student_name: str
    business_mode_enabled: bool
    company: Optional[CompanyOut]
    pentagon: Optional[BusinessPentagonOut]
    n_transactions_total: int
    n_invoices_total: int
    n_invoices_unpaid: int
    n_owner_salaries: int
    last_owner_salary_date: Optional[str]
    next_vat_due: Optional[str]
    summary_md: str


@teacher_router.get(
    "/overview/{student_id}",
    response_model=TeacherForetagOverviewOut,
)
def teacher_foretag_overview(
    student_id: int,
    info: TokenInfo = Depends(require_token),
) -> TeacherForetagOverviewOut:
    """Lärare ser elevens företagsstatus.

    Innehåller bolag, pentagon, transaktioner-summa, fakturor (totalt +
    obetalda), löneuttag och nästa moms-deadline. Ger läraren en snabb
    bild av om eleven aktivt driver företaget och vart hen är i flödet.
    """
    if info.role != "teacher" or info.teacher_id is None:
        raise HTTPException(403, "Endast lärare")

    from ..school.engines import master_session, scope_context, scope_for_student
    from ..school.models import Student
    with master_session() as ms:
        stu = ms.get(Student, student_id)
        if stu is None or stu.teacher_id != info.teacher_id:
            raise HTTPException(404, "Elev saknas")
        student_name = stu.display_name
        biz_enabled = bool(getattr(stu, "business_mode_enabled", False))
        scope_key = scope_for_student(stu)

    company_out: Optional[CompanyOut] = None
    pentagon_out: Optional[BusinessPentagonOut] = None
    n_tx = 0
    n_inv = 0
    n_inv_unpaid = 0
    n_salary = 0
    last_salary: Optional[str] = None
    next_vat_due: Optional[str] = None

    with scope_context(scope_key):
        with session_scope() as s:
            c = _get_active_company(s)
            if c is not None:
                company_out = _to_company_out(c)
                pentagon_out = BusinessPentagonOut(
                    **compute_business_pentagon(s, company=c),
                )
                n_tx = (
                    s.query(CompanyTransaction)
                    .filter(CompanyTransaction.company_id == c.id)
                    .count()
                )
                invs = (
                    s.query(CompanyInvoice)
                    .filter(CompanyInvoice.company_id == c.id)
                    .all()
                )
                n_inv = len(invs)
                n_inv_unpaid = sum(1 for i in invs if i.paid_on is None)
                salaries = (
                    s.query(CompanyOwnerSalary)
                    .filter(CompanyOwnerSalary.company_id == c.id)
                    .order_by(CompanyOwnerSalary.paid_on.desc())
                    .all()
                )
                n_salary = len(salaries)
                if salaries:
                    last_salary = salaries[0].paid_on.isoformat()
                next_vat = (
                    s.query(CompanyVatPeriod)
                    .filter(
                        CompanyVatPeriod.company_id == c.id,
                        CompanyVatPeriod.filed_on.is_(None),
                    )
                    .order_by(CompanyVatPeriod.due_on.asc())
                    .first()
                )
                if next_vat is not None and next_vat.due_on is not None:
                    next_vat_due = next_vat.due_on.isoformat()

    # Sammanfattning för läraren
    if not biz_enabled:
        summary = (
            f"## {student_name} har inte aktiverat företagsläge\n\n"
            "Använd toggeln på elev-detaljvyn för att aktivera "
            "företagsläget. När det är på kan eleven bokföra, "
            "fakturera, ta ut lön och hantera moms parallellt med "
            "privatekonomin."
        )
    elif company_out is None:
        summary = (
            f"## {student_name} har inte startat något bolag än\n\n"
            "Företagsläget är aktiverat men eleven har inte registrerat "
            "ett bolag. Bjud eleven att klicka **Starta företag** på "
            "biz-hubben för att börja."
        )
    else:
        score = pentagon_out.total_score if pentagon_out else 0
        summary = (
            f"## {student_name} driver {company_out.name}\n\n"
            f"- Form: **{company_out.form}**\n"
            f"- Pentagon-score: **{score}/100**\n"
            f"- Bokförda transaktioner: {n_tx}\n"
            f"- Fakturor: {n_inv} ({n_inv_unpaid} obetalda)\n"
            f"- Löneuttag: {n_salary}\n"
            + (
                f"- Nästa moms-due: **{next_vat_due}**\n"
                if next_vat_due else ""
            )
            + (
                f"- Senaste lön: {last_salary}\n"
                if last_salary else ""
            )
        )

    return TeacherForetagOverviewOut(
        student_id=student_id,
        student_name=student_name,
        business_mode_enabled=biz_enabled,
        company=company_out,
        pentagon=pentagon_out,
        n_transactions_total=n_tx,
        n_invoices_total=n_inv,
        n_invoices_unpaid=n_inv_unpaid,
        n_owner_salaries=n_salary,
        last_owner_salary_date=last_salary,
        next_vat_due=next_vat_due,
        summary_md=summary,
    )
