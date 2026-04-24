"""Tester för Fas 3.1: quiz-override + assignment-feedback.

Fokus:
- POST /teacher/progress/:id/quiz-override sätter data.teacher_override
- mastery-formeln respekterar teacher_override före first_correct
- POST /teacher/assignments/:id/feedback sparar body + request_retry
  nollar manually_completed_at
- Student- och teacher-endpoints inkluderar teacher_feedback i svaret
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import (
    Assignment, Competency, Module, ModuleStep, ModuleStepCompetency,
    Student, StudentModule, StudentProfile, StudentStepProgress, Teacher,
)
from hembudget.security.crypto import hash_password, random_token
from hembudget.api.deps import register_token


@pytest.fixture
def fx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    monkeypatch.delenv("TURNSTILE_SECRET", raising=False)
    from hembudget.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from hembudget.security import rate_limit as rl_mod
    rl_mod.reset_all_for_testing()
    from hembudget.school import engines as eng_mod
    if eng_mod._master_engine is not None:
        eng_mod._master_engine.dispose()
    eng_mod._master_engine = None
    eng_mod._master_session = None
    for e in list(eng_mod._scope_engines.values()):
        e.dispose()
    eng_mod._scope_engines.clear()
    eng_mod._scope_sessions.clear()
    from hembudget.school import demo_seed as demo_seed_mod
    monkeypatch.setattr(demo_seed_mod, "build_demo", lambda: {"skipped": True})

    import importlib
    import hembudget.main as main_mod
    importlib.reload(main_mod)
    app = main_mod.build_app()
    init_master_engine()

    with master_session() as s:
        t = Teacher(
            email="t@x.se", name="T",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(t); s.flush()
        tid = t.id
        stu = Student(
            teacher_id=tid, display_name="E", login_code="LOGINCODE",
        )
        s.add(stu); s.flush()
        sid = stu.id
        s.add(StudentProfile(
            student_id=sid, profession="p", employer="e",
            gross_salary_monthly=25000, net_salary_monthly=20000,
            tax_rate_effective=0.2, age=18, city="Sthlm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=5000, personality="blandad",
        ))

    tch_tok = random_token()
    stu_tok = random_token()
    register_token(tch_tok, role="teacher", teacher_id=tid)
    register_token(stu_tok, role="student", student_id=sid)
    return TestClient(app), tch_tok, stu_tok, tid, sid


# ---------- Quiz-override ----------

def test_quiz_override_sets_data(fx) -> None:
    client, tch, _stu, tid, sid = fx
    with master_session() as s:
        m = Module(teacher_id=tid, title="M"); s.add(m); s.flush()
        step = ModuleStep(
            module_id=m.id, sort_order=0, kind="quiz", title="Q",
            params={"question": "q", "options": ["a", "b"], "correct_index": 0},
        )
        s.add(step); s.flush()
        prog = StudentStepProgress(
            student_id=sid, step_id=step.id,
            completed_at=datetime.utcnow(),
            data={"answer": 1, "correct": False, "first_correct": False, "attempts": 1},
        )
        s.add(prog); s.flush()
        pid = prog.id

    r = client.post(
        f"/teacher/progress/{pid}/quiz-override",
        json={"correct": True, "note": "Frågan var tvetydig."},
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text

    with master_session() as s:
        prog = s.query(StudentStepProgress).filter(
            StudentStepProgress.id == pid
        ).first()
        to = prog.data["teacher_override"]
        assert to["correct"] is True
        assert to["note"] == "Frågan var tvetydig."


def test_quiz_override_affects_mastery(fx) -> None:
    client, tch, stu, tid, sid = fx
    with master_session() as s:
        c = Competency(
            key="k1", name="K", level="grund", is_system=True,
        )
        s.add(c); s.flush()
        m = Module(teacher_id=tid, title="M"); s.add(m); s.flush()
        s.add(StudentModule(student_id=sid, module_id=m.id))
        step = ModuleStep(
            module_id=m.id, sort_order=0, kind="quiz", title="Q",
            params={"question": "q", "options": ["a"], "correct_index": 0},
        )
        s.add(step); s.flush()
        s.add(ModuleStepCompetency(
            step_id=step.id, competency_id=c.id, weight=1.0,
        ))
        prog = StudentStepProgress(
            student_id=sid, step_id=step.id,
            completed_at=datetime.utcnow(),
            data={"answer": 1, "correct": False, "first_correct": False},
        )
        s.add(prog); s.flush()
        pid = prog.id

    # Innan override: mastery 0
    r = client.get("/student/mastery",
                   headers={"Authorization": f"Bearer {stu}"})
    ours = [r for r in r.json() if r["competency"]["key"] == "k1"][0]
    assert ours["mastery"] == 0.0

    # Override → mastery 1.0
    client.post(
        f"/teacher/progress/{pid}/quiz-override",
        json={"correct": True, "note": ""},
        headers={"Authorization": f"Bearer {tch}"},
    )
    r = client.get("/student/mastery",
                   headers={"Authorization": f"Bearer {stu}"})
    ours = [r for r in r.json() if r["competency"]["key"] == "k1"][0]
    assert ours["mastery"] == 1.0


def test_quiz_override_rejects_non_owner(fx) -> None:
    client, _tch, _stu, tid, sid = fx
    # Annan lärare
    other_tok = random_token()
    with master_session() as s:
        other = Teacher(
            email="o@x.se", name="O",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(other); s.flush()
        other_id = other.id
        m = Module(teacher_id=tid, title="M"); s.add(m); s.flush()
        step = ModuleStep(
            module_id=m.id, sort_order=0, kind="quiz", title="Q",
        )
        s.add(step); s.flush()
        prog = StudentStepProgress(
            student_id=sid, step_id=step.id,
            completed_at=datetime.utcnow(),
            data={"answer": 0, "correct": False},
        )
        s.add(prog); s.flush()
        pid = prog.id
    register_token(other_tok, role="teacher", teacher_id=other_id)

    r = client.post(
        f"/teacher/progress/{pid}/quiz-override",
        json={"correct": True},
        headers={"Authorization": f"Bearer {other_tok}"},
    )
    assert r.status_code == 403


def test_quiz_override_rejects_non_quiz_step(fx) -> None:
    client, tch, _stu, tid, sid = fx
    with master_session() as s:
        m = Module(teacher_id=tid, title="M"); s.add(m); s.flush()
        step = ModuleStep(
            module_id=m.id, sort_order=0, kind="read", title="R",
        )
        s.add(step); s.flush()
        prog = StudentStepProgress(
            student_id=sid, step_id=step.id,
            completed_at=datetime.utcnow(),
        )
        s.add(prog); s.flush()
        pid = prog.id
    r = client.post(
        f"/teacher/progress/{pid}/quiz-override",
        json={"correct": True},
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 400


# ---------- Assignment-feedback ----------

def test_assignment_feedback_saved_and_visible_to_student(fx) -> None:
    client, tch, stu, tid, sid = fx
    with master_session() as s:
        a = Assignment(
            teacher_id=tid, student_id=sid, title="Läs lön",
            description="Granska lönespec", kind="free_text",
        )
        s.add(a); s.flush()
        aid = a.id

    # Lärare skickar feedback
    r = client.post(
        f"/teacher/assignments/{aid}/feedback",
        json={"body": "Bra jobbat, men titta på skatten också."},
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text

    # Elev ser texten i sin lista
    r = client.get(
        "/student/assignments",
        headers={"Authorization": f"Bearer {stu}"},
    )
    items = r.json()
    mine = next(a for a in items if a["id"] == aid)
    assert mine["teacher_feedback"] == "Bra jobbat, men titta på skatten också."
    assert mine["teacher_feedback_at"] is not None


def test_assignment_feedback_request_retry_clears_completion(fx) -> None:
    client, tch, _stu, tid, sid = fx
    with master_session() as s:
        a = Assignment(
            teacher_id=tid, student_id=sid, title="X",
            description="y", kind="free_text",
            manually_completed_at=datetime.utcnow(),
        )
        s.add(a); s.flush()
        aid = a.id

    r = client.post(
        f"/teacher/assignments/{aid}/feedback",
        json={"body": "Gör om.", "request_retry": True},
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200

    with master_session() as s:
        a = s.query(Assignment).filter(Assignment.id == aid).first()
        assert a.manually_completed_at is None
        assert a.teacher_feedback == "Gör om."


def test_assignment_feedback_rejects_other_teacher(fx) -> None:
    client, _tch, _stu, tid, sid = fx
    with master_session() as s:
        other = Teacher(
            email="o@x.se", name="O",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(other); s.flush()
        oid = other.id
        a = Assignment(
            teacher_id=tid, student_id=sid, title="X", description="y",
            kind="free_text",
        )
        s.add(a); s.flush()
        aid = a.id
    other_tok = random_token()
    register_token(other_tok, role="teacher", teacher_id=oid)

    r = client.post(
        f"/teacher/assignments/{aid}/feedback",
        json={"body": "hej"},
        headers={"Authorization": f"Bearer {other_tok}"},
    )
    assert r.status_code == 404
