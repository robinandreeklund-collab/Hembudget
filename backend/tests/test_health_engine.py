"""Tester för game_engine.health_engine: sjuk + VAB + lönepåverkan."""
from __future__ import annotations

from pathlib import Path

import pytest


class TestSickPayCalculation:
    def test_one_day_is_karens_only(self):
        from hembudget.game_engine.health_engine import apply_sick_pay_reduction
        loss, b = apply_sick_pay_reduction(monthly_gross=35000, sick_days=1)
        assert loss > 0
        assert b["karens"] > 0
        assert b["dag2_14"] == 0
        assert b["dag15_plus"] == 0

    def test_five_days_includes_dag2_14(self):
        from hembudget.game_engine.health_engine import apply_sick_pay_reduction
        loss, b = apply_sick_pay_reduction(monthly_gross=35000, sick_days=5)
        assert b["karens"] > 0
        assert b["dag2_14"] > 0
        assert b["dag15_plus"] == 0

    def test_long_sick_includes_dag15_plus(self):
        from hembudget.game_engine.health_engine import apply_sick_pay_reduction
        loss, b = apply_sick_pay_reduction(monthly_gross=35000, sick_days=30)
        assert b["dag15_plus"] > 0

    def test_high_earner_dag15_capped_by_sgi(self):
        """80 % av 100k brutto = 80k men FK-tak 1209 kr/dag → mer förlust."""
        from hembudget.game_engine.health_engine import apply_sick_pay_reduction
        normal_loss, _ = apply_sick_pay_reduction(monthly_gross=35000, sick_days=20)
        high_loss, _ = apply_sick_pay_reduction(monthly_gross=100000, sick_days=20)
        # Höglönare ska förlora MER (relativt) pga taket
        assert high_loss > normal_loss

    def test_vab_no_karens(self):
        from hembudget.game_engine.health_engine import apply_sick_pay_reduction
        loss_sick, b_sick = apply_sick_pay_reduction(
            monthly_gross=30000, sick_days=3, is_vab=False,
        )
        loss_vab, b_vab = apply_sick_pay_reduction(
            monthly_gross=30000, sick_days=3, is_vab=True,
        )
        assert b_vab["karens"] == 0
        # Vid VAB är förlusten mindre dag 1 (ingen karens)
        assert loss_vab < loss_sick

    def test_zero_days_no_loss(self):
        from hembudget.game_engine.health_engine import apply_sick_pay_reduction
        loss, _ = apply_sick_pay_reduction(monthly_gross=30000, sick_days=0)
        assert loss == 0


class TestRollMonthlyHealthEvents:
    def test_winter_higher_sick_probability_than_summer(self):
        """Statistisk: jan ska ha fler sjukmånader än juli över 100 körningar."""
        from unittest.mock import MagicMock
        from hembudget.game_engine.health_engine.roller import (
            _roll_sick_episodes,
        )
        from hembudget.game_engine.profile_generator import generate_profile
        import random

        profile = generate_profile(seed=42)

        winter = sum(
            1 for s in range(200)
            if _roll_sick_episodes(
                random.Random(s), profile=profile, year_month="2026-01",
            )
        )
        summer = sum(
            1 for s in range(200)
            if _roll_sick_episodes(
                random.Random(s), profile=profile, year_month="2026-07",
            )
        )
        assert winter > summer, f"Winter {winter} ej > summer {summer}"

    def test_no_vab_when_no_kids(self):
        from hembudget.game_engine.health_engine.roller import _roll_vab_episodes
        from hembudget.game_engine.profile_generator import generate_profile
        import random

        # Solo-profil = inga barn
        profile = generate_profile(seed=42, partner_model="solo")
        for seed in range(100):
            episodes = _roll_vab_episodes(
                random.Random(seed), profile=profile, year_month="2026-01",
            )
            assert episodes == []

    def test_vab_only_for_kids_under_12(self):
        """VAB triggas bara för barn < 12."""
        from hembudget.game_engine.health_engine.roller import _roll_vab_episodes
        from hembudget.game_engine.profile_generator.schema import (
            FamilyChoice, GeneratedProfile, HousingChoice, PentagonInit,
        )
        import random

        # Bygg profil med ETT 16-årigt barn
        profile = GeneratedProfile(
            seed=1, name="X", yrke_key="okand", yrke_display="X", yrke_ssyk="0",
            monthly_gross=30000, monthly_net=22000,
            city_key="medelstad", city_display="X", region="Östra Mellansverige",
            housing=HousingChoice(type="hyresratt", size_kvm=30, monthly_cost=8000),
            family=FamilyChoice(
                status="familj_med_barn", partner_model="ai",
                partner_yrke_key="okand", partner_gross_monthly=25000,
                children_count=1, children_ages=[16],
            ),
            household_gross_monthly=55000, household_net_monthly=42000,
            pentagon=PentagonInit(economy=60, safety=60, health=60, social=60, leisure=60),
            facts={"age": 35, "physical_demand": 5},
        )
        # Ingen VAB ska genereras (barn är 16)
        for seed in range(100):
            ep = _roll_vab_episodes(
                random.Random(seed), profile=profile, year_month="2026-01",
            )
            assert ep == []


