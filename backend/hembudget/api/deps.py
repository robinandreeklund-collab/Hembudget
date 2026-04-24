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


# --- In-memory session token store ---
# Single-process (Cloud Run --max-instances=1).
_ACTIVE_TOKENS: dict[str, TokenInfo] = {}


def register_token(
    token: str,
    role: Role = "demo",
    *,
    teacher_id: int | None = None,
    student_id: int | None = None,
) -> None:
    _ACTIVE_TOKENS[token] = TokenInfo(
        token=token,
        role=role,
        teacher_id=teacher_id,
        student_id=student_id,
        ts=time.time(),
    )


def revoke_token(token: str) -> None:
    _ACTIVE_TOKENS.pop(token, None)


def _token_info(token: str) -> TokenInfo | None:
    info = _ACTIVE_TOKENS.get(token)
    if not info:
        return None
    if time.time() - info.ts > settings.session_timeout_minutes * 60:
        _ACTIVE_TOKENS.pop(token, None)
        return None
    info.ts = time.time()
    return info


def require_auth(
    authorization: str | None = Header(default=None),
) -> str:
    """Legacy-retur av token-sträng. OBS: student-scope (ContextVar) sätts
    INTE här — det görs i StudentScopeMiddleware som läser samma headers.
    Anledning: FastAPI kör sync deps i en threadpool med kopierad context,
    så ContextVar-set i deps propagerar inte ut till endpoint-körningen.
    """
    import os
    if os.environ.get("HEMBUDGET_DEMO_MODE", "").lower() in ("1", "true", "yes"):
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
    if os.environ.get("HEMBUDGET_DEMO_MODE", "").lower() in ("1", "true", "yes"):
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
