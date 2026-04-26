"""Lärar-endpoints för aktiehandel — klassöversikt med per-elev-aggregat.

Loopar genom lärarens alla elever, öppnar respektive scope, och
samlar portföljmetrik (omsättning, vinst, courtage). För drilldown
använder läraren befintlig X-As-Student-header som låter dem kalla
/stocks/portfolio + /stocks/ledger som om de vore eleven.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as sa_func

from ..db.base import session_scope
from ..db.models import StockHolding, StockTransaction
from ..school.engines import (
    master_session,
    scope_context,
    scope_for_student,
)
from ..school.models import Student
from .deps import TokenInfo, require_teacher


router = APIRouter(
    prefix="/teacher/stocks",
    tags=["teacher-stocks"],
    dependencies=[Depends(require_teacher)],
)


def _summarize_student(student) -> dict:
    """Öppna elevens scope och räkna ihop nyckeltal."""
    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            holdings = s.query(StockHolding).filter(
                StockHolding.quantity > 0,
            ).all()
            buys = (
                s.query(
                    sa_func.coalesce(sa_func.sum(StockTransaction.total_amount), 0),
                    sa_func.coalesce(sa_func.sum(StockTransaction.courtage), 0),
                    sa_func.count(StockTransaction.id),
                )
                .filter(StockTransaction.side == "buy")
                .one()
            )
            sells = (
                s.query(
                    sa_func.coalesce(sa_func.sum(StockTransaction.total_amount), 0),
                    sa_func.coalesce(sa_func.sum(StockTransaction.courtage), 0),
                    sa_func.coalesce(sa_func.sum(StockTransaction.realized_pnl), 0),
                    sa_func.count(StockTransaction.id),
                )
                .filter(StockTransaction.side == "sell")
                .one()
            )
            last_trade = (
                s.query(StockTransaction.executed_at)
                .order_by(StockTransaction.executed_at.desc())
                .first()
            )
            n_holdings = len({h.ticker for h in holdings})
            cost_basis = sum(
                Decimal(h.quantity) * Decimal(h.avg_cost) for h in holdings
            )
            return {
                "n_holdings": n_holdings,
                "cost_basis": float(cost_basis),
                "buy_volume": float(buys[0]),
                "sell_volume": float(sells[0]),
                "total_courtage": float(buys[1]) + float(sells[1]),
                "realized_pnl": float(sells[2]),
                "n_buys": int(buys[2]),
                "n_sells": int(sells[3]),
                "last_trade_at": (
                    last_trade[0].isoformat() if last_trade else None
                ),
            }


@router.get("/overview")
def class_overview(info: TokenInfo = Depends(require_teacher)) -> dict:
    """Tabellöversikt över alla elevers aktieaktivitet."""
    with master_session() as ms:
        students = (
            ms.query(Student)
            .filter(Student.teacher_id == info.teacher_id)
            .order_by(Student.class_label, Student.display_name)
            .all()
        )
        rows = []
        for st in students:
            try:
                summary = _summarize_student(st)
            except Exception:  # nolint
                summary = {
                    "n_holdings": 0,
                    "cost_basis": 0.0,
                    "buy_volume": 0.0,
                    "sell_volume": 0.0,
                    "total_courtage": 0.0,
                    "realized_pnl": 0.0,
                    "n_buys": 0,
                    "n_sells": 0,
                    "last_trade_at": None,
                }
            rows.append({
                "student_id": st.id,
                "display_name": st.display_name,
                "class_label": st.class_label,
                **summary,
            })

        # Klassens totalsummor
        agg = {
            "students": len(rows),
            "total_buy_volume": sum(r["buy_volume"] for r in rows),
            "total_sell_volume": sum(r["sell_volume"] for r in rows),
            "total_courtage": sum(r["total_courtage"] for r in rows),
            "total_realized_pnl": sum(r["realized_pnl"] for r in rows),
            "active_traders": sum(1 for r in rows if r["n_buys"] + r["n_sells"] > 0),
        }
        return {"rows": rows, "aggregate": agg}


@router.get("/student/{student_id}/ledger")
def student_ledger(
    student_id: int,
    limit: int = 200,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    """Hela aktieledger för en specifik elev.

    Lärare har redan tillgång via impersonation, men denna endpoint är
    optimerad för drilldown-vyn — slipper round-trip via X-As-Student.
    """
    with master_session() as ms:
        student = (
            ms.query(Student)
            .filter(
                Student.id == student_id,
                Student.teacher_id == info.teacher_id,
            )
            .first()
        )
        if student is None:
            raise HTTPException(404, "Student not found")

    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            rows = (
                s.query(StockTransaction)
                .order_by(StockTransaction.executed_at.desc())
                .limit(limit)
                .all()
            )
            return {
                "student_id": student_id,
                "ledger": [
                    {
                        "id": r.id,
                        "ticker": r.ticker,
                        "side": r.side,
                        "quantity": r.quantity,
                        "price": float(r.price),
                        "courtage": float(r.courtage),
                        "total_amount": float(r.total_amount),
                        "realized_pnl": (
                            float(r.realized_pnl)
                            if r.realized_pnl is not None else None
                        ),
                        "quote_id": r.quote_id,
                        "transaction_id": r.transaction_id,
                        "student_rationale": r.student_rationale,
                        "executed_at": r.executed_at.isoformat(),
                    }
                    for r in rows
                ],
                "count": len(rows),
            }
