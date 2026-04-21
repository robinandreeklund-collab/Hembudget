from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from ..config import settings
from ..db.base import get_engine, init_engine
from ..db.migrate import run_migrations
from ..db.models import create_all
from ..categorize.rules import seed_categories_and_rules
from ..db.base import session_scope
from ..security.crypto import derive_key, hash_password, random_token, verify_password
from .deps import register_token, revoke_token
from .schemas import LoginIn, LoginOut

router = APIRouter(tags=["auth"])


def _hash_path() -> Path:
    return settings.data_dir / "master.hash"


@router.get("/status")
def status_route() -> dict:
    import os
    demo = os.environ.get("HEMBUDGET_DEMO_MODE", "").lower() in ("1", "true", "yes")
    return {
        "initialized": _hash_path().exists(),
        "db_path": str(settings.db_path),
        "lm_studio": settings.lm_studio_base_url,
        "demo_mode": demo,
    }


@router.post("/init", response_model=LoginOut)
def init_route(payload: LoginIn) -> LoginOut:
    if _hash_path().exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "Already initialized")
    if len(payload.password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password too short (min 8)")

    key = derive_key(payload.password)
    init_engine(key=key)
    create_all()
    run_migrations(get_engine())
    with session_scope() as s:
        seed_categories_and_rules(s)

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    _hash_path().write_text(hash_password(payload.password))

    token = random_token()
    register_token(token)
    return LoginOut(token=token, initialized=True)


@router.post("/login", response_model=LoginOut)
def login_route(payload: LoginIn) -> LoginOut:
    if not _hash_path().exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not initialized")
    stored = _hash_path().read_text()
    if not verify_password(stored, payload.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid password")
    key = derive_key(payload.password)
    init_engine(key=key)
    # ensure schema exists (e.g. fresh install)
    create_all()
    run_migrations(get_engine())
    with session_scope() as s:
        seed_categories_and_rules(s)

    token = random_token()
    register_token(token)
    return LoginOut(token=token, initialized=True)


@router.post("/logout")
def logout_route(authorization: str | None = None) -> dict:
    if authorization and authorization.startswith("Bearer "):
        revoke_token(authorization[7:])
    return {"ok": True}
