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

import hashlib
from decimal import Decimal

from ..business.game_clock import current_game_date
from ..business.models import Company, CompanyTransaction
from ..business.service import EMPLOYER_FEE_DEFAULT
from ..db.base import session_scope
from ..db.models import Account, MailItem, Transaction as PrivTransaction
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


# ===========================================================
# Endpoints · Terminate (Fas E)
# ===========================================================


class TerminateIn(BaseModel):
    reason: str = Field(..., min_length=5, max_length=400)


@router.post(
    "/employments/{employment_id}/terminate",
    response_model=EmploymentOut,
)
def terminate_employment(
    employment_id: int,
    body: TerminateIn,
    info: TokenInfo = Depends(require_token),
):
    """Företagaren säger upp en klasskompis-anställning.

    30 dgrs LAS-uppsägningstid · last_day sätts till today_g + 30 dgr.
    ClassmateEmployment.status = 'terminated' direkt så payroll-endpointen
    slutar betala. StudentProfile.employment_end_on uppdateras så
    salary_phase också skippar lön efter sista dag.
    """
    owner_id = _require_student_id(info)
    today_g = current_game_date()
    last_day = today_g + timedelta(days=30)

    with master_session() as ms:
        emp = ms.get(ClassmateEmployment, employment_id)
        if emp is None:
            raise HTTPException(404, "Anställning hittades inte")
        if emp.owner_student_id != owner_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Du kan bara säga upp dina egna anställda",
            )
        if emp.status != "active":
            raise HTTPException(
                400,
                f"Anställningen är inte aktiv (status='{emp.status}')",
            )

        employee_id = emp.employee_student_id
        company_name = emp.company_name
        role = emp.role
        gross = emp.monthly_gross

        emp.status = "terminated"
        emp.last_day = last_day
        emp.termination_reason = body.reason
        emp.terminated_company_name = company_name

        # Uppdatera den anställdes profil så salary_phase fasar ut lönen
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == employee_id)
            .first()
        )
        if prof is not None:
            # Sätt status='unemployed' med end_on så lönen betalas till
            # och med last_day men inte längre.
            prof.employment_status = "unemployed"
            prof.employment_end_on = last_day
        ms.commit()

    # Formellt uppsägningsbrev till klasskompis
    try:
        _send_mail_to_student(
            employee_id,
            sender=company_name,
            sender_short=company_name[:4],
            sender_kind="agency",
            subject=f"Uppsägningsbesked · {company_name}",
            body_meta=f"Sista dag {last_day.isoformat()}",
            body=(
                f"Uppsägningsbesked enligt 8 § lagen (1982:80) om "
                f"anställningsskydd (LAS).\n\n"
                f"Härmed sägs din anställning som **{role}** vid "
                f"**{company_name}** upp.\n\n"
                f"· Uppsägningstid: 30 dagar (LAS § 11)\n"
                f"· Sista anställningsdag: {last_day.isoformat()}\n"
                f"· Lön och förmåner utgår oförändrat under "
                f"uppsägningstiden\n"
                f"· Företrädesrätt vid återanställning: 9 månader "
                f"(LAS § 25)\n\n"
                f"Skäl till uppsägning:\n{body.reason}\n\n"
                f"Du har rätt att begära skriftlig bekräftelse av detta "
                f"besked samt rätt att ogiltigförklara uppsägningen "
                f"genom att vända dig till facket eller domstol.\n\n"
                f"Lycka till framöver.\n\n"
                f"{company_name}"
            ),
            mail_type="authority",
        )
    except Exception:
        log.exception("terminate: brev till anställd misslyckades")

    # Lärar-spårning
    try:
        log_activity(
            kind="biz.employee_terminated",
            summary=f"Sade upp {role} · sista dag {last_day.isoformat()}",
            payload={
                "employment_id": employment_id,
                "employee_student_id": employee_id,
                "last_day": last_day.isoformat(),
                "reason": body.reason,
                "monthly_gross": gross,
            },
            student_id=owner_id,
        )
        log_activity(
            kind="private.terminated_by_employer",
            summary=f"Uppsagd från {company_name} · {role}",
            payload={
                "employment_id": employment_id,
                "company_name": company_name,
                "last_day": last_day.isoformat(),
                "reason": body.reason,
            },
            student_id=employee_id,
        )
    except Exception:
        pass

    # Pentagon
    try:
        from ..game_engine.pentagon import apply_pentagon_delta
        # Anställd · stor smäll på säkerhet + ekonomi
        apply_pentagon_delta(
            employee_id, axis="safety", requested_delta=-5,
            reason_kind="terminated",
            reason_id=employment_id,
            reason_table="classmate_employments",
            explanation=f"Uppsagd från {company_name}",
        )
        apply_pentagon_delta(
            employee_id, axis="economy", requested_delta=-3,
            reason_kind="terminated",
            reason_id=employment_id,
            reason_table="classmate_employments",
            explanation="Förlorade inkomst · uppsagd",
        )
        apply_pentagon_delta(
            employee_id, axis="social", requested_delta=-2,
            reason_kind="terminated",
            explanation="Social konflikt · uppsagd av klasskompis",
        )
        # Företagaren · liten social-smäll
        apply_pentagon_delta(
            owner_id, axis="social", requested_delta=-2,
            reason_kind="terminated_classmate",
            reason_id=employment_id,
            reason_table="classmate_employments",
            explanation="Sade upp klasskompis · social konsekvens",
        )
    except Exception:
        log.exception("terminate: pentagon-delta misslyckades")

    with master_session() as ms:
        emp = ms.get(ClassmateEmployment, employment_id)
        return _employment_to_out(emp)


