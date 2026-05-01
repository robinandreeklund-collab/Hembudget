"""Tester för game_engine.monthly_engine: salary + fixed + variable +
orchestrator + advance-month-endpoint.

Verifierar:
- Salary phase skapar lönespec-MailItem + lön-in-Transaction
- Fixed expenses ger 5-7 items spridda över dag 1-10 med rätt belopp
- Variable expenses respekterar Konsumentverket × spend_profile-multiplikator
- Orchestrator är idempotent (re-tick = skipped)
- WeekTickRun loggar status, seed_used, summary, completed_at
- Endpoint kräver lärar-token + 404 för okänd elev
- Tick history listar runs i fallande ym-ordning
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.engines import (
    init_master_engine,
    master_session,
    scope_context,
    scope_for_student,
    get_scope_session,
)
from hembudget.school.game_engine_models import WeekTickRun
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
            teacher_id=tid, display_name="Eva Test",
            login_code="EVA00001",
        )
        s.add(stu)
        s.flush()
        sid = stu.id

    tok = random_token()
    register_token(tok, role="teacher", teacher_id=tid)
    return TestClient(app), tok, tid, sid


# === Salary phase ===


class TestSalaryPhase:
    def test_creates_mail_and_transaction(self, fx):
        from hembudget.db.models import MailItem, Transaction
        from hembudget.game_engine.monthly_engine.salary_phase import (
            generate_salary_phase,
        )
        from hembudget.game_engine.monthly_engine.scope_seed import (
            ensure_scope_accounts,
        )
        from hembudget.game_engine.profile_generator import generate_profile

        _, _, _, sid = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        scope_key = scope_for_student(student)
        profile = generate_profile(seed=42)
        maker = get_scope_session(scope_key)

        with scope_context(scope_key):
            with maker() as s:
                accounts = ensure_scope_accounts(s, profile)
                summary = generate_salary_phase(
                    s,
                    profile=profile,
                    year_month="2026-03",
                    salary_account=accounts["lonekonto"],
                    student_scope=scope_key,
                    student_name="Eva Test",
                )
                s.commit()
                mails = s.query(MailItem).filter(
                    MailItem.mail_type == "salary_slip",
                ).all()
                txs = s.query(Transaction).all()

        assert summary["total_net_credited"] == profile.monthly_net
        assert len(mails) == 1
        assert mails[0].amount == Decimal(profile.monthly_net)
        assert mails[0].due_date == date(2026, 3, 25)
        assert len(txs) == 1
        assert txs[0].amount == Decimal(profile.monthly_net)


# === Fixed expenses ===


class TestFixedExpenses:
    def test_staggered_invoices_created(self, fx):
        from hembudget.db.models import MailItem
        from hembudget.game_engine.monthly_engine.fixed_expenses import (
            generate_fixed_expenses,
        )
        from hembudget.game_engine.profile_generator import generate_profile

        _, _, _, sid = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        scope_key = scope_for_student(student)
        profile = generate_profile(seed=42)
        maker = get_scope_session(scope_key)

        with scope_context(scope_key):
            with maker() as s:
                summary = generate_fixed_expenses(
                    s,
                    profile=profile,
                    year_month="2026-04",
                    student_scope=scope_key,
                )
                s.commit()
                invoices = s.query(MailItem).filter(
                    MailItem.mail_type == "invoice",
                ).all()

        assert summary["items_created"] >= 5
        assert summary["total_amount"] > 0
        assert len(invoices) == summary["items_created"]
        # Invoice-belopp är negativa
        for inv in invoices:
            assert inv.amount < 0
            assert inv.due_date is not None
            assert inv.due_date.month == 4
        # Inte alla på samma dag (staggered)
        days = {inv.due_date.day for inv in invoices}
        assert len(days) >= 4, f"För få unika dagar: {days}"


# === Variable expenses ===


class TestVariableExpenses:
    def test_spend_profile_affects_total(self, fx):
        from hembudget.game_engine.monthly_engine.scope_seed import (
            ensure_scope_accounts,
        )
        from hembudget.game_engine.monthly_engine.variable_expenses import (
            generate_variable_expenses,
        )
        from hembudget.game_engine.profile_generator import generate_profile

        _, _, _, sid = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        scope_key = scope_for_student(student)
        profile = generate_profile(seed=42)
        maker = get_scope_session(scope_key)

        # Kör tre månader (olika ym) med olika profile för att jämföra
        totals = {}
        for spend in ("sparsam", "balanserad", "slosa"):
            ym = {"sparsam": "2026-05", "balanserad": "2026-06", "slosa": "2026-07"}[spend]
            with scope_context(scope_key):
                with maker() as s:
                    accounts = ensure_scope_accounts(s, profile)
                    summary = generate_variable_expenses(
                        s,
                        profile=profile,
                        year_month=ym,
                        salary_account=accounts["lonekonto"],
                        student_scope=scope_key,
                        spend_profile=spend,
                        starting_level=1,
                    )
                    s.commit()
                    totals[spend] = summary["total_amount"]

        assert totals["sparsam"] < totals["balanserad"] < totals["slosa"], totals

    def test_transactions_distributed_across_month(self, fx):
        from hembudget.db.models import Transaction
        from hembudget.game_engine.monthly_engine.scope_seed import (
            ensure_scope_accounts,
        )
        from hembudget.game_engine.monthly_engine.variable_expenses import (
            generate_variable_expenses,
        )
        from hembudget.game_engine.profile_generator import generate_profile

        _, _, _, sid = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        scope_key = scope_for_student(student)
        profile = generate_profile(seed=42)
        maker = get_scope_session(scope_key)

        with scope_context(scope_key):
            with maker() as s:
                accounts = ensure_scope_accounts(s, profile)
                generate_variable_expenses(
                    s,
                    profile=profile,
                    year_month="2026-08",
                    salary_account=accounts["lonekonto"],
                    student_scope=scope_key,
                )
                s.commit()
                txs = s.query(Transaction).filter(
                    Transaction.amount < 0,
                ).all()

        assert len(txs) >= 10
        days = {t.date.day for t in txs}
        # Spridning över minst 5 olika dagar i månaden
        assert len(days) >= 5, f"Variabla utgifter bara på {days}"


# === Orchestrator + idempotens ===


class TestOrchestrator:
    def test_tick_month_creates_run_and_data(self, fx):
        from hembudget.db.models import MailItem, Transaction
        from hembudget.game_engine.monthly_engine import tick_month
        from hembudget.game_engine.profile_generator import generate_profile

        _, _, _, sid = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        scope_key = scope_for_student(student)
        profile = generate_profile(seed=42)

        result = tick_month(student, profile, "2026-09")

        assert result.skipped is False
        assert result.summary["salary"]["total_net_credited"] > 0
        assert result.summary["fixed"]["items_created"] >= 5
        assert result.summary["variable"]["transactions_created"] >= 10

        with master_session() as s:
            run = s.query(WeekTickRun).filter(
                WeekTickRun.student_id == sid,
                WeekTickRun.year_month == "2026-09",
            ).one()
            assert run.status == "completed"
            assert run.seed_used == 42
            assert run.completed_at is not None

        maker = get_scope_session(scope_key)
        with scope_context(scope_key):
            with maker() as s:
                mails = s.query(MailItem).all()
                txs = s.query(Transaction).all()
        assert len(mails) >= 6  # 1 salary + 5+ invoices
        assert len(txs) >= 11  # 1 salary + 10+ variable

    def test_re_tick_is_skipped(self, fx):
        from hembudget.db.models import Transaction
        from hembudget.game_engine.monthly_engine import tick_month
        from hembudget.game_engine.profile_generator import generate_profile

        _, _, _, sid = fx
        with master_session() as s:
            student = s.get(Student, sid)
            s.expunge(student)
        scope_key = scope_for_student(student)
        profile = generate_profile(seed=42)

        tick_month(student, profile, "2026-10")
        maker = get_scope_session(scope_key)
        with scope_context(scope_key):
            with maker() as s:
                first_count = s.query(Transaction).count()

        result2 = tick_month(student, profile, "2026-10")
        assert result2.skipped is True

        with scope_context(scope_key):
            with maker() as s:
                second_count = s.query(Transaction).count()
        assert second_count == first_count, "Idempotens bröts: nya rader skapades vid re-tick"


# === Endpoint /v2/teacher/students/{id}/advance-month ===


class TestAdvanceEndpoint:
    def test_advance_returns_summary(self, fx):
        client, tok, _, sid = fx
        r = client.post(
            f"/v2/teacher/students/{sid}/advance-month",
            json={"year_month": "2026-11", "seed": 100},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["skipped"] is False
        assert body["year_month"] == "2026-11"
        assert "salary" in body["summary"]
        assert "fixed" in body["summary"]
        assert "variable" in body["summary"]

    def test_advance_idempotent(self, fx):
        client, tok, _, sid = fx
        url = f"/v2/teacher/students/{sid}/advance-month"
        body = {"year_month": "2026-12", "seed": 5}
        r1 = client.post(url, json=body, headers={"Authorization": f"Bearer {tok}"})
        r2 = client.post(url, json=body, headers={"Authorization": f"Bearer {tok}"})
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["skipped"] is False
        assert r2.json()["skipped"] is True

    def test_advance_requires_teacher_token(self, fx):
        client, *_ = fx
        r = client.post(
            "/v2/teacher/students/999/advance-month",
            json={"year_month": "2026-01", "seed": 1},
        )
        assert r.status_code == 401

    def test_advance_404_unknown_student(self, fx):
        client, tok, *_ = fx
        r = client.post(
            "/v2/teacher/students/99999/advance-month",
            json={"year_month": "2026-01", "seed": 1},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 404

    def test_tick_history_lists_runs_desc(self, fx):
        client, tok, _, sid = fx
        # Tick:a tre månader
        for ym in ("2027-01", "2027-02", "2027-03"):
            client.post(
                f"/v2/teacher/students/{sid}/advance-month",
                json={"year_month": ym, "seed": 42},
                headers={"Authorization": f"Bearer {tok}"},
            )
        r = client.get(
            f"/v2/teacher/students/{sid}/tick-history",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200
        rows = r.json()
        assert [x["year_month"] for x in rows] == ["2027-03", "2027-02", "2027-01"]
        for row in rows:
            assert row["status"] == "completed"
            assert row["seed_used"] == 42

    def test_invalid_year_month_rejected(self, fx):
        client, tok, _, sid = fx
        r = client.post(
            f"/v2/teacher/students/{sid}/advance-month",
            json={"year_month": "26-1", "seed": 1},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 422
