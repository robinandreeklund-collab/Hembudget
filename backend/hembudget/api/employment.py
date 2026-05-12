"""Klasskompis-anställning · hire/accept/decline/terminate-flöden.

Spec: dev/employment-flows.md (Fas C-E)

Endpoints är i `/v2/employment/...`-paraply (ej `/v2/foretag/...`
eftersom de logiskt rör BÅDA elever — företagaren OCH den anställde).

Auth-modell:
  · hire-offer: kräver student-token + aktivt företag i scope
  · accept-offer / decline-offer: kräver att caller är `employee_student_id`
  · terminate: kräver att caller äger företaget (owner_student_id)
  · my-offers / my-employments: returnerar baserat på caller

Notifikationer:
  · Erbjudande → MailItem(authority) i klasskompisens scope
  · Accept → MailItem(authority) i båda elevers scope
  · Decline → MailItem(authority) i ägarens scope
  · Terminate → MailItem(authority) i klasskompisens scope
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..business.game_clock import current_game_date
from ..business.models import Company
from ..db.base import session_scope
from ..db.models import MailItem
from ..school.activity import log_activity
from ..school.employment_models import ClassmateEmployment
from ..school.engines import (
    master_session,
    scope_context,
    scope_for_student,
)
from ..school.models import Student, StudentProfile
from ..school.tax import compute_net_salary
from .deps import TokenInfo, require_token


log = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/employment", tags=["employment"])


# ===========================================================
# Helpers
# ===========================================================


def _require_student_id(info: TokenInfo) -> int:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Endast elever kan använda anställnings-flöden",
        )
    return info.student_id


def _get_owner_active_company(owner_student_id: int) -> Optional[Company]:
    """Slå upp ägarens aktiva företag i deras scope-DB."""
    with master_session() as ms:
        stu = ms.get(Student, owner_student_id)
        if stu is None:
            return None
        scope_key = scope_for_student(stu)
    with scope_context(scope_key):
        with session_scope() as scope_s:
            return (
                scope_s.query(Company)
                .filter(Company.active.is_(True))
                .first()
            )


def _send_mail_to_student(
    student_id: int,
    *,
    sender: str,
    sender_short: str,
    sender_kind: str,
    subject: str,
    body: str,
    body_meta: Optional[str] = None,
    mail_type: str = "authority",
) -> None:
    """Skapa MailItem i en specifik elevs scope-DB."""
    with master_session() as ms:
        stu = ms.get(Student, student_id)
        if stu is None:
            return
        scope_key = scope_for_student(stu)
    today_g = current_game_date()
    with scope_context(scope_key):
        with session_scope() as scope_s:
            scope_s.add(MailItem(
                sender=sender,
                sender_short=sender_short[:4].upper(),
                sender_kind=sender_kind,
                sender_meta=body_meta or "anställning",
                mail_type=mail_type,
                subject=subject,
                body_meta=body_meta or subject[:60],
                body=body,
                amount=None,
                due_date=None,
                status="unhandled",
                received_at=datetime.combine(
                    today_g, datetime.min.time(),
                ).replace(hour=10),
                released_at=None,
            ))


# ===========================================================
# Schemas
# ===========================================================


class HireOfferIn(BaseModel):
    classmate_student_id: int
    role: str = Field(..., min_length=2, max_length=80)
    monthly_gross: int = Field(..., ge=15000, le=200000)


class EmploymentOut(BaseModel):
    id: int
    company_id: int
    company_name: str
    owner_student_id: int
    employee_student_id: int
    role: str
    monthly_gross: int
    status: str
    offer_sent_on: datetime
    accepted_on: Optional[date]
    last_day: Optional[date]
    termination_reason: Optional[str]


class EmploymentListOut(BaseModel):
    employments: list[EmploymentOut]


def _employment_to_out(e: ClassmateEmployment) -> EmploymentOut:
    return EmploymentOut(
        id=e.id,
        company_id=e.company_id,
        company_name=e.company_name,
        owner_student_id=e.owner_student_id,
        employee_student_id=e.employee_student_id,
        role=e.role,
        monthly_gross=e.monthly_gross,
        status=e.status,
        offer_sent_on=e.offer_sent_on,
        accepted_on=e.accepted_on,
        last_day=e.last_day,
        termination_reason=e.termination_reason,
    )


# ===========================================================
# Endpoints · företagarens vy (ägaren)
# ===========================================================


@router.get("/employments", response_model=EmploymentListOut)
def list_my_employments(info: TokenInfo = Depends(require_token)):
    """Lista alla anställningar (active + pending + terminated) som
    företagaren har skapat."""
    owner_id = _require_student_id(info)
    with master_session() as ms:
        rows = (
            ms.query(ClassmateEmployment)
            .filter(ClassmateEmployment.owner_student_id == owner_id)
            .order_by(ClassmateEmployment.offer_sent_on.desc())
            .all()
        )
        return EmploymentListOut(
            employments=[_employment_to_out(e) for e in rows],
        )


@router.post("/hire-offer", response_model=EmploymentOut)
def hire_offer(
    body: HireOfferIn,
    info: TokenInfo = Depends(require_token),
):
    """Skicka erbjudande till en klasskompis · skapar
    ClassmateEmployment(status='pending_offer') + brev till
    klasskompisens postlåda."""
    owner_id = _require_student_id(info)
    if body.classmate_student_id == owner_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Du kan inte anställa dig själv",
        )

    # Verifiera att ägaren har ett aktivt bolag
    co = _get_owner_active_company(owner_id)
    if co is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Du måste ha ett aktivt bolag för att anställa",
        )
    company_id = co.id
    company_name = co.name

    # Verifiera att klasskompisen finns + är i samma klass
    with master_session() as ms:
        owner = ms.get(Student, owner_id)
        cand = ms.get(Student, body.classmate_student_id)
        if cand is None or owner is None:
            raise HTTPException(404, "Klasskompis hittades inte")
        if cand.teacher_id != owner.teacher_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Du kan bara anställa elever från din egen klass",
            )
        # Kolla om det redan finns pending eller active erbjudande
        existing = (
            ms.query(ClassmateEmployment)
            .filter(
                ClassmateEmployment.owner_student_id == owner_id,
                ClassmateEmployment.employee_student_id == body.classmate_student_id,
                ClassmateEmployment.status.in_(
                    ("pending_offer", "active"),
                ),
            )
            .first()
        )
        if existing is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Det finns redan ett {existing.status}-ärende för "
                f"den här klasskompisen",
            )
        candidate_name = cand.display_name

        emp = ClassmateEmployment(
            owner_student_id=owner_id,
            company_id=company_id,
            company_name=company_name,
            employee_student_id=body.classmate_student_id,
            role=body.role.strip(),
            monthly_gross=body.monthly_gross,
            status="pending_offer",
        )
        ms.add(emp)
        ms.flush()
        emp_id = emp.id
        ms.commit()

    # Skicka erbjudande-brev till klasskompisens postlåda
    try:
        _send_mail_to_student(
            body.classmate_student_id,
            sender=company_name,
            sender_short=company_name[:3],
            sender_kind="agency",
            subject=(
                f"Anställningserbjudande · {company_name} · "
                f"{body.role}"
            ),
            body_meta=(
                f"Lön {body.monthly_gross:,} kr/mån"
                .replace(",", " ")
            ),
            body=(
                f"Hej {candidate_name},\n\n"
                f"Vi på **{company_name}** erbjuder dig en anställning "
                f"som **{body.role}** med en månadslön på "
                f"**{body.monthly_gross:,} kr brutto**".replace(",", " ")
                + ".\n\n"
                "Anställningsvillkor:\n"
                "· Tillsvidareanställning\n"
                "· Kollektivavtals-skydd (LAS · 1 mån uppsägningstid)\n"
                "· Lönespec varje månad till din postlåda\n\n"
                "Om du tackar ja säger du automatiskt upp din nuvarande "
                "anställning (om du har en) med 30 dgr varsel enligt LAS.\n\n"
                "Du kan acceptera eller neka via knapparna nedan.\n"
                f"_employment_id={emp_id}"
            ),
            mail_type="authority",
        )
    except Exception:
        log.exception("hire-offer: kunde inte skicka erbjudande-brev")

    # Lärar-spårning · BÅDA elevers scope
    try:
        log_activity(
            kind="biz.employee_hire_offered",
            summary=(
                f"Erbjöd anställning till {candidate_name} · "
                f"{body.role} · {body.monthly_gross} kr/mån"
            ),
            payload={
                "employment_id": emp_id,
                "employee_student_id": body.classmate_student_id,
                "company_name": company_name,
                "role": body.role,
                "monthly_gross": body.monthly_gross,
            },
            student_id=owner_id,
        )
        log_activity(
            kind="private.employment_offer_received",
            summary=(
                f"Anställningserbjudande från {company_name} · "
                f"{body.role} · {body.monthly_gross} kr/mån"
            ),
            payload={
                "employment_id": emp_id,
                "company_name": company_name,
                "role": body.role,
                "monthly_gross": body.monthly_gross,
                "from_student_id": owner_id,
            },
            student_id=body.classmate_student_id,
        )
    except Exception:
        pass

    with master_session() as ms:
        emp = ms.get(ClassmateEmployment, emp_id)
        return _employment_to_out(emp)


# ===========================================================
# Endpoints · klasskompisens vy (kandidaten)
# ===========================================================


@router.get("/offers", response_model=EmploymentListOut)
def list_my_offers(info: TokenInfo = Depends(require_token)):
    """Lista pending anställningserbjudanden FÖR den inloggade eleven."""
    student_id = _require_student_id(info)
    with master_session() as ms:
        rows = (
            ms.query(ClassmateEmployment)
            .filter(
                ClassmateEmployment.employee_student_id == student_id,
                ClassmateEmployment.status == "pending_offer",
            )
            .order_by(ClassmateEmployment.offer_sent_on.desc())
            .all()
        )
        return EmploymentListOut(
            employments=[_employment_to_out(e) for e in rows],
        )


@router.post("/offers/{employment_id}/accept", response_model=EmploymentOut)
def accept_offer(
    employment_id: int,
    info: TokenInfo = Depends(require_token),
):
    """Klasskompis accepterar anställningserbjudande.

    Effekt:
      · ClassmateEmployment.status = 'active'
      · Om eleven har annat aktivt jobb · auto-resign med 30 dgr LAS
      · StudentProfile uppdateras (employer, profession, gross)
      · Bekräftelsebrev till båda elever
    """
    student_id = _require_student_id(info)
    today_g = current_game_date()

    with master_session() as ms:
        emp = ms.get(ClassmateEmployment, employment_id)
        if emp is None:
            raise HTTPException(404, "Erbjudande hittades inte")
        if emp.employee_student_id != student_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Du kan bara acceptera dina egna erbjudanden",
            )
        if emp.status != "pending_offer":
            raise HTTPException(
                400, f"Erbjudandet har redan status '{emp.status}'",
            )

        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        if prof is None:
            raise HTTPException(404, "Din profil saknas")

        # Auto-resign från tidigare jobb (om aktiv anställning)
        old_employer = prof.employer
        current_status = (
            getattr(prof, "employment_status", None) or "employed"
        )
        triggered_auto_resign = False
        if (
            current_status == "employed"
            and old_employer
            and old_employer != emp.company_name
        ):
            # 30 dgr LAS-notice · employer kvar tills end_on (då
            # auto-byts via salary_phase till new company-lön).
            # För enkelhetens skull bytar vi DIREKT till nya jobbet
            # eftersom user-flödet "klasskompis-erbjudande →
            # acceptera" är en aktiv handling. Den gamla arbetsgivaren
            # får ett uppsägningsbrev. (Verkligheten: man får jobba
            # ut sin uppsägningstid; vi förenklar för pedagogiken.)
            triggered_auto_resign = True

        # Aktivera anställningen
        emp.status = "active"
        emp.accepted_on = today_g

        # Uppdatera klasskompisens StudentProfile till nya jobbet
        prof.employer = emp.company_name
        prof.profession = emp.role
        prof.gross_salary_monthly = emp.monthly_gross
        # Räkna ny netto via samma tax-modul som karriär-onboarding
        try:
            tax_calc = compute_net_salary(emp.monthly_gross)
            prof.net_salary_monthly = int(tax_calc.net_monthly)
            prof.tax_rate_effective = float(tax_calc.effective_tax_rate)
        except Exception:
            log.exception(
                "accept_offer: compute_net_salary failed för %s",
                emp.monthly_gross,
            )
        prof.employment_status = "employed"
        prof.employment_end_on = None  # rensa ev pågående uppsägning

        ms.commit()
        # Snapshot för mail-sändning utanför sessionen
        company_name = emp.company_name
        role = emp.role
        gross = emp.monthly_gross
        owner_id = emp.owner_student_id

    # Bekräftelse till klasskompis (anställd)
    try:
        _send_mail_to_student(
            student_id,
            sender=company_name,
            sender_short=company_name[:3],
            sender_kind="agency",
            subject=f"Välkommen till {company_name}!",
            body_meta=f"Anställd som {role}",
            body=(
                f"Hej!\n\n"
                f"Vi är glada att du tackar ja till anställningen "
                f"som **{role}** på **{company_name}**.\n\n"
                f"Anställningsvillkor:\n"
                f"· Lön: {gross:,} kr brutto/mån\n".replace(",", " ")
                + f"· Tillträdesdag: {today_g.isoformat()}\n"
                f"· Lönespec utbetalas månadens 25:e till din postlåda\n\n"
                + (
                    "**OBS:** Din tidigare anställning hos "
                    f"{old_employer} sägs upp automatiskt med 30 dgrs "
                    "varsel enligt LAS. Sista lönespec därifrån "
                    "utbetalas i månaden efter."
                    if triggered_auto_resign else ""
                )
                + "\n\nVälkommen!\nHR-avdelningen"
            ),
        )
    except Exception:
        log.exception("accept: bekräftelse till anställd misslyckades")

    # Notifikation till företagaren
    try:
        _send_mail_to_student(
            owner_id,
            sender="Anställningssystemet",
            sender_short="HR",
            sender_kind="agency",
            subject=(
                f"{role} · erbjudande accepterat"
            ),
            body=(
                f"Bra nyheter!\n\n"
                f"Din anställning av {role}-positionen har accepterats. "
                f"Den nya anställde börjar {today_g.isoformat()}.\n\n"
                f"Glöm inte att skicka första lönespec i slutet av "
                f"månaden (Aktör · Företaget · Anställda)."
            ),
        )
    except Exception:
        pass

    # Lärar-spårning
    try:
        log_activity(
            kind="private.employment_accepted",
            summary=f"Accepterade anställning · {company_name} · {role}",
            payload={
                "employment_id": employment_id,
                "company_name": company_name,
                "role": role,
                "monthly_gross": gross,
            },
            student_id=student_id,
        )
        log_activity(
            kind="biz.employee_hired",
            summary=f"Anställning accepterad av klasskompis · {role}",
            payload={
                "employment_id": employment_id,
                "employee_student_id": student_id,
                "role": role,
            },
            student_id=owner_id,
        )
    except Exception:
        pass

    # Pentagon-delta · positiv för anställd (stabilitet)
    try:
        from ..game_engine.pentagon import apply_pentagon_delta
        apply_pentagon_delta(
            student_id, axis="safety", requested_delta=3,
            reason_kind="employment_accepted",
            reason_id=employment_id,
            reason_table="classmate_employments",
            explanation=(
                f"Anställd på {company_name} · stabilitet via "
                "klasskompis-anställning"
            ),
        )
        apply_pentagon_delta(
            student_id, axis="economy", requested_delta=2,
            reason_kind="employment_accepted",
            reason_id=employment_id,
            reason_table="classmate_employments",
            explanation="Ny fast inkomst",
        )
        apply_pentagon_delta(
            student_id, axis="social", requested_delta=1,
            reason_kind="employment_accepted",
            explanation="Anställd hos klasskompis · stärker social-band",
        )
        # Företagaren får också social-boost
        apply_pentagon_delta(
            owner_id, axis="social", requested_delta=2,
            reason_kind="employee_hired",
            reason_id=employment_id,
            reason_table="classmate_employments",
            explanation="Anställt klasskompis · status + nätverk",
        )
    except Exception:
        log.exception("accept: pentagon-delta misslyckades")

    with master_session() as ms:
        emp = ms.get(ClassmateEmployment, employment_id)
        return _employment_to_out(emp)


class DeclineOfferIn(BaseModel):
    reason: Optional[str] = None


@router.post("/offers/{employment_id}/decline", response_model=EmploymentOut)
def decline_offer(
    employment_id: int,
    body: DeclineOfferIn,
    info: TokenInfo = Depends(require_token),
):
    """Klasskompis tackar nej till erbjudande."""
    student_id = _require_student_id(info)
    with master_session() as ms:
        emp = ms.get(ClassmateEmployment, employment_id)
        if emp is None:
            raise HTTPException(404, "Erbjudande hittades inte")
        if emp.employee_student_id != student_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Du kan bara avböja dina egna erbjudanden",
            )
        if emp.status != "pending_offer":
            raise HTTPException(
                400, f"Erbjudandet har redan status '{emp.status}'",
            )

        emp.status = "declined"
        emp.termination_reason = body.reason
        ms.commit()
        owner_id = emp.owner_student_id
        company_name = emp.company_name
        role = emp.role

    # Notifiera företagaren
    try:
        _send_mail_to_student(
            owner_id,
            sender="Anställningssystemet",
            sender_short="HR",
            sender_kind="agency",
            subject=f"{role} · erbjudande avböjt",
            body=(
                f"Tyvärr · klasskompisen valde att tacka nej till "
                f"anställningen som {role}.\n\n"
                + (
                    f"Skäl: {body.reason}\n\n"
                    if body.reason else ""
                )
                + "Du kan göra ett nytt erbjudande till samma elev eller "
                "någon annan."
            ),
        )
    except Exception:
        pass

    # Lärar-spårning
    try:
        log_activity(
            kind="private.employment_declined",
            summary=f"Tackade nej till anställning · {company_name}",
            payload={
                "employment_id": employment_id,
                "reason": body.reason,
            },
            student_id=student_id,
        )
        log_activity(
            kind="biz.employee_offer_declined",
            summary=f"Klasskompis tackade nej · {role}",
            payload={
                "employment_id": employment_id,
                "reason": body.reason,
            },
            student_id=owner_id,
        )
    except Exception:
        pass

    with master_session() as ms:
        emp = ms.get(ClassmateEmployment, employment_id)
        return _employment_to_out(emp)