# ===========================================================
# Endpoints · Payroll-run (Fas D)
# ===========================================================


def _employment_payroll_hash(employment_id: int, year_month: str) -> str:
    raw = f"classmate_payroll|{employment_id}|{year_month}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _build_payslip_body(
    *, employee_name: str, role: str, company_name: str,
    gross: int, prel_tax: int, net: int,
    employer_fee: int, year_month: str,
) -> str:
    return (
        f"Lönespec {year_month}\n\n"
        f"Anställd: {employee_name}\n"
        f"Befattning: {role}\n"
        f"Arbetsgivare: {company_name}\n\n"
        f"Bruttolön                      {gross:>10,} kr\n".replace(",", " ")
        + f"Prel. A-skatt (30 %)           {prel_tax:>10,} kr\n".replace(",", " ")
        + f"------------------------------ -----------\n"
        + f"Nettolön (utbetalas 25:e)      {net:>10,} kr\n".replace(",", " ")
        + f"\n"
        + f"(Arbetsgivaravgift {employer_fee:,} kr betalas av {company_name})"
        .replace(",", " ")
    )


def _pay_one_employee_in_scope(
    emp: ClassmateEmployment,
    *,
    year_month: str,
    paid_on: date,
) -> dict:
    """Skapa lönespec + lön-in-tx i den ANSTÄLLDES scope-DB. Anropas
    inom scope_context(employee_scope). Idempotent via hash."""
    gross = emp.monthly_gross
    prel_tax_d = (Decimal(gross) * Decimal("0.30")).quantize(Decimal("1"))
    prel_tax = int(prel_tax_d)
    net = gross - prel_tax
    fee_d = (Decimal(gross) * EMPLOYER_FEE_DEFAULT).quantize(Decimal("1"))
    employer_fee = int(fee_d)

    tx_hash = _employment_payroll_hash(emp.id, year_month)

    with session_scope() as scope_s:
        existing_tx = (
            scope_s.query(PrivTransaction)
            .filter(PrivTransaction.hash == tx_hash)
            .first()
        )
        if existing_tx is not None:
            return {
                "employment_id": emp.id,
                "status": "already_paid",
                "net": net,
            }

        acc = (
            scope_s.query(Account)
            .filter(Account.type == "checking")
            .order_by(Account.id.asc())
            .first()
        )
        if acc is None:
            return {
                "employment_id": emp.id,
                "status": "skipped_no_account",
                "net": net,
            }

        scope_s.add(PrivTransaction(
            account_id=acc.id,
            date=paid_on,
            amount=Decimal(net),
            currency="SEK",
            raw_description=(
                f"Lön {year_month} · {emp.role} · {emp.company_name}"
            ),
            normalized_merchant=emp.company_name,
            hash=tx_hash,
            user_verified=True,
        ))

        body = _build_payslip_body(
            employee_name=f"#{emp.employee_student_id}",
            role=emp.role,
            company_name=emp.company_name,
            gross=gross,
            prel_tax=prel_tax,
            net=net,
            employer_fee=employer_fee,
            year_month=year_month,
        )
        received_at = datetime.combine(
            paid_on, datetime.min.time(),
        ).replace(hour=9)
        scope_s.add(MailItem(
            sender=emp.company_name,
            sender_short=emp.company_name[:4].upper(),
            sender_kind="work",
            sender_meta=f"lönespec · {year_month}",
            mail_type="salary_slip",
            subject=f"Lönespec {year_month} · {emp.company_name}",
            body_meta=f"Nettolön {net:,} kr".replace(",", " "),
            body=body,
            amount=Decimal(net),
            due_date=paid_on,
            status="unhandled",
            received_at=received_at,
        ))

    return {
        "employment_id": emp.id,
        "status": "paid",
        "gross": gross,
        "net": net,
        "employer_fee": employer_fee,
    }


