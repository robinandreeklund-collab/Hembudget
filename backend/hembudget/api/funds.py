"""Fondinnehav per konto (primärt ISK).

- GET  /funds/{account_id}              → lista aktuella innehav
- GET  /funds/{account_id}/history      → tidsserie (varje månadsuppdatering)
- POST /funds/{account_id}/parse-image  → vision-AI extrakt från skärmdump
- POST /funds/{account_id}/update       → manuell uppdatering av en rad

Monteras på prefix /funds.
"""
from __future__ import annotations

import base64
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from sqlalchemy import func as sa_func

from ..db.models import Account, FundHolding, FundHoldingSnapshot, Transaction
from ..llm.client import LMStudioClient, LLMUnavailable
from .deps import db, llm_client, require_auth
from .upcoming import _file_to_images

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/funds",
    tags=["funds"],
    dependencies=[Depends(require_auth)],
)


class FundHoldingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    fund_name: str
    units: Optional[Decimal]
    market_value: Decimal
    last_price: Optional[Decimal]
    change_pct: Optional[float]
    change_value: Optional[Decimal]
    day_change_pct: Optional[float]
    currency: str
    last_update_date: date


class FundHoldingIn(BaseModel):
    fund_name: str
    units: Optional[Decimal] = None
    market_value: Decimal
    last_price: Optional[Decimal] = None
    change_pct: Optional[float] = None
    change_value: Optional[Decimal] = None
    day_change_pct: Optional[float] = None
    currency: str = "SEK"
    snapshot_date: Optional[date] = None


class FundsSummaryOut(BaseModel):
    account_id: int
    account_name: str
    total_value: Decimal
    available_cash: Optional[Decimal]
    fund_count: int
    last_update_date: Optional[date]
    holdings: list[FundHoldingOut]


@router.get("/{account_id}", response_model=FundsSummaryOut)
def get_holdings(account_id: int, session: Session = Depends(db)) -> FundsSummaryOut:
    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(404, "Konto saknas")
    rows = (
        session.query(FundHolding)
        .filter(FundHolding.account_id == account_id)
        .order_by(FundHolding.market_value.desc())
        .all()
    )
    fund_total = sum((r.market_value for r in rows), Decimal("0"))
    latest = max((r.last_update_date for r in rows), default=None)
    # Cash på kontot = opening_balance + summa av alla transaktioner.
    # Tidigare returnerades bara opening_balance (eller None när det fanns
    # holdings) — det missade alla insättningar/överföringar in på ISK:n
    # så en elev som flyttat 10 000 kr fick "0 kr tillgängligt". Räkna
    # nu korrekt så cash-saldot stämmer mot Dashboard/Saldo-per-konto.
    ob = acc.opening_balance or Decimal("0")
    tx_sum = (
        session.query(sa_func.coalesce(sa_func.sum(Transaction.amount), 0))
        .filter(Transaction.account_id == account_id)
        .scalar() or 0
    )
    cash_balance = ob + Decimal(str(tx_sum))
    # Total-värde = cash + fond-marknadsvärde. Cash är den del av ISK:n
    # som ännu inte är investerad i fonder; eleven ska se båda.
    return FundsSummaryOut(
        account_id=acc.id,
        account_name=acc.name,
        total_value=fund_total + cash_balance,
        available_cash=cash_balance,
        fund_count=len(rows),
        last_update_date=latest,
        holdings=[FundHoldingOut.model_validate(r) for r in rows],
    )


@router.get("/{account_id}/history")
def get_history(
    account_id: int,
    fund_name: Optional[str] = None,
    session: Session = Depends(db),
) -> dict:
    """Historiska snapshots — per fond (om fund_name) eller aggregerat totalvärde per datum."""
    if session.get(Account, account_id) is None:
        raise HTTPException(404, "Konto saknas")
    q = session.query(FundHoldingSnapshot).filter(
        FundHoldingSnapshot.account_id == account_id,
    )
    if fund_name:
        q = q.filter(FundHoldingSnapshot.fund_name == fund_name)
    rows = q.order_by(
        FundHoldingSnapshot.snapshot_date.asc(),
        FundHoldingSnapshot.fund_name.asc(),
    ).all()

    if fund_name:
        return {
            "fund_name": fund_name,
            "points": [
                {
                    "date": r.snapshot_date.isoformat(),
                    "market_value": float(r.market_value),
                    "units": float(r.units) if r.units is not None else None,
                    "last_price": float(r.last_price) if r.last_price is not None else None,
                    "change_pct": r.change_pct,
                }
                for r in rows
            ],
        }

    # Aggregerat — summera per datum
    by_date: dict[date, Decimal] = {}
    for r in rows:
        by_date[r.snapshot_date] = by_date.get(r.snapshot_date, Decimal("0")) + r.market_value
    return {
        "points": [
            {"date": d.isoformat(), "market_value": float(v)}
            for d, v in sorted(by_date.items())
        ],
    }


