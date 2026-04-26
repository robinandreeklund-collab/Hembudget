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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from ..school import is_enabled as school_enabled
from ..school.engines import (
    dispose_scope_engine,
    drop_scope_db,
    drop_student_db,
    get_scope_engine,
    get_student_engine,
    master_has_column,
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
    InterestRateSeries,
    Message,
    Module,
    ModuleStep,
    MortgageDecision,
    ScenarioBatch,
    Student,
    StudentDataGenerationRun,
    StudentModule,
    StudentProfile,
    StudentStepProgress,
    Teacher,
)
from ..school.profile_fixtures import generate_profile
from ..school.tax import compute_net_salary
from ..security.crypto import hash_password, random_token, verify_password
from ..security.rate_limit import (
    RULES_BOOTSTRAP,
    RULES_LOGIN,
    check_rate_limit,
    turnstile_site_key,
    verify_turnstile,
)
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
    is_family_account: bool = False


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
    # True om StudentProfile-raden finns. False = "föräldralös" elev
    # (raden i `students` skapades men profile-INSERTen kraschade — då
    # behöver läraren reparera eller ta bort eleven).
    has_profile: bool = True


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
    partner_profession: Optional[str] = None
    partner_gross_salary: Optional[int] = None
    cost_split_preference: Optional[str] = None
    cost_split_decided_at: Optional[datetime] = None
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
    """Slumpa fram en deterministisk profil + cache:a netto-lön.

    Defensiv: om DB:n saknar de nyaste partner-kolumnerna (migration
    har inte körts) skapar vi profilen utan dem och loggar — då
    fungerar elev-skapande även om _run_master_migrations failade.
    """
    import logging
    gen = generate_profile(student.id, student.display_name)
    tax = compute_net_salary(gen.gross_salary_monthly)

    # Bas-fält som funnits sedan länge
    profile_kwargs = dict(
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

    # Lägg bara på partner-fälten om kolumnerna finns i DB:n. Då kan
    # vi aldrig generera en INSERT som refererar saknade kolumner.
    if master_has_column("student_profiles", "partner_profession"):
        profile_kwargs["partner_profession"] = gen.partner_profession
    if master_has_column("student_profiles", "partner_gross_salary"):
        profile_kwargs["partner_gross_salary"] = gen.partner_gross_salary

    try:
        profile = StudentProfile(**profile_kwargs)
        session.add(profile)
        session.flush()
        return profile
    except Exception:
        logging.getLogger(__name__).exception(
            "_create_profile_for_student: oväntat fel för student %s",
            student.id,
        )
        raise


def _safe_profile_attr(p: StudentProfile, field: str):
    """Läs ett deferred-fält om kolumnen finns i master-DB:n. Om
    migrationen ännu inte hunnit lägga till kolumnen i prod-Postgres
    returnerar vi None — då kraschar inte requesten."""
    if not master_has_column("student_profiles", field):
        return None
    try:
        return getattr(p, field)
    except Exception:
        # Defensiv fallback: om deferred-load kraschar, rulla tillbaka
        # session-state och returnera None.
        from sqlalchemy.orm import object_session
        sess = object_session(p)
        if sess is not None:
            try:
                sess.rollback()
            except Exception:
                pass
        return None


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
        partner_profession=_safe_profile_attr(p, "partner_profession"),
        partner_gross_salary=_safe_profile_attr(p, "partner_gross_salary"),
        cost_split_preference=_safe_profile_attr(p, "cost_split_preference"),
        cost_split_decided_at=_safe_profile_attr(p, "cost_split_decided_at"),
        backstory=p.backstory,
    )


# ---------- Teacher: bootstrap + login ----------

@router.post("/teacher/bootstrap", response_model=TeacherAuthOut)
def bootstrap_teacher(
    payload: TeacherBootstrapIn, request: Request,
) -> TeacherAuthOut:
    """Skapa första lärarkontot.

    - Om HEMBUDGET_BOOTSTRAP_SECRET är satt i env måste payloadens
      bootstrap_secret matcha (extra skydd när tjänsten ligger publikt).
    - Om env-varen INTE är satt räcker det att inga lärare finns — då
      kan första besökaren skapa kontot direkt från UI.
    - 410 Gone så snart minst en lärare finns."""
    _require_school_mode()
    # Rate-limit + Turnstile för bootstrap — annars kan en angripare
    # race:a mot en nyuppsatt server innan admin hunnit skapa kontot.
    check_rate_limit(request, "bootstrap", RULES_BOOTSTRAP)
    verify_turnstile(request, required=True)
    expected = os.environ.get("HEMBUDGET_BOOTSTRAP_SECRET", "")
    if expected:
        if not payload.bootstrap_secret or payload.bootstrap_secret != expected:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Invalid bootstrap secret",
            )
    with master_session() as s:
        # Demo-lärare räknas INTE som "riktig" lärare — de skapas på
        # startup via demo_seed och ska inte blockera bootstrap av den
        # första skarpa admin-läraren. Bara icke-demo-lärare tittar vi på.
        if s.query(Teacher).filter(Teacher.is_demo.is_(False)).count() > 0:
            raise HTTPException(
                status.HTTP_410_GONE, "Teachers already exist",
            )
        # Bootstrap-läraren är alltid super-admin — det är den enda lärare
        # som kan tilldela AI-rättigheter till övriga lärare. Räknas
        # email-verifierad direkt (vi litar på att env-var-admin har
        # rätt mail).
        teacher = Teacher(
            email=payload.email.lower(),
            name=payload.name,
            password_hash=hash_password(payload.password),
            is_super_admin=True,
            email_verified_at=datetime.utcnow(),
        )
        s.add(teacher)
        s.flush()
        tid = teacher.id
        tname = teacher.name
        temail = teacher.email
        tfam = teacher.is_family_account

    token = random_token()
    register_token(token, role="teacher", teacher_id=tid)
    return TeacherAuthOut(
        token=token, teacher_id=tid, name=tname, email=temail,
        is_family_account=tfam,
    )


@router.post("/teacher/login", response_model=TeacherAuthOut)
def teacher_login(
    payload: TeacherLoginIn, request: Request,
) -> TeacherAuthOut:
    _require_school_mode()
    # Rate-limit login per IP — brute-force-skydd.
    check_rate_limit(request, "teacher-login", RULES_LOGIN)
    verify_turnstile(request, required=True)
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
        # Blockera login om e-post inte är verifierad. Bootstrap- och
        # demo-lärare samt gamla konton (backfill vid migration) är
        # redan verifierade, så detta träffar bara nya open-signup-
        # lärare som glömt klicka länken.
        if teacher.email_verified_at is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "email_unverified",
            )
        tid = teacher.id
        tname = teacher.name
        temail = teacher.email
        tfam = teacher.is_family_account
    token = random_token()
    register_token(token, role="teacher", teacher_id=tid)
    return TeacherAuthOut(
        token=token, teacher_id=tid, name=tname, email=temail,
        is_family_account=tfam,
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
        has_profile=s.profile is not None,
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
            old_scope_key = scope_for_student(student)
            student.family_id = new_family_id
            s.flush()
            new_scope_key = scope_for_student(student)
            # Om scopet faktiskt ändrades: stäng gamla engine-handeln
            # från cachen (behåll filen — innehåller ev. historik).
            # Om eleven var ensam i gamla familje-scope kan vi även
            # radera filen, men för säkerhets skull behåller vi den.
            if old_scope_key != new_scope_key:
                dispose_scope_engine(old_scope_key)
            # Säkerställ att nya scope-DB:n finns
            get_scope_engine(new_scope_key)
        s.refresh(student)
        return _student_to_out(student)


@router.get("/teacher/students/{student_id}/qr")
def student_qr_code(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
):
    """Returnera en PNG-QR-kod för elevens login_code. Användbart för
    att skriva ut till klassen eller projicera på tavlan.
    QR-koden innehåller bara koden (inte URL:en) — eleverna anger den
    manuellt på inloggningssidan."""
    import io
    from fastapi.responses import Response
    try:
        import qrcode
    except ImportError:
        raise HTTPException(500, "qrcode library not installed")
    _require_school_mode()
    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == info.teacher_id,
        ).first()
        if not student:
            raise HTTPException(404, "Student not found")
        code = student.login_code

    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f172a", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


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


