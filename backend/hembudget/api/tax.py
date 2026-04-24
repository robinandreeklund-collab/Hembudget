from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.models import TaxEvent, Transaction, UpcomingTransaction
from ..tax.isk import ISKCalculator, ISKQuarterValue, ISKYearData
from ..tax.k4 import K4Calculator, Trade
from ..tax.rotrut import RotRutService
from .deps import db, require_auth

router = APIRouter(prefix="/tax", tags=["tax"], dependencies=[Depends(require_auth)])


@router.get("/salary-summary")
def salary_tax_summary(
    year: int | None = None,
    session: Session = Depends(db),
) -> dict:
    """Samlad skatteöversikt från uppladdade lönespec-PDFer.

    Läser UpcomingTransaction.notes (JSON från salary_pdf-parsern) och
    aggregerar per person: total brutto, skatt, extra_skatt, förmåner,
    netto. Ger sedan en enkel skatteprognos: om extra_skatt > 0 så är
    det överdragen skatt som borde komma tillbaka vid deklaration.
    """
    import json as _json
    from datetime import date as _date

    y = year or _date.today().year
    start = _date(y, 1, 1)
    end = _date(y + 1, 1, 1)

    salary_ups = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "income",
            UpcomingTransaction.source == "salary_pdf",
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
        )
        .all()
    )

    by_owner: dict[str, dict] = {}
    overall = {
        "gross": 0.0, "tax": 0.0, "extra_tax": 0.0,
        "benefit": 0.0, "net": 0.0, "count": 0,
    }

    for u in salary_ups:
        owner = (u.owner or "gemensamt").strip() or "gemensamt"
        bucket = by_owner.setdefault(
            owner,
            {
                "gross": 0.0, "tax": 0.0, "extra_tax": 0.0,
                "benefit": 0.0, "net": 0.0, "count": 0,
                "payslips": [],
                "suppliers": set(),
            },
        )
        try:
            meta = _json.loads(u.notes or "{}") if u.notes else {}
        except ValueError:
            meta = {}
        gross = float(meta.get("gross") or 0)
        tax = float(meta.get("tax") or 0)
        extra_tax = float(meta.get("extra_tax") or 0)
        benefit = float(meta.get("benefit") or 0)
        net = float(u.amount)

        bucket["gross"] += gross
        bucket["tax"] += tax
        bucket["extra_tax"] += extra_tax
        bucket["benefit"] += benefit
        bucket["net"] += net
        bucket["count"] += 1
        bucket["suppliers"].add(u.name)
        bucket["payslips"].append({
            "upcoming_id": u.id,
            "employer": u.name,
            "paid_date": u.expected_date.isoformat(),
            "gross": gross,
            "tax": tax,
            "extra_tax": extra_tax,
            "benefit": benefit,
            "net": net,
            "tax_table": meta.get("tax_table"),
            "vacation_days_paid": meta.get("vacation_days_paid"),
            "vacation_days_saved": meta.get("vacation_days_saved"),
        })

        overall["gross"] += gross
        overall["tax"] += tax
        overall["extra_tax"] += extra_tax
        overall["benefit"] += benefit
        overall["net"] += net
        overall["count"] += 1

    # Konvertera set → list för JSON
    for bucket in by_owner.values():
        bucket["suppliers"] = sorted(bucket["suppliers"])
        # Projektering linjär på årsbasis
        months = bucket["count"] or 1
        scale = 12.0 / months if months < 12 else 1.0
        bucket["projected_annual_gross"] = round(bucket["gross"] * scale, 2)
        bucket["projected_annual_tax"] = round(bucket["tax"] * scale, 2)
        bucket["projected_annual_extra_tax"] = round(bucket["extra_tax"] * scale, 2)
        # Enkel effektiv skattesats (inkl. extra skatt)
        bucket["effective_tax_rate"] = (
            round(bucket["tax"] / bucket["gross"], 4)
            if bucket["gross"] > 0 else 0.0
        )
        if bucket["extra_tax"] > 0:
            bucket["hint"] = (
                f"Extra skatt betald: {bucket['extra_tax']:.0f} kr. "
                f"Projekterat helår: {bucket['projected_annual_extra_tax']:.0f} kr. "
                "Troligen återbäring vid deklaration om tabellen stämmer."
            )
        else:
            bucket["hint"] = None

    # Runda overall
    for k in ("gross", "tax", "extra_tax", "benefit", "net"):
        overall[k] = round(overall[k], 2)

    return {
        "year": y,
        "by_owner": by_owner,
        "overall": overall,
    }


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
