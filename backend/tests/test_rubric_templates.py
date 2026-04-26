"""Tester för Fas 3.2: CRUD på RubricTemplate + kloning mellan lärare."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import RubricTemplate, Teacher
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
        a = Teacher(
            email="a@x.se", name="A",
            password_hash=hash_password("Abcdef12!"),
        )
        b = Teacher(
            email="b@x.se", name="B",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add_all([a, b]); s.flush()
        aid, bid = a.id, b.id
    a_tok, b_tok = random_token(), random_token()
    register_token(a_tok, role="teacher", teacher_id=aid)
    register_token(b_tok, role="teacher", teacher_id=bid)
    return TestClient(app), a_tok, aid, b_tok, bid


def _sample() -> dict:
    return {
        "name": "Reflektionskvalitet",
        "description": "Djup och struktur",
        "is_shared": False,
        "criteria": [
            {"key": "depth", "name": "Djup", "levels": ["Låg", "Medel", "Hög"]},
            {"key": "clar", "name": "Tydlighet", "levels": ["Låg", "Hög"]},
        ],
    }


def test_create_and_list(fx) -> None:
    client, a_tok, _a, _b_tok, _b = fx
    r = client.post(
        "/teacher/rubric-templates",
        json=_sample(),
        headers={"Authorization": f"Bearer {a_tok}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Reflektionskvalitet"
    assert body["is_mine"] is True
    assert len(body["criteria"]) == 2

    r2 = client.get(
        "/teacher/rubric-templates",
        headers={"Authorization": f"Bearer {a_tok}"},
    )
    assert r2.status_code == 200
    assert len(r2.json()) == 1


def test_other_teacher_sees_only_shared(fx) -> None:
    client, a_tok, _aid, b_tok, _bid = fx
    # A skapar en privat mall
    client.post(
        "/teacher/rubric-templates", json=_sample(),
        headers={"Authorization": f"Bearer {a_tok}"},
    )
    # B ska inte se den
    r = client.get(
        "/teacher/rubric-templates",
        headers={"Authorization": f"Bearer {b_tok}"},
    )
    assert len(r.json()) == 0

    # A markerar delad
    body = _sample(); body["is_shared"] = True
    client.post(
        "/teacher/rubric-templates", json=body,
        headers={"Authorization": f"Bearer {a_tok}"},
    )
    r = client.get(
        "/teacher/rubric-templates",
        headers={"Authorization": f"Bearer {b_tok}"},
    )
    listed = r.json()
    assert len(listed) == 1
    assert listed[0]["is_shared"] is True
    assert listed[0]["is_mine"] is False
    assert listed[0]["owner_name"] == "A"


def test_cannot_edit_others_template(fx) -> None:
    client, a_tok, _aid, b_tok, _bid = fx
    body = _sample(); body["is_shared"] = True
    rc = client.post(
        "/teacher/rubric-templates", json=body,
        headers={"Authorization": f"Bearer {a_tok}"},
    )
    tid = rc.json()["id"]
    # B försöker redigera
    r = client.patch(
        f"/teacher/rubric-templates/{tid}",
        json=_sample(),
        headers={"Authorization": f"Bearer {b_tok}"},
    )
    assert r.status_code == 403


def test_clone_creates_owned_copy(fx) -> None:
    client, a_tok, _aid, b_tok, _bid = fx
    body = _sample(); body["is_shared"] = True
    rc = client.post(
        "/teacher/rubric-templates", json=body,
        headers={"Authorization": f"Bearer {a_tok}"},
    )
    tid = rc.json()["id"]
    r = client.post(
        f"/teacher/rubric-templates/{tid}/clone",
        headers={"Authorization": f"Bearer {b_tok}"},
    )
    assert r.status_code == 200
    cloned = r.json()
    assert cloned["is_mine"] is True
    assert cloned["is_shared"] is False
    assert cloned["name"].endswith("(kopia)")

    # Original oförändrad
    with master_session() as s:
        orig = s.query(RubricTemplate).filter(RubricTemplate.id == tid).first()
        assert orig is not None
        assert orig.name == "Reflektionskvalitet"


def test_clone_rejects_non_shared(fx) -> None:
    client, a_tok, _aid, b_tok, _bid = fx
    rc = client.post(
        "/teacher/rubric-templates", json=_sample(),  # is_shared=False default
        headers={"Authorization": f"Bearer {a_tok}"},
    )
    tid = rc.json()["id"]
    r = client.post(
        f"/teacher/rubric-templates/{tid}/clone",
        headers={"Authorization": f"Bearer {b_tok}"},
    )
    assert r.status_code == 403


def test_delete_own_template(fx) -> None:
    client, a_tok, _aid, _b_tok, _bid = fx
    rc = client.post(
        "/teacher/rubric-templates", json=_sample(),
        headers={"Authorization": f"Bearer {a_tok}"},
    )
    tid = rc.json()["id"]
    r = client.delete(
        f"/teacher/rubric-templates/{tid}",
        headers={"Authorization": f"Bearer {a_tok}"},
    )
    assert r.status_code == 200
    r2 = client.get(
        "/teacher/rubric-templates",
        headers={"Authorization": f"Bearer {a_tok}"},
    )
    assert len(r2.json()) == 0


def test_create_rejects_empty_criteria(fx) -> None:
    client, a_tok, _aid, _b_tok, _bid = fx
    r = client.post(
        "/teacher/rubric-templates",
        json={
            "name": "x", "description": "",
            "criteria": [], "is_shared": False,
        },
        headers={"Authorization": f"Bearer {a_tok}"},
    )
    assert r.status_code == 422  # min_length=1 på criteria