@router.post("/teacher/students/{student_id}/repair-profile", response_model=StudentOut)
def repair_student_profile(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> StudentOut:
    """Skapa StudentProfile-raden för en "föräldralös" elev.

    Bakgrund: om master-migrationerna inte hunnit köra när första
    eleven skapades så kunde profile-INSERTen krascha medan
    Student-raden redan var commitad — då blev eleven "föräldralös"
    (Student finns men StudentProfile saknas). Defensiv-fixen i
    `_create_profile_for_student` förhindrar nya sådana fall, men
    befintliga elever måste lagas.

    Endpointen är idempotent: kan köras flera gånger, gör bara något
    om profilen faktiskt saknas. Returnerar uppdaterad StudentOut.
    """
    _require_school_mode()
    with master_session() as s:
        student = (
            s.query(Student)
            .filter(Student.id == student_id, Student.teacher_id == info.teacher_id)
            .first()
        )
        if not student:
            raise HTTPException(404, "Student not found")
        if student.profile is not None:
            # Idempotent: redan reparerad / aldrig trasig
            return _student_to_out(student)
        _create_profile_for_student(s, student)
        # Säkerställ att scope-DB:n finns (kategorier seedas där)
        get_scope_engine(scope_for_student(student))
        s.refresh(student)
        return _student_to_out(student)


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
    """Radera en familj. Kräver att den är TOM — alla medlemmar måste
    först flyttas ur via /teacher/students/{id} PATCH {family_id: null}.

    Anledning: familjens scope-DB innehåller hela hushållets data
    (transaktioner, budget, lån). Om vi tillät radering med aktiva
    medlemmar skulle vi antingen:
    1. Radera datat (tidigare bugg — data-förlust)
    2. Behålla filen som föräldralös (svårt att städa upp senare)
    3. Försöka migrera datat till en medlems solo-DB (komplex, riskfylld
       om flera medlemmar)

    Enklast och säkrast: kräv explicit åtgärd av läraren.
    """
    _require_school_mode()
    with master_session() as s:
        fam = s.query(Family).filter(
            Family.id == family_id,
            Family.teacher_id == info.teacher_id,
        ).first()
        if not fam:
            raise HTTPException(404, "Family not found")
        if len(fam.members) > 0:
            raise HTTPException(
                400,
                f"Familjen har fortfarande {len(fam.members)} medlem(mar). "
                f"Flytta dem till solo eller annan familj innan du tar bort "
                f"familjen. Detta skyddar deras data.",
            )
        s.delete(fam)
    # Säkert att radera scope-DB:n nu — ingen har data där längre
    drop_scope_db(f"f_{family_id}")
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
    """Eleven läser sin egen profil. Pedagogiskt: partner-lön döljs
    förrän eleven gjort cost-split-valet ('veil of ignorance')."""
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
        out = _profile_to_out(student.profile)
        # Dölj partner-lön tills eleven gjort cost-split-valet. Annars
        # förstör vi ärligheten i pedagogiken.
        is_household = student.profile.family_status in (
            "sambo", "familj_med_barn",
        )
        if is_household and not _safe_profile_attr(
            student.profile, "cost_split_preference",
        ):
            out.partner_gross_salary = None
            # Behåll partner_profession + partner_age — eleven får veta
            # ATT hen har en partner och vad partnern gör, men inte
            # exakt lön.
        return out


# ---------- Cost-split-preference ('veil of ignorance'-onboarding) ----------
#
# Pedagogiskt: eleven måste välja fördelningsmodell INNAN partner-lönen
# avslöjas. Det blir ett ärligt etiskt val (Rawls 'veil of ignorance')
# istället för ett rationellt självoptimerings-val. Endpointen
# blockerar att se partner-lön förrän valet gjorts.

class CostSplitOut(BaseModel):
    family_status: str
    needs_decision: bool  # True om sambo/familj OCH ej beslutat
    cost_split_preference: Optional[str] = None
    cost_split_decided_at: Optional[datetime] = None
    # Visa BARA om beslut gjorts:
    partner_profession: Optional[str] = None
    partner_gross_salary: Optional[int] = None
    student_share_pct: Optional[float] = None  # Beräknad andel (0-100)


class CostSplitIn(BaseModel):
    preference: str  # "even_50_50" | "pro_rata" | "all_shared"


def _calc_student_share(
    pref: str, student_salary: int, partner_salary: int,
) -> float:
    """Räknar elevens andel av gemensamma kostnader baserat på modellen."""
    if pref == "even_50_50":
        return 50.0
    total = student_salary + partner_salary
    if total <= 0:
        return 50.0
    # pro_rata och all_shared använder samma formel — i all_shared går
    # alla pengar via gemensamma konton men bokföringen är samma.
    return round(student_salary / total * 100, 1)


@router.get("/student/cost-split", response_model=CostSplitOut)
def student_get_cost_split(
    info: TokenInfo = Depends(require_token),
) -> CostSplitOut:
    """Returnerar elevens cost-split-status. Visar partner_profession +
    partner_gross_salary BARA om eleven redan beslutat — annars är
    fälten None ('veil of ignorance')."""
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == info.student_id
        ).first()
        if not student or not student.profile:
            raise HTTPException(404, "Profil saknas")
        p = student.profile

        is_household = p.family_status in ("sambo", "familj_med_barn")
        pref = _safe_profile_attr(p, "cost_split_preference")
        decided = pref is not None

        out = CostSplitOut(
            family_status=p.family_status,
            needs_decision=is_household and not decided,
            cost_split_preference=pref,
            cost_split_decided_at=_safe_profile_attr(p, "cost_split_decided_at"),
        )
        # Avslöja partner-info bara om eleven redan beslutat
        if decided and is_household:
            partner_salary = _safe_profile_attr(p, "partner_gross_salary")
            out.partner_profession = _safe_profile_attr(p, "partner_profession")
            out.partner_gross_salary = partner_salary
            out.student_share_pct = _calc_student_share(
                pref,
                p.gross_salary_monthly,
                partner_salary or 0,
            )
        return out


@router.post("/student/cost-split", response_model=CostSplitOut)
def student_set_cost_split(
    payload: CostSplitIn,
    info: TokenInfo = Depends(require_token),
) -> CostSplitOut:
    """Eleven sätter sin fördelningsmodell. Idempotent: kan ändras
    senare men cost_split_decided_at uppdateras inte (vi sparar det
    *första* valet — det är det pedagogiskt centrala)."""
    from datetime import datetime as _dt

    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    if payload.preference not in {"even_50_50", "pro_rata", "all_shared"}:
        raise HTTPException(400, "Ogiltig preference")

    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == info.student_id
        ).first()
        if not student or not student.profile:
            raise HTTPException(404, "Profil saknas")
        p = student.profile
        if p.family_status == "ensam":
            raise HTTPException(
                400, "Ensamhushåll har ingen partner att dela kostnader med",
            )
        if not master_has_column("student_profiles", "cost_split_preference"):
            # Migration ej körd ännu — be admin reparera DB-schemat innan
            # eleven gör cost-split-valet.
            raise HTTPException(
                503,
                "DB-schemat är inte fullständigt — be administratören "
                "köra migrationerna (POST /admin/ai/db/run-migrations).",
            )

        first_time = _safe_profile_attr(p, "cost_split_preference") is None
        p.cost_split_preference = payload.preference
        if first_time:
            p.cost_split_decided_at = _dt.utcnow()
        s.flush()

        partner_salary = _safe_profile_attr(p, "partner_gross_salary")
        share = _calc_student_share(
            payload.preference,
            p.gross_salary_monthly,
            partner_salary or 0,
        )
        return CostSplitOut(
            family_status=p.family_status,
            needs_decision=False,
            cost_split_preference=payload.preference,
            cost_split_decided_at=_safe_profile_attr(p, "cost_split_decided_at"),
            partner_profession=_safe_profile_attr(p, "partner_profession"),
            partner_gross_salary=partner_salary,
            student_share_pct=share,
        )


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


# Mappning från onboarding-fältnamn → app-kategorinamn. Vi sparar
# budgeten till elevens scope-DB:s Budget-tabell. Om kategorin saknas
# skapas den, så elevens budget alltid landar någonstans.
ONBOARDING_TO_CATEGORY: dict[str, str] = {
    "mat": "Mat",
    "individuellt_ovrigt": "Kläder & Skor",
    "boende": "Hyra",  # justeras nedan beroende på housing_type
    "el": "El",
    "bredband_mobil": "Internet",
    "medietjanster": "Streaming",
    "forbrukningsvaror": "Hem & Hushåll",
    "hemutrustning": "Hemelektronik",
    "vatten_avlopp": "Vatten/Avgift",
    "hemforsakring": "Hemförsäkring",
    "transport": "Transport",
    "lan_amortering_ranta": "Bolåneränta",
    "sparande": "Sparande/Investering",
    "nojen_marginal": "Nöje",
}


