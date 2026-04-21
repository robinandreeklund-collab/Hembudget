from __future__ import annotations

import base64
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import Category, Transaction, UpcomingTransaction
from ..llm.client import LMStudioClient, LLMUnavailable
from .deps import db, llm_client, require_auth

log = logging.getLogger(__name__)

router = APIRouter(prefix="/upcoming", tags=["upcoming"], dependencies=[Depends(require_auth)])


class UpcomingIn(BaseModel):
    kind: str  # "bill" | "income"
    name: str
    amount: Decimal
    expected_date: date
    owner: Optional[str] = None
    category_id: Optional[int] = None
    recurring_monthly: bool = False
    notes: Optional[str] = None


class UpcomingUpdate(BaseModel):
    kind: Optional[str] = None
    name: Optional[str] = None
    amount: Optional[Decimal] = None
    expected_date: Optional[date] = None
    owner: Optional[str] = None
    category_id: Optional[int] = None
    recurring_monthly: Optional[bool] = None
    notes: Optional[str] = None


class UpcomingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    name: str
    amount: Decimal
    expected_date: date
    owner: Optional[str]
    category_id: Optional[int]
    recurring_monthly: bool
    source: str
    source_image_path: Optional[str]
    notes: Optional[str]
    matched_transaction_id: Optional[int]


@router.get("/", response_model=list[UpcomingOut])
def list_upcoming(
    kind: Optional[str] = None,
    only_future: bool = True,
    session: Session = Depends(db),
) -> list[UpcomingTransaction]:
    q = session.query(UpcomingTransaction)
    if kind:
        q = q.filter(UpcomingTransaction.kind == kind)
    if only_future:
        q = q.filter(UpcomingTransaction.expected_date >= date.today())
    return q.order_by(UpcomingTransaction.expected_date.asc()).all()


@router.post("/", response_model=UpcomingOut)
def create_upcoming(payload: UpcomingIn, session: Session = Depends(db)) -> UpcomingTransaction:
    if payload.kind not in ("bill", "income"):
        raise HTTPException(400, "kind must be 'bill' or 'income'")
    u = UpcomingTransaction(**payload.model_dump())
    session.add(u)
    session.flush()
    return u


@router.patch("/{upcoming_id}", response_model=UpcomingOut)
def update_upcoming(
    upcoming_id: int, payload: UpcomingUpdate, session: Session = Depends(db)
) -> UpcomingTransaction:
    u = session.get(UpcomingTransaction, upcoming_id)
    if u is None:
        raise HTTPException(404, "Upcoming not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(u, k, v)
    session.flush()
    return u


@router.delete("/{upcoming_id}")
def delete_upcoming(upcoming_id: int, session: Session = Depends(db)) -> dict:
    u = session.get(UpcomingTransaction, upcoming_id)
    if u is None:
        raise HTTPException(404, "Upcoming not found")
    session.delete(u)
    return {"deleted": upcoming_id}


@router.post("/parse-text", response_model=UpcomingOut)
def parse_text(
    text: str = Form(...),
    kind: str = Form("bill"),
    session: Session = Depends(db),
    llm: LMStudioClient = Depends(llm_client),
) -> UpcomingTransaction:
    """Använd LM Studio för att tolka ett fritextmeddelande till en strukturerad
    kommande transaktion. Exempel: "Vattenfall 1 500 kr förfaller 2026-04-30"."""
    if not llm.is_alive():
        raise HTTPException(503, "LM Studio är inte tillgänglig")

    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "amount": {"type": "number"},
            "expected_date": {"type": "string", "description": "YYYY-MM-DD"},
            "owner": {"type": ["string", "null"]},
            "notes": {"type": ["string", "null"]},
        },
        "required": ["name", "amount", "expected_date"],
    }

    try:
        parsed = llm.complete_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Du tolkar svensk text om kommande fakturor eller löner. "
                        "Returnera JSON enligt schemat. Belopp som positivt tal i kr. "
                        "Datum i YYYY-MM-DD. Om datum saknas, sätt sista dagen i nästa månad."
                    ),
                },
                {"role": "user", "content": text},
            ],
            schema=schema,
            temperature=0.0,
        )
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    u = UpcomingTransaction(
        kind=kind,
        name=parsed["name"],
        amount=Decimal(str(parsed["amount"])),
        expected_date=date.fromisoformat(parsed["expected_date"]),
        owner=parsed.get("owner"),
        notes=parsed.get("notes"),
        source="ai_text",
    )
    session.add(u)
    session.flush()
    return u


