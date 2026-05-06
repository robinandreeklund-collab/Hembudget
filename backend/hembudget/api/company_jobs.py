"""Klass-företag jobbannonser · Fas D av Allabolag-paketet.

Spec: dev/feature-allabolag.md

Ägar-flöde:
* POST /v2/foretag/job-ads      · skapa jobbannons
* GET  /v2/foretag/job-ads/mine · lista mina annonser + ansökningar
* POST /v2/foretag/job-ads/{id}/applications/{app_id}/decide

Elev-flöde (på arbetsförmedlingen):
* GET  /v2/arbetsformedlingen/klass-jobb     · lista alla öppna
* POST /v2/arbetsformedlingen/klass-jobb/{id}/apply
* GET  /v2/arbetsformedlingen/mina-anstallningar
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .deps import TokenInfo, require_token
from ..business.models import Company
from ..db.base import session_scope


log = logging.getLogger(__name__)

owner_router = APIRouter(
    prefix="/v2/foretag/job-ads", tags=["allabolag"],
)
seeker_router = APIRouter(
    prefix="/v2/arbetsformedlingen", tags=["allabolag"],
)


def _require_student(info: TokenInfo) -> int:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(403, "Endast elever")
    return info.student_id


# === Schemas ===

class JobAdIn(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    description: str = Field(..., min_length=10, max_length=4000)
    monthly_salary: int = Field(ge=5000, le=200000)


class JobAdOut(BaseModel):
    id: int
    company_name: str = ""
    industry_label: Optional[str] = None
    title: str = ""
    description: str = ""
    monthly_salary: int = 0
    status: str = "open"
    posted_at: str = ""
    n_applicants: int = 0
    is_my_company: bool = False
    have_i_applied: bool = False
    my_application_status: Optional[str] = None


class JobApplicationIn(BaseModel):
    cover_letter: str = Field(..., min_length=20, max_length=4000)


class JobApplicationOut(BaseModel):
    id: int
    job_ad_id: int
    applicant_display: str
    cover_letter: str
    status: str
    submitted_at: str


class DecideApplicationIn(BaseModel):
    decision: str = Field(..., pattern="^(accepted|rejected)$")


class EmploymentOut(BaseModel):
    id: int
    company_name: str
    industry_label: Optional[str]
    monthly_salary: int
    started_at: str
    status: str


# === Owner endpoints ===

@owner_router.post("", response_model=JobAdOut)
def create_job_ad(
    body: JobAdIn,
    info: TokenInfo = Depends(require_token),
):
    """Företagsägaren skapar en jobbannons. Företaget måste vara
    publicerat på Allabolag innan annonsen blir synlig."""
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import (
        ClassCompanyShare, CompanyJobAd, Student,
    )

    with session_scope() as scope_s:
        co = (
            scope_s.query(Company)
            .filter(Company.active.is_(True))
            .first()
        )
        if co is None:
            raise HTTPException(400, "Du måste ha ett aktivt företag")
        co_id = co.id

        # Försök hitta share. Saknas den = self-heal: kör sync_class_
        # company_share så cachen byggs nu istället för att tvinga eleven
        # gå runt och "ticka" först.
        with master_session() as ms:
            share_id = (
                ms.query(ClassCompanyShare.id)
                .filter(
                    ClassCompanyShare.owner_student_id == student_id,
                    ClassCompanyShare.company_id_in_scope == co_id,
                )
                .scalar()
            )
        if share_id is None:
            try:
                from .allabolag import sync_class_company_share
                with master_session() as ms2:
                    stu = ms2.get(Student, student_id)
                    teacher_id = stu.teacher_id if stu else None
                    class_label = stu.class_label if stu else None
                if teacher_id is not None:
                    sync_class_company_share(
                        scope_s,
                        company=co,
                        teacher_id=teacher_id,
                        student_id=student_id,
                        class_label=class_label,
                    )
            except Exception:
                log.exception(
                    "create_job_ad: lazy-sync av ClassCompanyShare "
                    "misslyckades för company=%s student=%s",
                    co_id, student_id,
                )
            with master_session() as ms3:
                share_id = (
                    ms3.query(ClassCompanyShare.id)
                    .filter(
                        ClassCompanyShare.owner_student_id == student_id,
                        ClassCompanyShare.company_id_in_scope == co_id,
                    )
                    .scalar()
                )
            if share_id is None:
                raise HTTPException(
                    503,
                    "Allabolag-cachen kunde inte skapas. "
                    "Försök igen om en stund.",
                )

    with master_session() as s:
        share = s.get(ClassCompanyShare, share_id)
        if share is None:
            raise HTTPException(503, "Allabolag-cachen försvann")

        ad = CompanyJobAd(
            company_share_id=share.id,
            posted_by_student_id=student_id,
            title=body.title.strip(),
            description=body.description.strip(),
            monthly_salary=body.monthly_salary,
        )
        s.add(ad)
        s.commit()
        s.refresh(ad)

        return JobAdOut(
            id=ad.id,
            company_name=share.company_name,
            industry_label=share.industry_label,
            title=ad.title,
            description=ad.description,
            monthly_salary=ad.monthly_salary,
            status=ad.status,
            posted_at=ad.posted_at.isoformat(),
            n_applicants=0,
            is_my_company=True,
            have_i_applied=False,
        )


@owner_router.get("/mine", response_model=list[JobAdOut])
def list_my_job_ads(info: TokenInfo = Depends(require_token)):
    """Lista alla jobbannonser du har postat."""
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import (
        ClassCompanyShare, CompanyJobAd, CompanyJobApplication,
    )

    # Defensiv hela vägen: om master_session, query eller en specifik rad
    # smäller (t.ex. saknad kolumn på prod-Postgres innan migration kört)
    # vill vi returnera tom lista istället för 500/422 så frontend kan
    # rendera en användbar tom vy.
    try:
        with master_session() as s:
            ads = (
                s.query(CompanyJobAd)
                .filter(CompanyJobAd.posted_by_student_id == student_id)
                .order_by(CompanyJobAd.posted_at.desc())
                .all()
            )
            if not ads:
                return []
            share_ids = list({a.company_share_id for a in ads})
            shares = (
                s.query(ClassCompanyShare)
                .filter(ClassCompanyShare.id.in_(share_ids))
                .all()
            )
            share_map = {sh.id: sh for sh in shares}
            out = []
            for ad in ads:
                try:
                    n_apps = (
                        s.query(CompanyJobApplication)
                        .filter(CompanyJobApplication.job_ad_id == ad.id)
                        .count()
                    )
                except Exception:
                    n_apps = 0
                sh = share_map.get(ad.company_share_id)
                posted = getattr(ad, "posted_at", None)
                out.append(JobAdOut(
                    id=ad.id,
                    company_name=(sh.company_name if sh else "?") or "?",
                    industry_label=(
                        getattr(sh, "industry_label", None) if sh else None
                    ),
                    title=ad.title or "",
                    description=ad.description or "",
                    monthly_salary=int(ad.monthly_salary or 0),
                    status=ad.status or "open",
                    posted_at=posted.isoformat() if posted else "",
                    n_applicants=n_apps,
                    is_my_company=True,
                    have_i_applied=False,
                ))
            return out
    except Exception:
        log.exception(
            "list_my_job_ads misslyckades — returnerar tom lista",
        )
        return []


@owner_router.get("/{ad_id}/applications", response_model=list[JobApplicationOut])
def list_applications(
    ad_id: int,
    info: TokenInfo = Depends(require_token),
):
    """Lista ansökningar för en av mina jobbannonser."""
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import (
        CompanyJobAd, CompanyJobApplication, Student,
    )

    with master_session() as s:
        ad = s.get(CompanyJobAd, ad_id)
        if ad is None or ad.posted_by_student_id != student_id:
            raise HTTPException(404, "Annons saknas")
        apps = (
            s.query(CompanyJobApplication)
            .filter(CompanyJobApplication.job_ad_id == ad_id)
            .order_by(CompanyJobApplication.submitted_at.desc())
            .all()
        )
        applicant_ids = list({a.applicant_student_id for a in apps})
        students = (
            s.query(Student)
            .filter(Student.id.in_(applicant_ids))
            .all()
        )
        name_map = {st.id: st.display_name for st in students}
        return [
            JobApplicationOut(
                id=a.id,
                job_ad_id=a.job_ad_id,
                applicant_display=name_map.get(a.applicant_student_id, "?"),
                cover_letter=a.cover_letter,
                status=a.status,
                submitted_at=a.submitted_at.isoformat(),
            )
            for a in apps
        ]


@owner_router.post(
    "/{ad_id}/applications/{app_id}/decide", response_model=JobApplicationOut,
)
def decide_application(
    ad_id: int,
    app_id: int,
    body: DecideApplicationIn,
    info: TokenInfo = Depends(require_token),
):
    """Godkänn eller avslå en ansökan. Vid acceptance:
    1. App.status = accepted
    2. JobAd.status = filled, hired_student_id = applicant
    3. CompanyEmployment skapas
    4. Övriga sökandes apps → rejected
    """
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import (
        ClassCompanyShare, CompanyEmployment,
        CompanyJobAd, CompanyJobApplication, Student,
    )

    with master_session() as s:
        ad = s.get(CompanyJobAd, ad_id)
        if ad is None or ad.posted_by_student_id != student_id:
            raise HTTPException(404, "Annons saknas")
        app_row = s.get(CompanyJobApplication, app_id)
        if app_row is None or app_row.job_ad_id != ad_id:
            raise HTTPException(404, "Ansökan saknas")
        if ad.status != "open":
            raise HTTPException(409, "Annons är redan stängd")

        now = datetime.utcnow()
        app_row.status = body.decision
        app_row.decided_at = now

        if body.decision == "accepted":
            ad.status = "filled"
            ad.hired_student_id = app_row.applicant_student_id
            ad.filled_at = now
            # Avslå övriga
            others = (
                s.query(CompanyJobApplication)
                .filter(
                    CompanyJobApplication.job_ad_id == ad_id,
                    CompanyJobApplication.id != app_id,
                    CompanyJobApplication.status == "pending",
                )
                .all()
            )
            for o in others:
                o.status = "rejected"
                o.decided_at = now
            # Skapa anställning
            existing_empl = (
                s.query(CompanyEmployment)
                .filter(
                    CompanyEmployment.company_share_id == ad.company_share_id,
                    CompanyEmployment.employee_student_id == app_row.applicant_student_id,
                )
                .first()
            )
            if existing_empl is None:
                empl = CompanyEmployment(
                    company_share_id=ad.company_share_id,
                    employee_student_id=app_row.applicant_student_id,
                    monthly_salary=ad.monthly_salary,
                )
                s.add(empl)
            # Uppdatera klass-företag-cache · n_employees
            share = s.get(ClassCompanyShare, ad.company_share_id)
            if share is not None:
                share.n_employees = (
                    s.query(CompanyEmployment)
                    .filter(
                        CompanyEmployment.company_share_id == share.id,
                        CompanyEmployment.status == "active",
                    )
                    .count()
                )
        s.commit()
        s.refresh(app_row)

        st = s.get(Student, app_row.applicant_student_id)
        return JobApplicationOut(
            id=app_row.id,
            job_ad_id=app_row.job_ad_id,
            applicant_display=st.display_name if st else "?",
            cover_letter=app_row.cover_letter,
            status=app_row.status,
            submitted_at=app_row.submitted_at.isoformat(),
        )


# === Seeker endpoints (Arbetsförmedlingen-tab) ===

@seeker_router.get("/klass-jobb", response_model=list[JobAdOut])
def list_class_jobs(info: TokenInfo = Depends(require_token)):
    """Lista alla öppna klass-företag-jobbannonser för min teacher."""
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import (
        ClassCompanyShare, CompanyJobAd, CompanyJobApplication, Student,
    )

    with master_session() as s:
        stu = s.get(Student, student_id)
        if stu is None:
            raise HTTPException(404, "Elev saknas")
        teacher_id = stu.teacher_id

        ads = (
            s.query(CompanyJobAd)
            .join(
                ClassCompanyShare,
                ClassCompanyShare.id == CompanyJobAd.company_share_id,
            )
            .filter(
                ClassCompanyShare.teacher_id == teacher_id,
                CompanyJobAd.status == "open",
            )
            .order_by(CompanyJobAd.posted_at.desc())
            .all()
        )
        share_ids = list({a.company_share_id for a in ads})
        shares = (
            s.query(ClassCompanyShare)
            .filter(ClassCompanyShare.id.in_(share_ids))
            .all()
        )
        share_map = {sh.id: sh for sh in shares}

        out = []
        for ad in ads:
            n_apps = (
                s.query(CompanyJobApplication)
                .filter(CompanyJobApplication.job_ad_id == ad.id)
                .count()
            )
            my_app = (
                s.query(CompanyJobApplication)
                .filter(
                    CompanyJobApplication.job_ad_id == ad.id,
                    CompanyJobApplication.applicant_student_id == student_id,
                )
                .first()
            )
            sh = share_map.get(ad.company_share_id)
            out.append(JobAdOut(
                id=ad.id,
                company_name=sh.company_name if sh else "?",
                industry_label=sh.industry_label if sh else None,
                title=ad.title,
                description=ad.description,
                monthly_salary=ad.monthly_salary,
                status=ad.status,
                posted_at=ad.posted_at.isoformat(),
                n_applicants=n_apps,
                is_my_company=(ad.posted_by_student_id == student_id),
                have_i_applied=(my_app is not None),
                my_application_status=(my_app.status if my_app else None),
            ))
        return out


@seeker_router.post(
    "/klass-jobb/{ad_id}/apply", response_model=JobApplicationOut,
)
def apply_class_job(
    ad_id: int,
    body: JobApplicationIn,
    info: TokenInfo = Depends(require_token),
):
    """Sök ett klass-företag-jobb."""
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import (
        CompanyJobAd, CompanyJobApplication, Student,
    )

    with master_session() as s:
        ad = s.get(CompanyJobAd, ad_id)
        if ad is None:
            raise HTTPException(404, "Annons saknas")
        if ad.status != "open":
            raise HTTPException(409, "Annons är inte öppen")
        if ad.posted_by_student_id == student_id:
            raise HTTPException(
                400, "Du kan inte söka ditt eget bolags jobb",
            )

        existing = (
            s.query(CompanyJobApplication)
            .filter(
                CompanyJobApplication.job_ad_id == ad_id,
                CompanyJobApplication.applicant_student_id == student_id,
            )
            .first()
        )
        if existing is not None:
            raise HTTPException(409, "Du har redan ansökt")

        app_row = CompanyJobApplication(
            job_ad_id=ad_id,
            applicant_student_id=student_id,
            cover_letter=body.cover_letter.strip(),
        )
        s.add(app_row)
        s.commit()
        s.refresh(app_row)

        st = s.get(Student, student_id)
        return JobApplicationOut(
            id=app_row.id,
            job_ad_id=ad_id,
            applicant_display=st.display_name if st else "?",
            cover_letter=app_row.cover_letter,
            status=app_row.status,
            submitted_at=app_row.submitted_at.isoformat(),
        )


@seeker_router.get(
    "/mina-anstallningar", response_model=list[EmploymentOut],
)
def my_employments(info: TokenInfo = Depends(require_token)):
    """Lista var jag är anställd som klass-företag-anställd."""
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import ClassCompanyShare, CompanyEmployment

    with master_session() as s:
        empls = (
            s.query(CompanyEmployment)
            .filter(
                CompanyEmployment.employee_student_id == student_id,
                CompanyEmployment.status == "active",
            )
            .all()
        )
        if not empls:
            return []
        share_ids = list({e.company_share_id for e in empls})
        shares = (
            s.query(ClassCompanyShare)
            .filter(ClassCompanyShare.id.in_(share_ids))
            .all()
        )
        share_map = {sh.id: sh for sh in shares}
        return [
            EmploymentOut(
                id=e.id,
                company_name=share_map.get(e.company_share_id).company_name
                    if share_map.get(e.company_share_id) else "?",
                industry_label=share_map.get(e.company_share_id).industry_label
                    if share_map.get(e.company_share_id) else None,
                monthly_salary=e.monthly_salary,
                started_at=e.started_at.isoformat(),
                status=e.status,
            )
            for e in empls
        ]
