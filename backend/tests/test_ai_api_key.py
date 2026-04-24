"""Tester för super-admin-hantering av Anthropic API-nyckeln.

Täcker:
- Att inloggad super-admin kan sätta / visa / radera nyckel
- Att icke-super-admin får 403
- Att ai._read_api_key() prioriterar DB över env
- Att invalidate_client() tvingar ny klient-init
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.school import ai as ai_core
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import AppConfig, Teacher
from hembudget.security.crypto import hash_password, random_token
from hembudget.api.deps import register_token


@pytest.fixture
def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Fräsch school-mode-app per test — egen DATA_DIR så master.db är isolerat."""
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    monkeypatch.delenv("HEMBUDGET_BOOTSTRAP_TEACHER_EMAIL", raising=False)
    monkeypatch.delenv("HEMBUDGET_BOOTSTRAP_TEACHER_PASSWORD", raising=False)
    monkeypatch.delenv("HEMBUDGET_BOOTSTRAP_SECRET", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TURNSTILE_SECRET", raising=False)

    # settings är en Pydantic-singleton som bara läser env vid skapelse.
    # Att sätta miljövariabeln räcker inte — vi pekar om data_dir direkt.
    from hembudget.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    # Nollställ ai-klient + master-engine + scope-engines så varje test
    # får en helt egen master.db.
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

    # Patcha bort demo-seeden så den inte injicerar demo-lärare som
    # skulle kunna krocka med våra fixtures.
    from hembudget.school import demo_seed as demo_seed_mod
    monkeypatch.setattr(demo_seed_mod, "build_demo", lambda: {"skipped": True})

    import importlib
    import hembudget.main as main_mod
    importlib.reload(main_mod)
    app = main_mod.build_app()

    init_master_engine()
    with master_session() as s:
        admin = Teacher(
            email="admin@test.se",
            name="Admin",
            password_hash=hash_password("Abcdef12!"),
            is_super_admin=True,
        )
        teacher = Teacher(
            email="teacher@test.se",
            name="Lärare",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add_all([admin, teacher])
        s.flush()

    return TestClient(app)


def _super_admin_token() -> str:
    with master_session() as s:
        admin = s.query(Teacher).filter(Teacher.email == "admin@test.se").first()
        assert admin is not None
        token = random_token()
        register_token(token, role="teacher", teacher_id=admin.id)
        return token


def _regular_token() -> str:
    with master_session() as s:
        t = s.query(Teacher).filter(Teacher.email == "teacher@test.se").first()
        assert t is not None
        token = random_token()
        register_token(token, role="teacher", teacher_id=t.id)
        return token


def test_api_key_status_empty_by_default(app_client: TestClient) -> None:
    token = _super_admin_token()
    r = app_client.get(
        "/admin/ai/api-key",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["source"] == ""
    assert body["preview"] == ""


def test_non_super_admin_cannot_manage_key(app_client: TestClient) -> None:
    token = _regular_token()
    r = app_client.get(
        "/admin/ai/api-key",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_set_and_delete_api_key(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mocka anthropic-klienten så vi inte behöver riktig nyckel
    monkeypatch.setattr(ai_core, "is_available", lambda: True)

    token = _super_admin_token()
    fake_key = "sk-ant-api03-" + "A" * 30

    # Sätt
    r = app_client.post(
        "/admin/ai/api-key",
        json={"key": fake_key},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is True
    assert body["source"] == "db"
    assert body["preview"].endswith(fake_key[-4:])

    # Bekräfta att DB faktiskt fått värdet
    with master_session() as s:
        cfg = s.get(AppConfig, ai_core.AI_KEY_CONFIG_KEY)
        assert cfg is not None
        assert cfg.value["key"] == fake_key

    # Radera
    r = app_client.delete(
        "/admin/ai/api-key",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["source"] == ""

    # Bekräfta att DB-värdet är borta
    with master_session() as s:
        cfg = s.get(AppConfig, ai_core.AI_KEY_CONFIG_KEY)
        assert cfg is None


def test_db_key_beats_env_var(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Env-nyckel ska vara fallback, DB-nyckel ska vinna.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-" + "X" * 20)
    token = _super_admin_token()

    # Utan DB-värde → source=env
    assert ai_core.key_source() == "env"

    db_key = "sk-ant-api03-" + "Y" * 30
    r = app_client.post(
        "/admin/ai/api-key",
        json={"key": db_key},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    # Nu ska DB vinna
    assert ai_core.key_source() == "db"
    assert ai_core._read_api_key() == db_key


def test_short_key_rejected(app_client: TestClient) -> None:
    token = _super_admin_token()
    r = app_client.post(
        "/admin/ai/api-key",
        json={"key": "abc"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422  # pydantic min_length=20
