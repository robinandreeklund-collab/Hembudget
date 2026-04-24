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
    drop_scope_db,
    drop_student_db,
    get_scope_engine,
    get_student_engine,
    master_session,
    reset_scope_db,
    reset_student_db,
    scope_context,
    scope_for_student,
    student_scope,
)
from ..school.models import (
    Assignment,
    BatchArtifact,
    Family,
    ScenarioBatch,
    Student,
    StudentDataGenerationRun,
    StudentProfile,
    Teacher,
)
from ..school.profile_fixtures import generate_profile
from ..school.tax import compute_net_salary
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
    family_id: Optional[int] = None


class StudentUpdate(BaseModel):
    display_name: Optional[str] = None
    class_label: Optional[str] = None
    family_id: Optional[int] = None  # null = ta ur familj
    active: Optional[bool] = None


class StudentOut(BaseModel):
    id: int
    display_name: str
    class_label: Optional[str]
    login_code: str
    active: bool
    onboarding_completed: bool
    family_id: Optional[int] = None
    family_name: Optional[str] = None
    profession: Optional[str] = None
    personality: Optional[str] = None
    last_login_at: Optional[datetime]
    created_at: datetime


class StudentWithRunsOut(StudentOut):
    months_generated: list[str]


class FamilyIn(BaseModel):
    name: str


class FamilyOut(BaseModel):
    id: int
    name: str
    member_count: int
    created_at: datetime


class StudentProfileOut(BaseModel):
    student_id: int
    profession: str
    employer: str
    gross_salary_monthly: int
    net_salary_monthly: int
    tax_rate_effective: float
    personality: str
    age: int
    city: str
    family_status: str
    housing_type: str
    housing_monthly: int
    has_mortgage: bool
    has_car_loan: bool
    has_student_loan: bool
    has_credit_card: bool
    children_ages: list[int] = []
    partner_age: Optional[int] = None
    backstory: Optional[str]


class StudentProfileUpdate(BaseModel):
    """Lärarens override-fält. Allt valfritt — sätt bara det du vill ändra."""
    profession: Optional[str] = None
    employer: Optional[str] = None
    gross_salary_monthly: Optional[int] = None
    personality: Optional[str] = None
    age: Optional[int] = None
    city: Optional[str] = None
    family_status: Optional[str] = None
    housing_type: Optional[str] = None
    housing_monthly: Optional[int] = None
    has_mortgage: Optional[bool] = None
    has_car_loan: Optional[bool] = None
    has_student_loan: Optional[bool] = None
    has_credit_card: Optional[bool] = None
    backstory: Optional[str] = None


class TaxBreakdownOut(BaseModel):
    gross_monthly: int
    grundavdrag: int
    taxable: int
    kommunal_tax: int
    statlig_tax: int
    total_tax: int
    net_monthly: int
    effective_rate: float
    explanation: str


class StudentLoginIn(BaseModel):
    login_code: str


class StudentAuthOut(BaseModel):
    token: str
    student_id: int
    display_name: str
    class_label: Optional[str]
    onboarding_completed: bool = False
    family_id: Optional[int] = None


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


def _create_profile_for_student(session, student: Student) -> StudentProfile:
    """Slumpa fram en deterministisk profil + cache:a netto-lön."""
    gen = generate_profile(student.id, student.display_name)
    tax = compute_net_salary(gen.gross_salary_monthly)
    profile = StudentProfile(
        student_id=student.id,
        profession=gen.profession,
        employer=gen.employer,
        gross_salary_monthly=gen.gross_salary_monthly,
        net_salary_monthly=tax.net_monthly,
        tax_rate_effective=tax.effective_rate,
        personality=gen.personality,
        age=gen.age,
        city=gen.city,
        family_status=gen.family_status,
        housing_type=gen.housing_type,
        housing_monthly=gen.housing_monthly,
        has_mortgage=gen.has_mortgage,
        has_car_loan=gen.has_car_loan,
        has_student_loan=gen.has_student_loan,
        has_credit_card=gen.has_credit_card,
        backstory=gen.backstory,
        children_ages=gen.children_ages,
        partner_age=gen.partner_age,
    )
    session.add(profile)
    session.flush()
    return profile


