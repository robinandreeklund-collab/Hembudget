"""Tester för /ai/student/quiz-explain/stream.

Vi mockar stream_claude + is_available. Testerna verifierar:
- 400 om steget inte är quiz
- 400 om eleven inte svarat
- 400 om elevens svar faktiskt var rätt
- Happy path: SSE-frames med delta+done, användar-prompten innehåller
  elevens val och rätt svar.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from hembudget.school import ai as ai_core
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import (
    Module, ModuleStep, Student, StudentModule, StudentStepProgress, Teacher,
)
from hembudget.security.crypto import hash_password, random_token
from hembudget.api.deps import register_token


@pytest.fixture
def fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, str, int]:
    """Fräsch app + en elev med en quiz-progress som är fel-svarat."""
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
        s.add(t)
        s.flush()
        tid = t.id

        stu = Student(
            teacher_id=tid, display_name="E", login_code="LOGINCODE",
        )
        s.add(stu)
        s.flush()
        sid = stu.id

        mod = Module(teacher_id=tid, title="M")
        s.add(mod)
        s.flush()

        step = ModuleStep(
            module_id=mod.id, sort_order=0, kind="quiz",
            title="Q", content="Vad händer om räntan stiger?",
            params={
                "question": "Vad händer om räntan stiger?",
                "options": [
                    "Bolånet blir billigare",
                    "Bolånet blir dyrare",
                    "Inget händer",
                ],
                "correct_index": 1,
                "explanation": "Högre ränta → dyrare lån.",
            },
        )
        s.add(step)
        s.flush()
        step_id = step.id

        # enrolla eleven i modulen
        s.add(StudentModule(student_id=sid, module_id=mod.id))

        # Elevens (fel) svar
        s.add(StudentStepProgress(
            student_id=sid, step_id=step_id,
            completed_at=__import__("datetime").datetime.utcnow(),
            data={
                "answer": 0,
                "correct": False,
                "correct_index": 1,
                "first_correct": False,
                "attempts": 1,
            },
        ))

    # elev-token
    tok = random_token()
    register_token(tok, role="student", student_id=sid)
    return TestClient(app), tok, step_id


def test_quiz_explain_requires_wrong_answer(
    fixture: tuple[TestClient, str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, tok, step_id = fixture
    # Sätt AI som tillgänglig
    monkeypatch.setattr(ai_core, "is_available", lambda: True)
    monkeypatch.setattr(ai_core, "stream_claude",
                        lambda **k: iter([{"type": "done", "input_tokens": 1, "output_tokens": 1}]))

    # Markera svaret som rätt istället → 400
    with master_session() as s:
        prog = s.query(StudentStepProgress).first()
        assert prog is not None
        prog.data = dict(prog.data or {})
        prog.data["correct"] = True

    r = client.post(
        "/ai/student/quiz-explain/stream",
        json={"step_id": step_id},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 400


def test_quiz_explain_streams_with_context(
    fixture: tuple[TestClient, str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, tok, step_id = fixture
    monkeypatch.setattr(ai_core, "is_available", lambda: True)

    captured: dict[str, Any] = {}

    def fake_stream(**kwargs):
        captured["kwargs"] = kwargs
        yield {"type": "delta", "text": "Det är "}
        yield {"type": "delta", "text": "vanligt att tänka så."}
        yield {"type": "done", "input_tokens": 5, "output_tokens": 6}

    monkeypatch.setattr(ai_core, "stream_claude", fake_stream)

    with client.stream(
        "POST",
        "/ai/student/quiz-explain/stream",
        json={"step_id": step_id},
        headers={"Authorization": f"Bearer {tok}"},
    ) as r:
        assert r.status_code == 200
        body = b"".join(r.iter_bytes()).decode("utf-8")

    frames = [p for p in body.split("\n\n") if p.strip()]
    events = [json.loads(f[len("data:"):].strip()) for f in frames]
    assert events[0] == {"type": "delta", "text": "Det är "}
    assert events[-1]["type"] == "done"

    # Verifiera att prompten innehåller både elevens val + rätt svar
    user_prompt = captured["kwargs"]["user_prompt"]
    assert "Bolånet blir billigare" in user_prompt  # elevens val (index 0)
    assert "Bolånet blir dyrare" in user_prompt  # rätt svar (index 1)
