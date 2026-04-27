"""API-router för bank-flödet (idé 3 i dev_v1.md).

PR 5b täcker BankID-simulering:
- POST /bank/set-pin               — eleven sätter sin 4-siffriga PIN
- POST /bank/session/init          — starta ny session (skapa token)
- POST /bank/session/{token}/confirm — mobilen bekräftar med PIN
- GET  /bank/session/{token}       — desktop pollar status
- GET  /bank/me                    — kollar om eleven har PIN satt

Desktop-flöde:
1. Eleven trycker 'Logga in' på /bank
2. Frontend POST /bank/session/init → får token + qr-data
3. Mobil-vyn (på samma URL med ?token=) ber eleven mata PIN
4. Mobilen POST /bank/session/{token}/confirm {pin}
5. Desktop pollar /bank/session/{token} tills confirmed_at är satt

Server side bygger ingen ny token-kontext — bank-tokenen är
kopplad till elevens existerande session via student_id. Det vi
gör är att markera att eleven har gjort en BankID-bekräftelse
nyligen (15 min) och bank-vyn på frontend tillåts visas.
"""
from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..school import is_enabled as school_enabled
from ..school.bank_models import BankSession
from ..school.engines import master_session
from ..school.models import BatchArtifact, ScenarioBatch, Student
from ..security.crypto import hash_password, verify_password
from .deps import TokenInfo, require_token

log = logging.getLogger(__name__)

router = APIRouter(prefix="/bank", tags=["bank"])


SESSION_TTL_MINUTES = 15
PIN_PATTERN = re.compile(r"^\d{4}$")


def _require_school() -> None:
    if not school_enabled():
        raise HTTPException(404, "School mode inaktivt")


def _student_from_info(info: TokenInfo) -> int:
    if info.role == "student" and info.student_id:
        return info.student_id
    if info.role == "teacher" and info.student_id:
        # Lärar-impersonering — middleware har satt student_id
        return info.student_id
    raise HTTPException(
        400, "Ingen elev-context — eleven måste vara inloggad",
    )


# ---------- Schemas ----------

class SetPinIn(BaseModel):
    pin: str = Field(min_length=4, max_length=4)


class InitSessionIn(BaseModel):
    purpose: str = Field(default="login", min_length=1, max_length=80)


class InitSessionOut(BaseModel):
    token: str
    qr_url: str  # Den URL som mobilen ska öppna (eller skannas som QR)
    expires_at: str
    purpose: str


class ConfirmIn(BaseModel):
    pin: str = Field(min_length=4, max_length=4)


class SessionStatusOut(BaseModel):
    token: str
    purpose: str
    confirmed: bool
    expired: bool
    confirmed_at: Optional[str] = None


class BankMeOut(BaseModel):
    has_pin: bool
    student_id: int


# ---------- Endpoints ----------

@router.get("/me", response_model=BankMeOut)
def bank_me(info: TokenInfo = Depends(require_token)) -> BankMeOut:
    """Visar om eleven satt sin bank-PIN."""
    _require_school()
    student_id = _student_from_info(info)
    with master_session() as s:
        st = s.get(Student, student_id)
        if not st:
            raise HTTPException(404, "Eleven finns inte")
        return BankMeOut(
            has_pin=bool(st.bank_pin_hash),
            student_id=student_id,
        )


