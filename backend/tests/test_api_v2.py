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