@router.post("/parse-invoice-image", response_model=UpcomingOut)
async def parse_invoice_image(
    file: UploadFile = File(...),
    kind: str = Form("bill"),
    session: Session = Depends(db),
    llm: LMStudioClient = Depends(llm_client),
) -> UpcomingTransaction:
    """Skicka ett fakturafoto till en vision-kapabel modell i LM Studio
    (t.ex. Qwen2.5-VL, Llava) för automatisk extraktion av betalningsmottagare,
    belopp och förfallodag. Kräver att aktiv modell stödjer bild-input.
    """
    if not llm.is_alive():
        raise HTTPException(503, "LM Studio är inte tillgänglig")

    # Spara bild lokalt för audit
    image_dir = settings.data_dir / "invoices"
    image_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    image_path = image_dir / f"{ts}_{file.filename or 'invoice.png'}"
    content = await file.read()
    image_path.write_bytes(content)

    b64 = base64.b64encode(content).decode("ascii")
    mime = file.content_type or "image/png"

    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Mottagare/företagsnamn"},
            "amount": {"type": "number"},
            "expected_date": {"type": "string"},
            "notes": {"type": ["string", "null"]},
        },
        "required": ["name", "amount", "expected_date"],
    }

    try:
        parsed = llm.complete_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Du läser svenska fakturor och extraherar mottagare, "
                        "förfallodatum och totalbelopp. Returnera JSON. "
                        "Datum YYYY-MM-DD, belopp i kr som tal."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extrahera denna faktura:"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                },
            ],
            schema=schema,
            temperature=0.0,
        )
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        log.exception("Vision parse failed")
        raise HTTPException(
            500,
            f"Modellen kunde inte tolka bilden — byt till en vision-kapabel modell "
            f"i LM Studio (t.ex. Qwen2.5-VL). Fel: {exc}",
        ) from exc

    u = UpcomingTransaction(
        kind=kind,
        name=parsed["name"],
        amount=Decimal(str(parsed["amount"])),
        expected_date=date.fromisoformat(parsed["expected_date"]),
        notes=parsed.get("notes"),
        source="vision_ai",
        source_image_path=str(image_path),
    )
    session.add(u)
    session.flush()
    return u


@router.get("/forecast")
def monthly_forecast(
    month: Optional[str] = None,
    split_ratio: float = 0.5,
    session: Session = Depends(db),
) -> dict:
    """Månadsbalans: kommande lön – kommande fakturor – genomsnittliga
    fasta utgifter = disponibelt. Dela 50/50 (eller valfritt ratio)."""
    if month is None:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    year, mon = map(int, month.split("-"))
    start = date(year, mon, 1)
    if mon == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, mon + 1, 1)

    bills = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "bill",
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
        )
        .all()
    )
    incomes = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "income",
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
        )
        .all()
    )

    bills_total = sum((b.amount for b in bills), Decimal("0"))
    income_total = sum((i.amount for i in incomes), Decimal("0"))

    # Fasta kostnader uppskattning = snitt av senaste 3 månadernas utgifter
    # (endast negativa, exkl transfers)
    from sqlalchemy import func as sql_func
    rows = session.execute(
        session.query(
            sql_func.strftime("%Y-%m", Transaction.date).label("m"),
            sql_func.sum(Transaction.amount).label("tot"),
        )
        .where(
            Transaction.amount < 0,
            Transaction.is_transfer.is_(False),
            Transaction.date >= date(year - 1, mon, 1) if mon == 1
                else date(year, mon - 3 if mon > 3 else 1, 1),
            Transaction.date < start,
        )
        .group_by("m")
        .order_by("m")
        .subquery()
        .select()
    ).all()
    # Enklare: direkt fråga
    from sqlalchemy import select
    lookback_start = (
        date(year, mon - 3, 1) if mon > 3
        else date(year - 1, mon + 9, 1)
    )
    monthly_exp = session.execute(
        select(
            sql_func.strftime("%Y-%m", Transaction.date).label("m"),
            sql_func.sum(Transaction.amount).label("tot"),
        )
        .where(
            Transaction.amount < 0,
            Transaction.is_transfer.is_(False),
            Transaction.date >= lookback_start,
            Transaction.date < start,
        )
        .group_by("m")
    ).all()

    if monthly_exp:
        avg_expenses = abs(sum(float(t) for _, t in monthly_exp)) / len(monthly_exp)
    else:
        avg_expenses = 0.0

    available = float(income_total) - float(bills_total) - avg_expenses

    owners = {}
    for i in incomes:
        owners.setdefault(i.owner or "Okänd", Decimal("0"))
        owners[i.owner or "Okänd"] += i.amount

    return {
        "month": month,
        "upcoming_incomes": [
            {
                "id": i.id, "name": i.name, "amount": float(i.amount),
                "expected_date": i.expected_date.isoformat(),
                "owner": i.owner,
            } for i in incomes
        ],
        "upcoming_bills": [
            {
                "id": b.id, "name": b.name, "amount": float(b.amount),
                "expected_date": b.expected_date.isoformat(),
                "category_id": b.category_id,
            } for b in bills
        ],
        "totals": {
            "expected_income": float(income_total),
            "upcoming_bills": float(bills_total),
            "avg_fixed_expenses": round(avg_expenses, 2),
            "available_to_split": round(available, 2),
        },
        "split": {
            "ratio": split_ratio,
            "per_person_share": round(available * split_ratio, 2),
            "per_person_other": round(available * (1 - split_ratio), 2),
        },
        "income_by_owner": {k: float(v) for k, v in owners.items()},
    }
