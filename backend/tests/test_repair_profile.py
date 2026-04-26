"""Tester för repair-profile-endpointen.

Bakgrund: tidigare versioner av master-migrationerna kunde krascha
under elev-skapelsen så att Student-raden commit:ades men
StudentProfile-raden saknades. Den eleven blev "föräldralös" och
kunde inte tas bort via UI eftersom huvudvyn dolde elever utan
profil. Vi exponerar nu has_profile + en repair-endpoint.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import (
    Student, StudentProfile, Teacher,
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
        # Skapa en "föräldralös" elev (Student utan StudentProfile) —
        # simulerar tidigare prod-bug där migration kraschade.
        stu = Student(
            teacher_id=t.id, display_name="Orphan", login_code="ORPHAN1",
        )
        s.add(stu); s.flush()
        sid = stu.id
        tid = t.id
    teacher_tok = random_token()
    register_token(teacher_tok, role="teacher", teacher_id=tid)

    return TestClient(app), teacher_tok, sid


def test_orphan_appears_in_student_list_with_has_profile_false(fx) -> None:
    client, t_tok, sid = fx
    r = client.get(
        "/teacher/students",
        headers={"Authorization": f"Bearer {t_tok}"},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == sid
    assert row["has_profile"] is False
    # Profession är None när profilen saknas
    assert row["profession"] is None


def test_repair_profile_creates_missing_profile(fx) -> None:
    client, t_tok, sid = fx
    # Före: ingen profil
    with master_session() as s:
        assert s.query(StudentProfile).filter_by(student_id=sid).first() is None

    r = client.post(
        f"/teacher/students/{sid}/repair-profile",
        headers={"Authorization": f"Bearer {t_tok}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_profile"] is True
    assert body["profession"]  # genererad deterministiskt

    # Efter: profilen finns i DB:n
    with master_session() as s:
        prof = s.query(StudentProfile).filter_by(student_id=sid).first()
        assert prof is not None
        assert prof.gross_salary_monthly > 0


def test_repair_profile_is_idempotent(fx) -> None:
    client, t_tok, sid = fx
    r1 = client.post(
        f"/teacher/students/{sid}/repair-profile",
        headers={"Authorization": f"Bearer {t_tok}"},
    )
    assert r1.status_code == 200
    prof1 = r1.json()["profession"]

    r2 = client.post(
        f"/teacher/students/{sid}/repair-profile",
        headers={"Authorization": f"Bearer {t_tok}"},
    )
    assert r2.status_code == 200
    # Samma profil — andra anropet ändrar ingenting
    assert r2.json()["profession"] == prof1


def test_repair_profile_404_for_unknown_student(fx) -> None:
    client, t_tok, _sid = fx
    r = client.post(
        "/teacher/students/99999/repair-profile",
        headers={"Authorization": f"Bearer {t_tok}"},
    )
    assert r.status_code == 404


def test_orphan_student_can_be_deleted(fx) -> None:
    """Säkerhetsnät: själva delete-flödet fungerar för föräldralös elev."""
    client, t_tok, sid = fx
    r = client.delete(
        f"/teacher/students/{sid}",
        headers={"Authorization": f"Bearer {t_tok}"},
    )
    assert r.status_code == 200
    # Och eleven är borta från listan
    r2 = client.get(
        "/teacher/students",
        headers={"Authorization": f"Bearer {t_tok}"},
    )
    assert r2.status_code == 200
    assert r2.json() == []


def test_list_students_works_when_partner_columns_missing(fx, monkeypatch) -> None:
    """Simulerar prod-buggen: master-DB:n saknar partner-kolumner men har
    elever. Tidigare kraschade /teacher/students med 500. Med deferred()
    + master_has_column-guard ska listan returneras OK."""
    client, t_tok, sid = fx
    # Skapa profil först (så vi har fall där SELECT skulle träffa)
    rr = client.post(
        f"/teacher/students/{sid}/repair-profile",
        headers={"Authorization": f"Bearer {t_tok}"},
    )
    assert rr.status_code == 200

    # Patcha kolumn-cachen för att låtsas att kolumnerna saknas i DB:n
    from hembudget.school import engines as eng_mod
    original = dict(eng_mod._master_columns)
    sp = set(eng_mod._master_columns.get("student_profiles", set()))
    sp.discard("partner_profession")
    sp.discard("partner_gross_salary")
    sp.discard("cost_split_preference")
    sp.discard("cost_split_decided_at")
    eng_mod._master_columns["student_profiles"] = sp
    try:
        r = client.get(
            "/teacher/students",
            headers={"Authorization": f"Bearer {t_tok}"},
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) == 1
        assert rows[0]["has_profile"] is True
    finally:
        eng_mod._master_columns.clear()
        eng_mod._master_columns.update(original)