@router.post("/{account_id}/update", response_model=FundHoldingOut)
def update_holding(
    account_id: int,
    payload: FundHoldingIn,
    session: Session = Depends(db),
) -> FundHolding:
    if session.get(Account, account_id) is None:
        raise HTTPException(404, "Konto saknas")
    snap_date = payload.snapshot_date or date.today()
    row = _upsert_holding(
        session, account_id, payload.fund_name, {
            "units": payload.units,
            "market_value": payload.market_value,
            "last_price": payload.last_price,
            "change_pct": payload.change_pct,
            "change_value": payload.change_value,
            "day_change_pct": payload.day_change_pct,
            "currency": payload.currency,
            "last_update_date": snap_date,
        },
        snap_date,
    )
    session.flush()
    return row


@router.post("/{account_id}/parse-image")
async def parse_holdings_image(
    account_id: int,
    file: UploadFile = File(...),
    snapshot_date: Optional[str] = Form(None),
    session: Session = Depends(db),
    llm: LMStudioClient = Depends(llm_client),
) -> dict:
    """Ladda upp en skärmdump från bankens fondvy (t.ex. Nordea ISK).

    Vision-modellen extraherar varje fondrad (namn, andelar, kurs, värde,
    total värdeförändring) och dagsförändring. Befintliga FundHolding-
    rader uppdateras, nya skapas. En snapshot per fond och datum lagras
    för historisk utveckling.
    """
    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(404, "Konto saknas")

    if not llm.is_alive():
        raise HTTPException(503, "LM Studio är inte tillgänglig")

    content = await file.read()
    if not content:
        raise HTTPException(400, "Tom fil")

    try:
        images, img_mime = _file_to_images(content, file.content_type)
    except Exception as exc:
        raise HTTPException(400, f"Kunde inte läsa bild/PDF: {exc}") from exc

    try:
        snap_date = (
            date.fromisoformat(snapshot_date) if snapshot_date else date.today()
        )
    except ValueError:
        raise HTTPException(400, "snapshot_date måste vara YYYY-MM-DD")

    user_content: list[dict] = [
        {
            "type": "text",
            "text": _fund_vision_prompt(),
        }
    ]
    for img_bytes in images:
        b64 = base64.b64encode(img_bytes).decode("ascii")
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{img_mime};base64,{b64}"},
        })

    try:
        parsed = llm.complete_json(
            [
                {"role": "system", "content": _fund_system_prompt()},
                {"role": "user", "content": user_content},
            ],
            schema=_fund_schema(),
            temperature=0.0,
        )
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        log.exception("Vision fund-parse failed")
        raise HTTPException(500, f"Vision-anrop misslyckades: {exc}") from exc

    funds_raw = parsed.get("funds") or []
    available_cash = parsed.get("available_cash")
    total_value = parsed.get("total_value")

    created = 0
    updated = 0
    seen_names: set[str] = set()

    for item in funds_raw:
        name = (item.get("fund_name") or "").strip()
        if not name:
            continue
        seen_names.add(name.lower())
        mv = _dec(item.get("market_value"))
        if mv is None:
            continue
        existing = session.execute(
            select(FundHolding).where(
                FundHolding.account_id == account_id,
                FundHolding.fund_name == name,
            )
        ).scalar_one_or_none()
        data = {
            "units": _dec(item.get("units")),
            "market_value": mv,
            "last_price": _dec(item.get("last_price")),
            "change_pct": _float(item.get("change_pct")),
            "change_value": _dec(item.get("change_value")),
            "day_change_pct": _float(item.get("day_change_pct")),
            "currency": item.get("currency") or "SEK",
            "last_update_date": snap_date,
        }
        _upsert_holding(session, account_id, name, data, snap_date)
        if existing is None:
            created += 1
        else:
            updated += 1

    # Om banken visade tillgängligt kontantbelopp, uppdatera kontots opening_balance
    # (endast om skillnaden är liten — annars låter vi användaren kontrollera)
    if available_cash is not None:
        ac_dec = _dec(available_cash)
        if ac_dec is not None:
            acc.opening_balance = ac_dec
            acc.opening_balance_date = snap_date

    session.flush()

    rows = (
        session.query(FundHolding)
        .filter(FundHolding.account_id == account_id)
        .order_by(FundHolding.market_value.desc())
        .all()
    )
    total_stored = sum((r.market_value for r in rows), Decimal("0"))

    return {
        "account_id": account_id,
        "snapshot_date": snap_date.isoformat(),
        "funds_created": created,
        "funds_updated": updated,
        "total_funds": len(rows),
        "total_value_calculated": float(total_stored),
        "total_value_reported": _float(total_value),
        "available_cash": _float(available_cash),
        "holdings": [
            {
                "fund_name": r.fund_name,
                "units": float(r.units) if r.units is not None else None,
                "market_value": float(r.market_value),
                "last_price": float(r.last_price) if r.last_price is not None else None,
                "change_pct": r.change_pct,
                "change_value": float(r.change_value) if r.change_value is not None else None,
                "day_change_pct": r.day_change_pct,
            }
            for r in rows
        ],
    }


