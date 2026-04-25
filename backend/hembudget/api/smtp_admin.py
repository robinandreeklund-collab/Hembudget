"""Super-admin-endpoints för SMTP-config.

Ger super-admin UI för att sätta Gmail app-password (eller annan
SMTP-server) via webben istället för att redeploya med env-vars.

Konfiguration sparas i master-DB:n under nyckeln SMTP_CONFIG_KEY.
DB-värdet vinner över env-vars i security/email.py — så man kan
byta utan omstart.

Endpoints:
- GET    /admin/smtp/config — visa aktiv config + källa (db/env)
- POST   /admin/smtp/config — spara/uppdatera config
- DELETE /admin/smtp/config — rensa DB-config (faller ev. tillbaka till env)
- POST   /admin/smtp/test   — skicka ett testmail till godtycklig adress
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from ..school import is_enabled as school_enabled
from ..school.engines import master_session
from ..school.models import AppConfig, Teacher
from ..security import email as email_mod
from .deps import TokenInfo, require_teacher

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/smtp", tags=["admin-smtp"])


def _require_super_admin(
    info: TokenInfo = Depends(require_teacher),
) -> TokenInfo:
    if not school_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "School mode inaktivt")
    with master_session() as s:
        t = s.get(Teacher, info.teacher_id)
        if not t or not t.is_super_admin:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Super-admin krävs",
            )
    return info


# ---------- Schemas ----------

class SmtpConfigOut(BaseModel):
    configured: bool
    source: str  # "db" | "env" | ""
    host: str
    port: int
    user: str
    password_set: bool        # exponera ALDRIG lösenordet — bara om det finns
    password_preview: str     # "•••• ••••" eller tom
    starttls: bool
    mail_from: str
    mail_from_name: str
    public_base_url: str


class SmtpConfigIn(BaseModel):
    host: str = Field(min_length=3, max_length=200)
    port: int = Field(default=587, ge=1, le=65535)
    user: str = Field(min_length=3, max_length=200)
    # Om None lämnas befintligt lösenord oförändrat (så man kan
    # uppdatera host/port utan att skriva om appass varje gång).
    password: str | None = None
    starttls: bool = True
    mail_from: EmailStr
    mail_from_name: str = Field(default="Ekonomilabbet", max_length=80)
    public_base_url: str = Field(default="", max_length=200)


class SmtpTestIn(BaseModel):
    to: EmailStr


# ---------- Hjälpare ----------

def _build_status() -> SmtpConfigOut:
    cfg = email_mod._effective_config()
    pw = cfg["password"] or ""
    return SmtpConfigOut(
        configured=email_mod.is_configured(),
        source=email_mod.config_source(),
        host=str(cfg["host"] or ""),
        port=int(cfg["port"] or 587),
        user=str(cfg["user"] or ""),
        password_set=bool(pw),
        password_preview="•••• ••••" if pw else "",
        starttls=bool(cfg["starttls"]),
        mail_from=str(cfg["mail_from"] or ""),
        mail_from_name=str(cfg["mail_from_name"] or "Ekonomilabbet"),
        public_base_url=str(cfg["public_base_url"] or ""),
    )


# ---------- Endpoints ----------

@router.get("/config", response_model=SmtpConfigOut)
def get_smtp_config(
    _: TokenInfo = Depends(_require_super_admin),
) -> SmtpConfigOut:
    return _build_status()


@router.post("/config", response_model=SmtpConfigOut)
def set_smtp_config(
    payload: SmtpConfigIn,
    _: TokenInfo = Depends(_require_super_admin),
) -> SmtpConfigOut:
    """Spara SMTP-config i DB. Lösenordet är optional vid update —
    om None behålls befintligt."""
    with master_session() as s:
        cfg = s.get(AppConfig, email_mod.SMTP_CONFIG_KEY)
        old: dict = {}
        if cfg and isinstance(cfg.value, dict):
            old = dict(cfg.value)

        new_pw = payload.password
        if new_pw is None:
            # Behåll gammalt om det finns
            new_pw = old.get("password", "")
        new_pw = (new_pw or "").strip()

        new_value = {
            "host": payload.host.strip(),
            "port": int(payload.port),
            "user": payload.user.strip(),
            "password": new_pw,
            "starttls": bool(payload.starttls),
            "mail_from": str(payload.mail_from),
            "mail_from_name": payload.mail_from_name.strip() or "Ekonomilabbet",
            "public_base_url": payload.public_base_url.strip(),
        }
        if cfg is None:
            s.add(AppConfig(key=email_mod.SMTP_CONFIG_KEY, value=new_value))
        else:
            cfg.value = new_value
            cfg.updated_at = datetime.utcnow()
    return _build_status()


@router.delete("/config", response_model=SmtpConfigOut)
def clear_smtp_config(
    _: TokenInfo = Depends(_require_super_admin),
) -> SmtpConfigOut:
    """Rensa DB-config. Email-flödet faller tillbaka till env-vars
    om sådana finns, annars blir is_configured() False."""
    with master_session() as s:
        cfg = s.get(AppConfig, email_mod.SMTP_CONFIG_KEY)
        if cfg is not None:
            s.delete(cfg)
    return _build_status()


@router.post("/test")
def send_test_mail(
    payload: SmtpTestIn,
    _: TokenInfo = Depends(_require_super_admin),
) -> dict:
    """Skicka ett testmail till given adress. Använder aktiv config
    (DB om satt, annars env). Hjälper super-admin att verifiera att
    Gmail-app-password fungerar utan att triggera ett riktigt
    signup-flöde."""
    if not email_mod.is_configured():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SMTP är inte konfigurerat — fyll i config först.",
        )
    subject = "Ekonomilabbet — testmail"
    text = (
        "Det här är ett testmail från Ekonomilabbet.\n\n"
        "Om du läser det här fungerar SMTP-konfigurationen och du kan "
        "fortsätta använda signup-/reset-flödet.\n\n"
        "— Ekonomilabbet"
    )
    html = (
        '<div style="font-family:Arial,sans-serif;max-width:520px;'
        'margin:0 auto;padding:24px;color:#222;">'
        '<div style="font-family:Spectral,serif;font-weight:800;'
        'font-size:22px;margin-bottom:14px;">Ekonomilabbet — testmail</div>'
        "<p>Det här är ett testmail. Om du läser det fungerar "
        "SMTP-konfigurationen.</p>"
        "<p style=\"color:#666;font-size:13px;\">Skickat manuellt av "
        "super-admin via /admin/smtp/test.</p>"
        "</div>"
    )
    try:
        email_mod.send_mail(
            to=str(payload.to), subject=subject, html=html, text=text,
        )
    except email_mod.EmailNotConfigured as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        log.exception("smtp-test misslyckades")
        # Klassificera vanliga fel så super-admin direkt ser vad som
        # är problemet — SMTPLib-undantag har specifika klassnamn vi kan
        # mönstermatcha mot.
        cls = type(e).__name__
        msg = str(e)
        hint = ""
        low = (msg + " " + cls).lower()
        if "authentication" in low or "username and password" in low or "535" in msg:
            hint = (
                "Inloggningen avvisades. Kolla att du använder ett Gmail "
                "APP-PASSWORD (16 tecken utan mellanslag) — vanligt Gmail-"
                "lösen funkar INTE via SMTP. Skapa app-password på "
                "https://myaccount.google.com/apppasswords (kräver 2-stegs)."
            )
        elif "name or service not known" in low or "getaddrinfo" in low:
            hint = (
                "Kunde inte slå upp SMTP-host. Kolla att host:en är skriven "
                "rätt (för Gmail: smtp.gmail.com)."
            )
        elif "connection refused" in low or "connectionrefused" in low:
            hint = (
                "Servern svarade inte på den porten. Gmail använder 587 "
                "med STARTTLS eller 465 med SSL — kolla att port + STARTTLS-"
                "flaggan stämmer ihop."
            )
        elif "ssl" in low or "wrap_socket" in low or "certificate" in low:
            hint = (
                "TLS-handshake misslyckades. För Gmail port 587: ha STARTTLS "
                "PÅ. För port 465: ha STARTTLS AV (då används implicit SSL)."
            )
        elif "timed out" in low or "timeout" in low:
            hint = (
                "Anslutningen tog för lång tid. Cloud Run kan blockera "
                "utgående SMTP — testa från lokal körning först, eller "
                "använd en HTTP-baserad SMTP-relay (SendGrid, Postmark)."
            )
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": f"SMTP-fel ({cls}): {msg}",
                "hint": hint,
            },
        )
    return {"ok": True, "to": str(payload.to)}
