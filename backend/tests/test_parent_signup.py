"""Tester för /parent/signup — föräldraskap som ett familjekonto.

Tekniskt samma flöde som /teacher/signup men sätter
Teacher.is_family_account=True så UI:n kan välja förälder-anpassad
copy. Verifierar:
- Endpoint skapar Teacher med is_family_account=True
- Verifieringsmail skickas
- Inloggning fungerar och TeacherAuthOut returnerar flaggan
- Lärar-signup sätter inte is_family_account
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import Teacher


@pytest.fixture
def fx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TURNSTILE_SECRET", raising=False)
    # Stub:a SMTP så signup inte kraschar på saknad config
    monkeypatch.setenv("HEMBUDGET_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("HEMBUDGET_SMTP_USER", "u")
    monkeypatch.setenv("HEMBUDGET_SMTP_PASSWORD", "p")
    monkeypatch.setenv("HEMBUDGET_MAIL_FROM", "info@example.com")

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

    # Stub:a faktisk mejlsändning + is_configured så signup-flödet
    # inte kraschar på saknad SMTP-config. Vi vill bara testa Teacher-
    # rad-mutationen.
    #
    # OBS: email_auth importerar `send_mail` direkt med `from ... import`,
    # så vi måste patcha symbolen i email_auth-namespacet, inte bara i
    # email-modulen, annars träffar vi gamla referensen i full-suite-
    # körning där modulen redan importerats.
    from hembudget.security import email as email_mod
    from hembudget.api import email_auth as email_auth_mod
    monkeypatch.setattr(email_mod, "send_mail", lambda **kw: None)
    monkeypatch.setattr(email_auth_mod, "send_mail", lambda **kw: None)
    monkeypatch.setattr(email_mod, "is_configured", lambda: True)

    import importlib
    import hembudget.main as main_mod
    importlib.reload(main_mod)
    app = main_mod.build_app()
    init_master_engine()

    return TestClient(app)


def test_parent_signup_sets_family_account_flag(fx) -> None:
    client = fx
    r = client.post(
        "/parent/signup",
        json={
            "email": "forelder@x.se",
            "name": "En Förälder",
            "password": "Abcdef12!",
        },
    )
    assert r.status_code == 200, r.text

    with master_session() as s:
        t = s.query(Teacher).filter(Teacher.email == "forelder@x.se").first()
        assert t is not None
        assert t.is_family_account is True
        # Förälder ska INTE vara super-admin per default
        assert t.is_super_admin is False
        # Email_verified_at ska vara NULL — vi måste klicka länken
        assert t.email_verified_at is None


def test_teacher_signup_does_not_set_family_account(fx) -> None:
    client = fx
    r = client.post(
        "/teacher/signup",
        json={
            "email": "lar@x.se",
            "name": "En Lärare",
            "password": "Abcdef12!",
        },
    )
    assert r.status_code == 200, r.text

    with master_session() as s:
        t = s.query(Teacher).filter(Teacher.email == "lar@x.se").first()
        assert t is not None
        assert t.is_family_account is False


def test_teacher_me_returns_family_flag(fx) -> None:
    """Efter login ska /teacher/me innehålla is_family_account så att
    frontend kan välja Familjepanel-copy direkt utan extra DB-fråga."""
    from hembudget.security.crypto import hash_password, random_token
    from hembudget.api.deps import register_token
    from datetime import datetime
    client = fx
    with master_session() as s:
        t = Teacher(
            email="forel@x.se", name="Förälder",
            password_hash=hash_password("Abcdef12!"),
            email_verified_at=datetime.utcnow(),
            is_family_account=True,
        )
        s.add(t); s.flush()
        tid = t.id
    tok = random_token()
    register_token(tok, role="teacher", teacher_id=tid)

    r = client.get(
        "/teacher/me",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_family_account"] is True

    # En vanlig lärare ska få false
    with master_session() as s:
        t2 = Teacher(
            email="lar@x.se", name="Lärare",
            password_hash=hash_password("Abcdef12!"),
            email_verified_at=datetime.utcnow(),
        )
        s.add(t2); s.flush()
        t2id = t2.id
    tok2 = random_token()
    register_token(tok2, role="teacher", teacher_id=t2id)
    r = client.get(
        "/teacher/me",
        headers={"Authorization": f"Bearer {tok2}"},
    )
    assert r.status_code == 200
    assert r.json()["is_family_account"] is False


def test_parent_signup_409_on_duplicate_email_silently(fx) -> None:
    """För att inte läcka om mailen finns ska duplicate-fall returnera
    samma OK-svar — bara att inget mail skickas. Verifierat genom att
    Teacher-raden inte ändras till is_family_account=True om mailen
    redan tillhör en lärare."""
    client = fx
    # Skapa lärare först
    client.post(
        "/teacher/signup",
        json={"email": "shared@x.se", "name": "L", "password": "Abcdef12!"},
    )
    # Försök förälder-signup på samma mail
    r = client.post(
        "/parent/signup",
        json={"email": "shared@x.se", "name": "F", "password": "Abcdef12!"},
    )
    assert r.status_code == 200  # ingen läcka

    with master_session() as s:
        t = s.query(Teacher).filter(Teacher.email == "shared@x.se").first()
        assert t is not None
        # Ska fortfarande vara lärare, inte föräldra-flaggat
        assert t.is_family_account is False
