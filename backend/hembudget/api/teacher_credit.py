"""Lärar-API för kredit-aktivitet — klassöversikt + per-elev-drilldown."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as sa_func

from ..db.base import session_scope
from ..db.models import CreditApplication, Loan
from ..school.engines import (
    master_session,
    scope_context,
    scope_for_student,
)
from ..school.models import Student
from .deps import TokenInfo, require_teacher


router = APIRouter(
    prefix="/teacher/credit",
    tags=["teacher-credit"],
    dependencies=[Depends(require_teacher)],
)


def _summarize_student_credit(student) -> dict:
    """Öppna elevens scope och räkna ihop kredit-aktivitet."""
    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            apps = s.query(CreditApplication).all()
            n_applications = len(apps)
            n_approved = sum(1 for a in apps if a.result == "approved")
            n_accepted = sum(1 for a in apps if a.result == "accepted")
            n_declined = sum(1 for a in apps if a.result == "declined")
            n_sms = sum(1 for a in apps if a.kind == "sms")
            avg_score = (
                int(sum(a.score_value for a in apps if a.score_value)
                    / max(1, sum(1 for a in apps if a.score_value)))
                if any(a.score_value for a in apps) else None
            )

            # Aktiva lån + summa skulder
            loans = s.query(Loan).filter(Loan.active.is_(True)).all()
            n_loans = len(loans)
            total_debt = sum(
                Decimal(loan.principal_amount or 0) for loan in loans
            )
            # is_high_cost_credit är deferred + saknas i prod-Postgres
            # om migration ej hunnit köra. Säker access via try/except
            # så rapporten visas även med skev DB-schema.
            from ..school.engines import scope_has_column
            if scope_has_column("loans", "is_high_cost_credit"):
                try:
                    n_high_cost = sum(
                        1 for loan in loans if loan.is_high_cost_credit
                    )
                except Exception:
                    n_high_cost = 0
            else:
                n_high_cost = 0

            return {
                "n_applications": n_applications,
                "n_approved": n_approved,
                "n_accepted": n_accepted,
                "n_declined": n_declined,
                "n_sms_applications": n_sms,
                "avg_credit_score": avg_score,
                "active_loans": n_loans,
                "total_debt": float(total_debt),
                "high_cost_loans": n_high_cost,
            }


@router.get("/overview")
def class_overview(info: TokenInfo = Depends(require_teacher)) -> dict:
    """Per-elev kreditstatus + klassens summa."""
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
                summary = _summarize_student_credit(st)
            except Exception:
                summary = {
                    "n_applications": 0, "n_approved": 0, "n_accepted": 0,
                    "n_declined": 0, "n_sms_applications": 0,
                    "avg_credit_score": None, "active_loans": 0,
                    "total_debt": 0.0, "high_cost_loans": 0,
                }
            rows.append({
                "student_id": st.id,
                "display_name": st.display_name,
                "class_label": st.class_label,
                **summary,
            })

        agg = {
            "students": len(rows),
            "total_applications": sum(r["n_applications"] for r in rows),
            "total_accepted": sum(r["n_accepted"] for r in rows),
            "total_declined": sum(r["n_declined"] for r in rows),
            "total_sms": sum(r["n_sms_applications"] for r in rows),
            "total_debt": sum(r["total_debt"] for r in rows),
            "students_with_high_cost": sum(
                1 for r in rows if r["high_cost_loans"] > 0
            ),
        }
        return {"rows": rows, "aggregate": agg}


@router.get("/student/{student_id}/applications")
def student_applications(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    """Hela ansökningshistoriken för en elev (audit-spår)."""
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
            apps = (
                s.query(CreditApplication)
                .order_by(CreditApplication.created_at.desc())
                .all()
            )
            return {
                "student_id": student_id,
                "display_name": student.display_name,
                "applications": [
                    {
                        "id": a.id,
                        "kind": a.kind,
                        "requested_amount": float(a.requested_amount),
                        "requested_months": a.requested_months,
                        "purpose": a.purpose,
                        "result": a.result,
                        "score_value": a.score_value,
                        "decline_reason": a.decline_reason,
                        "simulated_lender": a.simulated_lender,
                        "offered_rate": a.offered_rate,
                        "offered_monthly_payment": (
                            float(a.offered_monthly_payment)
                            if a.offered_monthly_payment else None
                        ),
                        "resulting_loan_id": a.resulting_loan_id,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
                    }
                    for a in apps
                ],
                "count": len(apps),
            }
