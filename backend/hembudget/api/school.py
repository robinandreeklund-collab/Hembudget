"""API-routes för school-mode: lärare + elever.

Endpoints:
- POST /teacher/bootstrap    — skapa första lärarkontot (env-var-skyddat)
- POST /teacher/login        — logga in lärare (e-post + lösen)
- POST /teacher/logout
- GET/POST/DELETE /teacher/students
- POST /teacher/students/{id}/reset
- POST /teacher/generate     — generera exempeldata per månad
- GET /teacher/generate/history/{student_id}
- POST /student/login        — elev loggar in med login_code
- POST /student/logout
"""
from __future__ import annotations

import logging
import os
import random
import string
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from ..school import is_enabled as school_enabled
from ..school.engines import (
    drop_student_db,
    get_student_engine,
    master_session,
    reset_student_db,
    student_scope,
)
from ..school.models import Student, StudentDataGenerationRun, Teacher
from ..security.crypto import hash_password, random_token, verify_password
from .deps import (
    TokenInfo,
    register_token,
    require_teacher,
    require_token,
    revoke_token,
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["school"])


# ---------- Schemas ----------

class TeacherBootstrapIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str
    # Valfri — krävs bara om HEMBUDGET_BOOTSTRAP_SECRET är satt i
    # Cloud Run-env:en. När variabeln är tom räcker det att inga
    # lärare finns för att skapa den första från UI.
    bootstrap_secret: Optional[str] = None


class TeacherLoginIn(BaseModel):
    email: EmailStr
    password: str


class TeacherAuthOut(BaseModel):
    token: str
    teacher_id: int
    name: str
    email: str


class StudentIn(BaseModel):
    display_name: str
    class_label: Optional[str] = None


class StudentOut(BaseModel):
    id: int
    display_name: str
    class_label: Optional[str]
    login_code: str
    active: bool
    last_login_at: Optional[datetime]
    created_at: datetime


class StudentWithRunsOut(StudentOut):
    months_generated: list[str]


class StudentLoginIn(BaseModel):
    login_code: str


class StudentAuthOut(BaseModel):
    token: str
    student_id: int
    display_name: str
    class_label: Optional[str]


class GenerateIn(BaseModel):
    year_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    # Tom lista = alla läraräger
    student_ids: list[int] | None = None
    overwrite: bool = False


class GenerateResultRow(BaseModel):
    student_id: int
    display_name: str
    year_month: str
    status: str  # "created" | "skipped" | "overwritten" | "error"
    seed: Optional[int] = None
    stats: Optional[dict] = None
    error: Optional[str] = None


# ---------- Helpers ----------

def _require_school_mode() -> None:
    if not school_enabled():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "School mode not enabled",
        )


