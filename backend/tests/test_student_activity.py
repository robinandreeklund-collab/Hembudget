"""Tester för P2 — StudentActivity event-log.

Verifierar att meningsfulla handlingar i scope-DB:n (transaktioner,
budget, lån, kategorisering) lämnar ett audit-spår i master-DB:n så
läraren kan följa elevens arbete utan att impersonera.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import (
    Student, StudentActivity, Teacher,
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
        t = Teacher(
            email="t@x.se", name="T",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(t); s.flush()
        stu = Student(
            teacher_id=t.id, display_name="A", login_code="LOGINCODE",
        )
        s.add(stu); s.flush()
        sid = stu.id
        tid = t.id
    stu_tok = random_token()
    register_token(stu_tok, role="student", student_id=sid)
    teacher_tok = random_token()
    register_token(teacher_tok, role="teacher", teacher_id=tid)

    return TestClient(app), stu_tok, teacher_tok, sid


def _activities_for(sid: int) -> list[StudentActivity]:
    with master_session() as s:
        return (
            s.query(StudentActivity)
            .filter(StudentActivity.student_id == sid)
            .order_by(StudentActivity.occurred_at)
            .all()
        )


def test_set_budget_logs_activity(fx) -> None:
    client, stu_tok, _t_tok, sid = fx
    # Eleven sätter en budget — kräver att en kategori finns i scope-DB:n
    # (auto-seedas vid första anropet via /categories endpoint).
    cats = client.get(
        "/categories", headers={"Authorization": f"Bearer {stu_tok}"},
    ).json()
    assert isinstance(cats, list) and len(cats) > 0
    cat_id = cats[0]["id"]

    r = client.post(
        "/budget/",
        json={"month": "2025-08", "category_id": cat_id, "planned_amount": 1500},
        headers={"Authorization": f"Bearer {stu_tok}"},
    )
    assert r.status_code == 200, r.text

    rows = _activities_for(sid)
    assert len(rows) == 1
    assert rows[0].kind == "budget.set"
    assert "1500" in rows[0].summary
    assert rows[0].payload and rows[0].payload.get("month") == "2025-08"


def test_create_loan_logs_activity(fx) -> None:
    client, stu_tok, _t_tok, sid = fx
    r = client.post(
        "/loans/",
        json={
            "name": "Bolån",
            "lender": "SBAB",
            "principal_amount": 1500000,
            "start_date": "2024-01-01",
            "interest_rate": 0.035,
        },
        headers={"Authorization": f"Bearer {stu_tok}"},
    )
    assert r.status_code == 200, r.text
    rows = _activities_for(sid)
    assert any(r.kind == "loan.created" for r in rows)
    loan_act = next(r for r in rows if r.kind == "loan.created")
    assert "Bolån" in loan_act.summary
    assert loan_act.payload and loan_act.payload.get("principal_amount") == 1500000


def test_teacher_can_list_student_activity(fx) -> None:
    """Lärar-endpoint /teacher/students/{id}/activity returnerar
    elevens flöde i omvänd kronologisk ordning."""
    client, stu_tok, t_tok, sid = fx

    cats = client.get(
        "/categories", headers={"Authorization": f"Bearer {stu_tok}"},
    ).json()
    cat_id = cats[0]["id"]

    # Två handlingar
    client.post(
        "/budget/",
        json={"month": "2025-08", "category_id": cat_id, "planned_amount": 1000},
        headers={"Authorization": f"Bearer {stu_tok}"},
    )
    client.post(
        "/loans/",
        json={
            "name": "L1", "lender": "SBAB",
            "principal_amount": 50000,
            "start_date": "2024-01-01",
            "interest_rate": 0.04,
        },
        headers={"Authorization": f"Bearer {stu_tok}"},
    )

    # Lärar-vy
    r = client.get(
        f"/teacher/students/{sid}/activity",
        headers={"Authorization": f"Bearer {t_tok}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 2
    # Senaste först
    assert items[0]["kind"] == "loan.created"
    assert items[1]["kind"] == "budget.set"


def test_teacher_cannot_see_other_teachers_student_activity(fx) -> None:
    client, stu_tok, _t_tok, sid = fx
    cats = client.get(
        "/categories", headers={"Authorization": f"Bearer {stu_tok}"},
    ).json()
    cat_id = cats[0]["id"]
    client.post(
        "/budget/",
        json={"month": "2025-08", "category_id": cat_id, "planned_amount": 1000},
        headers={"Authorization": f"Bearer {stu_tok}"},
    )

    with master_session() as s:
        other = Teacher(
            email="o@x.se", name="O",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(other); s.flush()
        oid = other.id
    other_tok = random_token()
    register_token(other_tok, role="teacher", teacher_id=oid)

    r = client.get(
        f"/teacher/students/{sid}/activity",
        headers={"Authorization": f"Bearer {other_tok}"},
    )
    assert r.status_code == 404


def test_log_activity_silently_noops_without_actor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Helper:n får inte krascha om ContextVar saknas — t.ex. när
    den anropas från ett bakgrundsjobb utanför en HTTP-request."""
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    from hembudget.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from hembudget.school import engines as eng_mod
    if eng_mod._master_engine is not None:
        eng_mod._master_engine.dispose()
    eng_mod._master_engine = None
    eng_mod._master_session = None
    init_master_engine()

    from hembudget.school.activity import log_activity
    # Ingen actor-context satt → ska helt enkelt inte göra något
    log_activity("test.event", "borde inte krascha")
    # Ingen rad ska ha skapats
    with master_session() as s:
        n = s.query(StudentActivity).count()
        assert n == 0