def _book_payroll_in_owner_scope(
    *,
    company_id: int,
    paid_on: date,
    total_cost: int,
    n_employees: int,
    year_month: str,
) -> None:
    """Bokför löneutbetalningen som CompanyTransaction (kind=salary)
    i ägarens scope-DB. Idempotent via notes-marker."""
    with session_scope() as s:
        marker = f"classmate_payroll|{year_month}"
        existing = (
            s.query(CompanyTransaction)
            .filter(
                CompanyTransaction.company_id == company_id,
                CompanyTransaction.kind == "salary",
                CompanyTransaction.notes == marker,
            )
            .first()
        )
        if existing is not None:
            return
        s.add(CompanyTransaction(
            company_id=company_id,
            occurred_on=paid_on,
            kind="salary",
            category="Klasskompis-löner",
            description=(
                f"Löner {year_month} · {n_employees} anställda klasskompisar"
            ),
            amount_excl_vat=Decimal(total_cost),
            vat_rate=Decimal("0.0"),
            vat_amount=Decimal("0.0"),
            notes=marker,
        ))


class PayrollRunOut(BaseModel):
    year_month: str
    paid_on: date
    n_paid: int
    n_skipped: int
    total_gross: int
    total_net: int
    total_employer_fee: int
    total_cost: int
    details: list[dict]


@router.post("/payroll/run", response_model=PayrollRunOut)
def run_classmate_payroll(
    year_month: Optional[str] = None,
    info: TokenInfo = Depends(require_token),
):
    """Kör månadens lön för alla aktiva klasskompis-anställningar.

    Idempotent · samma year_month två gånger är no-op (markerar
    redan-betalda som 'already_paid').

    `year_month`: "YYYY-MM" — default nuvarande spel-månad.
    """
    owner_id = _require_student_id(info)
    today_g = current_game_date()
    if year_month is None:
        ym = today_g.strftime("%Y-%m")
    else:
        ym = year_month
    try:
        y_s, m_s = ym.split("-")
        paid_on = date(int(y_s), int(m_s), 25)
    except (ValueError, TypeError):
        raise HTTPException(400, "year_month måste vara YYYY-MM")

    co = _get_owner_active_company(owner_id)
    if co is None:
        raise HTTPException(409, "Du har inget aktivt bolag")
    company_id = co.id
    company_name = co.name

    with master_session() as ms:
        actives = (
            ms.query(ClassmateEmployment)
            .filter(
                ClassmateEmployment.owner_student_id == owner_id,
                ClassmateEmployment.status == "active",
            )
            .all()
        )
        snapshots = [
            {
                "id": e.id,
                "employee_student_id": e.employee_student_id,
                "role": e.role,
                "monthly_gross": e.monthly_gross,
                "company_name": e.company_name,
            }
            for e in actives
        ]

    details: list[dict] = []
    total_gross = 0
    total_net = 0
    total_fee = 0
    n_paid = 0
    n_skipped = 0

    for snap in snapshots:
        proxy = ClassmateEmployment(
            id=snap["id"],
            owner_student_id=owner_id,
            company_id=company_id,
            company_name=snap["company_name"],
            employee_student_id=snap["employee_student_id"],
            role=snap["role"],
            monthly_gross=snap["monthly_gross"],
            status="active",
        )
        with master_session() as ms:
            stu = ms.get(Student, snap["employee_student_id"])
            if stu is None:
                n_skipped += 1
                details.append({
                    "employment_id": snap["id"],
                    "status": "skipped_student_missing",
                })
                continue
            employee_scope = scope_for_student(stu)

        try:
            with scope_context(employee_scope):
                result = _pay_one_employee_in_scope(
                    proxy, year_month=ym, paid_on=paid_on,
                )
        except Exception:
            log.exception(
                "payroll: _pay_one_employee misslyckades · emp=%s",
                snap["id"],
            )
            n_skipped += 1
            details.append({"employment_id": snap["id"], "status": "error"})
            continue

        details.append(result)
        if result["status"] == "paid":
            n_paid += 1
            total_gross += result["gross"]
            total_net += result["net"]
            total_fee += result["employer_fee"]
        else:
            n_skipped += 1

    total_cost = total_gross + total_fee

    if n_paid > 0:
        try:
            owner_scope = None
            with master_session() as ms:
                ostu = ms.get(Student, owner_id)
                if ostu is not None:
                    owner_scope = scope_for_student(ostu)
            if owner_scope is not None:
                with scope_context(owner_scope):
                    _book_payroll_in_owner_scope(
                        company_id=company_id,
                        paid_on=paid_on,
                        total_cost=total_cost,
                        n_employees=n_paid,
                        year_month=ym,
                    )
        except Exception:
            log.exception(
                "payroll: bokföring i ägar-scope misslyckades",
            )

    try:
        log_activity(
            kind="biz.payroll_run",
            summary=(
                f"Körde lön {ym} · {n_paid} klasskompisar · "
                f"totalkost {total_cost} kr"
            ),
            payload={
                "year_month": ym,
                "n_paid": n_paid,
                "total_cost": total_cost,
                "company_name": company_name,
            },
            student_id=owner_id,
        )
    except Exception:
        pass

    return PayrollRunOut(
        year_month=ym,
        paid_on=paid_on,
        n_paid=n_paid,
        n_skipped=n_skipped,
        total_gross=total_gross,
        total_net=total_net,
        total_employer_fee=total_fee,
        total_cost=total_cost,
        details=details,
    )
