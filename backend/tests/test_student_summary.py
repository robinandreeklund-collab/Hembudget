"""Tester för Fas 4.2: AI-elevsammanfattning + pedagogisk kategori-
förklaring."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from hembudget.school import ai as ai_core
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
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TURNSTILE_SECRET", raising=False)
    from hembudget.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from hembudget.security import rate_limit as rl_mod
    rl_mod.reset_all_for_testing()
    ai_core.invalidate_client()
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
            ai_enabled=True,
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
        s.add(StudentModule(student_id=sid, module_id=m.id))
        # En kompetens + en reflektion + ett uppdrag
        c = Competency(
            key="ka", name="Kategori", level="grund", is_system=True,
        )
        s.add(c); s.flush()
        step = ModuleStep(
            module_id=m.id, sort_order=0, kind="reflect",
            title="Tänk", content="Varför?",
        )
        s.add(step); s.flush()
        s.add(ModuleStepCompetency(
            step_id=step.id, competency_id=c.id, weight=1.0,
        ))
        s.add(StudentStepProgress(
            student_id=sid, step_id=step.id,
            completed_at=__import__("datetime").datetime.utcnow(),
            data={"reflection": "Jag tänker att budget är viktigt."},
        ))
        s.add(Assignment(
            teacher_id=tid, student_id=sid,
            title="Läs lönespec", description="x", kind="free_text",
        ))

    tch_tok = random_token()
    stu_tok = random_token()
    register_token(tch_tok, role="teacher", teacher_id=tid)
    register_token(stu_tok, role="student", student_id=sid)
    monkeypatch.setattr(ai_core, "is_available", lambda: True)
    return TestClient(app), tch_tok, stu_tok, tid, sid


# ---------- Student summary ----------

def test_student_summary_uses_tool_and_includes_context(
    fx, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, tch, _stu, _tid, sid = fx
    captured_params: list[dict] = []

    class FakeMessages:
        def create(self, **params: Any) -> Any:
            captured_params.append(params)
            block = SimpleNamespace(
                type="tool_use",
                name="submit_student_summary",
                input={
                    "strengths": "Bra på att reflektera.",
                    "gaps": "Behöver mer om kategoriseringen.",
                    "next_steps": "Prova modulen Första budgeten.",
                },
            )
            usage = SimpleNamespace(
                input_tokens=50, output_tokens=100,
                cache_read_input_tokens=0, cache_creation_input_tokens=0,
            )
            return SimpleNamespace(content=[block], usage=usage)

    fake = SimpleNamespace(messages=FakeMessages())
    monkeypatch.setattr(ai_core, "_get_client", lambda: fake)

    r = client.post(
        f"/ai/teacher/students/{sid}/summary",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["student_id"] == sid
    assert body["strengths"] == "Bra på att reflektera."
    assert body["gaps"] == "Behöver mer om kategoriseringen."
    assert body["next_steps"] == "Prova modulen Första budgeten."

    # Prompten ska innehålla elevens namn + reflektionstext + uppdrag
    call = captured_params[0]
    user_msg = call["messages"][0]["content"]
    assert "Alice" in user_msg
    assert "budget är viktigt" in user_msg
    assert "Läs lönespec" in user_msg
    assert "Kategori" in user_msg  # kompetensen
    # Verifiera tool_choice-struktur
    assert call["tool_choice"]["name"] == "submit_student_summary"


def test_student_summary_rejects_other_teachers_student(
    fx, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _tch, _stu, _tid, sid = fx
    with master_session() as s:
        other = Teacher(
            email="o@x.se", name="O",
            password_hash=hash_password("Abcdef12!"),
            ai_enabled=True,
        )
        s.add(other); s.flush()
        oid = other.id
    other_tok = random_token()
    register_token(other_tok, role="teacher", teacher_id=oid)
    r = client.post(
        f"/ai/teacher/students/{sid}/summary",
        headers={"Authorization": f"Bearer {other_tok}"},
    )
    assert r.status_code == 404


# ---------- Category-explain streaming ----------

def test_category_explain_streams(
    fx, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _tch, stu, _tid, _sid = fx
    captured: list[dict] = []

    def fake_stream(**kw):
        captured.append(kw)
        yield {"type": "delta", "text": "Din kategorisering var rimlig..."}
        yield {"type": "done", "input_tokens": 10, "output_tokens": 15}

    monkeypatch.setattr(ai_core, "stream_claude", fake_stream)

    with client.stream(
        "POST",
        "/ai/category/explain/stream",
        json={
            "merchant": "ICA Maxi",
            "amount": 450.0,
            "student_category": "Kläder",
            "facit_category": "Mat",
        },
        headers={"Authorization": f"Bearer {stu}"},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = b"".join(r.iter_bytes()).decode("utf-8")

    frames = [p for p in body.split("\n\n") if p.strip()]
    events = [json.loads(f[len("data:"):].strip()) for f in frames]
    assert events[0]["type"] == "delta"
    assert events[-1]["type"] == "done"
    # Prompten ska innehålla båda kategorierna
    assert "Kläder" in captured[0]["user_prompt"]
    assert "Mat" in captured[0]["user_prompt"]
    assert "ICA Maxi" in captured[0]["user_prompt"]


def test_category_explain_requires_ai(
    fx, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _tch, stu, tid, _sid = fx
    with master_session() as s:
        t = s.query(Teacher).filter(Teacher.id == tid).first()
        t.ai_enabled = False
    r = client.post(
        "/ai/category/explain/stream",
        json={
            "merchant": "x", "amount": 100.0,
            "student_category": "a", "facit_category": "b",
        },
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 503
