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

        # Kassa = kanonisk helper · samma som Hub/Tillväxt visar.
        from ..business.cash import compute_company_cash as _ccc
        kassa = float(_ccc(s, company))

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

    # Self-heal: om eleven har ett aktivt bolag i sin scope-DB men ingen
    # ClassCompanyShare-rad i master, kör en sync så raden skapas innan
    # vi listar. Fångar fall där create_company-syncen failade tyst
    # (rörlig prod-Postgres, master-migration som inte körts än, etc.).
    if info.role == "student" and my_student_id is not None:
        try:
            from ..business.models import Company as _Co
            from ..db.base import session_scope as _scsc
            with master_session() as ms_pre:
                existing_share = (
                    ms_pre.query(ClassCompanyShare.id)
                    .filter(
                        ClassCompanyShare.owner_student_id == my_student_id,
                    )
                    .first()
                )
            if existing_share is None:
                with _scsc() as scope_s:
                    co = (
                        scope_s.query(_Co)
                        .filter(_Co.active.is_(True))
                        .first()
                    )
                    if co is not None:
                        with master_session() as ms_pre2:
                            stu = ms_pre2.get(Student, my_student_id)
                            class_label = (
                                stu.class_label if stu else None
                            )
                        sync_class_company_share(
                            scope_s,
                            company=co,
                            teacher_id=teacher_id,
                            student_id=my_student_id,
                            class_label=class_label,
                        )
        except Exception:
            log.exception(
                "list_class_companies: lazy-sync misslyckades för "
                "student=%s — fortsätter med befintliga rader",
                my_student_id,
            )

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
        key=lambda r: (
            -(getattr(r, "margin_pct", 0.0) or 0.0),
            -(getattr(r, "revenue_4w", 0) or 0),
        ),
    )

    # Defensiv läsning: om en migration inte kört på prod kan ett fält
    # vara None/saknas. getattr+default skyddar mot 500 så Allabolag visas
    # även med ofullständig schema (dvs. nya kolumner ofyllda).
    def _row(r: ClassCompanyShare) -> AllabolagRow:
        ar_decided = getattr(r, "annual_report_decided_at", None)
        last_synced = getattr(r, "last_synced_at", None)
        return AllabolagRow(
            company_id_in_scope=r.company_id_in_scope,
            company_name=r.company_name,
            industry_label=r.industry_label,
            industry_key=r.industry_key,
            city_key=getattr(r, "city_key", None),
            form=r.form,
            started_on=r.started_on.isoformat() if r.started_on else None,
            week_no=getattr(r, "week_no", 0) or 0,
            revenue_4w=getattr(r, "revenue_4w", 0) or 0,
            profit_4w=getattr(r, "profit_4w", 0) or 0,
            margin_pct=getattr(r, "margin_pct", 0.0) or 0.0,
            kassa=getattr(r, "kassa", 0) or 0,
            n_employees=getattr(r, "n_employees", 0) or 0,
            n_invoices_open=getattr(r, "n_invoices_open", 0) or 0,
            n_invoices_overdue=getattr(r, "n_invoices_overdue", 0) or 0,
            reputation=getattr(r, "reputation", 50) or 50,
            annual_report_status=getattr(
                r, "annual_report_status", "not_due",
            ) or "not_due",
            annual_report_year=getattr(r, "annual_report_year", None),
            annual_report_decided_at=(
                ar_decided.isoformat() if ar_decided else None
            ),
            uc_score=getattr(r, "uc_score", 50) or 50,
            uc_rating=getattr(r, "uc_rating", "B") or "B",
            company_level=getattr(r, "company_level", "startup") or "startup",
            is_mine=(r.owner_student_id == my_student_id),
            is_published=getattr(r, "is_published", True),
            owner_display_name=name_map.get(r.owner_student_id),
            last_synced_at=(
                last_synced.isoformat() if last_synced
                else datetime.utcnow().isoformat()
            ),
        )
    out_rows = [_row(r) for r in visible]
    return AllabolagListOut(
        rows=out_rows,
        class_total_revenue_4w=sum(r.revenue_4w for r in out_rows),
        class_total_profit_4w=sum(r.profit_4w for r in out_rows),
        n_companies=len(rows),
        n_published=sum(1 for r in rows if getattr(r, "is_published", True)),
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


# === Detail-vy · Allabolag-style företagsprofil ===

class HistoryPoint(BaseModel):
    label: str
    revenue: int
    profit_after_finance: int


class NyckeltalItem(BaseModel):
    pct: float
    label: str  # "Mycket bra" / "Tillfredsst." / "Svag"
    prev_pct: Optional[float] = None
    direction: str = "flat"  # "up" / "down" / "flat"


class AllabolagDetailOut(BaseModel):
    """Detaljerad företagsprofil — efterliknar allabolag.se-layouten
    med spelets data. Visas när eleven klickar på en rad i scoreboarden.
    """
    # Identitet
    company_id: int
    name: str
    org_number: str
    form: str
    started_on: Optional[str]
    sni_code: Optional[str]
    sni_label: str
    industry_label: Optional[str]
    industry_key: Optional[str]
    city_key: Optional[str]
    city_display: str
    address: str
    ledamot: Optional[str]
    is_mine: bool
    is_published: bool

    # Översikt-rad
    revenue_period: int
    profit_after_finance: int
    ebitda: int
    registreringsar: int
    n_employees: int
    share_capital: Optional[int]

    # Bokslut-sidebar
    bokslut_label: str
    omsattning: int
    resultat_efter_finansnetto: int
    arets_resultat: int
    summa_tillgangar: int
    eget_kapital: int

    # Period-historik (för stapeldiagram)
    history: list[HistoryPoint]

    # Nyckeltal
    kassalikviditet: NyckeltalItem
    vinstmarginal: NyckeltalItem
    soliditet: NyckeltalItem

    # Officiell info
    verksamhet_text: str
    vat_registered: bool
    f_skatt: bool
    arbetsgivaravgift: bool
    status_label: str

    last_synced_at: str


# Synthetic address-data per city. Pedagogiskt ok — eleven förstår att
# det är simulerat, men det matchar allabolag.se-layouten.
_CITY_DISPLAY = {
    "stockholm": ("Stockholm", "111 22"),
    "goteborg": ("Göteborg", "411 02"),
    "malmo": ("Malmö", "211 18"),
    "uppsala": ("Uppsala", "753 20"),
    "vasteras": ("Västerås", "722 12"),
    "orebro": ("Örebro", "702 10"),
    "linkoping": ("Linköping", "582 17"),
    "helsingborg": ("Helsingborg", "252 21"),
    "norrkoping": ("Norrköping", "602 21"),
    "jonkoping": ("Jönköping", "553 16"),
    "umea": ("Umeå", "903 30"),
    "lund": ("Lund", "222 21"),
    "boras": ("Borås", "503 30"),
    "sundsvall": ("Sundsvall", "852 29"),
    "eskilstuna": ("Eskilstuna", "632 18"),
    "halmstad": ("Halmstad", "302 41"),
    "vaxjo": ("Växjö", "352 30"),
    "karlstad": ("Karlstad", "652 24"),
}

_STREETS = (
    "Storgatan", "Drottninggatan", "Kungsgatan", "Vasagatan",
    "Klarabergsgatan", "Sveavägen", "Hamngatan", "Industrivägen",
)

_SNI_LABELS = {
    "snickare": ("43320", "Byggnadssnickeriarbeten"),
    "elektriker": ("43210", "Elinstallationer"),
    "rormokare": ("43221", "VS-installationer"),
    "fotograf": ("74201", "Fotografverksamhet"),
    "catering": ("56210", "Cateringverksamhet"),
    "frisor": ("96021", "Hårvård"),
    "konsult": ("70220", "Konsultverksamhet · företagsorg."),
    "designer": ("74100", "Specialiserad designverksamhet"),
    "tradgardsmastare": ("81300", "Skötsel och underhåll av grönytor"),
    "stadning": ("81210", "Lokalvård"),
}


def _synth_address(co: Company) -> tuple[str, str, str]:
    """Returnerar (display_address, city_display, postnr) deterministiskt
    från company-id + city_key. Endast för UI-presentation."""
    city_key = (co.city_key or "stockholm").lower()
    city_display, postnr = _CITY_DISPLAY.get(
        city_key, (city_key.title(), "100 00"),
    )
    street = _STREETS[co.id % len(_STREETS)]
    house_no = (co.id * 7) % 99 + 1
    address = f"{street} {house_no}, {postnr} {city_display}"
    return address, city_display, postnr


def _synth_org_number(co: Company) -> str:
    """org.nr 556xxx-xxxx · 10 siffror för AB, deterministiskt från id."""
    if co.org_number:
        return co.org_number
    base = 556000_0000 + (co.id * 99991) % 999_9999
    s = str(base)
    return f"{s[:6]}-{s[6:]}"


def _verksamhet_text(co: Company) -> str:
    """Generera 'Föremål för bolagets verksamhet' baserat på industry."""
    label = (co.industry_label or co.industry_key or "verksamhet").lower()
    if co.business_idea:
        return co.business_idea
    return (
        f"Föremålet för bolagets verksamhet är att verka inom {label} "
        "och därmed förenlig verksamhet."
    )


def _label_for_kassalikviditet(pct: float) -> str:
    if pct >= 100: return "Mycket bra"
    if pct >= 75: return "Tillfredsst."
    if pct >= 50: return "Svag"
    return "Otillfredsst."


def _label_for_vinstmarginal(pct: float) -> str:
    if pct >= 10: return "Mycket bra"
    if pct >= 5: return "Tillfredsst."
    if pct >= 0: return "Svag"
    return "Förlust"


def _label_for_soliditet(pct: float) -> str:
    if pct >= 40: return "Mycket bra"
    if pct >= 25: return "Tillfredsst."
    if pct >= 10: return "Svag"
    return "Otillfredsst."


def _direction(curr: float, prev: Optional[float]) -> str:
    if prev is None:
        return "flat"
    if curr > prev + 0.5: return "up"
    if curr < prev - 0.5: return "down"
    return "flat"


@router.get("/{company_id}/detail", response_model=AllabolagDetailOut)
def company_detail(
    company_id: int,
    info: TokenInfo = Depends(require_token),
):
    """Detaljerad företagsprofil — lik allabolag.se-layouten med
    spelets data. Visas när användaren klickar på en rad i scoreboard.

    Auth: ägaren ser alltid sitt eget. Andra elever ser bara
    publicerade företag. Lärare ser alla i sin klass.
    """
    from ..school.engines import (
        master_session, scope_context, scope_for_student,
    )
    from ..school.models import ClassCompanyShare, Student
    from ..db.base import session_scope as _session_scope
    from ..business.models import (
        SupplierInvoice as _SI,
    )

    # Lokalisera ClassCompanyShare i master + auth
    if info.role == "teacher" and info.teacher_id is not None:
        teacher_id = info.teacher_id
        my_student_id: Optional[int] = None
    elif info.role == "student" and info.student_id is not None:
        with master_session() as s:
            stu = s.get(Student, info.student_id)
            if stu is None:
                raise HTTPException(404, "Elev saknas")
            teacher_id = stu.teacher_id
            my_student_id = info.student_id
    else:
        raise HTTPException(403, "Endast lärare/elever")

    with master_session() as s:
        share = (
            s.query(ClassCompanyShare)
            .filter(
                ClassCompanyShare.company_id_in_scope == company_id,
                ClassCompanyShare.teacher_id == teacher_id,
            )
            .first()
        )
        if share is None:
            raise HTTPException(404, "Företag saknas")
        owner_id = share.owner_student_id
        is_mine = (owner_id == my_student_id)
        if info.role == "student" and not is_mine and not share.is_published:
            raise HTTPException(403, "Företaget är inte publicerat")
        owner_stu = s.get(Student, owner_id)
        owner_name = owner_stu.display_name if owner_stu else None
        last_synced = (
            share.last_synced_at.isoformat()
            if share.last_synced_at else datetime.utcnow().isoformat()
        )

    # Öppna ägarens scope-DB för att hämta Company + transaktioner
    if owner_stu is None:
        raise HTTPException(404, "Ägare saknas")
    scope_key = scope_for_student(owner_stu)
    with scope_context(scope_key):
        with _session_scope() as ss:
            co = (
                ss.query(Company)
                .filter(Company.id == company_id)
                .first()
            )
            if co is None:
                raise HTTPException(404, "Företag saknas i scope")

            txs = (
                ss.query(CompanyTransaction)
                .filter(CompanyTransaction.company_id == co.id)
                .all()
            )
            # Outstanding kundfordringar (sent, ej paid)
            outstanding_recv = sum(
                int(i.amount_excl_vat or 0) + int(i.vat_amount or 0)
                for i in ss.query(CompanyInvoice)
                .filter(
                    CompanyInvoice.company_id == co.id,
                    CompanyInvoice.status == "sent",
                ).all()
            )
            # Outstanding leverantörsskulder
            outstanding_pay = sum(
                int(i.amount_excl_vat or 0)
                for i in ss.query(_SI)
                .filter(
                    _SI.company_id == co.id,
                    _SI.status == "open",
                ).all()
            )

            # Bucket-aggregat per spel-vecka
            from collections import defaultdict
            by_week: dict[int, dict] = defaultdict(
                lambda: {"income": 0, "expense": 0}
            )
            from datetime import date as _date
            min_d = co.started_on or _date.today()
            for t in txs:
                if t.occurred_on is None:
                    continue
                week_idx = max(
                    0, (t.occurred_on - min_d).days // 7
                )
                amt = int(float(t.amount_excl_vat or 0))
                if t.kind == "income":
                    by_week[week_idx]["income"] += amt
                elif t.kind in ("expense", "salary", "vat_payment",
                                "tax_payment", "asset_purchase"):
                    by_week[week_idx]["expense"] += amt

            # Historik · gruppera till "perioder" om 4 veckor (lättare
            # att läsa än en stapel per vecka). Ta sista 5 perioderna
            # för stapeldiagram-design.
            max_week = max(by_week.keys(), default=0)
            n_periods = max(1, max_week // 4 + 1)
            period_data: list[dict] = []
            for p in range(n_periods):
                p_inc = sum(
                    by_week[w]["income"] for w in range(p * 4, p * 4 + 4)
                )
                p_exp = sum(
                    by_week[w]["expense"] for w in range(p * 4, p * 4 + 4)
                )
                period_data.append({
                    "label": f"P{p + 1}",
                    "income": p_inc,
                    "expense": p_exp,
                })
            history = [
                HistoryPoint(
                    label=p["label"],
                    revenue=p["income"],
                    profit_after_finance=p["income"] - p["expense"],
                )
                for p in period_data[-5:]
            ]

            # Aktuell period (senaste 4 veckorna) ===
            curr_inc = sum(
                by_week[w]["income"]
                for w in range(max(0, max_week - 3), max_week + 1)
            )
            curr_exp = sum(
                by_week[w]["expense"]
                for w in range(max(0, max_week - 3), max_week + 1)
            )
            curr_profit = curr_inc - curr_exp

            # Föregående period · för YoY-direction-pilar
            prev_inc = sum(
                by_week[w]["income"]
                for w in range(max(0, max_week - 7), max(0, max_week - 3))
            )
            prev_exp = sum(
                by_week[w]["expense"]
                for w in range(max(0, max_week - 7), max(0, max_week - 3))
            )

            # Kassa
            from ..business.cash import compute_company_cash as _ccc
            kassa = int(_ccc(ss, co))

            # Balansräkning · förenklad
            share_cap = int(co.share_capital or 0)
            summa_tillgangar = max(0, kassa) + outstanding_recv + share_cap
            eget_kapital = max(0, kassa) + share_cap - outstanding_pay

            # Nyckeltal · approximationer för pedagogiskt visa logiken
            # Kassalikviditet = (kassa + kundfordringar) / kortfristiga
            # skulder × 100. När skulder = 0 visar vi 999 (capped).
            kortfristiga = max(1, outstanding_pay)
            kassalik_pct = round(
                (kassa + outstanding_recv) / kortfristiga * 100.0, 1,
            )
            kassalik_pct = min(kassalik_pct, 999.0)

            vinstmarginal_pct = round(
                (curr_profit / curr_inc * 100.0) if curr_inc > 0 else 0.0, 1,
            )
            soliditet_pct = round(
                (eget_kapital / summa_tillgangar * 100.0)
                if summa_tillgangar > 0 else 0.0, 1,
            )

            # Föregående periodens nyckeltal · för pilarna
            prev_profit = prev_inc - prev_exp
            prev_vm = round(
                (prev_profit / prev_inc * 100.0) if prev_inc > 0 else 0.0,
                1,
            ) if prev_inc > 0 else None

            sni_default = _SNI_LABELS.get(
                co.industry_key or "", (None, "Övrig verksamhet"),
            )
            sni_code = co.sni_code or sni_default[0]
            sni_label = sni_default[1]

            address, city_display, _postnr = _synth_address(co)
            registreringsar = (
                co.started_on.year if co.started_on
                else datetime.utcnow().year
            )

            # Kvalificera AB-status
            f_skatt = True   # Alla bolag i spelet är F-skatt-aktiverade
            arbetsg = (
                getattr(share, "n_employees", 0) or 0
            ) > 0 or co.delivery_capacity > 1

            return AllabolagDetailOut(
                company_id=co.id,
                name=co.name,
                org_number=_synth_org_number(co),
                form=co.form,
                started_on=co.started_on.isoformat() if co.started_on else None,
                sni_code=sni_code,
                sni_label=sni_label,
                industry_label=co.industry_label,
                industry_key=co.industry_key,
                city_key=co.city_key,
                city_display=city_display,
                address=address,
                ledamot=owner_name,
                is_mine=is_mine,
                is_published=bool(getattr(share, "is_published", True)),

                revenue_period=curr_inc,
                profit_after_finance=curr_profit,
                ebitda=curr_profit,  # Approx · ingen ränta/avskrivning-split
                registreringsar=registreringsar,
                n_employees=getattr(share, "n_employees", 0) or 0,
                share_capital=co.share_capital,

                bokslut_label=f"Vecka {co.week_no}",
                omsattning=curr_inc,
                resultat_efter_finansnetto=curr_profit,
                arets_resultat=curr_profit,
                summa_tillgangar=summa_tillgangar,
                eget_kapital=eget_kapital,

                history=history,

                kassalikviditet=NyckeltalItem(
                    pct=kassalik_pct,
                    label=_label_for_kassalikviditet(kassalik_pct),
                    prev_pct=None,
                    direction="flat",
                ),
                vinstmarginal=NyckeltalItem(
                    pct=vinstmarginal_pct,
                    label=_label_for_vinstmarginal(vinstmarginal_pct),
                    prev_pct=prev_vm,
                    direction=_direction(vinstmarginal_pct, prev_vm),
                ),
                soliditet=NyckeltalItem(
                    pct=soliditet_pct,
                    label=_label_for_soliditet(soliditet_pct),
                    prev_pct=None,
                    direction="flat",
                ),

                verksamhet_text=_verksamhet_text(co),
                vat_registered=bool(co.vat_registered),
                f_skatt=f_skatt,
                arbetsgivaravgift=arbetsg,
                status_label="Aktiv" if co.active else "Avslutad",

                last_synced_at=last_synced,
            )
