"""Demo-miljö: bygger upp en fullständig lärar-klass med elever,
batcher, uppdrag och meddelanden. Används för publika "prova"-knappen.

Hela datan skapas deterministiskt från kod — ingen extern import.
Kan rebygges när som helst (är idempotent på demo-email).

build_demo() kallas av schemaläggaren var 10 min och vid startup.
"""
from __future__ import annotations

import logging
from datetime import datetime

from .engines import (
    drop_scope_db, get_scope_engine, master_session, scope_context,
    scope_for_student,
)
from .models import (
    Assignment, Family, Message, ScenarioBatch, Student, Teacher,
)
from ..security.crypto import hash_password

log = logging.getLogger(__name__)


DEMO_TEACHER_EMAIL = "demo@ekonomilabbet.org"
DEMO_TEACHER_PASSWORD = "Demo2026!"
DEMO_TEACHER_NAME = "Lärare Demo"


# Elevdefinitioner — alla påhittade men varierade profiler
DEMO_STUDENTS = [
    {"name": "Anna Andersson", "class": "9A", "code": "DEMO01", "family": "Familjen Andersson"},
    {"name": "Bosse Andersson", "class": "9A", "code": "DEMO02", "family": "Familjen Andersson"},
    {"name": "Carla Svensson", "class": "9A", "code": "DEMO03"},
    {"name": "David Nilsson", "class": "9B", "code": "DEMO04"},
    {"name": "Elin Karlsson", "class": "9B", "code": "DEMO05"},
]


def wipe_demo(s) -> dict:
    """Radera ALLA demo-lärare och deras ägda data. Returnerar antal."""
    counts = {"teachers": 0, "students": 0, "families": 0, "scope_dbs": 0}
    demo_teachers = s.query(Teacher).filter(Teacher.is_demo.is_(True)).all()
    for t in demo_teachers:
        # Radera scope-DB:er för alla elever + familjer
        students = s.query(Student).filter(Student.teacher_id == t.id).all()
        seen_scopes: set[str] = set()
        for st in students:
            sk = scope_for_student(st)
            if sk not in seen_scopes:
                try:
                    drop_scope_db(sk)
                    seen_scopes.add(sk)
                    counts["scope_dbs"] += 1
                except Exception:
                    log.exception("Failed to drop scope %s", sk)
        # Ta bort master-DB-raderna (cascade → profile, gen_runs, batches,
        # artifacts, messages, assignments, mortgage_decisions)
        for st in students:
            s.delete(st)
            counts["students"] += 1
        for fam in s.query(Family).filter(Family.teacher_id == t.id).all():
            s.delete(fam)
            counts["families"] += 1
        s.delete(t)
        counts["teachers"] += 1
    s.flush()
    return counts