def _profile_to_out(p: StudentProfile) -> StudentProfileOut:
    return StudentProfileOut(
        student_id=p.student_id,
        profession=p.profession,
        employer=p.employer,
        gross_salary_monthly=p.gross_salary_monthly,
        net_salary_monthly=p.net_salary_monthly,
        tax_rate_effective=p.tax_rate_effective,
        personality=p.personality,
        age=p.age,
        city=p.city,
        family_status=p.family_status,
        housing_type=p.housing_type,
        housing_monthly=p.housing_monthly,
        has_mortgage=p.has_mortgage,
        has_car_loan=p.has_car_loan,
        has_student_loan=p.has_student_loan,
        has_credit_card=p.has_credit_card,
        children_ages=p.children_ages or [],
        partner_age=p.partner_age,
        backstory=p.backstory,
    )


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
        onboarding_completed=s.onboarding_completed,
        family_id=s.family_id,
        family_name=s.family.name if s.family else None,
        profession=s.profile.profession if s.profile else None,
        personality=s.profile.personality if s.profile else None,
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
            base = _student_to_out(st)
            out.append(
                StudentWithRunsOut(
                    **base.model_dump(),
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
        # Validera familj
        if payload.family_id is not None:
            fam = s.query(Family).filter(
                Family.id == payload.family_id,
                Family.teacher_id == info.teacher_id,
            ).first()
            if not fam:
                raise HTTPException(404, "Family not found")

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
            family_id=payload.family_id,
            display_name=payload.display_name,
            class_label=payload.class_label,
            login_code=code,
        )
        s.add(student)
        s.flush()
        # Skapa profil deterministiskt på student_id
        _create_profile_for_student(s, student)
        # Skapa scope-DB direkt så kategorier seeds
        get_scope_engine(scope_for_student(student))
        s.refresh(student)
        return _student_to_out(student)


@router.patch("/teacher/students/{student_id}", response_model=StudentOut)
def update_student(
    student_id: int,
    payload: StudentUpdate,
    info: TokenInfo = Depends(require_teacher),
) -> StudentOut:
    _require_school_mode()
    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == info.teacher_id,
        ).first()
        if not student:
            raise HTTPException(404, "Student not found")
        if payload.display_name is not None:
            student.display_name = payload.display_name
        if payload.class_label is not None:
            student.class_label = payload.class_label or None
        if payload.active is not None:
            student.active = payload.active
        # Familjehantering: byte av familj betyder byte av scope-DB!
        # Vi kopierar INTE data mellan DB:erna — eleven börjar från noll
        # i den nya scopen. Detta är ett medvetet pedagogiskt val:
        # familjen delar ekonomi från och med "nu".
        if payload.family_id is not None or "family_id" in payload.model_fields_set:
            new_family_id = payload.family_id  # kan vara None
            if new_family_id is not None:
                fam = s.query(Family).filter(
                    Family.id == new_family_id,
                    Family.teacher_id == info.teacher_id,
                ).first()
                if not fam:
                    raise HTTPException(404, "Family not found")
            student.family_id = new_family_id
            s.flush()
            # Säkerställ att nya scope-DB:n finns
            get_scope_engine(scope_for_student(student))
        s.refresh(student)
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
        # OBS: om eleven är solo (inte i familj), radera även scope-DB.
        # Familjemedlemmar delar DB — radera den bara om hen var den
        # sista i familjen.
        scope_to_drop = None
        if not student.family_id:
            scope_to_drop = scope_for_student(student)
        else:
            siblings = s.query(Student).filter(
                Student.family_id == student.family_id,
                Student.id != student.id,
            ).count()
            if siblings == 0:
                scope_to_drop = scope_for_student(student)
        s.delete(student)  # cascade → profile, generation_runs
    if scope_to_drop:
        drop_scope_db(scope_to_drop)
    return {"ok": True}


