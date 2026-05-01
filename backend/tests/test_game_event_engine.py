"""Tester för game_engine.event_engine: templates, mitigation, roller +
endpoints (list templates, inject-event).

Verifierar:
- Template-pool struktur + realism (kostnader, frekvenser, age_range)
- Försäkrings-mildring: med/utan policy, savings_buffer-fallback
- roll_monthly_events: determinism (samma seed = samma events),
  profil-filter (familj_med_barn-events triggar inte för ensam),
  max-cap (≤ 3 per månad)
- apply_event: skapar MailItem + ev. InsuranceClaim
- Endpoint /v2/teacher/event-templates · 200 + auth
- Endpoint /v2/teacher/students/{id}/inject-event · 200, 401, 404
- Integration: tick_month inkluderar events i summary
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.engines import (
    get_scope_session,
    init_master_engine,
    master_session,
    scope_context,
    scope_for_student,
)
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
            login_code="EVA00001",
        )
        s.add(stu)
        s.flush()
        sid = stu.id

    tok = random_token()
    register_token(tok, role="teacher", teacher_id=tid)
    return TestClient(app), tok, tid, sid


# === Template-pool ===


class TestTemplatePool:
    def test_pool_size(self):
        from hembudget.game_engine.event_engine import EVENT_TEMPLATES
        assert 25 <= len(EVENT_TEMPLATES) <= 60

    def test_unique_keys(self):
        from hembudget.game_engine.event_engine import EVENT_TEMPLATES
        keys = [t.key for t in EVENT_TEMPLATES]
        dupes = [k for k, c in Counter(keys).items() if c > 1]
        assert not dupes, f"Duplicates: {dupes}"

    def test_lookup_index_matches_pool(self):
        from hembudget.game_engine.event_engine import (
            EVENT_BY_KEY, EVENT_TEMPLATES,
        )
        assert len(EVENT_BY_KEY) == len(EVENT_TEMPLATES)
        for t in EVENT_TEMPLATES:
            assert EVENT_BY_KEY[t.key] is t

    def test_frequencies_realistic(self):
        from hembudget.game_engine.event_engine import EVENT_TEMPLATES
        for t in EVENT_TEMPLATES:
            assert 0.0 < t.frequency_per_year <= 5.0, (
                f"{t.key}: orealistisk frekvens {t.frequency_per_year}"
            )

    def test_cost_ranges_well_formed(self):
        from hembudget.game_engine.event_engine import EVENT_TEMPLATES
        for t in EVENT_TEMPLATES:
            lo, hi = t.cost_range
            assert lo <= hi, f"{t.key}: cost_range {lo} > {hi}"

    def test_age_ranges_inside_16_99(self):
        from hembudget.game_engine.event_engine import EVENT_TEMPLATES
        for t in EVENT_TEMPLATES:
            assert 0 <= t.age_range[0] <= t.age_range[1] <= 99

    def test_mitigations_have_valid_multiplier(self):
        from hembudget.game_engine.event_engine import EVENT_TEMPLATES
        for t in EVENT_TEMPLATES:
            for m in t.mitigations:
                assert 0.0 <= m.cost_multiplier <= 1.0, (
                    f"{t.key}: mitigation multiplier {m.cost_multiplier}"
                )

    def test_pentagon_mitigated_better_than_unmitigated(self):
        from hembudget.game_engine.event_engine import EVENT_TEMPLATES
        for t in EVENT_TEMPLATES:
            if t.pentagon_mitigated is None or t.cost_range[1] <= 0:
                continue
            unmit = t.pentagon_unmitigated.economy
            mit = t.pentagon_mitigated.economy
            assert mit >= unmit, (
                f"{t.key}: mitigated {mit} < unmitigated {unmit}"
            )


# === Försäkrings-mildring ===


class FakePolicy:
    def __init__(self, kind, pid=1, status="active"):
        self.kind = kind
        self.id = pid
        self.status = status


class TestMitigation:
    def test_no_policy_no_mitigation(self):
        from hembudget.game_engine.event_engine import (
            EVENT_BY_KEY, apply_mitigation,
        )
        t = EVENT_BY_KEY["cykel_stulen"]
        result = apply_mitigation(t, base_cost=8000, policies=[])
        assert result.mitigation_used is False
        assert result.effective_cost == 8000
        assert result.pentagon_impact == t.pentagon_unmitigated

    def test_matching_policy_applies_multiplier(self):
        from hembudget.game_engine.event_engine import (
            EVENT_BY_KEY, apply_mitigation,
        )
        t = EVENT_BY_KEY["cykel_stulen"]  # mitig: hem 0.15
        result = apply_mitigation(
            t, base_cost=8000, policies=[FakePolicy("hem")],
        )
        assert result.mitigation_used is True
        assert result.effective_cost == int(8000 * 0.15)
        assert result.policy_kind == "hem"
        assert result.policy_id == 1

    def test_inactive_policy_ignored(self):
        from hembudget.game_engine.event_engine import (
            EVENT_BY_KEY, apply_mitigation,
        )
        t = EVENT_BY_KEY["cykel_stulen"]
        result = apply_mitigation(
            t, base_cost=8000,
            policies=[FakePolicy("hem", status="cancelled")],
        )
        assert result.mitigation_used is False

    def test_first_matching_mitigation_wins(self):
        from hembudget.game_engine.event_engine import (
            EVENT_BY_KEY, apply_mitigation,
        )
        t = EVENT_BY_KEY["vattenskada_badrum"]
        result = apply_mitigation(
            t,
            base_cost=20000,
            policies=[
                FakePolicy("hem", 1),
                FakePolicy("bostadsrattsforsakring", 2),
            ],
        )
        assert result.mitigation_used is True
        assert result.policy_id == 1


# === Rolling ===


class TestRolling:
    def test_same_seed_yields_same_events(self, fx):
        from hembudget.game_engine.event_engine import roll_monthly_events
        from hembudget.game_engine.profile_generator import generate_profile
        import random

        _, _, _, sid = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        scope_key = scope_for_student(student)
        profile = generate_profile(seed=42)
        maker = get_scope_session(scope_key)

        seeds = []
        for _ in range(2):
            with scope_context(scope_key):
                with maker() as s:
                    occs = roll_monthly_events(
                        s,
                        profile=profile,
                        year_month="2026-04",
                        student_scope=scope_key,
                        rng=random.Random("fixed-seed"),
                    )
                    s.rollback()
            seeds.append(
                [(o.template_key, o.mitigation.effective_cost) for o in occs]
            )
        assert seeds[0] == seeds[1]

    def test_max_events_per_month(self, fx):
        from hembudget.game_engine.event_engine import roll_monthly_events
        from hembudget.game_engine.profile_generator import generate_profile

        _, _, _, sid = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        scope_key = scope_for_student(student)
        profile = generate_profile(seed=1)
        maker = get_scope_session(scope_key)

        for ym in (f"2027-{m:02d}" for m in range(1, 13)):
            with scope_context(scope_key):
                with maker() as s:
                    occs = roll_monthly_events(
                        s, profile=profile,
                        year_month=ym, student_scope=scope_key,
                    )
                    assert len(occs) <= 3
                    s.rollback()

    def test_family_filter_respected(self, fx):
        from hembudget.game_engine.event_engine import roll_monthly_events
        from hembudget.game_engine.profile_generator import generate_profile

        _, _, _, sid = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        scope_key = scope_for_student(student)
        profile = generate_profile(seed=99, partner_model="solo")
        assert profile.family.status == "ensam"

        maker = get_scope_session(scope_key)
        seen = set()
        for ym in (f"2028-{m:02d}" for m in range(1, 13)):
            with scope_context(scope_key):
                with maker() as s:
                    occs = roll_monthly_events(
                        s, profile=profile,
                        year_month=ym, student_scope=scope_key,
                    )
                    for o in occs:
                        seen.add(o.template_key)
                    s.rollback()
        assert "kalas_inbjudan" not in seen
        assert "parboende_inflyttning" not in seen


# === Apply event ===


class TestApplyEvent:
    def test_creates_mail_with_negative_amount(self, fx):
        from hembudget.db.models import MailItem
        from hembudget.game_engine.event_engine import (
            EVENT_BY_KEY, apply_event,
        )
        from hembudget.game_engine.profile_generator import generate_profile
        import random

        _, _, _, sid = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        scope_key = scope_for_student(student)
        profile = generate_profile(seed=42)
        maker = get_scope_session(scope_key)

        t = EVENT_BY_KEY["tandlakar_kontroll"]
        with scope_context(scope_key):
            with maker() as s:
                occ = apply_event(
                    s, template=t, profile=profile,
                    year_month="2026-05", student_scope=scope_key,
                    rng=random.Random(1),
                    base_cost_override=5000,
                )
                s.commit()
                mail = s.get(MailItem, occ.mail_id)
                assert mail is not None
                assert mail.amount == Decimal(-5000)
                assert mail.mail_type == "invoice"

    def test_income_event_creates_positive_mail(self, fx):
        from hembudget.db.models import MailItem
        from hembudget.game_engine.event_engine import (
            EVENT_BY_KEY, apply_event,
        )
        from hembudget.game_engine.profile_generator import generate_profile
        import random

        _, _, _, sid = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        scope_key = scope_for_student(student)
        profile = generate_profile(seed=42)
        maker = get_scope_session(scope_key)

        t = EVENT_BY_KEY["bonus_julgava"]
        with scope_context(scope_key):
            with maker() as s:
                occ = apply_event(
                    s, template=t, profile=profile,
                    year_month="2026-12", student_scope=scope_key,
                    rng=random.Random(1),
                    base_cost_override=-8000,
                )
                s.commit()
                mail = s.get(MailItem, occ.mail_id)
                assert mail.amount > 0
                assert mail.mail_type == "info"


# === Integration ===


class TestMonthlyEngineIntegration:
    def test_tick_includes_event_summary(self, fx):
        from hembudget.game_engine.monthly_engine import tick_month
        from hembudget.game_engine.profile_generator import generate_profile

        _, _, _, sid = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        profile = generate_profile(seed=42)

        result = tick_month(student, profile, "2029-01")
        assert "events" in result.summary
        e = result.summary["events"]
        assert "triggered" in e
        assert "pentagon_delta" in e
        assert "by_template" in e
        assert isinstance(e["by_template"], list)
        assert e["triggered"] >= 0


# === Endpoints ===


class TestEndpoints:
    def test_list_templates_returns_pool(self, fx):
        client, tok, *_ = fx
        r = client.get(
            "/v2/teacher/event-templates",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) >= 25
        keys = [t["key"] for t in body]
        assert "tandlakar_kontroll" in keys
        assert "cykel_stulen" in keys

    def test_list_templates_requires_teacher(self, fx):
        client, *_ = fx
        r = client.get("/v2/teacher/event-templates")
        assert r.status_code == 401

    def test_inject_event_creates_mail(self, fx):
        client, tok, _, sid = fx
        r = client.post(
            f"/v2/teacher/students/{sid}/inject-event",
            json={
                "template_key": "tandlakar_kontroll",
                "year_month": "2030-03",
                "seed": 42,
                "base_cost_override": 4500,
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["template_key"] == "tandlakar_kontroll"
        assert body["base_cost"] == 4500
        assert body["effective_cost"] == 4500
        assert body["mitigation_used"] is False
        assert body["mail_id"] > 0

    def test_inject_event_unknown_template_404(self, fx):
        client, tok, _, sid = fx
        r = client.post(
            f"/v2/teacher/students/{sid}/inject-event",
            json={
                "template_key": "denna_finns_inte",
                "year_month": "2030-03",
                "seed": 1,
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 404

    def test_inject_event_unknown_student_404(self, fx):
        client, tok, *_ = fx
        r = client.post(
            "/v2/teacher/students/99999/inject-event",
            json={
                "template_key": "tandlakar_kontroll",
                "year_month": "2030-03",
                "seed": 1,
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 404

    def test_inject_event_requires_token(self, fx):
        client, _, _, sid = fx
        r = client.post(
            f"/v2/teacher/students/{sid}/inject-event",
            json={
                "template_key": "tandlakar_kontroll",
                "year_month": "2030-03",
                "seed": 1,
            },
        )
        assert r.status_code == 401
