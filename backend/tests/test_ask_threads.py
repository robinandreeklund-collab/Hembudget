"""Tester för Fas 4.1: multi-turn AskAI-trådar."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.school import ai as ai_core
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import (
    AskAiMessage, AskAiThread, Student, Teacher,
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
        stu = Student(
            teacher_id=t.id, display_name="A", login_code="LOGINCODE",
        )
        s.add(stu); s.flush()
        sid = stu.id
    tok = random_token()
    register_token(tok, role="student", student_id=sid)
    # Mock:a stream + is_available
    monkeypatch.setattr(ai_core, "is_available", lambda: True)

    return TestClient(app), tok, sid


def test_first_message_creates_thread(fx, monkeypatch: pytest.MonkeyPatch) -> None:
    client, tok, sid = fx

    def fake_stream(**kw):
        yield {"type": "delta", "text": "Svar."}
        yield {"type": "done", "input_tokens": 3, "output_tokens": 1}

    monkeypatch.setattr(ai_core, "stream_claude", fake_stream)

    with client.stream(
        "POST",
        "/ai/student/threads/message/stream",
        json={"question": "Vad är ränta?"},
        headers={"Authorization": f"Bearer {tok}"},
    ) as r:
        assert r.status_code == 200
        body = b"".join(r.iter_bytes()).decode("utf-8")

    frames = [p for p in body.split("\n\n") if p.strip()]
    events = [json.loads(f[len("data:"):].strip()) for f in frames]
    # Första event är "thread"
    assert events[0]["type"] == "thread"
    thread_id = events[0]["thread_id"]

    with master_session() as s:
        t = s.query(AskAiThread).filter(
            AskAiThread.id == thread_id
        ).first()
        assert t is not None
        assert t.student_id == sid
        msgs = s.query(AskAiMessage).filter(
            AskAiMessage.thread_id == thread_id,
        ).order_by(AskAiMessage.created_at).all()
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[0].content == "Vad är ränta?"
        assert msgs[1].role == "assistant"
        assert msgs[1].content == "Svar."


def test_second_message_uses_existing_thread_and_history(
    fx, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, tok, sid = fx

    captured: list[list[dict]] = []

    def fake_stream(**kw):
        captured.append(list(kw["messages"]))
        yield {"type": "delta", "text": "resp"}
        yield {"type": "done", "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(ai_core, "stream_claude", fake_stream)

    with client.stream(
        "POST",
        "/ai/student/threads/message/stream",
        json={"question": "Första"},
        headers={"Authorization": f"Bearer {tok}"},
    ) as r:
        body1 = b"".join(r.iter_bytes()).decode("utf-8")
    events1 = [
        json.loads(f[len("data:"):].strip())
        for f in body1.split("\n\n") if f.strip()
    ]
    tid = events1[0]["thread_id"]

    with client.stream(
        "POST",
        "/ai/student/threads/message/stream",
        json={"question": "Andra", "thread_id": tid},
        headers={"Authorization": f"Bearer {tok}"},
    ) as r:
        b"".join(r.iter_bytes())

    # Andra anropet bör skicka historik + nya user-meddelandet
    assert len(captured) == 2
    second_messages = captured[1]
    # Roller i ordning: user (1:a), assistant (1:a svar), user (2:a)
    assert [m["role"] for m in second_messages] == [
        "user", "assistant", "user",
    ]
    assert "Första" in second_messages[0]["content"]
    assert "Andra" in second_messages[-1]["content"]


def test_list_and_delete_thread(fx, monkeypatch: pytest.MonkeyPatch) -> None:
    client, tok, _sid = fx
    monkeypatch.setattr(ai_core, "stream_claude", lambda **kw: iter([
        {"type": "delta", "text": "x"},
        {"type": "done", "input_tokens": 1, "output_tokens": 1},
    ]))

    with client.stream(
        "POST",
        "/ai/student/threads/message/stream",
        json={"question": "Fråga 1"},
        headers={"Authorization": f"Bearer {tok}"},
    ) as r:
        body = b"".join(r.iter_bytes()).decode("utf-8")
    tid = next(
        json.loads(f[len("data:"):].strip())["thread_id"]
        for f in body.split("\n\n") if f.strip()
        and json.loads(f[len("data:"):].strip()).get("type") == "thread"
    )

    r = client.get(
        "/ai/student/threads",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    threads = r.json()
    assert len(threads) == 1
    assert threads[0]["id"] == tid
    assert threads[0]["message_count"] == 2

    r = client.delete(
        f"/ai/student/threads/{tid}",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
    r = client.get(
        "/ai/student/threads",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.json() == []


def test_cannot_access_another_students_thread(
    fx, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, tok, _sid = fx
    monkeypatch.setattr(ai_core, "stream_claude", lambda **kw: iter([
        {"type": "delta", "text": "x"},
        {"type": "done", "input_tokens": 1, "output_tokens": 1},
    ]))

    # Skapa tråd för första elev
    with client.stream(
        "POST",
        "/ai/student/threads/message/stream",
        json={"question": "Jag"},
        headers={"Authorization": f"Bearer {tok}"},
    ) as r:
        body = b"".join(r.iter_bytes()).decode("utf-8")
    tid = next(
        json.loads(f[len("data:"):].strip())["thread_id"]
        for f in body.split("\n\n") if f.strip()
        and json.loads(f[len("data:"):].strip()).get("type") == "thread"
    )

    # Skapa en annan elev
    with master_session() as s:
        t = s.query(Teacher).first()
        other = Student(
            teacher_id=t.id, display_name="B", login_code="OTHERCODE1",
        )
        s.add(other); s.flush()
        oid = other.id
    other_tok = random_token()
    register_token(other_tok, role="student", student_id=oid)

    r = client.get(
        f"/ai/student/threads/{tid}",
        headers={"Authorization": f"Bearer {other_tok}"},
    )
    assert r.status_code == 404