@router.post("/teacher/students/{student_id}/reset")
def reset_student(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    """Nollställ all transaktionsdata + onboarding-status. Behåll
    profilen (samma identitet, samma lön). Familje-DB nollställs för
    alla medlemmar samtidigt — det är meningen."""
    _require_school_mode()
    with master_session() as s:
        student = (
            s.query(Student)
            .filter(Student.id == student_id, Student.teacher_id == info.teacher_id)
            .first()
        )
        if not student:
            raise HTTPException(404, "Student not found")
        scope_key = scope_for_student(student)
        # Rensa generation-runs och onboarding-flagga för alla
        # familjemedlemmar (eller bara denna elev om solo)
        if student.family_id:
            family_member_ids = [
                m.id for m in s.query(Student).filter(
                    Student.family_id == student.family_id
                ).all()
            ]
        else:
            family_member_ids = [student.id]
        s.query(StudentDataGenerationRun).filter(
            StudentDataGenerationRun.student_id.in_(family_member_ids)
        ).delete(synchronize_session=False)
        for sid in family_member_ids:
            m = s.query(Student).filter(Student.id == sid).first()
            if m:
                m.onboarding_completed = False
    reset_scope_db(scope_key)
    # Skapa ny DB + seed kategorier
    get_scope_engine(scope_key)
    return {"ok": True}


# ---------- Familjer ----------

@router.get("/teacher/families", response_model=list[FamilyOut])
def list_families(
    info: TokenInfo = Depends(require_teacher),
) -> list[FamilyOut]:
    _require_school_mode()
    with master_session() as s:
        fams = s.query(Family).filter(
            Family.teacher_id == info.teacher_id
        ).order_by(Family.name).all()
        return [
            FamilyOut(
                id=f.id, name=f.name,
                member_count=len(f.members),
                created_at=f.created_at,
            )
            for f in fams
        ]


@router.post("/teacher/families", response_model=FamilyOut)
def create_family(
    payload: FamilyIn,
    info: TokenInfo = Depends(require_teacher),
) -> FamilyOut:
    _require_school_mode()
    with master_session() as s:
        fam = Family(teacher_id=info.teacher_id, name=payload.name)
        s.add(fam)
        s.flush()
        return FamilyOut(
            id=fam.id, name=fam.name, member_count=0,
            created_at=fam.created_at,
        )


@router.delete("/teacher/families/{family_id}")
def delete_family(
    family_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    _require_school_mode()
    with master_session() as s:
        fam = s.query(Family).filter(
            Family.id == family_id,
            Family.teacher_id == info.teacher_id,
        ).first()
        if not fam:
            raise HTTPException(404, "Family not found")
        # Lös upp familjebanden men behåll eleverna (de blir solo igen
        # och får sina egna scope-DB:er)
        for member in list(fam.members):
            member.family_id = None
        s.flush()
        # Radera familje-scope-DB:n
        drop_scope_db(f"f_{family_id}")
        s.delete(fam)
    return {"ok": True}


# ---------- Profile ----------

@router.get(
    "/teacher/students/{student_id}/profile",
    response_model=StudentProfileOut,
)
def get_student_profile(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> StudentProfileOut:
    _require_school_mode()
    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == info.teacher_id,
        ).first()
        if not student:
            raise HTTPException(404, "Student not found")
        if not student.profile:
            # Backward-compat för elever skapade innan profile fanns
            _create_profile_for_student(s, student)
        return _profile_to_out(student.profile)


@router.patch(
    "/teacher/students/{student_id}/profile",
    response_model=StudentProfileOut,
)
def update_student_profile(
    student_id: int,
    payload: StudentProfileUpdate,
    info: TokenInfo = Depends(require_teacher),
) -> StudentProfileOut:
    _require_school_mode()
    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == info.teacher_id,
        ).first()
        if not student:
            raise HTTPException(404, "Student not found")
        if not student.profile:
            _create_profile_for_student(s, student)
        prof = student.profile
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(prof, field, value)
        # Räkna om netto om bruttolönen ändrades
        if "gross_salary_monthly" in payload.model_fields_set:
            tax = compute_net_salary(prof.gross_salary_monthly)
            prof.net_salary_monthly = tax.net_monthly
            prof.tax_rate_effective = tax.effective_rate
        s.flush()
        return _profile_to_out(prof)


@router.get("/student/profile", response_model=StudentProfileOut)
def student_get_own_profile(
    info: TokenInfo = Depends(require_token),
) -> StudentProfileOut:
    """Eleven läser sin egen profil (för onboarding och info-vy)."""
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == info.student_id
        ).first()
        if not student:
            raise HTTPException(404, "Student not found")
        if not student.profile:
            _create_profile_for_student(s, student)
        return _profile_to_out(student.profile)


