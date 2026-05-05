"""Smoke-tester för /v2/* (parallell-migration).

Verifierar:
- /v2/status returnerar rätt fält för student/teacher/super-admin
- /v2/onboarding/complete sparar fält på Student-tabellen
- v2_eligible är alltid True (för super-admin är detta särskilt viktigt)
- 401 utan token
"""
from __future__ import annotations

from datetime import datetime
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
    # Postgres-mode: TRUNCATE alla tabeller mellan tester så de inte
    # kolliderar (SQLite får ny tmp_path per test, Postgres delas).
    # Vi öppnar en ENGÅNGS-connection direkt via psycopg2 så vi inte
    # är beroende av SQLAlchemy-engine-state (som är None just nu).
    import os as _os_test
    _pg_url = _os_test.environ.get(
        "HEMBUDGET_DATABASE_URL", "",
    ).strip()
    if _pg_url.startswith("postgresql"):
        try:
            import psycopg2 as _psy_truncate
            from urllib.parse import urlparse as _urlparse
            _parsed = _urlparse(
                _pg_url.replace("postgresql+psycopg2://", "postgresql://"),
            )
            _conn_t = _psy_truncate.connect(
                host=_parsed.hostname,
                port=_parsed.port or 5432,
                user=_parsed.username,
                password=_parsed.password,
                dbname=_parsed.path.lstrip("/"),
                connect_timeout=5,
            )
            _conn_t.autocommit = True
            with _conn_t.cursor() as _cur:
                _cur.execute(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public'",
                )
                _names = [r[0] for r in _cur.fetchall()]
                if _names:
                    _cur.execute(
                        f"TRUNCATE {', '.join(_names)} "
                        f"RESTART IDENTITY CASCADE",
                    )
            _conn_t.close()
        except Exception:
            pass
    if eng_mod._master_engine is not None:
        eng_mod._master_engine.dispose()
    eng_mod._master_engine = None
    eng_mod._master_session = None
    if hasattr(eng_mod, "_shared_scope_engine") and eng_mod._shared_scope_engine is not None:
        eng_mod._shared_scope_engine.dispose()
        eng_mod._shared_scope_engine = None
        eng_mod._shared_scope_session = None
    for e in list(eng_mod._scope_engines.values()):
        e.dispose()
    eng_mod._scope_engines.clear()
    eng_mod._scope_sessions.clear()
    if hasattr(eng_mod, "_seeded_tenants"):
        eng_mod._seeded_tenants.clear()
    from hembudget.school import demo_seed as demo_seed_mod
    monkeypatch.setattr(demo_seed_mod, "build_demo", lambda: {"skipped": True})

    # Töm in-process-cachar mellan tester. Annars cache:ar /v2/
    # notifications svar från ett tidigare test där student_id råkar
    # vara samma som i nuvarande test (typiskt sid=1) och de följande
    # testerna ser stale data.
    from hembudget.api import v2 as _v2_mod
    _v2_mod._notif_cache.clear()
    _v2_mod._wellbeing_cache.clear()
    _v2_mod._mailcount_cache.clear()

    import importlib
    import hembudget.main as main_mod
    importlib.reload(main_mod)
    app = main_mod.build_app()
    init_master_engine()

    with master_session() as s:
        # Vanlig lärare
        t = Teacher(
            email="t@x.se", name="T",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(t); s.flush()
        tid = t.id

        # Super-admin-lärare
        sa = Teacher(
            email="sa@x.se", name="Super Admin",
            password_hash=hash_password("Abcdef12!"),
            is_super_admin=True,
        )
        s.add(sa); s.flush()
        sa_id = sa.id

        stu = Student(
            teacher_id=tid, display_name="Eva",
            login_code="EVA00001",
        )
        s.add(stu); s.flush()
        sid = stu.id

    tch_tok = random_token()
    sa_tok = random_token()
    stu_tok = random_token()
    register_token(tch_tok, role="teacher", teacher_id=tid)
    register_token(sa_tok, role="teacher", teacher_id=sa_id)
    register_token(stu_tok, role="student", student_id=sid)
    return TestClient(app), tch_tok, sa_tok, stu_tok, tid, sa_id, sid


def test_v2_status_unauthenticated_returns_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/status")
    assert r.status_code == 401


def test_v2_status_for_student_default_values(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/status",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["role"] == "student"
    # Default: v2 ej aktiverat av lärare → eligible=False
    assert data["v2_eligible"] is False
    assert data["v2_onboarding_completed"] is False
    assert data["v2_level"] == 1
    assert data["v2_spend_profile"] == "sparsam"
    assert data["v2_partner_model"] == "solo"
    assert data["is_super_admin"] is False


def test_v2_toggle_per_student(fx) -> None:
    """Lärare kan aktivera v2 för en specifik elev."""
    client, tch, _sa, stu, _tid, _said, sid = fx

    # Före: ej eligible
    pre = client.get(
        "/v2/status", headers={"Authorization": f"Bearer {stu}"},
    ).json()
    assert pre["v2_eligible"] is False

    # Lärare aktiverar
    r = client.post(
        f"/v2/teacher/students/{sid}/v2-toggle",
        headers={"Authorization": f"Bearer {tch}"},
        json={"enabled": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["v2_enabled"] is True

    # Efter: eligible=True
    post = client.get(
        "/v2/status", headers={"Authorization": f"Bearer {stu}"},
    ).json()
    assert post["v2_eligible"] is True


def test_v2_toggle_marks_v1_onboarding_complete(fx) -> None:
    """När v2 aktiveras ska v1-onboarding-flaggan sättas så App.tsx
    inte tvingar v1-onboardingen för v2-elever."""
    client, tch, _sa, _stu, _tid, _said, sid = fx

    # Verifiera att eleven INTE är onboarding-klar i v1 från start
    from hembudget.school.engines import master_session
    from hembudget.school.models import Student
    with master_session() as db:
        s = db.get(Student, sid)
        assert s is not None
        assert s.onboarding_completed is False

    # Aktivera v2 → v1-onboarding ska auto-markeras klar
    r = client.post(
        f"/v2/teacher/students/{sid}/v2-toggle",
        headers={"Authorization": f"Bearer {tch}"},
        json={"enabled": True},
    )
    assert r.status_code == 200, r.text

    with master_session() as db:
        s = db.get(Student, sid)
        assert s is not None
        assert s.v2_enabled is True
        assert s.onboarding_completed is True  # ← bypass v1-onboarding


def test_v2_toggle_only_own_students(fx) -> None:
    """Lärare kan inte toggla en annan lärares elev."""
    client, _tch, sa, _stu, _tid, _said, sid = fx
    # super-admin är annan teacher_id; ska få 403 på *andra* lärares elever
    r = client.post(
        f"/v2/teacher/students/{sid}/v2-toggle",
        headers={"Authorization": f"Bearer {sa}"},
        json={"enabled": True},
    )
    assert r.status_code == 403, r.text


def test_v2_bulk_toggle_all(fx) -> None:
    """Bulk: aktivera v2 för alla lärarens elever."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/teacher/students/v2-bulk",
        headers={"Authorization": f"Bearer {tch}"},
        json={"enabled": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["affected"] >= 1
    assert r.json()["enabled"] is True


def test_v2_roster_lists_students(fx) -> None:
    """Lärar-roster visar alla elever + v2-status."""
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/teacher/students/v2-roster",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 1
    eva = next((row for row in rows if row["student_id"] == sid), None)
    assert eva is not None
    assert eva["display_name"] == "Eva"
    assert eva["v2_enabled"] is False  # default


def test_v2_status_for_teacher_marks_super_admin(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/status",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["role"] == "teacher"
    assert data["v2_eligible"] is True
    assert data["is_super_admin"] is True


def test_v2_status_for_normal_teacher_not_super_admin(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/status",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["role"] == "teacher"
    assert data["is_super_admin"] is False


def test_v2_onboarding_complete_saves_fields(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, sid = fx

    # Innan: ej klar
    pre = client.get(
        "/v2/status",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    assert pre["v2_onboarding_completed"] is False
    assert pre["v2_fairness_choice"] is None

    # Komplettera
    r = client.post(
        "/v2/onboarding/complete",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "spend_profile": "balanserad",
            "fairness_choice": "proportionellt",
            "partner_model": "ai",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["redirect_to"] == "/v2/hub"
    assert "completed_at" in data

    # Status ska nu visa klart
    post = client.get(
        "/v2/status",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    assert post["v2_onboarding_completed"] is True
    assert post["v2_spend_profile"] == "balanserad"
    assert post["v2_fairness_choice"] == "proportionellt"
    assert post["v2_partner_model"] == "ai"
    # Level rörs INTE av elev-onboarding
    assert post["v2_level"] == 1


def test_v2_onboarding_idempotent(fx) -> None:
    """Att posta igen ska bara uppdatera profile/fairness, inte krascha."""
    client, _tch, _sa, stu, _tid, _said, _sid = fx

    client.post(
        "/v2/onboarding/complete",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "spend_profile": "balanserad",
            "fairness_choice": "proportionellt",
            "partner_model": "ai",
        },
    )
    # Andra försöket: ändra värdering
    r = client.post(
        "/v2/onboarding/complete",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "spend_profile": "sparsam",
            "fairness_choice": "50_50",
            "partner_model": "solo",
        },
    )
    assert r.status_code == 200, r.text

    post = client.get(
        "/v2/status",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    assert post["v2_spend_profile"] == "sparsam"
    assert post["v2_fairness_choice"] == "50_50"
    assert post["v2_partner_model"] == "solo"


def test_v2_onboarding_event_logs_viewed(fx) -> None:
    """Eleven postar 'viewed' när hen visar ett steg → sparas i DB."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.post(
        "/v2/onboarding/event",
        headers={"Authorization": f"Bearer {stu}"},
        json={"step": 1, "event_type": "viewed"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["event_id"] > 0


def test_v2_onboarding_event_with_duration_and_payload(fx) -> None:
    """Frontend skickar duration + payload (t.ex. fairness-svar)."""
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/onboarding/event",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "step": 7,
            "event_type": "next",
            "duration_ms": 42000,
            "payload": "fairness=proportionellt",
        },
    )
    assert r.status_code == 200, r.text


def test_v2_onboarding_events_for_teacher(fx) -> None:
    """Lärare kan hämta full event-historik för sin elev."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    # Eleven loggar tre events
    for ev in [
        {"step": 1, "event_type": "viewed"},
        {"step": 1, "event_type": "next", "duration_ms": 5000},
        {"step": 2, "event_type": "viewed"},
    ]:
        client.post(
            "/v2/onboarding/event",
            headers={"Authorization": f"Bearer {stu}"},
            json=ev,
        )
    # Lärare hämtar
    r = client.get(
        f"/v2/teacher/students/{sid}/onboarding-events",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 3
    # Sorterat kronologiskt
    assert rows[0]["step"] == 1 and rows[0]["event_type"] == "viewed"
    assert rows[1]["event_type"] == "next"
    assert rows[1]["duration_ms"] == 5000
    assert rows[2]["step"] == 2


def test_v2_onboarding_events_blocks_other_teachers(fx) -> None:
    """En lärare får inte se andra lärares elever."""
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/onboarding-events",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


def test_v2_onboarding_event_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.post(
        "/v2/onboarding/event",
        json={"step": 1, "event_type": "viewed"},
    )
    assert r.status_code == 401


def test_v2_onboarding_for_teacher_returns_200_without_writing(fx) -> None:
    """Teacher-tokens får 200 men inget sparas (de har ingen elev-profil)."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/onboarding/complete",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "spend_profile": "sparsam",
            "fairness_choice": None,
            "partner_model": "solo",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == 0  # Markör att det inte var elev


# === /v2/hub ===

def test_v2_hub_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/hub")
    assert r.status_code == 401


def test_v2_hub_for_student_returns_basic_fields(fx) -> None:
    """Eleven utan profil får ändå hub-data tillbaka — minst karaktär,
    pentagon (ev. None) och tom månads-summa."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/hub",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["character"]["display_name"] == "Eva"
    # Defaults
    assert data["v2_level"] == 1
    assert data["v2_spend_profile"] == "sparsam"
    assert data["v2_partner_model"] == "solo"
    # Månads-summa finns alltid (tom om ingen scope-DB)
    assert "month_summary" in data
    ms = data["month_summary"]
    assert "income" in ms and "expenses" in ms
    assert "saved" in ms and "save_rate_pct" in ms
    assert "transactions_count" in ms
    # Saldo-fält
    assert "total_balance" in data
    assert "accounts_count" in data


def test_v2_hub_includes_profile_when_set(fx) -> None:
    """När StudentProfile finns ska hub leverera dess karaktärsfält."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    # Skapa profil för Eva
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska",
            employer="Region Stockholm",
            gross_salary_monthly=30000,
            net_salary_monthly=24000,
            tax_rate_effective=0.2,
            age=22,
            city="Stockholm",
            family_status="ensam",
            housing_type="hyresratt",
            housing_monthly=8000,
            personality="blandad",
        ))

    r = client.get(
        "/v2/hub",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    char = r.json()["character"]
    assert char["display_name"] == "Eva"
    assert char["profession"] == "Undersköterska"
    assert char["employer"] == "Region Stockholm"
    assert char["age"] == 22
    assert char["city"] == "Stockholm"
    assert char["family_status"] == "ensam"
    assert char["housing_type"] == "hyresratt"
    assert char["housing_monthly"] == 8000
    assert char["gross_salary_monthly"] == 30000
    assert char["net_salary_monthly"] == 24000
    assert char["personality"] == "blandad"


def test_v2_hub_uses_character_name_when_set(fx) -> None:
    """När StudentProfile har character_first_name + character_last_name
    ska de användas som display_name (inte student.display_name som är
    elevens login-namn)."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            character_first_name="Sara",
            character_last_name="Andersson",
            profession="Undersköterska",
            employer="Region Stockholm",
            gross_salary_monthly=30000,
            net_salary_monthly=24000,
            tax_rate_effective=0.2,
            age=22,
            city="Stockholm",
            family_status="ensam",
            housing_type="hyresratt",
            housing_monthly=8000,
            personality="blandad",
        ))

    r = client.get(
        "/v2/hub",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    char = r.json()["character"]
    # display_name = karaktärsnamn, inte elevens login-namn "Eva"
    assert char["display_name"] == "Sara Andersson"
    assert char["first_name"] == "Sara"
    assert char["last_name"] == "Andersson"


def test_v2_hub_reflects_v2_fields_after_onboarding(fx) -> None:
    """Onboarding-svaren ska speglas direkt i /v2/hub."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    # Komplettera onboarding
    client.post(
        "/v2/onboarding/complete",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "spend_profile": "balanserad",
            "fairness_choice": "proportionellt",
            "partner_model": "ai",
        },
    )

    r = client.get(
        "/v2/hub",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["v2_spend_profile"] == "balanserad"
    assert data["v2_fairness_choice"] == "proportionellt"
    assert data["v2_partner_model"] == "ai"


def test_v2_hub_for_teacher_returns_placeholder(fx) -> None:
    """Lärare har ingen egen hub-data — får tom placeholder."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/hub",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == 0
    assert data["character"]["display_name"] == "—"
    assert data["accounts_count"] == 0
    assert data["total_balance"] == 0
    assert data["month_summary"]["transactions_count"] == 0


# === /v2/bank ===

def test_v2_bank_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/bank")
    assert r.status_code == 401


def test_v2_bank_for_student_returns_structure(fx) -> None:
    """Eleven utan transaktioner får tom payload med rätt struktur."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/bank",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert "year_month" in data
    # Summary-fält
    s = data["summary"]
    for field in (
        "total_balance",
        "accounts_count",
        "upcoming_open_total",
        "upcoming_open_count",
        "income_this_month",
        "expenses_this_month",
        "transactions_count",
    ):
        assert field in s, f"saknar fält {field} i summary"
    # Listor (kan vara tomma)
    assert isinstance(data["accounts"], list)
    assert isinstance(data["recent_transactions"], list)
    assert isinstance(data["upcoming_bills"], list)


def test_v2_bank_for_teacher_returns_empty(fx) -> None:
    """Lärare har ingen scope-DB — får tom payload utan crash."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/bank",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == 0
    assert data["summary"]["accounts_count"] == 0
    assert data["accounts"] == []
    assert data["recent_transactions"] == []
    assert data["upcoming_bills"] == []


def _seed_scope(sid: int, fn) -> None:
    """Hjälp-funktion: kör `fn(session)` inom elevens scope-DB."""
    from hembudget.db.base import session_scope as _ss
    from hembudget.school.engines import (
        master_session as _ms, scope_context as _sc,
        scope_for_student as _sfs,
    )
    from hembudget.school.models import Student as _St

    with _ms() as m:
        student = m.get(_St, sid)
        assert student is not None
        scope_key = _sfs(student)
    with _sc(scope_key):
        with _ss() as s:
            fn(s)


def test_v2_bank_with_account_and_transactions(fx) -> None:
    """När scope-DB har konton + transaktioner ska de speglas i bank-vyn."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Account as _Acc, Transaction as _Tx

    def seed(s) -> None:
        acc = _Acc(
            name="Lönekonto", bank="SEB", type="checking",
            currency="SEK", opening_balance=_D("1000"),
            opening_balance_date=_d(2026, 1, 1),
        )
        s.add(acc)
        s.flush()
        s.add(_Tx(
            account_id=acc.id,
            date=_d.today(),
            amount=_D("500"),
            currency="SEK",
            raw_description="Test-insättning",
            hash="hub-bank-test-1",
            user_verified=True,
        ))
        s.add(_Tx(
            account_id=acc.id,
            date=_d.today(),
            amount=_D("-200"),
            currency="SEK",
            raw_description="ICA Maxi",
            hash="hub-bank-test-2",
            user_verified=True,
        ))

    _seed_scope(sid, seed)

    r = client.get(
        "/v2/bank",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["accounts_count"] == 1
    # 1000 + 500 - 200 = 1300
    assert data["summary"]["total_balance"] == 1300
    # 2 transaktioner denna månad
    assert data["summary"]["transactions_count"] == 2
    assert data["summary"]["income_this_month"] == 500
    assert data["summary"]["expenses_this_month"] == 200
    # Konto-data
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["name"] == "Lönekonto"
    assert data["accounts"][0]["bank"] == "SEB"
    # Transaktioner sorterade nyast först
    assert len(data["recent_transactions"]) == 2
    descs = [t["description"] for t in data["recent_transactions"]]
    assert "Test-insättning" in descs
    assert "ICA Maxi" in descs
    # Account-namn ska följa med transaktionerna
    for t in data["recent_transactions"]:
        assert t["account_name"] == "Lönekonto"


def test_v2_hub_isk_purchases_count_as_transfer_not_expense(fx) -> None:
    """ISK-/fond-köp ska markeras med is_transfer=True så hub-summary
    inte räknar dem som "utgifter denna mån". Pedagogiskt: investering
    är kapital-omflyttning, inte konsumtion.

    Regression-test för bug där "Sparat denna mån" visade −4 436 kr
    trots att eleven faktiskt FLYTTAT 5 000 kr till sparkonto + köpt
    aktier för 4 436 kr (= positiv kapital-omflyttning, inte utgift).
    """
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Account as _Acc, Transaction as _Tx

    def seed(s) -> None:
        # Lönekonto med opening + en lön-in-transaktion (riktig inkomst)
        check = _Acc(
            name="Lönekonto", bank="SEB", type="checking",
            currency="SEK", opening_balance=_D("10000"),
            opening_balance_date=_d(2026, 1, 1),
        )
        s.add(check)
        isk = _Acc(
            name="ISK", bank="SEB", type="isk",
            currency="SEK", opening_balance=_D("0"),
        )
        s.add(isk)
        s.flush()
        # Lön + ICA = riktiga inkomst/utgift
        s.add(_Tx(
            account_id=check.id, date=_d.today(),
            amount=_D("20000"), currency="SEK",
            raw_description="Lön april", hash="t-isk-lon",
            user_verified=True, is_transfer=False,
        ))
        s.add(_Tx(
            account_id=check.id, date=_d.today(),
            amount=_D("-1500"), currency="SEK",
            raw_description="ICA Maxi", hash="t-isk-ica",
            user_verified=True, is_transfer=False,
        ))
        # ISK-köp · MÅSTE vara is_transfer=True för att inte räknas
        # som utgift. (stocks/trading.py och fund-buy sätter detta nu.)
        s.add(_Tx(
            account_id=isk.id, date=_d.today(),
            amount=_D("-2657"), currency="SEK",
            raw_description="Köp 5 st Volvo B @ 529.98 SEK",
            hash="t-isk-volvo", user_verified=True, is_transfer=True,
        ))
        s.add(_Tx(
            account_id=isk.id, date=_d.today(),
            amount=_D("-321"), currency="SEK",
            raw_description="Köp 1 st Electrolux B @ 319.50 SEK",
            hash="t-isk-elec", user_verified=True, is_transfer=True,
        ))

    _seed_scope(sid, seed)

    r = client.get(
        "/v2/hub", headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    ms = r.json()["month_summary"]
    # Inkomst = bara lönen, INTE ISK-köp (som är negativa transfers)
    assert ms["income"] == 20000, ms
    # Utgifter = bara ICA, INTE ISK-köp
    assert ms["expenses"] == 1500, ms
    # Sparat = 20000 - 1500 = 18500 (inte -4436 + 20000-1500=14064 buggen)
    assert ms["saved"] == 18500, ms
    # Sparkvot räknas på riktig inkomst
    assert ms["save_rate_pct"] is not None
    assert abs(ms["save_rate_pct"] - 92.5) < 0.1, ms


def test_v2_hub_leon_scenario_isk_buys_dont_destroy_save_rate(fx) -> None:
    """Reproduce Leons skärmdump-scenario:
    - Lönekonto med opening 17 205 (efter april-aktivitet)
    - Maj-aktivitet: 4 överföringar (5000 kr ISK, 5000 kr sparkonto) +
      6 ISK-köp för totalt -4 436 kr
    - Förväntat: hub visar sparat=0, sparkvot=null (ingen lön i maj än)
    - Buggen var: sparat=-4 436, sparkvot=0.0% (vilseledande)
    """
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Account as _Acc, Transaction as _Tx

    today = _d.today()

    def seed(s) -> None:
        check = _Acc(
            name="Lönekonto", bank="Spelbanken", type="checking",
            currency="SEK", opening_balance=_D("17205"),
            opening_balance_date=_d(today.year, today.month, 1),
        )
        s.add(check)
        savings = _Acc(
            name="Sparkonto", bank="Spelbanken", type="savings",
            currency="SEK", opening_balance=_D("0"),
        )
        s.add(savings)
        isk = _Acc(
            name="ISK", bank="Spelbanken", type="isk",
            currency="SEK", opening_balance=_D("0"),
        )
        s.add(isk)
        s.flush()
        # Överföringar (transfer-pair)
        for i, (src, dst, amt) in enumerate([
            (check, isk, 5000),
            (check, savings, 5000),
        ]):
            out_tx = _Tx(
                account_id=src.id, date=today, amount=_D(-amt),
                currency="SEK",
                raw_description=f"Överföring till {dst.name}",
                hash=f"leon-tr-out-{i}", is_transfer=True,
                user_verified=True,
            )
            in_tx = _Tx(
                account_id=dst.id, date=today, amount=_D(amt),
                currency="SEK",
                raw_description=f"Överföring från {src.name}",
                hash=f"leon-tr-in-{i}", is_transfer=True,
                user_verified=True,
            )
            s.add_all([out_tx, in_tx])
        # 6 ISK-köp · is_transfer=True (efter min fix)
        isk_amounts = [-321, -589, -166, -245, -460, -2657]
        for i, amt in enumerate(isk_amounts):
            s.add(_Tx(
                account_id=isk.id, date=today, amount=_D(amt),
                currency="SEK",
                raw_description=f"Köp aktie #{i}",
                hash=f"leon-isk-{i}", is_transfer=True,
                user_verified=True,
            ))

    _seed_scope(sid, seed)

    r = client.get("/v2/hub", headers={"Authorization": f"Bearer {stu}"})
    assert r.status_code == 200, r.text
    ms = r.json()["month_summary"]
    # Inga riktiga inkomster eller utgifter — allt är transfers/investeringar
    assert ms["income"] == 0, f"Inkomst ska vara 0 (inga riktiga inkomster), fick {ms['income']}"
    assert ms["expenses"] == 0, f"Utgifter ska vara 0 (ISK-köp är transfers), fick {ms['expenses']}"
    assert ms["saved"] == 0, f"Sparat ska vara 0 (inga in/ut), fick {ms['saved']}"
    assert ms["save_rate_pct"] is None, (
        "Sparkvot ska vara None när income=0, "
        f"fick {ms['save_rate_pct']} (vilseleder eleven)"
    )
    # Saldot räknas: 17205 (opening) - 10000 (transfers ut från lk)
    # = 7205 på lönekonto, 5000 på spar, 5000-4438=562 på ISK
    # Total = 7205 + 5000 + 562 = 12767
    total = r.json()["total_balance"]
    assert 12760 <= total <= 12770, f"Total saldo {total} avviker från 12 767"


def test_v2_hub_save_rate_null_when_no_income(fx) -> None:
    """Sparkvot ska vara None (frontend visar "—") när income = 0,
    inte 0.0 % som vilseleder eleven att tro hen sparar 0 %."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Account as _Acc, Transaction as _Tx

    def seed(s) -> None:
        acc = _Acc(
            name="Lk", bank="B", type="checking", currency="SEK",
            opening_balance=_D("5000"),
        )
        s.add(acc)
        s.flush()
        # Bara en utgift, ingen inkomst
        s.add(_Tx(
            account_id=acc.id, date=_d.today(),
            amount=_D("-200"), currency="SEK",
            raw_description="Willys", hash="t-saverate-1",
            user_verified=True, is_transfer=False,
        ))

    _seed_scope(sid, seed)
    r = client.get(
        "/v2/hub", headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200
    ms = r.json()["month_summary"]
    assert ms["income"] == 0
    assert ms["expenses"] == 200
    assert ms["save_rate_pct"] is None, (
        f"Sparkvot ska vara None när income=0, fick {ms['save_rate_pct']}"
    )


def test_v2_bank_limit_transactions_param(fx) -> None:
    """limit_transactions kapar antalet returnerade transaktioner."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Account as _Acc, Transaction as _Tx

    def seed(s) -> None:
        acc = _Acc(name="K", bank="B", type="checking", currency="SEK")
        s.add(acc)
        s.flush()
        for i in range(5):
            s.add(_Tx(
                account_id=acc.id, date=_d.today(),
                amount=_D("10"), currency="SEK",
                raw_description=f"tx{i}", hash=f"limit-tx-{i}",
                user_verified=True,
            ))

    _seed_scope(sid, seed)

    r = client.get(
        "/v2/bank?limit_transactions=3",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["recent_transactions"]) == 3


# === /v2/budget ===

def test_v2_budget_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/budget")
    assert r.status_code == 401


def test_v2_budget_for_student_returns_structure(fx) -> None:
    """Eleven utan budget får tom payload med rätt struktur."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/budget",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert "month" in data
    s = data["summary"]
    for f in (
        "income_total",
        "expenses_total",
        "planned_expenses_total",
        "saved",
        "save_rate_pct",
        "days_into_month",
        "days_in_month",
        "progress_pct",
        "over_budget_total",
        "categories_count",
    ):
        assert f in s, f"saknar fält {f}"
    assert isinstance(data["categories"], list)


def test_v2_budget_for_teacher_returns_empty(fx) -> None:
    """Lärare har ingen scope-DB — får tom payload utan crash."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/budget",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == 0
    assert data["categories"] == []


def test_v2_budget_with_categories_and_actuals(fx) -> None:
    """När scope-DB har budget + transaktioner ska de speglas."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc, Budget as _Bd, Category as _Cat,
        Transaction as _Tx,
    )

    today = _d.today()
    ym = f"{today.year:04d}-{today.month:02d}"

    def seed(s) -> None:
        # Använd unika namn så de inte kolliderar med ev. seed-data
        cat_mat = _Cat(name="Mat-test-v2budget")
        cat_rest = _Cat(name="Restaurang-test-v2budget")
        cat_lon = _Cat(name="Lön-test-v2budget")
        s.add_all([cat_mat, cat_rest, cat_lon])
        s.flush()

        acc = _Acc(name="Lönekonto", bank="SEB", type="checking", currency="SEK")
        s.add(acc)
        s.flush()

        # Budget för månaden
        s.add_all([
            _Bd(month=ym, category_id=cat_mat.id, planned_amount=_D("-4000")),
            _Bd(month=ym, category_id=cat_rest.id, planned_amount=_D("-1200")),
            _Bd(month=ym, category_id=cat_lon.id, planned_amount=_D("22000")),
        ])

        # Transaktioner — utfall
        s.add(_Tx(
            account_id=acc.id, date=today,
            amount=_D("-3880"), currency="SEK",
            raw_description="ICA Maxi", category_id=cat_mat.id,
            hash="bud-mat-1",
        ))
        s.add(_Tx(
            account_id=acc.id, date=today,
            amount=_D("-2100"), currency="SEK",
            raw_description="Max Hökarängen", category_id=cat_rest.id,
            hash="bud-rest-1",
        ))
        s.add(_Tx(
            account_id=acc.id, date=today,
            amount=_D("22000"), currency="SEK",
            raw_description="Lön", category_id=cat_lon.id,
            hash="bud-lon-1",
        ))

    _seed_scope(sid, seed)

    r = client.get(
        "/v2/budget",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    cats = {c["category_name"]: c for c in data["categories"]}
    assert "Mat-test-v2budget" in cats
    assert "Restaurang-test-v2budget" in cats
    assert "Lön-test-v2budget" in cats

    # Mat: planned 4000, actual 3880 → under (97 % < 105 %)
    mat = cats["Mat-test-v2budget"]
    assert mat["planned"] == 4000
    assert mat["actual"] == 3880
    assert mat["status"] == "under"
    # Konsumentverket-referens hittas på "mat" i namnet
    assert mat["consumer_reference"] is not None

    # Restaurang: planned 1200, actual 2100 → over (175 %)
    rest = cats["Restaurang-test-v2budget"]
    assert rest["status"] == "over"
    assert rest["progress_pct"] > 100

    # Lön: kind income → status "income"
    lon = cats["Lön-test-v2budget"]
    assert lon["is_income"] is True
    assert lon["status"] == "income"

    # Summary
    s = data["summary"]
    assert s["income_total"] == 22000
    assert s["expenses_total"] == 5980  # 3880 + 2100
    assert s["saved"] == 16020
    # Over-budget total: rest överskred med 900
    assert s["over_budget_total"] == 900


def test_v2_budget_month_query_param(fx) -> None:
    """?month=YYYY-MM använder den specifika månaden."""
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/budget?month=2026-04",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["month"] == "2026-04"


def test_v2_budget_fixed_category_status(fx) -> None:
    """Hyra/autogiro → status=fixed oavsett actual/planned."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc, Budget as _Bd, Category as _Cat,
        Transaction as _Tx,
    )

    today = _d.today()
    ym = f"{today.year:04d}-{today.month:02d}"

    def seed(s) -> None:
        # Unikt namn för att undvika kollision med ev. seed-data,
        # men innehåller "hyra" för att trigga _is_fixed + ikon-mappning.
        cat_hyra = _Cat(name="Hyra-test-fixed")
        s.add(cat_hyra); s.flush()
        acc = _Acc(name="K", bank="B", type="checking", currency="SEK")
        s.add(acc); s.flush()
        s.add(_Bd(month=ym, category_id=cat_hyra.id, planned_amount=_D("-7240")))
        s.add(_Tx(
            account_id=acc.id, date=today,
            amount=_D("-7240"), currency="SEK",
            raw_description="Stockholmshem", category_id=cat_hyra.id,
            hash="bud-hyra-1",
        ))

    _seed_scope(sid, seed)

    r = client.get(
        "/v2/budget",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    cats = {c["category_name"]: c for c in r.json()["categories"]}
    assert cats["Hyra-test-fixed"]["status"] == "fixed"
    assert cats["Hyra-test-fixed"]["is_fixed"] is True
    assert cats["Hyra-test-fixed"]["icon"] == "▥"


# === /v2/budget POST/DELETE (editerbar budget) ===

def test_v2_budget_update_category(fx) -> None:
    """POST /v2/budget/{id} uppdaterar planerad budget för en kategori."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Category as _Cat

    today = _d.today()
    ym = f"{today.year:04d}-{today.month:02d}"

    cat_id_holder: dict[str, int] = {}

    def seed(s) -> None:
        cat = _Cat(name="Mat-update-test")
        s.add(cat); s.flush()
        cat_id_holder["id"] = cat.id

    _seed_scope(sid, seed)
    cat_id = cat_id_holder["id"]

    # Sätt budget till 4000 (utgift)
    r = client.post(
        f"/v2/budget/{cat_id}",
        headers={"Authorization": f"Bearer {stu}"},
        json={"planned_amount": 4000, "month": ym, "is_income": False},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["category_id"] == cat_id
    assert data["category_name"] == "Mat-update-test"
    assert data["planned"] == 4000
    assert data["is_income"] is False

    # Höj till 5000
    r = client.post(
        f"/v2/budget/{cat_id}",
        headers={"Authorization": f"Bearer {stu}"},
        json={"planned_amount": 5000, "month": ym, "is_income": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["planned"] == 5000

    # Verifiera via GET
    r = client.get(
        "/v2/budget",
        headers={"Authorization": f"Bearer {stu}"},
    )
    cats = {c["category_name"]: c for c in r.json()["categories"]}
    assert cats["Mat-update-test"]["planned"] == 5000


def test_v2_budget_update_unknown_category_returns_404(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/budget/9999",
        headers={"Authorization": f"Bearer {stu}"},
        json={"planned_amount": 100},
    )
    assert r.status_code == 404


def test_v2_budget_update_negative_amount_returns_422(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/budget/1",
        headers={"Authorization": f"Bearer {stu}"},
        json={"planned_amount": -100},
    )
    assert r.status_code == 422


def test_v2_budget_update_for_teacher_returns_403(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/budget/1",
        headers={"Authorization": f"Bearer {tch}"},
        json={"planned_amount": 100},
    )
    assert r.status_code == 403


def test_v2_budget_create_category(fx) -> None:
    """POST /v2/budget/category skapar ny kategori + sätter budget."""
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    from datetime import date as _d
    today = _d.today()
    ym = f"{today.year:04d}-{today.month:02d}"

    r = client.post(
        "/v2/budget/category",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "category_name": "Träning-test",
            "planned_amount": 500,
            "month": ym,
            "is_income": False,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["category_name"] == "Träning-test"
    assert data["planned"] == 500
    assert data["is_income"] is False
    assert data["category_id"] > 0

    # Idempotent: anropa igen → samma kategori, ny planned
    r2 = client.post(
        "/v2/budget/category",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "category_name": "Träning-test",
            "planned_amount": 800,
            "month": ym,
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["planned"] == 800
    # Samma category_id → idempotent
    assert r2.json()["category_id"] == data["category_id"]


def test_v2_budget_create_empty_name_returns_400(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/budget/category",
        headers={"Authorization": f"Bearer {stu}"},
        json={"category_name": "   ", "planned_amount": 100},
    )
    assert r.status_code in (400, 422)  # min_length=1 efter strip


def test_v2_budget_delete_row(fx) -> None:
    """DELETE /v2/budget/{id} raderar budget-raden men inte kategorin."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from datetime import date as _d
    today = _d.today()
    ym = f"{today.year:04d}-{today.month:02d}"

    # Skapa kategori + budget via POST
    r = client.post(
        "/v2/budget/category",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "category_name": "Tillfällig-test",
            "planned_amount": 200,
            "month": ym,
        },
    )
    cat_id = r.json()["category_id"]

    # Verifiera att raden finns i /v2/budget
    r2 = client.get(
        "/v2/budget",
        headers={"Authorization": f"Bearer {stu}"},
    )
    names = [c["category_name"] for c in r2.json()["categories"]]
    assert "Tillfällig-test" in names

    # Radera budget-raden
    r3 = client.delete(
        f"/v2/budget/{cat_id}?month={ym}",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r3.status_code == 204, r3.text

    # /v2/budget ska inte längre lista raden
    r4 = client.get(
        "/v2/budget",
        headers={"Authorization": f"Bearer {stu}"},
    )
    names = [c["category_name"] for c in r4.json()["categories"]]
    assert "Tillfällig-test" not in names


def test_v2_budget_delete_for_teacher_returns_403(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.delete(
        "/v2/budget/1",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 403


# === /v2/mal (sparmål) ===

def test_v2_mal_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/mal")
    assert r.status_code == 401


def test_v2_mal_for_student_returns_structure(fx) -> None:
    """Eleven utan mål får tom payload med rätt struktur."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/mal",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    s = data["summary"]
    for f in (
        "total_saved",
        "total_target",
        "overall_progress_pct",
        "monthly_pace_total",
        "goals_count",
        "on_track_count",
        "behind_count",
    ):
        assert f in s
    assert isinstance(data["goals"], list)


def test_v2_mal_for_teacher_returns_empty(fx) -> None:
    """Lärare har ingen scope-DB — får tom payload."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/mal",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == 0
    assert data["goals"] == []


def test_v2_mal_with_goals(fx) -> None:
    """Mål + saldo i scope-DB ska speglas korrekt."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from datetime import date as _d, timedelta as _td
    from decimal import Decimal as _D
    from hembudget.db.models import Goal as _Goal

    today = _d.today()

    def seed(s) -> None:
        # Mål 1: Buffert · 1800/22000 (8 %, 600/mån, klart dec 2028)
        s.add(_Goal(
            name="Buffert (akut)",
            target_amount=_D("22000"),
            current_amount=_D("1800"),
            target_date=today + _td(days=365 * 2),
        ))
        # Mål 2: Körkort · 4200/15000 (28 %)
        s.add(_Goal(
            name="Körkort B",
            target_amount=_D("15000"),
            current_amount=_D("4200"),
            target_date=today + _td(days=365),
        ))
        # Mål 3: Komplett — 8000/8000
        s.add(_Goal(
            name="Interrail-resa",
            target_amount=_D("8000"),
            current_amount=_D("8000"),
            target_date=today + _td(days=180),
        ))

    _seed_scope(sid, seed)

    r = client.get(
        "/v2/mal",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["goals_count"] == 3
    assert data["summary"]["total_saved"] == 14000  # 1800 + 4200 + 8000
    assert data["summary"]["total_target"] == 45000  # 22000 + 15000 + 8000

    by_name = {g["name"]: g for g in data["goals"]}

    # Buffert: 1800/22000 = 8 % → "new" (< low threshold typically)
    # men progress > 5 så det blir on_track eller behind beroende på
    # expected progress. Kollar bara att color/icon är rätt för nu.
    buf = by_name["Buffert (akut)"]
    assert buf["target_amount"] == 22000
    assert buf["current_amount"] == 1800
    assert buf["progress_pct"] > 5
    assert buf["color"] == "var(--accent)"
    assert buf["icon"] == "🛡"

    # Körkort: 28 % progress, har deadline → bör räkna pace
    kor = by_name["Körkort B"]
    assert kor["color"] == "var(--warm)"
    assert kor["icon"] == "🚗"
    assert kor["months_remaining"] is not None and kor["months_remaining"] > 0
    # (15000 - 4200) / months_remaining > 0
    assert kor["monthly_pace_target"] is not None
    assert kor["monthly_pace_target"] > 0

    # Interrail komplett: status=complete, ingen pace behövs
    ir = by_name["Interrail-resa"]
    assert ir["status"] == "complete"
    assert ir["color"] == "#6ee7b7"
    assert ir["icon"] == "🌍"


def test_v2_mal_progress_overall(fx) -> None:
    """overall_progress_pct = totalt sparat / totalt mål * 100."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from decimal import Decimal as _D
    from hembudget.db.models import Goal as _Goal

    def seed(s) -> None:
        s.add(_Goal(
            name="A", target_amount=_D("10000"), current_amount=_D("2500"),
        ))
        s.add(_Goal(
            name="B", target_amount=_D("5000"), current_amount=_D("2500"),
        ))

    _seed_scope(sid, seed)

    r = client.get(
        "/v2/mal",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    # 5000/15000 = 33.3 %
    assert abs(s["overall_progress_pct"] - 33.3) < 0.5


# === /v2/postladan ===

def test_v2_postladan_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/postladan")
    assert r.status_code == 401


def test_v2_postladan_for_student_returns_structure(fx) -> None:
    """Eleven utan brev får tom payload med rätt struktur."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/postladan",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    s = data["summary"]
    for f in (
        "total_count",
        "unhandled_count",
        "invoice_count",
        "salary_slip_count",
        "authority_count",
        "info_count",
        "to_pay_amount",
        "incoming_amount",
        "overdue_count",
    ):
        assert f in s
    assert isinstance(data["items"], list)


def test_v2_postladan_for_teacher_returns_empty(fx) -> None:
    """Lärare har ingen scope-DB — får tom payload."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/postladan",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == 0
    assert data["items"] == []


def test_v2_postladan_seed_and_read(fx) -> None:
    """Lärare seedar 3 mail → eleven ser dem korrekt."""
    client, tch, _sa, stu, _tid, _said, sid = fx

    # Lärare seedar 3 mail
    seed_body = {
        "items": [
            {
                "sender": "SEB Visa",
                "sender_short": "CC",
                "sender_kind": "cred",
                "mail_type": "invoice",
                "subject": "April-spend: 47 transaktioner att granska",
                "body_meta": "Mat 2 240 · Restaurang 1 470",
                "amount": -4822,
                "due_date": "2026-05-28",
                "is_recurring": False,
            },
            {
                "sender": "Skatteverket",
                "sender_short": "SKV",
                "sender_kind": "skv",
                "mail_type": "authority",
                "subject": "Inkomstdeklaration 2025 — granska",
                "body_meta": "1 förslag · prognos +1 240 kr tillbaka",
                "amount": 1240,
                "due_date": "2026-05-02",
            },
            {
                "sender": "Sthlm Sjukhus AB",
                "sender_short": "LÖN",
                "sender_kind": "work",
                "mail_type": "salary_slip",
                "subject": "Lönespec april 2026",
                "body_meta": "brutto 31 250 + OB 480",
                "amount": 22880,
                "due_date": "2026-05-25",
            },
        ],
        "replace_existing": True,
    }
    r = client.post(
        f"/v2/teacher/students/{sid}/mail-seed",
        headers={"Authorization": f"Bearer {tch}"},
        json=seed_body,
    )
    assert r.status_code == 200, r.text
    seed = r.json()
    assert seed["created"] == 3
    assert seed["student_id"] == sid

    # Eleven läser
    r2 = client.get(
        "/v2/postladan",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["summary"]["total_count"] == 3
    assert data["summary"]["unhandled_count"] == 3
    assert data["summary"]["invoice_count"] == 1
    assert data["summary"]["salary_slip_count"] == 1
    assert data["summary"]["authority_count"] == 1
    # Att betala: 4822 (CC-faktura)
    assert data["summary"]["to_pay_amount"] == 4822
    # Inkommande: 1240 (SKV-tillbaka) + 22880 (lön) = 24120
    assert data["summary"]["incoming_amount"] == 24120

    senders = {item["sender"] for item in data["items"]}
    assert "SEB Visa" in senders
    assert "Skatteverket" in senders
    assert "Sthlm Sjukhus AB" in senders


def test_v2_postladan_filter_unhandled(fx) -> None:
    """`?filter=unhandled` returnerar bara de som inte hanterats."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    client.post(
        f"/v2/teacher/students/{sid}/mail-seed",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "items": [
                {"sender": "A", "mail_type": "invoice", "subject": "x", "amount": -100},
                {"sender": "B", "mail_type": "invoice", "subject": "y", "amount": -200},
            ],
            "replace_existing": True,
        },
    )
    # Markera A som exporterad
    items = client.get(
        "/v2/postladan",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()["items"]
    a_id = next(it["id"] for it in items if it["sender"] == "A")
    r = client.patch(
        f"/v2/postladan/{a_id}/status",
        headers={"Authorization": f"Bearer {stu}"},
        json={"status": "exported"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "exported"

    # Nu ska filter=unhandled bara visa B
    r2 = client.get(
        "/v2/postladan?filter=unhandled",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r2.status_code == 200, r2.text
    items2 = r2.json()["items"]
    assert len(items2) == 1
    assert items2[0]["sender"] == "B"
    # Total-count är fortfarande 2 (filter påverkar inte summary)
    assert r2.json()["summary"]["total_count"] == 2
    assert r2.json()["summary"]["unhandled_count"] == 1


def test_v2_postladan_seed_blocks_other_teacher(fx) -> None:
    """Annan lärares elev → 403."""
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/mail-seed",
        headers={"Authorization": f"Bearer {sa}"},
        json={"items": [], "replace_existing": False},
    )
    assert r.status_code == 403


def test_v2_postladan_seed_replace_existing(fx) -> None:
    """replace_existing=True → tömmer befintliga rader först."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    # Första seed: 2 brev
    client.post(
        f"/v2/teacher/students/{sid}/mail-seed",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "items": [
                {"sender": "A", "mail_type": "invoice", "subject": "x"},
                {"sender": "B", "mail_type": "invoice", "subject": "y"},
            ],
            "replace_existing": True,
        },
    )
    # Andra seed: 1 brev, replace_existing=True
    r = client.post(
        f"/v2/teacher/students/{sid}/mail-seed",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "items": [
                {"sender": "C", "mail_type": "info", "subject": "z"},
            ],
            "replace_existing": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == 2
    assert r.json()["created"] == 1

    items = client.get(
        "/v2/postladan",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()["items"]
    assert len(items) == 1
    assert items[0]["sender"] == "C"


# === /v2/arbetsgivaren ===

def test_v2_arbetsgivaren_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/arbetsgivaren")
    assert r.status_code == 401


def test_v2_arbetsgivaren_for_teacher_returns_empty(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/arbetsgivaren",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == 0
    assert data["profession"] == "—"
    assert data["salary_slips"] == []
    assert data["questions"] == []


def test_v2_arbetsgivaren_without_profile_returns_empty(fx) -> None:
    """Elev utan StudentProfile får tom payload (inte crash)."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/arbetsgivaren",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["profession"] == "—"


def test_v2_arbetsgivaren_with_profile_returns_basics(fx) -> None:
    """Elev med profil får riktiga lönedata + agreement-defaults."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            character_first_name="Sara",
            character_last_name="Andersson",
            profession="Undersköterska",
            employer="Sthlm Sjukhus AB",
            gross_salary_monthly=31250,
            net_salary_monthly=22400,
            tax_rate_effective=0.28,
            age=22,
            city="Stockholm",
            family_status="ensam",
            housing_type="hyresratt",
            housing_monthly=8000,
            personality="blandad",
        ))
        db.commit()

    r = client.get(
        "/v2/arbetsgivaren",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["profession"] == "Undersköterska"
    assert data["employer"] == "Sthlm Sjukhus AB"
    assert data["gross_salary_monthly"] == 31250
    assert data["net_salary_monthly"] == 22400
    # Marknadsspann läses ENDAST från CollectiveAgreement.meta —
    # utan strukturerad meta finns inga schabloner.
    assert data["market_low"] is None
    assert data["market_high"] is None
    # Förmåner returneras BARA om profession har avtalad pension OCH/ELLER
    # CollectiveAgreement.meta innehåller benefits-lista. Utan profil-
    # kopplat avtal i denna test-fixture är listan tom.
    assert isinstance(data["agreement_benefits"], list)
    # Satisfaction default 70
    assert data["satisfaction"]["score"] == 70
    assert data["satisfaction"]["delta_4w"] == 0


def test_v2_arbetsgivaren_with_salary_transactions(fx) -> None:
    """Lönespecar härleds från transaktioner med 'lön' i description."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from datetime import date as _d, timedelta as _td
    from decimal import Decimal as _D
    from hembudget.db.models import Account as _Acc, Transaction as _Tx

    # Profil först
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska",
            employer="Sthlm Sjukhus AB",
            gross_salary_monthly=31250,
            net_salary_monthly=22400,
            tax_rate_effective=0.28,
            age=22, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000, personality="blandad",
        ))
        db.commit()

    today = _d.today()

    def seed(s) -> None:
        acc = _Acc(name="Lönekonto", bank="SEB", type="checking", currency="SEK")
        s.add(acc); s.flush()
        # 3 lönespecar i månader bakåt
        for i in range(3):
            d = today - _td(days=30 * (i + 1))
            s.add(_Tx(
                account_id=acc.id, date=d,
                amount=_D("22400"), currency="SEK",
                raw_description="Lön Sthlm Sjukhus AB",
                hash=f"lon-test-{i}",
            ))

    _seed_scope(sid, seed)

    r = client.get(
        "/v2/arbetsgivaren",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    slips = data["salary_slips"]
    assert len(slips) == 3
    # Senast först
    assert slips[0]["net_amount"] == 22400
    assert slips[0]["gross_amount"] == 31250
    # Skatt räknas nu via compute_net_salary (riktig kommunal+statlig)
    # · för 31 250 kr brutto blir det 9 600 kr. Tidigare användes
    # gross-net=8850 men det vilseleder vid sjukfrånvaro där diff:en
    # även inkluderar löneavdrag (visar 'skatt 26 908' = 84 % istället
    # för riktig skatt).
    assert slips[0]["tax_amount"] == 9600


# === Fas 2A: lärar-endpoints + KALP + CreditCheck ===

def test_v2_teacher_seed_default_loan_products(fx) -> None:
    """Lärar-endpoint seedar default-katalogen (5 produkter)."""
    client, tch, _sa, _stu, _tid, _said, sid = fx

    r = client.post(
        f"/v2/teacher/students/{sid}/loan-products/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["products_created"] == 5

    # Idempotent: andra anropet skapar inga nya
    r2 = client.post(
        f"/v2/teacher/students/{sid}/loan-products/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r2.json()["products_created"] == 0


def test_v2_teacher_seed_blocks_other_teachers_student(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/loan-products/seed-default",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


def test_v2_teacher_create_payment_mark_triggers_credit_check(fx) -> None:
    """Lägg till anmärkning → skapar PaymentMark + ny CreditCheck-rad."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    # Profil krävs för CreditCheck
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska",
            employer="Sthlm Sjukhus",
            gross_salary_monthly=26000,
            net_salary_monthly=18750,
            tax_rate_effective=0.28,
            age=22, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000, personality="blandad",
        ))
        db.commit()

    r = client.post(
        f"/v2/teacher/students/{sid}/payment-marks",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "occurred_on": "2025-08-15",
            "creditor": "Telia",
            "amount": 489,
            "kind": "obetald-faktura",
        },
    )
    assert r.status_code == 200, r.text
    mark = r.json()
    assert mark["creditor"] == "Telia"
    assert mark["amount"] == 489
    assert mark["kind"] == "obetald-faktura"
    # Default expires 3 år senare
    assert mark["expires_at"] == "2028-08-14"

    # Anmärkningen ska nu sänka UC-score i /v2/lan
    r2 = client.get(
        "/v2/lan",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r2.status_code == 200
    factors = r2.json()["credit_factors"]
    marks_factor = next(
        (f for f in factors if f["factor"] == "Betalningsanmärkningar"), None,
    )
    assert marks_factor is not None
    assert "1 aktiv" in marks_factor["value"]
    assert marks_factor["severity"] == "bad"


def test_v2_kalp_endpoint(fx) -> None:
    """POST /v2/lan/kalp räknar KALP och sparar resultatet."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska",
            employer="Sthlm Sjukhus",
            gross_salary_monthly=26000,
            net_salary_monthly=18750,
            tax_rate_effective=0.28,
            age=22, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000, personality="blandad",
        ))
        db.commit()

    r = client.post(
        "/v2/lan/kalp",
        headers={"Authorization": f"Bearer {stu}"},
        json={"loan_amount": 2400000, "loan_term_months": 300},
    )
    assert r.status_code == 200, r.text
    k = r.json()
    assert k["loan_amount"] == 2400000
    assert k["loan_term_months"] == 300
    # Stresstest 7 %
    assert abs(k["stress_test_rate"] - 0.07) < 0.001
    # Konsumentverket-schablon ensam = 8500
    assert k["monthly_consumer_schablon"] == 8500.0
    # Månadskostnad vid 7 % stresstest
    assert k["monthly_loan_payment_at_stress"] > 16000  # 2.4 Mkr / 25 år
    assert k["monthly_loan_payment_at_stress"] < 18000
    # Kvar = 18750 - 8000 (housing) - 8500 (consumer) - 0 (debt) - ~17000 → underkänd
    assert k["passed"] is False


def test_v2_lan_with_seeded_products_shows_them_as_cards(fx) -> None:
    """Efter seedning visas möjliga produkter som cards."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska", employer="Sthlm Sjukhus",
            gross_salary_monthly=26000, net_salary_monthly=18750,
            tax_rate_effective=0.28,
            age=22, city="Stockholm", family_status="ensam",
            housing_type="hyresratt", housing_monthly=8000,
            personality="blandad",
        ))
        db.commit()

    # Seed
    client.post(
        f"/v2/teacher/students/{sid}/loan-products/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )

    r = client.get(
        "/v2/lan",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    cards = r.json()["cards"]
    # 5 produkter seedade → 5 cards (alla möjliga eftersom inga aktiva)
    assert len(cards) == 5
    names = [c["name"] for c in cards]
    assert "Studielån (annuitet)" in names
    assert "Bolån (rörlig)" in names
    assert "Sms-lån (avråds)" in names
    # Risk-class färgar dem
    sms = next(c for c in cards if "Sms-lån" in c["name"])
    assert sms["is_warning"] is True
    assert sms["eyebrow"] == "Avråds"


def test_v2_teacher_credit_overview(fx) -> None:
    """GET /v2/teacher/students/{id}/credit-overview returnerar full insyn."""
    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska", employer="Sthlm Sjukhus",
            gross_salary_monthly=26000, net_salary_monthly=18750,
            tax_rate_effective=0.28,
            age=22, city="Stockholm", family_status="ensam",
            housing_type="hyresratt", housing_monthly=8000,
            personality="blandad",
        ))
        db.commit()

    # Seed default + lägg till en anmärkning
    client.post(
        f"/v2/teacher/students/{sid}/loan-products/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    client.post(
        f"/v2/teacher/students/{sid}/payment-marks",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "occurred_on": "2025-06-01",
            "creditor": "Hyresvärden",
            "amount": 7240,
            "kind": "obetald-faktura",
        },
    )

    r = client.get(
        f"/v2/teacher/students/{sid}/credit-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["annual_income"] == 312000
    assert data["loan_products_count"] == 5
    assert data["available_products_count"] == 5
    assert len(data["payment_marks"]) == 1
    assert data["payment_marks"][0]["creditor"] == "Hyresvärden"
    assert data["latest_credit_check"] is not None
    assert data["latest_credit_check"]["payment_marks_count"] == 1


def test_v2_lan_credit_class_drops_with_payment_marks(fx) -> None:
    """Många anmärkningar → klass D/E."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska", employer="Sthlm Sjukhus",
            gross_salary_monthly=26000, net_salary_monthly=18750,
            tax_rate_effective=0.28,
            age=22, city="Stockholm", family_status="ensam",
            housing_type="hyresratt", housing_monthly=8000,
            personality="blandad",
        ))
        db.commit()

    # 4 anmärkningar = -60 score → klass D eller E
    for i in range(4):
        client.post(
            f"/v2/teacher/students/{sid}/payment-marks",
            headers={"Authorization": f"Bearer {tch}"},
            json={
                "occurred_on": "2025-06-01",
                "creditor": f"Långivare {i}",
                "amount": 1000,
                "kind": "obetald-faktura",
            },
        )

    r = client.get(
        "/v2/lan",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # 4 marks = -60 score = 40 = klass C eller lägre
    assert data["credit_class"] in ("C", "D", "E")


# === /v2/lan ===

def test_v2_lan_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/lan")
    assert r.status_code == 401


def test_v2_lan_for_teacher_returns_empty(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/lan",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == 0
    assert data["cards"] == []


def test_v2_lan_with_profile_has_credit_factors_and_cards(fx) -> None:
    """Elev med profil får alltid credit_factors + möjliga lån-kort."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska",
            employer="Sthlm Sjukhus AB",
            gross_salary_monthly=26000,
            net_salary_monthly=18750,
            tax_rate_effective=0.28,
            age=22, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000, personality="blandad",
            has_student_loan=False,
            has_car_loan=False,
            has_mortgage=False,
        ))
        db.commit()

    r = client.get(
        "/v2/lan",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Annual gross = 26000 * 12 = 312000
    assert data["annual_income"] == 312000
    # Inga aktiva lån → debt_ratio = 0
    assert data["total_debt"] == 0
    assert data["debt_ratio"] == 0
    # /v2/lan räknar nu en riktig CreditCheck (Fas 2A) → klass A
    # eftersom inga skulder, inga anmärkningar, full inkomst
    assert data["credit_class"] == "A"
    # Inga möjliga-låneprodukter tills lärare seedat dem
    cards = data["cards"]
    assert cards == []
    # Riktiga kreditprövnings-faktorer från CreditCheck:
    # - Inkomst (alltid om profile har gross_salary_monthly)
    # - Betalningsanmärkningar (alltid med, även 0)
    # - UC-score (alltid med när CreditCheck finns)
    # Skuldkvot/KALP visas BARA när det finns data
    factors = data["credit_factors"]
    factor_names = [f["factor"] for f in factors]
    assert "Inkomst (årlig brutto)" in factor_names
    assert "Betalningsanmärkningar" in factor_names
    assert "UC-score" in factor_names
    # Inga lån → ingen skuldkvot-rad
    assert "Skuldkvot" not in factor_names
    # Ingen KALP-beräkning gjord → ingen KALP-rad
    assert "KALP · stresstest 7 %" not in factor_names


def test_v2_lan_with_active_loan_in_scope(fx) -> None:
    """Aktivt lån i scope-DB ska räknas in i total_debt + cards."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Loan as _Loan

    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska",
            employer="Sthlm Sjukhus AB",
            gross_salary_monthly=26000,
            net_salary_monthly=18750,
            tax_rate_effective=0.28,
            age=22, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000, personality="blandad",
            has_student_loan=True,
        ))
        db.commit()

    def seed(s) -> None:
        s.add(_Loan(
            name="CSN-lån",
            lender="CSN",
            loan_number="9342 19",
            principal_amount=_D("38200"),
            current_balance_at_creation=_D("38200"),
            start_date=_d(2024, 9, 1),
            interest_rate=0.017,
            binding_type="annuity",
            amortization_monthly=_D("312"),
            active=True,
        ))

    _seed_scope(sid, seed)

    r = client.get(
        "/v2/lan",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Aktiva lån ska visas
    active_cards = [c for c in data["cards"] if c["is_active"]]
    assert len(active_cards) == 1
    assert active_cards[0]["name"] == "CSN-lån"
    # outstanding_balance från LoanMatcher (utan transaktioner = principal)
    assert active_cards[0]["balance"] == 38200
    assert data["total_debt"] == 38200
    # Skuldkvot = 38200 / 312000 ≈ 0.12
    assert 0.10 <= data["debt_ratio"] <= 0.15


# === Fas 2D · Försäkringar · InsurancePolicy + InsuranceClaim ===

def _seed_insurance_profile(sid: int, **overrides) -> None:
    """Seedа en standard-elev med profil."""
    defaults = dict(
        student_id=sid,
        profession="Undersköterska",
        employer="Sthlm Sjukhus",
        gross_salary_monthly=26000,
        net_salary_monthly=18750,
        tax_rate_effective=0.28,
        age=22, city="Stockholm",
        family_status="ensam", housing_type="hyresratt",
        housing_monthly=8000, personality="blandad",
    )
    defaults.update(overrides)
    with master_session() as db:
        db.add(StudentProfile(**defaults))
        db.commit()


def test_v2_forsakringar_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/forsakringar")
    assert r.status_code == 401


def test_v2_forsakringar_for_teacher_returns_empty(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/forsakringar",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["student_id"] == 0
    assert r.json()["policies"] == []


def test_v2_forsakringar_empty_state_for_student(fx) -> None:
    """Elev utan policys får tom payload + coverage_gaps."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    _seed_insurance_profile(sid)

    r = client.get(
        "/v2/forsakringar",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["policies"] == []
    assert data["claims"] == []
    summary = data["summary"]
    assert summary["active_count"] == 0
    # Coverage_gaps: åtminstone "saknar hemförsäkring"
    gaps = summary["coverage_gaps"]
    assert any("hemförsäkring" in g.lower() for g in gaps)


def test_v2_teacher_seed_default_insurance(fx) -> None:
    """Lärar-seed skapar 6 default-policys."""
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/insurance/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["policies_created"] == 6

    # Idempotent
    r2 = client.post(
        f"/v2/teacher/students/{sid}/insurance/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r2.json()["policies_created"] == 0


def test_v2_forsakringar_with_seeded_policies(fx) -> None:
    client, tch, _sa, stu, _tid, _said, sid = fx
    _seed_insurance_profile(sid)
    client.post(
        f"/v2/teacher/students/{sid}/insurance/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )

    r = client.get(
        "/v2/forsakringar",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["policies"]) == 6
    # Default-status är "considered" → 0 active, 6 considered
    assert data["summary"]["active_count"] == 0
    assert data["summary"]["considered_count"] == 6
    assert data["summary"]["total_premium_monthly"] == 0  # bara active räknas


def test_v2_student_creates_and_activates_policy(fx) -> None:
    """Eleven skapar egen försäkring + aktiverar den."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    _seed_insurance_profile(sid)

    r = client.post(
        "/v2/forsakringar/policies",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "provider": "Folksam",
            "name": "Hemförsäkring",
            "kind": "hem",
            "premium_monthly": 189,
            "coverage_amount": 200000,
            "deductible": 1500,
            "autogiro": True,
            "status": "considered",
        },
    )
    assert r.status_code == 200, r.text
    pid = r.json()["id"]

    # Aktivera
    r2 = client.patch(
        f"/v2/forsakringar/policies/{pid}/status",
        headers={"Authorization": f"Bearer {stu}"},
        json={"status": "active"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "active"
    assert r2.json()["started_on"] is not None

    # /v2/forsakringar visar nu 1 active + premie 189
    r3 = client.get(
        "/v2/forsakringar",
        headers={"Authorization": f"Bearer {stu}"},
    )
    summary = r3.json()["summary"]
    assert summary["active_count"] == 1
    assert summary["total_premium_monthly"] == 189
    # Hem är nu täckt → ingen "saknar hemförsäkring"-gap längre
    assert not any(
        "saknar hemförsäkring" in g.lower()
        for g in summary["coverage_gaps"]
    )


def test_v2_teacher_creates_paid_claim(fx) -> None:
    """Lärare lägger in skadehändelse → räknas i claims_paid."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    _seed_insurance_profile(sid)

    # Skapa policy via lärar-seed
    client.post(
        f"/v2/teacher/students/{sid}/insurance/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )

    r = client.post(
        f"/v2/teacher/students/{sid}/insurance/claims",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "occurred_on": "2025-08-15",
            "kind": "stold",
            "title": "Cykel-stöld",
            "description": "Cykeln togs från cykelställ",
            "amount_claimed": 4700,
            "amount_paid": 3200,
            "status": "paid",
            "paid_at": "2025-09-01",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paid"
    assert r.json()["amount_paid"] == 3200

    # /v2/forsakringar reflekterar
    r2 = client.get(
        "/v2/forsakringar",
        headers={"Authorization": f"Bearer {stu}"},
    )
    summary = r2.json()["summary"]
    assert summary["claims_paid_12m"] == 1
    assert summary["claims_paid_amount_12m"] == 3200


def test_v2_teacher_creates_unprotected_claim(fx) -> None:
    """no_policy=True händelse → räknas som oskyddad."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    _seed_insurance_profile(sid)

    r = client.post(
        f"/v2/teacher/students/{sid}/insurance/claims",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "occurred_on": "2025-10-01",
            "kind": "vattenskada",
            "title": "Översvämning från grannlägenhet",
            "amount_claimed": 35000,
            "no_policy": True,
            "status": "info",
            "description": "Saknade hemförsäkring — bar kostnaden själv",
        },
    )
    assert r.status_code == 200, r.text

    r2 = client.get(
        "/v2/forsakringar",
        headers={"Authorization": f"Bearer {stu}"},
    )
    summary = r2.json()["summary"]
    assert summary["claims_unprotected_12m"] == 1


def test_v2_forsakringar_coverage_gaps_for_bostadsratt(fx) -> None:
    """Elev med bostadsrätt utan bostadsrättsförsäkring → coverage_gap."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    _seed_insurance_profile(
        sid, housing_type="bostadsratt", has_mortgage=True,
    )

    r = client.get(
        "/v2/forsakringar",
        headers={"Authorization": f"Bearer {stu}"},
    )
    gaps = r.json()["summary"]["coverage_gaps"]
    assert any("bostadsrätt" in g.lower() for g in gaps)


def test_v2_teacher_endpoint_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/insurance/seed-default",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === Fas 2C · Arbetsgivaren · AgreementBenefit + MarketSalaryRange ===

def test_v2_teacher_seed_default_agreement_benefits(fx) -> None:
    """Lärar-seed skapar benefit-rader för befintliga avtal."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    # Seedа avtal först (annars finns inga agreements att koppla till)
    from hembudget.school.employer_seed import (
        seed_collective_agreements as _seed_agr,
    )
    with master_session() as mdb:
        _seed_agr(mdb)

    r = client.post(
        "/v2/teacher/agreement-benefits/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] > 0

    # Idempotent
    r2 = client.post(
        "/v2/teacher/agreement-benefits/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r2.json()["created"] == 0


def test_v2_teacher_seed_default_market_ranges(fx) -> None:
    """Lärar-seed skapar marknadsspann för svenska 2026."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/teacher/market-salary-ranges/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] > 25  # 30+ rader i default-katalogen


def test_v2_teacher_create_agreement_benefit(fx) -> None:
    """Lärare skapar manuell benefit."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    from hembudget.school.employer_seed import (
        seed_collective_agreements as _seed_agr,
    )
    from hembudget.school.employer_models import (
        CollectiveAgreement as _CA,
    )
    with master_session() as mdb:
        _seed_agr(mdb)
        agreement_id = (
            mdb.query(_CA).order_by(_CA.id).first().id
        )

    r = client.post(
        "/v2/teacher/agreement-benefits",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "agreement_id": agreement_id,
            "kind": "tjanstebil",
            "name": "Tjänstebil",
            "detail": "Bil ingår enligt Bilförmånsregler",
            "value": "förmånsvärde",
            "sort_order": 60,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["agreement_id"] == agreement_id
    assert data["kind"] == "tjanstebil"
    assert data["name"] == "Tjänstebil"


def test_v2_teacher_create_market_range_idempotent_update(fx) -> None:
    """Skapa range, skapa igen → uppdaterar istället för att duplicera."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx

    body = {
        "profession": "Snickare",
        "city": "Helsingborg",
        "year": 2026,
        "experience_band": "alla",
        "low": 28000,
        "high": 38000,
        "median": 33000,
        "source": "test",
    }
    r1 = client.post(
        "/v2/teacher/market-salary-ranges",
        headers={"Authorization": f"Bearer {tch}"},
        json=body,
    )
    assert r1.status_code == 200
    range_id = r1.json()["id"]

    # Update
    body["high"] = 42000
    r2 = client.post(
        "/v2/teacher/market-salary-ranges",
        headers={"Authorization": f"Bearer {tch}"},
        json=body,
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == range_id  # Samma id — ingen dublett
    assert r2.json()["high"] == 42000


def test_v2_arbetsgivaren_uses_seeded_market_range(fx) -> None:
    """När MarketSalaryRange är seedat ska /v2/arbetsgivaren visa det."""
    client, tch, _sa, stu, _tid, _said, sid = fx

    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska",
            employer="Sthlm Sjukhus AB",
            gross_salary_monthly=31250,
            net_salary_monthly=22400,
            tax_rate_effective=0.28,
            age=22, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000, personality="blandad",
        ))
        db.commit()

    # Seedа default-marknadsspann
    client.post(
        "/v2/teacher/market-salary-ranges/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )

    r = client.get(
        "/v2/arbetsgivaren",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Default har Undersköterska Stockholm 2026: low=28000, high=35500
    assert data["market_low"] == 28000
    assert data["market_high"] == 35500


def test_v2_arbetsgivaren_uses_seeded_agreement_benefits(fx) -> None:
    """När AgreementBenefit är seedat ska benefits dyka upp."""
    client, tch, _sa, stu, _tid, _said, sid = fx

    # Seedа kollektivavtal + profession-mapping först
    from hembudget.school.employer_seed import (
        seed_collective_agreements as _seed_agr,
        seed_profession_agreements as _seed_pa,
    )
    with master_session() as mdb:
        _seed_agr(mdb)
        _seed_pa(mdb)

    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska",
            employer="Sthlm Sjukhus AB",
            gross_salary_monthly=31250,
            net_salary_monthly=22400,
            tax_rate_effective=0.28,
            age=22, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000, personality="blandad",
        ))
        db.commit()

    # Seedа förmåner (Kommunal HÖK-avtalet ska få 5 förmåner)
    client.post(
        "/v2/teacher/agreement-benefits/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )

    r = client.get(
        "/v2/arbetsgivaren",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    benefits = r.json()["agreement_benefits"]
    assert len(benefits) >= 4  # pension/OB/lönerevision/friskvård
    names = [b["name"] for b in benefits]
    assert any("pension" in n.lower() or "kap" in n.lower() for n in names)
    assert any("ob-tillägg" in n.lower() for n in names)


def test_v2_teacher_employer_overview(fx) -> None:
    """Lärar-vyn returnerar full insyn i arbetsgivar-aktören."""
    client, tch, _sa, _stu, _tid, _said, sid = fx

    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska",
            employer="Sthlm Sjukhus AB",
            gross_salary_monthly=31250,
            net_salary_monthly=22400,
            tax_rate_effective=0.28,
            age=22, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000, personality="blandad",
        ))
        db.commit()

    r = client.get(
        f"/v2/teacher/students/{sid}/employer-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["profession"] == "Undersköterska"
    assert data["employer"] == "Sthlm Sjukhus AB"
    assert data["gross_salary_monthly"] == 31250
    assert isinstance(data["benefits"], list)
    assert isinstance(data["salary_negotiations"], list)
    # Default satisfaction = 70
    assert data["satisfaction_score"] == 70


def test_v2_teacher_employer_overview_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/employer-overview",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === Fas 2B · Skatten · TaxDeduction + TaxProposal + Submit ===

def _seed_tax_profile(sid: int, has_student_loan: bool = False) -> None:
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska",
            employer="Sthlm Sjukhus",
            gross_salary_monthly=26000,
            net_salary_monthly=18750,
            tax_rate_effective=0.28,
            age=22, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000, personality="blandad",
            has_student_loan=has_student_loan,
        ))
        db.commit()


def test_v2_skatten_with_manual_deduction(fx) -> None:
    """Eleven registrerar manuellt avdrag → reducerar slutlig skatt."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    _seed_tax_profile(sid)

    r = client.post(
        "/v2/skatten/deductions",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "year": 2026,
            "kind": "fackavgift",
            "name": "Vårdförbundet medlemsavgift",
            "amount": 4800,
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["amount"] == 4800
    assert d["kind"] == "fackavgift"
    assert d["source"] == "manual"

    # Bekräfta i /v2/skatten
    r2 = client.get(
        "/v2/skatten?year=2026",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r2.json()
    assert len(data["deductions"]) == 1
    # Avdragseffekt = 4800 × 30 % = 1440 kr lägre slutlig skatt
    deduction_items = [
        i for i in data["items"] if i["category"] == "deduction"
    ]
    assert len(deduction_items) >= 1
    fack = next(
        i for i in deduction_items if "Vårdförbundet" in i["name"]
    )
    assert fack["amount"] == -1440.0


def test_v2_skatten_delete_deduction(fx) -> None:
    """Eleven kan ta bort sitt avdrag."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    _seed_tax_profile(sid)

    r = client.post(
        "/v2/skatten/deductions",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "year": 2026, "kind": "rese", "name": "Bil till jobbet",
            "amount": 4884,
        },
    )
    deduction_id = r.json()["id"]

    r2 = client.delete(
        f"/v2/skatten/deductions/{deduction_id}",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r2.status_code == 204

    r3 = client.get(
        "/v2/skatten?year=2026",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r3.json()["deductions"] == []


def test_v2_skatten_proposal_approve_creates_deduction(fx) -> None:
    """Approve förslag → skapar TaxDeduction automatiskt."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    _seed_tax_profile(sid)

    # Lärare skapar manuellt förslag (auto-generation kräver Loan-data)
    r = client.post(
        f"/v2/teacher/students/{sid}/tax-proposals",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "year": 2026,
            "kind": "csn-ranta",
            "name": "Ränteavdrag CSN",
            "description": "548 kr ränta · 30 % avdrag",
            "suggested_amount": 548,
        },
    )
    assert r.status_code == 200, r.text
    proposal_id = r.json()["id"]
    assert r.json()["status"] == "pending"

    # Eleven godkänner
    r2 = client.post(
        f"/v2/skatten/proposals/{proposal_id}/decision",
        headers={"Authorization": f"Bearer {stu}"},
        json={"decision": "approve"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "approved"
    assert r2.json()["deduction_id"] is not None

    # Avdraget syns nu i /v2/skatten
    r3 = client.get(
        "/v2/skatten?year=2026",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r3.json()
    assert len(data["deductions"]) == 1
    assert data["deductions"][0]["name"] == "Ränteavdrag CSN"


def test_v2_skatten_proposal_reject(fx) -> None:
    """Reject förslag → status=rejected, ingen deduction skapas."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    _seed_tax_profile(sid)

    r = client.post(
        f"/v2/teacher/students/{sid}/tax-proposals",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "year": 2026, "kind": "rese",
            "name": "Reseavdrag bil", "suggested_amount": 4884,
        },
    )
    proposal_id = r.json()["id"]

    r2 = client.post(
        f"/v2/skatten/proposals/{proposal_id}/decision",
        headers={"Authorization": f"Bearer {stu}"},
        json={"decision": "reject"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "rejected"
    assert r2.json()["deduction_id"] is None

    r3 = client.get(
        "/v2/skatten?year=2026",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r3.json()["deductions"] == []
    # Förslaget syns med status=rejected
    proposals = r3.json()["proposals"]
    rejected = [p for p in proposals if p["status"] == "rejected"]
    assert len(rejected) == 1


def test_v2_skatten_submit_locks_year(fx) -> None:
    """POST /v2/skatten/{year}/submit låser deklarationen."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    _seed_tax_profile(sid)

    r = client.post(
        "/v2/skatten/2026/submit",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["locked"] is True
    assert r.json()["year"] == 2026

    r2 = client.get(
        "/v2/skatten?year=2026",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r2.json()
    assert data["submitted"] is not None
    assert data["submitted"]["locked"] is True
    assert data["can_submit"] is False


def test_v2_skatten_auto_generate_from_loans(fx) -> None:
    """Lärare kör auto-generate-förslag → får ränteavdrag-förslag från Loan."""
    client, tch, _sa, _stu, _tid, _said, sid = fx
    _seed_tax_profile(sid, has_student_loan=True)

    # Seedа ett CSN-lån i scope-DB
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Loan as _Loan

    def seed(s) -> None:
        s.add(_Loan(
            name="CSN-lån (annuitet)",
            lender="CSN",
            loan_number="9342",
            principal_amount=_D("38200"),
            current_balance_at_creation=_D("38200"),
            start_date=_d(2024, 9, 1),
            interest_rate=0.017,  # 1,7 %
            binding_type="annuity",
            amortization_monthly=_D("312"),
            active=True,
        ))

    _seed_scope(sid, seed)

    r = client.post(
        f"/v2/teacher/students/{sid}/tax-proposals/auto-generate?year=2026",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1

    # Idempotent: andra anropet skapar inga nya
    r2 = client.post(
        f"/v2/teacher/students/{sid}/tax-proposals/auto-generate?year=2026",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r2.json()["created"] == 0


def test_v2_skatten_teacher_overview(fx) -> None:
    """Lärar-vyn returnerar full insyn."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    _seed_tax_profile(sid)

    # Eleven gör manuellt avdrag
    client.post(
        "/v2/skatten/deductions",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "year": 2026, "kind": "fackavgift",
            "name": "Akavia-avgift", "amount": 3600,
        },
    )

    r = client.get(
        f"/v2/teacher/students/{sid}/tax-overview?year=2026",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["year"] == 2026
    assert data["gross_income"] == 312000  # 26000 * 12
    assert len(data["deductions"]) == 1
    assert data["deductions"][0]["name"] == "Akavia-avgift"
    # Final tax = prelim − avdragseffekt = 26000*12*0.28 − 3600*0.30
    # = 87360 − 1080 = 86280
    assert data["final_tax"] == pytest.approx(86280, abs=1)


def test_v2_skatten_endpoints_403_for_teacher_role(fx) -> None:
    """Lärare kan inte använda elev-endpoints."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/skatten/deductions",
        headers={"Authorization": f"Bearer {tch}"},
        json={"year": 2026, "kind": "rese", "name": "X", "amount": 100},
    )
    assert r.status_code == 403


# === /v2/skatten ===

def test_v2_skatten_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/skatten")
    assert r.status_code == 401


def test_v2_skatten_for_teacher_returns_empty(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/skatten",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == 0
    assert data["items"] == []
    assert data["gross_income"] == 0


def test_v2_skatten_without_profile_returns_empty(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/skatten",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["items"] == []


def test_v2_skatten_with_profile_returns_basic_lines(fx) -> None:
    """Elev med profil får inkomst-rad + skatt-rad + diff-rad minst."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska",
            employer="Sthlm Sjukhus AB",
            gross_salary_monthly=26041,  # ger 312500 årslön
            net_salary_monthly=18750,
            tax_rate_effective=0.28,
            age=22, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000, personality="blandad",
            has_student_loan=False,
        ))
        db.commit()

    r = client.get(
        "/v2/skatten",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    # 312500 årslön
    assert data["gross_income"] == 312492 or data["gross_income"] == 312500
    # Förskottsinbetald skatt = brutto × 28 %
    assert data["prelim_tax_paid"] > 80000
    # Items innehåller åtminstone 3 rader (inkomst + skatt + diff)
    cats = [item["category"] for item in data["items"]]
    assert "income" in cats
    assert "tax" in cats
    assert "diff" in cats
    # deadline ~2 maj nästa år
    assert data["deadline"] is not None
    assert "-05-02" in data["deadline"]


def test_v2_skatten_no_schablon_deductions(fx) -> None:
    """has_student_loan/has_car_loan ska INTE generera schablon-avdrag.
    Riktiga avdrag kräver TaxDeduction-modellen (Fas 2)."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska",
            employer="Sthlm Sjukhus AB",
            gross_salary_monthly=26041,
            net_salary_monthly=18750,
            tax_rate_effective=0.28,
            age=22, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8000, personality="blandad",
            has_student_loan=True,
            has_car_loan=True,
        ))
        db.commit()

    r = client.get(
        "/v2/skatten",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Inga förslag tills TaxProposal-modellen finns
    assert data["pending_proposal_count"] == 0
    proposals = [i for i in data["items"] if i["is_proposal"]]
    assert proposals == []
    # Inga schablon-avdrag i items — bara inkomst + ev. ISK + skatt + diff
    deduction_items = [i for i in data["items"] if i["category"] == "deduction"]
    assert deduction_items == []


def test_v2_skatten_year_query_param(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/skatten?year=2024",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["year"] == 2024


def test_v2_bank_upcoming_bills(fx) -> None:
    """Öppna kommande fakturor speglas i payload + upcoming_open_total."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    from datetime import date as _d, timedelta as _td
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc, UpcomingTransaction as _Up,
    )

    def seed(s) -> None:
        acc = _Acc(name="K", bank="B", type="checking", currency="SEK")
        s.add(acc)
        s.flush()
        s.add(_Up(
            kind="bill", name="Hyra",
            amount=_D("8000"),
            expected_date=_d.today() + _td(days=5),
            debit_account_id=acc.id,
        ))
        s.add(_Up(
            kind="bill", name="El",
            amount=_D("750"),
            expected_date=_d.today() + _td(days=10),
        ))

    _seed_scope(sid, seed)

    r = client.get(
        "/v2/bank",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    bills = data["upcoming_bills"]
    assert len(bills) == 2
    # Sorterade kronologiskt — Hyra (5 dagar) före El (10 dagar)
    assert bills[0]["name"] == "Hyra"
    assert bills[1]["name"] == "El"
    assert all(b["is_paid"] is False for b in bills)
    # Total öppna fakturor: 8000 + 750
    assert data["summary"]["upcoming_open_total"] == 8750
    assert data["summary"]["upcoming_open_count"] == 2


# === Fas 2E · Förbrukning · UtilitySubscription + UtilityReading ===


def test_v2_forbrukning_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/forbrukning")
    assert r.status_code == 401


def test_v2_forbrukning_for_teacher_returns_empty(fx) -> None:
    client, tch, *_ = fx
    r = client.get(
        "/v2/forbrukning",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["student_id"] == 0
    assert r.json()["subscriptions"] == []
    assert r.json()["readings"] == []


def test_v2_forbrukning_empty_state_for_student(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/forbrukning",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["subscriptions"] == []
    assert data["summary"]["active_count"] == 0
    assert data["summary"]["total_monthly_cost"] == 0


def test_v2_teacher_seed_default_utility(fx) -> None:
    """Lärar-seed skapar 6 default-abonnemang i scope-DB."""
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/utility/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["subscriptions_created"] == 6
    # Idempotent: andra anropet skapar 0 till
    r2 = client.post(
        f"/v2/teacher/students/{sid}/utility/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r2.status_code == 200
    assert r2.json()["subscriptions_created"] == 0


def test_v2_forbrukning_with_seeded_subscriptions(fx) -> None:
    """Efter seed visar elev-vyn rätt sammanställning."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    client.post(
        f"/v2/teacher/students/{sid}/utility/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    r = client.get(
        "/v2/forbrukning",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # 6 abonnemang totalt, alla active
    assert len(data["subscriptions"]) == 6
    assert data["summary"]["active_count"] == 6
    # Tibber finns med spotpris
    suppliers = {s["supplier"] for s in data["subscriptions"]}
    assert "Tibber" in suppliers
    assert "Telia" in suppliers
    assert "Spotify" in suppliers
    assert "SL" in suppliers
    assert data["summary"]["has_spot_pricing"] is True
    # Stockholmshem ingår i hyran → bidrar inte till total_monthly_cost
    sthlms = [
        s for s in data["subscriptions"]
        if s["supplier"] == "Stockholmshem"
    ][0]
    assert sthlms["included_in_rent"] is True
    # Bredband 389 + mobil 119 + spotify 119 + sl 320 = 947
    # (Tibber själva = 0 fast, men har grid_fee 320 separat)
    assert data["summary"]["total_monthly_cost"] == 947
    assert data["summary"]["total_grid_fee"] == 320
    # Bindning utgår snart för Telia bredband (10 mån fram, > 30 dgr)
    # → ej "expiring soon" trots seed
    assert data["summary"]["binding_expiring_soon"] == 0


def test_v2_student_creates_and_patches_subscription(fx) -> None:
    """Eleven kan skapa egen abonnemang och uppdatera den."""
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/forbrukning/subscriptions",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "supplier": "Comviq",
            "name": "Mobil Fastpris",
            "category": "mobile",
            "monthly_cost": 49,
            "spot_pricing": False,
            "notice_days": 30,
            "status": "active",
        },
    )
    assert r.status_code == 200, r.text
    sub_id = r.json()["id"]
    assert r.json()["supplier"] == "Comviq"

    # Patcha till cancelled
    r2 = client.patch(
        f"/v2/forbrukning/subscriptions/{sub_id}",
        headers={"Authorization": f"Bearer {stu}"},
        json={"status": "cancelled"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "cancelled"
    assert r2.json()["ended_on"] is not None

    # Lista
    list_r = client.get(
        "/v2/forbrukning",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert any(
        s["id"] == sub_id and s["status"] == "cancelled"
        for s in list_r.json()["subscriptions"]
    )


def test_v2_teacher_creates_utility_reading(fx) -> None:
    """Lärare skapar månadsfaktura/avläsning som syns i elev-historiken."""
    from datetime import date as _d
    client, tch, _sa, stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/utility/readings",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "supplier": "Tibber",
            "meter_type": "electricity",
            "meter_role": "energy",
            "period_start": _d.today().replace(day=1).isoformat(),
            "period_end": _d.today().isoformat(),
            "consumption": 184,
            "consumption_unit": "kWh",
            "cost_kr": 812,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["consumption"] == 184
    assert r.json()["cost_kr"] == 812

    # Eleven ser readingen + last_month_cost
    list_r = client.get(
        "/v2/forbrukning",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = list_r.json()
    assert len(data["readings"]) == 1
    assert data["readings"][0]["supplier"] == "Tibber"
    assert data["summary"]["last_month_cost"] == 812
    assert data["summary"]["last_month_kwh"] == 184


def test_v2_forbrukning_savings_heuristic(fx) -> None:
    """Besparingspotential räknas korrekt enligt heuristik."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    # Seedа default-katalog → bredband 389 (>350) ⇒ -80, mobil 119
    # (>99 utan binding) ⇒ -50, spotify 119 utan familj ⇒ -20,
    # tibber spotpris ⇒ -50. Total ≈ 200
    client.post(
        f"/v2/teacher/students/{sid}/utility/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    r = client.get(
        "/v2/forbrukning",
        headers={"Authorization": f"Bearer {stu}"},
    )
    saved = r.json()["summary"]["suggested_savings_monthly"]
    # 80 (bredband > 350) + 50 (mobil > 99 utan binding) + 50 (spotpris-el)
    # = 180. Spotify räknas inte (notes nämner "familj-prenum" → träff).
    assert saved == 180


def test_v2_forbrukning_wellbeing_includes_spot_pricing(fx) -> None:
    """Spotpris-el ger +1 economy och 3+ aktiva +3 safety i wellbeing."""
    from hembudget.wellbeing.calculator import calculate_wellbeing
    from hembudget.db.base import session_scope as _ss
    from hembudget.school.engines import (
        master_session as _ms, scope_context as _sc,
        scope_for_student as _sfs,
    )
    from hembudget.school.models import Student as _St

    client, tch, _sa, _stu, _tid, _said, sid = fx
    client.post(
        f"/v2/teacher/students/{sid}/utility/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )

    # Kör calculator direkt mot scope-DB
    with _ms() as m:
        student = m.get(_St, sid)
        scope_key = _sfs(student)
    with _sc(scope_key):
        with _ss() as s:
            result = calculate_wellbeing(s, "2026-04")

    spot_factors = [
        f for f in result.factors
        if "spotpris" in f.explanation.lower()
    ]
    assert len(spot_factors) >= 1
    assert spot_factors[0].points == 1
    assert spot_factors[0].dimension == "economy"

    # 6 aktiva subscriptions (3+) → +3 safety
    safety_factors = [
        f for f in result.factors
        if "abonnemang" in f.explanation.lower()
        and f.dimension == "safety"
    ]
    assert len(safety_factors) >= 1
    assert safety_factors[0].points == 3


def test_v2_teacher_utility_overview(fx) -> None:
    """Lärar-overview returnerar full insyn med summary + subs + readings."""
    from datetime import date as _d
    client, tch, _sa, _stu, _tid, _said, sid = fx
    client.post(
        f"/v2/teacher/students/{sid}/utility/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    client.post(
        f"/v2/teacher/students/{sid}/utility/readings",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "supplier": "Tibber",
            "meter_type": "electricity",
            "meter_role": "energy",
            "period_start": _d.today().replace(day=1).isoformat(),
            "period_end": _d.today().isoformat(),
            "consumption": 184,
            "cost_kr": 812,
        },
    )
    r = client.get(
        f"/v2/teacher/students/{sid}/utility-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["student_name"]
    assert len(data["subscriptions"]) == 6
    assert len(data["readings"]) == 1
    assert data["summary"]["has_spot_pricing"] is True


def test_v2_teacher_utility_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/utility/seed-default",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === Fas 2F · Hyresvärden · RentalContract + RentalNotice ===


def _seed_rental_profile(sid: int, **overrides) -> None:
    """Seedа en standard-elev-profil för hyres-tester."""
    defaults = dict(
        student_id=sid,
        profession="Undersköterska",
        employer="Sthlm Sjukhus",
        gross_salary_monthly=26000,
        net_salary_monthly=19000,
        tax_rate_effective=0.27,
        age=24, city="Stockholm",
        family_status="ensam", housing_type="hyresratt",
        housing_monthly=7240, personality="blandad",
    )
    defaults.update(overrides)
    with master_session() as db:
        db.add(StudentProfile(**defaults))
        db.commit()


def test_v2_hyresvarden_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/hyresvarden")
    assert r.status_code == 401


def test_v2_hyresvarden_for_teacher_returns_empty(fx) -> None:
    client, tch, *_ = fx
    r = client.get(
        "/v2/hyresvarden",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["student_id"] == 0
    assert r.json()["contract"] is None


def test_v2_hyresvarden_empty_state_for_student(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, sid = fx
    _seed_rental_profile(sid)
    r = client.get(
        "/v2/hyresvarden",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["contract"] is None
    assert data["summary"]["has_active_contract"] is False
    assert data["notices"] == []


def test_v2_teacher_seed_default_rental(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/rental/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["contracts_created"] == 1
    assert body["notices_created"] == 4
    # Idempotent
    r2 = client.post(
        f"/v2/teacher/students/{sid}/rental/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r2.json()["contracts_created"] == 0
    assert r2.json()["notices_created"] == 0


def test_v2_hyresvarden_with_seeded_contract(fx) -> None:
    """Efter seed visar vyn Stockholmshem-kontraktet + 4 notiser."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    _seed_rental_profile(sid)
    client.post(
        f"/v2/teacher/students/{sid}/rental/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    r = client.get(
        "/v2/hyresvarden",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["has_active_contract"] is True
    assert data["summary"]["monthly_rent"] == 7240
    assert data["contract"]["landlord"] == "Stockholmshem"
    assert data["contract"]["rooms_label"] == "2 r o k"
    assert data["contract"]["contract_type"] == "forsta_hand"
    assert data["contract"]["duration_type"] == "tillsvidare"
    # 7240*12/47 ≈ 1849
    assert data["summary"]["rent_per_sqm_yearly"] == 1849
    # Hyra 7240 / netto 19000 = 38.1 %
    assert data["summary"]["rent_share_of_net_pct"] == 38.1
    # market_buy_estimate = 47 * 51000 = 2397000
    assert data["summary"]["market_buy_estimate"] == 2397000
    assert len(data["notices"]) == 4
    # Hyresavi finns och är paid
    avis = [n for n in data["notices"] if n["notice_type"] == "hyresavi"]
    assert len(avis) == 1
    assert avis[0]["status"] == "paid"


def test_v2_student_creates_and_terminates_contract(fx) -> None:
    """Eleven kan skapa eget kontrakt och säga upp det."""
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/hyresvarden/contracts",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "landlord": "BRF Solgården",
            "address": "Storgatan 5",
            "rooms_label": "3 r o k",
            "area_sqm": 65,
            "city": "Göteborg",
            "contract_type": "bostadsratt",
            "duration_type": "tillsvidare",
            "monthly_rent": 4500,
            "deposit": 0,
        },
    )
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert r.json()["contract_type"] == "bostadsratt"

    # Säg upp
    r2 = client.patch(
        f"/v2/hyresvarden/contracts/{cid}",
        headers={"Authorization": f"Bearer {stu}"},
        json={"status": "terminated"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "terminated"
    assert r2.json()["ended_on"] is not None


def test_v2_teacher_creates_rent_hike_notice(fx) -> None:
    """Lärare lägger in hyreshöjning > 4 % → drar economy i wellbeing."""
    from datetime import date as _d
    from hembudget.wellbeing.calculator import calculate_wellbeing
    from hembudget.db.base import session_scope as _ss
    from hembudget.school.engines import (
        master_session as _ms, scope_context as _sc,
        scope_for_student as _sfs,
    )
    from hembudget.school.models import Student as _St

    client, tch, _sa, _stu, _tid, _said, sid = fx
    _seed_rental_profile(sid)
    client.post(
        f"/v2/teacher/students/{sid}/rental/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    r = client.post(
        f"/v2/teacher/students/{sid}/rental/notices",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "occurred_on": _d.today().isoformat(),
            "notice_type": "hyreshojning",
            "title": "Hyreshöjning 5 %",
            "description": "Förhandlat 5 % höjning från och med juli",
            "change_pct": 5.0,
            "status": "acknowledged",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["change_pct"] == 5.0

    # Wellbeing ska ha hyreshöjning-faktor
    with _ms() as m:
        student = m.get(_St, sid)
        scope_key = _sfs(student)
    with _sc(scope_key):
        with _ss() as s:
            result = calculate_wellbeing(s, "2026-04")
    hike_factors = [
        f for f in result.factors
        if "hyreshöjning" in f.explanation.lower()
    ]
    assert len(hike_factors) >= 1
    assert hike_factors[0].dimension == "economy"
    assert hike_factors[0].points == -2


def test_v2_hyresvarden_wellbeing_first_hand_bonus(fx) -> None:
    """Förstahandskontrakt + tillsvidare → safety-bonus."""
    from hembudget.wellbeing.calculator import calculate_wellbeing
    from hembudget.db.base import session_scope as _ss
    from hembudget.school.engines import (
        master_session as _ms, scope_context as _sc,
        scope_for_student as _sfs,
    )
    from hembudget.school.models import Student as _St

    client, tch, _sa, _stu, _tid, _said, sid = fx
    _seed_rental_profile(sid)
    client.post(
        f"/v2/teacher/students/{sid}/rental/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )

    with _ms() as m:
        student = m.get(_St, sid)
        scope_key = _sfs(student)
    with _sc(scope_key):
        with _ss() as s:
            result = calculate_wellbeing(s, "2026-04")

    # +5 förstahand + +3 tillsvidare = +8 safety
    fh_factors = [
        f for f in result.factors
        if "förstahand" in f.explanation.lower()
    ]
    assert len(fh_factors) >= 1
    assert fh_factors[0].dimension == "safety"
    assert fh_factors[0].points == 5
    tv_factors = [
        f for f in result.factors
        if "tillsvidare" in f.explanation.lower()
    ]
    assert len(tv_factors) >= 1
    assert tv_factors[0].points == 3


def test_v2_hyresvarden_wellbeing_high_rent_share(fx) -> None:
    """Hyra > 40 % av netto → -economy."""
    from hembudget.wellbeing.calculator import calculate_wellbeing
    from hembudget.db.base import session_scope as _ss
    from hembudget.school.engines import (
        master_session as _ms, scope_context as _sc,
        scope_for_student as _sfs,
    )
    from hembudget.school.models import Student as _St

    client, tch, _sa, _stu, _tid, _said, sid = fx
    # Lågt netto → hyran 7240/14000 = 51.7 % blir > 40 %
    _seed_rental_profile(sid, net_salary_monthly=14000)
    client.post(
        f"/v2/teacher/students/{sid}/rental/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )

    with _ms() as m:
        student = m.get(_St, sid)
        scope_key = _sfs(student)
    with _sc(scope_key):
        with _ss() as s:
            result = calculate_wellbeing(s, "2026-04")
    high_rent_factors = [
        f for f in result.factors
        if "%" in f.explanation
        and "över 40" in f.explanation.lower()
    ]
    assert len(high_rent_factors) >= 1
    assert high_rent_factors[0].dimension == "economy"
    assert high_rent_factors[0].points < 0


def test_v2_teacher_rental_overview(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, sid = fx
    _seed_rental_profile(sid)
    client.post(
        f"/v2/teacher/students/{sid}/rental/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    r = client.get(
        f"/v2/teacher/students/{sid}/rental-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["student_name"]
    assert data["contract"]["landlord"] == "Stockholmshem"
    assert len(data["notices"]) == 4


def test_v2_teacher_rental_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/rental/seed-default",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === Fas 2G · Pension + Avanza ISK + aktiehandel ===


def _seed_pension_profile(sid: int, **overrides) -> None:
    """Seedа en standard-profil för pension/avanza-tester."""
    defaults = dict(
        student_id=sid,
        profession="Sjuksköterska",
        employer="Sthlm Sjukhus",
        gross_salary_monthly=32000,
        net_salary_monthly=23500,
        tax_rate_effective=0.27,
        age=28, city="Stockholm",
        family_status="ensam", housing_type="hyresratt",
        housing_monthly=7240, personality="blandad",
    )
    defaults.update(overrides)
    with master_session() as db:
        db.add(StudentProfile(**defaults))
        db.commit()


def test_v2_pension_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/pension")
    assert r.status_code == 401


def test_v2_pension_for_teacher_returns_empty(fx) -> None:
    client, tch, *_ = fx
    r = client.get(
        "/v2/pension",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["student_id"] == 0
    assert r.json()["pillars"] == []


def test_v2_pension_with_profile_returns_4_pelare(fx) -> None:
    """28-åring med 32k lön → 4 pelare beräknas."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    _seed_pension_profile(sid)
    r = client.get(
        "/v2/pension",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["age"] == 28
    assert data["gross_salary_monthly"] == 32000
    assert data["years_to_retire"] == 67 - 28
    assert data["has_collective_agreement"] is True
    assert len(data["pillars"]) == 4
    pillar_names = {p["name"] for p in data["pillars"]}
    assert "Inkomstpension" in pillar_names
    assert "Premiepension" in pillar_names
    assert "Tjänstepension ITP1" in pillar_names
    assert "Privat (Avanza ISK)" in pillar_names
    # Total ska vara > 0 (alla 4 pelare > 0 vid full karriär)
    assert data["total_monthly_at_retire"] > 0
    # Inkomstpension + premiepension > 0 (auto)
    auto_pillars = [
        p for p in data["pillars"] if p["source"] == "auto"
    ]
    assert all(p["monthly_at_retire"] > 0 for p in auto_pillars)


def test_v2_pension_egenforetagare_no_itp1(fx) -> None:
    """Egenföretagare → has_collective_agreement = False, ITP1 = 0."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    _seed_pension_profile(sid, profession="Egenföretagare frilans")
    r = client.get(
        "/v2/pension",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["has_collective_agreement"] is False
    itp = [p for p in data["pillars"] if "ITP1" in p["name"]][0]
    assert itp["monthly_at_retire"] == 0
    assert itp["source"] == "missing"


def test_v2_pension_scenarios_increase_with_age(fx) -> None:
    """65 år tidigt < 67 mål < 70 sent."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    _seed_pension_profile(sid)
    r = client.get(
        "/v2/pension",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r.json()
    sc = data["scenarios"]
    assert sc["age_65_early"] < sc["age_67_target"]
    assert sc["age_70_late"] > sc["age_67_target"]


def test_v2_student_patches_isk_monthly_savings(fx) -> None:
    """Eleven sätter custom_isk_monthly = 600 → påverkar pelare 3."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    _seed_pension_profile(sid)
    # Set isk monthly
    r = client.patch(
        "/v2/pension/assumptions",
        headers={"Authorization": f"Bearer {stu}"},
        json={"custom_isk_monthly": 600},
    )
    assert r.status_code == 200, r.text
    assert r.json()["custom_isk_monthly"] == 600

    # Hämta pension igen — pelare 3 ska ha högre belopp än innan
    r2 = client.get(
        "/v2/pension",
        headers={"Authorization": f"Bearer {stu}"},
    )
    privat = [
        p for p in r2.json()["pillars"]
        if p["source"] == "isk"
    ][0]
    assert privat["monthly_at_retire"] > 0


def test_v2_teacher_seed_default_pension(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/pension/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1
    # Idempotent
    r2 = client.post(
        f"/v2/teacher/students/{sid}/pension/seed-default",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r2.json()["created"] == 0


def test_v2_teacher_patches_pension_assumptions(fx) -> None:
    """Lärare sätter retire_age=69 → years_to_retire ändras."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    _seed_pension_profile(sid)
    r = client.patch(
        f"/v2/teacher/students/{sid}/pension/assumptions",
        headers={"Authorization": f"Bearer {tch}"},
        json={"retire_age": 69, "real_return_pct": 3.5},
    )
    assert r.status_code == 200, r.text
    assert r.json()["retire_age"] == 69
    assert r.json()["real_return_pct"] == 3.5

    # Pension-prognos ska reflektera 69-årig riktålder
    r2 = client.get(
        "/v2/pension",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r2.json()["years_to_retire"] == 69 - 28


def test_v2_teacher_pension_overview(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, sid = fx
    _seed_pension_profile(sid)
    r = client.get(
        f"/v2/teacher/students/{sid}/pension-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["student_name"]
    assert len(data["forecast"]["pillars"]) == 4


def test_v2_avanza_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/avanza")
    assert r.status_code == 401


def test_v2_avanza_no_isk_account_returns_empty(fx) -> None:
    """Eleven utan ISK-konto → tom payload."""
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/avanza",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["isk_account_id"] is None
    assert data["funds"] == []
    assert data["stocks"] == []


def test_v2_avanza_with_isk_account_and_funds(fx) -> None:
    """Skapa ISK-konto + 1 fond → returneras."""
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Account as _Acc, FundHolding as _FH

    client, _tch, _sa, stu, _tid, _said, sid = fx

    def seed(s) -> None:
        isk = _Acc(
            name="Avanza ISK", bank="Avanza", type="isk",
            currency="SEK", opening_balance=_D("1200"),
            opening_balance_date=_d(2026, 1, 1),
        )
        s.add(isk)
        s.flush()
        s.add(_FH(
            account_id=isk.id, fund_name="Globalfond",
            units=_D("12.5"), market_value=_D("3240"),
            last_price=_D("259"), change_pct=2.4,
            currency="SEK", last_update_date=_d.today(),
        ))

    _seed_scope(sid, seed)

    r = client.get(
        "/v2/avanza",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["isk_account_id"] is not None
    assert data["summary"]["isk_account_name"] == "Avanza ISK"
    assert data["summary"]["fund_count"] == 1
    assert data["summary"]["funds_value"] == 3240
    assert len(data["funds"]) == 1
    assert data["funds"][0]["fund_name"] == "Globalfond"
    # Schablonskatt: 0.89 % av (3240 + 1200) = ~40
    assert data["summary"]["schablonskatt_estimate"] == round(
        4440 * 0.0089, 0,
    )


def test_v2_avanza_pension_isk_savings_visible(fx) -> None:
    """Custom_isk_monthly från PensionAssumption visas i Avanza-summary."""
    client, _tch, _sa, stu, _tid, _said, sid = fx
    _seed_pension_profile(sid)
    client.patch(
        "/v2/pension/assumptions",
        headers={"Authorization": f"Bearer {stu}"},
        json={"custom_isk_monthly": 800},
    )
    r = client.get(
        "/v2/avanza",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.json()["summary"]["monthly_savings"] == 800


def test_v2_pension_wellbeing_isk_active_bonus(fx) -> None:
    """ISK med innehav → +2 growth i wellbeing."""
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Account as _Acc, FundHolding as _FH
    from hembudget.wellbeing.calculator import calculate_wellbeing
    from hembudget.db.base import session_scope as _ss
    from hembudget.school.engines import (
        master_session as _ms, scope_context as _sc,
        scope_for_student as _sfs,
    )
    from hembudget.school.models import Student as _St

    client, _tch, _sa, _stu, _tid, _said, sid = fx
    _seed_pension_profile(sid)

    def seed(s) -> None:
        isk = _Acc(
            name="Avanza ISK", bank="Avanza", type="isk",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d(2026, 1, 1),
        )
        s.add(isk)
        s.flush()
        s.add(_FH(
            account_id=isk.id, fund_name="Globalfond",
            market_value=_D("8460"),
            last_update_date=_d.today(),
        ))

    _seed_scope(sid, seed)

    with _ms() as m:
        student = m.get(_St, sid)
        scope_key = _sfs(student)
    with _sc(scope_key):
        with _ss() as s:
            result = calculate_wellbeing(s, "2026-04")

    isk_factors = [
        f for f in result.factors
        if "isk-portf" in f.explanation.lower()
    ]
    assert len(isk_factors) >= 1
    assert isk_factors[0].dimension == "economy"
    assert isk_factors[0].points == 2


def test_v2_pension_wellbeing_no_isk_age_25_penalty(fx) -> None:
    """Eleven > 25 år utan ISK → -2 growth."""
    from hembudget.wellbeing.calculator import calculate_wellbeing
    from hembudget.db.base import session_scope as _ss
    from hembudget.school.engines import (
        master_session as _ms, scope_context as _sc,
        scope_for_student as _sfs,
    )
    from hembudget.school.models import Student as _St

    client, _tch, _sa, _stu, _tid, _said, sid = fx
    _seed_pension_profile(sid)  # age=28

    with _ms() as m:
        student = m.get(_St, sid)
        scope_key = _sfs(student)
    with _sc(scope_key):
        with _ss() as s:
            result = calculate_wellbeing(s, "2026-04")
    no_isk = [
        f for f in result.factors
        if "tappar tidsfönstret" in f.explanation.lower()
    ]
    assert len(no_isk) >= 1
    assert no_isk[0].dimension == "economy"
    assert no_isk[0].points == -2


def test_v2_teacher_avanza_overview(fx) -> None:
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Account as _Acc, FundHolding as _FH

    client, tch, _sa, _stu, _tid, _said, sid = fx
    _seed_pension_profile(sid)

    def seed(s) -> None:
        isk = _Acc(
            name="Avanza ISK", bank="Avanza", type="isk",
            currency="SEK", opening_balance=_D("500"),
            opening_balance_date=_d(2026, 1, 1),
        )
        s.add(isk)
        s.flush()
        s.add(_FH(
            account_id=isk.id, fund_name="Sverige",
            market_value=_D("2180"),
            last_update_date=_d.today(),
        ))

    _seed_scope(sid, seed)

    r = client.get(
        f"/v2/teacher/students/{sid}/avanza-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["avanza"]["summary"]["isk_account_name"] == "Avanza ISK"
    assert data["avanza"]["summary"]["fund_count"] == 1


def test_v2_teacher_pension_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/pension/seed-default",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === Fas 2H · Bokföring · Transaction-klassning ===


def test_v2_bokforing_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/bokforing")
    assert r.status_code == 401


def test_v2_bokforing_for_teacher_returns_empty(fx) -> None:
    client, tch, *_ = fx
    r = client.get(
        "/v2/bokforing",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["student_id"] == 0
    assert r.json()["unclassified"] == []


def test_v2_bokforing_empty_state_for_student(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/bokforing",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["unclassified"] == []
    assert data["classified"] == []
    assert data["summary"]["total_transactions"] == 0
    assert data["summary"]["classification_rate_pct"] == 0


def test_v2_bokforing_summary_with_transactions(fx) -> None:
    """Eleven har 5 transaktioner — 3 klassade, 2 ovettade."""
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc,
        Category as _Cat,
        Transaction as _Tx,
    )

    client, _tch, _sa, stu, _tid, _said, sid = fx

    def seed(s) -> None:
        acc = _Acc(
            name="Lönekonto", bank="SEB", type="checking",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today().replace(day=1),
        )
        s.add(acc)
        s.flush()
        # Använd default-seedade kategorier (finns redan i scope-DB)
        cat_food = (
            s.query(_Cat).filter(_Cat.name == "Livsmedel").first()
        )
        cat_lon = s.query(_Cat).filter(_Cat.name == "Lön").first()
        assert cat_food is not None and cat_lon is not None
        # 3 klassade
        s.add(_Tx(
            account_id=acc.id, date=_d.today(),
            amount=_D("22400"), raw_description="Lön Sthlm Sjukhus",
            hash="t1", category_id=cat_lon.id, user_verified=True,
        ))
        s.add(_Tx(
            account_id=acc.id, date=_d.today(),
            amount=_D("-425"), raw_description="Hemköp Globen",
            hash="t2", category_id=cat_food.id, user_verified=True,
        ))
        s.add(_Tx(
            account_id=acc.id, date=_d.today(),
            amount=_D("-312"), raw_description="Coop Hökarängen",
            hash="t3", category_id=cat_food.id, user_verified=True,
        ))
        # 2 ovettade
        s.add(_Tx(
            account_id=acc.id, date=_d.today(),
            amount=_D("-168"), raw_description="Max Restaurang",
            hash="t4",
        ))
        s.add(_Tx(
            account_id=acc.id, date=_d.today(),
            amount=_D("-195"), raw_description="Bio Rio Hornstull",
            hash="t5",
        ))

    _seed_scope(sid, seed)

    r = client.get(
        "/v2/bokforing",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    s = data["summary"]
    assert s["total_transactions"] == 5
    assert s["unclassified"] == 2
    assert s["manual_classified"] == 3
    assert s["classification_rate_pct"] == 60.0
    # Inkomster 22400, utgifter 425+312+168+195 = 1100, sparat 21300
    assert s["income_total"] == 22400
    assert s["expense_total"] == 1100
    assert s["saved_total"] == 21300
    assert len(data["unclassified"]) == 2
    assert len(data["classified"]) == 3
    # Default-seedade kategorier finns (Lön, Livsmedel etc) — minst 10
    assert len(data["categories"]) >= 10


def test_v2_bokforing_student_classifies_transaction(fx) -> None:
    """Eleven sätter category_id på ovettad → user_verified=True."""
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc,
        Category as _Cat,
        Transaction as _Tx,
    )

    client, _tch, _sa, stu, _tid, _said, sid = fx

    tx_id_holder = {}
    cat_id_holder = {}

    def seed(s) -> None:
        acc = _Acc(
            name="Lönekonto", bank="SEB", type="checking",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today(),
        )
        s.add(acc)
        s.flush()
        # Använd existerande default-seedad "Restaurang"
        cat = s.query(_Cat).filter(_Cat.name == "Restaurang").first()
        assert cat is not None
        cat_id_holder["id"] = cat.id
        tx = _Tx(
            account_id=acc.id, date=_d.today(),
            amount=_D("-168"), raw_description="Max Restaurang",
            hash="ttest1",
        )
        s.add(tx)
        s.flush()
        tx_id_holder["id"] = tx.id

    _seed_scope(sid, seed)

    r = client.patch(
        f"/v2/bokforing/transactions/{tx_id_holder['id']}",
        headers={"Authorization": f"Bearer {stu}"},
        json={"category_id": cat_id_holder["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["category_id"] == cat_id_holder["id"]
    assert r.json()["user_verified"] is True

    # Lista igen — ska vara klassificerad nu
    list_r = client.get(
        "/v2/bokforing",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert list_r.json()["summary"]["unclassified"] == 0
    assert list_r.json()["summary"]["manual_classified"] == 1


def test_v2_bokforing_bulk_classify_via_history(fx) -> None:
    """Bulk-classify: en ovettad matchar mot user_verified history."""
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc,
        Category as _Cat,
        Transaction as _Tx,
    )

    client, _tch, _sa, stu, _tid, _said, sid = fx

    def seed(s) -> None:
        acc = _Acc(
            name="Lönekonto", bank="SEB", type="checking",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today(),
        )
        s.add(acc)
        s.flush()
        cat = s.query(_Cat).filter(_Cat.name == "Livsmedel").first()
        assert cat is not None
        # En verifierad rad — drives history-match
        s.add(_Tx(
            account_id=acc.id, date=_d.today(),
            amount=_D("-200"), raw_description="HEMKOP GLOBEN",
            normalized_merchant="HEMKOP GLOBEN",
            hash="hist1", category_id=cat.id, user_verified=True,
        ))
        # En ovettad med matchande raw_description
        s.add(_Tx(
            account_id=acc.id, date=_d.today(),
            amount=_D("-425"), raw_description="HEMKOP GLOBEN",
            hash="bulk1",
        ))

    _seed_scope(sid, seed)

    r = client.post(
        "/v2/bokforing/classify-bulk",
        headers={"Authorization": f"Bearer {stu}"},
        json={},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["processed"] == 1
    assert body["classified"] == 1
    assert body["via_history"] == 1
    assert body["still_unclassified"] == 0


def test_v2_bokforing_invalid_category_400(fx) -> None:
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Account as _Acc, Transaction as _Tx

    client, _tch, _sa, stu, _tid, _said, sid = fx
    tx_id_holder = {}

    def seed(s) -> None:
        acc = _Acc(
            name="Lönekonto", bank="SEB", type="checking",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today(),
        )
        s.add(acc)
        s.flush()
        tx = _Tx(
            account_id=acc.id, date=_d.today(),
            amount=_D("-168"), raw_description="Foo",
            hash="invalidcat1",
        )
        s.add(tx)
        s.flush()
        tx_id_holder["id"] = tx.id

    _seed_scope(sid, seed)

    r = client.patch(
        f"/v2/bokforing/transactions/{tx_id_holder['id']}",
        headers={"Authorization": f"Bearer {stu}"},
        json={"category_id": 99999},
    )
    assert r.status_code == 400


def test_v2_bokforing_wellbeing_high_classification_rate(fx) -> None:
    """Klassningsgrad >= 80 % → +2 economy."""
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc,
        Category as _Cat,
        Transaction as _Tx,
    )
    from hembudget.wellbeing.calculator import calculate_wellbeing
    from hembudget.db.base import session_scope as _ss
    from hembudget.school.engines import (
        master_session as _ms, scope_context as _sc,
        scope_for_student as _sfs,
    )
    from hembudget.school.models import Student as _St

    client, _tch, _sa, _stu, _tid, _said, sid = fx

    def seed(s) -> None:
        acc = _Acc(
            name="Lönekonto", bank="SEB", type="checking",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today(),
        )
        s.add(acc)
        s.flush()
        cat = s.query(_Cat).filter(_Cat.name == "Livsmedel").first()
        assert cat is not None
        # 5 klassade + 1 ovettad = 83 % klassning
        for i in range(5):
            s.add(_Tx(
                account_id=acc.id, date=_d.today(),
                amount=_D(f"-{100 + i}"),
                raw_description=f"Hemkop {i}",
                hash=f"hi{i}", category_id=cat.id,
            ))
        s.add(_Tx(
            account_id=acc.id, date=_d.today(),
            amount=_D("-200"), raw_description="Foo",
            hash="ovettad",
        ))

    _seed_scope(sid, seed)

    with _ms() as m:
        student = m.get(_St, sid)
        scope_key = _sfs(student)
    with _sc(scope_key):
        with _ss() as s:
            result = calculate_wellbeing(s, "2026-04")

    rate_factors = [
        f for f in result.factors
        if "klassningsgrad" in f.explanation.lower()
        and f.points > 0
    ]
    assert len(rate_factors) >= 1
    assert rate_factors[0].dimension == "economy"
    assert rate_factors[0].points == 2


def test_v2_teacher_bokforing_overview(fx) -> None:
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Account as _Acc, Transaction as _Tx

    client, tch, _sa, _stu, _tid, _said, sid = fx

    def seed(s) -> None:
        acc = _Acc(
            name="Lönekonto", bank="SEB", type="checking",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today(),
        )
        s.add(acc)
        s.flush()
        s.add(_Tx(
            account_id=acc.id, date=_d.today(),
            amount=_D("-100"), raw_description="Test",
            hash="ot1",
        ))

    _seed_scope(sid, seed)

    r = client.get(
        f"/v2/teacher/students/{sid}/bokforing-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["bokforing"]["summary"]["total_transactions"] == 1


def test_v2_teacher_bokforing_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/bokforing-overview",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === Fas 2I · Mina moduler · Module + StudentModule ===


def test_v2_moduler_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/moduler")
    assert r.status_code == 401


def test_v2_moduler_for_teacher_returns_empty(fx) -> None:
    client, tch, *_ = fx
    r = client.get(
        "/v2/moduler",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["student_id"] == 0


def test_v2_moduler_empty_state_for_student(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/moduler",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["in_progress"] == []
    assert data["completed"] == []
    # Available kan vara > 0 om systemet seedat templates


def test_v2_moduler_with_assigned_module(fx) -> None:
    """Lärar-tilldelar modul + eleven har klarat 2 av 4 steg."""
    from hembudget.school.models import (
        Module as _M,
        ModuleStep as _MS,
        StudentModule as _SM,
        StudentStepProgress as _SSP,
    )
    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        m = _M(
            teacher_id=tid,
            title="Bolån - din första",
            summary="KALP, ränta, amortering",
            is_template=False,
            sort_order=1,
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        steps = []
        for i, kind in enumerate(["read", "watch", "task", "quiz"]):
            st = _MS(
                module_id=m.id,
                sort_order=i,
                kind=kind,
                title=f"Steg {i + 1}",
            )
            db.add(st)
            steps.append(st)
        db.commit()
        for st in steps:
            db.refresh(st)
        sm = _SM(student_id=sid, module_id=m.id, sort_order=0)
        db.add(sm)
        db.commit()
        # Eleven har klarat steg 1 + 2
        from datetime import datetime as _dt_mod
        for st in steps[:2]:
            db.add(_SSP(
                student_id=sid, step_id=st.id,
                completed_at=_dt_mod.utcnow(),
                data={},
            ))
        db.commit()

    r = client.get(
        "/v2/moduler",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["in_progress_count"] == 1
    assert data["summary"]["completed_count"] == 0
    assert data["summary"]["avg_progress_pct"] == 50.0
    in_p = data["in_progress"][0]
    assert in_p["title"] == "Bolån - din första"
    assert in_p["step_count"] == 4
    assert in_p["completed_step_count"] == 2
    assert in_p["progress_pct"] == 50.0
    assert in_p["current_step_no"] == 3
    assert in_p["estimated_minutes_left"] == 10  # 2 steg × 5 min


def test_v2_moduler_completed_module(fx) -> None:
    """Modul med alla steg klara hamnar i 'completed'."""
    from hembudget.school.models import (
        Module as _M,
        ModuleStep as _MS,
        StudentModule as _SM,
        StudentStepProgress as _SSP,
    )
    from datetime import datetime as _dt_mod
    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        m = _M(
            teacher_id=tid,
            title="Din första månad",
            is_template=False,
            sort_order=0,
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        st = _MS(module_id=m.id, sort_order=0, kind="read", title="S1")
        db.add(st)
        db.commit()
        db.refresh(st)
        db.add(_SM(student_id=sid, module_id=m.id, sort_order=0))
        db.add(_SSP(
            student_id=sid, step_id=st.id,
            completed_at=_dt_mod.utcnow(),
            data={},
        ))
        db.commit()

    r = client.get(
        "/v2/moduler",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r.json()
    assert data["summary"]["completed_count"] == 1
    assert data["summary"]["in_progress_count"] == 0


def test_v2_moduler_available_template(fx) -> None:
    """Lärar-mall som inte är tilldelad → visas i available."""
    from hembudget.school.models import Module as _M, ModuleStep as _MS

    client, _tch, _sa, stu, tid, _said, _sid = fx
    with master_session() as db:
        m = _M(
            teacher_id=tid,
            title="Pension om 40 år",
            summary="5-stegs systemmodul",
            is_template=True,
            sort_order=0,
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        for i in range(5):
            db.add(_MS(
                module_id=m.id, sort_order=i,
                kind="read", title=f"S{i}",
            ))
        db.commit()

    r = client.get(
        "/v2/moduler",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r.json()
    available_titles = [a["title"] for a in data["available"]]
    assert "Pension om 40 år" in available_titles
    pension = [
        a for a in data["available"]
        if a["title"] == "Pension om 40 år"
    ][0]
    assert pension["step_count"] == 5
    assert pension["estimated_total_minutes"] == 25


def test_v2_teacher_moduler_overview(fx) -> None:
    from hembudget.school.models import Module as _M, StudentModule as _SM
    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        m = _M(title="Test-modul", is_template=False, sort_order=0)
        db.add(m)
        db.commit()
        db.refresh(m)
        db.add(_SM(student_id=sid, module_id=m.id, sort_order=0))
        db.commit()

    r = client.get(
        f"/v2/teacher/students/{sid}/moduler-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["student_name"]
    assert data["moduler"]["summary"]["in_progress_count"] >= 1


def test_v2_teacher_moduler_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/moduler-overview",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === Fas 2J · Investeringssim + Lånekalkylator ===


def test_v2_simulator_investment_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.post("/v2/simulator/investment", json={
        "start_amount": 0, "monthly_save": 600,
        "return_pct": 7, "years": 40,
    })
    assert r.status_code == 401


def test_v2_simulator_investment_basic_isk(fx) -> None:
    """600 kr/mån × 40 år vid 7 % real avk + 0,89 % schablon → ~1,2 Mkr."""
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/simulator/investment",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "start_amount": 0,
            "monthly_save": 600,
            "return_pct": 7,
            "years": 40,
            "schablonskatt_pct": 0.89,
            "is_isk": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_invested"] == 600 * 12 * 40
    # Final value bör vara > 1 000 000 vid 7 % över 40 år
    assert data["final_value"] > 1_000_000
    assert data["total_growth"] > 0
    assert len(data["yearly_balances"]) == 40
    # ISK-skatt > 0
    assert data["total_taxes"] > 0


def test_v2_simulator_investment_compare_modes(fx) -> None:
    """ISK ger lägre skatt än depå för samma scenario."""
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    common = {
        "start_amount": 0,
        "monthly_save": 1000,
        "return_pct": 7,
        "years": 30,
    }
    isk = client.post(
        "/v2/simulator/investment",
        headers={"Authorization": f"Bearer {stu}"},
        json={**common, "is_isk": True},
    ).json()
    depo = client.post(
        "/v2/simulator/investment",
        headers={"Authorization": f"Bearer {stu}"},
        json={**common, "is_isk": False},
    ).json()
    # ISK har lägre total skatt
    assert isk["total_taxes"] < depo["total_taxes"]
    # ISK ger högre final
    assert isk["final_value"] > depo["final_value"]


def test_v2_simulator_investment_save_scenario(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/simulator/investment",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "start_amount": 8460,
            "monthly_save": 600,
            "return_pct": 7,
            "years": 40,
            "save_as_scenario": True,
            "scenario_name": "600 i 40 år",
        },
    )
    assert r.status_code == 200, r.text
    sid = r.json()["saved_scenario_id"]
    assert sid is not None

    # Lista
    list_r = client.get(
        "/v2/simulator/scenarios",
        headers={"Authorization": f"Bearer {stu}"},
    )
    rows = list_r.json()
    assert len(rows) == 1
    assert rows[0]["name"] == "600 i 40 år"
    assert rows[0]["kind"] == "invest"


def test_v2_simulator_loan_annuity(fx) -> None:
    """Annuitet: 2,4 Mkr · 3,8 % · 240 mån → månadsbet ~14 270."""
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/simulator/loan",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "principal": 2_400_000,
            "interest_rate_pct": 3.8,
            "term_months": 240,
            "amortization_type": "annuity",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Annuitet på 240 mån ger ~14 270 / mån
    assert 14_000 < data["monthly_payment_baseline"] < 14_500
    assert data["total_interest_baseline"] > 1_000_000
    assert data["payoff_months_with_extra"] == 240
    assert data["months_saved"] == 0  # ingen extra
    assert len(data["schedule_first_12"]) == 12


def test_v2_simulator_loan_extra_amortization(fx) -> None:
    """Extra 500/mån på 38 200 CSN-lån → räntebesparing > 0."""
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/simulator/loan",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "principal": 38_200,
            "interest_rate_pct": 1.7,
            "term_months": 247,
            "amortization_type": "annuity",
            "extra_amortization_monthly": 500,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["interest_savings"] > 0
    assert data["months_saved"] > 0


def test_v2_simulator_loan_save_and_list(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/simulator/loan",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "principal": 100000,
            "interest_rate_pct": 5.0,
            "term_months": 120,
            "amortization_type": "annuity",
            "save_as_scenario": True,
        },
    )
    assert r.json()["saved_scenario_id"] is not None
    list_r = client.get(
        "/v2/simulator/scenarios?kind=loan",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert len(list_r.json()) == 1
    assert list_r.json()[0]["kind"] == "loan"


def test_v2_simulator_delete_scenario(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/simulator/investment",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "start_amount": 0, "monthly_save": 100,
            "return_pct": 5, "years": 5,
            "save_as_scenario": True,
        },
    )
    sid = r.json()["saved_scenario_id"]
    del_r = client.delete(
        f"/v2/simulator/scenarios/{sid}",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert del_r.status_code == 204
    list_r = client.get(
        "/v2/simulator/scenarios",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert all(r["id"] != sid for r in list_r.json())


def test_v2_simulator_wellbeing_long_horizon(fx) -> None:
    """Sparat invest-scenario med 40 års horisont → +1 economy."""
    from hembudget.wellbeing.calculator import calculate_wellbeing
    from hembudget.db.base import session_scope as _ss
    from hembudget.school.engines import (
        master_session as _ms, scope_context as _sc,
        scope_for_student as _sfs,
    )
    from hembudget.school.models import Student as _St

    client, _tch, _sa, stu, _tid, _said, sid = fx
    client.post(
        "/v2/simulator/investment",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "start_amount": 0, "monthly_save": 600,
            "return_pct": 7, "years": 40,
            "save_as_scenario": True,
        },
    )

    with _ms() as m:
        student = m.get(_St, sid)
        scope_key = _sfs(student)
    with _sc(scope_key):
        with _ss() as s:
            result = calculate_wellbeing(s, "2026-04")

    horizon_factors = [
        f for f in result.factors
        if "långsiktig planering" in f.explanation.lower()
    ]
    assert len(horizon_factors) >= 1
    assert horizon_factors[0].dimension == "economy"
    assert horizon_factors[0].points == 1


def test_v2_teacher_simulator_overview(fx) -> None:
    client, tch, _sa, stu, _tid, _said, sid = fx
    client.post(
        "/v2/simulator/investment",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "start_amount": 0, "monthly_save": 600,
            "return_pct": 7, "years": 40,
            "save_as_scenario": True,
            "scenario_name": "Pension om 40 år",
        },
    )
    client.post(
        "/v2/simulator/loan",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "principal": 2_400_000,
            "interest_rate_pct": 3.8,
            "term_months": 360,
            "amortization_type": "annuity",
            "save_as_scenario": True,
        },
    )
    r = client.get(
        f"/v2/teacher/students/{sid}/simulator-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["invest_count"] == 1
    assert data["loan_count"] == 1
    assert data["longest_horizon_years"] == 40
    assert data["biggest_principal"] == 2_400_000
    assert len(data["scenarios"]) == 2


def test_v2_teacher_simulator_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/simulator-overview",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === Fas 2K · Lärar-feedback · Message + Step-feedback + Assignment ===


def test_v2_feedback_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/feedback")
    assert r.status_code == 401


def test_v2_feedback_for_teacher_returns_empty(fx) -> None:
    client, tch, *_ = fx
    r = client.get(
        "/v2/feedback",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["student_id"] == 0


def test_v2_feedback_empty_state_for_student(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/feedback",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["items"] == []
    assert data["summary"]["total_count"] == 0


def test_v2_feedback_aggregates_message_and_step(fx) -> None:
    """Lärare har skickat 1 chat + gett feedback på 1 modul-steg."""
    from hembudget.school.models import (
        Message as _M,
        Module as _Mo,
        ModuleStep as _MS,
        StudentStepProgress as _SSP,
    )
    from datetime import datetime as _dt_t

    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        # 1 chat-meddelande
        db.add(_M(
            student_id=sid, teacher_id=tid,
            sender_role="teacher",
            body="Bra reflektion — höjer Bokföring till GRUND",
        ))
        # 1 step-feedback
        m = _Mo(teacher_id=tid, title="Bolån", is_template=False)
        db.add(m)
        db.commit()
        db.refresh(m)
        st = _MS(
            module_id=m.id, sort_order=0,
            kind="reflect", title="Steg 3 KALP",
        )
        db.add(st)
        db.commit()
        db.refresh(st)
        db.add(_SSP(
            student_id=sid, step_id=st.id,
            data={},
            teacher_feedback="Bra svar — du fattade poängen",
            feedback_at=_dt_t.utcnow(),
        ))
        db.commit()

    r = client.get(
        "/v2/feedback",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["total_count"] == 2
    assert data["summary"]["unread_count"] == 2
    assert data["summary"]["message_count"] == 1
    assert data["summary"]["module_step_count"] == 1
    kinds = sorted([i["kind"] for i in data["items"]])
    assert kinds == ["message", "module_step"]


def test_v2_feedback_mark_read(fx) -> None:
    """Mark-read minskar unread_count."""
    from hembudget.school.models import Message as _M
    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        db.add_all([
            _M(student_id=sid, teacher_id=tid, sender_role="teacher",
               body="Meddelande 1"),
            _M(student_id=sid, teacher_id=tid, sender_role="teacher",
               body="Meddelande 2"),
            _M(student_id=sid, teacher_id=tid, sender_role="teacher",
               body="Meddelande 3"),
        ])
        db.commit()

    list_r = client.get(
        "/v2/feedback",
        headers={"Authorization": f"Bearer {stu}"},
    )
    items = list_r.json()["items"]
    assert list_r.json()["summary"]["unread_count"] == 3

    # Markera 2 som lästa
    mark = client.post(
        "/v2/feedback/mark-read",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "items": [
                {"kind": "message", "source_id": items[0]["source_id"]},
                {"kind": "message", "source_id": items[1]["source_id"]},
            ],
        },
    )
    assert mark.status_code == 200, mark.text
    assert mark.json()["marked"] == 2
    assert mark.json()["already_read"] == 0

    # Idempotent: andra anropet → already_read=2
    mark2 = client.post(
        "/v2/feedback/mark-read",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "items": [
                {"kind": "message", "source_id": items[0]["source_id"]},
            ],
        },
    )
    assert mark2.json()["marked"] == 0
    assert mark2.json()["already_read"] == 1

    # Lista igen — unread = 1
    list_r2 = client.get(
        "/v2/feedback",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert list_r2.json()["summary"]["unread_count"] == 1


def test_v2_feedback_assignment(fx) -> None:
    """Assignment med teacher_feedback kommer in i feedback-listan."""
    from hembudget.school.models import Assignment as _A
    from datetime import datetime as _dt_a

    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        db.add(_A(
            teacher_id=tid,
            student_id=sid,
            title="Klassa 12 ovettade",
            description="Klassa alla 12 ovettade transaktioner",
            kind="categorize_all",
            teacher_feedback="Klart 17 apr · 12 manuella",
            teacher_feedback_at=_dt_a.utcnow(),
        ))
        db.commit()

    r = client.get(
        "/v2/feedback",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r.json()
    assignments = [i for i in data["items"] if i["kind"] == "assignment"]
    assert len(assignments) == 1
    assert "Klassa 12" in assignments[0]["title"]


def test_v2_feedback_wellbeing_unread_penalty(fx) -> None:
    """5+ olästa feedback senaste 30 dgr → -2 social."""
    from hembudget.school.models import Message as _M
    from hembudget.wellbeing.calculator import calculate_wellbeing
    from hembudget.db.base import session_scope as _ss
    from hembudget.school.engines import (
        master_session as _ms, scope_context as _sc,
        scope_for_student as _sfs,
    )
    from hembudget.school.models import Student as _St

    client, _tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        for i in range(6):
            db.add(_M(
                student_id=sid, teacher_id=tid,
                sender_role="teacher",
                body=f"Feedback {i}",
            ))
        db.commit()

    with _ms() as m:
        student = m.get(_St, sid)
        scope_key = _sfs(student)
    with _sc(scope_key):
        with _ss() as s:
            result = calculate_wellbeing(s, "2026-04")

    penalty_factors = [
        f for f in result.factors
        if "olästa lärar-feedback" in f.explanation.lower()
    ]
    assert len(penalty_factors) >= 1
    assert penalty_factors[0].dimension == "social"
    assert penalty_factors[0].points == -2


def test_v2_feedback_wellbeing_engaged_bonus(fx) -> None:
    """Alla feedback lästa + minst 1 läst → +1 social."""
    from hembudget.school.models import Message as _M
    from hembudget.wellbeing.calculator import calculate_wellbeing
    from hembudget.db.base import session_scope as _ss
    from hembudget.school.engines import (
        master_session as _ms, scope_context as _sc,
        scope_for_student as _sfs,
    )
    from hembudget.school.models import Student as _St

    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        db.add(_M(
            student_id=sid, teacher_id=tid,
            sender_role="teacher",
            body="Feedback A",
        ))
        db.commit()
    list_r = client.get(
        "/v2/feedback",
        headers={"Authorization": f"Bearer {stu}"},
    )
    msg_id = list_r.json()["items"][0]["source_id"]
    client.post(
        "/v2/feedback/mark-read",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "items": [
                {"kind": "message", "source_id": msg_id},
            ],
        },
    )

    with _ms() as m:
        student = m.get(_St, sid)
        scope_key = _sfs(student)
    with _sc(scope_key):
        with _ss() as s:
            result = calculate_wellbeing(s, "2026-04")

    bonus_factors = [
        f for f in result.factors
        if "engagerar dig i lärar-feedback" in f.explanation.lower()
    ]
    assert len(bonus_factors) >= 1
    assert bonus_factors[0].points == 1


def test_v2_teacher_feedback_overview(fx) -> None:
    from hembudget.school.models import Message as _M
    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        db.add(_M(
            student_id=sid, teacher_id=tid,
            sender_role="teacher",
            body="Test-feedback",
        ))
        db.commit()
    r = client.get(
        f"/v2/teacher/students/{sid}/feedback-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["feedback"]["summary"]["total_count"] >= 1


def test_v2_teacher_feedback_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/feedback-overview",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === Fas 2L · MariaV2 + BankIDV2 ===


def test_v2_maria_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/maria")
    assert r.status_code == 401


def test_v2_maria_empty_state(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/maria",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["has_active"] is False
    assert r.json()["history"] == []


def test_v2_maria_lists_active_negotiation(fx) -> None:
    """Aktivt SalaryNegotiation visas i v2/maria."""
    from hembudget.school.employer_models import (
        SalaryNegotiation as _SN,
        NegotiationRound as _NR,
    )
    from datetime import datetime as _dt
    from decimal import Decimal as _D
    client, _tch, _sa, stu, _tid, _said, sid = fx
    with master_session() as db:
        n = _SN(
            student_id=sid,
            profession="Undersköterska",
            employer="Sthlm Sjukhus",
            starting_salary=_D("26000"),
            avtal_norm_pct=2.4,
            avtal_code="vard_oms",
            status="active",
        )
        db.add(n)
        db.commit()
        db.refresh(n)
        db.add(_NR(
            negotiation_id=n.id,
            round_no=1,
            student_message="Jag yrkar 27 500.",
            employer_response="Bra argument. Jag erbjuder 26 200.",
            proposed_pct=3.1,
            input_tokens=120, output_tokens=80,
        ))
        db.commit()

    r = client.get(
        "/v2/maria",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r.json()
    assert data["has_active"] is True
    assert data["active"]["status"] == "active"
    assert len(data["active"]["rounds"]) == 1
    assert data["active"]["rounds"][0]["round_no"] == 1


def test_v2_teacher_maria_overview(fx) -> None:
    from hembudget.school.employer_models import SalaryNegotiation as _SN
    from decimal import Decimal as _D
    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        db.add(_SN(
            student_id=sid,
            profession="Sjuksköterska",
            employer="Sthlm Sjukhus",
            starting_salary=_D("32000"),
            status="active",
        ))
        db.commit()
    r = client.get(
        f"/v2/teacher/students/{sid}/maria-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["maria"]["has_active"] is True


def test_v2_bankid_session_create_and_sign(fx) -> None:
    """Skapa session med 2 fakturor → signera → autogiro=True."""
    from datetime import date as _d, timedelta as _td
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc,
        UpcomingTransaction as _UT,
    )

    client, _tch, _sa, stu, _tid, _said, sid = fx
    upcoming_ids: list[int] = []

    def seed(s) -> None:
        acc = _Acc(
            name="Lönekonto", bank="SEB", type="checking",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today(),
        )
        s.add(acc)
        s.flush()
        u1 = _UT(
            kind="bill", name="Stockholmshem (hyra)",
            amount=_D("7240"),
            expected_date=_d.today() + _td(days=5),
        )
        u2 = _UT(
            kind="bill", name="Tibber (el)",
            amount=_D("812"),
            expected_date=_d.today() + _td(days=10),
        )
        s.add(u1)
        s.add(u2)
        s.flush()
        upcoming_ids.append(u1.id)
        upcoming_ids.append(u2.id)

    _seed_scope(sid, seed)

    # Skapa session
    r = client.post(
        "/v2/bankid/sessions",
        headers={"Authorization": f"Bearer {stu}"},
        json={"upcoming_ids": upcoming_ids},
    )
    assert r.status_code == 200, r.text
    session_id = r.json()["id"]
    assert r.json()["status"] == "pending"
    assert r.json()["invoice_count"] == 2
    assert r.json()["total_amount"] == 7240 + 812
    assert r.json()["current_step"] == 4

    # Signera
    sign_r = client.post(
        f"/v2/bankid/sessions/{session_id}/sign",
        headers={"Authorization": f"Bearer {stu}"},
        json={"duration_seconds": 12},
    )
    assert sign_r.status_code == 200, sign_r.text
    assert sign_r.json()["status"] == "signed"
    assert sign_r.json()["signed_at"] is not None
    assert sign_r.json()["duration_seconds"] == 12
    assert sign_r.json()["current_step"] == 6


def test_v2_bankid_cancel(fx) -> None:
    from datetime import date as _d, timedelta as _td
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc,
        UpcomingTransaction as _UT,
    )
    client, _tch, _sa, stu, _tid, _said, sid = fx
    upcoming_ids: list[int] = []

    def seed(s) -> None:
        acc = _Acc(
            name="Lönekonto", bank="SEB", type="checking",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today(),
        )
        s.add(acc)
        s.flush()
        u = _UT(
            kind="bill", name="Folktandvården",
            amount=_D("4200"),
            expected_date=_d.today() + _td(days=14),
        )
        s.add(u)
        s.flush()
        upcoming_ids.append(u.id)

    _seed_scope(sid, seed)

    r = client.post(
        "/v2/bankid/sessions",
        headers={"Authorization": f"Bearer {stu}"},
        json={"upcoming_ids": upcoming_ids},
    )
    sid2 = r.json()["id"]
    cancel_r = client.post(
        f"/v2/bankid/sessions/{sid2}/cancel",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert cancel_r.status_code == 200, cancel_r.text
    assert cancel_r.json()["status"] == "cancelled"


def test_v2_bankid_list_sessions_summary(fx) -> None:
    from datetime import date as _d, timedelta as _td
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc,
        UpcomingTransaction as _UT,
    )
    client, _tch, _sa, stu, _tid, _said, sid = fx
    upcoming_ids: list[int] = []

    def seed(s) -> None:
        acc = _Acc(
            name="Lönekonto", bank="SEB", type="checking",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today(),
        )
        s.add(acc)
        s.flush()
        for i, amt in enumerate([7240, 812]):
            u = _UT(
                kind="bill", name=f"Test {i}",
                amount=_D(str(amt)),
                expected_date=_d.today() + _td(days=5),
            )
            s.add(u)
            s.flush()
            upcoming_ids.append(u.id)

    _seed_scope(sid, seed)

    # Skapa + signera 1
    r1 = client.post(
        "/v2/bankid/sessions",
        headers={"Authorization": f"Bearer {stu}"},
        json={"upcoming_ids": [upcoming_ids[0]]},
    )
    client.post(
        f"/v2/bankid/sessions/{r1.json()['id']}/sign",
        headers={"Authorization": f"Bearer {stu}"},
        json={"duration_seconds": 8},
    )
    # Skapa pending
    client.post(
        "/v2/bankid/sessions",
        headers={"Authorization": f"Bearer {stu}"},
        json={"upcoming_ids": [upcoming_ids[1]]},
    )

    list_r = client.get(
        "/v2/bankid/sessions",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = list_r.json()
    assert data["pending_count"] == 1
    assert data["signed_count"] == 1
    assert data["cancelled_count"] == 0
    assert data["total_signed_amount"] == 7240


def test_v2_bankid_invalid_upcoming_400(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/bankid/sessions",
        headers={"Authorization": f"Bearer {stu}"},
        json={"upcoming_ids": [99999]},
    )
    assert r.status_code == 400


def test_v2_bankid_wellbeing_signed_bonus(fx) -> None:
    """Signerad session senaste 90 dgr → +2 economy."""
    from datetime import date as _d, timedelta as _td
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc,
        UpcomingTransaction as _UT,
    )
    from hembudget.wellbeing.calculator import calculate_wellbeing
    from hembudget.db.base import session_scope as _ss
    from hembudget.school.engines import (
        master_session as _ms, scope_context as _sc,
        scope_for_student as _sfs,
    )
    from hembudget.school.models import Student as _St

    client, _tch, _sa, stu, _tid, _said, sid = fx
    upcoming_ids: list[int] = []

    def seed(s) -> None:
        acc = _Acc(
            name="Lönekonto", bank="SEB", type="checking",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today(),
        )
        s.add(acc)
        s.flush()
        u = _UT(
            kind="bill", name="Test", amount=_D("1000"),
            expected_date=_d.today() + _td(days=5),
        )
        s.add(u)
        s.flush()
        upcoming_ids.append(u.id)

    _seed_scope(sid, seed)

    r = client.post(
        "/v2/bankid/sessions",
        headers={"Authorization": f"Bearer {stu}"},
        json={"upcoming_ids": upcoming_ids},
    )
    client.post(
        f"/v2/bankid/sessions/{r.json()['id']}/sign",
        headers={"Authorization": f"Bearer {stu}"},
        json={"duration_seconds": 12},
    )

    with _ms() as m:
        student = m.get(_St, sid)
        scope_key = _sfs(student)
    with _sc(scope_key):
        with _ss() as s:
            result = calculate_wellbeing(s, "2026-04")

    bonus_factors = [
        f for f in result.factors
        if "bankid-signering" in f.explanation.lower()
        and f.points > 0
    ]
    assert len(bonus_factors) >= 1
    assert bonus_factors[0].dimension == "economy"
    assert bonus_factors[0].points == 2


def test_v2_teacher_bankid_overview(fx) -> None:
    from datetime import date as _d, timedelta as _td
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc,
        UpcomingTransaction as _UT,
    )
    client, tch, _sa, stu, _tid, _said, sid = fx
    upcoming_ids: list[int] = []

    def seed(s) -> None:
        acc = _Acc(
            name="Lönekonto", bank="SEB", type="checking",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today(),
        )
        s.add(acc)
        s.flush()
        u = _UT(
            kind="bill", name="Test", amount=_D("500"),
            expected_date=_d.today() + _td(days=5),
        )
        s.add(u)
        s.flush()
        upcoming_ids.append(u.id)

    _seed_scope(sid, seed)
    client.post(
        "/v2/bankid/sessions",
        headers={"Authorization": f"Bearer {stu}"},
        json={"upcoming_ids": upcoming_ids},
    )
    r = client.get(
        f"/v2/teacher/students/{sid}/bankid-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["bankid"]["pending_count"] == 1


def test_v2_teacher_bankid_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/bankid-overview",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


def test_v2_teacher_maria_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/maria-overview",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === Fas 2M · TxV2 + MeddelandenV2 + PortfolioV2 ===


def _make_tx(s, acc_id, amount, desc, hash_, normalized=None,
             category_id=None) -> int:
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import Transaction as _Tx
    t = _Tx(
        account_id=acc_id, date=_d.today(),
        amount=_D(str(amount)),
        raw_description=desc,
        normalized_merchant=normalized,
        hash=hash_, category_id=category_id,
    )
    s.add(t)
    s.flush()
    return t.id


def test_v2_tx_detail_404(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/tx/99999",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 404


def test_v2_tx_detail_returns_recurring(fx) -> None:
    """Foodora-köp: detalj-vyn ska visa de andra Foodora-köpen senaste 90 dgr."""
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc, Transaction as _Tx,
    )

    client, _tch, _sa, stu, _tid, _said, sid = fx
    target_id: dict[str, int] = {}

    def seed(s) -> None:
        acc = _Acc(
            name="SEB Visa", bank="SEB", type="credit",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today(),
        )
        s.add(acc)
        s.flush()
        # Tre Foodora-köp, första är "denna"
        target_id["id"] = _make_tx(
            s, acc.id, -187, "Foodora pizza",
            "h1", normalized="FOODORA",
        )
        _make_tx(s, acc.id, -156, "Foodora burger",
                 "h2", normalized="FOODORA")
        _make_tx(s, acc.id, -212, "Foodora sushi",
                 "h3", normalized="FOODORA")

    _seed_scope(sid, seed)

    r = client.get(
        f"/v2/tx/{target_id['id']}",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["raw_description"] == "Foodora pizza"
    assert data["amount"] == -187
    assert len(data["recurring"]) == 3
    self_rows = [r for r in data["recurring"] if r["is_self"]]
    assert len(self_rows) == 1
    assert self_rows[0]["id"] == target_id["id"]
    assert data["recurring_count_30d"] == 2  # 2 andra utöver "denna"
    assert data["recurring_total_30d"] == 156 + 212


def test_v2_tx_classify_via_patch(fx) -> None:
    """PATCH sätter category_id + user_verified=True."""
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc, Category as _Cat,
    )

    client, _tch, _sa, stu, _tid, _said, sid = fx
    holder: dict[str, int] = {}

    def seed(s) -> None:
        acc = _Acc(
            name="SEB Visa", bank="SEB", type="credit",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today(),
        )
        s.add(acc)
        s.flush()
        cat = (
            s.query(_Cat).filter(_Cat.name == "Restaurang").first()
        )
        assert cat is not None
        holder["cat_id"] = cat.id
        holder["tx_id"] = _make_tx(
            s, acc.id, -187, "Foodora", "patch1",
            normalized="FOODORA",
        )

    _seed_scope(sid, seed)

    r = client.patch(
        f"/v2/tx/{holder['tx_id']}",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "category_id": holder["cat_id"],
            "notes": "Efter laxsim",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["category_id"] == holder["cat_id"]
    assert r.json()["user_verified"] is True
    assert r.json()["notes"] == "Efter laxsim"


def test_v2_tx_create_rule_classifies_existing(fx) -> None:
    """Skapa regel "FOODORA → Restaurang" + apply_to_existing=True."""
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc, Category as _Cat,
    )

    client, _tch, _sa, stu, _tid, _said, sid = fx
    holder: dict[str, int] = {}

    def seed(s) -> None:
        acc = _Acc(
            name="SEB Visa", bank="SEB", type="credit",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today(),
        )
        s.add(acc)
        s.flush()
        cat = s.query(_Cat).filter(_Cat.name == "Restaurang").first()
        assert cat is not None
        holder["cat_id"] = cat.id
        # 3 oklassificerade Foodora
        holder["tx_id"] = _make_tx(
            s, acc.id, -187, "Foodora pizza", "rule1",
            normalized="FOODORA",
        )
        _make_tx(s, acc.id, -156, "Foodora burger",
                 "rule2", normalized="FOODORA")
        _make_tx(s, acc.id, -212, "Foodora sushi",
                 "rule3", normalized="FOODORA")

    _seed_scope(sid, seed)

    r = client.post(
        f"/v2/tx/{holder['tx_id']}/create-rule",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "category_id": holder["cat_id"],
            "apply_to_existing": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["already_existed"] is False
    assert r.json()["applied_count"] == 3  # alla 3 klassades om
    assert r.json()["pattern"] == "FOODORA"

    # Andra anropet → already_existed
    r2 = client.post(
        f"/v2/tx/{holder['tx_id']}/create-rule",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "category_id": holder["cat_id"],
            "apply_to_existing": False,
        },
    )
    assert r2.json()["already_existed"] is True


def test_v2_messages_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/messages")
    assert r.status_code == 401


def test_v2_messages_empty_state(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/messages",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["messages"] == []
    assert data["unread_count"] == 0


def test_v2_messages_send_and_receive(fx) -> None:
    """Eleven skickar + lärare svarar via /v2/teacher/messages."""
    client, tch, _sa, stu, _tid, _said, sid = fx
    # Eleven skickar
    r1 = client.post(
        "/v2/messages",
        headers={"Authorization": f"Bearer {stu}"},
        json={"body": "Hej Anders, jag har en fråga om CSN-räntan."},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["sender_role"] == "student"

    # Lärare svarar
    r2 = client.post(
        f"/v2/teacher/students/{sid}/messages",
        headers={"Authorization": f"Bearer {tch}"},
        json={"body": "Bra fråga — räntan är ovanligt låg."},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["sender_role"] == "teacher"

    # Lista
    list_r = client.get(
        "/v2/messages",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert len(list_r.json()["messages"]) == 2
    assert list_r.json()["unread_count"] == 1  # lärar-msg är oläst
    assert list_r.json()["teacher_name"]


def test_v2_messages_mark_read(fx) -> None:
    client, tch, _sa, stu, _tid, _said, sid = fx
    client.post(
        f"/v2/teacher/students/{sid}/messages",
        headers={"Authorization": f"Bearer {tch}"},
        json={"body": "Test"},
    )
    list_r = client.get(
        "/v2/messages",
        headers={"Authorization": f"Bearer {stu}"},
    )
    msg_id = list_r.json()["messages"][0]["id"]
    mark = client.post(
        f"/v2/messages/{msg_id}/mark-read",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert mark.status_code == 204
    list2 = client.get(
        "/v2/messages",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert list2.json()["unread_count"] == 0


def test_v2_portfolio_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/portfolio")
    assert r.status_code == 401


def test_v2_portfolio_empty_state(fx) -> None:
    """Inga kompetenser seedade → tom payload."""
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/portfolio",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Kan ha system-kompetenser från default-seed, men alla på BASIS
    assert data["summary"]["fordjup_count"] == 0


def test_v2_portfolio_with_completed_competency(fx) -> None:
    """En modul med 100% klar → kompetensen på FÖRDJUPNING."""
    from hembudget.school.models import (
        Module as _M,
        ModuleStep as _MS,
        StudentStepProgress as _SSP,
        Competency as _Comp,
        ModuleStepCompetency as _MSC,
    )
    from datetime import datetime as _dt

    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        c = _Comp(
            key="bokforing",
            name="Bokföring",
            level="grund",
            is_system=True,
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        m = _M(teacher_id=tid, title="Test", is_template=False)
        db.add(m)
        db.commit()
        db.refresh(m)
        st = _MS(
            module_id=m.id, sort_order=0,
            kind="read", title="S1",
        )
        db.add(st)
        db.commit()
        db.refresh(st)
        db.add(_MSC(step_id=st.id, competency_id=c.id, weight=1.0))
        db.add(_SSP(
            student_id=sid, step_id=st.id,
            completed_at=_dt.utcnow(),
            data={},
        ))
        db.commit()

    r = client.get(
        "/v2/portfolio",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r.json()
    bokforing = [
        e for e in data["competencies"]
        if e["key"] == "bokforing"
    ]
    assert len(bokforing) == 1
    assert bokforing[0]["mastery"] == 1.0
    assert bokforing[0]["level"] == "F"
    assert bokforing[0]["level_label"] == "FÖRDJUPNING"
    assert data["summary"]["fordjup_count"] >= 1


def test_v2_teacher_messages_overview(fx) -> None:
    client, tch, _sa, stu, _tid, _said, sid = fx
    client.post(
        "/v2/messages",
        headers={"Authorization": f"Bearer {stu}"},
        json={"body": "Hej"},
    )
    r = client.get(
        f"/v2/teacher/students/{sid}/messages-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["teacher_unread_count"] == 1


def test_v2_teacher_portfolio_overview(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/portfolio-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["student_id"] == sid


def test_v2_teacher_messages_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/messages-overview",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


def test_v2_teacher_portfolio_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/portfolio-overview",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === Fas 2N · MailDetail (CC + Lönespec) ===


def test_v2_mail_detail_404(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/postladan/99999/detail",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 404


def test_v2_mail_detail_cc_invoice(fx) -> None:
    """Kreditkortsfaktura-detalj med transaktioner inom perioden."""
    from datetime import date as _d, timedelta as _td
    from decimal import Decimal as _D
    from hembudget.db.models import (
        Account as _Acc,
        MailItem as _Mail,
        Transaction as _Tx,
    )

    client, _tch, _sa, stu, _tid, _said, sid = fx
    holder: dict[str, int] = {}

    def seed(s) -> None:
        cc = _Acc(
            name="SEB Visa", bank="SEB", type="credit",
            currency="SEK", opening_balance=_D("0"),
            opening_balance_date=_d.today() - _td(days=60),
        )
        s.add(cc)
        s.flush()
        # 5 tx inom de senaste 30 dgr
        for i, (amt, desc) in enumerate([
            (-168, "Max Hökarängen"),
            (-187, "Foodora pizza"),
            (-312, "Coop Konsum"),
            (-498, "H&M Globen"),
            (-72, "Pressbyrån"),
        ]):
            t = _Tx(
                account_id=cc.id,
                date=_d.today() - _td(days=5 + i),
                amount=_D(str(amt)),
                raw_description=desc,
                normalized_merchant=desc.upper(),
                hash=f"cc{i}",
                # Klassa 2 av 5 manuellt
                category_id=None,
                user_verified=False,
            )
            s.add(t)
        # CC-faktura mail
        mail = _Mail(
            sender="SEB Visa",
            sender_short="CC",
            sender_kind="cred",
            mail_type="invoice",
            subject="April-spend",
            amount=_D("-1237"),
            due_date=_d.today() + _td(days=20),
            status="unhandled",
        )
        s.add(mail)
        s.flush()
        holder["mail_id"] = mail.id

    _seed_scope(sid, seed)

    r = client.get(
        f"/v2/postladan/{holder['mail_id']}/detail",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mail"]["sender"] == "SEB Visa"
    # status ska ha gått från unhandled → viewed
    assert data["mail"]["status"] == "viewed"
    assert data["cc_invoice"] is not None
    assert data["salary_slip"] is None
    cc = data["cc_invoice"]
    assert cc["tx_count"] == 5
    assert cc["unclassified_count"] == 5
    assert cc["total_amount"] == 168 + 187 + 312 + 498 + 72  # 1237
    assert len(cc["transactions"]) == 5
    assert cc["profile_label"] in ["balanserad", "sparsam", "slösa"]


def test_v2_mail_detail_salary_slip(fx) -> None:
    """Lönespec-detalj med brutto/netto/employer-breakdown."""
    from datetime import date as _d
    from decimal import Decimal as _D
    from hembudget.db.models import MailItem as _Mail
    from hembudget.school.models import StudentProfile

    client, _tch, _sa, stu, _tid, _said, sid = fx
    # Seed StudentProfile
    with master_session() as db:
        db.add(StudentProfile(
            student_id=sid,
            profession="Undersköterska 80 % tjänst",
            employer="Sthlm Sjukhus AB",
            gross_salary_monthly=31730,
            net_salary_monthly=22880,
            tax_rate_effective=0.28,
            age=22, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=7240, personality="balanserad",
        ))
        db.commit()

    holder: dict[str, int] = {}

    def seed(s) -> None:
        mail = _Mail(
            sender="Sthlm Sjukhus AB",
            sender_short="LÖN",
            sender_kind="work",
            mail_type="salary_slip",
            subject="Lönespec april — 22 880 kr netto",
            body_meta="april 2026 (preliminär)",
            amount=_D("22880"),
            due_date=_d.today(),
            status="unhandled",
        )
        s.add(mail)
        s.flush()
        holder["mail_id"] = mail.id

    _seed_scope(sid, seed)

    r = client.get(
        f"/v2/postladan/{holder['mail_id']}/detail",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["salary_slip"] is not None
    assert data["cc_invoice"] is None
    sal = data["salary_slip"]
    assert sal["gross_salary"] == 31730
    assert sal["net_salary"] == 22880
    assert sal["tax"] > 0
    # ITP1 = 4.5 % av brutto ≈ 1428
    assert 1400 < sal["employer_itp1"] < 1450
    # Sociala = 31.42 % ≈ 9970
    assert 9900 < sal["employer_social"] < 10000
    assert sal["employer_friskvard"] == 417
    # Total kostnad arbetsgivare = ~43545
    assert 43500 < sal["total_employer_cost"] < 43600
    # net_lines + employer_lines har innehåll
    assert any(line["is_total"] for line in sal["net_lines"])
    assert any(line["is_total"] for line in sal["employer_lines"])


def test_v2_mail_detail_authority_no_extras(fx) -> None:
    """Myndighetspost: cc_invoice och salary_slip ska vara None."""
    from datetime import date as _d, timedelta as _td
    from hembudget.db.models import MailItem as _Mail

    client, _tch, _sa, stu, _tid, _said, sid = fx
    holder: dict[str, int] = {}

    def seed(s) -> None:
        mail = _Mail(
            sender="Skatteverket",
            sender_kind="skv",
            mail_type="authority",
            subject="Myndighetsbrev",
            due_date=_d.today() + _td(days=30),
            status="unhandled",
        )
        s.add(mail)
        s.flush()
        holder["mail_id"] = mail.id

    _seed_scope(sid, seed)

    r = client.get(
        f"/v2/postladan/{holder['mail_id']}/detail",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r.json()
    assert data["cc_invoice"] is None
    assert data["salary_slip"] is None


def test_v2_teacher_mail_detail_overview(fx) -> None:
    """Lärar-overview för mail-detail · markerar inte viewed."""
    from datetime import date as _d, timedelta as _td
    from decimal import Decimal as _D
    from hembudget.db.models import MailItem as _Mail

    client, tch, _sa, _stu, _tid, _said, sid = fx
    holder: dict[str, int] = {}

    def seed(s) -> None:
        mail = _Mail(
            sender="SEB Visa",
            sender_kind="cred",
            mail_type="invoice",
            subject="CC april",
            amount=_D("-2400"),
            due_date=_d.today() + _td(days=20),
            status="unhandled",
        )
        s.add(mail)
        s.flush()
        holder["mail_id"] = mail.id

    _seed_scope(sid, seed)

    r = client.get(
        f"/v2/teacher/students/{sid}/mail/{holder['mail_id']}/detail",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["student_id"] == sid
    # Lärar-overview SKA INTE markera viewed
    assert r.json()["detail"]["mail"]["status"] == "unhandled"


def test_v2_teacher_mail_detail_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/mail/1/detail",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === UppdragV2 (Mina uppdrag) — Fas 2P ===


def test_v2_uppdrag_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/uppdrag")
    assert r.status_code == 401


def test_v2_uppdrag_empty_state(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/uppdrag",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["active"] == []
    assert data["completed"] == []
    assert data["summary"]["active_count"] == 0
    assert data["summary"]["completed_count"] == 0
    assert data["summary"]["overdue_count"] == 0


def test_v2_uppdrag_lists_active_with_urgency(fx) -> None:
    """Lärar-uppdrag med olika due_date → sorteras på urgency."""
    from hembudget.school.models import Assignment as _A
    from datetime import datetime as _dt, timedelta as _td

    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        db.add(_A(
            teacher_id=tid, student_id=sid,
            title="Räkna KALP 2,4 Mkr",
            description="Bolån för 2:a i Hökarängen",
            kind="free_text",
            due_date=_dt.utcnow() + _td(days=5),
        ))
        db.add(_A(
            teacher_id=tid, student_id=sid,
            title="Peer-review Hassans portfolio",
            description="Granska klasskamratens lönesamtal",
            kind="free_text",
            due_date=_dt.utcnow() + _td(days=1),
        ))
        db.add(_A(
            teacher_id=tid, student_id=sid,
            title="Reflektera över april",
            description="200-400 ord",
            kind="free_text",
            due_date=_dt.utcnow() + _td(days=14),
        ))
        db.commit()

    r = client.get(
        "/v2/uppdrag",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    titles = [row["title"] for row in data["active"]]
    # Sortering: 1 dag → 5 dgr → 14 dgr
    assert titles[0].startswith("Peer-review")
    assert "KALP" in titles[1]
    assert "april" in titles[2]
    assert data["summary"]["active_count"] == 3
    assert data["summary"]["nearest_due_label"] in {"imorgon", "1 dgr"}
    # urgency-tags
    urgencies = [row["urgency"] for row in data["active"]]
    assert urgencies[0] == "tomorrow"
    assert urgencies[1] == "this_week"
    assert urgencies[2] == "later"


def test_v2_uppdrag_overdue_counted(fx) -> None:
    from hembudget.school.models import Assignment as _A
    from datetime import datetime as _dt, timedelta as _td

    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        db.add(_A(
            teacher_id=tid, student_id=sid,
            title="Försenat", description="...",
            kind="free_text",
            due_date=_dt.utcnow() - _td(days=2),
        ))
        db.commit()
    r = client.get(
        "/v2/uppdrag",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r.json()
    assert data["summary"]["overdue_count"] == 1
    assert data["active"][0]["urgency"] == "overdue"


def test_v2_uppdrag_self_complete_free_text(fx) -> None:
    from hembudget.school.models import Assignment as _A

    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        a = _A(
            teacher_id=tid, student_id=sid,
            title="Skriv reflektion",
            description="200 ord",
            kind="free_text",
        )
        db.add(a); db.flush()
        aid = a.id
        db.commit()

    r = client.post(
        f"/v2/uppdrag/{aid}/self-complete",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["assignment_id"] == aid

    # Nu ska den ligga i completed-listan
    r2 = client.get(
        "/v2/uppdrag",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r2.json()
    assert data["summary"]["active_count"] == 0
    assert data["summary"]["completed_count"] == 1
    assert data["completed"][0]["status"] == "completed"
    assert data["summary"]["completed_this_month"] == 1


def test_v2_uppdrag_self_complete_blocks_auto_kind(fx) -> None:
    """save_amount bedöms automatiskt — kan ej själv-klarmarkeras."""
    from hembudget.school.models import Assignment as _A

    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        a = _A(
            teacher_id=tid, student_id=sid,
            title="Spara 2000",
            description="Spara 2000 kr",
            kind="save_amount",
            params={"amount": 2000},
        )
        db.add(a); db.flush()
        aid = a.id
        db.commit()

    r = client.post(
        f"/v2/uppdrag/{aid}/self-complete",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 400


def test_v2_uppdrag_self_complete_other_student_404(fx) -> None:
    """Eleven kan inte själv-klarmarkera annan elevs uppdrag."""
    from hembudget.school.models import Assignment as _A, Student as _S

    client, _tch, _sa, stu, tid, _said, _sid = fx
    with master_session() as db:
        other = _S(
            teacher_id=tid, display_name="Hassan",
            login_code="HAS00002",
        )
        db.add(other); db.flush()
        a = _A(
            teacher_id=tid, student_id=other.id,
            title="X", description="X", kind="free_text",
        )
        db.add(a); db.flush()
        aid = a.id
        db.commit()

    r = client.post(
        f"/v2/uppdrag/{aid}/self-complete",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 404


def test_v2_teacher_uppdrag_overview(fx) -> None:
    from hembudget.school.models import Assignment as _A
    from datetime import datetime as _dt, timedelta as _td

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        db.add(_A(
            teacher_id=tid, student_id=sid,
            title="Räkna KALP",
            description="Bolån",
            kind="free_text",
            due_date=_dt.utcnow() + _td(days=3),
        ))
        db.commit()

    r = client.get(
        f"/v2/teacher/students/{sid}/uppdrag-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["uppdrag"]["summary"]["active_count"] == 1
    assert data["uppdrag"]["active"][0]["title"] == "Räkna KALP"


def test_v2_teacher_uppdrag_blocks_other_teachers(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/uppdrag-overview",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === KompetensV2 (Kompetens-detalj) — Fas 2Q ===


def test_v2_kompetens_detail_404_when_unknown(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/kompetens/9999",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 404


def test_v2_kompetens_detail_basis_when_no_progress(fx) -> None:
    """Ny kompetens, ingen progress → BASIS, krav i listan."""
    from hembudget.school.models import Competency as _Comp

    client, _tch, _sa, stu, _tid, _said, _sid = fx
    with master_session() as db:
        c = _Comp(
            key="lon", name="Lön",
            level="grund", is_system=True,
        )
        db.add(c); db.flush()
        cid = c.id
        db.commit()

    r = client.get(
        f"/v2/kompetens/{cid}",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["competency_id"] == cid
    assert data["key"] == "lon"
    assert data["level"] == "B"
    assert data["next_level"] == "G"
    assert data["next_level_label"] == "GRUND"
    assert data["mastery"] == 0.0
    assert data["completed_steps"] == 0
    assert data["timeline"] == []
    # 3 krav-rader för nästa nivå
    assert len(data["requirements_for_next"]) == 3
    assert all(r["met"] is False for r in data["requirements_for_next"])


def test_v2_kompetens_detail_with_completed_module(fx) -> None:
    """En modul klar → mastery=1.0 → FÖRDJUPNING + module_completed-event."""
    from hembudget.school.models import (
        Module as _M, ModuleStep as _MS,
        StudentStepProgress as _SSP, StudentModule as _SM,
        Competency as _Comp, ModuleStepCompetency as _MSC,
    )
    from datetime import datetime as _dt

    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        c = _Comp(
            key="bokforing", name="Bokföring",
            level="grund", is_system=True,
        )
        db.add(c); db.flush()
        cid = c.id
        m = _M(
            teacher_id=tid, title="Bokföring grunder",
            is_template=False,
        )
        db.add(m); db.flush()
        mid = m.id
        st1 = _MS(
            module_id=mid, sort_order=0,
            kind="read", title="Vad är bokföring",
        )
        st2 = _MS(
            module_id=mid, sort_order=1,
            kind="task", title="Klassa 5 transaktioner",
        )
        db.add(st1); db.add(st2); db.flush()
        db.add(_MSC(step_id=st1.id, competency_id=cid, weight=1.0))
        db.add(_MSC(step_id=st2.id, competency_id=cid, weight=1.0))
        completed_at = _dt.utcnow()
        db.add(_SSP(
            student_id=sid, step_id=st1.id,
            completed_at=completed_at, data={},
        ))
        db.add(_SSP(
            student_id=sid, step_id=st2.id,
            completed_at=completed_at, data={},
        ))
        db.add(_SM(
            student_id=sid, module_id=mid,
            started_at=completed_at,
            completed_at=completed_at,
        ))
        db.commit()

    r = client.get(
        f"/v2/kompetens/{cid}",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mastery"] == 1.0
    assert data["level"] == "F"
    assert data["next_level"] is None
    assert data["completed_steps"] == 2
    assert data["total_steps"] == 2
    # Timeline: 2 step_completed + 1 module_completed = 3 events
    assert len(data["timeline"]) == 3
    types = {e["event_type"] for e in data["timeline"]}
    assert "step_completed" in types
    assert "module_completed" in types
    # Connected modules · 1 klar
    assert len(data["connected_modules"]) == 1
    assert data["connected_modules"][0]["completed"] is True
    assert data["connected_modules"][0]["completed_steps"] == 2


def test_v2_kompetens_detail_progress_to_grund(fx) -> None:
    """1 av 3 steg klart → mastery ~0.33 (G-tröskeln) → GRUND-nivå."""
    from hembudget.school.models import (
        Module as _M, ModuleStep as _MS,
        StudentStepProgress as _SSP,
        Competency as _Comp, ModuleStepCompetency as _MSC,
    )
    from datetime import datetime as _dt

    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        c = _Comp(key="skatt", name="Skatt", level="grund", is_system=True)
        db.add(c); db.flush()
        cid = c.id
        m = _M(teacher_id=tid, title="Skatten", is_template=False)
        db.add(m); db.flush()
        steps = [
            _MS(module_id=m.id, sort_order=i, kind="read", title=f"S{i}")
            for i in range(3)
        ]
        for st in steps:
            db.add(st)
        db.flush()
        for st in steps:
            db.add(_MSC(step_id=st.id, competency_id=cid, weight=1.0))
        db.add(_SSP(
            student_id=sid, step_id=steps[0].id,
            completed_at=_dt.utcnow(), data={},
        ))
        db.commit()

    r = client.get(
        f"/v2/kompetens/{cid}",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r.json()
    # 1/3 = 0.3333 → just under threshold för GRUND (0.33),
    # men round-to-3 hamnar på 0.333 som är >= 0.33
    assert data["completed_steps"] == 1
    assert data["total_steps"] == 3
    # Mastery exakt 1/3 ~= 0.3333 → level G (>= 0.33)
    assert data["level"] == "G"
    assert data["next_level"] == "F"


def test_v2_teacher_kompetens_overview(fx) -> None:
    from hembudget.school.models import Competency as _Comp

    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        c = _Comp(
            key="budget", name="Budget",
            level="grund", is_system=True,
        )
        db.add(c); db.flush()
        cid = c.id
        db.commit()

    r = client.get(
        f"/v2/teacher/students/{sid}/kompetens/{cid}",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["detail"]["competency_id"] == cid
    assert data["detail"]["level"] == "B"


def test_v2_teacher_kompetens_blocks_other_teachers(fx) -> None:
    from hembudget.school.models import Competency as _Comp

    client, _tch, sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        c = _Comp(key="x", name="X", level="grund", is_system=True)
        db.add(c); db.flush()
        cid = c.id
        db.commit()

    r = client.get(
        f"/v2/teacher/students/{sid}/kompetens/{cid}",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === KlassHubV2 (Lärar-hub · klass-overview) — Fas 2R ===


def test_v2_klass_overview_blocks_students(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/klass-overview",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 403


def test_v2_klass_overview_basic_shape(fx) -> None:
    """Lärare med 1 elev → minimal payload med rätt struktur."""
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/teacher/klass-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_students"] == 1
    assert data["teacher_name"] == "T"
    assert "klass_pentagon" in data
    assert "klass_stats" in data
    assert len(data["klass_stats"]) == 5
    assert "mini_pentagons" in data
    assert len(data["mini_pentagons"]) == 1
    assert data["mini_pentagons"][0]["student_id"] == sid
    # Defaultvärden 50 när scope-DB är tom
    p = data["klass_pentagon"]
    for axis in ("total_score", "economy", "safety", "health", "social", "leisure"):
        assert isinstance(p[axis], int)


def test_v2_klass_overview_with_pending_negotiation(fx) -> None:
    """Aktivt lönesamtal dyker upp i pending_negotiations."""
    from hembudget.school.employer_models import (
        SalaryNegotiation as _SN,
        NegotiationRound as _NR,
    )
    from decimal import Decimal as _D

    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        n = _SN(
            student_id=sid,
            profession="Frisör",
            employer="Salongen",
            starting_salary=_D("25000.00"),
            status="active",
        )
        db.add(n); db.flush()
        nid = n.id
        db.add(_NR(
            negotiation_id=nid, round_no=2,
            student_message="Jag yrkar 28 000.",
            employer_response="Vi kan tänka oss 26 500.",
            proposed_pct=6.0,
        ))
        db.commit()

    r = client.get(
        "/v2/teacher/klass-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    negs = data["pending_negotiations"]
    assert len(negs) == 1
    assert negs[0]["round_no"] == 2
    assert negs[0]["status"] == "active"
    assert negs[0]["student_id"] == sid
    # 25000 × 1.06 = 26500
    assert abs(negs[0]["last_proposed_salary"] - 26500.0) < 0.5
    # Stat-kortet "Lönesamtal i Maria" ska visa 1
    maria_stat = next(
        s for s in data["klass_stats"] if s["eye"] == "Lönesamtal i Maria"
    )
    assert maria_stat["num_value"] == "1"


def test_v2_klass_overview_level_distribution(fx) -> None:
    """v2_level=2 räknas i level_2_count."""
    from hembudget.school.models import Student as _S

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        # Lägg till en till elev på nivå 2
        s2 = _S(
            teacher_id=tid, display_name="Hanna",
            login_code="HAN00099",
        )
        db.add(s2); db.flush()
        s2.v2_level = 2
        # Befintliga eleven Eva → nivå 1 default
        db.commit()

    r = client.get(
        "/v2/teacher/klass-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    ld = data["level_distribution"]
    assert ld["level_1_count"] == 1
    assert ld["level_2_count"] == 1
    assert ld["level_3_count"] == 0


def test_v2_klass_overview_period_label_format(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/klass-overview",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    label = data["period_label"]
    # "v18 · onsdag 29 april" eller liknande svensk format
    assert label.startswith("v")
    assert " · " in label
    weekdays = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]
    assert any(w in label for w in weekdays)


# === TeacherStudentDetailV2 (p-elev) — Fas 2S ===


def test_v2_teacher_student_detail_blocks_other_teacher(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/student-detail",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


def test_v2_teacher_student_detail_blocks_students(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/student-detail",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 403


def test_v2_teacher_student_detail_basic_shape(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/student-detail",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["student_name"] == "Eva"
    assert data["v2_level"] == 1
    assert data["v2_level_label"] == "Sparsam"
    # Pentagon-keys
    p = data["pentagon"]
    for axis in (
        "total_score", "economy", "safety", "health",
        "social", "leisure", "tipped_towards",
    ):
        assert axis in p
    # Active modules + competencies (empty fixture)
    assert isinstance(data["active_modules"], list)
    assert isinstance(data["competencies"], list)
    assert isinstance(data["recent_events"], list)
    assert "level_progression" in data
    assert data["level_progression"]["current_level"] == 1
    assert data["level_progression"]["target_level"] == 2
    # Login-suffix bara sista 4 tecken
    assert data["login_code_suffix"] == "0001"


def test_v2_teacher_student_detail_with_pending_negotiation(fx) -> None:
    from hembudget.school.employer_models import (
        SalaryNegotiation as _SN,
        NegotiationRound as _NR,
    )
    from decimal import Decimal as _D

    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        n = _SN(
            student_id=sid,
            profession="Frisör",
            employer="Salongen",
            starting_salary=_D("25000.00"),
            status="active",
        )
        db.add(n); db.flush()
        nid = n.id
        db.add(_NR(
            negotiation_id=nid, round_no=3,
            student_message="x", employer_response="y",
            proposed_pct=8.0,
        ))
        db.commit()

    r = client.get(
        f"/v2/teacher/students/{sid}/student-detail",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    pneg = data["pending_negotiation"]
    assert pneg is not None
    assert pneg["round_no"] == 3
    assert pneg["status"] == "active"


def test_v2_teacher_student_detail_with_active_module(fx) -> None:
    """Modul med delvis klar progress → räknas som aktiv med progress_pct."""
    from hembudget.school.models import (
        Module as _M, ModuleStep as _MS,
        StudentStepProgress as _SSP, StudentModule as _SM,
    )
    from datetime import datetime as _dt

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        m = _M(
            teacher_id=tid, title="Bolån",
            summary="Förstå bolån",
            is_template=False,
        )
        db.add(m); db.flush()
        steps = [
            _MS(module_id=m.id, sort_order=i, kind="read", title=f"S{i}")
            for i in range(4)
        ]
        for st in steps:
            db.add(st)
        db.flush()
        # 1 av 4 klar
        db.add(_SSP(
            student_id=sid, step_id=steps[0].id,
            completed_at=_dt.utcnow(), data={},
        ))
        db.add(_SM(
            student_id=sid, module_id=m.id,
            started_at=_dt.utcnow(),
        ))
        db.commit()

    r = client.get(
        f"/v2/teacher/students/{sid}/student-detail",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    am = data["active_modules"]
    assert len(am) == 1
    assert am[0]["title"] == "Bolån"
    assert am[0]["completed_steps"] == 1
    assert am[0]["total_steps"] == 4
    assert am[0]["progress_pct"] == 25
    assert am[0]["next_step_title"] == "S1"


def test_v2_teacher_student_detail_recent_events_includes_step(fx) -> None:
    """Klarat steg senaste 30 dgr → kommer in i recent_events."""
    from hembudget.school.models import (
        Module as _M, ModuleStep as _MS,
        StudentStepProgress as _SSP,
    )
    from datetime import datetime as _dt

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        m = _M(teacher_id=tid, title="X", is_template=False)
        db.add(m); db.flush()
        st = _MS(
            module_id=m.id, sort_order=0,
            kind="reflect", title="Reflektera om april",
        )
        db.add(st); db.flush()
        db.add(_SSP(
            student_id=sid, step_id=st.id,
            completed_at=_dt.utcnow(), data={"reflection": "abc"},
        ))
        db.commit()

    r = client.get(
        f"/v2/teacher/students/{sid}/student-detail",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    titles = [e["summary"] for e in data["recent_events"]]
    assert any("Reflektera om april" in t for t in titles)


def test_v2_teacher_student_detail_404_when_not_found(fx) -> None:
    client, tch, *_ = fx
    r = client.get(
        "/v2/teacher/students/9999/student-detail",
        headers={"Authorization": f"Bearer {tch}"},
    )
    # Saknad elev → 403 (beror på Student-objekt None)
    assert r.status_code == 403


# === TeacherReflectionsV2 (p-refl) — Fas 2T ===


def test_v2_teacher_reflections_blocks_non_teacher(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/reflections",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 403


def test_v2_teacher_reflections_empty(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/reflections",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["total_count"] == 0
    assert data["items"] == []


def test_v2_teacher_reflections_lists_with_summary(fx) -> None:
    """3 reflektioner → summary räknar rätt + flaggar."""
    from hembudget.school.models import (
        Module as _M, ModuleStep as _MS,
        StudentStepProgress as _SSP,
    )
    from datetime import datetime as _dt

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        m = _M(teacher_id=tid, title="Skatt", is_template=False)
        db.add(m); db.flush()
        s1 = _MS(
            module_id=m.id, sort_order=0,
            kind="reflect", title="Vad lärde du dig?",
            content="Skriv 200+ ord",
        )
        s2 = _MS(
            module_id=m.id, sort_order=1,
            kind="reflect", title="Hur gick det?",
        )
        s3 = _MS(
            module_id=m.id, sort_order=2,
            kind="reflect", title="Reflektera om april",
        )
        db.add(s1); db.add(s2); db.add(s3); db.flush()
        # Klar reflektion utan feedback
        db.add(_SSP(
            student_id=sid, step_id=s1.id,
            completed_at=_dt.utcnow(),
            data={"reflection": "Jag förstår nu mycket bättre."},
        ))
        # Klar reflektion MED feedback
        db.add(_SSP(
            student_id=sid, step_id=s2.id,
            completed_at=_dt.utcnow(),
            data={"reflection": "Det gick bra."},
            teacher_feedback="Snyggt!",
            feedback_at=_dt.utcnow(),
        ))
        # Klar reflektion med help-flagga
        db.add(_SSP(
            student_id=sid, step_id=s3.id,
            completed_at=_dt.utcnow(),
            data={"reflection": "Vet inte hur jag deklarerar"},
        ))
        db.commit()

    r = client.get(
        "/v2/teacher/reflections",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    s = data["summary"]
    assert s["total_count"] == 3
    assert s["unread_count"] == 2
    assert s["flagged_count"] == 1
    assert s["avg_word_count"] > 0
    titles = [i["step_title"] for i in data["items"]]
    assert "Vad lärde du dig?" in titles


def test_v2_teacher_reflections_filter_unread(fx) -> None:
    from hembudget.school.models import (
        Module as _M, ModuleStep as _MS,
        StudentStepProgress as _SSP,
    )
    from datetime import datetime as _dt

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        m = _M(teacher_id=tid, title="X", is_template=False)
        db.add(m); db.flush()
        s1 = _MS(module_id=m.id, sort_order=0, kind="reflect", title="A")
        s2 = _MS(module_id=m.id, sort_order=1, kind="reflect", title="B")
        db.add(s1); db.add(s2); db.flush()
        db.add(_SSP(
            student_id=sid, step_id=s1.id,
            completed_at=_dt.utcnow(),
            data={"reflection": "ord ord ord"},
            teacher_feedback="bra",
            feedback_at=_dt.utcnow(),
        ))
        db.add(_SSP(
            student_id=sid, step_id=s2.id,
            completed_at=_dt.utcnow(),
            data={"reflection": "andra reflektion"},
        ))
        db.commit()

    r = client.get(
        "/v2/teacher/reflections?filter=unread",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    # Items är filtrerat till bara olästa men summary är total
    assert data["summary"]["total_count"] == 2
    assert len(data["items"]) == 1
    assert data["items"][0]["step_title"] == "B"


def test_v2_teacher_reflections_filter_flagged(fx) -> None:
    from hembudget.school.models import (
        Module as _M, ModuleStep as _MS,
        StudentStepProgress as _SSP,
    )
    from datetime import datetime as _dt

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        m = _M(teacher_id=tid, title="X", is_template=False)
        db.add(m); db.flush()
        s = _MS(module_id=m.id, sort_order=0, kind="reflect", title="Q")
        db.add(s); db.flush()
        db.add(_SSP(
            student_id=sid, step_id=s.id,
            completed_at=_dt.utcnow(),
            data={"reflection": "Behöver hjälp innan deadline"},
        ))
        db.commit()

    r = client.get(
        "/v2/teacher/reflections?filter=flagged",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["flagged_for_help"] is True


def test_v2_teacher_reflections_post_feedback(fx) -> None:
    from hembudget.school.models import (
        Module as _M, ModuleStep as _MS,
        StudentStepProgress as _SSP,
    )
    from datetime import datetime as _dt

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        m = _M(teacher_id=tid, title="Z", is_template=False)
        db.add(m); db.flush()
        s = _MS(module_id=m.id, sort_order=0, kind="reflect", title="Q")
        db.add(s); db.flush()
        prog = _SSP(
            student_id=sid, step_id=s.id,
            completed_at=_dt.utcnow(),
            data={"reflection": "tankar"},
        )
        db.add(prog); db.flush()
        pid = prog.id
        db.commit()

    r = client.post(
        f"/v2/teacher/reflections/{pid}/feedback",
        headers={"Authorization": f"Bearer {tch}"},
        json={"body": "Bra reflektion! Försök gå djupare nästa gång."},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["teacher_feedback"].startswith("Bra reflektion!")
    assert out["feedback_at"] is not None

    # Lista igen → unread_count nu 0
    r2 = client.get(
        "/v2/teacher/reflections",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r2.json()["summary"]["unread_count"] == 0


def test_v2_teacher_reflections_feedback_blocks_other_teacher(fx) -> None:
    from hembudget.school.models import (
        Module as _M, ModuleStep as _MS,
        StudentStepProgress as _SSP,
    )
    from datetime import datetime as _dt

    client, _tch, sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        m = _M(teacher_id=tid, title="Q", is_template=False)
        db.add(m); db.flush()
        s = _MS(module_id=m.id, sort_order=0, kind="reflect", title="?")
        db.add(s); db.flush()
        prog = _SSP(
            student_id=sid, step_id=s.id,
            completed_at=_dt.utcnow(),
            data={"reflection": "x"},
        )
        db.add(prog); db.flush()
        pid = prog.id
        db.commit()

    r = client.post(
        f"/v2/teacher/reflections/{pid}/feedback",
        headers={"Authorization": f"Bearer {sa}"},
        json={"body": "kommentar"},
    )
    assert r.status_code == 403


# === TeacherMailboxV2 (p-mail) — Fas 2U ===


def test_v2_teacher_mailboxes_blocks_students(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/mailboxes",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 403


def test_v2_teacher_mailboxes_empty(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/mailboxes",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["total_students"] == 1
    assert len(data["rows"]) == 1
    # Tom scope-DB → "klar"
    assert data["rows"][0]["status"] == "klar"
    assert data["rows"][0]["unhandled_count"] == 0


def test_v2_teacher_mailboxes_status_levels(fx) -> None:
    """Skicka olika antal brev till elever via mail-seed → status varieras."""
    client, tch, _sa, _stu, tid, _said, sid = fx
    # Lägg till 2 elever till
    from hembudget.school.models import Student as _S
    with master_session() as db:
        s2 = _S(
            teacher_id=tid, display_name="B", login_code="BBB00002",
        )
        s3 = _S(
            teacher_id=tid, display_name="C", login_code="CCC00003",
        )
        db.add(s2); db.add(s3); db.flush()
        sid2 = s2.id
        sid3 = s3.id
        db.commit()

    # Eleven Eva (sid) → 2 ohanterade (i_fas)
    r = client.post(
        f"/v2/teacher/students/{sid}/mail-seed",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "items": [
                {
                    "sender": "El AB", "mail_type": "invoice",
                    "subject": "El april", "amount": 800,
                },
                {
                    "sender": "Tibber", "mail_type": "invoice",
                    "subject": "El mars", "amount": 700,
                },
            ],
            "replace_existing": True,
        },
    )
    assert r.status_code == 200, r.text
    # Eleven B (sid2) → 6 ohanterade (släper)
    items_släper = [
        {
            "sender": f"X{i}", "mail_type": "invoice",
            "subject": f"X{i}", "amount": 100,
        }
        for i in range(6)
    ]
    r = client.post(
        f"/v2/teacher/students/{sid2}/mail-seed",
        headers={"Authorization": f"Bearer {tch}"},
        json={"items": items_släper, "replace_existing": True},
    )
    assert r.status_code == 200, r.text
    # Eleven C (sid3) → ingen → klar

    r = client.get(
        "/v2/teacher/mailboxes",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    rows = data["rows"]
    by_id = {row["student_id"]: row for row in rows}
    assert by_id[sid]["unhandled_count"] == 2
    assert by_id[sid]["status"] == "i_fas"
    assert by_id[sid2]["unhandled_count"] == 6
    assert by_id[sid2]["status"] == "släper"
    assert by_id[sid3]["unhandled_count"] == 0
    assert by_id[sid3]["status"] == "klar"

    # Sortering · risk/släper först
    assert rows[0]["status"] in ("risk", "släper")


def test_v2_teacher_mailboxes_summary_counts_correctly(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, sid = fx
    client.post(
        f"/v2/teacher/students/{sid}/mail-seed",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "items": [
                {
                    "sender": "X", "mail_type": "reminder",
                    "subject": "Påminn", "amount": 100,
                },
                {
                    "sender": "Y", "mail_type": "invoice",
                    "subject": "Faktura", "amount": 200,
                },
            ],
            "replace_existing": True,
        },
    )
    r = client.get(
        "/v2/teacher/mailboxes",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    assert data["summary"]["reminders_total"] == 1
    assert data["summary"]["total_generated_period"] == 2
    # Student Eva har 1 reminder → status risk
    assert data["rows"][0]["status"] == "risk"


def test_v2_teacher_mailboxes_bulk_inject_to_all(fx) -> None:
    from hembudget.school.models import Student as _S

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        s2 = _S(
            teacher_id=tid, display_name="B", login_code="BBB00002",
        )
        db.add(s2); db.flush()
        sid2 = s2.id
        db.commit()

    r = client.post(
        "/v2/teacher/mailboxes/bulk-inject",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "sender": "Folktandvården",
            "mail_type": "invoice",
            "subject": "Karies-bokning",
            "amount": 850,
        },
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["students_targeted"] == 2
    assert out["mails_created"] == 2

    r2 = client.get(
        "/v2/teacher/mailboxes",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r2.json()
    by_id = {row["student_id"]: row for row in data["rows"]}
    assert by_id[sid]["unhandled_count"] == 1
    assert by_id[sid2]["unhandled_count"] == 1


def test_v2_teacher_mailboxes_bulk_inject_target_subset(fx) -> None:
    from hembudget.school.models import Student as _S

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        s2 = _S(
            teacher_id=tid, display_name="B", login_code="BBB00002",
        )
        db.add(s2); db.flush()
        sid2 = s2.id
        db.commit()

    r = client.post(
        "/v2/teacher/mailboxes/bulk-inject",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "sender": "Klarna",
            "mail_type": "invoice",
            "subject": "Faktura",
            "amount": 500,
            "target_student_ids": [sid2],
        },
    )
    assert r.json()["mails_created"] == 1

    r2 = client.get(
        "/v2/teacher/mailboxes",
        headers={"Authorization": f"Bearer {tch}"},
    )
    by_id = {row["student_id"]: row for row in r2.json()["rows"]}
    assert by_id[sid2]["unhandled_count"] == 1
    assert by_id[sid]["unhandled_count"] == 0


def test_v2_teacher_mailboxes_bulk_inject_blocks_other_teachers(
    fx,
) -> None:
    """Annan lärare kan inte injicera till första lärarens elever."""
    client, _tch, sa, _stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/teacher/mailboxes/bulk-inject",
        headers={"Authorization": f"Bearer {sa}"},
        json={
            "sender": "X",
            "mail_type": "invoice",
            "subject": "X",
        },
    )
    # Super-admin har inga elever → 0 affected (inte 403, men inget skapas)
    assert r.status_code == 200
    assert r.json()["mails_created"] == 0


# === TeacherMariaListV2 (p-maria) — Fas 2V ===


def test_v2_teacher_maria_list_blocks_students(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/maria-list",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 403


def test_v2_teacher_maria_list_empty(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/maria-list",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["total_count"] == 0
    assert data["active"] == []
    assert data["completed"] == []


def test_v2_teacher_maria_list_active_with_rounds(fx) -> None:
    """Aktiv förhandling med 3 ronder → senaste 2 visas i compact."""
    from hembudget.school.employer_models import (
        SalaryNegotiation as _SN,
        NegotiationRound as _NR,
    )
    from decimal import Decimal as _D

    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        n = _SN(
            student_id=sid,
            profession="Underskoterska",
            employer="Vården",
            starting_salary=_D("25000.00"),
            status="active",
        )
        db.add(n); db.flush()
        nid = n.id
        for i, pct in enumerate((4.0, 5.0, 6.5), start=1):
            db.add(_NR(
                negotiation_id=nid, round_no=i,
                student_message=f"Yrkar mer (rond {i})",
                employer_response=f"Vi kan {25000 * (1 + pct/100):.0f}",
                proposed_pct=pct,
            ))
        db.commit()

    r = client.get(
        "/v2/teacher/maria-list",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    assert data["summary"]["active_count"] == 1
    assert len(data["active"]) == 1
    item = data["active"][0]
    assert item["current_round_no"] == 3
    assert len(item["rounds"]) == 2  # senaste 2
    assert item["rounds"][0]["round_no"] == 2
    assert item["rounds"][1]["round_no"] == 3
    # 6.5 % >= 6 → near_pain
    assert item["near_pain_threshold"] is True
    assert data["summary"]["near_pain_count"] == 1


def test_v2_teacher_maria_list_completed_in_window(fx) -> None:
    from hembudget.school.employer_models import (
        SalaryNegotiation as _SN,
    )
    from decimal import Decimal as _D
    from datetime import datetime as _dt, timedelta as _td

    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        # Klar inom 30 dgr
        n1 = _SN(
            student_id=sid,
            profession="X", employer="Y",
            starting_salary=_D("25000.00"),
            status="completed",
            completed_at=_dt.utcnow() - _td(days=3),
            final_salary=_D("26500.00"),
            final_pct=6.0,
        )
        # För gammal — ska INTE komma med
        n2 = _SN(
            student_id=sid,
            profession="A", employer="B",
            starting_salary=_D("25000.00"),
            status="completed",
            completed_at=_dt.utcnow() - _td(days=60),
        )
        db.add(n1); db.add(n2); db.commit()

    r = client.get(
        "/v2/teacher/maria-list",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    assert data["summary"]["completed_count"] == 1
    assert len(data["completed"]) == 1
    assert data["completed"][0]["final_salary"] == 26500.0


def test_v2_teacher_maria_list_only_own_students(fx) -> None:
    """Annan lärares elev syns inte."""
    from hembudget.school.models import Student as _S, Teacher as _T
    from hembudget.school.employer_models import (
        SalaryNegotiation as _SN,
    )
    from hembudget.security.crypto import hash_password
    from decimal import Decimal as _D

    client, tch, _sa, _stu, _tid, _said, _sid = fx
    with master_session() as db:
        t2 = _T(
            email="other@x.se", name="Other",
            password_hash=hash_password("Abcdef12!"),
        )
        db.add(t2); db.flush()
        s_other = _S(
            teacher_id=t2.id, display_name="Annan elev",
            login_code="OTH00099",
        )
        db.add(s_other); db.flush()
        db.add(_SN(
            student_id=s_other.id,
            profession="Z", employer="Q",
            starting_salary=_D("25000.00"),
            status="active",
        ))
        db.commit()

    r = client.get(
        "/v2/teacher/maria-list",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    assert data["summary"]["active_count"] == 0


# === TeacherPedagogicsV2 (p-peda) — Fas 2W ===


def test_v2_teacher_pedagogics_blocks_students(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/pedagogics",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 403


def test_v2_teacher_pedagogics_basic_shape(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/pedagogics",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # 8 hård-kodade boxar i mappningen
    assert data["summary"]["total_boxes"] == 8
    assert data["summary"]["total_concepts"] > 30
    assert len(data["concept_boxes"]) == 8
    # Tom klass · alla boxar är underexposed (single student, no scope-DB)
    for box in data["concept_boxes"]:
        assert "key" in box
        assert "concepts" in box


def test_v2_teacher_pedagogics_competency_distribution(fx) -> None:
    """En system-kompetens med 1 elev som inte gjort något → basis_count=1."""
    from hembudget.school.models import Competency as _Comp

    client, tch, _sa, _stu, _tid, _said, _sid = fx
    with master_session() as db:
        c = _Comp(
            key="lan_ranta", name="Lån & ränta",
            level="grund", is_system=True,
        )
        db.add(c); db.commit()

    r = client.get(
        "/v2/teacher/pedagogics",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    rows = data["competency_distribution"]
    by_key = {r["key"]: r for r in rows}
    assert "lan_ranta" in by_key
    assert by_key["lan_ranta"]["basis_count"] == 1
    assert by_key["lan_ranta"]["grund_count"] == 0
    assert by_key["lan_ranta"]["fordjup_count"] == 0
    assert by_key["lan_ranta"]["is_concerning"] is True


def test_v2_teacher_pedagogics_suggests_action_for_concerning_competency(
    fx,
) -> None:
    """5+ elever på basis i en kompetens → förslag dyker upp."""
    from hembudget.school.models import (
        Student as _S, Competency as _Comp,
    )

    client, tch, _sa, _stu, tid, _said, _sid = fx
    with master_session() as db:
        # Lägg till 5 elever till
        for i in range(5):
            db.add(_S(
                teacher_id=tid,
                display_name=f"Elev {i}",
                login_code=f"E{i:07d}",
            ))
        c = _Comp(
            key="skatt_grund", name="Skatte-grund",
            level="grund", is_system=True,
        )
        db.add(c); db.commit()

    r = client.get(
        "/v2/teacher/pedagogics",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    titles = [s["title"] for s in data["suggestions"]]
    # Förslag med kompetens-gap för skatt finns
    assert any("Skatte-grund" in t for t in titles)


def test_v2_teacher_pedagogics_module_exposure_counts(fx) -> None:
    """Elev med startad bolåne-modul → modul_bolan-boxen räknar 1."""
    from hembudget.school.models import (
        Module as _M, ModuleStep as _MS,
        StudentModule as _SM,
    )
    from datetime import datetime as _dt

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        m = _M(
            teacher_id=tid, title="Bolån för 2:a",
            is_template=False,
        )
        db.add(m); db.flush()
        db.add(_SM(
            student_id=sid, module_id=m.id,
            started_at=_dt.utcnow(),
        ))
        db.commit()

    r = client.get(
        "/v2/teacher/pedagogics",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    bolan_box = next(
        b for b in data["concept_boxes"] if b["key"] == "modul_bolan"
    )
    assert bolan_box["student_count"] == 1


# === TeacherCreateStudentV2 (p-skapa) — Fas 2X ===


def test_v2_teacher_create_student_blocks_students(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {stu}"},
        json={"first_name": "Test"},
    )
    assert r.status_code == 403


def test_v2_teacher_create_student_basic(fx) -> None:
    client, tch, _sa, _stu, tid, _said, _sid = fx
    r = client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "first_name": "Maja",
            "last_initial": "F",
            "archetype": "kassorska",
            "spend_profile": "sparsam",
            "partner_model": "solo",
            "starting_level": 1,
            "guardian_email": "erik.fredriksson@gmail.com",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_name"] == "Maja F."
    assert len(data["login_code"]) >= 6
    assert data["spend_profile"] == "sparsam"
    assert data["partner_model"] == "solo"
    assert data["starting_level"] == 1
    assert data["activated"] is False  # ingen login än

    # Lärar-roster ska nu ha 2 elever (eva + maja)
    from hembudget.school.models import Student as _S
    with master_session() as db:
        students = (
            db.query(_S).filter(_S.teacher_id == tid).all()
        )
    assert len(students) == 2


def test_v2_teacher_create_student_random_archetype(fx) -> None:
    client, tch, *_ = fx
    r = client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "first_name": "Robin",
            "last_initial": "Z.",
            "archetype": "random",
            "starting_level": 2,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["spend_profile"] == "balanserad"  # default för level 2
    assert data["partner_model"] in ("solo", "ai", "klasskompis")


def test_v2_teacher_delete_student(fx) -> None:
    """Lärare kan radera elev permanent · scope-data + master-rad bort."""
    from hembudget.school.models import Student as _S

    client, tch, *_ = fx
    # Skapa Otto
    create_r = client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {tch}"},
        json={"first_name": "Otto", "last_initial": "D."},
    )
    assert create_r.status_code == 200, create_r.text
    otto_id = create_r.json()["student_id"]
    # Verifiera att han finns
    with master_session() as s:
        assert s.get(_S, otto_id) is not None
    # Radera
    del_r = client.delete(
        f"/v2/teacher/students/{otto_id}",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert del_r.status_code == 204, del_r.text
    # Verifiera att han är borta
    with master_session() as s:
        assert s.get(_S, otto_id) is None


def test_v2_teacher_delete_student_with_onboarding_events(fx) -> None:
    """Regression: elev MED v2_onboarding_events ska kunna raderas.

    Buggen: V2OnboardingEvent.student_id hade FK utan ondelete=CASCADE
    → IntegrityError → 500 i UI. Reproducerar den genom att skapa elev,
    seeda onboarding-event manuellt, sen radera.
    """
    from hembudget.school.models import (
        Student as _S, V2OnboardingEvent as _OE,
    )

    client, tch, *_ = fx
    create_r = client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {tch}"},
        json={"first_name": "Ulla", "last_initial": "E."},
    )
    assert create_r.status_code == 200, create_r.text
    ulla_id = create_r.json()["student_id"]
    with master_session() as s:
        s.add(_OE(
            student_id=ulla_id, step=1, event_type="viewed",
        ))
        s.add(_OE(
            student_id=ulla_id, step=2, event_type="next",
        ))
        s.commit()
        assert s.query(_OE).filter(_OE.student_id == ulla_id).count() == 2
    del_r = client.delete(
        f"/v2/teacher/students/{ulla_id}",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert del_r.status_code == 204, del_r.text
    with master_session() as s:
        assert s.get(_S, ulla_id) is None
        assert s.query(_OE).filter(_OE.student_id == ulla_id).count() == 0


def test_v2_teacher_delete_student_other_teachers_student_404(fx) -> None:
    """Lärare kan inte radera annan lärares elev."""
    client, _tch, _sa, _stu, _tid, _said, sid = fx
    # Skapa en annan lärare
    from hembudget.school.models import Teacher as _T
    from hembudget.security.crypto import hash_password
    with master_session() as s:
        other = _T(
            email="annan@skola.se",
            password_hash=hash_password("hemligt12"),
            name="Annan",
            email_verified_at=datetime.utcnow(),
        )
        s.add(other)
        s.commit()
        s.refresh(other)
    login_r = client.post(
        "/teacher/login",
        json={"email": "annan@skola.se", "password": "hemligt12"},
    )
    assert login_r.status_code == 200
    other_token = login_r.json()["token"]
    # Försök radera Eva (sid tillhör tch, inte annan)
    r = client.delete(
        f"/v2/teacher/students/{sid}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert r.status_code == 404


def test_v2_seed_initial_marks_april_as_paid(fx) -> None:
    """Reproduce: ny elev → april ska vara HISTORIK (alla fakturor
    autogiro-betalda, status=paid), inte ohanterade.

    Buggen: april-fakturor seedades med status=unhandled så
    eleven såg dem som "förfallna" trots att april redan hänt.
    """
    from hembudget.api.v2 import _seed_initial_student_data
    from hembudget.db.models import MailItem
    from hembudget.school.models import Student as _S

    _client, tch, *_ = fx
    # Skapa elev (utlöser seed)
    create_r = _client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "first_name": "Greta",
            "archetype": "vard_underskoterska",
            "starting_level": 1,
        },
    )
    assert create_r.status_code == 200, create_r.text
    sid_g = create_r.json()["student_id"]

    # Kolla i scope-DB att alla fakturor från förra månaden är paid
    from datetime import date as _d
    today = _d.today()
    if today.month == 1:
        prev_y, prev_m = today.year - 1, 12
    else:
        prev_y, prev_m = today.year, today.month - 1
    period_start = _d(prev_y, prev_m, 1)
    period_end = (
        _d(prev_y + 1, 1, 1) if prev_m == 12
        else _d(prev_y, prev_m + 1, 1)
    )

    def check(s) -> None:
        prev_invoices = (
            s.query(MailItem)
            .filter(MailItem.mail_type == "invoice")
            .filter(MailItem.due_date >= period_start)
            .filter(MailItem.due_date < period_end)
            .all()
        )
        # Det ska finnas några fakturor från förra månaden
        assert len(prev_invoices) > 0, (
            "fixed_expenses skapar normalt 5-7 fakturor per månad"
        )
        # Alla ska vara paid (autogiro)
        unhandled = [m for m in prev_invoices if m.status != "paid"]
        assert not unhandled, (
            f"April-fakturor som inte är paid: "
            f"{[(m.id, m.status, m.subject) for m in unhandled]}"
        )
        # Lönespec från förra månaden ska också vara hanterad
        # — annars ligger den som "ohanterad · förfaller 25 apr"
        # i postlådan på 5:e maj, vilket är pedagogiskt fel.
        prev_payslips = (
            s.query(MailItem)
            .filter(MailItem.mail_type == "salary_slip")
            .filter(MailItem.due_date >= period_start)
            .filter(MailItem.due_date < period_end)
            .all()
        )
        assert len(prev_payslips) > 0, (
            "salary_phase ska ha seedat en lönespec för förra månaden"
        )
        unhandled_pay = [m for m in prev_payslips if m.status != "paid"]
        assert not unhandled_pay, (
            f"April-lönespecar som inte är paid: "
            f"{[(m.id, m.status, m.subject) for m in unhandled_pay]}"
        )

    _seed_scope(sid_g, check)


def test_v2_teacher_list_created_students(fx) -> None:
    client, tch, *_ = fx
    # Eva finns från fixture (ej aktiverad)
    r = client.get(
        "/v2/teacher/students/created",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_count"] == 1
    assert data["pending_activation_count"] == 1

    # Skapa en till
    client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {tch}"},
        json={"first_name": "Otto", "last_initial": "L"},
    )
    r = client.get(
        "/v2/teacher/students/created",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    assert data["total_count"] == 2
    assert data["pending_activation_count"] == 2
    # Senaste först (Otto)
    assert "Otto" in data["rows"][0]["student_name"]


def test_v2_teacher_create_student_level_3_skips_onboarding(fx) -> None:
    """Starting level > 1 → onboarding_completed=True direkt."""
    from hembudget.school.models import Student as _S

    client, tch, *_ = fx
    r = client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "first_name": "Erik",
            "starting_level": 3,
            "spend_profile": "slosa",
        },
    )
    sid = r.json()["student_id"]
    with master_session() as db:
        st = db.get(_S, sid)
        assert st.onboarding_completed is True
        assert st.v2_level == 3
        assert st.v2_spend_profile == "slosa"


def test_v2_teacher_create_student_seeds_initial_data(fx) -> None:
    """Ny elev ska få initial-data (lön + utgifter + mail + försäkring +
    pension) direkt vid skapande, så hen inte ser tomt skal vid första
    inloggning."""
    from hembudget.school.engines import (
        get_scope_session, scope_context, scope_for_student,
    )
    from hembudget.school.models import Student as _S
    from hembudget.school.game_engine_models import WeekTickRun
    from hembudget.db.models import (
        Account as _Acc, InsurancePolicy, MailItem as _Mail,
        PensionAssumption, Transaction as _Tx,
    )

    client, tch, *_ = fx
    r = client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "first_name": "Linn",
            "last_initial": "B",
            "archetype": "random",
            "spend_profile": "balanserad",
            "starting_level": 1,
        },
    )
    assert r.status_code == 200, r.text
    sid = r.json()["student_id"]

    # 1. Master-DB ska ha en WeekTickRun för förra månaden
    with master_session() as db:
        runs = db.query(WeekTickRun).filter(
            WeekTickRun.student_id == sid,
        ).all()
        assert len(runs) >= 1, "tick_month skulle ha kört åtminstone en gång"
        assert runs[0].status == "completed"
        # Plocka student för scope-key
        st = db.get(_S, sid)
        assert st is not None
        scope_key = scope_for_student(st)

    # 2. Scope-DB · konton + lönespec + fakturor + lön-transaktion
    maker = get_scope_session(scope_key)
    with scope_context(scope_key):
        with maker() as s:
            # === Konton ===
            accounts = s.query(_Acc).all()
            assert len(accounts) >= 1, (
                "tick_month skulle ha skapat minst lönekontot"
            )
            account_types = {a.type for a in accounts}
            assert "checking" in account_types, (
                "Lönekontot (checking) saknas — tick_month "
                "ensure_scope_accounts har inte körts"
            )

            # === Transaktioner ===
            txs = s.query(_Tx).all()
            assert len(txs) >= 1, (
                "tick_month skulle ha skapat minst lönen"
            )
            # Det ska finnas minst en INKOMST-transaktion (positiv) =
            # lönen som ramlade in
            income_txs = [t for t in txs if t.amount and t.amount > 0]
            assert len(income_txs) >= 1, (
                f"Lön-inbetalning saknas. Hittade {len(txs)} txs men "
                f"ingen positiv → spelmotorn matade inte lönespecen."
            )
            # Det ska finnas minst en utgift (fasta utgifter genererade)
            expense_txs = [t for t in txs if t.amount and t.amount < 0]
            # Inte assert — fasta utgifter beror på random men "lön in"
            # är garanterat. Vi vill iaf veta att det inte är 0.

            # === Postlådan: lönespec + fakturor ===
            mails = s.query(_Mail).all()
            assert len(mails) >= 1, (
                f"Postlådan tom efter tick_month — borde ha minst "
                f"lönespecen. Hittade 0 mail-items."
            )
            mail_types = {m.mail_type for m in mails}
            assert "salary_slip" in mail_types, (
                f"Lönespecen saknas i postlådan. Hittade typer: "
                f"{mail_types}. Spelmotorn skickade inte lönespecen."
            )
            # Fasta-utgifts-fakturor (hyra, abonnemang) → invoices
            invoice_count = sum(1 for m in mails if m.mail_type == "invoice")
            assert invoice_count >= 1, (
                f"Inga fakturor i postlådan. Spelmotorn skickade inte "
                f"de fasta utgifterna (hyra, abonnemang) som mail. "
                f"Mail-typer: {mail_types}"
            )

            # === Försäkring + pension seedade ===
            policies = s.query(InsurancePolicy).all()
            assert len(policies) >= 1, (
                "seed_default_insurance_policies skulle ha skapat "
                "default-katalogen"
            )
            pa = s.query(PensionAssumption).first()
            assert pa is not None, (
                "seed_default_pension skulle ha skapat singleton"
            )


# === TeacherStudentHistoryV2 (p-historik) — Fas 2Y ===


def test_v2_teacher_history_blocks_other_teacher(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/activity-log",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


def test_v2_teacher_history_blocks_students(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/activity-log",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 403


def test_v2_teacher_history_basic_shape(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/activity-log",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert "stats" in data
    assert isinstance(data["events"], list)


def test_v2_teacher_history_aggregates_multiple_kinds(fx) -> None:
    """Skapa events av flera typer → alla syns i timeline."""
    from hembudget.school.models import (
        StudentActivity as _SA,
        Module as _M, ModuleStep as _MS,
        StudentStepProgress as _SSP,
        Assignment as _A,
        V2OnboardingEvent as _OE,
    )
    from hembudget.school.employer_models import (
        SalaryNegotiation as _SN,
        NegotiationRound as _NR,
    )
    from datetime import datetime as _dt
    from decimal import Decimal as _D

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        # Onboarding
        db.add(_OE(
            student_id=sid, step=8,
            event_type="completed", duration_ms=11000,
        ))
        # StudentActivity
        db.add(_SA(
            student_id=sid, kind="transaction.created",
            summary="Klassade 5 transaktioner i april",
        ))
        # Modul-steg
        m = _M(teacher_id=tid, title="ISK-modul", is_template=False)
        db.add(m); db.flush()
        st = _MS(
            module_id=m.id, sort_order=0,
            kind="reflect", title="Vad är ISK?",
        )
        db.add(st); db.flush()
        db.add(_SSP(
            student_id=sid, step_id=st.id,
            completed_at=_dt.utcnow(),
            data={"reflection": "ord"},
        ))
        # Maria-runda
        n = _SN(
            student_id=sid, profession="X", employer="Y",
            starting_salary=_D("25000.00"),
            status="active",
        )
        db.add(n); db.flush()
        db.add(_NR(
            negotiation_id=n.id, round_no=1,
            student_message="Yrkar 28k",
            employer_response="26 800",
            proposed_pct=7.2,
        ))
        # Uppdrag klart
        db.add(_A(
            teacher_id=tid, student_id=sid,
            title="Reflektion-uppgift",
            description="Skriv 200 ord",
            kind="free_text",
            manually_completed_at=_dt.utcnow(),
        ))
        db.commit()

    r = client.get(
        f"/v2/teacher/students/{sid}/activity-log",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    kinds = {e["kind"] for e in data["events"]}
    assert "onboarding" in kinds
    assert "transaction" in kinds
    assert "module_step" in kinds
    assert "maria_round" in kinds
    assert "assignment" in kinds
    assert data["stats"]["maria_rounds_count"] >= 1
    assert data["stats"]["module_steps_count"] >= 1
    assert data["stats"]["reflections_count"] >= 1


def test_v2_teacher_history_sorts_newest_first(fx) -> None:
    """Events sorteras nyast överst."""
    from hembudget.school.models import StudentActivity as _SA
    from datetime import datetime as _dt, timedelta as _td

    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        # Äldre event
        a1 = _SA(
            student_id=sid, kind="transaction.created",
            summary="Äldre tx",
        )
        a1.occurred_at = _dt.utcnow() - _td(days=10)
        db.add(a1)
        # Nyare event
        a2 = _SA(
            student_id=sid, kind="budget.set",
            summary="Nyare budget",
        )
        a2.occurred_at = _dt.utcnow() - _td(hours=2)
        db.add(a2)
        db.commit()

    r = client.get(
        f"/v2/teacher/students/{sid}/activity-log",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    titles = [e["title"] for e in data["events"]]
    # Den nyare ska komma först
    nyare_idx = titles.index("Nyare budget")
    aldre_idx = titles.index("Äldre tx")
    assert nyare_idx < aldre_idx


def test_v2_teacher_history_limit_param(fx) -> None:
    """limit-param respekteras."""
    from hembudget.school.models import StudentActivity as _SA

    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        for i in range(20):
            db.add(_SA(
                student_id=sid, kind="transaction.created",
                summary=f"tx {i}",
            ))
        db.commit()

    r = client.get(
        f"/v2/teacher/students/{sid}/activity-log?limit=5",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    assert len(data["events"]) == 5


# === Pentagon Axis Detail (Flip-card) — Fas 2Z ===


def test_v2_pentagon_axis_blocks_teachers(fx) -> None:
    """Elev-endpoint blockerar lärare."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/pentagon/axis/economy",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 403


def test_v2_pentagon_axis_basic_shape(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    for axis in ("economy", "safety", "health", "social", "leisure"):
        r = client.get(
            f"/v2/pentagon/axis/{axis}",
            headers={"Authorization": f"Bearer {stu}"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["axis"] == axis
        assert "axis_label" in data
        assert "score" in data
        assert "factors" in data
        assert "events" in data
        assert "summary_text" in data


def test_v2_pentagon_axis_invalid_404(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/pentagon/axis/karriar",
        headers={"Authorization": f"Bearer {stu}"},
    )
    # Ej en av Literal-typerna → 422
    assert r.status_code == 422


def test_v2_teacher_pentagon_axis(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/pentagon/axis/economy",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["detail"]["axis"] == "economy"
    assert data["detail"]["axis_label"] == "Ekonomi"


def test_v2_teacher_pentagon_axis_cross_teacher_403(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/pentagon/axis/economy",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


# === V2 Notifications (Fas 2AB · live-notiser) ===


def test_v2_notifications_empty_for_teacher(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/notifications",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["total_count"] == 0
    assert data["items"] == []


def test_v2_notifications_unauthenticated_401(fx) -> None:
    client, *_ = fx
    r = client.get("/v2/notifications")
    assert r.status_code == 401


def test_v2_notifications_assignment_appears(fx) -> None:
    from hembudget.school.models import Assignment as _A

    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        db.add(_A(
            teacher_id=tid, student_id=sid,
            title="Räkna KALP",
            description="Bolån för 2:a",
            kind="free_text",
        ))
        db.commit()
    r = client.get(
        "/v2/notifications",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r.json()
    assert data["summary"]["unread_count"] >= 1
    titles = [n["title"] for n in data["items"]]
    assert any("NYTT UPPDRAG" in t for t in titles)


def test_v2_notifications_teacher_message(fx) -> None:
    from hembudget.school.models import Message as _M

    client, _tch, _sa, stu, tid, _said, sid = fx
    with master_session() as db:
        db.add(_M(
            student_id=sid,
            teacher_id=tid,
            sender_role="teacher",
            body="Hej Eva, hur går det?",
        ))
        db.commit()
    r = client.get(
        "/v2/notifications",
        headers={"Authorization": f"Bearer {stu}"},
    )
    data = r.json()
    titles = [n["title"] for n in data["items"]]
    assert any("Meddelande" in t for t in titles)
    # Olästa räknas
    assert data["summary"]["unread_count"] >= 1


# === Lärar-notiser (Fas 2AE) ===


def test_v2_notifications_teacher_empty(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/notifications",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200
    data = r.json()
    # Default: 1 elev (Eva) inaktiv → "behöver stöd"-notis kan dyka upp
    assert "items" in data


def test_v2_notifications_teacher_new_reflection(fx) -> None:
    """Klar reflektion utan teacher_feedback → notis till läraren."""
    from hembudget.school.models import (
        Module as _M, ModuleStep as _MS,
        StudentStepProgress as _SSP,
    )
    from datetime import datetime as _dt

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        m = _M(teacher_id=tid, title="X", is_template=False)
        db.add(m); db.flush()
        st = _MS(
            module_id=m.id, sort_order=0,
            kind="reflect", title="Vad lärde du dig?",
        )
        db.add(st); db.flush()
        db.add(_SSP(
            student_id=sid, step_id=st.id,
            completed_at=_dt.utcnow(),
            data={"reflection": "Bra reflektion utan flagga."},
        ))
        db.commit()
    r = client.get(
        "/v2/notifications",
        headers={"Authorization": f"Bearer {tch}"},
    )
    titles = [n["title"] for n in r.json()["items"]]
    assert any("Ny reflektion" in t for t in titles)


def test_v2_notifications_teacher_overdue_assignment(fx) -> None:
    from hembudget.school.models import Assignment as _A
    from datetime import datetime as _dt, timedelta as _td

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        db.add(_A(
            teacher_id=tid, student_id=sid,
            title="Försenad uppgift",
            description="x",
            kind="free_text",
            due_date=_dt.utcnow() - _td(days=2),
        ))
        db.commit()
    r = client.get(
        "/v2/notifications",
        headers={"Authorization": f"Bearer {tch}"},
    )
    titles = [n["title"] for n in r.json()["items"]]
    assert any("FÖRSENAT" in t for t in titles)


def test_v2_notifications_caches_within_ttl(fx) -> None:
    """Andra anropet inom TTL ska vara cache-hit (ingen DB-trafik).
    Verifierar via att vi mutar master-DB:n MELLAN anropen och ser
    att svaret är oförändrat tills cachen invalideras."""
    from hembudget.school.models import Message as _M
    from hembudget.api.v2 import invalidate_notif_cache

    client, _tch, _sa, stu, tid, _said, sid = fx
    invalidate_notif_cache()  # rensa eventuell residual cache

    # 1) Första anropet — bygger upp cachen, 0 nya meddelanden
    r1 = client.get(
        "/v2/notifications",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r1.status_code == 200
    items1 = r1.json()["items"]
    msg_count_1 = sum(
        1 for n in items1 if n["title"] == "Meddelande från läraren"
    )

    # 2) Skicka ett meddelande direkt i master-DB
    with master_session() as db:
        db.add(_M(
            student_id=sid, teacher_id=tid,
            sender_role="teacher",
            body="Cache-test",
        ))
        db.commit()

    # 3) Andra anropet — ska INTE se det nya meddelandet (cache hit)
    r2 = client.get(
        "/v2/notifications",
        headers={"Authorization": f"Bearer {stu}"},
    )
    items2 = r2.json()["items"]
    msg_count_2 = sum(
        1 for n in items2 if n["title"] == "Meddelande från läraren"
    )
    assert msg_count_2 == msg_count_1, (
        "andra anropet inom TTL ska vara cache-hit; saw "
        f"{msg_count_1} → {msg_count_2}"
    )

    # 4) Invalidera och verifiera att det nya meddelandet syns
    invalidate_notif_cache("student", sid)
    r3 = client.get(
        "/v2/notifications",
        headers={"Authorization": f"Bearer {stu}"},
    )
    titles3 = [n["title"] for n in r3.json()["items"]]
    assert any("Meddelande" in t for t in titles3), (
        "efter cache-invalidate ska nytt meddelande synas"
    )


def test_v2_notifications_feedback_no_n_plus_one(fx) -> None:
    """10 reflektioner med feedback ska resultera i ENDA FeedbackRead-
    SELECT (batched), inte 10 (N+1).
    Mäter via SQLAlchemy event-counter på Session.execute."""
    from hembudget.school.models import (
        Module as _M, ModuleStep as _MS,
        StudentStepProgress as _SSP, FeedbackRead as _FR,
    )
    from hembudget.api.v2 import invalidate_notif_cache
    from sqlalchemy import event

    client, _tch, _sa, stu, tid, _said, sid = fx
    invalidate_notif_cache()

    # Seeda 10 reflektioner med teacher_feedback satt
    with master_session() as db:
        m = _M(teacher_id=tid, title="N+1", is_template=False)
        db.add(m); db.flush()
        for i in range(10):
            st = _MS(
                module_id=m.id, sort_order=i,
                kind="reflect", title=f"Q{i}",
            )
            db.add(st); db.flush()
            db.add(_SSP(
                student_id=sid, step_id=st.id,
                completed_at=datetime.utcnow(),
                feedback_at=datetime.utcnow(),
                teacher_feedback=f"Bra svar {i}!",
                data={"reflection": "Mitt svar"},
            ))
        db.commit()

    # Räkna antal queries mot FeedbackRead-tabellen.
    fr_query_count = {"n": 0}

    @event.listens_for(_FR, "load")
    def _on_load(_target, _ctx):  # pragma: no cover
        fr_query_count["n"] += 1

    # Räkna istället via raw SQL - lägg till statement-listener
    seen_statements: list[str] = []

    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "before_cursor_execute")
    def _on_exec(_conn, _cursor, statement, *_args, **_kwargs):
        if "feedback_reads" in statement.lower():
            seen_statements.append(statement)

    try:
        r = client.get(
            "/v2/notifications",
            headers={"Authorization": f"Bearer {stu}"},
        )
        assert r.status_code == 200
        # Grundkrav: notiserna ska finnas
        titles = [n["title"] for n in r.json()["items"]]
        feedback_notifs = [
            t for t in titles if "Feedback" in t
        ]
        assert len(feedback_notifs) == 10
        # Den kritiska assertionen: bara 1 SELECT mot feedback_reads,
        # inte 10. Tidigare: en per progress-rad inne i for-loopen.
        assert len(seen_statements) <= 1, (
            f"N+1 regression: {len(seen_statements)} queries mot "
            f"feedback_reads (förväntade ≤1).\n"
            f"Statements: {seen_statements}"
        )
    finally:
        event.remove(Engine, "before_cursor_execute", _on_exec)


def test_v2_notifications_teacher_flagged_reflection(fx) -> None:
    """Reflektion med 'behöver hjälp' → flag-notis."""
    from hembudget.school.models import (
        Module as _M, ModuleStep as _MS,
        StudentStepProgress as _SSP,
    )
    from datetime import datetime as _dt

    client, tch, _sa, _stu, tid, _said, sid = fx
    with master_session() as db:
        m = _M(teacher_id=tid, title="X", is_template=False)
        db.add(m); db.flush()
        st = _MS(
            module_id=m.id, sort_order=0,
            kind="reflect", title="Q",
        )
        db.add(st); db.flush()
        db.add(_SSP(
            student_id=sid, step_id=st.id,
            completed_at=_dt.utcnow(),
            data={"reflection": "Vet inte hur jag ska göra"},
        ))
        db.commit()
    r = client.get(
        "/v2/notifications",
        headers={"Authorization": f"Bearer {tch}"},
    )
    titles = [n["title"] for n in r.json()["items"]]
    assert any("flaggar stöd-behov" in t for t in titles)


# === Skapa uppdrag (Fas 2AF) ===


def test_v2_teacher_create_assignment_blocks_students(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/uppdrag",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "title": "Uppdrag-test", "description": "Beskrivning",
            "kind": "free_text",
        },
    )
    assert r.status_code == 403


def test_v2_teacher_create_assignment_basic(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/uppdrag",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "title": "Räkna KALP för 2,4 Mkr",
            "description": "Hämta data från banken + lön + budget",
            "kind": "free_text",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["title"] == "Räkna KALP för 2,4 Mkr"
    assert data["kind"] == "free_text"

    # Visas nu i elevens uppdrag-lista
    r2 = client.get(
        "/v2/uppdrag",
        headers={"Authorization": f"Bearer {fx[3]}"},
    )
    titles = [a["title"] for a in r2.json()["active"]]
    assert "Räkna KALP för 2,4 Mkr" in titles


def test_v2_teacher_create_assignment_cross_teacher_403(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/uppdrag",
        headers={"Authorization": f"Bearer {sa}"},
        json={
            "title": "Uppdrag-test", "description": "Beskrivning",
            "kind": "free_text",
        },
    )
    assert r.status_code == 403


def test_v2_teacher_create_assignment_with_due_date(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/uppdrag",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "title": "Reflektion april",
            "description": "200+ ord",
            "kind": "free_text",
            "due_date": "2026-05-14T23:59:59",
        },
    )
    assert r.status_code == 200, r.text
    assert "2026-05-14" in r.json()["due_date"]


# === Nivå-promotion + kompetens-override (Fas 2AG) ===


def test_v2_teacher_promote_level_blocks_students(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/level-promote",
        headers={"Authorization": f"Bearer {stu}"},
        json={"target_level": 2},
    )
    assert r.status_code == 403


def test_v2_teacher_promote_level_basic(fx) -> None:
    from hembudget.school.models import Student as _S
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.post(
        f"/v2/teacher/students/{sid}/level-promote",
        headers={"Authorization": f"Bearer {tch}"},
        json={"target_level": 2, "motivation": "Klar för balanserad."},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["previous_level"] == 1
    assert data["new_level"] == 2
    assert data["new_spend_profile"] == "balanserad"

    with master_session() as db:
        st = db.get(_S, sid)
        assert st.v2_level == 2
        assert st.v2_spend_profile == "balanserad"


def test_v2_teacher_promote_level_already_400(fx) -> None:
    """Försök bumpa till nivå som redan är aktiv → 400."""
    from hembudget.school.models import Student as _S
    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        st = db.get(_S, sid)
        st.v2_level = 2
        db.commit()
    r = client.post(
        f"/v2/teacher/students/{sid}/level-promote",
        headers={"Authorization": f"Bearer {tch}"},
        json={"target_level": 2},
    )
    assert r.status_code == 400


def test_v2_teacher_competency_override_basic(fx) -> None:
    from hembudget.school.models import Competency as _Comp
    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        c = _Comp(
            key="bokforing", name="Bokföring",
            level="grund", is_system=True,
        )
        db.add(c); db.flush()
        cid = c.id
        db.commit()

    r = client.post(
        f"/v2/teacher/students/{sid}/kompetens/{cid}/override",
        headers={"Authorization": f"Bearer {tch}"},
        json={
            "level": "F",
            "motivation": "Klassrum-diskussion visade fördjupning.",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["level"] == "F"
    assert "diskussion" in data["motivation"]

    # Portfolio respekterar override (mastery=0 men nivå=F)
    r2 = client.get(
        "/v2/portfolio",
        headers={"Authorization": f"Bearer {fx[3]}"},
    )
    bokforing = next(
        c for c in r2.json()["competencies"] if c["key"] == "bokforing"
    )
    assert bokforing["level"] == "F"
    assert bokforing["level_label"] == "FÖRDJUPNING"


def test_v2_teacher_competency_override_update(fx) -> None:
    """Andra POST på samma kompetens ska uppdatera, inte duplicera."""
    from hembudget.school.models import (
        Competency as _Comp,
        StudentCompetencyOverride as _SCO,
    )
    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        c = _Comp(key="x", name="X", level="grund", is_system=True)
        db.add(c); db.flush()
        cid = c.id
        db.commit()

    client.post(
        f"/v2/teacher/students/{sid}/kompetens/{cid}/override",
        headers={"Authorization": f"Bearer {tch}"},
        json={"level": "G", "motivation": "Första försök."},
    )
    r = client.post(
        f"/v2/teacher/students/{sid}/kompetens/{cid}/override",
        headers={"Authorization": f"Bearer {tch}"},
        json={"level": "F", "motivation": "Höjd igen."},
    )
    assert r.status_code == 200
    with master_session() as db:
        rows = db.query(_SCO).filter(_SCO.student_id == sid).all()
        assert len(rows) == 1
        assert rows[0].level == "F"


def test_v2_teacher_competency_override_delete(fx) -> None:
    from hembudget.school.models import (
        Competency as _Comp,
        StudentCompetencyOverride as _SCO,
    )
    client, tch, _sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        c = _Comp(key="x", name="X", level="grund", is_system=True)
        db.add(c); db.flush()
        cid = c.id
        db.commit()
    client.post(
        f"/v2/teacher/students/{sid}/kompetens/{cid}/override",
        headers={"Authorization": f"Bearer {tch}"},
        json={"level": "F", "motivation": "höj"},
    )
    r = client.delete(
        f"/v2/teacher/students/{sid}/kompetens/{cid}/override",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    with master_session() as db:
        assert db.query(_SCO).count() == 0


def test_v2_teacher_competency_override_cross_teacher_403(fx) -> None:
    from hembudget.school.models import Competency as _Comp
    client, _tch, sa, _stu, _tid, _said, sid = fx
    with master_session() as db:
        c = _Comp(key="x", name="X", level="grund", is_system=True)
        db.add(c); db.flush()
        cid = c.id
        db.commit()
    r = client.post(
        f"/v2/teacher/students/{sid}/kompetens/{cid}/override",
        headers={"Authorization": f"Bearer {sa}"},
        json={"level": "F", "motivation": "test"},
    )
    assert r.status_code == 403


# === Klass-pentagon axis-detail (Fas 2AH) ===


def test_v2_klass_pentagon_axis_blocks_students(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/klass-pentagon/axis/economy",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 403


def test_v2_klass_pentagon_axis_basic(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    for axis in ("economy", "safety", "health", "social", "leisure"):
        r = client.get(
            f"/v2/teacher/klass-pentagon/axis/{axis}",
            headers={"Authorization": f"Bearer {tch}"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["axis"] == axis
        assert data["student_count"] == 1
        assert "distribution" in data
        assert "top_contributors" in data
        assert "bottom_contributors" in data
        assert "summary_text" in data


def test_v2_klass_pentagon_axis_includes_students(fx) -> None:
    """Med 3 elever ska top + bottom contain elev-rader."""
    from hembudget.school.models import Student as _S
    client, tch, _sa, _stu, tid, _said, _sid = fx
    with master_session() as db:
        for i in range(3):
            db.add(_S(
                teacher_id=tid,
                display_name=f"Elev {i}",
                login_code=f"E{i:07d}",
            ))
        db.commit()
    r = client.get(
        "/v2/teacher/klass-pentagon/axis/economy",
        headers={"Authorization": f"Bearer {tch}"},
    )
    data = r.json()
    assert data["student_count"] == 4  # original Eva + 3
    assert len(data["top_contributors"]) >= 1
    assert len(data["bottom_contributors"]) >= 1


# === Lärar-impersonation av v2/hub (Fas 2AI) ===


def test_v2_hub_supports_teacher_impersonation(fx) -> None:
    """Lärare med x-as-student kan se elevens v2/hub-data."""
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/hub",
        headers={
            "Authorization": f"Bearer {tch}",
            "x-as-student": str(sid),
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Får elevens student_id (Eva), inte 0
    assert data["student_id"] == sid


def test_v2_hub_teacher_without_impersonation_empty(fx) -> None:
    """Lärare utan x-as-student → tom payload (orörd från innan)."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/hub",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200
    assert r.json()["student_id"] == 0


def test_v2_hub_cross_teacher_impersonation_blocked(fx) -> None:
    """Annan lärare kan inte impersonera första lärarens elev."""
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        "/v2/hub",
        headers={
            "Authorization": f"Bearer {sa}",
            "x-as-student": str(sid),
        },
    )
    # Middleware filtrerar bort student-id som inte tillhör läraren →
    # actor sätts inte → tom payload
    assert r.status_code == 200
    assert r.json()["student_id"] == 0


# === Login-QR (Fas 2AJ) ===


def test_v2_teacher_login_qr_blocks_students(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/login-qr",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 403


def test_v2_teacher_login_qr_basic(fx) -> None:
    client, tch, _sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/login-qr",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["student_id"] == sid
    assert data["login_code"]  # icke-tom
    assert "ekonomilabbet" in data["login_url"]
    assert data["login_code"] in data["login_url"]
    # SVG bör börja med <?xml eller <svg
    assert "<svg" in data["qr_svg"] or "<?xml" in data["qr_svg"]


def test_v2_teacher_login_qr_cross_teacher_403(fx) -> None:
    client, _tch, sa, _stu, _tid, _said, sid = fx
    r = client.get(
        f"/v2/teacher/students/{sid}/login-qr",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 403


def test_v2_teacher_login_qr_404_when_unknown_student(fx) -> None:
    """Saknad elev → 403 (treatas som cross-teacher)."""
    client, tch, _sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/students/9999/login-qr",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 403


# === Bulk login-QR (Fas 2AP) ===


def test_v2_teacher_login_qr_bulk_blocks_students(fx) -> None:
    client, _tch, _sa, stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/students/login-qr-bulk",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 403


def test_v2_teacher_login_qr_bulk_returns_all(fx) -> None:
    """Två elever → båda har QR i payload."""
    from hembudget.school.models import Student as _S
    client, tch, _sa, _stu, tid, _said, _sid = fx
    with master_session() as db:
        db.add(_S(
            teacher_id=tid, display_name="Hassan",
            login_code="HAS00099",
        ))
        db.commit()

    r = client.get(
        "/v2/teacher/students/login-qr-bulk",
        headers={"Authorization": f"Bearer {tch}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["items"]) == 2
    for it in data["items"]:
        assert "<svg" in it["qr_svg"] or "<?xml" in it["qr_svg"]
        assert it["login_code"]
        assert it["login_code"] in it["login_url"]


def test_v2_teacher_login_qr_bulk_only_own_students(fx) -> None:
    """Annan lärare ska inte se första lärarens elever."""
    client, _tch, sa, _stu, _tid, _said, _sid = fx
    r = client.get(
        "/v2/teacher/students/login-qr-bulk",
        headers={"Authorization": f"Bearer {sa}"},
    )
    assert r.status_code == 200
    # Super-admin-läraren har inga elever
    assert r.json()["items"] == []


# =================================================================
# /v2/lan/apply — eleven ansöker själv om lån
# =================================================================

def _create_seeded_student_and_get_token(client, tch_tok, **overrides):
    """Helper: skapa en elev + få student-token för loan-tester."""
    create_r = client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {tch_tok}"},
        json={
            "first_name": "Lina",
            "archetype": "vard_underskoterska",
            "starting_level": 1,
            **overrides,
        },
    )
    assert create_r.status_code == 200, create_r.text
    sid = create_r.json()["student_id"]
    # Hämta login-code så vi kan logga in som elev
    from hembudget.school.models import Student
    with master_session() as s:
        st = s.get(Student, sid)
        login_code = st.login_code
    login_r = client.post(
        "/student/login",
        json={"login_code": login_code},
    )
    assert login_r.status_code == 200, login_r.text
    return sid, login_r.json()["token"]


def test_v2_loan_apply_smslan_always_approved(fx) -> None:
    """SMS-lån godkänns även med dålig score — det är pedagogiska poängen."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)

    r = client.post(
        "/v2/lan/apply",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "loan_kind": "smslan",
            "amount": 5000,
            "term_months": 6,
            "purpose": "test",
            "accept_offer": False,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["approved"] is True
    assert data["loan_kind"] == "smslan"
    # Effektiv ränta måste vara minst 30 % (det är poängen)
    assert (data["offered_rate"] or 0) >= 0.30
    # Ska komma med varning
    assert any("rta" in w or "VARNING" in w for w in data["warnings"])


def test_v2_loan_apply_privatlan_huge_amount_kalp_declined(fx) -> None:
    """500k privatlån på 12 mån = ~45k/mån — KALP felar för alla."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)

    r = client.post(
        "/v2/lan/apply",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "loan_kind": "privatlan",
            "amount": 500000,
            "term_months": 12,
            "accept_offer": False,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["approved"] is False
    assert data["decline_reason"] is not None
    # Score returneras även vid avslag
    assert data["score"] >= 300


def test_v2_loan_apply_amount_outside_range_declined(fx) -> None:
    """Belopp utanför kind-spec → snabb-avslag."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)

    # SMS-lån max 30k — 100k ska avslås direkt
    r = client.post(
        "/v2/lan/apply",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "loan_kind": "smslan",
            "amount": 100000,
            "term_months": 6,
            "accept_offer": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["approved"] is False
    assert "ögsta belopp" in data["decline_reason"]


def test_v2_loan_apply_smslan_accept_creates_loan_and_tx(fx) -> None:
    """accept_offer=True med SMS-lån skapar Loan + utbetalningstx."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)

    # Hämta lönekontot (default-utbetalning)
    bank_r = client.get(
        "/v2/bank?account_id=0",
        headers={"Authorization": f"Bearer {stu}"},
    )
    accounts = bank_r.json()["accounts"]
    checking = next(a for a in accounts if a["type"] == "checking")

    r = client.post(
        "/v2/lan/apply",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "loan_kind": "smslan",
            "amount": 5000,
            "term_months": 6,
            "debit_account_id": checking["id"],
            "accept_offer": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["approved"] is True
    assert data["loan_id"] is not None

    # Verifiera Loan-rad i scope-DB
    from hembudget.db.models import Loan as _L, Transaction as _T, LoanScheduleEntry as _LSE
    from hembudget.school.engines import scope_for_student, scope_context, get_scope_session
    from hembudget.school.models import Student as _Stu
    with master_session() as ms:
        st = ms.get(_Stu, sid)
        sk = scope_for_student(st)
    with scope_context(sk):
        with get_scope_session(sk)() as ss:
            loan = ss.get(_L, data["loan_id"])
            assert loan is not None
            assert loan.is_high_cost_credit is True
            assert loan.loan_kind == "sms"

            # Utbetalningstx finns på checking — matchas via amount + lender
            tx = ss.query(_T).filter(
                _T.account_id == checking["id"],
                _T.amount == 5000,
                _T.normalized_merchant == loan.lender,
            ).first()
            assert tx is not None

            # Schedule-rader finns (interest + amort × 6 mån = 12)
            schedule = ss.query(_LSE).filter(_LSE.loan_id == loan.id).all()
            assert len(schedule) >= 6  # Minst en rad per månad


def test_v2_loan_apply_logs_activity_for_teacher(fx) -> None:
    """Lärar-spårning: loan.created loggas till StudentActivity."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)

    bank_r = client.get(
        "/v2/bank?account_id=0",
        headers={"Authorization": f"Bearer {stu}"},
    )
    checking = next(a for a in bank_r.json()["accounts"] if a["type"] == "checking")

    r = client.post(
        "/v2/lan/apply",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "loan_kind": "smslan",
            "amount": 5000,
            "term_months": 6,
            "debit_account_id": checking["id"],
            "accept_offer": True,
        },
    )
    assert r.status_code == 200

    # Verifiera att StudentActivity har loan.created
    from hembudget.school.models import StudentActivity
    with master_session() as ms:
        events = (
            ms.query(StudentActivity)
            .filter(StudentActivity.student_id == sid)
            .filter(StudentActivity.kind == "loan.created")
            .all()
        )
        assert len(events) == 1
        assert events[0].payload["loan_kind"] == "smslan"
        assert events[0].payload["amount"] == 5000


# =================================================================
# Sociala events / händelser i V2 (StudentEvent + ClassEventInvite)
# =================================================================

def _seed_event_for_student(sid: int, *, category: str = "social"):
    """Skapa en pending StudentEvent direkt i scope-DB:n."""
    from datetime import date, timedelta
    from decimal import Decimal as _Dec
    from hembudget.db.models import StudentEvent
    from hembudget.school.engines import (
        scope_for_student, scope_context, get_scope_session,
    )
    from hembudget.school.models import Student as _Stu
    with master_session() as ms:
        st = ms.get(_Stu, sid)
        sk = scope_for_student(st)
    with scope_context(sk):
        with get_scope_session(sk)() as ss:
            ev = StudentEvent(
                event_code="bio_filmstaden",
                title="Bio på Filmstaden",
                description="Klasskompisar bjuder dig på bio.",
                category=category,
                cost=_Dec("180"),
                deadline=date.today() + timedelta(days=4),
                source="system",
                status="pending",
                social_invite_allowed=True,
                declinable=True,
            )
            ss.add(ev)
            ss.commit()
            return ev.id


def _seed_event_template(code: str = "bio_filmstaden"):
    """Säkerställ att master har EventTemplate-raden så accept fungerar."""
    from hembudget.school.event_models import EventTemplate
    with master_session() as ms:
        existing = (
            ms.query(EventTemplate)
            .filter(EventTemplate.code == code)
            .first()
        )
        if existing is None:
            tpl = EventTemplate(
                code=code,
                title="Bio på Filmstaden",
                description="Klasskompisar bjuder dig på bio.",
                category="social",
                cost_min=150, cost_max=200,
                impact_economy=-1,
                impact_social=3,
                impact_leisure=2,
            )
            ms.add(tpl)
            ms.commit()


def test_v2_event_accept_creates_tx_and_applies_pentagon(fx) -> None:
    """Accept ett event → skapar Transaction + applicerar pentagon-delta
    via apply_pentagon_delta. Tidigare buggen: impacts lagrades bara
    som JSON i ev.impact_applied — pentagon uppdaterades aldrig."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)
    _seed_event_template()
    ev_id = _seed_event_for_student(sid)

    # Acceptera
    r = client.post(
        f"/events/{ev_id}/accept",
        headers={"Authorization": f"Bearer {stu}"},
        json={},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "accepted"
    assert data["impact_applied"]["social"] == 3

    # Verifiera att WellbeingEvent-rader skapades (pentagon-delta)
    from hembudget.game_engine.pentagon.wellbeing_log import (
        pentagon_history_for_student,
    )
    history = pentagon_history_for_student(sid, days=7)
    # Vi förväntar minst en rad för axis='social' med reason_kind='event_accepted'
    social_rows = [
        h for h in history
        if h.axis == "social" and h.reason_kind == "event_accepted"
    ]
    assert len(social_rows) >= 1, (
        f"Pentagon-delta saknas — events: "
        f"{[(h.axis, h.reason_kind) for h in history]}"
    )


def test_v2_event_decline_logs_activity(fx) -> None:
    """Decline → log_activity 'event.declined' + ev pentagon-delta."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)
    _seed_event_template()
    ev_id = _seed_event_for_student(sid)

    r = client.post(
        f"/events/{ev_id}/decline",
        headers={"Authorization": f"Bearer {stu}"},
        json={"decision_reason": "valde sparande"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "declined"

    # Aktivitet loggad
    from hembudget.school.models import StudentActivity
    with master_session() as ms:
        events_ = (
            ms.query(StudentActivity)
            .filter(
                StudentActivity.student_id == sid,
                StudentActivity.kind == "event.declined",
            )
            .all()
        )
        assert len(events_) == 1


def test_v2_notifications_includes_pending_events(fx) -> None:
    """Pending StudentEvent ska dyka upp i /v2/notifications som social."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)
    _seed_event_for_student(sid, category="social")

    # Töm cachen så vi får färska data
    from hembudget.api import v2 as v2_mod
    v2_mod._notif_cache.clear()

    r = client.get(
        "/v2/notifications",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    event_notifs = [n for n in data["items"] if n["id"].startswith("event-")]
    assert len(event_notifs) >= 1
    assert event_notifs[0]["kind"] == "social"
    assert event_notifs[0]["target_route"] == "/v2/handelser"


def test_v2_hub_includes_pending_events(fx) -> None:
    """Hub-svaret ska innehålla pending_events-listan."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)
    _seed_event_for_student(sid, category="culture")

    r = client.get(
        "/v2/hub",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "pending_events" in data
    assert len(data["pending_events"]) >= 1
    assert data["pending_events"][0]["category"] == "culture"
    assert data["pending_events"][0]["kind"] == "event"


# =================================================================
# Dunning-flödet · auto-eskalering av obetalda fakturor
# =================================================================

def _seed_overdue_invoice(sid: int, *, days_overdue: int = 10):
    """Skapa en MailItem(invoice) som är overdue med X dagar."""
    from datetime import date, timedelta
    from decimal import Decimal as _Dec
    from hembudget.db.models import MailItem
    from hembudget.school.engines import (
        scope_for_student, scope_context, get_scope_session,
    )
    from hembudget.school.models import Student as _Stu
    with master_session() as ms:
        st = ms.get(_Stu, sid)
        sk = scope_for_student(st)
    with scope_context(sk):
        with get_scope_session(sk)() as ss:
            mi = MailItem(
                sender="Linköping Bostäder",
                sender_short="HYR",
                sender_kind="land",
                mail_type="invoice",
                subject="Hyresavi 2026-04",
                body="Hyra 5 265 kr",
                amount=_Dec("-5265"),
                due_date=date.today() - timedelta(days=days_overdue),
                status="unhandled",
                ocr_reference="A1B2C3D4",
                bankgiro="5402-3961",
            )
            ss.add(mi)
            ss.commit()
            return mi.id


def _scope_query(sid: int, fn):
    from hembudget.school.engines import (
        scope_for_student, scope_context, get_scope_session,
    )
    from hembudget.school.models import Student as _Stu
    with master_session() as ms:
        st = ms.get(_Stu, sid)
        sk = scope_for_student(st)
    with scope_context(sk):
        with get_scope_session(sk)() as ss:
            return fn(ss)


def test_v2_dunning_creates_paminnelse_after_5_days(fx) -> None:
    """5 dagar förbi förfall → Påminnelse-mail i postlådan + 60 kr avgift."""
    from hembudget.api import v2 as v2_mod
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)
    _seed_overdue_invoice(sid, days_overdue=7)
    v2_mod._dunning_cache.clear()

    v2_mod._run_dunning_for_student(sid)

    from hembudget.db.models import MailItem
    reminders = _scope_query(sid, lambda ss: ss.query(MailItem).filter(
        MailItem.mail_type == "reminder",
        MailItem.reminder_level == 1,
    ).all())
    assert len(reminders) == 1
    r = reminders[0]
    assert "Påminnelse" in r.subject
    assert float(r.amount) == -60


def test_v2_dunning_kronofogden_creates_payment_mark(fx) -> None:
    """60 dagar förbi förfall → Kronofogden + PaymentMark + UC-skuld."""
    from hembudget.api import v2 as v2_mod
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)
    _seed_overdue_invoice(sid, days_overdue=65)
    v2_mod._dunning_cache.clear()

    v2_mod._run_dunning_for_student(sid)

    from hembudget.db.models import MailItem, PaymentMark
    reminders = _scope_query(sid, lambda ss: ss.query(MailItem).filter(
        MailItem.mail_type == "reminder",
        MailItem.reminder_level == 4,
    ).all())
    assert len(reminders) == 1
    assert reminders[0].sender == "Kronofogdemyndigheten"

    marks = _scope_query(sid, lambda ss: ss.query(PaymentMark).filter(
        PaymentMark.kind == "kronofogden",
    ).all())
    assert len(marks) == 1


def test_v2_dunning_idempotent(fx) -> None:
    """Två körningar i rad ska inte skapa dubbla reminders."""
    from hembudget.api import v2 as v2_mod
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)
    _seed_overdue_invoice(sid, days_overdue=8)

    v2_mod._dunning_cache.clear()
    v2_mod._run_dunning_for_student(sid)
    v2_mod._dunning_cache.clear()  # bypass 60s cache
    v2_mod._run_dunning_for_student(sid)

    from hembudget.db.models import MailItem
    reminders = _scope_query(sid, lambda ss: ss.query(MailItem).filter(
        MailItem.mail_type == "reminder",
    ).all())
    # Bara en reminder per (parent, level)
    assert len(reminders) == 1


def test_v2_dunning_paid_via_match_does_not_trigger(fx) -> None:
    """Om upcoming-match finns → marker mailet som paid, ingen reminder."""
    from hembudget.api import v2 as v2_mod
    from hembudget.db.models import (
        MailItem, UpcomingTransaction, Transaction, Account,
    )
    from datetime import date, timedelta
    from decimal import Decimal as _Dec

    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)
    mid = _seed_overdue_invoice(sid, days_overdue=20)

    # Koppla mailet till en upcoming + matchande transaktion = "betald"
    def setup(ss):
        acc = ss.query(Account).filter(Account.type == "checking").first()
        tx = Transaction(
            account_id=acc.id, date=date.today() - timedelta(days=10),
            amount=_Dec("-5265"), currency="SEK",
            raw_description="Hyra Linköping Bostäder",
            normalized_merchant="Linköping Bostäder",
            hash="dunning-test-paid", user_verified=True,
        )
        ss.add(tx); ss.flush()
        upc = UpcomingTransaction(
            kind="bill", name="Hyra", amount=_Dec("5265"),
            expected_date=date.today() - timedelta(days=20),
            matched_transaction_id=tx.id,
        )
        ss.add(upc); ss.flush()
        m = ss.get(MailItem, mid)
        m.upcoming_id = upc.id
        ss.commit()
    _scope_query(sid, setup)

    v2_mod._dunning_cache.clear()
    v2_mod._run_dunning_for_student(sid)

    # Inga reminders ska ha skapats — och original-mailet ska markerats
    # som paid eftersom det är matchat
    def check(ss):
        reminders = ss.query(MailItem).filter(
            MailItem.mail_type == "reminder",
        ).all()
        m = ss.get(MailItem, mid)
        return len(reminders), m.status
    n, status = _scope_query(sid, check)
    assert n == 0
    assert status == "paid"


# =================================================================
# Arbetsförmedlingen · Sprint 7 · personligt brev + AI-bedömning
# =================================================================

def test_v2_arbetsformedlingen_jobs_have_full_ad_data(fx) -> None:
    """Job-listan ska returnera utökad annons-data: requirements,
    meriter, benefits, employment_type, application_deadline."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)

    r = client.get(
        "/v2/arbetsformedlingen/jobs?ym=2026-05",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["jobs"]) > 0
    j = data["jobs"][0]
    # Sprint 7-fält måste finnas
    for field in (
        "company_blurb", "job_description", "requirements",
        "meriter", "benefits", "employment_type",
        "application_deadline", "work_hours", "start_date",
    ):
        assert field in j, f"saknar {field}"
    assert isinstance(j["requirements"], list)
    assert len(j["requirements"]) > 0
    assert isinstance(j["benefits"], list)


def test_v2_arbetsformedlingen_apply_logs_activity(fx) -> None:
    """apply triggar log_activity('job.applied') för lärar-spårning."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)

    r = client.get(
        "/v2/arbetsformedlingen/jobs?ym=2026-05",
        headers={"Authorization": f"Bearer {stu}"},
    )
    job = r.json()["jobs"][0]
    apply_r = client.post(
        "/v2/arbetsformedlingen/apply",
        headers={"Authorization": f"Bearer {stu}"},
        json=job,
    )
    assert apply_r.status_code == 200, apply_r.text

    from hembudget.school.models import StudentActivity
    with master_session() as ms:
        events = (
            ms.query(StudentActivity)
            .filter(
                StudentActivity.student_id == sid,
                StudentActivity.kind == "job.applied",
            )
            .all()
        )
        assert len(events) == 1
        assert events[0].payload["yrke_key"] == job["yrke_key"]


def test_v2_arbetsformedlingen_round1_takes_text_not_slider(fx, monkeypatch) -> None:
    """Rond 1 tar nu cover_letter_text. Heuristik-fallback fungerar
    när AI inte är aktiv (för kort brev → låg score)."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)

    # Mocka AI så vi inte hittar Anthropic-klient
    from hembudget.school import ai as ai_mod
    monkeypatch.setattr(ai_mod, "evaluate_cover_letter", lambda **_: None)

    r = client.get(
        "/v2/arbetsformedlingen/jobs?ym=2026-05",
        headers={"Authorization": f"Bearer {stu}"},
    )
    job = r.json()["jobs"][0]
    apply_r = client.post(
        "/v2/arbetsformedlingen/apply",
        headers={"Authorization": f"Bearer {stu}"},
        json=job,
    )
    app_id = apply_r.json()["id"]

    # Skicka in rond 1 med kort text (heuristik ska ge låg score)
    short_text = "Hej, jag vill ha jobbet."
    round_r = client.post(
        f"/v2/arbetsformedlingen/applications/{app_id}/round",
        headers={"Authorization": f"Bearer {stu}"},
        json={"payload": {"cover_letter_text": short_text}},
    )
    assert round_r.status_code == 200, round_r.text
    out = round_r.json()
    assert out["round_n"] == 1
    # Score_delta ska vara negativt för kort text
    assert out["score_delta"] < 0
    assert "Personligt brev" in out["feedback_md"]


def test_v2_arbetsformedlingen_cover_letter_preview_short_text(fx) -> None:
    """Preview-endpoint kräver minst 30 ord."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)

    r = client.post(
        "/v2/arbetsformedlingen/cover-letter-preview",
        headers={"Authorization": f"Bearer {stu}"},
        json={
            "text": "Hej jag vill ha jobbet",
            "yrke_display": "IT-konsult",
            "employer_name": "Visma",
        },
    )
    assert r.status_code == 400
    assert "30 ord" in r.json()["detail"]


def test_v2_arbetsformedlingen_apply_stores_full_ad_in_application(fx) -> None:
    """När eleven söker ska job_ad_data sparas på applikationen så
    lärar-vy senare kan visa exakt vad eleven såg."""
    client, tch, *_ = fx
    sid, stu = _create_seeded_student_and_get_token(client, tch)

    r = client.get(
        "/v2/arbetsformedlingen/jobs?ym=2026-05",
        headers={"Authorization": f"Bearer {stu}"},
    )
    job = r.json()["jobs"][0]
    apply_r = client.post(
        "/v2/arbetsformedlingen/apply",
        headers={"Authorization": f"Bearer {stu}"},
        json=job,
    )
    assert apply_r.status_code == 200
    app_id = apply_r.json()["id"]

    # Verifiera att job_ad_data är sparad i scope-DB
    from hembudget.db.models import JobApplication
    def check(ss):
        a = ss.get(JobApplication, app_id)
        return a.job_ad_data
    ad_data = _scope_query(sid, check)
    assert ad_data is not None
    assert "requirements" in ad_data
    assert "benefits" in ad_data
    assert ad_data["employment_type"] == job["employment_type"]
