"""Allabolag · klass-skopig scoreboard över alla elev-företag.

Spec: dev/feature-allabolag.md (Fas A)

Designprincip: master-DB cachar aggregat (omsättning, vinst, antal
anställda) per Company så att en query räcker för en hel klass.
Cachen uppdateras av sync_class_company_share() som anropas av
auto_tick_if_due (varje gång företaget tickas) + create_company.

Privacy: bara aggregat speglas. Aldrig transaktionslistor.
Eleven kan toggla `is_published=False` för att dölja från klassen
— läraren ser ändå alltid allt.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as SASession

from .deps import TokenInfo, require_token
from ..business.models import Company, CompanyInvoice, CompanyTransaction


log = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/allabolag", tags=["allabolag"])


# === Pydantic schemas ===

class AllabolagRow(BaseModel):
    """En rad i scoreboarden — ett klass-företag."""
    company_id_in_scope: int
    company_name: str
    industry_label: Optional[str]
    industry_key: Optional[str]
    city_key: Optional[str]
    form: str
    started_on: Optional[str]
    week_no: int
    revenue_4w: int
    profit_4w: int
    margin_pct: float
    kassa: int
    n_employees: int
    n_invoices_open: int
    n_invoices_overdue: int
    reputation: int
    annual_report_status: str
    annual_report_year: Optional[int]
    annual_report_decided_at: Optional[str]
    uc_score: int = 50
    uc_rating: str = "B"
    company_level: str = "startup"
    is_mine: bool
    is_published: bool
    owner_display_name: Optional[str]
    last_synced_at: str


class AllabolagListOut(BaseModel):
    rows: list[AllabolagRow]
    class_total_revenue_4w: int
    class_total_profit_4w: int
    n_companies: int
    n_published: int


class TogglePublishIn(BaseModel):
    is_published: bool


# === Sync helper · uppdatera cache från scope-DB ===

def _compute_uc(
    *,
    kassa: int,
    margin_pct: float,
    income_4w: int,
    n_invoices_overdue: int,
    reputation: int,
    weeks_active: int,
) -> tuple[int, str]:
    """Räkna ut företags-UC 0-100 + rating-bokstav.

    Spec: Fas G
      Likviditet (kassa/4v-snittkostnad)  30 %
      Vinstmarginal 4 v                   25 %
      Försenade fakturor (negativt)        20 %
      Rykte                                15 %
      Företagets ålder                     10 %
    """
    # Likviditet · approx-månadskostnad = expense + lön. Eftersom vi inte
    # har den direkt här tar vi income_4w som proxy: kassa relativt 4v-oms.
    base_monthly = max(1, income_4w * 0.6)  # förenklad bedömning
    liquidity_score = max(0, min(100, int(kassa / base_monthly * 50)))

    # Marginal: 0-50 → 0-100 score
    margin_score = max(0, min(100, int((margin_pct + 10) * 5)))

    # Försenade fakturor: 0 = 100, 5+ = 0
    overdue_score = max(0, min(100, 100 - n_invoices_overdue * 20))

    # Rykte direkt
    rep_score = reputation

    # Ålder: 0v = 30, 12v+ = 100
    age_score = max(30, min(100, 30 + weeks_active * 6))

    score = int(round(
        liquidity_score * 0.30
        + margin_score * 0.25
        + overdue_score * 0.20
        + rep_score * 0.15
        + age_score * 0.10
    ))
    score = max(0, min(100, score))

    if score >= 75:
        rating = "AAA"
    elif score >= 60:
        rating = "A"
    elif score >= 40:
        rating = "B"
    elif score >= 20:
        rating = "C"
    else:
        rating = "D"
    return score, rating


def _compute_level(
    *,
    income_4w: int,
    kassa: int,
    n_employees: int,
    reputation: int,
) -> str:
    """4-nivå-progression. Spec: Fas G."""
    if income_4w >= 500000 and n_employees >= 5 and reputation >= 85:
        return "marknadsledare"
    if income_4w >= 200000 and n_employees >= 3 and kassa >= 50000:
        return "etablerat"
    if income_4w >= 50000 and n_employees >= 1:
        return "vaxande"
    return "startup"


def sync_class_company_share(
    s: SASession, *,
    company: Company,
    teacher_id: int,
    student_id: int,
    class_label: Optional[str],
) -> None:
    """Uppdatera ClassCompanyShare-raden för ett företag. Idempotent.

    Kallas från:
    - auto_tick_if_due (efter varje vecko-tick)
    - create_company (initial sync)
    - file_vat / annual-report-flow (uppdatera bolagsverket-status)

    `s` är scope-DB-sessionen (där företaget bor). Vi öppnar separat
    master-session inom funktionen för att skriva cache-raden.
    """
    try:
        # Räkna fakturor + transaktioner i scope-DB
        invs = (
            s.query(CompanyInvoice)
            .filter(CompanyInvoice.company_id == company.id)
            .all()
        )
        today = date.today()
        n_open = sum(1 for i in invs if i.status == "sent")
        n_overdue = sum(
            1 for i in invs
            if i.status == "sent" and i.due_on < today
        )

        # 4-veckors-aggregat · senaste ~30 dagar
        from datetime import timedelta
        cutoff = today - timedelta(days=30)
        txs = (
            s.query(CompanyTransaction)
            .filter(
                CompanyTransaction.company_id == company.id,
                CompanyTransaction.occurred_on >= cutoff,
            )
            .all()
        )
        income = sum(
            float(t.amount_excl_vat or 0)
            for t in txs if t.kind == "income"
        )
        expense = sum(
            float(t.amount_excl_vat or 0)
            for t in txs
            if t.kind in ("expense", "salary")
        )
        profit = income - expense
        margin = (profit / income * 100.0) if income > 0 else 0.0

        # Kassa = saldo på företagskonto · approximation: alla
        # transaktioner sedan start
        all_txs = (
            s.query(CompanyTransaction)
            .filter(CompanyTransaction.company_id == company.id)
            .all()
        )
        kassa = sum(
            float(t.amount_excl_vat or 0) * (1 if t.kind == "income" else -1)
            for t in all_txs
        )
        # Plus eventuellt aktiekapital
        if company.share_capital:
            kassa += float(company.share_capital)

        # Anställda — Fas D · CompanyEmployment-räknare. Fas A: 0.
        n_employees = 0

        # Skriv master-cache
        from ..school.engines import master_session
        from ..school.models import ClassCompanyShare
        with master_session() as ms:
            row = (
                ms.query(ClassCompanyShare)
                .filter(
                    ClassCompanyShare.owner_student_id == student_id,
                    ClassCompanyShare.company_id_in_scope == company.id,
                )
                .first()
            )
            if row is None:
                row = ClassCompanyShare(
                    teacher_id=teacher_id,
                    owner_student_id=student_id,
                    class_label=class_label,
                    company_id_in_scope=company.id,
                    company_name=company.name,
                    industry_label=company.industry_label,
                    industry_key=company.industry_key,
                    city_key=company.city_key,
                    form=company.form,
                    started_on=company.started_on,
                )
                ms.add(row)
            # Uppdatera fält som kan ändras
            row.company_name = company.name
            row.industry_label = company.industry_label
            row.industry_key = company.industry_key
            row.city_key = company.city_key
            row.form = company.form
            row.started_on = company.started_on
            row.week_no = int(company.week_no or 0)
            row.revenue_4w = int(income)
            row.profit_4w = int(profit)
            row.margin_pct = round(margin, 1)
            row.kassa = int(kassa)
            row.n_employees = n_employees
            row.n_invoices_open = n_open
            row.n_invoices_overdue = n_overdue
            row.reputation = int(company.reputation or 50)

            # Fas G · företags-UC + nivå-progression
            uc_score, uc_rating = _compute_uc(
                kassa=int(kassa),
                margin_pct=margin,
                income_4w=int(income),
                n_invoices_overdue=n_overdue,
                reputation=int(company.reputation or 50),
                weeks_active=int(company.week_no or 0),
            )
            level = _compute_level(
                income_4w=int(income),
                kassa=int(kassa),
                n_employees=n_employees,
                reputation=int(company.reputation or 50),
            )
            if level != row.company_level and row.company_level:
                row.level_unlocked_at = datetime.utcnow()
            row.uc_score = uc_score
            row.uc_rating = uc_rating
            row.company_level = level

            row.last_synced_at = datetime.utcnow()
            ms.commit()
    except Exception:
        log.exception(
            "sync_class_company_share misslyckades för company=%s student=%s",
            company.id, student_id,
        )


# === Endpoints ===

@router.get("", response_model=AllabolagListOut)
def list_class_companies(info: TokenInfo = Depends(require_token)):
    """Lista alla klassens företag.

    Studenter: ser bara `is_published=True` + sitt eget företag (även
    om opublicerat). Lärare: ser ALLA företag i sin klass.
    """
    from ..school.engines import master_session
    from ..school.models import ClassCompanyShare, Student

    if info.role == "teacher" and info.teacher_id is not None:
        teacher_id = info.teacher_id
        my_student_id: Optional[int] = None
    elif info.role == "student" and info.student_id is not None:
        # Hämta lärar-id via student
        with master_session() as s:
            stu = s.get(Student, info.student_id)
            if stu is None:
                raise HTTPException(404, "Elev saknas")
            teacher_id = stu.teacher_id
            my_student_id = info.student_id
    else:
        raise HTTPException(403, "Endast lärare/elever")

    with master_session() as s:
        rows = (
            s.query(ClassCompanyShare)
            .filter(ClassCompanyShare.teacher_id == teacher_id)
            .all()
        )
        # Hämta elev-namn för att visa "Anton AB · ägare: Anton P"
        student_ids = list({r.owner_student_id for r in rows})
        students = (
            s.query(Student)
            .filter(Student.id.in_(student_ids))
            .all()
        )
        name_map = {st.id: st.display_name for st in students}

    visible: list[ClassCompanyShare] = []
    for r in rows:
        # Studenter ser sina egna + andras publicerade
        if info.role == "student":
            if r.owner_student_id != my_student_id and not r.is_published:
                continue
        visible.append(r)

    # Sortera: vinstmarginal desc, omsättning desc som tiebreak
    visible.sort(
        key=lambda r: (-r.margin_pct, -r.revenue_4w),
    )

    out_rows = [
        AllabolagRow(
            company_id_in_scope=r.company_id_in_scope,
            company_name=r.company_name,
            industry_label=r.industry_label,
            industry_key=r.industry_key,
            city_key=r.city_key,
            form=r.form,
            started_on=r.started_on.isoformat() if r.started_on else None,
            week_no=r.week_no,
            revenue_4w=r.revenue_4w,
            profit_4w=r.profit_4w,
            margin_pct=r.margin_pct,
            kassa=r.kassa,
            n_employees=r.n_employees,
            n_invoices_open=r.n_invoices_open,
            n_invoices_overdue=r.n_invoices_overdue,
            reputation=r.reputation,
            annual_report_status=r.annual_report_status,
            annual_report_year=r.annual_report_year,
            annual_report_decided_at=(
                r.annual_report_decided_at.isoformat()
                if r.annual_report_decided_at else None
            ),
            uc_score=r.uc_score,
            uc_rating=r.uc_rating,
            company_level=r.company_level,
            is_mine=(r.owner_student_id == my_student_id),
            is_published=r.is_published,
            owner_display_name=name_map.get(r.owner_student_id),
            last_synced_at=r.last_synced_at.isoformat(),
        )
        for r in visible
    ]
    return AllabolagListOut(
        rows=out_rows,
        class_total_revenue_4w=sum(r.revenue_4w for r in out_rows),
        class_total_profit_4w=sum(r.profit_4w for r in out_rows),
        n_companies=len(rows),
        n_published=sum(1 for r in rows if r.is_published),
    )


@router.post("/publish", response_model=dict)
def toggle_publish(
    body: TogglePublishIn,
    info: TokenInfo = Depends(require_token),
):
    """Eleven togglar om sitt företag visas på Allabolag för
    klasskompisar. Lärare ser alltid alla."""
    if info.role != "student" or info.student_id is None:
        raise HTTPException(403, "Endast elever kan toggla sitt företag")
    from ..school.engines import master_session
    from ..school.models import ClassCompanyShare
    with master_session() as s:
        rows = (
            s.query(ClassCompanyShare)
            .filter(ClassCompanyShare.owner_student_id == info.student_id)
            .all()
        )
        if not rows:
            raise HTTPException(404, "Du har inget företag att publicera")
        for r in rows:
            r.is_published = body.is_published
        s.commit()
    return {"is_published": body.is_published, "n_updated": len(rows)}
