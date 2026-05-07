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

    # Anställda · läs via master-DB
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


@router.post("/quit-private-job", response_model=QuitJobOut)
def quit_private_job(info: TokenInfo = Depends(require_token)):
    """Säga upp privat-jobbet · biz-tiden ökar med +44 h/v men privat-
    pentagon Trygghet sjunker direkt."""
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import StudentProfile
    with master_session() as ms:
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        if prof is None:
            raise HTTPException(404, "Profil saknas")
        if (getattr(prof, "weekly_hours_employed", 40) or 0) == 0:
            raise HTTPException(409, "Du har redan inget privat-jobb")

        old_hours = int(prof.weekly_hours_employed or 40)
        prof.weekly_hours_employed = 0
        if hasattr(prof, "employment_status"):
            prof.employment_status = "unemployed"
        ms.commit()

    # Privat-pentagon · Trygghet -15
    try:
        from ..game_engine.pentagon import apply_pentagon_delta
        apply_pentagon_delta(
            student_id, axis="safety",
            requested_delta=-15,
            reason_kind="private_job_quit",
            reason_id=None,
            reason_table=None,
            explanation=(
                "Du sa upp dig från privat-jobbet · "
                "tryggheten sjunker, men nu har du tid för bolaget."
            ),
        )
    except Exception:
        log.exception("apply_pentagon_delta failed för quit_private_job")

    # Generera mail i postlådan
    try:
        from ..db.base import session_scope as _ps
        from ..db.models import MailItem
        from datetime import datetime as _dt
        with _ps() as priv_s:
            priv_s.add(MailItem(
                sender="Maria · HR-chef",
                sender_short="MARIA",
                sender_kind="employer",
                mail_type="info",
                subject="Du har sagt upp dig",
                body=(
                    "Hej. Vi har tagit emot din uppsägning. Sista lönen "
                    f"betalades ut i månaden. Du går från {old_hours} h/v "
                    "till heltidsentreprenör.\n\n"
                    "Konsekvenser för din ekonomi:\n"
                    f"· Trygghet -15 i pentagon\n"
                    f"· Lönen från oss försvinner\n"
                    f"· Du har +{84 - 0} h/v för bolaget\n\n"
                    "Lycka till. /Maria"
                ),
                amount=None,
                due_date=None,
                status="unhandled",
            ))
            priv_s.commit()
    except Exception:
        log.exception("kunde inte generera quit-mail")

    # Lärar-spårning
    try:
        from ..school.activity import log_activity
        log_activity(
            kind="private_quit",
            summary=(
                f"Sa upp sig från privat-jobbet ({old_hours} h/v) · "
                "satsar fullt på företaget"
            ),
            payload={"old_hours": old_hours},
        )
    except Exception:
        pass

    return QuitJobOut(
        ok=True,
        message=(
            "Du är nu heltidsentreprenör. Trygghet sjönk men du har "
            "44+ h/v extra för bolaget."
        ),
        new_employment_status="unemployed",
        safety_delta=-15,
        biz_hours_freed=old_hours,
    )
