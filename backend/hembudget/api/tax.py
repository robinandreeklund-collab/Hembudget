from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.models import TaxEvent, Transaction
from ..tax.isk import ISKCalculator, ISKQuarterValue, ISKYearData
from ..tax.k4 import K4Calculator, Trade
from ..tax.rotrut import RotRutService
from .deps import db, require_auth

router = APIRouter(prefix="/tax", tags=["tax"], dependencies=[Depends(require_auth)])


class ISKIn(BaseModel):
    year: int
    opening_balance: Decimal
    deposits: Decimal
    quarter_values: list[Decimal]   # 4 values
    statslaneranta_30_nov: Decimal


@router.post("/isk")
def compute_isk(payload: ISKIn) -> dict:
    data = ISKYearData(
        year=payload.year,
        opening_balance=payload.opening_balance,
        deposits=payload.deposits,
        quarter_values=[ISKQuarterValue(i + 1, v) for i, v in enumerate(payload.quarter_values)],
        statslaneranta_30_nov=payload.statslaneranta_30_nov,
    )
    r = ISKCalculator().compute(data)
    return {
        "year": r.year,
        "underlag": float(r.underlag),
        "schablonrate": float(r.schablonrate),
        "schablonintakt": float(r.schablonintakt),
        "skatt": float(r.skatt),
        "notes": r.notes,
    }


class TradeIn(BaseModel):
    date: date
    symbol: str
    qty: Decimal
    price: Decimal
    fee: Decimal = Decimal("0")
    currency: str = "SEK"


class K4In(BaseModel):
    year: int
    trades: list[TradeIn]


@router.post("/k4")
def compute_k4(payload: K4In) -> dict:
    trades = [
        Trade(date=t.date, symbol=t.symbol, qty=t.qty, price=t.price, fee=t.fee, currency=t.currency)
        for t in payload.trades
    ]
    rep = K4Calculator().compute(trades, payload.year)
    return {
        "year": rep.year,
        "total_gain": float(rep.total_gain),
        "total_loss": float(rep.total_loss),
        "net": float(rep.net),
        "lines": [
            {
                "symbol": l.symbol,
                "total_sold_qty": float(l.total_sold_qty),
                "sale_proceeds": float(l.sale_proceeds),
                "acquisition_cost": float(l.acquisition_cost),
                "gain": float(l.gain),
            }
            for l in rep.lines
        ],
    }


class RotRutTagIn(BaseModel):
    transaction_id: int
    kind: str  # "rot" | "rut"
    deduction_amount: Decimal


@router.post("/rotrut/tag")
def tag_rotrut(payload: RotRutTagIn, session: Session = Depends(db)) -> dict:
    try:
        ev = RotRutService(session).tag_transaction(
            payload.transaction_id, payload.kind, payload.deduction_amount
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"id": ev.id, "type": ev.type, "amount": float(ev.amount), "date": ev.date.isoformat()}


@router.get("/rotrut/{year}")
def rotrut_summary(year: int, session: Session = Depends(db)) -> dict:
    s = RotRutService(session).summary(year)
    return {
        "year": s.year,
        "rot_used": float(s.rot_used),
        "rut_used": float(s.rut_used),
        "rot_cap": float(s.rot_cap),
        "rut_cap": float(s.rut_cap),
        "rot_remaining": float(s.rot_remaining),
        "rut_remaining": float(s.rut_remaining),
        "notes": s.notes,
    }


@router.get("/events/{year}")
def list_events(year: int, session: Session = Depends(db)) -> dict:
    rows = (
        session.query(TaxEvent)
        .filter(TaxEvent.date >= date(year, 1, 1), TaxEvent.date < date(year + 1, 1, 1))
        .order_by(TaxEvent.date.asc())
        .all()
    )
    return {
        "events": [
            {
                "id": e.id,
                "type": e.type,
                "amount": float(e.amount),
                "date": e.date.isoformat(),
                "transaction_id": e.transaction_id,
                "meta": e.meta,
            }
            for e in rows
        ]
    }
