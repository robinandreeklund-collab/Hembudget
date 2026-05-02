"""End-to-end test för skapa-elev → verifiera HELA plattformen levererar data.

Denna test simulerar exakt vad användaren gör:
  1. Lärare skapar en ny elev via /v2/teacher/students/create
  2. Verifierar att ALL initial-data faktiskt finns:
     - Master-DB: WeekTickRun status='completed', INTE 'failed'
     - Scope-DB: konton + transaktioner + lönespec + fakturor
     - Försäkringar + pension seedade
  3. Lärare hämtar elev-detalj-vyn och verifierar att data syns
  4. Lärare ser student i klass-översikt
  5. Pentagon-history finns

Misslyckas testet → riktig bugg, ingen genväg.
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
def app_and_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Bygg app + aktiv lärar-session. Imiterar produktionsläget."""
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
        teacher = Teacher(
            name="Anna Lärare",
            email="anna@example.com",
            password_hash=hash_password("hemligt"),
            ai_enabled=False,
            active=True,
        )
        s.add(teacher)
        s.flush()
        teacher_id = teacher.id
        s.commit()

    token = random_token()
    register_token(token, role="teacher", teacher_id=teacher_id)

    client = TestClient(app)
    return client, token, teacher_id


def test_e2e_create_student_full_flow(app_and_token):
    """Verifierar att en ny elev får ALL data direkt vid skapande,
    från lärarens perspektiv."""
    client, token, teacher_id = app_and_token

    # === 1. Skapa elev ===
    r = client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "first_name": "Linn",
            "last_initial": "B",
            "archetype": "kassorska",
            "spend_profile": "balanserad",
            "partner_model": "solo",
            "starting_level": 1,
            "guardian_email": None,
        },
    )
    assert r.status_code == 200, f"create-student failed: {r.text}"
    create_data = r.json()
    sid = create_data["student_id"]
    login_code = create_data["login_code"]
    assert login_code, "Ingen login-kod returnerad"

    # === 2. Verifiera WeekTickRun INTE har status='failed' ===
    from hembudget.school.game_engine_models import WeekTickRun
    with master_session() as s:
        runs = (
            s.query(WeekTickRun)
            .filter(WeekTickRun.student_id == sid)
            .all()
        )
        assert len(runs) >= 1, (
            f"Spelmotor körde inte vid student-creation. "
            f"Inga WeekTickRun-rader för student {sid}."
        )
        for run in runs:
            assert run.status != "failed", (
                f"WeekTickRun status='failed' för student {sid} "
                f"month={run.year_month}: {run.error_message}"
            )
        # Senaste run ska vara completed
        latest = max(runs, key=lambda r: r.started_at)
        assert latest.status == "completed", (
            f"Senaste WeekTickRun har status='{latest.status}' "
            f"(förväntade 'completed'). error_message={latest.error_message}"
        )

    # === 3. Hämta lärar-detalj-vy för eleven ===
    r = client.get(
        f"/v2/teacher/students/{sid}/student-detail",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"student-detail failed: {r.text}"
    detail = r.json()
    assert detail.get("student_name"), (
        "Eleven saknar student_name i student-detail"
    )
    pent = detail.get("pentagon")
    assert pent is not None, "student-detail saknar pentagon"
    # Pentagon ska ha värden från initial-seed (inte alla på default 50)
    pent_values = [
        pent.get(k, 50)
        for k in ("economy", "safety", "health", "social", "leisure")
    ]
    # Minst en axel ska skilja sig från default 50 efter tick
    assert any(v != 50 for v in pent_values), (
        f"Pentagon har alla axlar på default 50 — wellbeing beräknades "
        f"inte. Värden: {pent_values}"
    )

    # === 4. Hämta tick-history ===
    r = client.get(
        f"/v2/teacher/students/{sid}/tick-history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"tick-history failed: {r.text}"
    ticks = r.json()
    assert isinstance(ticks, list), "tick-history ska vara lista"
    assert len(ticks) >= 1, "Inga ticks i historiken"
    # Alla ticks ska vara completed (inga failed)
    for t in ticks:
        assert t["status"] != "failed", (
            f"Tick {t['year_month']} har status='failed': "
            f"{t.get('error_message')}"
        )

    # === 5. Pentagon-history ska finnas ===
    r = client.get(
        f"/v2/teacher/students/{sid}/pentagon-history?days=60",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, (
        f"pentagon-history failed: {r.status_code} {r.text}"
    )
    history = r.json()
    assert isinstance(history, list), "pentagon-history ska vara lista"
    # Pentagon-events skapas av tick → ska finnas minst en post
    assert len(history) >= 1, (
        "Pentagon-history är tom — spelmotorn skrev ingen WellbeingEvent"
    )

    # === 6. Lärar-klass-översikt visar eleven ===
    r = client.get(
        "/v2/teacher/klass-overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"klass-overview failed: {r.text}"
    klass = r.json()
    student_ids = [
        m["student_id"] for m in (klass.get("mini_pentagons") or [])
    ]
    assert sid in student_ids, (
        f"Eleven {sid} syns inte i klass-översikten "
        f"(student_ids={student_ids})"
    )

    # === 7. Direkt i scope-DB: konton + transaktioner + mail ===
    from hembudget.school.engines import (
        get_scope_session, scope_context, scope_for_student,
    )
    from hembudget.db.models import (
        Account as _Acc, MailItem as _Mail,
        Transaction as _Tx,
        InsurancePolicy, PensionAssumption,
    )

    with master_session() as s:
        st = s.get(Student, sid)
        scope_key = scope_for_student(st)

    maker = get_scope_session(scope_key)
    with scope_context(scope_key):
        with maker() as s:
            accounts = s.query(_Acc).all()
            assert len(accounts) >= 1, "Inga konton skapade"
            assert any(a.type == "checking" for a in accounts), (
                "Lönekonto (checking) saknas"
            )

            txs = s.query(_Tx).all()
            assert len(txs) >= 1, "Inga transaktioner"
            income = [t for t in txs if t.amount and t.amount > 0]
            assert len(income) >= 1, (
                f"Ingen lön-inbetalning. Hittade {len(txs)} txs."
            )

            mails = s.query(_Mail).all()
            assert len(mails) >= 1, "Postlådan tom"
            mail_types = {m.mail_type for m in mails}
            assert "salary_slip" in mail_types, (
                f"Lönespec saknas. Hittade typer: {mail_types}"
            )

            # Försäkring + pension
            policies = s.query(InsurancePolicy).all()
            assert len(policies) >= 1, "Inga default-försäkringar seedade"
            pa = s.query(PensionAssumption).first()
            assert pa is not None, "Pension-singleton saknas"


def test_e2e_create_student_idempotent(app_and_token):
    """Att skapa två elever efter varandra ska INTE krasch:a för andra."""
    client, token, _teacher_id = app_and_token

    for first_name in ["Anna", "Bertil", "Cecilia"]:
        r = client.post(
            "/v2/teacher/students/create",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "first_name": first_name,
                "starting_level": 1,
            },
        )
        assert r.status_code == 200, (
            f"create-student för {first_name} failed: {r.text}"
        )
        sid = r.json()["student_id"]

        # Verifiera tick-status för var och en
        from hembudget.school.game_engine_models import WeekTickRun
        with master_session() as s:
            runs = (
                s.query(WeekTickRun)
                .filter(WeekTickRun.student_id == sid)
                .all()
            )
            for run in runs:
                assert run.status != "failed", (
                    f"{first_name}: tick failed: {run.error_message}"
                )


def test_e2e_create_student_at_different_levels(app_and_token):
    """Levels 1-3 ska alla seeda data utan att krasch:a."""
    client, token, _teacher_id = app_and_token

    for level in [1, 2, 3]:
        r = client.post(
            "/v2/teacher/students/create",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "first_name": f"Level{level}",
                "starting_level": level,
            },
        )
        assert r.status_code == 200, f"Level {level}: {r.text}"
        sid = r.json()["student_id"]

        from hembudget.school.game_engine_models import WeekTickRun
        with master_session() as s:
            runs = (
                s.query(WeekTickRun)
                .filter(WeekTickRun.student_id == sid)
                .all()
            )
            for run in runs:
                assert run.status != "failed", (
                    f"Level {level}: tick failed: {run.error_message}"
                )


def test_e2e_auto_recovery_from_old_student_without_data(app_and_token):
    """KRITISK BUG: gamla elever som skapades innan seed-funktionen
    byggdes (eller där alla seed-försök har failat) har INGEN data.
    När läraren klickar på dem på student-detail-vyn ska auto-recovery
    triggas så de får data automatiskt.

    Reproducerar exakt det användaren såg: 'seed failed' på en student
    som saknar data."""
    client, token, teacher_id = app_and_token

    # Skapa elev MED data
    r = client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {token}"},
        json={"first_name": "Gamla", "starting_level": 1},
    )
    assert r.status_code == 200
    sid = r.json()["student_id"]

    # SIMULERA en gammal trasig student: ta BORT alla WeekTickRuns OCH
    # all scope-DB-data för att efterlikna en student utan data.
    from hembudget.school.game_engine_models import WeekTickRun
    from hembudget.school.engines import (
        get_scope_session, scope_context, scope_for_student,
    )
    from hembudget.db.models import (
        Account as _Acc, MailItem as _Mail, Transaction as _Tx,
    )
    from hembudget.school.models import Student as _Stu

    with master_session() as s:
        # Ta bort alla WeekTickRuns
        s.query(WeekTickRun).filter(
            WeekTickRun.student_id == sid,
        ).delete(synchronize_session=False)
        # Skapa en FAILED rad så det ser ut som det aldrig gick
        s.add(WeekTickRun(
            student_id=sid,
            year_month="2026-04",
            status="failed",
            error_message="simulerat fel från tidigare deploy",
        ))
        s.commit()
        st = s.get(_Stu, sid)
        scope_key = scope_for_student(st)

    # Ta bort all scope-DB-data så student verkligen är tom
    maker = get_scope_session(scope_key)
    with scope_context(scope_key):
        with maker() as s:
            s.query(_Tx).delete(synchronize_session=False)
            s.query(_Mail).delete(synchronize_session=False)
            s.query(_Acc).delete(synchronize_session=False)
            s.commit()

    # Verifiera att eleven nu är TOM (som användaren ser i produktion)
    with master_session() as s:
        runs = s.query(WeekTickRun).filter(
            WeekTickRun.student_id == sid,
        ).all()
        assert len(runs) == 1
        assert runs[0].status == "failed"

    # NU: lärare öppnar student-detail-vyn → auto-recovery ska köra seed
    r = client.get(
        f"/v2/teacher/students/{sid}/student-detail",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, f"student-detail crashed: {r.text}"

    # Efter auto-recovery ska det finnas en COMPLETED tick + scope-data
    with master_session() as s:
        completed = (
            s.query(WeekTickRun)
            .filter(
                WeekTickRun.student_id == sid,
                WeekTickRun.status == "completed",
            )
            .count()
        )
        assert completed >= 1, (
            "Auto-recovery körde inte seed för stuck student"
        )

    with scope_context(scope_key):
        with maker() as s:
            accounts = s.query(_Acc).all()
            assert len(accounts) >= 1, (
                "Auto-recovery skapade inte konton"
            )
            mails = s.query(_Mail).all()
            assert len(mails) >= 1, (
                "Auto-recovery seedade inte postlådan"
            )


def test_e2e_recovery_from_stale_failed_run(app_and_token):
    """Om en student har en gammal WeekTickRun med status='failed' så
    ska seeden retry:a och få den till 'completed' eller skapa en ny."""
    client, token, teacher_id = app_and_token

    # Skapa en elev (lyckas)
    r = client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {token}"},
        json={"first_name": "Stale", "starting_level": 1},
    )
    assert r.status_code == 200
    sid = r.json()["student_id"]

    # Korrumpera: sätt en WeekTickRun till 'failed' manuellt (simulerar
    # gammal tidpunkt då tick faktiskt failade)
    from hembudget.school.game_engine_models import WeekTickRun
    with master_session() as s:
        runs = (
            s.query(WeekTickRun)
            .filter(WeekTickRun.student_id == sid)
            .all()
        )
        for run in runs:
            run.status = "failed"
            run.error_message = "simulerat fel från tidigare körning"
        s.commit()

    # Trigga en ny tick via advance-month — den ska SKRIVA OVER den
    # failade raden eller skapa en ny som lyckas.
    from datetime import date as _d
    today = _d.today()
    if today.month == 1:
        prev_year = today.year - 1
        prev_month = 12
    else:
        prev_year = today.year
        prev_month = today.month - 1
    year_month = f"{prev_year:04d}-{prev_month:02d}"

    r = client.post(
        f"/v2/teacher/students/{sid}/advance-month",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "year_month": year_month,
            "seed": 42,
            "archetype": "random",
            "starting_level": 1,
            "spend_profile": "balanserad",
        },
    )
    assert r.status_code == 200, f"advance-month failed: {r.text}"

    # Nu ska den failade raden vara completed (eller en ny ska finnas)
    with master_session() as s:
        runs = (
            s.query(WeekTickRun)
            .filter(
                WeekTickRun.student_id == sid,
                WeekTickRun.year_month == year_month,
            )
            .all()
        )
        assert any(r.status == "completed" for r in runs), (
            f"Efter retry har vi fortfarande inga completed runs för "
            f"{year_month}: {[(r.status, r.error_message) for r in runs]}"
        )
