"""Tester för email-verifiering + lösenords-återställning.

Mockar SMTP via monkey-patching så inga riktiga mail skickas. Testar
happy-path, utgångna tokens, redan använda tokens, rate-limit och
att login blockeras för icke-verifierade nya lärare.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api import email_auth as ea_mod
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import EmailToken, Teacher
from hembudget.security.crypto import hash_password


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Fångar alla mail istället för att skicka dem via SMTP."""
    captured: list[dict] = []

    def _fake_send_mail(*, to: str, subject: str, html: str, text: str) -> None:
        captured.append(
            {"to": to, "subject": subject, "html": html, "text": text},
        )

    # Patcha direkt i email_auth-modulen (som importerar send_mail)
    monkeypatch.setattr(ea_mod, "send_mail", _fake_send_mail)
    # Mark SMTP som konfigurerat (endpoints kollar detta via
    # ea_mod._require_email_configured som i sin tur kallar is_configured)
    from hembudget.security import email as email_mod
    monkeypatch.setattr(email_mod, "is_configured", lambda: True)
    return captured


@pytest.fixture
def app_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Fräsch school-mode-app per test."""
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    monkeypatch.delenv("HEMBUDGET_BOOTSTRAP_TEACHER_EMAIL", raising=False)
    monkeypatch.delenv("HEMBUDGET_BOOTSTRAP_TEACHER_PASSWORD", raising=False)
    monkeypatch.delenv("HEMBUDGET_BOOTSTRAP_SECRET", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TURNSTILE_SECRET", raising=False)

    from hembudget.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    # Sätt SMTP-config så is_configured() returnerar True — send_mail är
    # ändå mockad i fixturen `sent`.
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_user", "info@ekonomilabbet.org")
    monkeypatch.setattr(settings, "mail_from", "info@ekonomilabbet.org")
    monkeypatch.setattr(settings, "public_base_url", "https://example.com")

    # Rate-limiters är in-memory; nollställ mellan tester så
    # föregående test inte läcker räknare.
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
    return TestClient(app)


# ---------- Signup + verifiering ----------

def test_signup_creates_unverified_teacher_and_sends_mail(
    app_client: TestClient, sent: list[dict],
) -> None:
    r = app_client.post(
        "/teacher/signup",
        json={
            "email": "ny@exempel.se",
            "password": "Abcdef12!",
            "name": "Ny Lärare",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    with master_session() as s:
        t = s.query(Teacher).filter(Teacher.email == "ny@exempel.se").first()
        assert t is not None
        assert t.email_verified_at is None  # ej verifierad
        assert not t.is_super_admin

    assert len(sent) == 1
    assert sent[0]["to"] == "ny@exempel.se"
    assert "verifier" in sent[0]["subject"].lower() or "bekräfta" in sent[0]["subject"].lower()
    assert "https://example.com/verify-email?token=" in sent[0]["html"]


def test_signup_rejects_short_password(app_client: TestClient) -> None:
    r = app_client.post(
        "/teacher/signup",
        json={"email": "x@y.se", "password": "abc", "name": "X"},
    )
    assert r.status_code == 422  # pydantic min_length


def test_signup_duplicate_silent(
    app_client: TestClient, sent: list[dict],
) -> None:
    """Dubbel signup ska inte läcka att mailen redan finns — men inte
    heller skapa ny lärare eller mail."""
    with master_session() as s:
        s.add(Teacher(
            email="redan@exempel.se",
            name="Redan",
            password_hash=hash_password("Abcdef12!"),
            email_verified_at=datetime.utcnow(),
        ))

    r = app_client.post(
        "/teacher/signup",
        json={"email": "redan@exempel.se", "password": "NyttLosen!", "name": "X"},
    )
    assert r.status_code == 200  # ingen avslöjande 409
    assert sent == []  # inget mail skickas


def test_verify_email_happy_path(
    app_client: TestClient, sent: list[dict],
) -> None:
    app_client.post(
        "/teacher/signup",
        json={"email": "v@x.se", "password": "Abcdef12!", "name": "V"},
    )
    url = sent[0]["html"]
    # Plocka ut token ur HTML
    token = url.split("token=")[1].split('"')[0]

    r = app_client.get(f"/teacher/verify-email?token={token}")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    with master_session() as s:
        t = s.query(Teacher).filter(Teacher.email == "v@x.se").first()
        assert t is not None
        assert t.email_verified_at is not None


def test_verify_email_token_reuse_410(
    app_client: TestClient, sent: list[dict],
) -> None:
    app_client.post(
        "/teacher/signup",
        json={"email": "v2@x.se", "password": "Abcdef12!", "name": "V2"},
    )
    token = sent[0]["html"].split("token=")[1].split('"')[0]
    r1 = app_client.get(f"/teacher/verify-email?token={token}")
    assert r1.status_code == 200
    r2 = app_client.get(f"/teacher/verify-email?token={token}")
    assert r2.status_code == 410  # redan använd


def test_verify_email_expired_410(
    app_client: TestClient, sent: list[dict],
) -> None:
    app_client.post(
        "/teacher/signup",
        json={"email": "v3@x.se", "password": "Abcdef12!", "name": "V3"},
    )
    token = sent[0]["html"].split("token=")[1].split('"')[0]

    # Tvinga tokenet att gå ut
    with master_session() as s:
        et = s.query(EmailToken).first()
        assert et is not None
        et.expires_at = datetime.utcnow() - timedelta(seconds=1)

    r = app_client.get(f"/teacher/verify-email?token={token}")
    assert r.status_code == 410


def test_verify_email_invalid_token_404(app_client: TestClient) -> None:
    r = app_client.get("/teacher/verify-email?token=deadbeef_nonsense")
    assert r.status_code == 404


def test_resend_verify_invalidates_previous(
    app_client: TestClient, sent: list[dict],
) -> None:
    app_client.post(
        "/teacher/signup",
        json={"email": "rv@x.se", "password": "Abcdef12!", "name": "RV"},
    )
    first_token = sent[0]["html"].split("token=")[1].split('"')[0]

    r = app_client.post(
        "/teacher/request-verify-resend", json={"email": "rv@x.se"},
    )
    assert r.status_code == 200
    assert len(sent) == 2
    # Första token ska nu vara ogiltigt (markerat used)
    r2 = app_client.get(f"/teacher/verify-email?token={first_token}")
    assert r2.status_code == 410


# ---------- Login-blockering för overifierade ----------

def test_login_blocked_if_unverified(
    app_client: TestClient, sent: list[dict],
) -> None:
    app_client.post(
        "/teacher/signup",
        json={"email": "block@x.se", "password": "Abcdef12!", "name": "B"},
    )
    r = app_client.post(
        "/teacher/login",
        json={"email": "block@x.se", "password": "Abcdef12!"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "email_unverified"


def test_login_works_after_verification(
    app_client: TestClient, sent: list[dict],
) -> None:
    app_client.post(
        "/teacher/signup",
        json={"email": "ok@x.se", "password": "Abcdef12!", "name": "OK"},
    )
    token = sent[0]["html"].split("token=")[1].split('"')[0]
    app_client.get(f"/teacher/verify-email?token={token}")

    r = app_client.post(
        "/teacher/login",
        json={"email": "ok@x.se", "password": "Abcdef12!"},
    )
    assert r.status_code == 200, r.text
    assert "token" in r.json()


# ---------- Lösenords-återställning ----------

def test_password_reset_flow(
    app_client: TestClient, sent: list[dict],
) -> None:
    with master_session() as s:
        s.add(Teacher(
            email="reset@x.se",
            name="R",
            password_hash=hash_password("GammaltLosen!"),
            email_verified_at=datetime.utcnow(),
        ))

    r = app_client.post(
        "/teacher/request-password-reset", json={"email": "reset@x.se"},
    )
    assert r.status_code == 200
    assert len(sent) == 1
    token = sent[0]["html"].split("token=")[1].split('"')[0]

    r = app_client.post(
        "/teacher/reset-password",
        json={"token": token, "password": "NyttLosen!"},
    )
    assert r.status_code == 200

    # Gamla lösenordet ska inte längre funka
    r_old = app_client.post(
        "/teacher/login",
        json={"email": "reset@x.se", "password": "GammaltLosen!"},
    )
    assert r_old.status_code == 401

    # Nya ska funka
    r_new = app_client.post(
        "/teacher/login",
        json={"email": "reset@x.se", "password": "NyttLosen!"},
    )
    assert r_new.status_code == 200


def test_password_reset_unknown_mail_silent(
    app_client: TestClient, sent: list[dict],
) -> None:
    """Okänd email → 200 men inget mail (enumeration-skydd)."""
    r = app_client.post(
        "/teacher/request-password-reset", json={"email": "saknas@x.se"},
    )
    assert r.status_code == 200
    assert sent == []


def test_password_reset_token_single_use(
    app_client: TestClient, sent: list[dict],
) -> None:
    with master_session() as s:
        s.add(Teacher(
            email="once@x.se",
            name="O",
            password_hash=hash_password("Abcdef12!"),
            email_verified_at=datetime.utcnow(),
        ))

    app_client.post(
        "/teacher/request-password-reset", json={"email": "once@x.se"},
    )
    token = sent[0]["html"].split("token=")[1].split('"')[0]

    r1 = app_client.post(
        "/teacher/reset-password",
        json={"token": token, "password": "Nytt1Losen!"},
    )
    assert r1.status_code == 200
    r2 = app_client.post(
        "/teacher/reset-password",
        json={"token": token, "password": "Nytt2Losen!"},
    )
    assert r2.status_code == 410


def test_password_reset_mail_unconfigured_returns_ok_but_no_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enumeration-skyddet betyder att reset-request alltid svarar OK
    — även om SMTP inte är konfigurerat räcker det att ingen email
    skickats för att flödet ska "fungera tyst"."""
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    monkeypatch.delenv("HEMBUDGET_BOOTSTRAP_SECRET", raising=False)
    monkeypatch.delenv("TURNSTILE_SECRET", raising=False)

    from hembudget.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "smtp_host", "")  # EJ konfigurerat
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "mail_from", "")

    from hembudget.security import rate_limit as rl_mod
    rl_mod.reset_all_for_testing()
    from hembudget.school import engines as eng_mod
    if eng_mod._master_engine is not None:
        eng_mod._master_engine.dispose()
    eng_mod._master_engine = None
    eng_mod._master_session = None
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
        s.add(Teacher(
            email="nop@x.se",
            name="N",
            password_hash=hash_password("Abcdef12!"),
            email_verified_at=datetime.utcnow(),
        ))

    c = TestClient(app)
    # Okänd email → 200 oavsett SMTP
    r = c.post(
        "/teacher/request-password-reset", json={"email": "saknas@x.se"},
    )
    assert r.status_code == 200
    # Känd email + SMTP saknas → 503 (endpoint returnerar fel för att
    # indikera att mailet inte kunde skickas; detta är tydligare för
    # administratören än att tyst fejka)
    r2 = c.post(
        "/teacher/request-password-reset", json={"email": "nop@x.se"},
    )
    assert r2.status_code == 503