class OnboardingBudgetIn(BaseModel):
    """Eleven skickar in den justerade budgeten från sista
    onboarding-steget. Nycklarna ska matcha BudgetSuggestionOut-fälten.
    Sparas i elevens scope-DB:s Budget-tabell för innevarande månad."""
    year_month: Optional[str] = Field(
        default=None, pattern=r"^\d{4}-\d{2}$",
    )
    values: dict[str, int]


@router.post("/student/onboarding/complete")
def complete_onboarding(
    payload: OnboardingBudgetIn | None = None,
    info: TokenInfo = Depends(require_token),
) -> dict:
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    saved_count = 0
    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == info.student_id
        ).first()
        if not student:
            raise HTTPException(404, "Student not found")
        # Säkerställ att profilen finns — behövs för housing_type-mappingen
        # nedan och för att elevens framtida scenario-genereringar ska
        # fungera. För elever skapade innan profile-fältet fanns.
        if not student.profile:
            _create_profile_for_student(s, student)
        student.onboarding_completed = True
        scope_key = scope_for_student(student)
        housing_type = student.profile.housing_type

    # Spara budgeten till elevens scope-DB om vi fick värden
    if payload and payload.values:
        from datetime import date as _date
        from decimal import Decimal as _Dec
        from ..db.base import session_scope as _ss
        from ..db.models import Budget, Category

        # Innevarande månad om inget angavs
        target_month = payload.year_month or _date.today().strftime("%Y-%m")

        # Justera boende-mappingen efter elevens boendetyp
        mapping = dict(ONBOARDING_TO_CATEGORY)
        if housing_type == "bostadsratt":
            mapping["boende"] = "Boende"  # ej Hyra för BRF/villa
        elif housing_type == "villa":
            mapping["boende"] = "Boende"

        with scope_context(scope_key):
            with _ss() as scope_s:
                cat_by_name = {
                    c.name: c for c in scope_s.query(Category).all()
                }
                for field_key, amount in payload.values.items():
                    if amount <= 0:
                        continue
                    cat_name = mapping.get(field_key)
                    if not cat_name:
                        continue
                    cat = cat_by_name.get(cat_name)
                    if not cat:
                        # Skapa kategorin om den saknas
                        cat = Category(name=cat_name)
                        scope_s.add(cat)
                        scope_s.flush()
                        cat_by_name[cat_name] = cat
                    # Upsert: en post per (month, category_id)
                    existing = (
                        scope_s.query(Budget)
                        .filter(
                            Budget.month == target_month,
                            Budget.category_id == cat.id,
                        )
                        .first()
                    )
                    if existing:
                        existing.planned_amount = _Dec(amount)
                    else:
                        scope_s.add(Budget(
                            month=target_month,
                            category_id=cat.id,
                            planned_amount=_Dec(amount),
                        ))
                    saved_count += 1

    # Default-uppdrag: "Sätt din första budget" — skapa om saknas
    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == info.student_id
        ).first()
        if student and s.query(Assignment).filter(
            Assignment.student_id == student.id,
            Assignment.kind == "set_budget",
        ).count() == 0:
            from ..teacher.assignments import DEFAULT_ASSIGNMENTS_FOR_NEW_STUDENT
            for spec in DEFAULT_ASSIGNMENTS_FOR_NEW_STUDENT:
                s.add(Assignment(
                    teacher_id=student.teacher_id,
                    student_id=student.id,
                    title=spec["title"],
                    description=spec["description"],
                    kind=spec["kind"],
                ))
    return {"ok": True, "budget_rows_saved": saved_count}


# ---------- Elev-dashboard ----------

class DashboardCategoryRow(BaseModel):
    category: str
    budget: int
    spent: int
    pct: int


class DashboardOvershootRow(BaseModel):
    date: str
    description: str
    amount: int
    category_hint: Optional[str] = None


class InactivityNudgeOut(BaseModel):
    days_away: int
    last_active: str  # ISO-datum


class StudentDashboardOut(BaseModel):
    year_month: str
    net_income: int
    total_spent: int
    balance: int  # net_income - total_spent
    savings_done: int
    savings_goal: Optional[int] = None
    category_rows: list[DashboardCategoryRow]
    recent_overshoots: list[DashboardOvershootRow]
    assignments_done: int
    assignments_total: int
    personality: str
    profession: str
    display_name: str
    # Sätts om eleven inte har klarat ett steg på >= 5 dagar MEN har
    # minst ett historiskt klart steg. Frontend visar en välkomst-banner.
    inactivity_nudge: Optional[InactivityNudgeOut] = None


@router.get("/student/dashboard", response_model=StudentDashboardOut)
def student_dashboard(
    year_month: Optional[str] = None,
    info: TokenInfo = Depends(require_token),
) -> StudentDashboardOut:
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    from datetime import date as _date
    from decimal import Decimal as _Dec
    from ..db.base import session_scope as _ss
    from ..db.models import Budget, Category, Transaction
    from ..teacher.assignments import evaluate

    ym = year_month or _date.today().strftime("%Y-%m")
    y, m = map(int, ym.split("-"))
    start = _date(y, m, 1)
    end = _date(y + 1, 1, 1) if m == 12 else _date(y, m + 1, 1)

    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == info.student_id
        ).first()
        if not student or not student.profile:
            raise HTTPException(404, "Student/profile not found")
        display_name = student.display_name
        personality = student.profile.personality
        profession = student.profile.profession
        net_income_default = student.profile.net_salary_monthly
        scope_key = scope_for_student(student)

        # Assignments-summary
        assignments = s.query(Assignment).filter(
            Assignment.student_id == student.id
        ).all()
        a_done = 0
        a_total = len(assignments)
        savings_goal: int | None = None
        for a in assignments:
            try:
                res = evaluate(a, student)
                if res.status == "completed":
                    a_done += 1
                if a.kind == "save_amount" and a.params:
                    goal = a.params.get("amount")
                    if isinstance(goal, (int, float)):
                        savings_goal = max(savings_goal or 0, int(goal))
            except Exception:
                continue

    # Scope-DB-query
    category_rows: list[DashboardCategoryRow] = []
    overshoots: list[DashboardOvershootRow] = []
    total_spent = 0
    savings_done = 0
    net_income = net_income_default

    with scope_context(scope_key):
        with _ss() as scope_s:
            # Månadens tx
            txs = (
                scope_s.query(Transaction)
                .filter(Transaction.date >= start, Transaction.date < end)
                .all()
            )
            # Faktisk inkomst denna månad (summa positiva)
            positive = sum(
                float(t.amount) for t in txs
                if float(t.amount) > 0 and not t.is_transfer
            )
            if positive > 0:
                net_income = int(round(positive))

            # Aggregera utgifter per kategori
            cats_by_id = {c.id: c for c in scope_s.query(Category).all()}
            spent_by_cat: dict[int, int] = {}
            for t in txs:
                amt = float(t.amount)
                if amt >= 0 or t.is_transfer:
                    continue
                cid = t.category_id or 0
                spent_by_cat[cid] = spent_by_cat.get(cid, 0) + int(abs(amt))
                total_spent += int(abs(amt))
                # Markera stora oväntade utgifter som overshoots
                if abs(amt) >= 1500:
                    overshoots.append(DashboardOvershootRow(
                        date=t.date.isoformat(),
                        description=t.raw_description,
                        amount=int(abs(amt)),
                        category_hint=(
                            cats_by_id.get(cid).name if cid in cats_by_id else None
                        ),
                    ))

            # Sparkonto-överföringar räknas separat (negativa tx men inte utgift)
            for t in txs:
                if float(t.amount) < 0 and (
                    "SPARKONTO" in t.raw_description.upper()
                    or "SPARANDE" in t.raw_description.upper()
                ):
                    savings_done += int(abs(float(t.amount)))
                    # Dra bort från total_spent om vi räknade dubbelt
                    total_spent -= int(abs(float(t.amount)))

            # Budget per kategori
            budget_rows = (
                scope_s.query(Budget).filter(Budget.month == ym).all()
            )
            for br in budget_rows:
                cat = cats_by_id.get(br.category_id)
                if not cat:
                    continue
                budget = int(br.planned_amount)
                spent = spent_by_cat.get(cat.id, 0)
                pct = int(100 * spent / budget) if budget > 0 else 0
                category_rows.append(DashboardCategoryRow(
                    category=cat.name,
                    budget=budget,
                    spent=spent,
                    pct=pct,
                ))

    # Sortera overshoots nyast först, max 5
    overshoots.sort(key=lambda o: o.date, reverse=True)
    overshoots = overshoots[:5]
    # Sortera kategorier efter % (överskridna först)
    category_rows.sort(key=lambda r: -r.pct)

    balance = net_income - total_spent - savings_done

    # Inaktivitets-nudge: var eleven borta ≥ 5 dagar?
    nudge: Optional[InactivityNudgeOut] = None
    with master_session() as s:
        last_prog = (
            s.query(StudentStepProgress)
            .filter(
                StudentStepProgress.student_id == info.student_id,
                StudentStepProgress.completed_at.isnot(None),
            )
            .order_by(StudentStepProgress.completed_at.desc())
            .first()
        )
        if last_prog and last_prog.completed_at:
            days = (datetime.utcnow() - last_prog.completed_at).days
            if days >= 5:
                nudge = InactivityNudgeOut(
                    days_away=days,
                    last_active=last_prog.completed_at.date().isoformat(),
                )

    return StudentDashboardOut(
        year_month=ym,
        net_income=net_income,
        total_spent=total_spent,
        balance=balance,
        savings_done=savings_done,
        savings_goal=savings_goal,
        category_rows=category_rows,
        recent_overshoots=overshoots,
        assignments_done=a_done,
        assignments_total=a_total,
        personality=personality,
        profession=profession,
        display_name=display_name,
        inactivity_nudge=nudge,
    )