# ---------- Tax-helper ----------

@router.get("/school/tax/breakdown", response_model=TaxBreakdownOut)
def tax_breakdown(gross_monthly: int) -> TaxBreakdownOut:
    """Räkna ut nettolön + skattefördelning + förklaring för en bruttolön.
    Används av onboarding-stegen och budget-setup."""
    if gross_monthly <= 0 or gross_monthly > 1_000_000:
        raise HTTPException(400, "gross_monthly out of range")
    t = compute_net_salary(gross_monthly)
    return TaxBreakdownOut(
        gross_monthly=t.gross_monthly,
        grundavdrag=t.grundavdrag,
        taxable=t.taxable,
        kommunal_tax=t.kommunal_tax,
        statlig_tax=t.statlig_tax,
        total_tax=t.total_tax,
        net_monthly=t.net_monthly,
        effective_rate=t.effective_rate,
        explanation=t.explanation,
    )


# ---------- Konsumentverket-referens + budget-rekommendation ----------

class BudgetSuggestionOut(BaseModel):
    """En rekommenderad startbudget per kategori, baserad på
    Konsumentverkets 2026-värden + elevens profil."""
    mat: int
    individuellt_ovrigt: int
    boende: int
    el: int
    bredband_mobil: int
    medietjanster: int
    forbrukningsvaror: int
    hemutrustning: int
    vatten_avlopp: int
    hemforsakring: int
    transport: int
    lan_amortering_ranta: int
    sparande: int
    nojen_marginal: int
    total: int
    persons_in_household: int
    source_url: str
    source_title: str
    note: str


@router.get("/school/konsumentverket")
def konsumentverket_info() -> dict:
    """Info-text + länk till Konsumentverkets sida om hushållskostnader.
    Visas i budget-setup-vyn och som "Vill veta mer?"-länk."""
    from ..school.konsumentverket import (
        SOURCE_TITLE, SOURCE_URL, GEMENSAMT_PER_PERSONER,
        MAT_HEMMA_PER_AGE, INDIVID_OVRIGT_PER_AGE,
    )
    return {
        "title": SOURCE_TITLE,
        "url": SOURCE_URL,
        "intro": (
            "Konsumentverket räknar varje år ut vad ett vanligt svenskt "
            "hushåll kan behöva lägga på olika utgifter. Siffrorna är "
            "uppskattningar och bygger på en fyraveckors matsedel + "
            "schablonkostnader för kläder, hygien, hemutrustning m.m. "
            "Använd dem som stöd när du sätter din egen budget."
        ),
        "mat_per_age": [
            {"from": r.start, "to": r.stop - 1, "kr_per_month": v}
            for r, v in MAT_HEMMA_PER_AGE
        ],
        "ovrigt_per_age": [
            {"from": r.start, "to": r.stop - 1, "kr_per_month": v}
            for r, v in INDIVID_OVRIGT_PER_AGE
        ],
        "gemensamt_per_persons": GEMENSAMT_PER_PERSONER,
    }


