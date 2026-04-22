"""Tester för users CRUD + owner_id på konto + backup/restore + default-
debit-konto via settings-endpoint.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("HEMBUDGET_DEMO_MODE", "1")
    # Använd en filbaserad DB så VACUUM INTO funkar (i-minne klarar inte)
    monkeypatch.setenv("HEMBUDGET_DATA_DIR", str(tmp_path))

    from hembudget.db.models import Base

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False,
    )

    from hembudget import demo as demo_mod
    monkeypatch.setattr(demo_mod, "bootstrap_if_empty", lambda: {"skipped": True})

    from hembudget.api import deps as api_deps
    from hembudget.main import build_app

    app = build_app()

    def _fake_db():
        s = SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[api_deps.db] = _fake_db

    with TestClient(app) as c:
        yield c, SessionLocal, tmp_path


# ---------- Users CRUD ----------


def test_create_and_list_users(client):
    c, _, _ = client
    r = c.post("/users", json={"name": "Robin"})
    assert r.status_code == 200
    robin = r.json()
    assert robin["name"] == "Robin"
    assert robin["id"] >= 1

    r = c.post("/users", json={"name": "Evelina"})
    eve = r.json()

    r = c.get("/users")
    assert r.status_code == 200
    names = [u["name"] for u in r.json()]
    assert names == ["Robin", "Evelina"]
    assert eve["id"] != robin["id"]


def test_set_account_owner_via_patch(client):
    c, SL, _ = client
    # Skapa user + konto
    u = c.post("/users", json={"name": "Robin"}).json()
    acc = c.post(
        "/accounts",
        json={"name": "Privat", "bank": "nordea", "type": "checking"},
    ).json()
    assert acc["owner_id"] is None

    # Koppla ägare
    r = c.patch(f"/accounts/{acc['id']}", json={"owner_id": u["id"]})
    assert r.status_code == 200
    assert r.json()["owner_id"] == u["id"]

    # Verifiera i DB
    from hembudget.db.models import Account
    with SL() as s:
        a = s.get(Account, acc["id"])
        assert a.owner_id == u["id"]


def test_delete_user_clears_account_owner(client):
    c, SL, _ = client
    u = c.post("/users", json={"name": "Temp"}).json()
    acc = c.post(
        "/accounts",
        json={
            "name": "X", "bank": "nordea", "type": "checking",
            "owner_id": u["id"],
        },
    ).json()

    r = c.delete(f"/users/{u['id']}")
    assert r.status_code == 200

    # Konto finns kvar men owner_id är null
    from hembudget.db.models import Account
    with SL() as s:
        a = s.get(Account, acc["id"])
        assert a is not None
        assert a.owner_id is None


# ---------- Settings / default debit ----------


def test_settings_put_get_delete(client):
    c, _, _ = client
    r = c.put("/settings/default_debit_account_id", json={"value": 42})
    assert r.status_code == 200
    assert r.json() == {"key": "default_debit_account_id", "value": 42}

    r = c.get("/settings/default_debit_account_id")
    assert r.status_code == 200
    assert r.json()["value"] == 42

    r = c.get("/settings/")
    assert r.json() == {"default_debit_account_id": 42}

    r = c.delete("/settings/default_debit_account_id")
    assert r.status_code == 200
    r = c.get("/settings/default_debit_account_id")
    assert r.status_code == 404


def test_default_debit_applied_to_new_upcoming_bill(client):
    c, SL, _ = client
    acc = c.post(
        "/accounts",
        json={"name": "Löner", "bank": "nordea", "type": "checking"},
    ).json()
    c.put(
        "/settings/default_debit_account_id",
        json={"value": acc["id"]},
    )

    # Skapa en bill utan debit_account_id → ska få default
    r = c.post("/upcoming/", json={
        "kind": "bill",
        "name": "Elräkning",
        "amount": "1200.00",
        "expected_date": "2026-06-27",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["debit_account_id"] == acc["id"]


def test_default_debit_not_applied_to_income(client):
    c, _, _ = client
    acc = c.post(
        "/accounts", json={"name": "A", "bank": "nordea", "type": "checking"},
    ).json()
    c.put("/settings/default_debit_account_id", json={"value": acc["id"]})

    # En income (lön) ska INTE få default-debit-kontot (det är ett bill-fält)
    r = c.post("/upcoming/", json={
        "kind": "income",
        "name": "Arbetsgivare",
        "amount": "25000",
        "expected_date": "2026-06-25",
    })
    assert r.status_code == 200
    assert r.json()["debit_account_id"] is None


# ---------- Backup/restore ----------


def test_backup_create_list_delete(client):
    c, _, tmp_path = client

    # Inga backuper från början
    r = c.get("/backup/list")
    assert r.status_code == 200
    assert r.json()["backups"] == []

    # Skapa en
    r = c.post("/backup/create", json={"label": "januari-2026"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filename"].startswith("januari-2026_")
    assert body["filename"].endswith(".db")
    assert body["size_bytes"] > 0

    # Listan har den nya
    r = c.get("/backup/list")
    backups = r.json()["backups"]
    assert len(backups) == 1
    assert backups[0]["label"].startswith("januari-2026")

    # Radera
    r = c.delete(f"/backup/{body['filename']}")
    assert r.status_code == 200

    r = c.get("/backup/list")
    assert r.json()["backups"] == []


def test_backup_sanitizes_filename(client):
    c, _, _ = client
    # Försök med farligt label
    r = c.post("/backup/create", json={"label": "../../etc/passwd"})
    assert r.status_code == 200
    filename = r.json()["filename"]
    # Inga slashes, inga punkter i början
    assert "/" not in filename
    assert not filename.startswith(".")


def test_delete_backup_rejects_path_traversal(client):
    c, _, _ = client
    r = c.delete("/backup/..%2Fetc%2Fpasswd")
    # FastAPI normaliserar inte %2F automatiskt i path-params, men
    # vår validering avvisar det
    assert r.status_code in (404, 400)
