"""Tester för achievement-systemet.

Täcker:
- evaluate_and_grant är idempotent (samma rad skapas inte två gånger)
- first_step tilldelas efter första klara steg
- ten_reflections vid 10 reflektion-steg
- streak: konsekutiva dagar ger current_streak
- seven_day_streak ges när streak når 7
- GET /student/achievements listar earned + available + streak
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.school import achievements as ach
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import (
    Module, ModuleStep, Student, StudentAchievement,
    StudentModule, StudentStepProgress, Teacher,
)
from hembudget.security.crypto import hash_password, random_token
from hembudget.api.deps import register_token


@pytest.fixture
def fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, str, int, int]:
    """Returnerar (client, student_token, student_id, module_id)."""
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
        mod = Module(teacher_id=t.id, title="M")
        s.add(mod); s.flush()
        mid = mod.id
        s.add(StudentModule(student_id=sid, module_id=mid))

    tok = random_token()
    register_token(tok, role="student", student_id=sid)
    return TestClient(app), tok, sid, mid


def _add_step_and_complete(mid: int, sid: int, kind: str, **prog_data) -> int:
    with master_session() as s:
        step = ModuleStep(
            module_id=mid, sort_order=0, kind=kind, title="s",
            content="Läs", params={},
        )
        s.add(step); s.flush()
        prog = StudentStepProgress(
            student_id=sid, step_id=step.id,
            completed_at=datetime.utcnow(),
            data=prog_data or None,
        )
        s.add(prog); s.flush()
        return step.id


def test_first_step_granted(fixture) -> None:
    _, _, sid, mid = fixture
    _add_step_and_complete(mid, sid, "read")
    with master_session() as s:
        new = ach.evaluate_and_grant(s, sid)
    assert "first_step" in new


def test_grant_is_idempotent(fixture) -> None:
    _, _, sid, mid = fixture
    _add_step_and_complete(mid, sid, "read")
    with master_session() as s:
        ach.evaluate_and_grant(s, sid)
    # Körning två → inga nya keys, inga dubbletter
    with master_session() as s:
        new = ach.evaluate_and_grant(s, sid)
        count = s.query(StudentAchievement).filter(
            StudentAchievement.student_id == sid,
            StudentAchievement.key == "first_step",
        ).count()
    assert new == []
    assert count == 1


def test_ten_reflections_threshold(fixture) -> None:
    _, _, sid, mid = fixture
    for _ in range(10):
        _add_step_and_complete(mid, sid, "reflect", reflection="en text")
    with master_session() as s:
        new = ach.evaluate_and_grant(s, sid)
    assert "ten_reflections" in new


def test_first_quiz_perfect_only_on_first_correct(fixture) -> None:
    _, _, sid, mid = fixture
    _add_step_and_complete(
        mid, sid, "quiz",
        answer=1, correct=True, first_correct=True, attempts=1,
    )
    with master_session() as s:
        new = ach.evaluate_and_grant(s, sid)
    assert "first_quiz_perfect" in new


def test_first_quiz_perfect_not_granted_if_first_was_wrong(fixture) -> None:
    _, _, sid, mid = fixture
    _add_step_and_complete(
        mid, sid, "quiz",
        answer=1, correct=True, first_correct=False, attempts=3,
    )
    with master_session() as s:
        new = ach.evaluate_and_grant(s, sid)
    assert "first_quiz_perfect" not in new


def test_streak_consecutive_days(fixture) -> None:
    _, _, sid, _ = fixture
    # Skapa slutförda progress-rader på 3 konsekutiva dagar
    today = datetime.utcnow().date()
    with master_session() as s:
        mid = s.query(Module).first().id
        for i in range(3):
            step = ModuleStep(
                module_id=mid, sort_order=i, kind="read", title=f"s{i}",
            )
            s.add(step); s.flush()
            prog = StudentStepProgress(
                student_id=sid, step_id=step.id,
                completed_at=datetime.combine(
                    today - timedelta(days=i),
                    datetime.min.time(),
                ),
            )
            s.add(prog)

    with master_session() as s:
        current, longest = ach.compute_streak(s, sid, today=today)
    assert current == 3
    assert longest == 3


def test_seven_day_streak_triggers(fixture) -> None:
    _, _, sid, _ = fixture
    today = datetime.utcnow().date()
    with master_session() as s:
        mid = s.query(Module).first().id
        for i in range(7):
            step = ModuleStep(
                module_id=mid, sort_order=i, kind="read", title=f"d{i}",
            )
            s.add(step); s.flush()
            s.add(StudentStepProgress(
                student_id=sid, step_id=step.id,
                completed_at=datetime.combine(
                    today - timedelta(days=i),
                    datetime.min.time(),
                ),
            ))

    with master_session() as s:
        new = ach.evaluate_and_grant(s, sid)
    assert "seven_day_streak" in new


def test_endpoint_lists_earned_and_available(fixture) -> None:
    client, tok, sid, mid = fixture
    _add_step_and_complete(mid, sid, "read")
    with master_session() as s:
        ach.evaluate_and_grant(s, sid)

    r = client.get(
        "/student/achievements",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    earned_keys = {e["key"] for e in body["earned"]}
    assert "first_step" in earned_keys
    # available innehåller alla achievements
    assert len(body["available"]) >= len(earned_keys)
    # streak finns
    assert "current" in body["streak"]
    assert "longest" in body["streak"]


def test_complete_endpoint_includes_new_achievements(fixture) -> None:
    client, tok, sid, mid = fixture
    with master_session() as s:
        step = ModuleStep(
            module_id=mid, sort_order=0, kind="read", title="s",
        )
        s.add(step); s.flush()
        step_id = step.id

    r = client.post(
        f"/student/steps/{step_id}/complete",
        json={},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "new_achievements" in body
    keys = [a["key"] for a in body["new_achievements"]]
    # first_step och first_module_done (modulen har bara 1 steg) kommer
    # båda på första completion
    assert "first_step" in keys
    assert "first_module_done" in keys

    # Andra anrop med samma (redan klart) steg: alla achievements redan
    # tjänade → inget nytt.
    r2 = client.post(
        f"/student/steps/{step_id}/complete",
        json={},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r2.json()["new_achievements"] == []
