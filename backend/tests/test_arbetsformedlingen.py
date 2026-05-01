"""Tester för game_engine.arbetsformedlingen + /v2/arbetsformedlingen/*."""
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
            email="t@s.se", name="T",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(t); s.flush()
        tid = t.id
        stu = Student(
            teacher_id=tid, display_name="Eva",
            login_code="EVA00001",
        )
        s.add(stu); s.flush()
        sid = stu.id
        sp = StudentProfile(
            student_id=sid, profession="Butiksbiträde",
            employer="ICA", gross_salary_monthly=27000,
            net_salary_monthly=20000, tax_rate_effective=0.26,
            personality="blandad", age=25, city="Göteborg",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000,
        )
        s.add(sp); s.commit()

    teacher_tok = random_token()
    student_tok = random_token()
    register_token(teacher_tok, role="teacher", teacher_id=tid)
    register_token(student_tok, role="student", student_id=sid)
    return TestClient(app), teacher_tok, student_tok, tid, sid


# === Matching ===


class TestMatching:
    def test_match_score_within_0_100(self):
        from hembudget.game_engine.arbetsformedlingen import (
            available_jobs_for_student,
        )
        from hembudget.game_engine.profile_generator import generate_profile
        profile = generate_profile(seed=42)
        jobs = available_jobs_for_student(profile, "2026-01", n=10)
        for j in jobs:
            assert 0 <= j.match_score <= 100

    def test_jobs_sorted_descending_by_match(self):
        from hembudget.game_engine.arbetsformedlingen import (
            available_jobs_for_student,
        )
        from hembudget.game_engine.profile_generator import generate_profile
        profile = generate_profile(seed=42)
        jobs = available_jobs_for_student(profile, "2026-01", n=8)
        scores = [j.match_score for j in jobs]
        assert scores == sorted(scores, reverse=True)

    def test_excludes_current_yrke(self):
        """Eleven söker inte samma jobb hen redan har."""
        from hembudget.game_engine.arbetsformedlingen import (
            available_jobs_for_student,
        )
        from hembudget.game_engine.profile_generator import generate_profile
        profile = generate_profile(seed=42)
        jobs = available_jobs_for_student(profile, "2026-01", n=20)
        keys = {j.yrke_key for j in jobs}
        assert profile.yrke_key not in keys

    def test_excludes_studerande(self):
        from hembudget.game_engine.arbetsformedlingen import (
            available_jobs_for_student,
        )
        from hembudget.game_engine.profile_generator import generate_profile
        profile = generate_profile(seed=42)
        jobs = available_jobs_for_student(profile, "2026-01", n=15)
        for j in jobs:
            assert not j.yrke_key.startswith("studerande_")


# === Endpoints ===


