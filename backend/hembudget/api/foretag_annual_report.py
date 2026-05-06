"""Årsredovisning-flöde · AI Bolagsverket-granskning.

Spec: dev/feature-allabolag.md (Fas B)

Eleven samlar transaktioner under året, klickar "Lämna in årsbokslutet"
→ AI Bolagsverket granskar → approved/rejected. Approved =
ClassCompanyShare.annual_report_status uppdateras + syns på Allabolag.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .deps import TokenInfo, require_token
from ..business.models import (
    Company,
    CompanyAnnualReport,
    CompanyInvoice,
    CompanyOwnerSalary,
    CompanyTransaction,
)
from ..db.base import session_scope


log = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/foretag/annual-report", tags=["allabolag"])


def _require_student(info: TokenInfo) -> int:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(403, "Endast elever")
    return info.student_id


def _get_active_company(s) -> Optional[Company]:
    return s.query(Company).filter(Company.active.is_(True)).first()


# === Schemas ===

class AnnualReportSnapshot(BaseModel):
    fiscal_year: int
    revenue_total: int
    expense_total: int
    salary_total: int
    profit_before_tax: int
    corporate_tax: int
    profit_after_tax: int
    equity_end: int
    n_invoices_paid: int
    n_invoices_unpaid: int


class AnnualReportOut(BaseModel):
    id: Optional[int]
    fiscal_year: int
    status: str
    snapshot: AnnualReportSnapshot
    student_note: Optional[str]
    ai_decision: Optional[str]
    ai_feedback_md: Optional[str]
    ai_issues: list[dict]
    submitted_at: Optional[str]
    decided_at: Optional[str]


class AnnualReportSubmitIn(BaseModel):
    fiscal_year: int = Field(..., ge=2000, le=2100)
    student_note: Optional[str] = Field(default=None, max_length=2000)


# === Helper: bygg snapshot från scope-data ===

def _build_snapshot(s, company: Company, fiscal_year: int) -> AnnualReportSnapshot:
    """Aggregera transaktioner + lön + fakturor för bokslutsåret."""
    start = date(fiscal_year, 1, 1)
    end = date(fiscal_year, 12, 31)

    txs = (
        s.query(CompanyTransaction)
        .filter(
            CompanyTransaction.company_id == company.id,
            CompanyTransaction.occurred_on >= start,
            CompanyTransaction.occurred_on <= end,
        )
        .all()
    )
    revenue = int(sum(
        float(t.amount_excl_vat or 0) for t in txs if t.kind == "income"
    ))
    expense = int(sum(
        float(t.amount_excl_vat or 0)
        for t in txs if t.kind == "expense"
    ))
    salary = int(sum(
        float(t.amount_excl_vat or 0)
        for t in txs if t.kind == "salary"
    ))

    # Owner salaries (AB-form) räknas inte som expense ovan utan har
    # egen tabell — men de ingår i lön-total ovan om bokförda som "salary"
    profit_before_tax = revenue - expense - salary

    # Bolagsskatt 20.6% på positiv vinst (förenklad)
    corporate_tax = int(round(profit_before_tax * 0.206)) if profit_before_tax > 0 else 0
    profit_after_tax = profit_before_tax - corporate_tax

    equity_end = int(company.share_capital or 0) + profit_after_tax

    invs = (
        s.query(CompanyInvoice)
        .filter(
            CompanyInvoice.company_id == company.id,
            CompanyInvoice.issued_on >= start,
            CompanyInvoice.issued_on <= end,
        )
        .all()
    )
    n_paid = sum(1 for i in invs if i.status == "paid")
    n_unpaid = sum(1 for i in invs if i.status != "paid")

    return AnnualReportSnapshot(
        fiscal_year=fiscal_year,
        revenue_total=revenue,
        expense_total=expense,
        salary_total=salary,
        profit_before_tax=profit_before_tax,
        corporate_tax=corporate_tax,
        profit_after_tax=profit_after_tax,
        equity_end=equity_end,
        n_invoices_paid=n_paid,
        n_invoices_unpaid=n_unpaid,
    )


def _to_out(row: CompanyAnnualReport) -> AnnualReportOut:
    return AnnualReportOut(
        id=row.id,
        fiscal_year=row.fiscal_year,
        status=row.status,
        snapshot=AnnualReportSnapshot(
            fiscal_year=row.fiscal_year,
            revenue_total=row.revenue_total,
            expense_total=row.expense_total,
            salary_total=row.salary_total,
            profit_before_tax=row.profit_before_tax,
            corporate_tax=row.corporate_tax,
            profit_after_tax=row.profit_after_tax,
            equity_end=row.equity_end,
            n_invoices_paid=row.n_invoices_paid,
            n_invoices_unpaid=row.n_invoices_unpaid,
        ),
        student_note=row.student_note,
        ai_decision=row.ai_decision,
        ai_feedback_md=row.ai_feedback_md,
        ai_issues=row.ai_issues or [],
        submitted_at=row.submitted_at.isoformat() if row.submitted_at else None,
        decided_at=row.decided_at.isoformat() if row.decided_at else None,
    )


# === Endpoints ===

@router.get("/preview", response_model=AnnualReportSnapshot)
def preview_annual_report(
    fiscal_year: Optional[int] = None,
    info: TokenInfo = Depends(require_token),
):
    """Visa förhandsvisning av årsbokslut INNAN inlämning. Eleven ser
    siffrorna och kan dubbelkolla mot bokföringen."""
    _require_student(info)
    year = fiscal_year or date.today().year
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Inget aktivt bolag")
        return _build_snapshot(s, c, year)


@router.get("", response_model=list[AnnualReportOut])
def list_annual_reports(info: TokenInfo = Depends(require_token)):
    """Lista alla bolagets årsredovisningar (historik)."""
    _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            return []
        rows = (
            s.query(CompanyAnnualReport)
            .filter(CompanyAnnualReport.company_id == c.id)
            .order_by(CompanyAnnualReport.fiscal_year.desc())
            .all()
        )
        return [_to_out(r) for r in rows]


@router.post("/submit", response_model=AnnualReportOut)
def submit_annual_report(
    body: AnnualReportSubmitIn,
    info: TokenInfo = Depends(require_token),
):
    """Skicka in årsredovisning till AI Bolagsverket.

    Steg:
    1. Bygg snapshot från scope-data
    2. Skapa eller uppdatera CompanyAnnualReport-rad (status=submitted)
    3. Anropa AI för granskning
    4. Sätt status=approved/rejected baserat på AI-svar
    5. Uppdatera ClassCompanyShare så Allabolag visar status
    6. Returnera resultatet
    """
    student_id = _require_student(info)
    teacher_id = info.teacher_id
    if teacher_id is None:
        from ..school.engines import master_session
        from ..school.models import Student
        with master_session() as ms:
            stu = ms.get(Student, student_id)
            if stu is not None:
                teacher_id = stu.teacher_id

    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Inget aktivt bolag")

        # Block: inte tillåtet att skicka in nuvarande år (måste vara
        # kalenderår som är slut)
        today = date.today()
        if body.fiscal_year >= today.year:
            raise HTTPException(
                400,
                f"Du kan bara lämna in årsbokslut för år som är slut. "
                f"Bolagsår {body.fiscal_year} är inte avslutat än.",
            )

        snap = _build_snapshot(s, c, body.fiscal_year)

        # Hämta eller skapa raden
        row = (
            s.query(CompanyAnnualReport)
            .filter(
                CompanyAnnualReport.company_id == c.id,
                CompanyAnnualReport.fiscal_year == body.fiscal_year,
            )
            .first()
        )
        if row is None:
            row = CompanyAnnualReport(
                company_id=c.id,
                fiscal_year=body.fiscal_year,
            )
            s.add(row)
        # Approved-rader är låsta (kan inte skicka in på nytt)
        if row.status == "approved":
            raise HTTPException(
                409,
                f"Årsbokslutet för {body.fiscal_year} är redan godkänt.",
            )

        # Skriv över snapshot vid varje submit (ev. nya transaktioner
        # sedan senaste försök)
        row.revenue_total = snap.revenue_total
        row.expense_total = snap.expense_total
        row.salary_total = snap.salary_total
        row.profit_before_tax = snap.profit_before_tax
        row.corporate_tax = snap.corporate_tax
        row.profit_after_tax = snap.profit_after_tax
        row.equity_end = snap.equity_end
        row.n_invoices_paid = snap.n_invoices_paid
        row.n_invoices_unpaid = snap.n_invoices_unpaid
        row.student_note = body.student_note
        row.status = "submitted"
        row.submitted_at = datetime.utcnow()
        s.flush()

        # AI-granskning
        from ..business.ai import review_annual_report
        ai_result = review_annual_report(
            fiscal_year=snap.fiscal_year,
            revenue_total=snap.revenue_total,
            expense_total=snap.expense_total,
            salary_total=snap.salary_total,
            profit_before_tax=snap.profit_before_tax,
            corporate_tax=snap.corporate_tax,
            profit_after_tax=snap.profit_after_tax,
            equity_end=snap.equity_end,
            n_invoices_paid=snap.n_invoices_paid,
            n_invoices_unpaid=snap.n_invoices_unpaid,
            student_note=body.student_note,
            teacher_id=teacher_id,
        )

        if ai_result is None:
            # Fallback: deterministisk approval om aritmetiken stämmer
            arith_ok = (
                abs(
                    snap.profit_before_tax
                    - (snap.revenue_total - snap.expense_total - snap.salary_total)
                ) <= 5
            )
            if arith_ok:
                row.ai_decision = "approved"
                row.ai_feedback_md = (
                    "Bolagsverket godkänner årsredovisningen "
                    "(automatisk granskning · AI tillfälligt otillgänglig)."
                )
                row.ai_issues = []
                row.status = "approved"
            else:
                row.ai_decision = "rejected"
                row.ai_feedback_md = (
                    "Resultatet stämmer inte aritmetiskt. "
                    "Kontrollera intäkter − kostnader − lön = vinst före skatt."
                )
                row.ai_issues = [{
                    "category": "aritmetik",
                    "explanation": "Resultaträkningen går inte ihop.",
                }]
                row.status = "rejected"
        else:
            row.ai_decision = ai_result["decision"]
            row.ai_feedback_md = ai_result["feedback_md"]
            row.ai_issues = ai_result["issues"]
            row.status = ai_result["decision"]

        row.decided_at = datetime.utcnow()
        s.flush()

        # Sync till master-DB · uppdatera Allabolag-status
        try:
            from ..school.engines import master_session
            from ..school.models import ClassCompanyShare
            with master_session() as ms:
                share = (
                    ms.query(ClassCompanyShare)
                    .filter(
                        ClassCompanyShare.owner_student_id == student_id,
                        ClassCompanyShare.company_id_in_scope == c.id,
                    )
                    .first()
                )
                if share is not None:
                    share.annual_report_status = row.status
                    share.annual_report_year = body.fiscal_year
                    share.annual_report_decided_at = row.decided_at
                    ms.commit()
        except Exception:
            log.exception(
                "submit_annual_report: kunde inte sync:a till Allabolag",
            )

        # Lärar-spårning
        try:
            from ..school.activity import log_activity
            log_activity(
                kind=(
                    f"biz.annual_report_{row.status}"
                ),
                summary=(
                    f"Årsbokslut {body.fiscal_year} "
                    f"{'godkänt av' if row.status == 'approved' else 'återsänt av'} "
                    "AI Bolagsverket · "
                    f"vinst {snap.profit_after_tax} kr"
                ),
                payload={
                    "fiscal_year": body.fiscal_year,
                    "decision": row.ai_decision,
                    "revenue": snap.revenue_total,
                    "profit": snap.profit_after_tax,
                },
            )
        except Exception:
            pass

        return _to_out(row)