@router.post("/set-pin")
def set_pin(
    payload: SetPinIn,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Eleven sätter sin 4-siffriga bank-PIN.

    Idempotent: kan ändras av eleven själv senare. Lärare kan
    nollställa via /teacher/employer/{id}/reset-bank-pin
    (PR 5b — lärar-endpoint kommer i samma commit).
    """
    _require_school()
    student_id = _student_from_info(info)
    if not PIN_PATTERN.match(payload.pin):
        raise HTTPException(400, "PIN måste vara exakt 4 siffror")
    with master_session() as s:
        st = s.get(Student, student_id)
        if not st:
            raise HTTPException(404, "Eleven finns inte")
        st.bank_pin_hash = hash_password(payload.pin)
        s.flush()
        return {"ok": True}


@router.post("/session/init", response_model=InitSessionOut)
def init_session(
    payload: InitSessionIn,
    request: Request,
    info: TokenInfo = Depends(require_token),
) -> InitSessionOut:
    """Skapa ny BankSession. Returnerar token + QR-URL.

    QR-URL är en länk eleven kan öppna på mobilen för att
    bekräfta. I praktiken pekar den på frontend-sidan
    /bank/sign?token=... som visar PIN-formuläret.
    """
    _require_school()
    student_id = _student_from_info(info)
    with master_session() as s:
        st = s.get(Student, student_id)
        if not st:
            raise HTTPException(404, "Eleven finns inte")
        if not st.bank_pin_hash:
            raise HTTPException(
                400,
                "PIN saknas — sätt din bank-PIN först (POST /bank/set-pin)",
            )
        token = secrets.token_urlsafe(24)
        expires = datetime.utcnow() + timedelta(
            minutes=SESSION_TTL_MINUTES,
        )
        client_ip = (
            request.client.host if request.client else None
        )
        s.add(BankSession(
            student_id=student_id,
            token=token,
            purpose=payload.purpose or "login",
            expires_at=expires,
            ip_address=client_ip,
        ))
        s.flush()

        # qr_url byggs som relativ URL — frontend lägger till origin
        qr_url = f"/bank/sign?token={token}"
        return InitSessionOut(
            token=token,
            qr_url=qr_url,
            expires_at=expires.isoformat(),
            purpose=payload.purpose or "login",
        )


@router.post(
    "/session/{token}/confirm",
)
def confirm_session(
    token: str,
    payload: ConfirmIn,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Mobilen bekräftar sessionen genom att mata in PIN.

    PIN matchas mot Student.bank_pin_hash. Sessionens student_id
    måste matcha den inloggade eleven (annars kan vem som helst
    bekräfta vem som helst).
    """
    _require_school()
    student_id = _student_from_info(info)
    with master_session() as s:
        sess = (
            s.query(BankSession)
            .filter(BankSession.token == token)
            .first()
        )
        if not sess:
            raise HTTPException(404, "Sessionen finns inte")
        if sess.student_id != student_id:
            raise HTTPException(403, "Sessionen tillhör annan elev")
        if sess.expires_at < datetime.utcnow():
            raise HTTPException(410, "Sessionen har löpt ut")
        if sess.confirmed_at is not None:
            return {"ok": True, "already_confirmed": True}
        st = s.get(Student, student_id)
        if not st or not st.bank_pin_hash:
            raise HTTPException(400, "PIN saknas")
        if not verify_password(st.bank_pin_hash, payload.pin):
            raise HTTPException(401, "Fel PIN")
        sess.confirmed_at = datetime.utcnow()
        s.flush()
        return {"ok": True}


class BankArtifactOut(BaseModel):
    artifact_id: int
    batch_id: int
    year_month: str
    kind: str  # "kontoutdrag" | "kreditkort_faktura" | "lan_besked"
    title: str
    filename: str
    exported_to_my_batches: bool
    exported_at: Optional[str] = None
    imported_at: Optional[str] = None


# Bank-artefakter = bank-relaterade BatchArtifact-kinds som hör hemma
# i banken (inte /arbetsgivare). Lönespec exkluderas medvetet.
BANK_ARTIFACT_KINDS = {"kontoutdrag", "kreditkort_faktura", "lan_besked"}


@router.get("/statements", response_model=list[BankArtifactOut])
def list_bank_artifacts(
    info: TokenInfo = Depends(require_token),
) -> list[BankArtifactOut]:
    """Lista bank-relaterade dokument från elevens batches.

    Returnerar kontoutdrag, kreditkortsfakturor och lånebesked
    (alla 'pappersdokument från banken'). Lönespec hör inte
    hit — den ligger på /arbetsgivare.

    Senaste batch först. Visar status: redan exporterad till
    /my-batches eller ej, redan importerad eller ej.
    """
    _require_school()
    student_id = _student_from_info(info)
    with master_session() as s:
        rows = (
            s.query(BatchArtifact, ScenarioBatch)
            .join(ScenarioBatch, ScenarioBatch.id == BatchArtifact.batch_id)
            .filter(
                ScenarioBatch.student_id == student_id,
                BatchArtifact.kind.in_(BANK_ARTIFACT_KINDS),
            )
            .order_by(
                ScenarioBatch.year_month.desc(),
                BatchArtifact.sort_order.asc(),
            )
            .all()
        )
        return [
            BankArtifactOut(
                artifact_id=art.id,
                batch_id=batch.id,
                year_month=batch.year_month,
                kind=art.kind,
                title=art.title,
                filename=art.filename,
                exported_to_my_batches=bool(art.exported_to_my_batches),
                exported_at=(
                    art.exported_at.isoformat()
                    if art.exported_at else None
                ),
                imported_at=(
                    art.imported_at.isoformat()
                    if art.imported_at else None
                ),
            )
            for (art, batch) in rows
        ]


@router.post(
    "/statements/{batch_id}/{artifact_id}/export",
)
def export_to_my_batches(
    batch_id: int,
    artifact_id: int,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Exportera ett bank-dokument till /my-batches.

    Pedagogiskt motiv: i verkligheten laddar du ner en PDF från
    banken och importerar sedan i bokföringen — det är två
    separata system. Här simulerar vi det genom att eleven
    aktivt måste 'flytta' dokumentet till sin dokumentmapp.

    Idempotent: redan-exporterade artefakter får ingen ny tidsstämpel.
    """
    _require_school()
    student_id = _student_from_info(info)
    with master_session() as s:
        # Validera ägarskap via batch
        batch = s.get(ScenarioBatch, batch_id)
        if not batch or batch.student_id != student_id:
            raise HTTPException(404, "Batch finns inte")
        art = s.get(BatchArtifact, artifact_id)
        if not art or art.batch_id != batch_id:
            raise HTTPException(404, "Dokumentet finns inte")
        if art.kind not in BANK_ARTIFACT_KINDS:
            raise HTTPException(
                400,
                f"Dokumentet ({art.kind}) hör inte till banken",
            )
        if art.exported_to_my_batches:
            return {"ok": True, "already_exported": True}
        art.exported_to_my_batches = True
        art.exported_at = datetime.utcnow()
        s.flush()
        return {"ok": True}


@router.get("/session/{token}", response_model=SessionStatusOut)
def session_status(
    token: str,
    info: TokenInfo = Depends(require_token),
) -> SessionStatusOut:
    """Polla session-status.

    Eleven kan polla sin egen session; läraren får 403 om hen
    inte impersonerar samma elev.
    """
    _require_school()
    student_id = _student_from_info(info)
    with master_session() as s:
        sess = (
            s.query(BankSession)
            .filter(BankSession.token == token)
            .first()
        )
        if not sess:
            raise HTTPException(404, "Sessionen finns inte")
        if sess.student_id != student_id:
            raise HTTPException(403, "Sessionen tillhör annan elev")
        expired = sess.expires_at < datetime.utcnow()
        return SessionStatusOut(
            token=token,
            purpose=sess.purpose,
            confirmed=sess.confirmed_at is not None,
            expired=expired,
            confirmed_at=(
                sess.confirmed_at.isoformat() if sess.confirmed_at else None
            ),
        )