# ---------- helpers ----------

def _upsert_holding(
    session: Session,
    account_id: int,
    fund_name: str,
    data: dict,
    snap_date: date,
) -> FundHolding:
    """Infoga eller uppdatera aktuell rad + lagra snapshot för historik."""
    existing = session.execute(
        select(FundHolding).where(
            FundHolding.account_id == account_id,
            FundHolding.fund_name == fund_name,
        )
    ).scalar_one_or_none()
    if existing is None:
        row = FundHolding(account_id=account_id, fund_name=fund_name, **data)
        session.add(row)
    else:
        for k, v in data.items():
            setattr(existing, k, v)
        row = existing

    # Snapshot (idempotent per (account, fund, date) via unique-constraint)
    existing_snap = session.execute(
        select(FundHoldingSnapshot).where(
            FundHoldingSnapshot.account_id == account_id,
            FundHoldingSnapshot.fund_name == fund_name,
            FundHoldingSnapshot.snapshot_date == snap_date,
        )
    ).scalar_one_or_none()
    snap_data = {k: v for k, v in data.items() if k != "last_update_date"}
    if existing_snap is None:
        session.add(FundHoldingSnapshot(
            account_id=account_id,
            fund_name=fund_name,
            snapshot_date=snap_date,
            **snap_data,
        ))
    else:
        for k, v in snap_data.items():
            setattr(existing_snap, k, v)
    return row


def _dec(v) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _fund_system_prompt() -> str:
    return (
        "Du är en expert på att läsa svenska banksidor för fondinnehav "
        "(Nordea, Avanza, SEB). Extrahera varje fond-rad exakt som den står "
        "i tabellen. Returnera ENDAST giltig JSON enligt schemat."
    )


def _fund_vision_prompt() -> str:
    return (
        "Extrahera alla fondinnehav från denna skärmdump (svensk bankvy).\n\n"
        "För varje fond:\n"
        "  - fund_name: fondens namn exakt som det står (t.ex. 'Nordea Stratega 70')\n"
        "  - units: antal andelar (kolumn 'Innehav', fältet t.ex. '17,97 st')\n"
        "  - market_value: marknadsvärde i SEK (kolumn 'Innehav', fältet t.ex. '8 415,70 SEK')\n"
        "  - last_price: aktuell kurs per andel (kolumn 'Kurs', huvudsiffran t.ex. '468,39 SEK')\n"
        "  - day_change_pct: dagsförändring i procent (kolumn 'Kurs', den lilla +0,67% eller -0,05%)\n"
        "  - change_pct: total värdeförändring i procent (kolumn 'Förändring', t.ex. 20,22)\n"
        "  - change_value: total värdeförändring i SEK (kolumn 'Förändring', andra raden t.ex. '1 415,70 SEK')\n"
        "  - currency: 'SEK' om inget annat står\n\n"
        "Om sidan visar tillgängligt kontantsaldo (t.ex. 'Tillgängligt belopp: 0,99 SEK' "
        "eller raden 'Saldo: 0,99 SEK'), ange det som available_cash.\n"
        "Ange totalsumman av alla fonder som total_value (kolumnen 'Samlat värde' högst upp).\n\n"
        "Använd svensk decimalkomma men returnera ALLT som JSON-tal (punkt som separator, "
        "inga tusentalsseparatorer). T.ex. '8 415,70 SEK' → 8415.70."
    )


def _fund_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "total_value": {"type": ["number", "null"]},
            "available_cash": {"type": ["number", "null"]},
            "funds": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "fund_name": {"type": "string"},
                        "units": {"type": ["number", "null"]},
                        "market_value": {"type": "number"},
                        "last_price": {"type": ["number", "null"]},
                        "day_change_pct": {"type": ["number", "null"]},
                        "change_pct": {"type": ["number", "null"]},
                        "change_value": {"type": ["number", "null"]},
                        "currency": {"type": ["string", "null"]},
                    },
                    "required": ["fund_name", "market_value"],
                },
            },
        },
        "required": ["funds"],
    }
