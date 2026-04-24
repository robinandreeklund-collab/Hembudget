"""In-memory rate limiter + Cloudflare Turnstile-verifikation.

Single-process (Cloud Run --max-instances=1) — räcker för spam-skydd
på login/bootstrap/signup. Ingen Redis krävs.

Två skyddsnivåer:

1) Rate limiting per (IP, endpoint) — sliding window
   - Login: 5 försök / 60s och 20 / 15 min
   - Bootstrap: 3 / 60s och 10 / 15 min
   - AI-student-fråga: 15 / min per IP

2) Turnstile-challenge (Cloudflare CAPTCHA)
   - Fronten skickar en token via header X-Turnstile-Token
   - Backend verifierar mot Cloudflare och kräver success
   - Om TURNSTILE_SECRET inte är satt → skippas tyst
     (så desktop-läge + lokal dev fungerar utan hinder)
"""
from __future__ import annotations

import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from fastapi import HTTPException, Request, status

log = logging.getLogger(__name__)


@dataclass
class Rule:
    """En rate-limit-regel: max N försök per window_sec sekunder."""
    limit: int
    window_sec: float
    name: str = ""


# Alla bucket:ar: { (ip, bucket_key): deque([timestamps...]) }
_buckets: dict[tuple[str, str], Deque[float]] = {}


def _client_ip(request: Request) -> str:
    """Plocka riktig IP från Cloudflare-header om den finns, annars
    från request-klienten. cf-connecting-ip är trustworthy från
    Cloudflare edge (eftersom vi sitter bakom det i prod)."""
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xf = request.headers.get("x-forwarded-for")
    if xf:
        return xf.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def check_rate_limit(
    request: Request, bucket: str, rules: list[Rule],
) -> None:
    """Kontrollerar alla regler i tur. 429 om någon överskrids.

    rules kan vara flera (t.ex. 5/min + 20/15min) och alla måste klaras.
    """
    ip = _client_ip(request)
    now = time.time()
    # Vi använder en gemensam deque per (ip, bucket) med alla timestamps
    # och filtrerar mot varje regels window vid varje anrop. Detta
    # räcker för små volymer — minnet rensas passivt när deque poppas.
    key = (ip, bucket)
    dq = _buckets.get(key)
    if dq is None:
        dq = deque()
        _buckets[key] = dq
    # Rensa för en global "största window" och lägg till now i slutet.
    largest_window = max(r.window_sec for r in rules)
    while dq and now - dq[0] > largest_window:
        dq.popleft()

    for rule in rules:
        # Räkna hur många timestamps som ligger inom rule.window_sec
        cutoff = now - rule.window_sec
        count = sum(1 for t in dq if t >= cutoff)
        if count >= rule.limit:
            retry_after = int(
                max(1, rule.window_sec - (now - dq[-count]) if count else 1),
            )
            log.warning(
                "rate-limit: ip=%s bucket=%s rule=%s count=%d",
                ip, bucket, rule.name or f"{rule.limit}/{rule.window_sec}s",
                count,
            )
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "För många försök. Vänta en stund innan du försöker igen.",
                headers={"Retry-After": str(retry_after)},
            )

    dq.append(now)


# ---------- Turnstile ----------

def _turnstile_secret() -> str:
    return os.environ.get("TURNSTILE_SECRET", "").strip()


def turnstile_site_key() -> str:
    """Publik site-key som frontend läser via /school/status."""
    return os.environ.get("TURNSTILE_SITE_KEY", "").strip()


def verify_turnstile(request: Request, *, required: bool = True) -> None:
    """Verifierar X-Turnstile-Token mot Cloudflare.

    - Om TURNSTILE_SECRET inte är satt = skippas (lokal dev/desktop).
    - Om required=True och verifiering misslyckas → 403.
    - required=False = verifiera om token finns, annars strunt.
    """
    secret = _turnstile_secret()
    if not secret:
        return

    token = request.headers.get("x-turnstile-token", "").strip()
    if not token:
        if required:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Säkerhetskontroll krävs. Ladda om sidan och försök igen.",
            )
        return

    try:
        import httpx
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={
                    "secret": secret,
                    "response": token,
                    "remoteip": _client_ip(request),
                },
            )
        ok = False
        try:
            ok = bool(resp.json().get("success"))
        except Exception:
            ok = False
    except Exception:
        log.exception("turnstile: verifikation misslyckades tekniskt")
        # Fail-open bara om inte required (annars bryts inloggning om
        # Cloudflare själv har hicka). För login är required=True.
        if required:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Säkerhetskontroll tillfälligt ej tillgänglig. Försök igen.",
            )
        return

    if not ok:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Säkerhetskontroll avvisades. Försök igen.",
        )


# ---------- Vanliga rule-presets ----------

RULES_LOGIN = [
    Rule(limit=5, window_sec=60, name="login-1min"),
    Rule(limit=20, window_sec=900, name="login-15min"),
]

RULES_BOOTSTRAP = [
    Rule(limit=3, window_sec=60, name="bootstrap-1min"),
    Rule(limit=10, window_sec=900, name="bootstrap-15min"),
]

RULES_STUDENT_ASK = [
    Rule(limit=15, window_sec=60, name="ask-1min"),
    Rule(limit=100, window_sec=3600, name="ask-1h"),
]

RULES_SIGNUP = [
    Rule(limit=3, window_sec=300, name="signup-5min"),
    Rule(limit=10, window_sec=3600, name="signup-1h"),
]

# Återställ-lösenord-förfrågan: begränsas hårt per IP för att minska
# spam-risken ("någon bad om reset av din mail"-bombning av andra).
RULES_PASSWORD_RESET_REQUEST = [
    Rule(limit=3, window_sec=300, name="reset-5min"),
    Rule(limit=10, window_sec=3600, name="reset-1h"),
]

# Re-send av verifieringsmail — samma profil.
RULES_VERIFY_RESEND = [
    Rule(limit=3, window_sec=300, name="verify-5min"),
    Rule(limit=10, window_sec=3600, name="verify-1h"),
]


def reset_all_for_testing() -> None:
    """Nollställ alla buckets — ENDAST för tester."""
    _buckets.clear()
