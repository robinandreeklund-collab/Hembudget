"""Tester för Fas 2.3-tillägg:
- next_threshold + steps_remaining på /student/mastery
- peer_feedback i /student/steps/{id}/progress
- inactivity_nudge i /student/dashboard
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import (
    Competency, Module, ModuleStep, ModuleStepCompetency,
    PeerFeedback, Student, StudentModule, StudentProfile,
    StudentStepProgress, Teacher,
)
from hembudget.security.crypto import hash_password, random_token
from hembudget.api.deps import register_token


@pytest.fixture
def fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
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
        stu = Student(
            teacher_id=t.id, display_name="E", login_code="LOGINCODE",
        )
        s.add(stu); s.flush()
        sid = stu.id
        s.add(StudentProfile(
            student_id=sid,
            profession="elev", employer="Skola",
            gross_salary_monthly=25000, net_salary_monthly=20000,
            tax_rate_effective=0.20, age=18, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=7000, personality="blandad",
        ))
        mod = Module(teacher_id=t.id, title="M")
        s.add(mod); s.flush()
        mid = mod.id
        s.add(StudentModule(student_id=sid, module_id=mid))

    tok = random_token()
    register_token(tok, role="student", student_id=sid)
    return TestClient(app), tok, sid, mid


def test_mastery_returns_next_threshold_and_steps(fixture) -> None:
    client, tok, sid, mid = fixture
    # Skapa en kompetens och två steg kopplat med 50% (båda) completed=0
    with master_session() as s:
        c = Competency(
            key="test", name="Test-kompetens", level="grund", is_system=True,
        )
        s.add(c); s.flush()
        cid = c.id
        # Två steg, båda kopplade till kompetensen
        for i in range(2):
            step = ModuleStep(
                module_id=mid, sort_order=i, kind="read",
                title=f"s{i}",
            )
            s.add(step); s.flush()
            s.add(ModuleStepCompetency(
                step_id=step.id, competency_id=cid, weight=1.0,
            ))

    r = client.get(
        "/student/mastery",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    ours = [r for r in rows if r["competency"]["key"] == "test"]
    assert ours
    our = ours[0]
    # Inget klart → mastery 0, nästa tröskel = 0.25, två steg kvar
    assert our["mastery"] == 0.0
    assert our["next_threshold"] == 0.25
    assert our["steps_remaining"] == 2


def test_mastery_next_threshold_none_when_at_100(fixture) -> None:
    client, tok, sid, mid = fixture
    with master_session() as s:
        c = Competency(
            key="done", name="Klar", level="grund", is_system=True,
        )
        s.add(c); s.flush()
        step = ModuleStep(
            module_id=mid, sort_order=0, kind="read", title="s",
        )
        s.add(step); s.flush()
        s.add(ModuleStepCompetency(
            step_id=step.id, competency_id=c.id, weight=1.0,
        ))
        s.add(StudentStepProgress(
            student_id=sid, step_id=step.id,
            completed_at=datetime.utcnow(),
        ))

    r = client.get(
        "/student/mastery",
        headers={"Authorization": f"Bearer {tok}"},
    )
    rows = r.json()
    ours = [r for r in rows if r["competency"]["key"] == "done"]
    assert ours[0]["mastery"] == 1.0
    assert ours[0]["next_threshold"] is None
    assert ours[0]["steps_remaining"] == 0


def test_step_progress_returns_peer_feedback(fixture) -> None:
    client, tok, sid, mid = fixture
    with master_session() as s:
        step = ModuleStep(
            module_id=mid, sort_order=0, kind="reflect", title="r",
            content="Varför?",
        )
        s.add(step); s.flush()
        step_id = step.id
        prog = StudentStepProgress(
            student_id=sid, step_id=step_id,
            completed_at=datetime.utcnow(),
            data={"reflection": "Jag tänkte så här..."},
        )
        s.add(prog); s.flush()
        # En annan elev som reviewer
        other = Student(
            teacher_id=s.query(Teacher).first().id,
            display_name="O", login_code="OTHERCODE1",
        )
        s.add(other); s.flush()
        s.add(PeerFeedback(
            reviewer_student_id=other.id,
            target_progress_id=prog.id,
            body="Bra reflektion!",
        ))

    r = client.get(
        f"/student/steps/{step_id}/progress",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["peer_feedback"]) == 1
    assert body["peer_feedback"][0]["body"] == "Bra reflektion!"
    # Ingen reviewer-id/namn ska läcka — anonymt
    assert "reviewer_student_id" not in body["peer_feedback"][0]


def test_dashboard_inactivity_nudge_after_5_days(
    fixture, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, tok, sid, mid = fixture
    with master_session() as s:
        step = ModuleStep(
            module_id=mid, sort_order=0, kind="read", title="s",
        )
        s.add(step); s.flush()
        # Klar för 7 dagar sedan
        s.add(StudentStepProgress(
            student_id=sid, step_id=step.id,
            completed_at=datetime.utcnow() - timedelta(days=7),
        ))

    r = client.get(
        "/student/dashboard",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inactivity_nudge"] is not None
    assert body["inactivity_nudge"]["days_away"] >= 5


def test_dashboard_no_nudge_if_recent(fixture) -> None:
    client, tok, sid, mid = fixture
    with master_session() as s:
        step = ModuleStep(
            module_id=mid, sort_order=0, kind="read", title="s",
        )
        s.add(step); s.flush()
        s.add(StudentStepProgress(
            student_id=sid, step_id=step.id,
            completed_at=datetime.utcnow(),  # idag
        ))

    r = client.get(
        "/student/dashboard",
        headers={"Authorization": f"Bearer {tok}"},
    )
    body = r.json()
    assert body["inactivity_nudge"] is None


def test_dashboard_no_nudge_if_never_active(fixture) -> None:
    client, tok, _sid, _mid = fixture
    r = client.get(
        "/student/dashboard",
        headers={"Authorization": f"Bearer {tok}"},
    )
    body = r.json()
    assert body["inactivity_nudge"] is None
