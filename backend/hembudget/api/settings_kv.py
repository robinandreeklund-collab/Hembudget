"""Generisk nyckel-värde settings-endpoint.

Används av frontend för att spara användarens preferenser:
- default_debit_account_id: vilket konto som föreslås för nya fakturor
- default_currency, per-användarspecifika flaggor, osv.

Värden sparas som JSON så alla primitiva typer + enkla dicts stöds.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.models import AppSetting
from .deps import db, require_auth

router = APIRouter(
    prefix="/settings", tags=["settings"], dependencies=[Depends(require_auth)],
)


class SettingValue(BaseModel):
    value: Any


@router.get("/")
def list_settings(session: Session = Depends(db)) -> dict:
    """Alla sparade inställningar som dict {key: value}."""
    rows = session.query(AppSetting).all()
    return {r.key: (r.value or {}).get("v") for r in rows}


@router.get("/{key}")
def get_setting(key: str, session: Session = Depends(db)) -> dict:
    row = session.get(AppSetting, key)
    if row is None:
        raise HTTPException(404, f"Setting '{key}' not found")
    return {"key": key, "value": (row.value or {}).get("v")}


@router.put("/{key}")
def set_setting(
    key: str, payload: SettingValue, session: Session = Depends(db),
) -> dict:
    row = session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value={"v": payload.value})
        session.add(row)
    else:
        row.value = {"v": payload.value}
    session.flush()
    return {"key": key, "value": payload.value}


@router.delete("/{key}")
def delete_setting(key: str, session: Session = Depends(db)) -> dict:
    row = session.get(AppSetting, key)
    if row is None:
        raise HTTPException(404, f"Setting '{key}' not found")
    session.delete(row)
    session.flush()
    return {"deleted": key}
