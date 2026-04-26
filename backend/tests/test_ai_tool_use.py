"""Tester för tool_use-baserad JSON-struktur + SSE-streaming.

Vi mockar Anthropic-klienten — inga riktiga API-anrop. Testerna verifierar:
- Rubric/module/category-anropen använder tool_use med rätt schema.
- Endpoints returnerar `parsed`-dict direkt från tool-input (ingen manuell
  JSON-parse som kan krascha).
- Streaming-endpointen strömmar SSE-frames med delta/done-event.
"""
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
    Module, ModuleStep, Student, StudentStepProgress, Teacher,
)
from hembudget.security.crypto import hash_password, random_token
from hembudget.api.deps import register_token


@pytest.fixture
def app_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Samma mönster som test_ai_api_key.py — fräsch school-app."""
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    monkeypatch.delenv("HEMBUDGET_BOOTSTRAP_SECRET", raising=False)
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
        teacher = Teacher(
            email="t@x.se",
            name="T",
            password_hash=hash_password("Abcdef12!"),
            ai_enabled=True,
        )
        s.add(teacher)

    return TestClient(app)


def _teacher_token() -> tuple[str, int]:
    with master_session() as s:
        t = s.query(Teacher).filter(Teacher.email == "t@x.se").first()
        assert t is not None
        tok = random_token()
        register_token(tok, role="teacher", teacher_id=t.id)
        return tok, t.id


def _mock_client(monkeypatch: pytest.MonkeyPatch, *, tool_input: dict,
                 tool_name: str) -> list[dict]:
    """Patcha _get_client så client.messages.create(...) svarar med ett
    tool_use-block som innehåller `tool_input`. Returnerar listan av
    faktiska params som varje create-anrop fick, så testet kan
    verifiera schemat."""
    calls: list[dict] = []

    class FakeMessages:
        def create(self, **params: Any) -> Any:
            calls.append(params)
            block = SimpleNamespace(
                type="tool_use",
                name=tool_name,
                input=tool_input,
            )
            usage = SimpleNamespace(
                input_tokens=10,
                output_tokens=20,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
            return SimpleNamespace(content=[block], usage=usage)

    fake = SimpleNamespace(messages=FakeMessages())
    monkeypatch.setattr(ai_core, "_get_client", lambda: fake)
    return calls


# ---------- Tool-use: rubric ----------

def test_rubric_suggestion_uses_tool_schema(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, tid = _teacher_token()

    # Skapa elev + modul + reflektionssteg med rubric + ifyllt svar
    with master_session() as s:
        stu = Student(
            teacher_id=tid, display_name="E", login_code="LOGINCODE",
        )
        s.add(stu)
        s.flush()
        mod = Module(teacher_id=tid, title="Test")
        s.add(mod)
        s.flush()
        step = ModuleStep(
            module_id=mod.id, sort_order=0, kind="reflect",
            title="Fråga", content="Varför?",
            params={"rubric": [
                {"key": "k1", "name": "Struktur", "levels": ["låg", "hög"]},
            ]},
        )
        s.add(step)
        s.flush()
        prog = StudentStepProgress(
            student_id=stu.id, step_id=step.id,
            data={"reflection": "Jag tycker att..."},
        )
        s.add(prog)
        s.flush()
        prog_id = prog.id

    fake_result = {
        "scores": [
            {"criterion_id": "k1", "score": 1,
             "rationale": "Bra struktur"},
        ],
        "overall_comment": "Tydligt svar.",
    }
    calls = _mock_client(
        monkeypatch, tool_input=fake_result,
        tool_name="submit_rubric_assessment",
    )

    r = app_client.post(
        f"/ai/reflection/{prog_id}/rubric-suggestion",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # `parsed` kommer från tool-input direkt, inget manuellt JSON-parse
    assert body["parsed"] == fake_result

    # Verifiera att vi faktiskt skickade ett tool-choice-anrop
    assert len(calls) == 1
    call = calls[0]
    assert "tools" in call and len(call["tools"]) == 1
    assert call["tools"][0]["name"] == "submit_rubric_assessment"
    assert call["tool_choice"] == {
        "type": "tool", "name": "submit_rubric_assessment",
    }
    schema = call["tools"][0]["input_schema"]
    assert "scores" in schema["properties"]
    assert "overall_comment" in schema["properties"]


# ---------- Tool-use: modul-generering ----------

def test_module_generate_uses_tool_schema(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, _ = _teacher_token()
    fake_result = {
        "title": "Första budgeten",
        "summary": "En enkel budget.",
        "steps": [
            {"kind": "read", "title": "Intro", "body": "Text.", "sort_order": 0},
            {"kind": "reflect", "title": "Varför?", "body": "Skriv.", "sort_order": 1},
            {"kind": "task", "title": "Gör", "body": "Skapa.", "sort_order": 2},
            {"kind": "quiz", "title": "Q", "body": "Frågor.", "sort_order": 3},
        ],
    }
    calls = _mock_client(
        monkeypatch, tool_input=fake_result,
        tool_name="submit_module_template",
    )

    r = app_client.post(
        "/ai/modules/generate",
        json={"prompt": "En kort modul om basbudget för gymnasieelev."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parsed"]["title"] == "Första budgeten"
    assert len(body["parsed"]["steps"]) == 4

    assert calls[0]["tool_choice"]["name"] == "submit_module_template"


# ---------- Tool-use: kategori-check ----------

def test_category_check_uses_tool_schema(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, _ = _teacher_token()
    fake = {
        "is_match": True,
        "confidence": 0.85,
        "explanation": "Ungefär samma.",
    }
    calls = _mock_client(
        monkeypatch, tool_input=fake,
        tool_name="submit_category_match",
    )

    r = app_client.post(
        "/ai/category/check",
        json={
            "merchant": "ICA Maxi",
            "amount": 450.0,
            "student_category": "Matvaror",
            "facit_category": "Mat & livsmedel",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_match"] is True
    assert body["confidence"] == 0.85
    assert body["explanation"] == "Ungefär samma."
    assert calls[0]["tool_choice"]["name"] == "submit_category_match"


# ---------- Streaming ----------

def test_ask_stream_emits_delta_and_done(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock:a stream_claude så den yieldar 2 deltas + 1 done; verifiera
    att endpointen skickar dem som SSE-frames."""
    token, _ = _teacher_token()

    def fake_stream(**kwargs):
        yield {"type": "delta", "text": "Hej "}
        yield {"type": "delta", "text": "världen"}
        yield {"type": "done", "input_tokens": 3, "output_tokens": 2}

    monkeypatch.setattr(ai_core, "stream_claude", fake_stream)
    # _gate_ai kollar is_available() innan den släpper fram anropet
    monkeypatch.setattr(ai_core, "is_available", lambda: True)

    with app_client.stream(
        "POST",
        "/ai/student/ask/stream",
        json={"question": "Vad är ränta?"},
        headers={"Authorization": f"Bearer {token}"},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = b""
        for chunk in r.iter_bytes():
            body += chunk
    text = body.decode("utf-8")
    # Dela upp på SSE-frames
    frames = [p.strip() for p in text.split("\n\n") if p.strip()]
    events = []
    for f in frames:
        assert f.startswith("data:")
        events.append(json.loads(f[len("data:"):].strip()))
    assert events[0] == {"type": "delta", "text": "Hej "}
    assert events[1] == {"type": "delta", "text": "världen"}
    assert events[-1]["type"] == "done"


def test_ask_stream_requires_ai(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lärare utan ai_enabled → 503."""
    with master_session() as s:
        t = s.query(Teacher).filter(Teacher.email == "t@x.se").first()
        assert t is not None
        t.ai_enabled = False
    token, _ = _teacher_token()
    r = app_client.post(
        "/ai/student/ask/stream",
        json={"question": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 503