# ---------- Assignments / uppdrag ----------

class AssignmentIn(BaseModel):
    title: str
    description: str
    kind: str  # "set_budget" | "import_batch" | "balance_month" | ...
    student_id: Optional[int] = None  # None = bulk till alla mina elever
    target_year_month: Optional[str] = Field(
        default=None, pattern=r"^\d{4}-\d{2}$",
    )
    params: Optional[dict] = None


class AssignmentOut(BaseModel):
    id: int
    teacher_id: int
    student_id: Optional[int]
    title: str
    description: str
    kind: str
    target_year_month: Optional[str]
    params: Optional[dict]
    created_at: datetime


class AssignmentStatusOut(AssignmentOut):
    status: str  # "not_started" | "in_progress" | "completed"
    progress: str
    detail: Optional[dict] = None
    teacher_feedback: Optional[str] = None
    teacher_feedback_at: Optional[datetime] = None


def _assignment_to_out(a: Assignment) -> AssignmentOut:
    return AssignmentOut(
        id=a.id, teacher_id=a.teacher_id, student_id=a.student_id,
        title=a.title, description=a.description, kind=a.kind,
        target_year_month=a.target_year_month, params=a.params,
        created_at=a.created_at,
    )


@router.post("/teacher/assignments", response_model=list[AssignmentOut])
def create_assignment(
    payload: AssignmentIn,
    info: TokenInfo = Depends(require_teacher),
) -> list[AssignmentOut]:
    """Skapa ett uppdrag för en specifik elev eller alla mina elever
    (om student_id=None). Returnerar lista — en post per elev när bulk."""
    _require_school_mode()
    out: list[AssignmentOut] = []
    with master_session() as s:
        if payload.student_id is not None:
            # Validera ägarskap
            stu = s.query(Student).filter(
                Student.id == payload.student_id,
                Student.teacher_id == info.teacher_id,
            ).first()
            if not stu:
                raise HTTPException(404, "Student not found")
            target_ids = [payload.student_id]
        else:
            target_ids = [
                st.id for st in s.query(Student).filter(
                    Student.teacher_id == info.teacher_id,
                    Student.active.is_(True),
                ).all()
            ]
        for sid in target_ids:
            a = Assignment(
                teacher_id=info.teacher_id,
                student_id=sid,
                title=payload.title,
                description=payload.description,
                kind=payload.kind,
                target_year_month=payload.target_year_month,
                params=payload.params,
            )
            s.add(a)
            s.flush()
            out.append(_assignment_to_out(a))
    return out


class AssignmentFeedbackIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    # Om True nollställs manually_completed_at så eleven måste
    # markera uppdraget som klart igen efter att ha läst feedbacken.
    request_retry: bool = False


