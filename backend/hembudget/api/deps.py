from __future__ import annotations

import time
from typing import Iterator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..config import settings
from ..db.base import session_scope
from ..llm.client import LMStudioClient


# --- In-memory session token store (single-user desktop) ---
_ACTIVE_TOKENS: dict[str, float] = {}


def register_token(token: str) -> None:
    _ACTIVE_TOKENS[token] = time.time()


def revoke_token(token: str) -> None:
    _ACTIVE_TOKENS.pop(token, None)


def _token_valid(token: str) -> bool:
    ts = _ACTIVE_TOKENS.get(token)
    if not ts:
        return False
    if time.time() - ts > settings.session_timeout_minutes * 60:
        _ACTIVE_TOKENS.pop(token, None)
        return False
    _ACTIVE_TOKENS[token] = time.time()
    return True


def require_auth(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization[7:]
    if not _token_valid(token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return token


def db() -> Iterator[Session]:
    with session_scope() as s:
        yield s


def llm_client() -> LMStudioClient:
    return LMStudioClient()
