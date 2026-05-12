"""Lärar-API · Klassens anställnings-ekosystem (Fas H).

Spec: dev/employment-flows.md (Fas H)

Visar en lärar-översikt över ALLA klasskompis-anställningar i klassen:
  · Vem äger ett bolag (företagare)
  · Vem är anställd hos vem (klasskompis-anställningar)
  · Total payroll-volym i klassen senaste månaden
  · Antal aktiva / konkurser / uppsägningar

Endpointen kräver lärar-token. Returnerar graph-data lämplig för
nodes+edges-rendering i frontend.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..school.engines import master_session
from ..school.employment_models import ClassmateEmployment
from ..school.models import Student, StudentActivity
from .deps import TokenInfo, require_teacher


router = APIRouter(prefix="/v2/teacher/employment", tags=["teacher-employment"])


# ===========================================================
# Schemas
# ===========================================================


class StudentNode(BaseModel):
    student_id: int
    display_name: str
    class_label: Optional[str] = None
    is_employer: bool
    company_name: Optional[str] = None
    n_employees: int = 0
    employed_at: Optional[str] = None  # company-namn där de är anställda


class EmploymentEdge(BaseModel):
    employment_id: int
    owner_student_id: int
    employee_student_id: int
    company_name: str
    role: str
    monthly_gross: int
    status: str
    accepted_on: Optional[str] = None
    last_day: Optional[str] = None


class EcosystemOut(BaseModel):
    students: list[StudentNode]
    employments: list[EmploymentEdge]
    stats: dict


# ===========================================================
# Endpoints
# ===========================================================


@router.get("/ecosystem", response_model=EcosystemOut)
def class_employment_ecosystem(
    class_label: Optional[str] = None,
    info: TokenInfo = Depends(require_teacher),
):
    """Returnera alla anställnings-relationer i klassen som
    nodes (elever) + edges (anställningar)."""
    teacher_id = info.teacher_id
    if teacher_id is None:
        raise HTTPException(403, "Lärar-token utan teacher_id")

    with master_session() as s:
        q = s.query(Student).filter(Student.teacher_id == teacher_id)
        if class_label:
            q = q.filter(Student.class_label == class_label)
        students = q.order_by(Student.display_name).all()
        student_ids = [st.id for st in students]

        # Alla employments där ANTINGEN owner eller employee finns i
        # klassen (vanligtvis båda).
        all_emps = (
            s.query(ClassmateEmployment)
            .filter(
                (ClassmateEmployment.owner_student_id.in_(student_ids))
                | (ClassmateEmployment.employee_student_id.in_(student_ids)),
            )
            .order_by(ClassmateEmployment.offer_sent_on.desc())
            .all()
        )

        # Bygg upp employer/employee-tillstånd per student
        n_employees_per_owner: dict[int, int] = {}
        owner_company: dict[int, str] = {}
        employee_company: dict[int, str] = {}
        for e in all_emps:
            if e.status == "active":
                n_employees_per_owner[e.owner_student_id] = (
                    n_employees_per_owner.get(e.owner_student_id, 0) + 1
                )
                owner_company[e.owner_student_id] = e.company_name
                employee_company[e.employee_student_id] = e.company_name

        nodes = [
            StudentNode(
                student_id=st.id,
                display_name=st.display_name,
                class_label=st.class_label,
                is_employer=n_employees_per_owner.get(st.id, 0) > 0,
                company_name=owner_company.get(st.id),
                n_employees=n_employees_per_owner.get(st.id, 0),
                employed_at=employee_company.get(st.id),
            )
            for st in students
        ]

        edges = [
            EmploymentEdge(
                employment_id=e.id,
                owner_student_id=e.owner_student_id,
                employee_student_id=e.employee_student_id,
                company_name=e.company_name,
                role=e.role,
                monthly_gross=e.monthly_gross,
                status=e.status,
                accepted_on=(
                    e.accepted_on.isoformat() if e.accepted_on else None
                ),
                last_day=(
                    e.last_day.isoformat() if e.last_day else None
                ),
            )
            for e in all_emps
        ]

        # Statistik — senaste 30 dgr
        cutoff = datetime.utcnow() - timedelta(days=30)
        recent_payroll = (
            s.query(StudentActivity)
            .filter(
                StudentActivity.student_id.in_(student_ids),
                StudentActivity.kind == "biz.payroll_run",
                StudentActivity.created_at >= cutoff,
            )
            .all()
        )
        total_payroll_30d = 0
        for act in recent_payroll:
            pl = act.payload or {}
            total_payroll_30d += int(pl.get("total_cost") or 0)

        n_active = sum(1 for e in all_emps if e.status == "active")
        n_pending = sum(1 for e in all_emps if e.status == "pending_offer")
        n_terminated = sum(1 for e in all_emps if e.status == "terminated")
        n_declined = sum(1 for e in all_emps if e.status == "declined")
        n_employers = sum(1 for n in nodes if n.is_employer)

        return EcosystemOut(
            students=nodes,
            employments=edges,
            stats={
                "n_students_total": len(students),
                "n_employers": n_employers,
                "n_active_employments": n_active,
                "n_pending_offers": n_pending,
                "n_terminated": n_terminated,
                "n_declined": n_declined,
                "total_payroll_paid_30d": total_payroll_30d,
            },
        )
