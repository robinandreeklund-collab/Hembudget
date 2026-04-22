"""Backup och restore av SQLite-databasen.

En backup är en fullständig snapshot av databas-filen. Filer läggs
under `data_dir/backups/` med valbart namn + timestamp. Användare kan:
- Skapa backup ("Spara januari")
- Lista backuper med datum + storlek
- Återställa från backup (rullar tillbaka till den snapshotens data)
- Radera en backup

Implementation: SQLite `VACUUM INTO` används när databasen är aktiv — det
är officiella sättet att ta en konsistent kopia utan att låsa DB:n. Om
VACUUM INTO inte är tillgängligt (vissa sqlcipher-byggen) faller vi
tillbaka på att stänga connections och kopiera filen.
"""
from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..db import base as db_base
from .deps import db, require_auth

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/backup", tags=["backup"], dependencies=[Depends(require_auth)],
)


def _backup_dir() -> Path:
    p = settings.data_dir / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_\-]")


def _safe_label(label: str | None) -> str:
    if not label:
        return "snapshot"
    cleaned = _SAFE_NAME_RE.sub("_", label.strip())
    return cleaned[:64] or "snapshot"


class BackupCreate(BaseModel):
    label: Optional[str] = None


class BackupRestore(BaseModel):
    filename: str


@router.get("/list")
def list_backups() -> dict:
    """Lista alla backup-filer med storlek och datum."""
    out = []
    for p in sorted(_backup_dir().glob("*.db"), reverse=True):
        stat = p.stat()
        out.append({
            "filename": p.name,
            "label": p.stem,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return {"backups": out, "directory": str(_backup_dir())}


@router.post("/create")
def create_backup(
    payload: BackupCreate, session: Session = Depends(db),
) -> dict:
    """Skapa en ny backup av aktuell databas.

    Namn (t.ex. 'januari-2026') + timestamp bildar filnamnet så att två
    backuper med samma namn inte skriver över varandra."""
    label = _safe_label(payload.label)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    filename = f"{label}_{ts}.db"
    dest = _backup_dir() / filename

    # Försök VACUUM INTO — officiell SQLite-metod för live-backup
    try:
        session.execute(text(f"VACUUM INTO :p"), {"p": str(dest)})
        session.commit()
    except Exception as exc:
        # Fallback: vänta kort, stäng anslutningar, kopiera filen.
        log.warning("VACUUM INTO misslyckades, fallback till filkopiering: %s", exc)
        try:
            src = settings.db_path
            if not src.exists():
                raise HTTPException(500, "DB-filen hittades inte på disk")
            db_base.get_engine().dispose()
            shutil.copy2(src, dest)
        except Exception as exc2:
            raise HTTPException(500, f"Backup misslyckades: {exc2}") from exc2

    stat = dest.stat()
    return {
        "filename": dest.name,
        "label": dest.stem,
        "size_bytes": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


@router.post("/restore")
def restore_backup(payload: BackupRestore) -> dict:
    """Återställ databasen från en sparad backup.

    VIKTIGT: Alla data som tillkommit sedan backupen togs GÅR FÖRLORADE.
    Anrop krossar pågående transaktioner genom att stänga engine, skriver
    över databasfilen och initialiserar motorn igen.
    """
    # Validera filnamn
    if "/" in payload.filename or "\\" in payload.filename or payload.filename.startswith("."):
        raise HTTPException(400, "Ogiltigt filnamn")
    src = _backup_dir() / payload.filename
    if not src.exists() or not src.is_file() or src.suffix != ".db":
        raise HTTPException(404, "Backup-filen hittades inte")

    dest = settings.db_path
    # Spara en "före-restore"-kopia så användaren kan ångra
    pre_restore = _backup_dir() / f"pre_restore_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.db"
    try:
        db_base.get_engine().dispose()
        if dest.exists():
            shutil.copy2(dest, pre_restore)
        shutil.copy2(src, dest)
        # Tvinga ny engine så att cached key inte används mot ny fil
        db_base._engine = None  # type: ignore[attr-defined]
        db_base._SessionLocal = None  # type: ignore[attr-defined]
    except Exception as exc:
        raise HTTPException(500, f"Restore misslyckades: {exc}") from exc

    return {
        "restored_from": payload.filename,
        "pre_restore_backup": pre_restore.name,
    }


@router.delete("/{filename}")
def delete_backup(filename: str) -> dict:
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(400, "Ogiltigt filnamn")
    p = _backup_dir() / filename
    if not p.exists() or p.suffix != ".db":
        raise HTTPException(404, "Backup-filen hittades inte")
    p.unlink()
    return {"deleted": filename}