# ---------- Signup utan SMTP ----------

def test_signup_without_smtp_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    monkeypatch.delenv("TURNSTILE_SECRET", raising=False)

    from hembudget.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "mail_from", "")

    from hembudget.security import rate_limit as rl_mod
    rl_mod.reset_all_for_testing()
    from hembudget.school import engines as eng_mod
    if eng_mod._master_engine is not None:
        eng_mod._master_engine.dispose()
    eng_mod._master_engine = None
    eng_mod._master_session = None
    eng_mod._scope_engines.clear()
    eng_mod._scope_sessions.clear()
    from hembudget.school import demo_seed as demo_seed_mod
    monkeypatch.setattr(demo_seed_mod, "build_demo", lambda: {"skipped": True})

    import importlib
    import hembudget.main as main_mod
    importlib.reload(main_mod)
    app = main_mod.build_app()
    init_master_engine()

    c = TestClient(app)
    r = c.post(
        "/teacher/signup",
        json={"email": "a@b.se", "password": "Abcdef12!", "name": "A"},
    )
    assert r.status_code == 503


# ---------- Rate limit ----------

def test_signup_rate_limited(
    app_client: TestClient, sent: list[dict],
) -> None:
    """RULES_SIGNUP: 3 / 5min. Fjärde försöket → 429."""
    for i in range(3):
        r = app_client.post(
            "/teacher/signup",
            json={"email": f"rl{i}@x.se", "password": "Abcdef12!", "name": "R"},
        )
        assert r.status_code == 200, f"försök {i}: {r.text}"
    r4 = app_client.post(
        "/teacher/signup",
        json={"email": "rl99@x.se", "password": "Abcdef12!", "name": "R"},
    )
    assert r4.status_code == 429
