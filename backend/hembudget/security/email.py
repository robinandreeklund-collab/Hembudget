"""SMTP-baserad transaktionell mailare för school-läget.

Används för:
- Verifiering av nya lärarregistreringar
- Lösenords-återställning

Design:
- Stdlib smtplib + email.message. Inga extra deps.
- Konfigureras via HEMBUDGET_SMTP_* i env/config. Utan smtp_host satt
  kastar send_mail() EmailNotConfigured — endpoints översätter till 503
  så det är tydligt att funktionen är avstängd, inte trasig.
- Prod: Gmail via app password (smtp.gmail.com:587 + STARTTLS).
- Tokens i länkar är råa strängar; DB lagrar SHA-256-hash så att en
  master.db-dump inte exponerar aktiva tokens.
"""
from __future__ import annotations

import hashlib
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from ..config import settings

log = logging.getLogger(__name__)

# AppConfig-nyckel där super-admins UI sparar SMTP-config (DB vinner
# över env-vars så man kan byta utan att redeploya). Strukturen är:
#   {"host": "...", "port": 587, "user": "...", "password": "...",
#    "starttls": true, "mail_from": "...", "mail_from_name": "...",
#    "public_base_url": "..."}
SMTP_CONFIG_KEY = "smtp_config"


class EmailNotConfigured(RuntimeError):
    """SMTP är inte konfigurerat. Endpoints som kräver mail ska omvandla
    detta till HTTP 503."""


def _read_db_config() -> dict | None:
    """Försök läsa SMTP-config från master-DB:n. Returnerar None om
    school-läge inte är på eller om inget värde finns."""
    try:
        from ..school.engines import master_session
        from ..school.models import AppConfig
        with master_session() as s:
            cfg = s.get(AppConfig, SMTP_CONFIG_KEY)
            if cfg and isinstance(cfg.value, dict):
                return dict(cfg.value)
    except Exception:
        # DB-läsning får aldrig krascha mail-flödet — falla tillbaka
        # till env tyst.
        log.exception("email: kunde inte läsa SMTP-config från DB")
    return None


def _effective_config() -> dict:
    """Slå ihop env (settings) + DB. DB vinner per fält."""
    db = _read_db_config() or {}
    return {
        "host": db.get("host") or settings.smtp_host,
        "port": db.get("port") or settings.smtp_port,
        "user": db.get("user") or settings.smtp_user,
        "password": db.get("password") or settings.smtp_password,
        "starttls": db.get("starttls", settings.smtp_starttls),
        "mail_from": db.get("mail_from") or settings.mail_from,
        "mail_from_name": db.get("mail_from_name") or settings.mail_from_name,
        "public_base_url": db.get("public_base_url") or settings.public_base_url,
    }


def is_configured() -> bool:
    cfg = _effective_config()
    return bool(cfg["host"] and cfg["user"] and cfg["mail_from"])


def config_source() -> str:
    """'db' om DB-config aktivt sätter host, 'env' om bara env-var, '' annars."""
    db = _read_db_config()
    if db and db.get("host"):
        return "db"
    if settings.smtp_host:
        return "env"
    return ""


def _from_header() -> str:
    cfg = _effective_config()
    name = cfg["mail_from_name"] or "Ekonomilabbet"
    return formataddr((name, cfg["mail_from"]))


def send_mail(*, to: str, subject: str, html: str, text: str) -> None:
    """Skicka mail. Kastar EmailNotConfigured om SMTP inte är inställt."""
    if not is_configured():
        raise EmailNotConfigured(
            "SMTP är inte konfigurerat (sätt det via super-admin eller "
            "HEMBUDGET_SMTP_HOST m.fl.)."
        )

    cfg = _effective_config()
    msg = EmailMessage()
    msg["From"] = _from_header()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    host = str(cfg["host"])
    port = int(cfg["port"])
    user = str(cfg["user"])
    pw = str(cfg["password"] or "")
    use_tls = bool(cfg["starttls"])

    # Gmail: STARTTLS på 587. Implicit TLS (465) hanteras av SMTP_SSL —
    # vi stöder båda via flaggan.
    if port == 465 and not use_tls:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as s:
            if user:
                s.login(user, pw)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.ehlo()
            if use_tls:
                context = ssl.create_default_context()
                s.starttls(context=context)
                s.ehlo()
            if user:
                s.login(user, pw)
            s.send_message(msg)

    log.info("Skickade mail till %s: %s", to, subject)


# ---------- Token-hashning (URL-säker men oreverse-bar i DB) ----------

