"""Landningssidans gallery — publik läs + super-admin uppladdning.

Sex skärmdumps-slots för "Vyerna"-sektionen på landningssidan.
- Publik: GET /landing/gallery (lista slots) + GET /landing/gallery/{id}/image
  (serverar bytes). Ingen auth — landningssidan visas av oinloggade besökare.
- Super-admin:
    PUT /admin/landing/gallery/{id}             (multipart med metadata + valfri bild)
    DELETE /admin/landing/gallery/{id}/image    (rensa bilden, behåll slot)

Bilderna lagras som blob i master-DB:n så de följer med backupen.
Max 5 MB per bild — räcker mer än väl för en PNG/JPEG-skärmdump.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status,
)
from pydantic import BaseModel

from ..school import is_enabled as school_enabled
from ..school.engines import master_session
from ..school.models import LandingAsset, Teacher
from .deps import TokenInfo, require_teacher

log = logging.getLogger(__name__)

router = APIRouter(tags=["landing"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_MIMES = {
    "image/png", "image/jpeg", "image/webp", "image/gif",
}


def _require_super_admin(
    info: TokenInfo = Depends(require_teacher),
) -> TokenInfo:
    if not school_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "School mode inaktivt")
    with master_session() as s:
        t = s.get(Teacher, info.teacher_id)
        if not t or not t.is_super_admin:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Super-admin krävs",
            )
    return info


# ---------- Schemas ----------

class LandingAssetOut(BaseModel):
    id: int
    slot: str
    title: str
    body: str
    chip: str
    chip_color: str
    sort_order: int
    has_image: bool
    image_url: Optional[str]


def _to_out(a: LandingAsset) -> LandingAssetOut:
    return LandingAssetOut(
        id=a.id,
        slot=a.slot,
        title=a.title,
        body=a.body,
        chip=a.chip,
        chip_color=a.chip_color,
        sort_order=a.sort_order,
        has_image=a.image_blob is not None,
        image_url=(
            f"/landing/gallery/{a.id}/image"
            if a.image_blob is not None else None
        ),
    )


# ---------- Publik läs (visas på landningssidan) ----------

@router.get("/landing/gallery", response_model=list[LandingAssetOut])
def list_landing_gallery() -> list[LandingAssetOut]:
    """Lista alla gallery-slots i sort_order. Returnerar tom lista om
    school-läget inte är aktiverat — landningssidan faller då tillbaka
    på sina inbyggda placeholder-kort."""
    if not school_enabled():
        return []
    with master_session() as s:
        rows = (
            s.query(LandingAsset)
            .order_by(LandingAsset.sort_order, LandingAsset.id)
            .all()
        )
        return [_to_out(a) for a in rows]


@router.get("/landing/gallery/{asset_id}/image")
def get_landing_image(asset_id: int) -> Response:
    """Servera den uppladdade bilden för en slot."""
    if not school_enabled():
        raise HTTPException(404, "Not found")
    with master_session() as s:
        a = s.get(LandingAsset, asset_id)
        if not a or not a.image_blob:
            raise HTTPException(404, "Bild finns ej")
        return Response(
            content=bytes(a.image_blob),
            media_type=a.image_mime or "application/octet-stream",
            headers={
                # Cacha en timme — admin kan ändå PUT:a en ny bild som
                # busts:as via updated_at (frontend bygger url med ?v=).
                "Cache-Control": "public, max-age=3600",
            },
        )


# ---------- Super-admin: redigera + ladda upp ----------

@router.get(
    "/admin/landing/gallery",
    response_model=list[LandingAssetOut],
)
def admin_list_gallery(
    _: TokenInfo = Depends(_require_super_admin),
) -> list[LandingAssetOut]:
    """Samma data som publik endpoint — separat så super-admin alltid
    får aktuella värden även när det publika svaret cachats av en
    proxy."""
    with master_session() as s:
        rows = (
            s.query(LandingAsset)
            .order_by(LandingAsset.sort_order, LandingAsset.id)
            .all()
        )
        return [_to_out(a) for a in rows]


@router.put(
    "/admin/landing/gallery/{asset_id}",
    response_model=LandingAssetOut,
)
async def admin_update_asset(
    asset_id: int,
    title: str = Form(...),
    body: str = Form(""),
    chip: str = Form(""),
    chip_color: str = Form("grund"),
    sort_order: int = Form(0),
    image: Optional[UploadFile] = File(default=None),
    _: TokenInfo = Depends(_require_super_admin),
) -> LandingAssetOut:
    """Uppdatera metadata och (frivilligt) ersätt bilden. Skicka bara
    title-fältet om du vill behålla nuvarande bild."""
    with master_session() as s:
        a = s.get(LandingAsset, asset_id)
        if not a:
            raise HTTPException(404, "Slot finns ej")
        a.title = title.strip()[:120] or a.title
        a.body = body
        a.chip = chip.strip()[:8]
        a.chip_color = (chip_color or "grund").strip()[:20]
        a.sort_order = int(sort_order)

        if image is not None:
            data = await image.read()
            if len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(
                    413,
                    f"Bilden är för stor "
                    f"(max {MAX_IMAGE_BYTES // 1024 // 1024} MB)",
                )
            mime = (image.content_type or "").lower()
            if mime not in ALLOWED_MIMES:
                raise HTTPException(
                    415,
                    f"Otillåten filtyp ({mime}). "
                    f"Tillåtna: {', '.join(sorted(ALLOWED_MIMES))}",
                )
            if not data:
                raise HTTPException(400, "Tom fil")
            a.image_blob = data
            a.image_mime = mime
        s.flush()
        return _to_out(a)


@router.delete("/admin/landing/gallery/{asset_id}/image")
def admin_clear_image(
    asset_id: int,
    _: TokenInfo = Depends(_require_super_admin),
) -> dict:
    """Rensa bilden för en slot (behåll metadata). Landningssidan
    faller tillbaka på placeholder-kortet."""
    with master_session() as s:
        a = s.get(LandingAsset, asset_id)
        if not a:
            raise HTTPException(404, "Slot finns ej")
        a.image_blob = None
        a.image_mime = None
        return {"ok": True}
