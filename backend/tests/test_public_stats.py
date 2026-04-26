"""Test för GET /public/stats — landningssidans ticker."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import (
    Module, ModuleStep, Student, StudentModule, StudentStepProgress, Teacher,
)
from hembudget.security.crypto import hash_password


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
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
    return TestClient(app)


def test_public_stats_counts(client: TestClient) -> None:
    with master_session() as s:
        t = Teacher(
            email="a@x.se", name="A",
            password_hash=hash_password("Abcdef12!"),
        )
        demo = Teacher(
            email="demo@x.se", name="Demo", is_demo=True,
            password_hash=hash_password("Abcdef12!"),
        )
        s.add_all([t, demo]); s.flush()
        stu = Student(
            teacher_id=t.id, display_name="E", login_code="LOGINCODE",
        )
        s.add(stu); s.flush()
        m = Module(teacher_id=t.id, title="M")
        s.add(m); s.flush()
        # Modul avklarad
        s.add(StudentModule(
            student_id=stu.id, module_id=m.id,
            completed_at=datetime.utcnow(),
        ))
        step = ModuleStep(
            module_id=m.id, sort_order=0, kind="reflect", title="R",
        )
        s.add(step); s.flush()
        s.add(StudentStepProgress(
            student_id=stu.id, step_id=step.id,
            completed_at=datetime.utcnow(),
            data={"reflection": "text"},
        ))

    r = client.get("/public/stats")
    assert r.status_code == 200
    body = r.json()
    # Demo-läraren räknas inte med
    assert body["teachers"] == 1
    assert body["students"] == 1
    assert body["modules_completed"] == 1
    assert body["reflections_written"] == 1


def test_public_stats_has_no_pii(client: TestClient) -> None:
    r = client.get("/public/stats")
    body = r.json()
    assert set(body.keys()) == {
        "teachers", "students", "modules_completed", "reflections_written",
    }
    for v in body.values():
        assert isinstance(v, int)