@router.get("/student/budget/suggested", response_model=BudgetSuggestionOut)
def suggested_budget(
    info: TokenInfo = Depends(require_token),
) -> BudgetSuggestionOut:
    """Returnera en rekommenderad startbudget för eleven, baserad på
    deras profil (lön, boende, familj, lån) och Konsumentverkets
    2026-värden. Eleven justerar i UI:n och POST:ar sedan till
    /budget eller liknande."""
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    from ..school.konsumentverket import suggest_budget, SOURCE_URL, SOURCE_TITLE
    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == info.student_id
        ).first()
        if not student:
            raise HTTPException(404, "Student not found")
        if not student.profile:
            _create_profile_for_student(s, student)
        p = student.profile
        sug = suggest_budget(
            adult_age=p.age,
            partner_age=p.partner_age,
            children_ages=p.children_ages or [],
            housing_type=p.housing_type,
            housing_monthly=p.housing_monthly,
            has_mortgage=p.has_mortgage,
            has_car_loan=p.has_car_loan,
            has_student_loan=p.has_student_loan,
            net_salary_monthly=p.net_salary_monthly,
        )
        persons = (
            1 + (1 if p.partner_age else 0) + len(p.children_ages or [])
        )
        note = (
            "Denna budget är ett FÖRSLAG baserat på Konsumentverkets "
            "siffror för 2026. Justera värdena så de passar din "
            "personlighet och dina vanor — du kan alltid ändra senare."
        )
        if sug.nojen_marginal == 0:
            note = (
                "OBS: Med denna profils fasta utgifter blir det inget "
                "kvar till nöjen. Du måste dra ner någonstans — eller "
                "tänka på att höja inkomsten. Detta är pedagogiskt: "
                "verkligheten är inte alltid balanserad!"
            )
        return BudgetSuggestionOut(
            **sug.to_dict(),
            persons_in_household=persons,
            source_url=SOURCE_URL,
            source_title=SOURCE_TITLE,
            note=note,
        )


# ---------- Onboarding ----------

class OnboardingCompleteIn(BaseModel):
    """Marker att eleven har gått igenom hela onboarding-flödet."""
    pass


@router.post("/student/onboarding/complete")
def complete_onboarding(
    info: TokenInfo = Depends(require_token),
) -> dict:
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == info.student_id
        ).first()
        if not student:
            raise HTTPException(404, "Student not found")
        student.onboarding_completed = True
    return {"ok": True}


# ---------- Scenario-batches (PDF-utskick + import) ----------

class BatchArtifactOut(BaseModel):
    id: int
    kind: str
    title: str
    filename: str
    sort_order: int
    imported_at: Optional[datetime]
    meta: Optional[dict]


class ScenarioBatchOut(BaseModel):
    id: int
    student_id: int
    year_month: str
    created_at: datetime
    artifact_count: int
    imported_count: int


class ScenarioBatchDetailOut(ScenarioBatchOut):
    artifacts: list[BatchArtifactOut]


class CreateBatchesIn(BaseModel):
    year_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    student_ids: list[int] | None = None
    overwrite: bool = False


class CreateBatchResultRow(BaseModel):
    student_id: int
    display_name: str
    year_month: str
    status: str  # "created" | "exists" | "overwritten" | "error"
    batch_id: Optional[int] = None
    artifact_count: Optional[int] = None
    error: Optional[str] = None


def _batch_to_out(b: ScenarioBatch) -> ScenarioBatchOut:
    imported = sum(1 for a in b.artifacts if a.imported_at is not None)
    return ScenarioBatchOut(
        id=b.id, student_id=b.student_id, year_month=b.year_month,
        created_at=b.created_at,
        artifact_count=len(b.artifacts),
        imported_count=imported,
    )


def _batch_to_detail(b: ScenarioBatch) -> ScenarioBatchDetailOut:
    base = _batch_to_out(b)
    return ScenarioBatchDetailOut(
        **base.model_dump(),
        artifacts=[
            BatchArtifactOut(
                id=a.id, kind=a.kind, title=a.title, filename=a.filename,
                sort_order=a.sort_order, imported_at=a.imported_at,
                meta=a.meta,
            )
            for a in b.artifacts
        ],
    )


