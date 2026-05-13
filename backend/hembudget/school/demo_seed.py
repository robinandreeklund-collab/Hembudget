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


# Demo-personerna är de tre karaktärer som visas på landingsidan
# (demo-landing/index.html). Tema per persona:
#   Linda    · 22 år · arbetslivet (lönesamtal, pension, första jobb)
#   Evelina  · 27 år · investeringsstrategi (ISK, risk, marknadsanalys)
#   Peter    · 38 år · vardagsekonomi (familj, fakturor, buffert, barn)
#
# `profile`-dicten överrider `generate_profile()` så demoupplevelsen
# blir EXAKT samma som det landingsidan lovar. Slumpmässig genererad
# data räckte inte — användaren förväntar sig att klicka "Linda" på
# /demo och möta exakt den karaktär hen läst om på framsidan.
DEMO_STUDENTS = [
    {
        "name": "Linda Bergström",
        "class": "Vol. 01",
        "code": "LINDA",
        "profile": {
            "profession": "IT-konsult (junior)",
            "employer": "Visma Sverige AB",
            "gross_salary_monthly": 38500,
            "personality": "balanserad",
            "age": 22,
            "city": "Stockholm",
            "family_status": "ensam",
            "housing_type": "hyresratt",
            "housing_monthly": 9800,
            "has_mortgage": False,
            "has_car_loan": False,
            "has_student_loan": True,
            "has_credit_card": True,
            "children_ages": None,
            "partner_age": None,
            "partner_profession": None,
            "partner_gross_salary": None,
            "character_first_name": "Linda",
            "character_last_name": "Bergström",
            "backstory": (
                "Nyutbildad IT-konsult i sitt första riktiga jobb. "
                "Pluggat fyra år, har CSN-skuld kvar att betala. Lär "
                "sig hantera lönesamtal, pension och oväntade kostnader "
                "som tandläkarakut."
            ),
        },
    },
    {
        "name": "Evelina Lundqvist",
        "class": "Vol. 01",
        "code": "EVELINA",
        "profile": {
            "profession": "Ekonom",
            "employer": "Handelsbanken Malmö",
            "gross_salary_monthly": 42500,
            "personality": "sparsam",
            "age": 27,
            "city": "Malmö",
            "family_status": "ensam",
            "housing_type": "bostadsratt",
            "housing_monthly": 7800,
            "has_mortgage": True,
            "has_car_loan": False,
            "has_student_loan": True,
            "has_credit_card": True,
            "children_ages": None,
            "partner_age": None,
            "partner_profession": None,
            "partner_gross_salary": None,
            "character_first_name": "Evelina",
            "character_last_name": "Lundqvist",
            "backstory": (
                "Ekonom på Handelsbanken som följer börsen aktivt. "
                "Har 12,4 % avkastning på sin ISK senaste året. Lär "
                "sig hantera marknadsfluktuationer och långsiktig "
                "portföljstrategi."
            ),
        },
    },
    {
        "name": "Peter Holmberg",
        "class": "Vol. 01",
        "code": "PETER",
        "family": "Familjen Holmberg",
        "profile": {
            "profession": "Projektledare bygg",
            "employer": "Skanska Göteborg",
            "gross_salary_monthly": 38000,
            "personality": "balanserad",
            "age": 38,
            "city": "Göteborg",
            "family_status": "familj_med_barn",
            "housing_type": "hyresratt",
            "housing_monthly": 8200,
            "has_mortgage": False,
            "has_car_loan": True,
            "has_student_loan": False,
            "has_credit_card": True,
            "children_ages": [4, 7],
            "partner_age": 36,
            "partner_profession": "Lärare F-3",
            "partner_gross_salary": 35000,
            "character_first_name": "Peter",
            "character_last_name": "Holmberg",
            "backstory": (
                "Småbarnsförälder i Göteborg med 23 fakturor i "
                "månaden — hyra 8 200 kr, försäkringar, dagis, "
                "abonnemang. Sambo med Linnea (lärare F-3). Två "
                "barn (4 och 7 år). Lär sig bygga buffert och "
                "planera framåt med den knappa ekonomin."
            ),
        },
    },
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
            # Skapa profil. Demo-personerna har hardcoded profile-data
            # i DEMO_STUDENTS-spec så Linda/Evelina/Peter alltid blir
            # exakt de karaktärer landingsidan beskriver. Ingen slump.
            from .tax import compute_net_salary
            from .models import StudentProfile
            from .engines import master_has_column
            override = spec.get("profile") or {}
            gross = override.get("gross_salary_monthly", 35000)
            tax = compute_net_salary(gross)
            profile_kwargs = dict(
                student_id=stu.id,
                profession=override.get("profession", "—"),
                employer=override.get("employer", "—"),
                gross_salary_monthly=gross,
                net_salary_monthly=tax.net_monthly,
                tax_rate_effective=tax.effective_rate,
                personality=override.get("personality", "balanserad"),
                age=override.get("age", 30),
                city=override.get("city", "Stockholm"),
                family_status=override.get("family_status", "ensam"),
                housing_type=override.get("housing_type", "hyresratt"),
                housing_monthly=override.get("housing_monthly", 8000),
                has_mortgage=override.get("has_mortgage", False),
                has_car_loan=override.get("has_car_loan", False),
                has_student_loan=override.get("has_student_loan", False),
                has_credit_card=override.get("has_credit_card", True),
                children_ages=override.get("children_ages"),
                partner_age=override.get("partner_age"),
                backstory=override.get("backstory"),
            )
            if master_has_column("student_profiles", "partner_profession"):
                profile_kwargs["partner_profession"] = (
                    override.get("partner_profession")
                )
            if master_has_column("student_profiles", "partner_gross_salary"):
                profile_kwargs["partner_gross_salary"] = (
                    override.get("partner_gross_salary")
                )
            if master_has_column("student_profiles", "character_first_name"):
                profile_kwargs["character_first_name"] = (
                    override.get("character_first_name")
                )
            if master_has_column("student_profiles", "character_last_name"):
                profile_kwargs["character_last_name"] = (
                    override.get("character_last_name")
                )
            s.add(StudentProfile(**profile_kwargs))
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
                    # KRITISKT: rollback hela sessionen så efterföljande
                    # elever inte ärver en invalid transaction. Tidigare:
                    # första batch failar (t.ex. Cloud SQL restart) →
                    # session blev "PendingRollbackError" → ALLA följande
                    # elever kraschar med samma fel.
                    try:
                        s.rollback()
                    except Exception:
                        log.exception("rollback failed too — aborting demo build")
                        return stats
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
