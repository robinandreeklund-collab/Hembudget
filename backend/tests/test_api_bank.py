"""Smoke-tester för /bank/* (idé 3, PR 5b).

Verifierar:
- /bank/me visar has_pin=False initialt
- /bank/set-pin sätter PIN
- /bank/session/init kräver PIN, skapar token
- /bank/session/{token}/confirm med rätt PIN sätter confirmed_at
- /bank/session/{token} returnerar status
- Lärar-reset av PIN
- 403 vid annan elev
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import Student, StudentProfile, Teacher
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
        stu = Student(
            teacher_id=tid, display_name="Eva", login_code="EVA00001",
        )
        s.add(stu); s.flush()
        sid = stu.id
        s.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska", employer="Region Stockholm",
            gross_salary_monthly=30000, net_salary_monthly=24000,
            tax_rate_effective=0.2, age=22, city="Sthlm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000, personality="blandad",
        ))

    tch_tok = random_token()
    stu_tok = random_token()
    register_token(tch_tok, role="teacher", teacher_id=tid)
    register_token(stu_tok, role="student", student_id=sid)
    return TestClient(app), tch_tok, stu_tok, tid, sid


def test_bank_me_no_pin_initially(fx) -> None:
    client, _, stu, *_ = fx
    r = client.get("/bank/me", headers={"Authorization": f"Bearer {stu}"})
    assert r.status_code == 200
    assert r.json()["has_pin"] is False


def test_set_pin_then_me_shows_has_pin(fx) -> None:
    client, _, stu, *_ = fx
    r = client.post(
        "/bank/set-pin",
        json={"pin": "1234"},
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    r2 = client.get("/bank/me", headers={"Authorization": f"Bearer {stu}"})
    assert r2.json()["has_pin"] is True


def test_set_pin_requires_4_digits(fx) -> None:
    client, _, stu, *_ = fx
    r = client.post(
        "/bank/set-pin",
        json={"pin": "abcd"},
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 400


def test_init_session_requires_pin_first(fx) -> None:
    client, _, stu, *_ = fx
    r = client.post(
        "/bank/session/init",
        json={"purpose": "login"},
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 400


def test_full_session_flow_init_confirm_status(fx) -> None:
    client, _, stu, *_ = fx
    # Sätt PIN
    client.post(
        "/bank/set-pin",
        json={"pin": "5678"},
        headers={"Authorization": f"Bearer {stu}"},
    )
    # Init session
    r = client.post(
        "/bank/session/init",
        json={"purpose": "login"},
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert r.json()["qr_url"].startswith("/bank/sign?token=")

    # Status: inte confirmed än
    s = client.get(
        f"/bank/session/{token}",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    assert s["confirmed"] is False
    assert s["expired"] is False

    # Confirm med fel PIN
    r = client.post(
        f"/bank/session/{token}/confirm",
        json={"pin": "0000"},
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 401

    # Confirm med rätt PIN
    r = client.post(
        f"/bank/session/{token}/confirm",
        json={"pin": "5678"},
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200

    # Status nu confirmed
    s2 = client.get(
        f"/bank/session/{token}",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    assert s2["confirmed"] is True


def test_teacher_reset_bank_pin(fx) -> None:
    client, tch, stu, _tid, sid = fx
    client.post(
        "/bank/set-pin",
        json={"pin": "1111"},
        headers={"Authorization": f"Bearer {stu}"},
    )
    # Reset
    r = client.post(
        f"/teacher/employer/{sid}/reset-bank-pin",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200
    # /bank/me visar has_pin=False igen
    me = client.get(
        "/bank/me",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    assert me["has_pin"] is False


def test_other_student_cannot_confirm_session(fx) -> None:
    client, _, stu, tid, _sid = fx
    # Sätt PIN
    client.post(
        "/bank/set-pin",
        json={"pin": "2222"},
        headers={"Authorization": f"Bearer {stu}"},
    )
    init = client.post(
        "/bank/session/init",
        json={"purpose": "login"},
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    token = init["token"]
    # Skapa annan elev som försöker bekräfta
    with master_session() as s:
        other = Student(
            teacher_id=tid, display_name="Bob", login_code="BOB00001",
        )
        s.add(other); s.flush()
        oid = other.id
        # Annan elev har egen PIN
        s.add(StudentProfile(
            student_id=oid,
            profession="Frisör", employer="Cutters",
            gross_salary_monthly=27000, net_salary_monthly=22000,
            tax_rate_effective=0.2, age=20, city="Sthlm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=7000, personality="blandad",
        ))
    other_tok = random_token()
    register_token(other_tok, role="student", student_id=oid)
    # Sätt PIN för denna och försök bekräfta
    client.post(
        "/bank/set-pin",
        json={"pin": "3333"},
        headers={"Authorization": f"Bearer {other_tok}"},
    )
    r = client.post(
        f"/bank/session/{token}/confirm",
        json={"pin": "3333"},
        headers={"Authorization": f"Bearer {other_tok}"},
    )
    assert r.status_code == 403
