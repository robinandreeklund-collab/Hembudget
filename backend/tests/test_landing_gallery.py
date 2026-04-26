"""Tester för landningssidans gallery — publik läsning + super-admin
upload av skärmdumpar."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.landing_seed import seed_landing_assets
from hembudget.school.models import LandingAsset, Teacher
from hembudget.security.crypto import hash_password, random_token


def _tiny_png() -> bytes:
    """En ~70-byte transparent 1x1 PNG — tillräckligt för upload-testen."""
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAY"
        "AAjCB0C8AAAAASUVORK5CYII="
    )


@pytest.fixture
def fx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
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
        seed_landing_assets(s)
        super_t = Teacher(
            email="root@x.se", name="Root",
            password_hash=hash_password("Abcdef12!"),
            is_super_admin=True,
        )
        normal_t = Teacher(
            email="t@x.se", name="T",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add_all([super_t, normal_t]); s.flush()
        super_id = super_t.id
        normal_id = normal_t.id

    super_tok = random_token()
    register_token(super_tok, role="teacher", teacher_id=super_id)
    normal_tok = random_token()
    register_token(normal_tok, role="teacher", teacher_id=normal_id)

    return TestClient(app), super_tok, normal_tok


def test_public_gallery_lists_seeded_slots(fx) -> None:
    client, _, _ = fx
    r = client.get("/landing/gallery")
    assert r.status_code == 200
    rows = r.json()
    # Sex slots seedas
    assert len(rows) == 6
    slots = {r["slot"] for r in rows}
    assert slots == {
        "dashboard", "modules", "mastery",
        "portfolio", "ai", "time-on-task",
    }
    # Inga bilder ännu
    assert all(not r["has_image"] for r in rows)
    assert all(r["image_url"] is None for r in rows)


def test_super_admin_can_upload_image(fx) -> None:
    client, super_tok, _ = fx

    # Hämta första slot:en
    rows = client.get("/landing/gallery").json()
    asset_id = rows[0]["id"]

    r = client.put(
        f"/admin/landing/gallery/{asset_id}",
        data={
            "title": "Ny titel",
            "body": "Ny beskrivning",
            "chip": "X",
            "chip_color": "fordj",
            "sort_order": "5",
        },
        files={"image": ("shot.png", _tiny_png(), "image/png")},
        headers={"Authorization": f"Bearer {super_tok}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Ny titel"
    assert body["has_image"] is True
    assert body["image_url"] == f"/landing/gallery/{asset_id}/image"

    # Bilden serveras publikt
    r = client.get(f"/landing/gallery/{asset_id}/image")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content == _tiny_png()


def test_normal_teacher_cannot_upload(fx) -> None:
    client, _, normal_tok = fx
    rows = client.get("/landing/gallery").json()
    asset_id = rows[0]["id"]
    r = client.put(
        f"/admin/landing/gallery/{asset_id}",
        data={"title": "x"},
        headers={"Authorization": f"Bearer {normal_tok}"},
    )
    assert r.status_code == 403


def test_image_size_limit(fx) -> None:
    client, super_tok, _ = fx
    rows = client.get("/landing/gallery").json()
    asset_id = rows[0]["id"]
    big = b"\x00" * (5 * 1024 * 1024 + 1)  # 5 MB + 1 byte
    r = client.put(
        f"/admin/landing/gallery/{asset_id}",
        data={"title": "x"},
        files={"image": ("big.png", big, "image/png")},
        headers={"Authorization": f"Bearer {super_tok}"},
    )
    assert r.status_code == 413


def test_image_mime_validation(fx) -> None:
    client, super_tok, _ = fx
    rows = client.get("/landing/gallery").json()
    asset_id = rows[0]["id"]
    r = client.put(
        f"/admin/landing/gallery/{asset_id}",
        data={"title": "x"},
        files={"image": ("evil.exe", b"MZ\x00\x00", "application/octet-stream")},
        headers={"Authorization": f"Bearer {super_tok}"},
    )
    assert r.status_code == 415


def test_super_admin_can_clear_image(fx) -> None:
    client, super_tok, _ = fx
    rows = client.get("/landing/gallery").json()
    asset_id = rows[0]["id"]

    # Ladda upp först
    client.put(
        f"/admin/landing/gallery/{asset_id}",
        data={"title": "x"},
        files={"image": ("shot.png", _tiny_png(), "image/png")},
        headers={"Authorization": f"Bearer {super_tok}"},
    )

    # Rensa
    r = client.delete(
        f"/admin/landing/gallery/{asset_id}/image",
        headers={"Authorization": f"Bearer {super_tok}"},
    )
    assert r.status_code == 200

    # Nu serveras inte bilden längre
    r = client.get(f"/landing/gallery/{asset_id}/image")
    assert r.status_code == 404

    # Slot:en finns kvar i listan, men har_image=False
    rows = client.get("/landing/gallery").json()
    me = next(r for r in rows if r["id"] == asset_id)
    assert me["has_image"] is False


def test_seed_is_idempotent(fx) -> None:
    """Att köra seed:en två gånger skapar inte dubletter."""
    client, _, _ = fx
    rows1 = client.get("/landing/gallery").json()
    with master_session() as s:
        n = seed_landing_assets(s)
        assert n == 0  # alla slots fanns redan
    rows2 = client.get("/landing/gallery").json()
    assert len(rows1) == len(rows2) == 6


def test_variant_default_is_default(fx) -> None:
    """Innan någon super-admin toggar ska /landing/variant returnera
    'default' så frontend renderar den klassiska paper-sidan."""
    client, _, _ = fx
    r = client.get("/landing/variant")
    assert r.status_code == 200
    assert r.json() == {"variant": "default"}


def test_super_admin_can_toggle_variant(fx) -> None:
    client, super_tok, _ = fx
    # Sätt till c
    r = client.put(
        "/admin/landing/variant",
        json={"variant": "c"},
        headers={"Authorization": f"Bearer {super_tok}"},
    )
    assert r.status_code == 200
    assert r.json()["variant"] == "c"
    # Publik endpoint speglar
    assert client.get("/landing/variant").json()["variant"] == "c"
    # Toggla tillbaka
    r = client.put(
        "/admin/landing/variant",
        json={"variant": "default"},
        headers={"Authorization": f"Bearer {super_tok}"},
    )
    assert r.json()["variant"] == "default"
    assert client.get("/landing/variant").json()["variant"] == "default"


def test_invalid_variant_rejected(fx) -> None:
    client, super_tok, _ = fx
    r = client.put(
        "/admin/landing/variant",
        json={"variant": "evil"},
        headers={"Authorization": f"Bearer {super_tok}"},
    )
    assert r.status_code == 400


def test_normal_teacher_cannot_toggle_variant(fx) -> None:
    client, _, normal_tok = fx
    r = client.put(
        "/admin/landing/variant",
        json={"variant": "c"},
        headers={"Authorization": f"Bearer {normal_tok}"},
    )
    assert r.status_code == 403