@router.post("/teacher/batches", response_model=list[CreateBatchResultRow])
def create_batches(
    payload: CreateBatchesIn,
    info: TokenInfo = Depends(require_teacher),
) -> list[CreateBatchResultRow]:
    """Generera PDF-batches för en månad — eleven får sedan importera
    dem en i taget. Ersätter den gamla /teacher/generate-flödet med
    en pedagogisk variant där eleven aktivt jobbar med dokumenten."""
    _require_school_mode()
    from ..teacher.batch import create_batch_for_student

    results: list[CreateBatchResultRow] = []
    with master_session() as s:
        q = s.query(Student).filter(
            Student.teacher_id == info.teacher_id,
            Student.active.is_(True),
        )
        if payload.student_ids:
            q = q.filter(Student.id.in_(payload.student_ids))
        students = q.all()

        for student in students:
            try:
                if not student.profile:
                    _create_profile_for_student(s, student)
                existing = s.query(ScenarioBatch).filter(
                    ScenarioBatch.student_id == student.id,
                    ScenarioBatch.year_month == payload.year_month,
                ).first()
                if existing and not payload.overwrite:
                    results.append(CreateBatchResultRow(
                        student_id=student.id,
                        display_name=student.display_name,
                        year_month=payload.year_month,
                        status="exists", batch_id=existing.id,
                        artifact_count=len(existing.artifacts),
                    ))
                    continue
                status_str = "overwritten" if existing else "created"
                batch = create_batch_for_student(
                    s, student, payload.year_month,
                    overwrite=payload.overwrite,
                )
                s.flush()
                results.append(CreateBatchResultRow(
                    student_id=student.id,
                    display_name=student.display_name,
                    year_month=payload.year_month,
                    status=status_str, batch_id=batch.id,
                    artifact_count=len(batch.artifacts),
                ))
            except Exception as e:
                log.exception("Batch creation failed for %d", student.id)
                results.append(CreateBatchResultRow(
                    student_id=student.id,
                    display_name=student.display_name,
                    year_month=payload.year_month,
                    status="error", error=str(e),
                ))
    return results


@router.get(
    "/teacher/students/{student_id}/batches",
    response_model=list[ScenarioBatchOut],
)
def list_student_batches(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> list[ScenarioBatchOut]:
    _require_school_mode()
    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == info.teacher_id,
        ).first()
        if not student:
            raise HTTPException(404, "Student not found")
        batches = (
            s.query(ScenarioBatch)
            .filter(ScenarioBatch.student_id == student_id)
            .order_by(ScenarioBatch.year_month.desc())
            .all()
        )
        return [_batch_to_out(b) for b in batches]


@router.get(
    "/student/batches",
    response_model=list[ScenarioBatchOut],
)
def student_list_batches(
    info: TokenInfo = Depends(require_token),
) -> list[ScenarioBatchOut]:
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    with master_session() as s:
        batches = (
            s.query(ScenarioBatch)
            .filter(ScenarioBatch.student_id == info.student_id)
            .order_by(ScenarioBatch.year_month.desc())
            .all()
        )
        return [_batch_to_out(b) for b in batches]


