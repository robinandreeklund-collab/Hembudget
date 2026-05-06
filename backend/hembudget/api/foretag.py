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
from typing import Optional

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
    active: bool


class CompanyIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    form: str = Field(default="enskild_firma")
    org_number: Optional[str] = None
    sni_code: Optional[str] = None
    industry_label: Optional[str] = None
    vat_registered: bool = False
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


# === Endpoints: Company ===


@router.get("", response_model=Optional[CompanyOut])
def get_company(info: TokenInfo = Depends(require_token)):
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        return _to_company_out(c) if c else None


@router.post("", response_model=CompanyOut)
def create_company(
    body: CompanyIn,
    info: TokenInfo = Depends(require_token),
):
    _require_student(info)
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
            sni_code=body.sni_code,
            industry_label=body.industry_label,
        )
        s.add(c)
        s.flush()
        return _to_company_out(c)


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
        return _invoice_to_out(inv, cust.name)


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
        return _invoice_to_out(inv, cust.name if cust else "?")


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
        return OwnerSalaryOut(
            id=row.id,
            paid_on=row.paid_on.isoformat(),
            gross_salary=float(row.gross_salary),
            employer_fee_amount=float(row.employer_fee_amount),
            prel_tax_amount=float(row.prel_tax_amount),
            net_to_owner=float(row.net_to_owner),
            total_cost_to_company=float(row.total_cost_to_company),
        )


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
        return VatPeriodOut(
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
    """Läraren aktiverar/avaktiverar företagsläget för en elev."""
    if info.role != "teacher" or info.teacher_id is None:
        raise HTTPException(403, "Endast lärare")
    from ..school.engines import master_session
    from ..school.models import Student
    with master_session() as ms:
        stu = ms.get(Student, student_id)
        if stu is None or stu.teacher_id != info.teacher_id:
            raise HTTPException(404, "Elev saknas")
        stu.business_mode_enabled = body.enabled
        ms.commit()
    return BusinessModeStatusOut(
        enabled=body.enabled,
        has_active_company=False,
    )


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
