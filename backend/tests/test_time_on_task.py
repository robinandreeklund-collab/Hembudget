"""Tester för Fas 3.3: heartbeat + time-on-task + bulk-portfolio-ZIP."""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import (
    Module, ModuleStep, Student, StudentModule, StudentProfile,
    StudentStepHeartbeat, StudentStepProgress, Teacher,
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
            teacher_id=tid, display_name="Alice", login_code="LOGINCODE1",
        )
        s.add(stu); s.flush()
        sid = stu.id
        s.add(StudentProfile(
            student_id=sid, profession="elev", employer="e",
            gross_salary_monthly=25000, net_salary_monthly=20000,
            tax_rate_effective=0.2, age=18, city="Sthlm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=5000, personality="blandad",
        ))
        m = Module(teacher_id=tid, title="M")
        s.add(m); s.flush()
        mid = m.id
        s.add(StudentModule(student_id=sid, module_id=mid))

    tch_tok = random_token()
    stu_tok = random_token()
    register_token(tch_tok, role="teacher", teacher_id=tid)
    register_token(stu_tok, role="student", student_id=sid)
    return TestClient(app), tch_tok, stu_tok, tid, sid, mid


# ---------- Heartbeat ----------

def test_heartbeat_creates_row(fx) -> None:
    client, _tch, stu, _tid, sid, mid = fx
    with master_session() as s:
        step = ModuleStep(
            module_id=mid, sort_order=0, kind="read", title="s",
        )
        s.add(step); s.flush()
        step_id = step.id

    r = client.post(
        "/student/step-heartbeat",
        json={"step_id": step_id},
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200

    with master_session() as s:
        hb = s.query(StudentStepHeartbeat).filter(
            StudentStepHeartbeat.student_id == sid,
            StudentStepHeartbeat.step_id == step_id,
        ).first()
        assert hb is not None
        assert hb.opened_at == hb.last_heartbeat_at


def test_heartbeat_updates_existing(fx) -> None:
    client, _tch, stu, _tid, sid, mid = fx
    with master_session() as s:
        step = ModuleStep(
            module_id=mid, sort_order=0, kind="read", title="s",
        )
        s.add(step); s.flush()
        step_id = step.id

    client.post(
        "/student/step-heartbeat",
        json={"step_id": step_id},
        headers={"Authorization": f"Bearer {stu}"},
    )
    import time as _t; _t.sleep(0.05)
    client.post(
        "/student/step-heartbeat",
        json={"step_id": step_id},
        headers={"Authorization": f"Bearer {stu}"},
    )
    with master_session() as s:
        hb = s.query(StudentStepHeartbeat).filter(
            StudentStepHeartbeat.student_id == sid,
        ).first()
        assert hb.last_heartbeat_at > hb.opened_at


def test_heartbeat_rejects_unassigned_module(fx) -> None:
    client, _tch, stu, _tid, _sid, mid = fx
    # Skapa en modul som eleven INTE är tilldelad
    with master_session() as s:
        t = s.query(Teacher).first()
        m2 = Module(teacher_id=t.id, title="Annan")
        s.add(m2); s.flush()
        step = ModuleStep(
            module_id=m2.id, sort_order=0, kind="read", title="x",
        )
        s.add(step); s.flush()
        step_id = step.id
    r = client.post(
        "/student/step-heartbeat",
        json={"step_id": step_id},
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 403


# ---------- Time-on-task-rapport ----------

def test_time_on_task_reports_median(fx) -> None:
    client, tch, _stu, _tid, sid, mid = fx
    with master_session() as s:
        step = ModuleStep(
            module_id=mid, sort_order=0, kind="read", title="Studera",
        )
        s.add(step); s.flush()
        step_id = step.id
        opened = datetime.utcnow() - timedelta(minutes=10)
        s.add(StudentStepHeartbeat(
            student_id=sid, step_id=step_id,
            opened_at=opened,
            last_heartbeat_at=opened + timedelta(minutes=8),
        ))
        s.add(StudentStepProgress(
            student_id=sid, step_id=step_id,
            completed_at=opened + timedelta(minutes=8),
        ))

    r = client.get(
        "/teacher/time-on-task",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    ours = [r for r in rows if r["step_id"] == step_id][0]
    assert ours["n_completed"] == 1
    assert ours["median_minutes"] is not None
    assert 7.5 < ours["median_minutes"] < 8.5


def test_time_on_task_counts_stuck(fx) -> None:
    client, tch, _stu, _tid, sid, mid = fx
    with master_session() as s:
        step = ModuleStep(
            module_id=mid, sort_order=0, kind="read", title="s",
        )
        s.add(step); s.flush()
        # Heartbeat men ingen completion = stuck
        s.add(StudentStepHeartbeat(
            student_id=sid, step_id=step.id,
        ))
    r = client.get(
        "/teacher/time-on-task",
        headers={"Authorization": f"Bearer {tch}"},
    )
    rows = r.json()
    ours = rows[0]
    assert ours["n_stuck"] == 1
    assert ours["n_completed"] == 0


# ---------- Bulk-portfolio ZIP ----------

def test_portfolio_bundle_zip(fx) -> None:
    client, tch, _stu, _tid, _sid, _mid = fx
    r = client.get(
        "/teacher/portfolio-bundle.zip",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    # Extrahera — ska finnas minst en PDF
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert len(names) >= 1
    assert all(n.endswith(".pdf") for n in names)
    assert any("Alice" in n for n in names)


def test_portfolio_bundle_requires_students(fx) -> None:
    # Läraren har redan Alice men vi ska testa "inga elever"-fallet.
    # Skapa en helt ny lärare utan elever.
    client, _tch, _stu, _tid, _sid, _mid = fx
    from hembudget.security.crypto import hash_password as _hp
    with master_session() as s:
        empty_teacher = Teacher(
            email="empty@x.se", name="Empty",
            password_hash=_hp("Abcdef12!"),
        )
        s.add(empty_teacher); s.flush()
        tid = empty_teacher.id
    from hembudget.api.deps import register_token as _rt
    tok = random_token()
    _rt(tok, role="teacher", teacher_id=tid)
    r = client.get(
        "/teacher/portfolio-bundle.zip",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 404