@router.post("/teacher/assignments/{assignment_id}/feedback")
def assignment_feedback(
    assignment_id: int,
    payload: AssignmentFeedbackIn,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    """Lärare lämnar skriftlig återkoppling på ett uppdrag. Eleven ser
    texten i uppdrags-vyn. Om request_retry=True nollas status så
    eleven ombeds att försöka igen."""
    _require_school_mode()
    with master_session() as s:
        a = s.query(Assignment).filter(
            Assignment.id == assignment_id,
            Assignment.teacher_id == info.teacher_id,
        ).first()
        if not a:
            raise HTTPException(
                404, "Uppdrag finns ej eller tillhör inte dig",
            )
        a.teacher_feedback = payload.body.strip()
        a.teacher_feedback_at = datetime.utcnow()
        if payload.request_retry:
            a.manually_completed_at = None
    return {"ok": True}


@router.get(
    "/teacher/assignments",
    response_model=list[AssignmentStatusOut],
)
def list_assignments(
    student_id: Optional[int] = None,
    info: TokenInfo = Depends(require_teacher),
) -> list[AssignmentStatusOut]:
    """Lista alla uppdrag (eller för en specifik elev) med live-status."""
    _require_school_mode()
    from ..teacher.assignments import evaluate
    with master_session() as s:
        q = s.query(Assignment).filter(
            Assignment.teacher_id == info.teacher_id,
        )
        if student_id is not None:
            q = q.filter(Assignment.student_id == student_id)
        assignments = q.order_by(Assignment.created_at.desc()).all()
        out: list[AssignmentStatusOut] = []
        for a in assignments:
            student = (
                s.query(Student).filter(Student.id == a.student_id).first()
                if a.student_id else None
            )
            if student:
                try:
                    res = evaluate(a, student)
                    status_val = res.status
                    progress = res.progress
                    detail = res.detail
                except Exception as e:
                    log.exception("Assignment eval failed for %d", a.id)
                    status_val = "in_progress"
                    progress = f"Fel vid utvärdering: {e}"
                    detail = None
            else:
                status_val = "in_progress"
                progress = "Bulk-uppdrag (ingen specifik elev)"
                detail = None
            base = _assignment_to_out(a)
            out.append(AssignmentStatusOut(
                **base.model_dump(),
                status=status_val,
                progress=progress,
                detail=detail,
                teacher_feedback=a.teacher_feedback,
                teacher_feedback_at=a.teacher_feedback_at,
            ))
        return out


class MatrixAssignment(BaseModel):
    title: str
    kind: str
    target_year_month: Optional[str] = None


class MatrixCell(BaseModel):
    assignment_id: Optional[int] = None  # null = eleven saknar uppdraget
    status: str  # "not_started" | "in_progress" | "completed" | "missing"
    progress: Optional[str] = None


class MatrixStudent(BaseModel):
    student_id: int
    display_name: str
    class_label: Optional[str] = None
    cells: list[MatrixCell]


class AssignmentMatrixOut(BaseModel):
    columns: list[MatrixAssignment]
    rows: list[MatrixStudent]


@router.get("/teacher/assignments/matrix",
            response_model=AssignmentMatrixOut)
def assignment_matrix(
    info: TokenInfo = Depends(require_teacher),
) -> AssignmentMatrixOut:
    """Klassöversikt: alla lärarens elever (rader) × alla unika uppdrag
    (kolumner). Varje cell visar elevens status för det uppdraget eller
    "missing" om eleven inte har det."""
    _require_school_mode()
    from ..teacher.assignments import evaluate
    with master_session() as s:
        students = (
            s.query(Student)
            .filter(Student.teacher_id == info.teacher_id)
            .order_by(Student.class_label, Student.display_name)
            .all()
        )
        # Alla uppdrag grupperade på (title, kind, target_year_month)
        all_assignments = (
            s.query(Assignment)
            .filter(Assignment.teacher_id == info.teacher_id)
            .order_by(Assignment.created_at)
            .all()
        )
        unique_keys: list[tuple] = []
        seen: set[tuple] = set()
        for a in all_assignments:
            key = (a.title, a.kind, a.target_year_month)
            if key not in seen:
                seen.add(key)
                unique_keys.append(key)

        columns = [
            MatrixAssignment(
                title=k[0], kind=k[1], target_year_month=k[2],
            )
            for k in unique_keys
        ]

        rows: list[MatrixStudent] = []
        for st in students:
            student_assignments = {
                (a.title, a.kind, a.target_year_month): a
                for a in all_assignments
                if a.student_id == st.id
            }
            cells: list[MatrixCell] = []
            for key in unique_keys:
                a = student_assignments.get(key)
                if not a:
                    cells.append(MatrixCell(status="missing"))
                    continue
                try:
                    res = evaluate(a, st)
                    cells.append(MatrixCell(
                        assignment_id=a.id,
                        status=res.status,
                        progress=res.progress,
                    ))
                except Exception as e:
                    cells.append(MatrixCell(
                        assignment_id=a.id,
                        status="in_progress",
                        progress=str(e),
                    ))
            rows.append(MatrixStudent(
                student_id=st.id,
                display_name=st.display_name,
                class_label=st.class_label,
                cells=cells,
            ))
        return AssignmentMatrixOut(columns=columns, rows=rows)


@router.delete("/teacher/assignments/{assignment_id}")
def delete_assignment(
    assignment_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    _require_school_mode()
    with master_session() as s:
        a = s.query(Assignment).filter(
            Assignment.id == assignment_id,
            Assignment.teacher_id == info.teacher_id,
        ).first()
        if not a:
            raise HTTPException(404, "Assignment not found")
        s.delete(a)
    return {"ok": True}


@router.get("/student/assignments", response_model=list[AssignmentStatusOut])
def student_my_assignments(
    info: TokenInfo = Depends(require_token),
) -> list[AssignmentStatusOut]:
    """Lista uppdrag för aktiv elev. Tillåter lärar-impersonation via
    x-as-student-headern så lärare kan kolla elevens vy utan 403."""
    _require_school_mode()
    from ..api.modules import _resolve_student_actor
    student_id = _resolve_student_actor(info)
    from ..teacher.assignments import evaluate
    with master_session() as s:
        student = s.query(Student).filter(Student.id == student_id).first()
        if not student:
            raise HTTPException(404, "Student not found")
        assignments = s.query(Assignment).filter(
            Assignment.student_id == student.id,
        ).order_by(Assignment.created_at.desc()).all()
        out: list[AssignmentStatusOut] = []
        for a in assignments:
            try:
                res = evaluate(a, student)
            except Exception as e:
                log.exception("Assignment eval failed")
                res = type("R", (), {
                    "status": "in_progress",
                    "progress": str(e),
                    "detail": None,
                })()
            base = _assignment_to_out(a)
            out.append(AssignmentStatusOut(
                **base.model_dump(),
                status=res.status, progress=res.progress, detail=res.detail,
                teacher_feedback=a.teacher_feedback,
                teacher_feedback_at=a.teacher_feedback_at,
            ))
        return out


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
                # SAVEPOINT per elev: om en specifik elev-batch failar
                # (t.ex. unika constraint, integer-overflow, etc.) ska
                # sessionen rollbacka isolerat så övriga elever lyckas
                # och hela POST-svaret inte blir 500.
                with s.begin_nested():
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
                    # Auto-skapa import-uppdrag för månaden om det inte finns
                    from ..teacher.assignments import (
                        DEFAULT_ASSIGNMENT_FOR_NEW_BATCH,
                    )
                    exists_a = s.query(Assignment).filter(
                        Assignment.student_id == student.id,
                        Assignment.kind == "import_batch",
                        Assignment.target_year_month == payload.year_month,
                    ).first()
                    if not exists_a:
                        s.add(Assignment(
                            teacher_id=info.teacher_id,
                            student_id=student.id,
                            title=(
                                f"Importera dokument för {payload.year_month}"
                            ),
                            description=DEFAULT_ASSIGNMENT_FOR_NEW_BATCH[
                                "description"
                            ],
                            kind="import_batch",
                            target_year_month=payload.year_month,
                        ))
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


class TeacherAllBatchesRow(BaseModel):
    student_id: int
    display_name: str
    class_label: Optional[str]
    family_name: Optional[str]
    batch: Optional[ScenarioBatchOut]


@router.get("/teacher/batches/by-month/{year_month}",
            response_model=list[TeacherAllBatchesRow])
def list_all_batches_for_month(
    year_month: str,
    info: TokenInfo = Depends(require_teacher),
) -> list[TeacherAllBatchesRow]:
    """Samlad vy: alla lärarens elever + deras batch för given månad.
    Visar tomt (batch=None) om ingen batch skapad för eleven ännu."""
    _require_school_mode()
    with master_session() as s:
        students = (
            s.query(Student)
            .filter(Student.teacher_id == info.teacher_id)
            .order_by(Student.class_label, Student.display_name)
            .all()
        )
        out: list[TeacherAllBatchesRow] = []
        for st in students:
            batch = s.query(ScenarioBatch).filter(
                ScenarioBatch.student_id == st.id,
                ScenarioBatch.year_month == year_month,
            ).first()
            out.append(TeacherAllBatchesRow(
                student_id=st.id,
                display_name=st.display_name,
                class_label=st.class_label,
                family_name=st.family.name if st.family else None,
                batch=_batch_to_out(batch) if batch else None,
            ))
        return out


# ---------- Facit-check för elevens kategoriseringar ----------

class CategoryCheckRow(BaseModel):
    tx_id: int
    date: str
    description: str
    amount: float
    expected_category: str
    actual_category: Optional[str]
    is_correct: bool
    is_uncategorized: bool


class CategoryCheckOut(BaseModel):
    student_id: int
    display_name: str
    year_month: str
    total: int
    correct: int
    incorrect: int
    uncategorized: int
    rows: list[CategoryCheckRow]


@router.get(
    "/teacher/students/{student_id}/facit/{year_month}",
    response_model=CategoryCheckOut,
)
def category_facit(
    student_id: int, year_month: str,
    info: TokenInfo = Depends(require_teacher),
) -> CategoryCheckOut:
    """Jämför elevens valda kategori mot scenario-facit. Facit lagras i
    ScenarioBatch.meta['category_hints'] — vi matchar via (description,
    date, abs(amount)) mot motsvarande Transaction i elevens scope-DB.

    Matchas INTE mot tx.notes (det är elevens eget fält som vi inte
    skriver på)."""
    _require_school_mode()
    from datetime import date as _date
    from ..db.base import session_scope as _ss
    from ..db.models import Transaction, Category as _Cat

    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == info.teacher_id,
        ).first()
        if not student:
            raise HTTPException(404, "Student not found")
        scope_key = scope_for_student(student)
        name = student.display_name
        # Hämta facit från batch.meta för denna månad
        batch = s.query(ScenarioBatch).filter(
            ScenarioBatch.student_id == student_id,
            ScenarioBatch.year_month == year_month,
        ).first()
        facit_by_key: dict[tuple, str] = {}
        if batch and batch.meta:
            for h in batch.meta.get("category_hints", []):
                # Normalisera amount till positiv så vi kan matcha både
                # konto-tx (negativa) och kort-tx (negativa vid import)
                key = (
                    h["description"],
                    h["date"],
                    abs(float(h["amount"])),
                )
                facit_by_key[key] = h["hint"]

    y, m = map(int, year_month.split("-"))
    start = _date(y, m, 1)
    end = _date(y + 1, 1, 1) if m == 12 else _date(y, m + 1, 1)
    rows: list[CategoryCheckRow] = []
    total = correct = incorrect = uncat = 0
    with scope_context(scope_key):
        with _ss() as scope_s:
            cats = {c.id: c.name for c in scope_s.query(_Cat).all()}
            txs = (
                scope_s.query(Transaction)
                .filter(Transaction.date >= start, Transaction.date < end)
                .order_by(Transaction.date)
                .all()
            )
            for t in txs:
                key = (
                    t.raw_description,
                    t.date.isoformat(),
                    abs(float(t.amount)),
                )
                expected = facit_by_key.get(key)
                if not expected:
                    continue
                actual = cats.get(t.category_id) if t.category_id else None
                is_cat = actual is not None
                is_correct = is_cat and (
                    actual == expected or
                    # Föräldrakategori räknas också som rätt
                    _is_parent(cats, t.category_id, expected, scope_s)
                )
                total += 1
                if not is_cat:
                    uncat += 1
                elif is_correct:
                    correct += 1
                else:
                    incorrect += 1
                rows.append(CategoryCheckRow(
                    tx_id=t.id,
                    date=t.date.isoformat(),
                    description=t.raw_description,
                    amount=float(t.amount),
                    expected_category=expected,
                    actual_category=actual,
                    is_correct=is_correct,
                    is_uncategorized=not is_cat,
                ))
    return CategoryCheckOut(
        student_id=student_id, display_name=name, year_month=year_month,
        total=total, correct=correct, incorrect=incorrect,
        uncategorized=uncat, rows=rows,
    )


def _is_parent(cats_by_id: dict, category_id, expected_name: str, s) -> bool:
    """Kolla om facit-kategori är förälder till elevens val."""
    from ..db.models import Category as _C
    row = s.query(_C).filter(_C.id == category_id).first()
    if not row or row.parent_id is None:
        return False
    return cats_by_id.get(row.parent_id) == expected_name


# ---------- Manual complete för free_text-uppdrag ----------

@router.post("/teacher/assignments/{assignment_id}/complete")
def manually_complete_assignment(
    assignment_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    """Manuell "klar"-markering av ett uppdrag. Används främst för
    kind="free_text" där automatisk utvärdering inte går."""
    _require_school_mode()
    from datetime import datetime as _dt
    with master_session() as s:
        a = s.query(Assignment).filter(
            Assignment.id == assignment_id,
            Assignment.teacher_id == info.teacher_id,
        ).first()
        if not a:
            raise HTTPException(404, "Assignment not found")
        a.manually_completed_at = _dt.utcnow()
    return {"ok": True}


@router.post("/teacher/assignments/{assignment_id}/uncomplete")
def uncomplete_assignment(
    assignment_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    _require_school_mode()
    with master_session() as s:
        a = s.query(Assignment).filter(
            Assignment.id == assignment_id,
            Assignment.teacher_id == info.teacher_id,
        ).first()
        if not a:
            raise HTTPException(404, "Assignment not found")
        a.manually_completed_at = None
    return {"ok": True}


# ---------- Skattesatser som settings ----------

class TaxSettingsIn(BaseModel):
    kommunal: float = Field(ge=0.10, le=0.45)
    statlig: float = Field(ge=0.10, le=0.30)
    brytpunkt: int = Field(ge=30_000, le=100_000)
    grundavdrag: int = Field(ge=0, le=5_000)


class TaxSettingsOut(TaxSettingsIn):
    is_default: bool
    updated_at: Optional[datetime] = None


@router.get("/teacher/settings/tax", response_model=TaxSettingsOut)
def get_tax_settings(
    info: TokenInfo = Depends(require_teacher),
) -> TaxSettingsOut:
    _require_school_mode()
    from ..school.models import AppConfig
    from ..school.tax import (
        DEFAULT_KOMMUNALSKATT, DEFAULT_STATLIG_SKATT,
        DEFAULT_BRYTPUNKT_MANATLIG, DEFAULT_GRUNDAVDRAG_MANATLIG,
    )
    with master_session() as s:
        row = s.query(AppConfig).filter(AppConfig.key == "tax").first()
        if row and row.value:
            v = row.value
            return TaxSettingsOut(
                kommunal=v.get("kommunal", DEFAULT_KOMMUNALSKATT),
                statlig=v.get("statlig", DEFAULT_STATLIG_SKATT),
                brytpunkt=v.get("brytpunkt", DEFAULT_BRYTPUNKT_MANATLIG),
                grundavdrag=v.get("grundavdrag", DEFAULT_GRUNDAVDRAG_MANATLIG),
                is_default=False,
                updated_at=row.updated_at,
            )
    return TaxSettingsOut(
        kommunal=DEFAULT_KOMMUNALSKATT,
        statlig=DEFAULT_STATLIG_SKATT,
        brytpunkt=DEFAULT_BRYTPUNKT_MANATLIG,
        grundavdrag=DEFAULT_GRUNDAVDRAG_MANATLIG,
        is_default=True,
    )


@router.put("/teacher/settings/tax", response_model=TaxSettingsOut)
def put_tax_settings(
    payload: TaxSettingsIn,
    info: TokenInfo = Depends(require_teacher),
) -> TaxSettingsOut:
    _require_school_mode()
    from ..school.models import AppConfig
    with master_session() as s:
        row = s.query(AppConfig).filter(AppConfig.key == "tax").first()
        if not row:
            row = AppConfig(key="tax", value=payload.model_dump())
            s.add(row)
        else:
            row.value = payload.model_dump()
    return TaxSettingsOut(**payload.model_dump(), is_default=False)


# ---------- Meddelanden (elev ↔ lärare) ----------

class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    context_type: Optional[str] = None
    context_id: Optional[int] = None


class MessageOut(BaseModel):
    id: int
    student_id: int
    teacher_id: int
    sender_role: str
    body: str
    context_type: Optional[str]
    context_id: Optional[int]
    read_at: Optional[datetime]
    created_at: datetime


class ThreadSummaryOut(BaseModel):
    student_id: int
    display_name: str
    class_label: Optional[str]
    last_message_at: Optional[datetime]
    last_message_preview: Optional[str]
    unread_count: int


def _msg_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id, student_id=m.student_id, teacher_id=m.teacher_id,
        sender_role=m.sender_role, body=m.body,
        context_type=m.context_type, context_id=m.context_id,
        read_at=m.read_at, created_at=m.created_at,
    )


@router.post("/student/messages", response_model=MessageOut)
def student_send_message(
    payload: MessageIn,
    info: TokenInfo = Depends(require_token),
) -> MessageOut:
    """Eleven skickar meddelande till sin lärare."""
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    with master_session() as s:
        student = s.query(Student).filter(
            Student.id == info.student_id
        ).first()
        if not student:
            raise HTTPException(404, "Student not found")
        msg = Message(
            student_id=student.id,
            teacher_id=student.teacher_id,
            sender_role="student",
            body=payload.body.strip(),
            context_type=payload.context_type,
            context_id=payload.context_id,
        )
        s.add(msg)
        s.flush()
        return _msg_out(msg)


@router.get("/student/messages", response_model=list[MessageOut])
def student_list_messages(
    info: TokenInfo = Depends(require_token),
) -> list[MessageOut]:
    """Elevens meddelandetråd (båda riktningarna, kronologiskt).
    Markerar samtidigt lärarens meddelanden som lästa."""
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    from datetime import datetime as _dt
    with master_session() as s:
        msgs = (
            s.query(Message)
            .filter(Message.student_id == info.student_id)
            .order_by(Message.created_at)
            .all()
        )
        # Markera lärare-meddelanden som lästa
        for m in msgs:
            if m.sender_role == "teacher" and m.read_at is None:
                m.read_at = _dt.utcnow()
        return [_msg_out(m) for m in msgs]


@router.get("/student/messages/unread-count")
def student_unread_count(
    info: TokenInfo = Depends(require_token),
) -> dict:
    _require_school_mode()
    if info.role != "student":
        return {"unread": 0}
    with master_session() as s:
        n = (
            s.query(Message)
            .filter(
                Message.student_id == info.student_id,
                Message.sender_role == "teacher",
                Message.read_at.is_(None),
            )
            .count()
        )
        return {"unread": n}


@router.get("/teacher/messages/threads",
            response_model=list[ThreadSummaryOut])
def teacher_list_threads(
    info: TokenInfo = Depends(require_teacher),
) -> list[ThreadSummaryOut]:
    """Översikt av alla trådar: en per elev. Visar senaste meddelande +
    oläst-räknare."""
    _require_school_mode()
    out: list[ThreadSummaryOut] = []
    with master_session() as s:
        students = (
            s.query(Student)
            .filter(Student.teacher_id == info.teacher_id)
            .order_by(Student.display_name)
            .all()
        )
        for st in students:
            last = (
                s.query(Message)
                .filter(Message.student_id == st.id)
                .order_by(Message.created_at.desc())
                .first()
            )
            unread = (
                s.query(Message)
                .filter(
                    Message.student_id == st.id,
                    Message.sender_role == "student",
                    Message.read_at.is_(None),
                )
                .count()
            )
            out.append(ThreadSummaryOut(
                student_id=st.id,
                display_name=st.display_name,
                class_label=st.class_label,
                last_message_at=last.created_at if last else None,
                last_message_preview=(
                    (last.body[:80] + ("…" if len(last.body) > 80 else ""))
                    if last else None
                ),
                unread_count=unread,
            ))
    # Sortera: olästa först, sedan senaste meddelande
    out.sort(
        key=lambda t: (
            -t.unread_count,
            t.last_message_at.isoformat() if t.last_message_at else "",
        ),
        reverse=False,
    )
    # Ovan sort ger olästa först (negativ unread=lägre) men senaste
    # meddelande hamnar stigande — fix:
    out.sort(
        key=lambda t: (
            0 if t.unread_count > 0 else 1,
            -(
                t.last_message_at.timestamp()
                if t.last_message_at else 0
            ),
        ),
    )
    return out


@router.get("/teacher/messages/threads/{student_id}",
            response_model=list[MessageOut])
def teacher_list_thread(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> list[MessageOut]:
    """Hämta hela tråden för en specifik elev + markera elev-msg som
    lästa."""
    _require_school_mode()
    from datetime import datetime as _dt
    with master_session() as s:
        stu = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == info.teacher_id,
        ).first()
        if not stu:
            raise HTTPException(404, "Student not found")
        msgs = (
            s.query(Message)
            .filter(Message.student_id == student_id)
            .order_by(Message.created_at)
            .all()
        )
        for m in msgs:
            if m.sender_role == "student" and m.read_at is None:
                m.read_at = _dt.utcnow()
        return [_msg_out(m) for m in msgs]


@router.post("/teacher/messages/threads/{student_id}",
             response_model=MessageOut)
def teacher_send_message(
    student_id: int,
    payload: MessageIn,
    info: TokenInfo = Depends(require_teacher),
) -> MessageOut:
    _require_school_mode()
    with master_session() as s:
        stu = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == info.teacher_id,
        ).first()
        if not stu:
            raise HTTPException(404, "Student not found")
        msg = Message(
            student_id=student_id,
            teacher_id=info.teacher_id,
            sender_role="teacher",
            body=payload.body.strip(),
            context_type=payload.context_type,
            context_id=payload.context_id,
        )
        s.add(msg)
        s.flush()
        return _msg_out(msg)


@router.get("/teacher/messages/unread-count")
def teacher_unread_count(
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    _require_school_mode()
    with master_session() as s:
        n = (
            s.query(Message)
            .join(Student, Message.student_id == Student.id)
            .filter(
                Student.teacher_id == info.teacher_id,
                Message.sender_role == "student",
                Message.read_at.is_(None),
            )
            .count()
        )
        return {"unread": n}


# ---------- Räntor + bolåne-beslut ----------

class RatePoint(BaseModel):
    year_month: str
    rate: float


class RateSeriesOut(BaseModel):
    rate_type: str
    points: list[RatePoint]


@router.get("/school/rates/{rate_type}", response_model=RateSeriesOut)
def get_rate_series(rate_type: str) -> RateSeriesOut:
    """Offentlig — används för ränte-graf i UI."""
    _require_school_mode()
    with master_session() as s:
        rows = (
            s.query(InterestRateSeries)
            .filter(InterestRateSeries.rate_type == rate_type)
            .order_by(InterestRateSeries.year_month)
            .all()
        )
        return RateSeriesOut(
            rate_type=rate_type,
            points=[RatePoint(year_month=r.year_month, rate=r.rate) for r in rows],
        )


@router.post("/teacher/rates/refresh")
def refresh_rates(info: TokenInfo = Depends(require_teacher)) -> dict:
    """Hämta senaste policy-räntor från Riksbanken och fyll InterestRateSeries.
    Oförändrat i fall API:et inte svarar — statisk data ligger kvar."""
    from ..school.rates import refresh_from_riksbank
    _require_school_mode()
    with master_session() as s:
        return refresh_from_riksbank(s)


class MortgageChoiceIn(BaseModel):
    assignment_id: int
    chosen: str  # "rorlig" | "3ar" | "5ar"


class MortgageOutcomeOut(BaseModel):
    chosen: str
    decision_month: str
    horizon_months: int
    principal: float
    locked_rate: Optional[float]
    # Faktisk kostnad enligt räntekurvan under horisonten
    cost_rorlig: float
    cost_3ar: float
    cost_5ar: float
    cost_chosen: float
    best_choice: str
    diff_vs_best: float
    horizon_completed: bool


@router.post("/student/mortgage/choose")
def submit_mortgage_choice(
    payload: MortgageChoiceIn,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Elev gör sitt val i ett mortgage_decision-uppdrag. Valet lockas."""
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    if payload.chosen not in ("rorlig", "3ar", "5ar"):
        raise HTTPException(400, "chosen must be rorlig/3ar/5ar")
    with master_session() as s:
        a = s.query(Assignment).filter(
            Assignment.id == payload.assignment_id,
            Assignment.student_id == info.student_id,
            Assignment.kind == "mortgage_decision",
        ).first()
        if not a:
            raise HTTPException(404, "Uppdrag inte hittat")
        existing = s.query(MortgageDecision).filter(
            MortgageDecision.assignment_id == a.id
        ).first()
        if existing:
            raise HTTPException(400, "Du har redan gjort ditt val")
        params = a.params or {}
        dm = params.get("decision_month") or a.target_year_month
        if not dm:
            raise HTTPException(400, "Uppdraget saknar decision_month")
        horizon = int(params.get("horizon_months", 36))
        principal = float(params.get("principal", 2_000_000))
        locked: float | None = None
        if payload.chosen in ("3ar", "5ar"):
            from ..school.rates import get_rate_for_month
            locked = get_rate_for_month(
                s, dm,
                "bolan_3ar" if payload.chosen == "3ar" else "bolan_5ar",
            )
        s.add(MortgageDecision(
            assignment_id=a.id,
            student_id=info.student_id,
            chosen=payload.chosen,
            decision_month=dm,
            horizon_months=horizon,
            principal=principal,
            locked_rate=locked,
        ))
    return {"ok": True}


@router.get("/student/mortgage/{assignment_id}/outcome",
            response_model=MortgageOutcomeOut)
def mortgage_outcome(
    assignment_id: int,
    info: TokenInfo = Depends(require_token),
) -> MortgageOutcomeOut:
    """Facit: jämför kostnaden av elevens val vs de andra alternativen
    över horisonten. Rörlig använder månadens aktuella ränta; bunden
    använder den låsta räntan. Räntekostnad i kronor = principal * rate / 12
    per månad (förenklat — ignorerar amortering)."""
    _require_school_mode()
    from ..school.rates import get_rate_for_month
    from datetime import date as _date
    with master_session() as s:
        a = s.query(Assignment).filter(
            Assignment.id == assignment_id
        ).first()
        if not a:
            raise HTTPException(404, "Uppdrag inte hittat")
        mc = s.query(MortgageDecision).filter(
            MortgageDecision.assignment_id == assignment_id
        ).first()
        if not mc:
            raise HTTPException(404, "Inget val gjort ännu")
        # Iterera månader i horisonten
        y, m = map(int, mc.decision_month.split("-"))
        months: list[str] = []
        for i in range(mc.horizon_months):
            mm = m + i
            yy = y + mm // 12
            mm = mm % 12 + 1
            months.append(f"{yy:04d}-{mm:02d}")
        today = _date.today().strftime("%Y-%m")
        # Vilka månader har räntedata (historia + nutid)?
        available = [m for m in months if m <= today]
        horizon_completed = len(available) == mc.horizon_months

        def cost_for(rate_type_for_var: str, fixed_rate: float | None) -> float:
            total = 0.0
            for mo in available:
                if fixed_rate is not None:
                    r = fixed_rate
                else:
                    r = get_rate_for_month(s, mo, rate_type_for_var) or 0.0
                total += mc.principal * r / 12
            return total

        rate_3ar = mc.locked_rate if mc.chosen == "3ar" else (
            get_rate_for_month(s, mc.decision_month, "bolan_3ar") or 0.0
        )
        rate_5ar = mc.locked_rate if mc.chosen == "5ar" else (
            get_rate_for_month(s, mc.decision_month, "bolan_5ar") or 0.0
        )

        cost_r = cost_for("bolan_rorlig", None)
        cost_3 = cost_for("bolan_rorlig", rate_3ar)
        cost_5 = cost_for("bolan_rorlig", rate_5ar)

        # Vilken var billigast?
        options = {"rorlig": cost_r, "3ar": cost_3, "5ar": cost_5}
        best = min(options, key=options.get)
        chosen_cost = options[mc.chosen]
        diff = chosen_cost - options[best]

        return MortgageOutcomeOut(
            chosen=mc.chosen,
            decision_month=mc.decision_month,
            horizon_months=mc.horizon_months,
            principal=mc.principal,
            locked_rate=mc.locked_rate,
            cost_rorlig=round(cost_r),
            cost_3ar=round(cost_3),
            cost_5ar=round(cost_5),
            cost_chosen=round(chosen_cost),
            best_choice=best,
            diff_vs_best=round(diff),
            horizon_completed=horizon_completed,
        )


# ---------- Demo-konto ----------

class DemoLoginOut(BaseModel):
    token: str
    role: str
    display_name: str
    next_reset_at: Optional[datetime] = None


@router.post("/demo/teacher", response_model=DemoLoginOut)
def demo_teacher_login() -> DemoLoginOut:
    """Logga in som demo-lärare direkt utan lösen. Miljön är publik och
    resetas var 10 min."""
    _require_school_mode()
    from ..school.demo_seed import DEMO_TEACHER_EMAIL
    with master_session() as s:
        t = s.query(Teacher).filter(
            Teacher.email == DEMO_TEACHER_EMAIL,
            Teacher.is_demo.is_(True),
        ).first()
        if not t:
            raise HTTPException(503, "Demo ej initialiserad än — försök igen")
        token = random_token()
        register_token(token, role="teacher", teacher_id=t.id)
        return DemoLoginOut(
            token=token, role="teacher",
            display_name=t.name,
            next_reset_at=_next_demo_reset(),
        )


@router.post("/demo/student", response_model=DemoLoginOut)
def demo_student_login(code: Optional[str] = None) -> DemoLoginOut:
    """Logga in som en förvald demo-elev. Om 'code' anges, använd den;
    annars första demo-eleven (DEMO01)."""
    _require_school_mode()
    target_code = (code or "DEMO01").upper()
    with master_session() as s:
        stu = s.query(Student).filter(
            Student.login_code == target_code
        ).first()
        if not stu:
            raise HTTPException(503, "Demo ej initialiserad än — försök igen")
        # Verifiera att eleven tillhör en demo-lärare
        t = s.query(Teacher).filter(Teacher.id == stu.teacher_id).first()
        if not t or not t.is_demo:
            raise HTTPException(403, "Koden tillhör inte demomiljön")
        stu.last_login_at = datetime.utcnow()
        token = random_token()
        register_token(token, role="student", student_id=stu.id)
        return DemoLoginOut(
            token=token, role="student",
            display_name=stu.display_name,
            next_reset_at=_next_demo_reset(),
        )


@router.get("/demo/status")
def demo_status() -> dict:
    """Publikt info-endpoint: listar demo-konton + nästa reset."""
    if not school_enabled():
        return {"demo_available": False}
    with master_session() as s:
        t = s.query(Teacher).filter(Teacher.is_demo.is_(True)).first()
        if not t:
            return {"demo_available": False, "reason": "ej seedat än"}
        students = s.query(Student).filter(Student.teacher_id == t.id).all()
        return {
            "demo_available": True,
            "teacher_email": t.email,
            "student_codes": [
                {"name": st.display_name, "code": st.login_code, "class": st.class_label}
                for st in students
            ],
            "next_reset_at": _next_demo_reset().isoformat() if _next_demo_reset() else None,
        }


@router.post("/admin/demo/rebuild")
def admin_rebuild_demo(info: TokenInfo = Depends(require_teacher)) -> dict:
    """Super-admin: trigga om demo-byggandet manuellt utan att vänta
    på schemaläggaren (10 min). Använd om demo-data är trasigt eller
    försvunnit efter en deploy."""
    _require_school_mode()
    with master_session() as s:
        t = s.query(Teacher).filter(Teacher.id == info.teacher_id).first()
        if not t or not t.is_super_admin:
            raise HTTPException(403, "Super-admin krävs")
    from ..school.demo_seed import build_demo
    return build_demo()


@router.get("/demo/is-demo")
def am_i_in_demo(info: TokenInfo = Depends(require_token)) -> dict:
    """Används av frontend för att visa demobanner ovanför allt UI."""
    from ..school.demo_seed import is_demo_token
    return {
        "is_demo": is_demo_token(info),
        "next_reset_at": _next_demo_reset().isoformat() if _next_demo_reset() else None,
    }


def _next_demo_reset() -> Optional[datetime]:
    """Returnerar när nästa reset förväntas köra, om vi har schemat
    startat. Om ingen schemaläggare: None."""
    from ..main import next_demo_reset_at
    return next_demo_reset_at


@router.get("/teacher/batches/months",
            response_model=list[str])
def list_all_batch_months(
    info: TokenInfo = Depends(require_teacher),
) -> list[str]:
    """Lista alla unika year_month värden där minst en batch finns, för
    lärarens elever. Används för månadsväljaren i samlad vy."""
    _require_school_mode()
    with master_session() as s:
        rows = (
            s.query(ScenarioBatch.year_month)
            .join(Student, ScenarioBatch.student_id == Student.id)
            .filter(Student.teacher_id == info.teacher_id)
            .distinct()
            .order_by(ScenarioBatch.year_month.desc())
            .all()
        )
        return [r[0] for r in rows]


@router.get(
    "/student/batches",
    response_model=list[ScenarioBatchOut],
)
def student_list_batches(
    info: TokenInfo = Depends(require_token),
) -> list[ScenarioBatchOut]:
    """Lista elevens egna batchar. Tillåter lärar-impersonation
    (x-as-student-headern) så lärare kan kolla elevens vy utan att
    smällas ut med 403."""
    _require_school_mode()
    # Använd actor_student_id från middleware — fungerar för både
    # elev-token och lärare med x-as-student.
    from ..api.modules import _resolve_student_actor
    student_id = _resolve_student_actor(info)
    with master_session() as s:
        batches = (
            s.query(ScenarioBatch)
            .filter(ScenarioBatch.student_id == student_id)
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
        from ..school.activity import log_activity as _act
        _act(
            "batch.imported",
            f"Importerade {artifact.kind} ({batch.year_month})",
            payload={
                "batch_id": batch.id, "artifact_id": artifact.id,
                "kind": artifact.kind, "year_month": batch.year_month,
            },
            student_id=student.id,
        )
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
        if results:
            from ..school.activity import log_activity as _act
            _act(
                "batch.imported",
                f"Importerade alla {len(results)} dokument för "
                f"{batch.year_month}",
                payload={
                    "batch_id": batch.id, "year_month": batch.year_month,
                    "count": len(results),
                },
                student_id=student.id,
            )
    return {"results": results}


# ---------- Teacher: datagenerering (GAMMAL endpoint — borttagen) ----------
# /teacher/generate tidigare direkt-genererade transaktioner i scope-DB:n.
# Den är borttagen eftersom nya batch-flödet (/teacher/batches) ersätter
# den fullt ut. Om den kördes parallellt med batch-importen skulle eleven
# få dubbelt data. Returnera 410 Gone med instruktion.


@router.post("/teacher/generate")
def generate_month_deprecated(
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    raise HTTPException(
        status.HTTP_410_GONE,
        "Denna endpoint är ersatt av /teacher/batches som skapar PDF:er "
        "som eleverna importerar själva. Uppdatera klienten.",
    )


# ---------- Student login ----------

@router.post("/student/login", response_model=StudentAuthOut)
def student_login(
    payload: StudentLoginIn, request: Request,
) -> StudentAuthOut:
    _require_school_mode()
    # Elev-loginkoden är kort (6 tecken) → sårbar för brute force.
    # Rate-limit + Turnstile skyddar utan att krångla för eleven.
    check_rate_limit(request, "student-login", RULES_LOGIN)
    verify_turnstile(request, required=False)
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
            total = s.query(Teacher).count()
            real = s.query(Teacher).filter(Teacher.is_demo.is_(False)).count()
            # teacher_count exponerar bara riktiga (icke-demo) lärare för
            # frontend — demo-kontot är en intern teknisk detalj.
            info["teacher_count"] = real
            info["demo_teacher_count"] = total - real
            # bootstrap_ready = ingen RIKTIG lärare finns ännu; demo-
            # läraren (återskapas vid varje start) blockerar inte.
            info["bootstrap_ready"] = real == 0
            info["bootstrap_requires_secret"] = bool(
                os.environ.get("HEMBUDGET_BOOTSTRAP_SECRET")
            )
    # Publik Turnstile-site-key (tom sträng = bot-skyddet är av).
    # Frontend läser detta vid uppstart för att rendera challenge-
    # widgeten på login-sidorna.
    info["turnstile_site_key"] = turnstile_site_key()
    return info


@router.get("/public/stats")
def public_stats() -> dict:
    """Aggregerade, icke-PII-siffror för landningssidan. Fallback till
    0 om school-läget inte är aktiverat så anropet alltid är säkert."""
    if not school_enabled():
        return {
            "teachers": 0, "students": 0,
            "modules_completed": 0, "reflections_written": 0,
        }
    with master_session() as s:
        from ..school.models import (
            StudentModule as _SM,
            StudentStepProgress as _P,
            ModuleStep as _Step,
        )
        teachers = s.query(Teacher).filter(
            Teacher.is_demo.is_(False),
            Teacher.active.is_(True),
        ).count()
        students = s.query(Student).filter(Student.active.is_(True)).count()
        modules_completed = s.query(_SM).filter(
            _SM.completed_at.isnot(None)
        ).count()
        reflections_written = (
            s.query(_P).join(_Step, _P.step_id == _Step.id).filter(
                _Step.kind == "reflect",
                _P.completed_at.isnot(None),
            ).count()
        )
    return {
        "teachers": teachers,
        "students": students,
        "modules_completed": modules_completed,
        "reflections_written": reflections_written,
    }


@router.get("/teacher/me", response_model=TeacherAuthOut)
def teacher_me(info: TokenInfo = Depends(require_teacher)) -> TeacherAuthOut:
    _require_school_mode()
    with master_session() as s:
        t = s.query(Teacher).filter(Teacher.id == info.teacher_id).first()
        if not t:
            raise HTTPException(404, "Teacher not found")
        return TeacherAuthOut(
            token=info.token, teacher_id=t.id, name=t.name, email=t.email,
            is_family_account=t.is_family_account,
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