def _gen_login_code() -> str:
    """6-tecken kod, enkel att läsa (inga 0/O/1/I)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choice(alphabet) for _ in range(6))


# ---------- Teacher: bootstrap + login ----------

@router.post("/teacher/bootstrap", response_model=TeacherAuthOut)
def bootstrap_teacher(payload: TeacherBootstrapIn) -> TeacherAuthOut:
    """Skapa första lärarkontot.

    - Om HEMBUDGET_BOOTSTRAP_SECRET är satt i env måste payloadens
      bootstrap_secret matcha (extra skydd när tjänsten ligger publikt).
    - Om env-varen INTE är satt räcker det att inga lärare finns — då
      kan första besökaren skapa kontot direkt från UI.
    - 410 Gone så snart minst en lärare finns."""
    _require_school_mode()
    expected = os.environ.get("HEMBUDGET_BOOTSTRAP_SECRET", "")
    if expected:
        if not payload.bootstrap_secret or payload.bootstrap_secret != expected:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Invalid bootstrap secret",
            )
    with master_session() as s:
        if s.query(Teacher).count() > 0:
            raise HTTPException(
                status.HTTP_410_GONE, "Teachers already exist",
            )
        teacher = Teacher(
            email=payload.email.lower(),
            name=payload.name,
            password_hash=hash_password(payload.password),
        )
        s.add(teacher)
        s.flush()
        tid = teacher.id
        tname = teacher.name
        temail = teacher.email

    token = random_token()
    register_token(token, role="teacher", teacher_id=tid)
    return TeacherAuthOut(
        token=token, teacher_id=tid, name=tname, email=temail,
    )


@router.post("/teacher/login", response_model=TeacherAuthOut)
def teacher_login(payload: TeacherLoginIn) -> TeacherAuthOut:
    _require_school_mode()
    with master_session() as s:
        teacher = (
            s.query(Teacher).filter(Teacher.email == payload.email.lower()).first()
        )
        if (
            not teacher
            or not teacher.active
            or not verify_password(teacher.password_hash, payload.password)
        ):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Invalid credentials",
            )
        tid = teacher.id
        tname = teacher.name
        temail = teacher.email
    token = random_token()
    register_token(token, role="teacher", teacher_id=tid)
    return TeacherAuthOut(
        token=token, teacher_id=tid, name=tname, email=temail,
    )


@router.post("/teacher/logout")
def teacher_logout(info: TokenInfo = Depends(require_teacher)) -> dict:
    revoke_token(info.token)
    return {"ok": True}


# ---------- Teacher: elevhantering ----------

def _student_to_out(s: Student) -> StudentOut:
    return StudentOut(
        id=s.id,
        display_name=s.display_name,
        class_label=s.class_label,
        login_code=s.login_code,
        active=s.active,
        last_login_at=s.last_login_at,
        created_at=s.created_at,
    )


@router.get("/teacher/students", response_model=list[StudentWithRunsOut])
def list_students(
    info: TokenInfo = Depends(require_teacher),
) -> list[StudentWithRunsOut]:
    _require_school_mode()
    with master_session() as s:
        students = (
            s.query(Student)
            .filter(Student.teacher_id == info.teacher_id)
            .order_by(Student.class_label, Student.display_name)
            .all()
        )
        out: list[StudentWithRunsOut] = []
        for st in students:
            runs = (
                s.query(StudentDataGenerationRun.year_month)
                .filter(StudentDataGenerationRun.student_id == st.id)
                .order_by(StudentDataGenerationRun.year_month)
                .all()
            )
            out.append(
                StudentWithRunsOut(
                    id=st.id,
                    display_name=st.display_name,
                    class_label=st.class_label,
                    login_code=st.login_code,
                    active=st.active,
                    last_login_at=st.last_login_at,
                    created_at=st.created_at,
                    months_generated=[r[0] for r in runs],
                )
            )
        return out


@router.post("/teacher/students", response_model=StudentOut)
def create_student(
    payload: StudentIn,
    info: TokenInfo = Depends(require_teacher),
) -> StudentOut:
    _require_school_mode()
    with master_session() as s:
        # Generera unik login_code (max 5 försök)
        code = None
        for _ in range(5):
            candidate = _gen_login_code()
            if not s.query(Student).filter(Student.login_code == candidate).first():
                code = candidate
                break
        if code is None:
            raise HTTPException(500, "Could not generate login code")
        student = Student(
            teacher_id=info.teacher_id,
            display_name=payload.display_name,
            class_label=payload.class_label,
            login_code=code,
        )
        s.add(student)
        s.flush()
        # Skapa elevens DB direkt så kategorier seeds
        get_student_engine(student.id)
        return _student_to_out(student)


@router.delete("/teacher/students/{student_id}")
def delete_student(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    _require_school_mode()
    with master_session() as s:
        student = (
            s.query(Student)
            .filter(Student.id == student_id, Student.teacher_id == info.teacher_id)
            .first()
        )
        if not student:
            raise HTTPException(404, "Student not found")
        # generation_runs raderas via cascade
        s.delete(student)
    drop_student_db(student_id)
    return {"ok": True}


@router.post("/teacher/students/{student_id}/reset")
def reset_student(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    _require_school_mode()
    with master_session() as s:
        student = (
            s.query(Student)
            .filter(Student.id == student_id, Student.teacher_id == info.teacher_id)
            .first()
        )
        if not student:
            raise HTTPException(404, "Student not found")
        # Rensa generation-runs så de kan regenereras
        s.query(StudentDataGenerationRun).filter(
            StudentDataGenerationRun.student_id == student_id
        ).delete()
    reset_student_db(student_id)
    # Skapa ny DB + seed kategorier
    get_student_engine(student_id)
    return {"ok": True}


# ---------- Teacher: datagenerering ----------

@router.post("/teacher/generate", response_model=list[GenerateResultRow])
def generate_month(
    payload: GenerateIn,
    info: TokenInfo = Depends(require_teacher),
) -> list[GenerateResultRow]:
    _require_school_mode()
    from ..teacher.generator import MonthlyDataGenerator

    with master_session() as s:
        q = s.query(Student).filter(
            Student.teacher_id == info.teacher_id,
            Student.active.is_(True),
        )
        if payload.student_ids:
            q = q.filter(Student.id.in_(payload.student_ids))
        students = q.all()
        student_list = [
            (st.id, st.display_name) for st in students
        ]

    results: list[GenerateResultRow] = []
    for sid, name in student_list:
        seed = abs(hash((sid, payload.year_month))) & 0xFFFFFFFF
        with master_session() as s:
            existing = (
                s.query(StudentDataGenerationRun)
                .filter(
                    StudentDataGenerationRun.student_id == sid,
                    StudentDataGenerationRun.year_month == payload.year_month,
                )
                .first()
            )
            if existing and not payload.overwrite:
                results.append(
                    GenerateResultRow(
                        student_id=sid, display_name=name,
                        year_month=payload.year_month,
                        status="skipped", seed=existing.seed,
                        stats=existing.stats,
                    )
                )
                continue

        try:
            # Öppna elevens DB + kör generatorn
            get_student_engine(sid)
            with student_scope(sid):
                gen = MonthlyDataGenerator(
                    student_id=sid,
                    year_month=payload.year_month,
                    seed=seed,
                )
                stats = gen.generate(overwrite=payload.overwrite)
            with master_session() as s:
                existing = (
                    s.query(StudentDataGenerationRun)
                    .filter(
                        StudentDataGenerationRun.student_id == sid,
                        StudentDataGenerationRun.year_month == payload.year_month,
                    )
                    .first()
                )
                if existing:
                    existing.seed = seed
                    existing.stats = stats
                    existing.generated_at = datetime.utcnow()
                    status_out = "overwritten"
                else:
                    s.add(StudentDataGenerationRun(
                        student_id=sid,
                        year_month=payload.year_month,
                        seed=seed,
                        stats=stats,
                    ))
                    status_out = "created"
            results.append(
                GenerateResultRow(
                    student_id=sid, display_name=name,
                    year_month=payload.year_month,
                    status=status_out, seed=seed, stats=stats,
                )
            )
        except Exception as e:
            log.exception("Generation failed for student %d", sid)
            results.append(
                GenerateResultRow(
                    student_id=sid, display_name=name,
                    year_month=payload.year_month,
                    status="error", error=str(e),
                )
            )

    return results


# ---------- Student login ----------

@router.post("/student/login", response_model=StudentAuthOut)
def student_login(payload: StudentLoginIn) -> StudentAuthOut:
    _require_school_mode()
    code = payload.login_code.strip().upper()
    with master_session() as s:
        student = s.query(Student).filter(Student.login_code == code).first()
        if not student or not student.active:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Invalid code",
            )
        student.last_login_at = datetime.utcnow()
        sid = student.id
        name = student.display_name
        cls = student.class_label
    # Säkerställ att elevens DB finns (med seed)
    get_student_engine(sid)
    token = random_token()
    register_token(token, role="student", student_id=sid)
    return StudentAuthOut(
        token=token, student_id=sid,
        display_name=name, class_label=cls,
    )


@router.post("/student/logout")
def student_logout(info: TokenInfo = Depends(require_token)) -> dict:
    revoke_token(info.token)
    return {"ok": True}


# ---------- Info-endpoint för frontend ----------

@router.get("/school/status")
def school_status() -> dict:
    enabled = school_enabled()
    info: dict = {"school_mode": enabled}
    if enabled:
        with master_session() as s:
            info["teacher_count"] = s.query(Teacher).count()
            # bootstrap_ready = ingen lärare finns ännu (första besökaren
            # kan skapa). requires_secret styr om UI ska visa fältet för
            # HEMBUDGET_BOOTSTRAP_SECRET eller ej.
            info["bootstrap_ready"] = info["teacher_count"] == 0
            info["bootstrap_requires_secret"] = bool(
                os.environ.get("HEMBUDGET_BOOTSTRAP_SECRET")
            )
    return info


@router.get("/teacher/me", response_model=TeacherAuthOut)
def teacher_me(info: TokenInfo = Depends(require_teacher)) -> TeacherAuthOut:
    _require_school_mode()
    with master_session() as s:
        t = s.query(Teacher).filter(Teacher.id == info.teacher_id).first()
        if not t:
            raise HTTPException(404, "Teacher not found")
        return TeacherAuthOut(
            token=info.token, teacher_id=t.id, name=t.name, email=t.email,
        )


@router.get("/student/me", response_model=StudentAuthOut)
def student_me(info: TokenInfo = Depends(require_token)) -> StudentAuthOut:
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a student token")
    with master_session() as s:
        st = s.query(Student).filter(Student.id == info.student_id).first()
        if not st:
            raise HTTPException(404, "Student not found")
        return StudentAuthOut(
            token=info.token, student_id=st.id,
            display_name=st.display_name, class_label=st.class_label,
        )
