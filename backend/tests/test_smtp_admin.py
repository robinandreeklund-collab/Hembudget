"""Tester för super-admins SMTP-config-endpoints."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import AppConfig, Teacher
from hembudget.security import email as email_mod
from hembudget.security.crypto import hash_password, random_token
from hembudget.api.deps import register_token


@pytest.fixture
def fx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    monkeypatch.delenv("TURNSTILE_SECRET", raising=False)

    from hembudget.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    # Inga env-vars: DB ska vara enda källan
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "mail_from", "")

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
        admin = Teacher(
            email="admin@x.se", name="Admin",
            password_hash=hash_password("Abcdef12!"),
            is_super_admin=True,
        )
        regular = Teacher(
            email="t@x.se", name="T",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add_all([admin, regular]); s.flush()
        aid, rid = admin.id, regular.id
    a_tok, r_tok = random_token(), random_token()
    register_token(a_tok, role="teacher", teacher_id=aid)
    register_token(r_tok, role="teacher", teacher_id=rid)
    return TestClient(app), a_tok, r_tok


def _good_payload() -> dict:
    return {
        "host": "smtp.gmail.com",
        "port": 587,
        "user": "info@ekonomilabbet.org",
        "password": "abcdefghijklmnop",
        "starttls": True,
        "mail_from": "info@ekonomilabbet.org",
        "mail_from_name": "Ekonomilabbet",
        "public_base_url": "https://ekonomilabbet.org",
    }


def test_get_empty_config(fx) -> None:
    client, a_tok, _ = fx
    r = client.get("/admin/smtp/config",
                   headers={"Authorization": f"Bearer {a_tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is False
    assert body["source"] == ""
    assert body["password_set"] is False


def test_non_super_admin_forbidden(fx) -> None:
    client, _, r_tok = fx
    r = client.get("/admin/smtp/config",
                   headers={"Authorization": f"Bearer {r_tok}"})
    assert r.status_code == 403


def test_set_config_persists_and_marks_configured(fx) -> None:
    client, a_tok, _ = fx
    r = client.post("/admin/smtp/config",
                    json=_good_payload(),
                    headers={"Authorization": f"Bearer {a_tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is True
    assert body["source"] == "db"
    assert body["host"] == "smtp.gmail.com"
    assert body["password_set"] is True
    # Lösenordet ska INTE returneras klartext
    assert "abcdefghijklmnop" not in r.text

    # AppConfig-raden ska finnas i master-DB
    with master_session() as s:
        cfg = s.get(AppConfig, email_mod.SMTP_CONFIG_KEY)
        assert cfg is not None
        assert cfg.value["host"] == "smtp.gmail.com"
        assert cfg.value["password"] == "abcdefghijklmnop"


def test_password_optional_on_update(fx) -> None:
    client, a_tok, _ = fx
    # Sätt full config
    client.post("/admin/smtp/config", json=_good_payload(),
                headers={"Authorization": f"Bearer {a_tok}"})
    # Uppdatera utan att skicka password
    p = _good_payload()
    p["host"] = "smtp.example.com"
    p.pop("password")
    r = client.post("/admin/smtp/config", json=p,
                    headers={"Authorization": f"Bearer {a_tok}"})
    assert r.status_code == 200
    with master_session() as s:
        cfg = s.get(AppConfig, email_mod.SMTP_CONFIG_KEY)
        assert cfg.value["host"] == "smtp.example.com"
        # Lösenordet ska behållas
        assert cfg.value["password"] == "abcdefghijklmnop"


def test_delete_config_clears_db(fx) -> None:
    client, a_tok, _ = fx
    client.post("/admin/smtp/config", json=_good_payload(),
                headers={"Authorization": f"Bearer {a_tok}"})
    r = client.delete("/admin/smtp/config",
                      headers={"Authorization": f"Bearer {a_tok}"})
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    with master_session() as s:
        cfg = s.get(AppConfig, email_mod.SMTP_CONFIG_KEY)
        assert cfg is None


def test_test_endpoint_requires_config(fx) -> None:
    client, a_tok, _ = fx
    r = client.post("/admin/smtp/test", json={"to": "test@x.se"},
                    headers={"Authorization": f"Bearer {a_tok}"})
    assert r.status_code == 503


def test_test_endpoint_calls_send_mail(
    fx, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, a_tok, _ = fx
    client.post("/admin/smtp/config", json=_good_payload(),
                headers={"Authorization": f"Bearer {a_tok}"})
    sent: list[dict] = []
    monkeypatch.setattr(
        email_mod, "send_mail",
        lambda **kw: sent.append(kw),
    )
    r = client.post("/admin/smtp/test", json={"to": "verify@x.se"},
                    headers={"Authorization": f"Bearer {a_tok}"})
    assert r.status_code == 200
    assert len(sent) == 1
    assert sent[0]["to"] == "verify@x.se"
    assert "testmail" in sent[0]["subject"].lower()
