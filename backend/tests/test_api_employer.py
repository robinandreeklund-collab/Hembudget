"""Smoke-tester för /employer/* + /teacher/employer/* (idé 1, C4).

Vi verifierar:
- Kärn-flödet status → next-question → answer → score uppdaterad
- Eventlogg fylls korrekt
- Idempotens på answer
- Lärar-vy visar eleven + manuell delta påverkar score
- Rangevalidering på lärar-delta
- Auth-skydd: ingen token → 401, fel teacher → 403
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.employer_seed import seed_all
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

        # Två elever — vi testar både teacher.class-vyn och
        # impersonering / delta för en specifik
        stu = Student(
            teacher_id=tid, display_name="Eva",
            login_code="EVA00001",
        )
        s.add(stu); s.flush()
        sid = stu.id
        s.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska",
            employer="Region Stockholm",
            gross_salary_monthly=30000, net_salary_monthly=24000,
            tax_rate_effective=0.2, age=22, city="Sthlm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000, personality="blandad",
        ))
        seed_all(s)

    tch_tok = random_token()
    stu_tok = random_token()
    register_token(tch_tok, role="teacher", teacher_id=tid)
    register_token(stu_tok, role="student", student_id=sid)
    return TestClient(app), tch_tok, stu_tok, tid, sid


# ---------- Status ----------

def test_status_unauthenticated_returns_401(fx) -> None:
    client, *_ = fx
    r = client.get("/employer/status")
    assert r.status_code == 401


def test_status_for_student_returns_profile_and_default_score(fx) -> None:
    client, _tch, stu, _tid, sid = fx
    r = client.get(
        "/employer/status",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["profession"] == "Undersköterska"
    assert data["employer"] == "Region Stockholm"
    # Default-score är 70 första gången
    assert data["satisfaction"]["score"] == 70
    assert data["satisfaction"]["trend"] == "stable"
    # HÖK Kommunal ska matcha Undersköterska
    assert data["has_agreement"] is True
    assert data["agreement"]["code"] == "hok_kommunal_2026"
    # Pension-pct från avtalets meta
    assert data["pension_pct"] is not None and data["pension_pct"] > 0


# ---------- Workplace-frågor ----------

def test_next_question_returns_lowest_difficulty_first(fx) -> None:
    client, _, stu, *_ = fx
    r = client.get(
        "/employer/questions/next",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    q = r.json()
    assert q is not None
    # Pedagogiskt: deltas/explanations får inte läcka
    for opt in q["options"]:
        assert "delta" not in opt
        assert "explanation" not in opt
    assert q["difficulty"] == 1


def test_answer_applies_delta_and_logs_event(fx) -> None:
    client, _, stu, *_ = fx
    nxt = client.get(
        "/employer/questions/next",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    qid = nxt["id"]
    # Välj första alternativet (oftast positivt delta enligt seedet)
    r = client.post(
        "/employer/questions/answer",
        json={"question_id": qid, "chosen_index": 0},
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    a = r.json()
    assert "delta_applied" in a
    assert "correct_path_md" in a
    # Score ska ha justerats motsvarande
    assert a["new_score"] == 70 + a["delta_applied"]
    # Eventloggen ska ha en rad
    ev = client.get(
        "/employer/events",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    assert ev["total"] == 1
    assert ev["events"][0]["kind"] == "question_answered"


def test_answer_is_idempotent(fx) -> None:
    client, _, stu, *_ = fx
    nxt = client.get(
        "/employer/questions/next",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    qid = nxt["id"]
    a1 = client.post(
        "/employer/questions/answer",
        json={"question_id": qid, "chosen_index": 0},
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    a2 = client.post(
        "/employer/questions/answer",
        json={"question_id": qid, "chosen_index": 0},
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    assert a1["new_score"] == a2["new_score"]
    # Eventloggen får inte ha duplicerats
    ev = client.get(
        "/employer/events",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    assert ev["total"] == 1


def test_invalid_chosen_index_returns_400(fx) -> None:
    client, _, stu, *_ = fx
    nxt = client.get(
        "/employer/questions/next",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    r = client.post(
        "/employer/questions/answer",
        json={"question_id": nxt["id"], "chosen_index": 99},
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 400


# ---------- Lärar-vy ----------

def test_teacher_class_lists_student(fx) -> None:
    client, tch, *_ = fx
    r = client.get(
        "/teacher/employer/class",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_students"] == 1
    row = data["rows"][0]
    assert row["display_name"] == "Eva"
    assert row["score"] == 70
    assert row["agreement_code"] == "hok_kommunal_2026"


def test_manual_delta_updates_score_and_logs_event(fx) -> None:
    client, tch, stu, _tid, sid = fx
    r = client.post(
        f"/teacher/employer/{sid}/delta",
        json={"delta": -10, "reason_md": "Sen ankomst tre dagar i rad"},
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["new_score"] == 60
    # Eventloggen visar den manuella raden
    ev = client.get(
        "/employer/events",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    assert ev["total"] == 1
    assert ev["events"][0]["kind"] == "manual_teacher"


def test_manual_delta_range_enforced(fx) -> None:
    client, tch, _stu, _tid, sid = fx
    r = client.post(
        f"/teacher/employer/{sid}/delta",
        json={"delta": 50, "reason_md": "för stor delta"},
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 422  # Pydantic-validering


def test_other_teacher_cannot_set_delta(fx, monkeypatch) -> None:
    client, _tch, _stu, _tid, sid = fx
    # Skapa en annan lärare
    with master_session() as s:
        other = Teacher(
            email="other@x.se", name="Other",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(other); s.flush()
        oid = other.id
    other_tok = random_token()
    register_token(other_tok, role="teacher", teacher_id=oid)
    r = client.post(
        f"/teacher/employer/{sid}/delta",
        json={"delta": 5, "reason_md": "fel lärare försöker"},
        headers={"Authorization": f"Bearer {other_tok}"},
    )
    assert r.status_code == 403