class TestMonthlyEngineHealthIntegration:
    @pytest.fixture
    def fx(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
        main_mod.build_app()
        from hembudget.school.engines import init_master_engine, master_session
        from hembudget.school.models import Teacher, Student
        from hembudget.security.crypto import hash_password
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
        return tid, sid

    def test_tick_includes_health_summary(self, fx):
        from hembudget.game_engine.monthly_engine import tick_month
        from hembudget.game_engine.profile_generator import generate_profile
        from hembudget.school.engines import master_session
        from hembudget.school.models import Student

        _, sid = fx
        with master_session() as s:
            stu = s.get(Student, sid); s.expunge(stu)
        profile = generate_profile(seed=42)
        result = tick_month(stu, profile, "2026-01")
        assert "health" in result.summary
        h = result.summary["health"]
        assert "episodes" in h
        assert "by_episode" in h

    def test_employer_satisfaction_logged_after_sick(self, fx):
        """Säkerställ att EmployerSatisfactionEvent loggas för sjuk-events."""
        from hembudget.db.models import Account
        from hembudget.game_engine.health_engine import apply_health_episode
        from hembudget.game_engine.health_engine.roller import (
            SHORT_SICK_TEMPLATES,
        )
        from hembudget.game_engine.profile_generator import generate_profile
        from hembudget.school.engines import (
            get_scope_session, master_session, scope_context, scope_for_student,
        )
        from hembudget.school.employer_models import EmployerSatisfactionEvent
        from hembudget.school.models import Student
        import random
        from decimal import Decimal

        _, sid = fx
        with master_session() as s:
            stu = s.get(Student, sid); s.expunge(stu)
        scope_key = scope_for_student(stu)
        profile = generate_profile(seed=42)
        maker = get_scope_session(scope_key)

        with scope_context(scope_key):
            with maker() as s:
                acc = Account(
                    name="Lk", bank="X", type="checking",
                    opening_balance=Decimal(50000),
                )
                s.add(acc); s.commit()
                apply_health_episode(
                    s,
                    student_id=sid,
                    student_scope=scope_key,
                    profile=profile,
                    template=SHORT_SICK_TEMPLATES[0],
                    n_days=5,
                    year_month="2026-02",
                    rng=random.Random(1),
                    salary_account=acc,
                )
                s.commit()

        with master_session() as s:
            events = (
                s.query(EmployerSatisfactionEvent)
                .filter(EmployerSatisfactionEvent.student_id == sid)
                .all()
            )
            assert len(events) >= 1
            assert events[0].kind == "sick"
            assert events[0].delta_score < 0  # negativ effekt
