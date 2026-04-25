"""Regressionstest för impersonations-buggen där lärare som tittade
på en elevs modul slängdes ut till landningssidan.

Bug-orsak: /student/modules/* endpoints krävde info.role == "student"
och 403:ade för en lärare som impersonerade. Frontend tolkade 403 som
token-utgång och rensade auth → Landing-redirect.

Fix: backend tillåter nu lärare att läsa /student/* GET-endpoints om
de har `x-as-student` mot en av sina egna elever. Frontend rensar
inte längre token vid 403.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import (
    Module, ModuleStep, Student, StudentModule, Teacher,
)
from hembudget.security.crypto import hash_password, random_token


@pytest.fixture
def fx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
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
        teacher = Teacher(
            email="lar@x.se", name="Lärare",
            password_hash=hash_password("Abcdef12!"),
            email_verified_at=datetime.utcnow(),
        )
        s.add(teacher); s.flush()
        student = Student(
            teacher_id=teacher.id, display_name="Elev",
            login_code="LOGINCODE",
        )
        s.add(student); s.flush()
        # Skapa en modul + steg + tilldela till eleven
        m = Module(teacher_id=None, title="Test-modul", is_template=True)
        s.add(m); s.flush()
        step = ModuleStep(
            module_id=m.id, sort_order=0, kind="read",
            title="Steg 1", content="Läs detta",
        )
        s.add(step); s.flush()
        s.add(StudentModule(
            student_id=student.id, module_id=m.id, sort_order=0,
        ))
        tid = teacher.id
        sid = student.id
        mid = m.id
        step_id = step.id

    teacher_tok = random_token()
    register_token(teacher_tok, role="teacher", teacher_id=tid)
    student_tok = random_token()
    register_token(student_tok, role="student", student_id=sid)

    return TestClient(app), teacher_tok, student_tok, sid, mid, step_id


def test_student_can_list_their_modules(fx) -> None:
    client, _, student_tok, _sid, mid, _step_id = fx
    r = client.get(
        "/student/modules",
        headers={"Authorization": f"Bearer {student_tok}"},
    )
    assert r.status_code == 200
    assert any(m["module_id"] == mid for m in r.json())


def test_teacher_with_x_as_student_can_list_modules(fx) -> None:
    """Den faktiska bug-fixen: lärare med x-as-student-impersonation
    måste få 200 (inte 403) på /student/modules."""
    client, teacher_tok, _, sid, mid, _step_id = fx
    r = client.get(
        "/student/modules",
        headers={
            "Authorization": f"Bearer {teacher_tok}",
            "X-As-Student": str(sid),
        },
    )
    assert r.status_code == 200, r.text
    assert any(m["module_id"] == mid for m in r.json())


def test_teacher_with_x_as_student_can_open_module_detail(fx) -> None:
    """Den specifika sidan användaren rapporterade — /modules/1 öppnade
    landingsidan eftersom backend 403:ade för impersonerande lärare."""
    client, teacher_tok, _, sid, mid, _step_id = fx
    r = client.get(
        f"/student/modules/{mid}",
        headers={
            "Authorization": f"Bearer {teacher_tok}",
            "X-As-Student": str(sid),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == mid
    assert body["title"] == "Test-modul"


def test_teacher_with_x_as_student_can_read_step_progress(fx) -> None:
    client, teacher_tok, _, sid, _mid, step_id = fx
    r = client.get(
        f"/student/steps/{step_id}/progress",
        headers={
            "Authorization": f"Bearer {teacher_tok}",
            "X-As-Student": str(sid),
        },
    )
    assert r.status_code == 200, r.text


def test_teacher_without_x_as_student_still_403(fx) -> None:
    """Lärare UTAN impersonation ska fortfarande inte komma åt
    /student/modules — det skulle inte vara meningsfullt eftersom
    läraren inte har egna progress-rader."""
    client, teacher_tok, _, _sid, _mid, _step_id = fx
    r = client.get(
        "/student/modules",
        headers={"Authorization": f"Bearer {teacher_tok}"},
    )
    assert r.status_code == 403


def test_teacher_cannot_impersonate_other_teachers_student(fx) -> None:
    """Lärare A ska inte komma åt elev hos lärare B — middleware ska
    inte sätta actor_student_id i det fallet."""
    client, _teacher_tok, _stu_tok, sid, _mid, _step_id = fx
    with master_session() as s:
        other_t = Teacher(
            email="other@x.se", name="Annan",
            password_hash=hash_password("Abcdef12!"),
            email_verified_at=datetime.utcnow(),
        )
        s.add(other_t); s.flush()
        otid = other_t.id
    other_tok = random_token()
    register_token(other_tok, role="teacher", teacher_id=otid)
    r = client.get(
        "/student/modules",
        headers={
            "Authorization": f"Bearer {other_tok}",
            "X-As-Student": str(sid),
        },
    )
    # Middleware sätter inte actor_student_id eftersom eleven inte
    # tillhör läraren → endpointen ser "ingen student-kontext" och
    # 403:ar.
    assert r.status_code == 403


def test_step_complete_still_locked_to_student_role(fx) -> None:
    """Mutationer (POST step-complete) ska FORTFARANDE kräva elev-roll
    så lärare som klickar runt inte triggar achievements eller
    förorenar progress för eleven."""
    client, teacher_tok, _, sid, _mid, step_id = fx
    r = client.post(
        f"/student/steps/{step_id}/complete",
        json={},
        headers={
            "Authorization": f"Bearer {teacher_tok}",
            "X-As-Student": str(sid),
        },
    )
    assert r.status_code == 403