def token_hash(token: str) -> str:
    """SHA-256 hex — stabil och jämförbar. Tokens är redan 32-byte
    random (urlsafe base64) så inget salt behövs."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------- Rendering av mallar ----------

_BRAND_HEADER = (
    '<div style="font-family:\'Spectral\',Georgia,serif;'
    'font-size:24px;font-weight:800;color:#111217;margin-bottom:12px;">'
    "Ekonomilabbet</div>"
)

_FOOTER = (
    '<hr style="border:none;border-top:1px solid #eee;margin:24px 0;" />'
    '<div style="font-family:Arial,sans-serif;font-size:12px;color:#777;">'
    "Detta mail skickades från Ekonomilabbet. Har du inte bett om det "
    "kan du ignorera det."
    "</div>"
)


def render_verify_email(verify_url: str, teacher_name: str) -> tuple[str, str, str]:
    """(subject, html, text)"""
    subject = "Bekräfta din e-post för Ekonomilabbet"
    safe_name = teacher_name or "lärare"
    text = (
        f"Hej {safe_name},\n\n"
        "Välkommen till Ekonomilabbet! Bekräfta din e-postadress genom "
        "att klicka på länken nedan:\n\n"
        f"{verify_url}\n\n"
        "Länken är giltig i 24 timmar. Har du inte skapat kontot kan du "
        "ignorera mailet.\n\n"
        "— Ekonomilabbet"
    )
    html = (
        '<div style="font-family:Arial,sans-serif;max-width:560px;'
        'margin:0 auto;padding:24px;color:#222;">'
        f"{_BRAND_HEADER}"
        f"<p>Hej {safe_name},</p>"
        "<p>Välkommen till Ekonomilabbet! Bekräfta din e-postadress "
        "genom att klicka på knappen nedan.</p>"
        f'<p style="margin:24px 0;">'
        f'<a href="{verify_url}" '
        'style="display:inline-block;background:#111217;color:#fff;'
        "padding:12px 20px;border-radius:6px;text-decoration:none;"
        'font-weight:600;">Bekräfta e-post</a>'
        "</p>"
        f'<p style="font-size:13px;color:#555;">Om knappen inte '
        f'fungerar, klistra in länken i webbläsaren:<br/>'
        f'<span style="word-break:break-all;">{verify_url}</span></p>'
        '<p style="font-size:13px;color:#555;">'
        "Länken är giltig i 24 timmar."
        "</p>"
        f"{_FOOTER}"
        "</div>"
    )
    return subject, html, text


def render_reset_email(reset_url: str, teacher_name: str) -> tuple[str, str, str]:
    """(subject, html, text)"""
    subject = "Återställ ditt lösenord — Ekonomilabbet"
    safe_name = teacher_name or "lärare"
    text = (
        f"Hej {safe_name},\n\n"
        "Någon bad om att återställa lösenordet för ditt Ekonomilabbet-"
        "konto. Klicka på länken nedan för att välja ett nytt lösenord:\n\n"
        f"{reset_url}\n\n"
        "Länken är giltig i 60 minuter och kan bara användas en gång. "
        "Var det inte du? Ignorera mailet — ditt konto är orört.\n\n"
        "— Ekonomilabbet"
    )
    html = (
        '<div style="font-family:Arial,sans-serif;max-width:560px;'
        'margin:0 auto;padding:24px;color:#222;">'
        f"{_BRAND_HEADER}"
        f"<p>Hej {safe_name},</p>"
        "<p>Någon bad om att återställa lösenordet för ditt "
        "Ekonomilabbet-konto. Klicka på knappen nedan för att välja "
        "ett nytt lösenord.</p>"
        f'<p style="margin:24px 0;">'
        f'<a href="{reset_url}" '
        'style="display:inline-block;background:#111217;color:#fff;'
        "padding:12px 20px;border-radius:6px;text-decoration:none;"
        'font-weight:600;">Välj nytt lösenord</a>'
        "</p>"
        f'<p style="font-size:13px;color:#555;">Om knappen inte '
        f'fungerar, klistra in länken i webbläsaren:<br/>'
        f'<span style="word-break:break-all;">{reset_url}</span></p>'
        '<p style="font-size:13px;color:#555;">'
        "Länken gäller i 60 minuter och kan bara användas en gång. "
        "Var det inte du som bad om återställningen? Ignorera mailet."
        "</p>"
        f"{_FOOTER}"
        "</div>"
    )
    return subject, html, text
