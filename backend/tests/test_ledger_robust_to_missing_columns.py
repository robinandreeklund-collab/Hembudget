"""Regression: /ledger/ får inte krascha när nya Loan-kolumner saknas i scope-DB.

Bakgrund (prod-bug 2026-04-26): scope-Postgres saknade
loans.loan_kind/is_high_cost_credit/applied_at/score_at_application
eftersom run_migrations aldrig kördes på shared-Postgres-engine + de
nya Loan-kolumnerna saknade ALTER-migrationer. SELECT på Loan i
ledger.py kraschade med 'column does not exist' → /teacher/students
+ /ledger/ blev oanvändbara.

Fixens två lager:
1. db/migrate.py är cross-dialect (Postgres IF NOT EXISTS) + har nu
   ALTER för de nya Loan-kolumnerna.
2. Loan-modellen markerar nya kolumner som deferred() — default-
   SELECT inkluderar dem inte, så lazy-load funkar oavsett om
   migrationen hunnit köra.

Testet patchar scope_columns-cachen för att låtsas att kolumnerna
saknas, sedan kör /ledger/ och förväntar sig 200 OK.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.engines import (
    get_scope_engine, init_master_engine, master_session, scope_for_student,
)
from hembudget.school.models import Student, Teacher
from hembudget.security.crypto import hash_password, random_token


@pytest.fixture
def fx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TURNSTILE_SECRET", raising=False)
    monkeypatch.delenv("HEMBUDGET_DATABASE_URL", raising=False)
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
    eng_mod._scope_columns.clear()
    from hembudget.school import demo_seed as demo_seed_mod
    monkeypatch.setattr(demo_seed_mod, "build_demo", lambda: {"skipped": True})

    import importlib
    import hembudget.main as main_mod
    importlib.reload(main_mod)
    app = main_mod.build_app()
    init_master_engine()

    with master_session() as s:
        t = Teacher(
            email="t@x.se", name="T",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(t); s.flush()
        stu = Student(
            teacher_id=t.id, display_name="A", login_code="LEDGER1",
        )
        s.add(stu); s.flush()
        sid = stu.id
        tid = t.id
    # Tvinga scope-engine att skapas (annars sätter middleware ingen scope)
    with master_session() as s:
        stu = s.query(Student).filter(Student.id == sid).first()
        get_scope_engine(scope_for_student(stu))

    teacher_tok = random_token()
    register_token(teacher_tok, role="teacher", teacher_id=tid)

    return TestClient(app), teacher_tok, sid


def test_ledger_works_when_new_loan_columns_missing(fx) -> None:
    """Simulerar prod-buggen: scope-DB:n saknar loan_kind etc. /ledger/
    måste fortfarande returnera 200 OK (tom data är fine)."""
    client, t_tok, sid = fx

    # Patcha scope-cachen så att de nya Loan-kolumnerna 'saknas'
    from hembudget.school import engines as eng_mod
    original = dict(eng_mod._scope_columns)
    loans_cols = set(eng_mod._scope_columns.get("loans", set()))
    loans_cols.discard("loan_kind")
    loans_cols.discard("is_high_cost_credit")
    loans_cols.discard("applied_at")
    loans_cols.discard("score_at_application")
    eng_mod._scope_columns["loans"] = loans_cols
    try:
        r = client.get(
            "/ledger/?year=2025",
            headers={
                "Authorization": f"Bearer {t_tok}",
                "X-As-Student": str(sid),
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "loans" in body
        assert "totals" in body
        assert "checks" in body
    finally:
        eng_mod._scope_columns.clear()
        eng_mod._scope_columns.update(original)


def test_ledger_returns_200_on_empty_scope(fx) -> None:
    """Sanity check: /ledger/ funkar med en helt tom scope-DB
    (ny elev utan transaktioner)."""
    client, t_tok, sid = fx
    r = client.get(
        "/ledger/?year=2025",
        headers={
            "Authorization": f"Bearer {t_tok}",
            "X-As-Student": str(sid),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["totals"]["income"] == 0
    assert body["totals"]["expenses"] == 0
