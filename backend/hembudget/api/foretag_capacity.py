"""Tids-kapacitet · breakdown av timmar per vecka + tier-prediktion.

Spec: Fas K · dev/feature-allabolag.md

Modell:
  Ägaren:            84 h produktiv tid/v (entreprenörens egna timmar
                     — inkl. kvällar/helger som man som egenföretagare
                     ofta jobbar utöver dagjobbet)
  Privat-jobb äter:  weekly_hours_employed (default 40 = heltidsjobb)
  Anställda ger:     +40 h/heltidsanställd (svensk lagstadgad arbetstid)
  MCP-frilans ger:   +40 h om aktiv (heltidsfrilansare 1 v)

Tiers:
  T0 ≤ 100% kapacitet · ingen påföljd
  T1 101-130%         · stressig vecka, 5% delay-risk
  T2 131-180%         · överbelastad, 25% delay-risk
  T3 > 180%           · burnout-zon, 50% delay-risk + sjuk
  T4 (T3 i 4+ v rakt) · krasch · capacity 0 i 1 v
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel


from .deps import TokenInfo, require_token
from ..business.game_clock import current_game_date
from ..business.models import (
    Company, CompanyMcpRental, Job,
)
from ..db.base import session_scope


log = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/foretag/capacity", tags=["foretag-capacity"])


# Konfig
PRODUCTIVE_HOURS_PER_PERSON_WEEK = 84.0  # ägaren · inkl. kvällar/helger
EMPLOYEE_HOURS_PER_WEEK = 40.0  # heltid · svensk lagstadgad arbetstid
MCP_HOURS_PER_WEEK = 40.0  # frilans · 1 v heltid


def _require_student(info: TokenInfo) -> int:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(403, "Endast elever")
    return info.student_id


def _get_active_company(s) -> Optional[Company]:
    return s.query(Company).filter(Company.active.is_(True)).first()


def _classify_tier(overload_ratio: float, weeks_overloaded: int) -> int:
    """Returnera tier 0-4 baserat på ratio + historik."""
    if overload_ratio <= 1.0:
        return 0
    if overload_ratio <= 1.3:
        return 1
    if overload_ratio <= 1.8:
        return 2
    # >1.8
    if weeks_overloaded >= 4:
        return 4
    return 3


TIER_INFO = {
    0: {
        "label": "På marginalen",
        "color": "#6ee7b7",
        "desc": "Du har god kontroll över arbetsbördan.",
        "delay_risk_pct": 0,
        "health_per_week": 0,
        "safety_per_week": 0,
    },
    1: {
        "label": "Stressig vecka",
        "color": "#fbbf24",
        "desc": "Lite press, men hanterbart om det inte blir rutin.",
        "delay_risk_pct": 5,
        "health_per_week": -3,
        "safety_per_week": 0,
    },
    2: {
        "label": "Överbelastad",
        "color": "#fb923c",
        "desc": "Tydlig stress · kvalitet sjunker · kunder börjar märka.",
        "delay_risk_pct": 25,
        "health_per_week": -8,
        "safety_per_week": -2,
    },
    3: {
        "label": "Burnout-zon",
        "color": "#dc4c2b",
        "desc": "Akut · risk för varaktiga skador på rykte och hälsa.",
        "delay_risk_pct": 50,
        "health_per_week": -15,
        "safety_per_week": -5,
    },
    4: {
        "label": "Krasch · sjukfrånvaro",
        "color": "#a83817",
        "desc": "Du är tvingad ledig 1 vecka · alla aktiva jobb pausas.",
        "delay_risk_pct": 100,
        "health_per_week": -20,
        "safety_per_week": -8,
    },
}


def compute_time_capacity(
    s, *, company: Company, student_id: int,
) -> dict:
    """Bygg full tids-kapacitet-breakdown."""
    # Privat-jobb-timmar från StudentProfile
    from ..school.engines import master_session
    from ..school.models import StudentProfile, Student
    student_hours_used_for_private = 40.0
    weeks_overloaded = 0
    employment_status = "employed"
    with master_session() as ms:
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        if prof is not None:
            student_hours_used_for_private = float(
                getattr(prof, "weekly_hours_employed", 40) or 40
            )
            weeks_overloaded = int(
                getattr(prof, "consecutive_overload_weeks", 0) or 0
            )
            employment_status = (
                getattr(prof, "employment_status", "employed") or "employed"
            )

    # Egen biz-timmar
    self_biz_hours = max(
        0.0,
        PRODUCTIVE_HOURS_PER_PERSON_WEEK - student_hours_used_for_private,
    )

    # Anställda · TVÅ källor:
    # 1. CompanyEmployment (master DB) · skapas när annan elev söker
    #    klassens jobbannons och blir godkänd. Ger ett namn.
    # 2. Company.delivery_capacity (scope DB) · skapas när eleven
    #    själv köper "Anställ heltid"-besluten i Tillväxt-fliken.
    #    Inkrementeras i foretag_engine.py (BusinessDecision-flödet).
    #    Default 1 = ägaren själv, så fiktiva anställda = capacity − 1.
    # Tidigare bug: capacity läste BARA källa #1 → fiktiva anställda från
    # Tillväxt-flödet gav ingen kapacitets-bonus i tids-modellen.
    n_employees = 0
    employee_names: list[str] = []
    try:
        from ..school.models import (
            ClassCompanyShare, CompanyEmployment, Student as _Stu,
        )
        with master_session() as ms:
            share = (
                ms.query(ClassCompanyShare)
                .filter(
                    ClassCompanyShare.owner_student_id == student_id,
                    ClassCompanyShare.company_id_in_scope == company.id,
                )
                .first()
            )
            if share is not None:
                empls = (
                    ms.query(CompanyEmployment)
                    .filter(
                        CompanyEmployment.company_share_id == share.id,
                        CompanyEmployment.status == "active",
                    )
                    .all()
                )
                n_employees = len(empls)
                emp_ids = [e.employee_student_id for e in empls]
                if emp_ids:
                    students = (
                        ms.query(_Stu).filter(_Stu.id.in_(emp_ids)).all()
                    )
                    employee_names = [s.display_name for s in students]
    except Exception:
        log.exception("compute_time_capacity: kunde inte räkna anställda")

    # Lägg till fiktiva anställda från Tillväxt-besluten (Company.
    # delivery_capacity - 1). Real-student-anställda räknas redan ovan.
    fictional_employees = max(0, int(company.delivery_capacity or 1) - 1)
    if fictional_employees > 0:
        n_employees += fictional_employees
        employee_names.append(
            f"+{fictional_employees} fiktiv{'a' if fictional_employees > 1 else ''}"
        )
    employee_hours = n_employees * EMPLOYEE_HOURS_PER_WEEK

    # MCP
    today = current_game_date()
    n_mcp = (
        s.query(CompanyMcpRental)
        .filter(
            CompanyMcpRental.company_id == company.id,
            CompanyMcpRental.status == "active",
            CompanyMcpRental.ends_on >= today,
        )
        .count()
    )
    mcp_hours = n_mcp * MCP_HOURS_PER_WEEK

    total_available = self_biz_hours + employee_hours + mcp_hours

    # Använda timmar = aktiva jobs hours_per_week
    active_jobs = (
        s.query(Job)
        .filter(
            Job.company_id == company.id,
            Job.status == "in_progress",
        )
        .all()
    )
    hours_used = sum(int(j.hours_per_week or 0) for j in active_jobs)
    if total_available <= 0:
        ratio = 99.0 if hours_used > 0 else 0.0
    else:
        ratio = hours_used / total_available
    util_pct = int(round(ratio * 100))
    remaining = max(0.0, total_available - hours_used)

    tier = _classify_tier(ratio, weeks_overloaded)

    # Sammanställning av aktiva jobb
    job_summary = [
        {
            "id": j.id,
            "title": j.title,
            "customer_name": j.customer_name,
            "hours_per_week": int(j.hours_per_week or 0),
            "estimated_hours": int(j.estimated_hours or 0),
            "expected_complete_on": j.expected_complete_on.isoformat(),
            "delays_count": int(j.delays_count or 0),
        }
        for j in active_jobs
    ]

    return {
        "available_hours": int(total_available),
        "used_hours": int(hours_used),
        "remaining_hours": int(remaining),
        "utilization_pct": util_pct,
        "ratio": round(ratio, 3),
        "tier": tier,
        "tier_label": TIER_INFO[tier]["label"],
        "tier_color": TIER_INFO[tier]["color"],
        "tier_desc": TIER_INFO[tier]["desc"],
        "weeks_overloaded": weeks_overloaded,
        "employment_status": employment_status,
        "breakdown": {
            "student_self_hours": int(self_biz_hours),
            "private_job_hours": int(student_hours_used_for_private),
            "n_employees": n_employees,
            "employee_hours_total": int(employee_hours),
            "employee_names": employee_names,
            "mcp_hours": int(mcp_hours),
            "mcp_active": n_mcp > 0,
        },
        "active_jobs": job_summary,
    }


# === Schemas ===

class TimeCapacityOut(BaseModel):
    available_hours: int
    used_hours: int
    remaining_hours: int
    utilization_pct: int
    ratio: float
    tier: int
    tier_label: str
    tier_color: str
    tier_desc: str
    weeks_overloaded: int
    employment_status: str
    breakdown: dict
    active_jobs: list[dict]


class JobImpactPreviewOut(BaseModel):
    """Prediktion: om eleven tar denna offert, vad blir tier?"""
    job_estimated_hours: int
    job_hours_per_week: int
    job_weeks: int
    current_used_hours: int
    current_available_hours: int
    after_used_hours: int
    after_ratio: float
    after_utilization_pct: int
    after_tier: int
    after_tier_label: str
    after_tier_color: str
    after_tier_desc: str
    delay_risk_pct: int
    health_impact_per_week: int
    safety_impact_per_week: int


# === Helper · uppskatta job hours från industri ===

def estimate_job_hours(
    industry_key: str, delivery_days: int,
) -> tuple[int, int]:
    """Returnera (estimated_hours, hours_per_week) för ett jobb baserat
    på industrins time_per_job_hours_min/max."""
    try:
        from ..business.industries import get_industry
        ind = get_industry(industry_key)
        avg_hours = (ind.time_per_job_hours_min + ind.time_per_job_hours_max) / 2.0
    except Exception:
        avg_hours = 8.0  # fallback

    # Skala med delivery_days runt en baseline (14 dagar)
    scaled = avg_hours * max(0.4, min(2.0, delivery_days / 14.0))
    estimated = int(round(scaled))
    weeks = max(1, math.ceil(delivery_days / 7))
    per_week = int(round(estimated / weeks))
    return estimated, per_week


# === Endpoints ===

@router.get("/time", response_model=TimeCapacityOut)
def time_capacity(info: TokenInfo = Depends(require_token)):
    """Full breakdown · för BizHub-widget + Tillväxt-vyn."""
    student_id = _require_student(info)
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Inget aktivt bolag")
        return compute_time_capacity(s, company=c, student_id=student_id)


@router.get(
    "/preview-impact/{opp_id}", response_model=JobImpactPreviewOut,
)
def preview_impact(
    opp_id: int,
    info: TokenInfo = Depends(require_token),
):
    """Prediktion: hur påverkar detta jobb min kapacitet om jag tar det?

    Används av offert-modal för att visa varning innan submit."""
    student_id = _require_student(info)
    from ..business.models import JobOpportunity
    with session_scope() as s:
        c = _get_active_company(s)
        if c is None:
            raise HTTPException(400, "Inget aktivt bolag")
        opp = s.get(JobOpportunity, opp_id)
        if opp is None or opp.company_id != c.id:
            raise HTTPException(404, "Offert saknas")

        job_hours, job_per_week = estimate_job_hours(
            opp.industry_tag or c.industry_key or "default",
            opp.expected_delivery_days,
        )

        # Aktuell capacity
        cap = compute_time_capacity(s, company=c, student_id=student_id)
        current_used = cap["used_hours"]
        avail = max(1, cap["available_hours"])
        new_used = current_used + job_per_week
        new_ratio = new_used / avail
        new_tier = _classify_tier(new_ratio, cap["weeks_overloaded"])
        info_t = TIER_INFO[new_tier]

        return JobImpactPreviewOut(
            job_estimated_hours=job_hours,
            job_hours_per_week=job_per_week,
            job_weeks=max(1, math.ceil(opp.expected_delivery_days / 7)),
            current_used_hours=current_used,
            current_available_hours=avail,
            after_used_hours=new_used,
            after_ratio=round(new_ratio, 3),
            after_utilization_pct=int(round(new_ratio * 100)),
            after_tier=new_tier,
            after_tier_label=info_t["label"],
            after_tier_color=info_t["color"],
            after_tier_desc=info_t["desc"],
            delay_risk_pct=info_t["delay_risk_pct"],
            health_impact_per_week=info_t["health_per_week"],
            safety_impact_per_week=info_t["safety_per_week"],
        )


# === Säga upp privat-jobb ===

class QuitJobOut(BaseModel):
    ok: bool
    message: str
    new_employment_status: str
    safety_delta: int
    biz_hours_freed: int
    employment_end_on: Optional[date] = None


@router.post("/quit-private-job", response_model=QuitJobOut)
def quit_private_job(info: TokenInfo = Depends(require_token)):
    """Säga upp privat-jobbet enligt LAS · 1 mån uppsägningstid (default).

    Status sätts till 'self_employed' OM eleven driver ett aktivt
    bolag, annars 'unemployed'. Anställningen löper formellt ut på
    employment_end_on (today_game + uppsägningstid) · salary_phase
    fortsätter generera lön fram till dess.
    """
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import StudentProfile
    from ..business.game_clock import current_game_date
    from datetime import timedelta as _td_q

    today_g = current_game_date()
    # LAS-uppsägningstid · 1 mån default (< 2 års anställning är vanligt
    # för spelets karaktärer som är 22-30 år gamla). Vi har inte
    # employment_start_date på profilen så vi hardcodar 1 mån här.
    notice_days = 30
    end_on = today_g + _td_q(days=notice_days)

    has_active_business = False
    old_hours: int = 0
    old_employer: Optional[str] = None
    old_profession: Optional[str] = None

    with master_session() as ms:
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        if prof is None:
            raise HTTPException(404, "Profil saknas")
        current_status = (
            getattr(prof, "employment_status", None) or "employed"
        )
        if current_status != "employed":
            raise HTTPException(
                409,
                f"Du har redan status '{current_status}' · "
                "ingen aktiv anställning att säga upp.",
            )

        old_hours = int(getattr(prof, "weekly_hours_employed", 40) or 40)
        old_employer = prof.employer
        old_profession = prof.profession

        # Detektera aktivt bolag · ägs av eleven, status != 'bankrupt'.
        try:
            from ..business.models import Company
            from ..school.engines import scope_for_student as _sfs_b
            from ..school.engines import scope_context as _sctx_b
            from ..db.base import session_scope as _ss_b
            from ..school.models import Student as _Stu_b
            stu_b = ms.get(_Stu_b, student_id)
            if stu_b is not None:
                scope_key_b = _sfs_b(stu_b)
                with _sctx_b(scope_key_b):
                    with _ss_b() as _sb:
                        co = (
                            _sb.query(Company)
                            .filter(Company.is_active.is_(True))
                            .first()
                        )
                        if co is not None:
                            has_active_business = True
        except Exception:
            log.exception(
                "quit_private_job: kunde inte detektera aktivt bolag",
            )

        # Sätt employment_end_on + behåll status 'employed' tills
        # end_on passerats (då auto-skiftar via salary_phase-gaten).
        # Vi sätter dock NY status direkt så HubV2 visar 'Egenföretagare'
        # eller 'Söker jobb' utan väntan på end_on.
        new_status = "self_employed" if has_active_business else "unemployed"
        prof.employment_status = new_status
        prof.employment_end_on = end_on
        if hasattr(prof, "weekly_hours_employed"):
            prof.weekly_hours_employed = 0
        ms.commit()

    # Privat-pentagon · realistiska deltan beroende på fallback-jobb
    try:
        from ..game_engine.pentagon import apply_pentagon_delta
        if has_active_business:
            # Egenföretagare · måttlig osäkerhet, frihet positiv
            apply_pentagon_delta(
                student_id, axis="safety", requested_delta=-5,
                reason_kind="private_job_quit",
                explanation=(
                    "Sa upp privat-jobb · drivs nu helt av eget bolag · "
                    "egenföretagar-osäkerhet sänker trygghet."
                ),
            )
            apply_pentagon_delta(
                student_id, axis="economy", requested_delta=-2,
                reason_kind="private_job_quit",
                explanation="Slutar få fast lön efter 1 mån",
            )
            apply_pentagon_delta(
                student_id, axis="leisure", requested_delta=2,
                reason_kind="private_job_quit",
                explanation="Frihet från fast jobb-schema",
            )
        else:
            # Arbetslös · större dipp
            apply_pentagon_delta(
                student_id, axis="safety", requested_delta=-10,
                reason_kind="private_job_quit",
                explanation=(
                    "Sa upp privat-jobb utan att ha annan inkomstkälla · "
                    "tryggheten sjunker markant."
                ),
            )
            apply_pentagon_delta(
                student_id, axis="economy", requested_delta=-5,
                reason_kind="private_job_quit",
                explanation="Ingen inkomst efter 1 mån",
            )
        apply_pentagon_delta(
            student_id, axis="social", requested_delta=-1,
            reason_kind="private_job_quit",
            explanation="Tappar arbetskollegor",
        )
    except Exception:
        log.exception("apply_pentagon_delta failed för quit_private_job")

    # Formellt uppsägningsbrev · ser ut som riktigt bekräftelse-mail
    try:
        from ..db.base import session_scope as _ps
        from ..db.models import MailItem
        from datetime import datetime as _dt, time as _time_q
        from ..business.game_clock import current_game_date as _cgd_mail
        today_for_mail = _cgd_mail()
        next_action = (
            "Du driver eget AB · företagsekonomin tar nu fullt ansvar."
            if has_active_business
            else (
                "Du kommer stå utan inkomst · sök nytt jobb via "
                "/v2/arbetsformedlingen så snart möjligt."
            )
        )
        with _ps() as priv_s:
            priv_s.add(MailItem(
                sender=old_employer or "Arbetsgivaren",
                sender_short=(
                    (old_employer or "EMP")[:3].upper()
                ),
                sender_kind="work",
                sender_meta="uppsägningsbekräftelse",
                mail_type="info",
                subject=(
                    f"Uppsägning bekräftad · sista anställningsdag "
                    f"{end_on.isoformat()}"
                ),
                body_meta=f"Sista dag {end_on.isoformat()}",
                body=(
                    f"Hej {old_profession or 'medarbetare'},\n\n"
                    f"Vi bekräftar härmed mottagandet av din uppsägning. "
                    f"Enligt lagen om anställningsskydd (LAS) har du en "
                    f"uppsägningstid om {notice_days} dagar. Din sista "
                    f"anställningsdag är **{end_on.strftime('%Y-%m-%d')}**.\n\n"
                    f"Under uppsägningstiden:\n"
                    f"· Du har kvar din lön och dina förmåner\n"
                    f"· Du har företrädesrätt vid återanställning under "
                    f"9 mån från sista dag\n"
                    f"· Sista lönespec utbetalas månaden då anställningen "
                    f"upphör\n\n"
                    f"Efter sista anställningsdag:\n"
                    f"{next_action}\n\n"
                    f"Vi tackar för din tid hos {old_employer or 'oss'} "
                    f"och önskar dig lycka till framåt.\n\n"
                    f"Med vänlig hälsning,\n"
                    f"HR-avdelningen"
                ),
                amount=None,
                due_date=None,
                status="unhandled",
                received_at=_dt.combine(today_for_mail, _time_q(9, 0)),
                released_at=None,
            ))
            priv_s.commit()
    except Exception:
        log.exception("kunde inte generera uppsägningsbrev")

    # Lärar-spårning
    try:
        from ..school.activity import log_activity
        new_status_label = (
            "self_employed" if has_active_business else "unemployed"
        )
        log_activity(
            kind="private.resigned",
            summary=(
                f"Sa upp sig från {old_employer or 'privat-jobb'} · "
                f"sista dag {end_on.isoformat()} · → {new_status_label}"
            ),
            payload={
                "old_employer": old_employer,
                "old_profession": old_profession,
                "old_hours": old_hours,
                "employment_end_on": end_on.isoformat(),
                "new_status": new_status_label,
                "has_business": has_active_business,
            },
        )
    except Exception:
        pass

    return QuitJobOut(
        ok=True,
        message=(
            f"Uppsägning bekräftad · sista anställningsdag "
            f"{end_on.isoformat()}. " + (
                "Du driver eget AB · all inkomst kommer nu från bolaget."
                if has_active_business
                else "Sök nytt jobb i Arbetsförmedlingen för att undvika "
                "ekonomisk dipp."
            )
        ),
        new_employment_status=(
            "self_employed" if has_active_business else "unemployed"
        ),
        safety_delta=-5 if has_active_business else -10,
        biz_hours_freed=old_hours,
        employment_end_on=end_on,
    )
