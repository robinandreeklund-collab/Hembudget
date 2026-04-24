"""E-post-baserad auth: öppen lärar-signup, e-post-verifiering, lösenords-
återställning.

Ligger separerat från school.py (som är > 2700 rader) för tydlighetens
skull. Alla endpoints kräver school-läge — i desktop-läge saknar de mening.

Flöden:
1) POST /teacher/signup
   - skapa ny lärare med email_verified_at=NULL
   - skicka verifieringsmail med engångs-token (24 h TTL)
   - returnera { ok: True } (ingen inloggning — måste verifiera först)

2) GET /teacher/verify-email?token=...
   - sätt email_verified_at, markera token used_at
   - idempotent (andra klick ger 410)

3) POST /teacher/request-verify-resend { email }
   - om kontot finns + ej verifierat → skicka ny token, invalidera gamla
   - alltid 204 oavsett om kontot finns (hindrar enumeration)

4) POST /teacher/request-password-reset { email }
   - om kontot finns → skicka reset-token (60 min TTL)
   - alltid 204 oavsett om kontot finns (enumeration-skydd)

5) POST /teacher/reset-password { token, password }
   - validera token → byt lösenord → markera token used_at
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from ..config import settings
from ..school import is_enabled as school_enabled
from ..school.engines import master_session
from ..school.models import EmailToken, Teacher
from ..security.crypto import hash_password, random_token
from ..security.email import (
    EmailNotConfigured,
    render_reset_email,
    render_verify_email,
    send_mail,
    token_hash,
)
from ..security.rate_limit import (
    RULES_PASSWORD_RESET_REQUEST,
    RULES_SIGNUP,
    RULES_VERIFY_RESEND,
    check_rate_limit,
    verify_turnstile,
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["email-auth"])


# Tokens gäller:
VERIFY_TTL_HOURS = 24
RESET_TTL_MINUTES = 60


# ---------- Utility ----------

def _require_school_mode() -> None:
    if not school_enabled():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Endpoint är endast tillgänglig i school-läge",
        )


def _require_email_configured() -> None:
    from ..security.email import is_configured
    if not is_configured():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "E-postutskick är inte konfigurerat på servern.",
        )


def _build_url(request: Request, path: str) -> str:
    """Publik URL för länkar i mail. Prioritet:
    1. settings.public_base_url (satt i prod)
    2. request-headern (Cloudflare sätter host korrekt)
    """
    base = settings.public_base_url.rstrip("/") if settings.public_base_url else ""
    if not base:
        # Forwarded proto + host om Cloudflare är framför
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.headers.get(
            "host", ""
        )
        if host:
            base = f"{proto}://{host}"
        else:
            base = str(request.base_url).rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def _issue_token(
    session, teacher_id: int, kind: str, ttl: timedelta,
) -> str:
    """Skapa engångs-token. Invalidera äldre oförbrukade tokens av samma
    kind så bara senaste länken fungerar."""
    now = datetime.utcnow()
    # Markera äldre tokens som "used" (de fungerar inte längre)
    (
        session.query(EmailToken)
        .filter(
            EmailToken.teacher_id == teacher_id,
            EmailToken.kind == kind,
            EmailToken.used_at.is_(None),
        )
        .update({"used_at": now}, synchronize_session=False)
    )
    raw = random_token(32)
    session.add(
        EmailToken(
            teacher_id=teacher_id,
            kind=kind,
            token_hash=token_hash(raw),
            expires_at=now + ttl,
        )
    )
    return raw


def _consume_token(
    session, raw_token: str, kind: str,
) -> EmailToken:
    """Slå upp, validera, markera förbrukad. Kastar 410/404 vid fel."""
    th = token_hash(raw_token)
    et = (
        session.query(EmailToken)
        .filter(
            EmailToken.token_hash == th,
            EmailToken.kind == kind,
        )
        .first()
    )
    if et is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Länken är ogiltig.",
        )
    if et.used_at is not None:
        raise HTTPException(
            status.HTTP_410_GONE,
            "Länken har redan använts. Be om en ny om det behövs.",
        )
    if et.expires_at < datetime.utcnow():
        raise HTTPException(
            status.HTTP_410_GONE,
            "Länken har gått ut. Be om en ny.",
        )
    et.used_at = datetime.utcnow()
    return et


def _send_verify(
    session, request: Request, teacher: Teacher,
) -> None:
    _require_email_configured()
    raw = _issue_token(
        session, teacher.id, "verify", timedelta(hours=VERIFY_TTL_HOURS),
    )
    url = _build_url(request, f"/verify-email?token={raw}")
    subject, html, text = render_verify_email(url, teacher.name)
    try:
        send_mail(to=teacher.email, subject=subject, html=html, text=text)
    except EmailNotConfigured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "E-postutskick är inte konfigurerat på servern.",
        )
    except Exception as e:
        log.exception("SMTP-fel vid verify-mail till %s", teacher.email)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Kunde inte skicka mail just nu: {e}",
        )


def _send_reset(
    session, request: Request, teacher: Teacher,
) -> None:
    _require_email_configured()
    raw = _issue_token(
        session, teacher.id, "reset", timedelta(minutes=RESET_TTL_MINUTES),
    )
    url = _build_url(request, f"/reset-password?token={raw}")
    subject, html, text = render_reset_email(url, teacher.name)
    try:
        send_mail(to=teacher.email, subject=subject, html=html, text=text)
    except EmailNotConfigured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "E-postutskick är inte konfigurerat på servern.",
        )
    except Exception as e:
        log.exception("SMTP-fel vid reset-mail till %s", teacher.email)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Kunde inte skicka mail just nu: {e}",
        )


# ---------- Schemas ----------

class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=160)


class ResendIn(BaseModel):
    email: EmailStr


class ResetRequestIn(BaseModel):
    email: EmailStr


class ResetSubmitIn(BaseModel):
    token: str = Field(min_length=10)
    password: str = Field(min_length=8)


class SimpleOkOut(BaseModel):
    ok: bool = True


# ---------- Endpoints ----------

@router.post("/teacher/signup", response_model=SimpleOkOut)
def teacher_signup(payload: SignupIn, request: Request) -> SimpleOkOut:
    """Öppen registrering av nytt lärarkonto. Läraren måste bekräfta
    e-post innan den kan logga in.

    Bootstrap-flödet i school.py är fortfarande separat — det används
    för FÖRSTA läraren (super-admin) medan denna endpoint är för alla
    efterföljande lärare som själva skaffar konto.
    """
    _require_school_mode()
    _require_email_configured()
    check_rate_limit(request, "teacher-signup", RULES_SIGNUP)
    verify_turnstile(request, required=True)

    email = payload.email.lower()
    with master_session() as s:
        existing = s.query(Teacher).filter(Teacher.email == email).first()
        if existing is not None:
            # Vi vill undvika att läcka om mailen redan finns. Svara OK
            # men skicka inget mail (användaren kan be om lösenords-
            # återställning i så fall). Rate-limiten hindrar spam.
            return SimpleOkOut(ok=True)

        teacher = Teacher(
            email=email,
            name=payload.name.strip(),
            password_hash=hash_password(payload.password),
            email_verified_at=None,
        )
        s.add(teacher)
        s.flush()
        _send_verify(s, request, teacher)
    return SimpleOkOut(ok=True)


@router.post("/teacher/request-verify-resend", response_model=SimpleOkOut)
def request_verify_resend(
    payload: ResendIn, request: Request,
) -> SimpleOkOut:
    """Skicka ett nytt verifieringsmail. Alltid 200 — ingen enum."""
    _require_school_mode()
    check_rate_limit(request, "verify-resend", RULES_VERIFY_RESEND)
    verify_turnstile(request, required=True)

    email = payload.email.lower()
    with master_session() as s:
        teacher = s.query(Teacher).filter(Teacher.email == email).first()
        if teacher is not None and teacher.email_verified_at is None:
            _send_verify(s, request, teacher)
    return SimpleOkOut(ok=True)


@router.get("/teacher/verify-email", response_model=SimpleOkOut)
def verify_email(token: str, request: Request) -> SimpleOkOut:
    """Klicka-länk: sätter email_verified_at."""
    _require_school_mode()
    if not token or len(token) < 10:
        raise HTTPException(400, "Ogiltig token")
    with master_session() as s:
        et = _consume_token(s, token, "verify")
        teacher = s.query(Teacher).filter(Teacher.id == et.teacher_id).first()
        if teacher is None:
            raise HTTPException(404, "Kontot finns inte längre.")
        if teacher.email_verified_at is None:
            teacher.email_verified_at = datetime.utcnow()
    return SimpleOkOut(ok=True)


@router.post("/teacher/request-password-reset", response_model=SimpleOkOut)
def request_password_reset(
    payload: ResetRequestIn, request: Request,
) -> SimpleOkOut:
    _require_school_mode()
    check_rate_limit(
        request, "password-reset-request", RULES_PASSWORD_RESET_REQUEST,
    )
    verify_turnstile(request, required=True)

    email = payload.email.lower()
    with master_session() as s:
        teacher = s.query(Teacher).filter(Teacher.email == email).first()
        if teacher is not None and teacher.active:
            _send_reset(s, request, teacher)
    # Svara alltid OK — vi vill inte avslöja om mailen finns eller inte.
    return SimpleOkOut(ok=True)


@router.post("/teacher/reset-password", response_model=SimpleOkOut)
def reset_password(payload: ResetSubmitIn, request: Request) -> SimpleOkOut:
    _require_school_mode()
    # Separat bucket för själva sändningen så en angripare inte kan
    # brute-forca tokens förbi rate-limiten på "request".
    check_rate_limit(
        request, "password-reset-submit", RULES_PASSWORD_RESET_REQUEST,
    )
    with master_session() as s:
        et = _consume_token(s, payload.token, "reset")
        teacher = s.query(Teacher).filter(Teacher.id == et.teacher_id).first()
        if teacher is None:
            raise HTTPException(404, "Kontot finns inte längre.")
        teacher.password_hash = hash_password(payload.password)
        # Efter reset anses mailen verifierad (bara användaren har
        # tillgång till inkorgen).
        if teacher.email_verified_at is None:
            teacher.email_verified_at = datetime.utcnow()
    return SimpleOkOut(ok=True)
