"""Smoke-tester för /v2/* (parallell-migration).

Verifierar:
- /v2/status returnerar rätt fält för student/teacher/super-admin
- /v2/onboarding/complete sparar fält på Student-tabellen
- v2_eligible är alltid True (för super-admin är detta särskilt viktigt)
- 401 utan token
"""
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
    # Marknadsspann auto-räknat ±5-8 % runt brutto
    assert data["market_low"] is not None
    assert data["market_high"] is not None
    assert data["market_low"] < data["gross_salary_monthly"]
    assert data["market_high"] > data["gross_salary_monthly"]
    # Default-förmåner finns alltid (även utan agreement)
    assert len(data["agreement_benefits"]) >= 3
    benefit_names = [b["name"] for b in data["agreement_benefits"]]
    assert "Friskvårdsbidrag" in benefit_names
    assert "OB-tillägg" in benefit_names
    assert "Lönerevision" in benefit_names
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
    # Skatt = brutto − netto = 8850
    assert slips[0]["tax_amount"] == 8850


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


def test_v2_skatten_with_student_loan_has_csn_proposal(fx) -> None:
    """has_student_loan=True → ett CSN-ränteavdrag-förslag dyker upp."""
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
        ))
        db.commit()

    r = client.get(
        "/v2/skatten",
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["pending_proposal_count"] == 1
    proposals = [i for i in data["items"] if i["is_proposal"]]
    assert len(proposals) == 1
    assert proposals[0]["proposal_id"] == "csn-interest"
    # Avdraget gör skatten ~142 kr lägre (548 × 30 %)
    assert proposals[0]["amount"] < 0
    assert abs(proposals[0]["amount"]) > 100
    assert abs(proposals[0]["amount"]) < 200


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