class TestEndpoints:
    def test_jobs_endpoint(self, fx):
        client, _, stok, _, _ = fx
        r = client.get(
            "/v2/arbetsformedlingen/jobs?ym=2026-01&n=5",
            headers={"Authorization": f"Bearer {stok}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "mats_message" in body
        assert len(body["jobs"]) == 5

    def test_jobs_requires_student_token(self, fx):
        client, *_ = fx
        r = client.get("/v2/arbetsformedlingen/jobs?ym=2026-01")
        assert r.status_code == 401

    def test_jobs_rejects_teacher(self, fx):
        client, ttok, _, _, _ = fx
        r = client.get(
            "/v2/arbetsformedlingen/jobs?ym=2026-01",
            headers={"Authorization": f"Bearer {ttok}"},
        )
        # 403 enligt _require_student
        assert r.status_code == 403

    def test_full_5_round_flow(self, fx):
        client, _, stok, _, sid = fx
        # Hämta jobs
        jobs = client.get(
            "/v2/arbetsformedlingen/jobs?ym=2026-01",
            headers={"Authorization": f"Bearer {stok}"},
        ).json()["jobs"]
        first = jobs[0]
        # Apply
        r = client.post(
            "/v2/arbetsformedlingen/apply",
            json=first,
            headers={"Authorization": f"Bearer {stok}"},
        )
        assert r.status_code == 200, r.text
        app_id = r.json()["id"]
        assert r.json()["status"] == "round_1"

        # Round 1
        r1 = client.post(
            f"/v2/arbetsformedlingen/applications/{app_id}/round",
            json={"payload": {"cover_letter_hours": 1.5}},
            headers={"Authorization": f"Bearer {stok}"},
        )
        assert r1.status_code == 200
        assert r1.json()["application"]["status"] == "round_2"

        # Round 2
        r2 = client.post(
            f"/v2/arbetsformedlingen/applications/{app_id}/round",
            json={"payload": {"tone": "reflekterande", "answers": ["a", "b", "c", "d"]}},
            headers={"Authorization": f"Bearer {stok}"},
        )
        assert r2.json()["application"]["status"] == "round_3"

        # Round 3
        r3 = client.post(
            f"/v2/arbetsformedlingen/applications/{app_id}/round",
            json={"payload": {"effort_level": "djup", "case_answer": "x" * 250}},
            headers={"Authorization": f"Bearer {stok}"},
        )
        assert r3.json()["application"]["status"] == "round_4"

        # Round 4 → triggar round 5 direkt
        r4 = client.post(
            f"/v2/arbetsformedlingen/applications/{app_id}/round",
            json={"payload": {"dress": "business_casual", "research_hours": 2.0}},
            headers={"Authorization": f"Bearer {stok}"},
        )
        assert r4.status_code == 200
        # Status ska vara antingen offer_pending eller rejected
        assert r4.json()["application"]["status"] in ("offer_pending", "rejected")
        assert r4.json()["application"]["final_score"] is not None

    def test_max_2_active_applications(self, fx):
        client, _, stok, _, _ = fx
        jobs = client.get(
            "/v2/arbetsformedlingen/jobs?ym=2026-01&n=5",
            headers={"Authorization": f"Bearer {stok}"},
        ).json()["jobs"]
        for j in jobs[:2]:
            r = client.post(
                "/v2/arbetsformedlingen/apply",
                json=j,
                headers={"Authorization": f"Bearer {stok}"},
            )
            assert r.status_code == 200
        # Tredje ska ge 400
        r3 = client.post(
            "/v2/arbetsformedlingen/apply",
            json=jobs[2],
            headers={"Authorization": f"Bearer {stok}"},
        )
        assert r3.status_code == 400

    def test_abandon_application(self, fx):
        client, _, stok, _, _ = fx
        jobs = client.get(
            "/v2/arbetsformedlingen/jobs?ym=2026-01",
            headers={"Authorization": f"Bearer {stok}"},
        ).json()["jobs"]
        app_id = client.post(
            "/v2/arbetsformedlingen/apply", json=jobs[0],
            headers={"Authorization": f"Bearer {stok}"},
        ).json()["id"]
        r = client.post(
            f"/v2/arbetsformedlingen/applications/{app_id}/abandon",
            headers={"Authorization": f"Bearer {stok}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "abandoned"

    def test_teacher_can_view_student_applications(self, fx):
        client, ttok, stok, _, sid = fx
        # Eleven söker
        jobs = client.get(
            "/v2/arbetsformedlingen/jobs?ym=2026-01",
            headers={"Authorization": f"Bearer {stok}"},
        ).json()["jobs"]
        client.post(
            "/v2/arbetsformedlingen/apply", json=jobs[0],
            headers={"Authorization": f"Bearer {stok}"},
        )
        # Lärare kollar
        r = client.get(
            f"/v2/teacher/arbetsformedlingen/applications/{sid}",
            headers={"Authorization": f"Bearer {ttok}"},
        )
        assert r.status_code == 200
        assert len(r.json()) == 1
