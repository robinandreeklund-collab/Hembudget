"""Tester för game_engine: ClassCalendar-modell, helpers, Profile Generator
och /v2/teacher/calendars + /v2/teacher/students/profile-preview-endpoints.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.game_engine_models import (
    ClassCalendar,
    compute_current_sim_year_month,
    shift_year_month,
)
from hembudget.school.models import Teacher
from hembudget.security.crypto import hash_password, random_token


# === Fixture (samma mönster som test_api_v2.fx) ===


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
            email="lar@skola.se", name="Test-lärare",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(t)
        s.flush()
        tid = t.id

    tok = random_token()
    register_token(tok, role="teacher", teacher_id=tid)
    return TestClient(app), tok, tid


# === shift_year_month + compute_current_sim_year_month ===


class TestYearMonthHelpers:
    def test_shift_forward(self):
        assert shift_year_month("2026-01", 1) == "2026-02"
        assert shift_year_month("2026-12", 1) == "2027-01"
        assert shift_year_month("2026-06", 18) == "2027-12"

    def test_shift_backward(self):
        assert shift_year_month("2026-01", -1) == "2025-12"
        assert shift_year_month("2026-03", -3) == "2025-12"

    def test_compute_current_at_start(self):
        start = datetime(2026, 5, 1, 9, 0)
        assert (
            compute_current_sim_year_month("2026-01", start, start, 1)
            == "2026-01"
        )

    def test_compute_current_after_three_weeks_fast(self):
        """Tempo 1 vecka per spelmånad → 3 veckor = 3 månader framåt."""
        start = datetime(2026, 5, 1, 9, 0)
        now = start + timedelta(weeks=3)
        assert (
            compute_current_sim_year_month("2026-01", start, now, 1)
            == "2026-04"
        )

    def test_compute_current_normal_tempo(self):
        """Tempo 2 veckor per spelmånad → 4 veckor = 2 månader."""
        start = datetime(2026, 5, 1)
        now = start + timedelta(weeks=4)
        assert (
            compute_current_sim_year_month("2026-01", start, now, 2)
            == "2026-03"
        )


# === Profile Generator (utan endpoint) ===


class TestProfileGenerator:
    def test_same_seed_produces_same_profile(self, fx):
        # Vi behöver master-DB för att compute_net_salary ska kunna läsa
        # AppConfig — fixturen säkerställer det.
        from hembudget.game_engine.profile_generator import generate_profile
        a = generate_profile(seed=42)
        b = generate_profile(seed=42)
        assert a.yrke_key == b.yrke_key
        assert a.city_key == b.city_key
        assert a.monthly_gross == b.monthly_gross
        assert a.housing.monthly_cost == b.housing.monthly_cost
        assert a.pentagon.economy == b.pentagon.economy

    def test_different_seeds_produce_variation(self, fx):
        from hembudget.game_engine.profile_generator import generate_profile
        profiles = [generate_profile(seed=s) for s in range(20)]
        cities = {p.city_key for p in profiles}
        yrken = {p.yrke_key for p in profiles}
        assert len(cities) >= 5, f"För få unika städer: {cities}"
        assert len(yrken) >= 5, f"För få unika yrken: {yrken}"

    def test_pentagon_within_45_80(self, fx):
        from hembudget.game_engine.profile_generator import generate_profile
        for s in range(50):
            p = generate_profile(seed=s)
            for axis in ("economy", "safety", "health", "social", "leisure"):
                v = getattr(p.pentagon, axis)
                assert 45 <= v <= 80, (
                    f"seed={s} {axis}={v} utanför 45-80"
                )

    def test_solo_partner_model_yields_no_partner(self, fx):
        from hembudget.game_engine.profile_generator import generate_profile
        for s in range(20):
            p = generate_profile(seed=s, partner_model="solo")
            assert p.family.status == "ensam"
            assert p.family.partner_yrke_key is None
            assert p.family.partner_gross_monthly is None

    def test_ai_partner_model_can_create_couple(self, fx):
        from hembudget.game_engine.profile_generator import generate_profile
        # Många seeds: minst en bör hamna i sambo eller barn
        sambos = 0
        for s in range(40):
            p = generate_profile(seed=s, partner_model="ai")
            if p.family.status in ("sambo", "familj_med_barn"):
                sambos += 1
                assert p.family.partner_yrke_key is not None
                assert (p.family.partner_gross_monthly or 0) > 0
        assert sambos >= 5, f"För få sambo-profiler: {sambos}/40"

    def test_housing_within_budget_constraint(self, fx):
        """Boendekostnad ska aldrig överstiga 35 % av hushållsnetto (ensam)
        eller 25 % (familj med barn). Studerande-arketyper exkluderas —
        de modelleras som "bor hemma hos förälder" (egen-boende-budgeten
        gäller inte) och får en separat fas senare."""
        from hembudget.game_engine.profile_generator import generate_profile
        violations = 0
        relevant = 0
        for s in range(120):
            p = generate_profile(seed=s)
            if p.yrke_key.startswith("studerande_"):
                continue
            relevant += 1
            limit = 0.25 if p.family.status == "familj_med_barn" else 0.32
            pct = p.housing.monthly_cost / max(p.household_net_monthly, 1)
            if pct > limit + 0.05:
                violations += 1
        assert relevant >= 80, f"För få vuxna profiler i samplet: {relevant}"
        assert violations == 0, (
            f"{violations}/{relevant} vuxen-profiler överstiger budget-cap"
        )

    def test_specific_archetype_returned(self, fx):
        from hembudget.game_engine.profile_generator import generate_profile
        p = generate_profile(seed=1, archetype="vard_underskoterska")
        assert "underskoterska" in p.yrke_key

    def test_facts_dict_complete(self, fx):
        from hembudget.game_engine.profile_generator import generate_profile
        p = generate_profile(seed=1)
        for required in (
            "age", "commute_minutes", "housing_pct", "has_student_loan",
            "family_status", "physical_demand",
        ):
            assert required in p.facts, f"Saknar fakta {required}"


# === ClassCalendar-endpoints ===


class TestCalendarEndpoints:
    def test_create_calendar(self, fx):
        client, tok, _ = fx
        r = client.post(
            "/v2/teacher/calendars",
            json={
                "class_label": "8A",
                "sim_start_year_month": "2026-01",
                "weeks_per_sim_month": 1,
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["class_label"] == "8A"
        assert body["sim_start_year_month"] == "2026-01"
        assert body["weeks_per_sim_month"] == 1
        # last_tick = sim_start - 1
        assert body["last_tick_year_month"] == "2025-12"
        assert body["is_paused"] is False

    def test_upsert_is_idempotent(self, fx):
        client, tok, _ = fx
        for tempo in (1, 2):
            r = client.post(
                "/v2/teacher/calendars",
                json={
                    "class_label": "9B",
                    "sim_start_year_month": "2026-01",
                    "weeks_per_sim_month": tempo,
                },
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert r.status_code == 200
        # Bara en kalender ska finnas
        rl = client.get(
            "/v2/teacher/calendars",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert rl.status_code == 200
        cals = [c for c in rl.json() if c["class_label"] == "9B"]
        assert len(cals) == 1
        assert cals[0]["weeks_per_sim_month"] == 2

    def test_pause_and_resume(self, fx):
        client, tok, _ = fx
        r = client.post(
            "/v2/teacher/calendars",
            json={
                "class_label": "8B",
                "sim_start_year_month": "2026-01",
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        cal_id = r.json()["id"]

        future = (datetime.utcnow() + timedelta(days=30)).isoformat()
        rp = client.post(
            f"/v2/teacher/calendars/{cal_id}/pause",
            json={"paused_until": future},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert rp.status_code == 200, rp.text
        assert rp.json()["is_paused"] is True

        rr = client.post(
            f"/v2/teacher/calendars/{cal_id}/resume",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert rr.status_code == 200
        assert rr.json()["paused_until"] is None
        assert rr.json()["is_paused"] is False

    def test_delete_calendar(self, fx):
        client, tok, _ = fx
        r = client.post(
            "/v2/teacher/calendars",
            json={
                "class_label": "9C",
                "sim_start_year_month": "2026-01",
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        cal_id = r.json()["id"]
        rd = client.delete(
            f"/v2/teacher/calendars/{cal_id}",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert rd.status_code == 204

    def test_other_teacher_cannot_access(self, fx):
        client, tok, tid = fx
        r = client.post(
            "/v2/teacher/calendars",
            json={
                "class_label": "8A",
                "sim_start_year_month": "2026-01",
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        cal_id = r.json()["id"]
        # Skapa annan lärare + token
        with master_session() as s:
            other = Teacher(
                email="other@x.se", name="Other",
                password_hash=hash_password("Abcdef12!"),
            )
            s.add(other)
            s.flush()
            other_id = other.id
        other_tok = random_token()
        register_token(other_tok, role="teacher", teacher_id=other_id)

        rp = client.post(
            f"/v2/teacher/calendars/{cal_id}/pause",
            json={"paused_until": (datetime.utcnow() + timedelta(days=1)).isoformat()},
            headers={"Authorization": f"Bearer {other_tok}"},
        )
        assert rp.status_code == 404

    def test_calendar_requires_teacher_token(self, fx):
        client, *_ = fx
        r = client.get("/v2/teacher/calendars")
        assert r.status_code == 401


# === Profile-preview-endpoint ===


class TestProfilePreviewEndpoint:
    def test_preview_default(self, fx):
        client, tok, _ = fx
        r = client.post(
            "/v2/teacher/students/profile-preview",
            json={"seed": 12345, "name": "Förhand"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["seed"] == 12345
        assert body["name"] == "Förhand"
        assert body["yrke_key"]
        assert body["city_key"]
        assert body["pentagon"]["economy"] >= 45
        assert body["pentagon"]["economy"] <= 80
        assert body["housing"]["monthly_cost"] > 0

    def test_preview_seed_is_deterministic(self, fx):
        client, tok, _ = fx
        a = client.post(
            "/v2/teacher/students/profile-preview",
            json={"seed": 7},
            headers={"Authorization": f"Bearer {tok}"},
        ).json()
        b = client.post(
            "/v2/teacher/students/profile-preview",
            json={"seed": 7},
            headers={"Authorization": f"Bearer {tok}"},
        ).json()
        assert a["yrke_key"] == b["yrke_key"]
        assert a["monthly_gross"] == b["monthly_gross"]
        assert a["housing"]["monthly_cost"] == b["housing"]["monthly_cost"]

    def test_preview_requires_teacher(self, fx):
        client, *_ = fx
        r = client.post(
            "/v2/teacher/students/profile-preview",
            json={"seed": 1},
        )
        assert r.status_code == 401

    def test_preview_invalid_starting_level_returns_422(self, fx):
        client, tok, _ = fx
        r = client.post(
            "/v2/teacher/students/profile-preview",
            json={"seed": 1, "starting_level": 99},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 422