def build_demo() -> dict:
    """Säkerställ att en färsk demo-lärare + elever + batchar finns.
    Idempotent: rensar befintlig demo-data först, bygger sedan upp
    allt från grunden."""
    stats = {"built_at": datetime.utcnow().isoformat()}
    with master_session() as s:
        cleaned = wipe_demo(s)
        stats["cleaned"] = cleaned

        # Skapa demo-lärare
        teacher = Teacher(
            email=DEMO_TEACHER_EMAIL,
            name=DEMO_TEACHER_NAME,
            password_hash=hash_password(DEMO_TEACHER_PASSWORD),
            is_demo=True,
        )
        s.add(teacher)
        s.flush()

        # Familjer (skapa alla unika först)
        family_names = {
            spec["family"] for spec in DEMO_STUDENTS if spec.get("family")
        }
        family_by_name: dict[str, Family] = {}
        for name in family_names:
            fam = Family(teacher_id=teacher.id, name=name)
            s.add(fam)
            s.flush()
            family_by_name[name] = fam

        # Elever med deterministiska login-koder (DEMO01..DEMO05)
        students: list[Student] = []
        for i, spec in enumerate(DEMO_STUDENTS):
            stu = Student(
                teacher_id=teacher.id,
                family_id=family_by_name[spec["family"]].id
                    if spec.get("family") else None,
                display_name=spec["name"],
                class_label=spec["class"],
                login_code=spec["code"],
                onboarding_completed=True,
            )
            s.add(stu)
            s.flush()
            # Skapa profil (samma logik som create_student)
            from .profile_fixtures import generate_profile
            from .tax import compute_net_salary
            from .models import StudentProfile
            gen = generate_profile(stu.id, stu.display_name)
            tax = compute_net_salary(gen.gross_salary_monthly)
            s.add(StudentProfile(
                student_id=stu.id,
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
                children_ages=gen.children_ages,
                partner_age=gen.partner_age,
                partner_profession=gen.partner_profession,
                partner_gross_salary=gen.partner_gross_salary,
                backstory=gen.backstory,
            ))
            # Skapa scope-DB så kategorier seedas
            get_scope_engine(scope_for_student(stu))
            students.append(stu)
        s.flush()
        stats["students_created"] = len(students)

        # COMMIT av students + profiler så de är persistenta innan
        # batch-byggandet börjar. Tidigare bug: ett fel i batch-build
        # (t.ex. integer-overflow) satte HELA sessionen i rollback,
        # vilket tog ner profile-add:s också → "Student saknar profil"
        # för efterföljande elever.
        s.commit()

        # Generera 3 månaders batchar för varje elev + importera automatiskt.
        # Varje (elev, månad) körs i en SAVEPOINT så ett fel inte tar
        # ner resten av batchen.
        from ..teacher.batch import create_batch_for_student, import_artifact
        months = ["2026-02", "2026-03", "2026-04"]
        batches_created = 0
        artifacts_imported = 0
        for stu in students:
            for ym in months:
                try:
                    with s.begin_nested():
                        batch = create_batch_for_student(s, stu, ym, overwrite=True)
                        batches_created += 1
                        # Importera alla så demot känns "ifyllt"
                        for art in batch.artifacts:
                            import_artifact(s, art, stu)
                            artifacts_imported += 1
                except Exception:
                    log.exception(
                        "Failed building batch for %s %s", stu.display_name, ym,
                    )
        stats["batches"] = batches_created
        stats["artifacts"] = artifacts_imported

        # Några uppdrag i olika status
        for stu in students[:3]:  # bara för de tre första
            s.add(Assignment(
                teacher_id=teacher.id, student_id=stu.id,
                title="Sätt din första budget",
                description="Gå igenom Konsumentverkets siffror och sätt en rimlig budget.",
                kind="set_budget",
            ))
            s.add(Assignment(
                teacher_id=teacher.id, student_id=stu.id,
                title="Importera aprildokumenten",
                description="Ladda ner och importera alla PDF:er för april.",
                kind="import_batch",
                target_year_month="2026-04",
            ))
        s.add(Assignment(
            teacher_id=teacher.id, student_id=students[0].id,
            title="Spara 2 000 kr i april",
            description="Klarar du att sätta undan minst 2 000 kr?",
            kind="save_amount",
            target_year_month="2026-04",
            params={"amount": 2000},
        ))
        # Reflektionsuppdrag med manuell klarmarkering
        s.add(Assignment(
            teacher_id=teacher.id, student_id=students[1].id,
            title="Reflektera över din månad",
            description="Skriv några meningar om vad du lärt dig.",
            kind="free_text",
            manually_completed_at=datetime.utcnow(),
        ))
        s.flush()

        # Några meddelanden i tråden
        s.add(Message(
            student_id=students[0].id, teacher_id=teacher.id,
            sender_role="student",
            body="Hej, jag förstår inte riktigt hur lön blir till netto. Kan du förklara?",
        ))
        s.add(Message(
            student_id=students[0].id, teacher_id=teacher.id,
            sender_role="teacher",
            body="Bra fråga! Skatten dras av direkt av arbetsgivaren. Titta på onboarding-steg 2 för en genomgång.",
        ))
        s.add(Message(
            student_id=students[0].id, teacher_id=teacher.id,
            sender_role="student",
            body="Tack, nu förstår jag!",
        ))

    stats["demo_teacher_email"] = DEMO_TEACHER_EMAIL
    stats["demo_teacher_password"] = DEMO_TEACHER_PASSWORD
    stats["demo_student_codes"] = [sp["code"] for sp in DEMO_STUDENTS]
    return stats


def is_demo_token(info) -> bool:
    """Check om en TokenInfo representerar en demo-session.
    Används för att visa demobanner i UI."""
    if not info:
        return False
    try:
        with master_session() as s:
            if info.role == "teacher" and info.teacher_id:
                t = s.query(Teacher).filter(Teacher.id == info.teacher_id).first()
                return bool(t and t.is_demo)
            if info.role == "student" and info.student_id:
                stu = s.query(Student).filter(Student.id == info.student_id).first()
                if not stu:
                    return False
                t = s.query(Teacher).filter(Teacher.id == stu.teacher_id).first()
                return bool(t and t.is_demo)
    except Exception:
        pass
    return False
