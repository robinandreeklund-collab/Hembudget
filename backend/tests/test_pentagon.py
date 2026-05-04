"""Tester för game_engine.pentagon: drift_calculator, momentum + tröghet,
WellbeingEvent-logg, snabbspola-endpoints (advance-months, advance-class)
och pentagon-history-endpoint.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.engines import (
    init_master_engine,
    master_session,
)
from hembudget.school.game_engine_models import WellbeingEvent
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
            email="t@s.se", name="T",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(t)
        s.flush()
        tid = t.id
        stu = Student(
            teacher_id=tid, display_name="Eva",
            login_code="EVA00001", class_label="8A",
        )
        s.add(stu)
        s.flush()
        sid = stu.id
        # Andra elev i samma klass
        stu2 = Student(
            teacher_id=tid, display_name="Filip",
            login_code="FIL00001", class_label="8A",
        )
        s.add(stu2)
        s.flush()
        sid2 = stu2.id

    tok = random_token()
    register_token(tok, role="teacher", teacher_id=tid)
    return TestClient(app), tok, tid, sid, sid2


# === P1 · Tröghet (momentum) ===


class FakeHistoryEvent:
    def __init__(self, axis, occurred_at, delta):
        self.axis = axis
        self.occurred_at = occurred_at
        self.delta = delta


class TestMomentum:
    def test_clamp_per_event(self):
        from hembudget.game_engine.pentagon import apply_momentum
        applied = apply_momentum("economy", requested_delta=20, history=[])
        assert applied == 5
        applied = apply_momentum("economy", requested_delta=-15, history=[])
        assert applied == -5

    def test_clamp_per_24h(self):
        """Om eleven redan fått +6 senaste 24h kan hen bara få +2 till."""
        from hembudget.game_engine.pentagon import apply_momentum
        now = datetime.utcnow()
        history = [
            FakeHistoryEvent("health", now - timedelta(hours=2), +4),
            FakeHistoryEvent("health", now - timedelta(hours=10), +2),
        ]
        applied = apply_momentum(
            "health", requested_delta=+5, history=history, now=now,
        )
        assert applied == 2  # 8 - 6 = 2

    def test_clamp_per_30d(self):
        """30-dagars-takt klampar mot ±12."""
        from hembudget.game_engine.pentagon import apply_momentum
        now = datetime.utcnow()
        # 11 kr ackumulerat senaste 30 d (utanför 24h så bara 30d gäller)
        history = [
            FakeHistoryEvent("safety", now - timedelta(days=5), +5),
            FakeHistoryEvent("safety", now - timedelta(days=10), +4),
            FakeHistoryEvent("safety", now - timedelta(days=20), +2),
        ]
        applied = apply_momentum("safety", +5, history, now=now)
        assert applied == 1  # 12 - 11 = 1

    def test_independent_axes(self):
        """Klampning sker per axel — 24h-kvoten på health påverkar inte safety."""
        from hembudget.game_engine.pentagon import apply_momentum
        now = datetime.utcnow()
        history = [FakeHistoryEvent("health", now - timedelta(hours=2), +8)]
        applied = apply_momentum("safety", +5, history, now=now)
        assert applied == 5

    def test_negative_direction_independent(self):
        from hembudget.game_engine.pentagon import apply_momentum
        now = datetime.utcnow()
        # Eleven har redan -7 senaste 24h
        history = [FakeHistoryEvent("economy", now - timedelta(hours=3), -7)]
        # Försöker dra ytterligare -5 — får bara -1 till (-7-1=-8)
        applied = apply_momentum("economy", -5, history, now=now)
        assert applied == -1


# === M4 · Drift calculator ===


class TestDriftCalculator:
    def test_drift_returns_axes_within_clamp(self, fx):
        """Drift ska aldrig vara större än ±5 per axel."""
        from hembudget.game_engine.monthly_engine import tick_month
        from hembudget.game_engine.pentagon import compute_monthly_drift
        from hembudget.game_engine.profile_generator import generate_profile
        from hembudget.school.engines import (
            get_scope_session, scope_context, scope_for_student,
        )

        _, _, _, sid, _ = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        scope_key = scope_for_student(student)
        profile = generate_profile(seed=42)

        # Tick en månad så scope-DB:n får lön + utgifter
        tick_month(student, profile, "2026-01")

        maker = get_scope_session(scope_key)
        with scope_context(scope_key):
            with maker() as s:
                drift = compute_monthly_drift(s, year_month="2026-01")

        for axis in ("economy", "safety", "health", "social", "leisure"):
            assert -5 <= drift.deltas[axis] <= 5, (
                f"{axis}: {drift.deltas[axis]} utanför ±5"
            )

    def test_drift_explanations_attached(self, fx):
        from hembudget.game_engine.monthly_engine import tick_month
        from hembudget.game_engine.pentagon import compute_monthly_drift
        from hembudget.game_engine.profile_generator import generate_profile
        from hembudget.school.engines import (
            get_scope_session, scope_context, scope_for_student,
        )

        _, _, _, sid, _ = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        scope_key = scope_for_student(student)
        profile = generate_profile(seed=42)
        tick_month(student, profile, "2026-02")

        maker = get_scope_session(scope_key)
        with scope_context(scope_key):
            with maker() as s:
                drift = compute_monthly_drift(s, year_month="2026-02")

        # Minst en axel ska ha en förklaring (eleven har handlat något)
        all_explanations = sum((v for v in drift.explanations.values()), [])
        assert any(all_explanations), "Inga drift-förklaringar genererades"


# === P2 · WellbeingEvent-logg ===


class TestWellbeingLog:
    def test_apply_pentagon_delta_logs_row(self, fx):
        from hembudget.game_engine.pentagon import apply_pentagon_delta
        _, _, _, sid, _ = fx
        applied, new_value = apply_pentagon_delta(
            sid,
            axis="health",
            requested_delta=+3,
            reason_kind="event",
            explanation="testfall",
        )
        assert applied == 3
        assert new_value == 63  # default 60 + 3
        with master_session() as s:
            row = (
                s.query(WellbeingEvent)
                .filter(WellbeingEvent.student_id == sid)
                .first()
            )
            assert row is not None
            assert row.axis == "health"
            assert row.applied_delta == 3
            assert row.new_value == 63
            assert row.reason_kind == "event"

    def test_apply_pentagon_delta_clamps(self, fx):
        from hembudget.game_engine.pentagon import apply_pentagon_delta
        _, _, _, sid, _ = fx
        # Försök +20 → klampas till +5
        applied, new_value = apply_pentagon_delta(
            sid, axis="economy", requested_delta=+20, reason_kind="event",
        )
        assert applied == 5
        assert new_value == 65

    def test_value_persists_across_calls(self, fx):
        from hembudget.game_engine.pentagon import apply_pentagon_delta
        _, _, _, sid, _ = fx
        apply_pentagon_delta(sid, axis="social", requested_delta=+4, reason_kind="event")
        # Andra anropet startar från nya värdet 64
        applied, new_value = apply_pentagon_delta(
            sid, axis="social", requested_delta=+3, reason_kind="event",
        )
        assert new_value == 64 + 3

    def test_history_endpoint_returns_rows(self, fx):
        from hembudget.game_engine.monthly_engine import tick_month
        from hembudget.game_engine.profile_generator import generate_profile
        client, tok, _, sid, _ = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        profile = generate_profile(seed=42)
        tick_month(student, profile, "2026-01")

        r = client.get(
            f"/v2/teacher/students/{sid}/pentagon-history",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 1
        for row in rows:
            assert row["axis"] in ("economy", "safety", "health", "social", "leisure")
            assert row["reason_kind"] in ("drift", "event", "decision", "init", "goal_achieved")


# === Integration: Monthly Engine inkluderar pentagon-fas ===


class TestPentagonInMonthlyEngine:
    def test_tick_includes_pentagon_summary(self, fx):
        from hembudget.game_engine.monthly_engine import tick_month
        from hembudget.game_engine.profile_generator import generate_profile

        _, _, _, sid, _ = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        profile = generate_profile(seed=42)

        result = tick_month(student, profile, "2026-01")
        assert "pentagon" in result.summary
        p = result.summary["pentagon"]
        assert "by_axis" in p
        assert "new_values" in p
        for axis in ("economy", "safety", "health", "social", "leisure"):
            assert axis in p["by_axis"]


# === M6 · Snabbspola-endpoints ===


class TestAdvanceEndpoints:
    def test_advance_months_processes_three(self, fx):
        client, tok, _, sid, _ = fx
        r = client.post(
            f"/v2/teacher/students/{sid}/advance-months",
            json={
                "start_year_month": "2026-04",
                "n_months": 3,
                "seed": 42,
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["months_processed"] == 3
        assert body["months_skipped"] == 0
        assert body["last_year_month"] == "2026-06"
        assert len(body["summaries"]) == 3
        for s in body["summaries"]:
            assert "pentagon" in s["summary"]
            assert "events" in s["summary"]
            assert "salary" in s["summary"]

    def test_advance_months_skips_already_ticked(self, fx):
        client, tok, _, sid, _ = fx
        # Tick en månad först
        client.post(
            f"/v2/teacher/students/{sid}/advance-month",
            json={"year_month": "2026-04", "seed": 42},
            headers={"Authorization": f"Bearer {tok}"},
        )
        # Försök snabbspola från samma månad → ska skippa första
        r = client.post(
            f"/v2/teacher/students/{sid}/advance-months",
            json={
                "start_year_month": "2026-04",
                "n_months": 2,
                "seed": 42,
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["months_skipped"] == 1
        assert body["months_processed"] == 1

    def test_advance_months_too_many_rejected(self, fx):
        client, tok, _, sid, _ = fx
        r = client.post(
            f"/v2/teacher/students/{sid}/advance-months",
            json={
                "start_year_month": "2026-04",
                "n_months": 24,
                "seed": 42,
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 422

    def test_advance_months_requires_teacher(self, fx):
        client, _, _, sid, _ = fx
        r = client.post(
            f"/v2/teacher/students/{sid}/advance-months",
            json={
                "start_year_month": "2026-04", "n_months": 1, "seed": 1,
            },
        )
        assert r.status_code == 401

    def test_advance_class_ticks_all_students(self, fx):
        client, tok, tid, sid, sid2 = fx
        # Skapa kalender för klass 8A
        r = client.post(
            "/v2/teacher/calendars",
            json={
                "class_label": "8A",
                "sim_start_year_month": "2026-01",
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        cal_id = r.json()["id"]

        # Snabbspola hela klassen en månad
        r = client.post(
            f"/v2/teacher/calendars/{cal_id}/advance",
            json={"seed_strategy": "per_student"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Båda eleverna i 8A ska ha tickats
        assert body["students_advanced"] == 2
        assert body["students_failed"] == 0
        assert body["sim_year_month_after"] == "2026-01"

    def test_advance_class_paused_returns_400(self, fx):
        client, tok, _, _, _ = fx
        r = client.post(
            "/v2/teacher/calendars",
            json={
                "class_label": "8A",
                "sim_start_year_month": "2026-01",
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        cal_id = r.json()["id"]
        future = (datetime.utcnow() + timedelta(days=30)).isoformat()
        client.post(
            f"/v2/teacher/calendars/{cal_id}/pause",
            json={"paused_until": future},
            headers={"Authorization": f"Bearer {tok}"},
        )
        r = client.post(
            f"/v2/teacher/calendars/{cal_id}/advance",
            json={"seed_strategy": "per_student"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 400

    def test_advance_class_404_other_teacher(self, fx):
        client, tok, _, _, _ = fx
        r = client.post(
            "/v2/teacher/calendars/99999/advance",
            json={"seed_strategy": "per_student"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 404