def _resolve_batch_for_actor(
    info: TokenInfo, batch_id: int, s,
) -> ScenarioBatch:
    batch = s.query(ScenarioBatch).filter(
        ScenarioBatch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(404, "Batch not found")
    if info.role == "student" and batch.student_id != info.student_id:
        raise HTTPException(404, "Batch not found")
    if info.role == "teacher":
        student = s.query(Student).filter(
            Student.id == batch.student_id
        ).first()
        if not student or student.teacher_id != info.teacher_id:
            raise HTTPException(404, "Batch not found")
    return batch


@router.get(
    "/student/batches/{batch_id}",
    response_model=ScenarioBatchDetailOut,
)
def student_batch_detail(
    batch_id: int,
    info: TokenInfo = Depends(require_token),
) -> ScenarioBatchDetailOut:
    _require_school_mode()
    with master_session() as s:
        batch = _resolve_batch_for_actor(info, batch_id, s)
        return _batch_to_detail(batch)


@router.get("/student/batches/{batch_id}/artifacts/{artifact_id}/download")
def download_artifact(
    batch_id: int,
    artifact_id: int,
    info: TokenInfo = Depends(require_token),
):
    from fastapi.responses import Response
    _require_school_mode()
    with master_session() as s:
        batch = _resolve_batch_for_actor(info, batch_id, s)
        artifact = s.query(BatchArtifact).filter(
            BatchArtifact.id == artifact_id,
            BatchArtifact.batch_id == batch.id,
        ).first()
        if not artifact:
            raise HTTPException(404, "Artifact not found")
        return Response(
            content=bytes(artifact.pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition":
                    f'attachment; filename="{artifact.filename}"',
            },
        )


@router.post("/student/batches/{batch_id}/artifacts/{artifact_id}/import")
def import_artifact_endpoint(
    batch_id: int,
    artifact_id: int,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Importera en specifik artefakt (PDF) till elevens scope-DB."""
    from ..teacher.batch import import_artifact
    _require_school_mode()
    with master_session() as s:
        batch = _resolve_batch_for_actor(info, batch_id, s)
        artifact = s.query(BatchArtifact).filter(
            BatchArtifact.id == artifact_id,
            BatchArtifact.batch_id == batch.id,
        ).first()
        if not artifact:
            raise HTTPException(404, "Artifact not found")
        student = s.query(Student).filter(
            Student.id == batch.student_id
        ).first()
        if not student:
            raise HTTPException(404, "Student not found")
        result = import_artifact(s, artifact, student)
        return result


@router.post("/student/batches/{batch_id}/import-all")
def import_all_endpoint(
    batch_id: int,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Importera alla artefakter i en batch i ordning."""
    from ..teacher.batch import import_artifact
    _require_school_mode()
    results: list[dict] = []
    with master_session() as s:
        batch = _resolve_batch_for_actor(info, batch_id, s)
        student = s.query(Student).filter(
            Student.id == batch.student_id
        ).first()
        if not student:
            raise HTTPException(404, "Student not found")
        # Sortera: kontoutdrag först (skapar tx), sedan lönespec/lan/kort
        # som berikar/länkar
        order_priority = {
            "kontoutdrag": 0, "lonespec": 1, "lan_besked": 2,
            "kreditkort_faktura": 3,
        }
        sorted_arts = sorted(
            batch.artifacts,
            key=lambda a: order_priority.get(a.kind, 99),
        )
        for art in sorted_arts:
            r = import_artifact(s, art, student)
            results.append({"artifact_id": art.id, "kind": art.kind, **r})
    return {"results": results}


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
            (st.id, st.display_name, scope_for_student(st)) for st in students
        ]

    results: list[GenerateResultRow] = []
    for sid, name, scope_key in student_list:
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
            # Öppna scope-DB + kör generatorn
            get_scope_engine(scope_key)
            with scope_context(scope_key):
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
        # Säkerställ profil (för elever skapade innan profile fanns)
        if not student.profile:
            _create_profile_for_student(s, student)
        student.last_login_at = datetime.utcnow()
        sid = student.id
        name = student.display_name
        cls = student.class_label
        onb = student.onboarding_completed
        fam_id = student.family_id
        scope_key = scope_for_student(student)
    # Säkerställ att scope-DB:n finns (med seed)
    get_scope_engine(scope_key)
    token = random_token()
    register_token(token, role="student", student_id=sid)
    return StudentAuthOut(
        token=token, student_id=sid,
        display_name=name, class_label=cls,
        onboarding_completed=onb, family_id=fam_id,
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
            onboarding_completed=st.onboarding_completed,
            family_id=st.family_id,
        )
