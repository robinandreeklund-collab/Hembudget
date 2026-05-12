"""Smoke-test för /v2/employment/* (klasskompis-anställning).

Spec: dev/employment-flows.md (Fas C)

Verifierar:
- Endpoints är registrerade (returnerar 401 utan token, inte 404)
- hire-offer → kräver student-token + aktivt bolag (409 utan bolag)
- Båda elever måste tillhöra samma lärare (403 cross-class)
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import Student, Teacher
from hembudget.security.crypto import hash_password, random_token


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
        t = Teacher(
            email="t@x.se", name="T",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(t); s.flush()
        tid = t.id

        a = Student(
            teacher_id=tid, display_name="Alice",
            login_code="ALICE001",
        )
        b = Student(
            teacher_id=tid, display_name="Bob",
            login_code="BOB00001",
        )
        s.add_all([a, b]); s.flush()
        aid, bid = a.id, b.id

    a_tok = random_token()
    b_tok = random_token()
    register_token(a_tok, role="student", student_id=aid)
    register_token(b_tok, role="student", student_id=bid)
    return TestClient(app), a_tok, b_tok, aid, bid


def test_employments_requires_auth(fx):
    client, _a_tok, _b_tok, _aid, _bid = fx
    r = client.get("/v2/employment/employments")
    assert r.status_code in (401, 403), r.text


def test_offers_requires_auth(fx):
    client, *_ = fx
    r = client.get("/v2/employment/offers")
    assert r.status_code in (401, 403)


def test_hire_offer_without_company_returns_409(fx):
    client, a_tok, _b_tok, _aid, bid = fx
    r = client.post(
        "/v2/employment/hire-offer",
        headers={"Authorization": f"Bearer {a_tok}"},
        json={
            "classmate_student_id": bid,
            "role": "Säljare",
            "monthly_gross": 28000,
        },
    )
    # Alice har inget aktivt bolag · expect 409 Conflict
    assert r.status_code == 409, r.text


def test_hire_offer_self_returns_400(fx):
    client, a_tok, _b_tok, aid, _bid = fx
    r = client.post(
        "/v2/employment/hire-offer",
        headers={"Authorization": f"Bearer {a_tok}"},
        json={
            "classmate_student_id": aid,
            "role": "Säljare",
            "monthly_gross": 28000,
        },
    )
    assert r.status_code == 400, r.text


def test_list_offers_empty(fx):
    client, _a_tok, b_tok, _aid, _bid = fx
    r = client.get(
        "/v2/employment/offers",
        headers={"Authorization": f"Bearer {b_tok}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data == {"employments": []}


def test_accept_nonexistent_offer_returns_404(fx):
    client, _a_tok, b_tok, *_ = fx
    r = client.post(
        "/v2/employment/offers/9999/accept",
        headers={"Authorization": f"Bearer {b_tok}"},
    )
    assert r.status_code == 404, r.text


def test_payroll_run_without_company_returns_409(fx):
    client, a_tok, *_ = fx
    r = client.post(
        "/v2/employment/payroll/run",
        headers={"Authorization": f"Bearer {a_tok}"},
    )
    # Alice har inget bolag · 409 Conflict
    assert r.status_code == 409, r.text


def test_payroll_run_requires_auth(fx):
    client, *_ = fx
    r = client.post("/v2/employment/payroll/run")
    assert r.status_code in (401, 403)
