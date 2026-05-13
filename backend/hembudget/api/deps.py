from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterator, Literal

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..config import settings
from ..db.base import session_scope
from ..llm.client import LMStudioClient


Role = Literal["demo", "teacher", "student"]


@dataclass
class TokenInfo:
    token: str
    role: Role
    teacher_id: int | None = None
    student_id: int | None = None
    ts: float = 0.0


# --- Token store: DB-backat med in-memory cache ovanpå ---
#
# Tidigare bara in-memory (`_ACTIVE_TOKENS`-dict) — fungerade BARA med
# Cloud Run max-instances=1. När vi skalar horisontellt måste tokens
# delas över instanser så att login på instans A funkar på B.
#
# Skiktning:
#   1. Skriv: register_token / revoke_token → DB (sanning) + cache
#   2. Läs: cache först (snabb path), DB-fallback om miss (token kanske
#      registrerades på annan instans)
#   3. Sliding-window expiration via last_seen_at i DB
#
# Cachen är en 60 s TTL ovanpå DB:n så vi inte gör en SELECT per
# autentiserad request på samma instans. Andra instanser går till DB
# en gång och cachar sen.
_TOKEN_CACHE_TTL_SECONDS = 60.0
_token_cache: dict[str, tuple[float, TokenInfo]] = {}


def _cache_get(token: str) -> TokenInfo | None:
    entry = _token_cache.get(token)
    if entry is None:
        return None
    expires_at, info = entry
    if expires_at < time.monotonic():
        _token_cache.pop(token, None)
        return None
    return info


def _cache_set(token: str, info: TokenInfo) -> None:
    _token_cache[token] = (
        time.monotonic() + _TOKEN_CACHE_TTL_SECONDS, info,
    )


def _cache_pop(token: str) -> None:
    _token_cache.pop(token, None)


def register_token(
    token: str,
    role: Role = "demo",
    *,
    teacher_id: int | None = None,
    student_id: int | None = None,
) -> None:
    """Skriv token till DB + cache. Multi-instance-säkert."""
    now = time.time()
    info = TokenInfo(
        token=token,
        role=role,
        teacher_id=teacher_id,
        student_id=student_id,
        ts=now,
    )
    _cache_set(token, info)
    # Skriv till DB om vi har school-mode + master-engine (prod). Lokal
    # SQLite-utveckling utan school-mode hoppar över DB-write — tokens
    # försvinner på instans-restart men det är OK för dev.
    try:
        _persist_token(info)
    except Exception:
        # Fallback till bara in-memory om DB inte funkar — tokens
        # försvinner på instans-restart men lokal session funkar.
        import logging
        logging.getLogger(__name__).exception(
            "register_token: DB-persist failed (cache fortfarande satt)",
        )


def revoke_token(token: str) -> None:
    """Radera token från DB + cache."""
    _cache_pop(token)
    try:
        _delete_token(token)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "revoke_token: DB-delete failed",
        )


def _token_info(token: str) -> TokenInfo | None:
    """Resolva token → TokenInfo. Cache-hit först, sedan DB-lookup,
    sliding-window expiration via last_seen_at-uppdatering."""
    cached = _cache_get(token)
    if cached is not None:
        return cached

    # Cache-miss · slå upp i DB
    try:
        info = _load_token(token)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_token_info: DB-load failed",
        )
        return None
    if info is None:
        return None
    # Verifiera ej-expirerad via sliding window
    timeout_sec = settings.session_timeout_minutes * 60
    if time.time() - info.ts > timeout_sec:
        # Expired → städa
        try:
            _delete_token(token)
        except Exception:
            pass
        return None
    _cache_set(token, info)
    # Uppdatera last_seen_at i DB (best-effort)
    try:
        _touch_token(token)
    except Exception:
        pass
    return info


def _persist_token(info: TokenInfo) -> None:
    """Skriv token till master-DB. Idempotent."""
    if info.role == "demo":
        # Demo-tokens behöver inte persisteras — de är process-lokala
        # och varje instans hanterar sitt eget demo-läge.
        return
    from ..school.engines import master_session as _ms
    from ..school.models import AuthToken as _AT
    with _ms() as s:
        existing = s.query(_AT).filter(
            _AT.token == info.token,
        ).first()
        if existing is not None:
            existing.role = info.role
            existing.teacher_id = info.teacher_id
            existing.student_id = info.student_id
        else:
            s.add(_AT(
                token=info.token,
                role=info.role,
                teacher_id=info.teacher_id,
                student_id=info.student_id,
            ))


def _delete_token(token: str) -> None:
    """Radera token från master-DB."""
    from ..school.engines import master_session as _ms
    from ..school.models import AuthToken as _AT
    with _ms() as s:
        s.query(_AT).filter(_AT.token == token).delete(
            synchronize_session=False,
        )


def _load_token(token: str) -> TokenInfo | None:
    """Hämta token från master-DB."""
    from ..school.engines import master_session as _ms
    from ..school.models import AuthToken as _AT
    with _ms() as s:
        row = s.query(_AT).filter(_AT.token == token).first()
        if row is None:
            return None
        return TokenInfo(
            token=row.token,
            role=row.role,
            teacher_id=row.teacher_id,
            student_id=row.student_id,
            ts=row.last_seen_at.timestamp() if row.last_seen_at else 0.0,
        )


def _touch_token(token: str) -> None:
    """Uppdatera last_seen_at för sliding-window expiration."""
    from ..school.engines import master_session as _ms
    from ..school.models import AuthToken as _AT
    from sqlalchemy import func as _f
    with _ms() as s:
        s.query(_AT).filter(_AT.token == token).update(
            {_AT.last_seen_at: _f.now()},
            synchronize_session=False,
        )


def require_auth(
    authorization: str | None = Header(default=None),
) -> str:
    """Legacy-retur av token-sträng. OBS: student-scope (ContextVar) sätts
    INTE här — det görs i StudentScopeMiddleware som läser samma headers.
    Anledning: FastAPI kör sync deps i en threadpool med kopierad context,
    så ContextVar-set i deps propagerar inte ut till endpoint-körningen.
    """
    import os
    school_on = os.environ.get("HEMBUDGET_SCHOOL_MODE", "").lower() in (
        "1", "true", "yes",
    )
    demo_on = os.environ.get("HEMBUDGET_DEMO_MODE", "").lower() in (
        "1", "true", "yes",
    )
    if demo_on and not school_on:
        return "demo"

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Missing bearer token",
        )
    token = authorization[7:]
    info = _token_info(token)
    if not info:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
        )
    return info.token


def require_token(
    authorization: str | None = Header(default=None),
) -> TokenInfo:
    """Som require_auth men returnerar hela TokenInfo."""
    import os
    school_on = os.environ.get("HEMBUDGET_SCHOOL_MODE", "").lower() in (
        "1", "true", "yes",
    )
    demo_on = os.environ.get("HEMBUDGET_DEMO_MODE", "").lower() in (
        "1", "true", "yes",
    )
    if demo_on and not school_on:
        return TokenInfo(token="demo", role="demo", ts=time.time())

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Missing bearer token",
        )
    token = authorization[7:]
    info = _token_info(token)
    if not info:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
        )
    return info


def require_teacher(info: TokenInfo = Depends(require_token)) -> TokenInfo:
    if info.role != "teacher":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Teacher role required")
    return info


def db() -> Iterator[Session]:
    with session_scope() as s:
        yield s


def llm_client() -> LMStudioClient:
    return LMStudioClient()
