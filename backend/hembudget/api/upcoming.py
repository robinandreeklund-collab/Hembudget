from __future__ import annotations

import base64
import io
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func as _sa_func
from sqlalchemy.orm import Session


def func_lower(col):
    return _sa_func.lower(col)

from ..categorize.engine import CategorizationEngine
from ..config import settings
from ..db.models import (
    Account,
    Category,
    Import,
    Transaction,
    UpcomingTransaction,
    UpcomingTransactionLine,
    User,
)
from ..llm.client import LMStudioClient, LLMUnavailable
from ..splits import build_lines_from_vision, resolve_category_id
from ..transfers.detector import TransferDetector
from ..upcoming_match.materializer import UpcomingMaterializer
from .deps import db, llm_client, require_auth

log = logging.getLogger(__name__)

router = APIRouter(prefix="/upcoming", tags=["upcoming"], dependencies=[Depends(require_auth)])

PDF_MAGIC = b"%PDF"
MAX_PDF_PAGES = 3           # vision-kontexter är dyrt — håll oss till 3
IMAGE_MAX_DIM = 1024        # max bredd/höjd i px innan vi skickar
IMAGE_JPEG_QUALITY = 75     # bra balans text-läsbarhet/token-storlek


def _downscale_to_jpeg(
    pil_image, max_dim: int = IMAGE_MAX_DIM, quality: int = IMAGE_JPEG_QUALITY
) -> bytes:
    """Ta en PIL-bild, skala ner och JPEG-komprimera så vi håller token-antalet
    nere. Svenska bankfakturor är textdrag-tunga — 1024 px räcker för vision
    att läsa alla siffror."""
    from PIL import Image

    w, h = pil_image.size
    if max(w, h) > max_dim:
        ratio = max_dim / max(w, h)
        pil_image = pil_image.resize(
            (max(1, int(w * ratio)), max(1, int(h * ratio))),
            Image.LANCZOS,
        )
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")
    buf = io.BytesIO()
    pil_image.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _rasterize_pdf(pdf_bytes: bytes, max_pages: int = MAX_PDF_PAGES) -> list[bytes]:
    """Renderar PDF-sidor till komprimerade JPEG-bilder."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise HTTPException(
            500,
            "pypdfium2 saknas — kör 'pip install -e .[dev]' i backend/",
        ) from exc

    images: list[bytes] = []
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        if len(pdf) == 0:
            raise HTTPException(400, "PDF:en innehåller inga sidor")
        for i in range(min(len(pdf), max_pages)):
            page = pdf[i]
            try:
                # scale=1.5 + nedskalning till 1024 px = små, men läsbara JPEG
                bitmap = page.render(scale=1.5)
                try:
                    pil_image = bitmap.to_pil()
                    try:
                        images.append(_downscale_to_jpeg(pil_image))
                    finally:
                        pil_image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
    finally:
        pdf.close()
    return images


def _vision_error_hint(exc: Exception) -> str:
    """Formaterar ett tydligt felmeddelande när vision-anrop misslyckas."""
    msg = str(exc)
    low = msg.lower()
    if "context" in low and ("exceeds" in low or "tokens" in low):
        return (
            "Bildens storlek överskrider LM Studios kontextfönster. "
            "Ladda om modellen i LM Studio med minst 16k context length "
            "(i 'Model' → 'Load configuration' → 'Context length'). "
            f"Detaljer: {msg}"
        )
    if "not support" in low or "image" in low and "unknown" in low:
        return (
            "Den aktiva modellen i LM Studio verkar inte stödja bilder. "
            "Byt till en vision-kapabel modell (Qwen2.5-VL, Pixtral, Llava). "
            f"Detaljer: {msg}"
        )
    return f"Vision-anropet misslyckades: {msg}"


def _shrink_raw_image(content: bytes) -> bytes:
    """Nedskala & JPEG-komprimera en uppladdad bild för vision-call."""
    from PIL import Image

    pil_image = Image.open(io.BytesIO(content))
    try:
        return _downscale_to_jpeg(pil_image)
    finally:
        pil_image.close()


def _file_to_images(content: bytes, content_type: str | None) -> tuple[list[bytes], str]:
    """Returnera (lista med JPEG-bytes, mime-type).
    PDF → rasteriseras per sida; bilder → nedskalade & komprimerade."""
    if content.startswith(PDF_MAGIC) or (content_type or "").lower() == "application/pdf":
        return _rasterize_pdf(content), "image/jpeg"
    try:
        return [_shrink_raw_image(content)], "image/jpeg"
    except Exception:
        # Om det är nåt annat format vi inte kan öppna, skicka originalet
        return [content], content_type or "image/png"


class UpcomingLineIn(BaseModel):
    description: str
    amount: Decimal
    category_id: Optional[int] = None
    sort_order: int = 0


class UpcomingLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    description: str
    amount: Decimal
    category_id: Optional[int]
    sort_order: int


class UpcomingIn(BaseModel):
    kind: str  # "bill" | "income"
    name: str
    amount: Decimal
    expected_date: date
    owner: Optional[str] = None
    category_id: Optional[int] = None
    recurring_monthly: bool = False
    notes: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    ocr_reference: Optional[str] = None
    bankgiro: Optional[str] = None
    plusgiro: Optional[str] = None
    iban: Optional[str] = None
    debit_account_id: Optional[int] = None
    debit_date: Optional[date] = None
    autogiro: bool = False
    lines: list[UpcomingLineIn] = []


class UpcomingUpdate(BaseModel):
    kind: Optional[str] = None
    name: Optional[str] = None
    amount: Optional[Decimal] = None
    expected_date: Optional[date] = None
    owner: Optional[str] = None
    category_id: Optional[int] = None
    recurring_monthly: Optional[bool] = None
    notes: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    ocr_reference: Optional[str] = None
    bankgiro: Optional[str] = None
    plusgiro: Optional[str] = None
    iban: Optional[str] = None
    debit_account_id: Optional[int] = None
    debit_date: Optional[date] = None
    autogiro: Optional[bool] = None


class UpcomingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    name: str
    amount: Decimal
    expected_date: date
    owner: Optional[str]
    category_id: Optional[int]
    recurring_monthly: bool
    source: str
    source_image_path: Optional[str]
    notes: Optional[str]
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    ocr_reference: Optional[str] = None
    bankgiro: Optional[str] = None
    plusgiro: Optional[str] = None
    iban: Optional[str] = None
    debit_account_id: Optional[int] = None
    debit_date: Optional[date] = None
    autogiro: bool = False
    matched_transaction_id: Optional[int]
    lines: list[UpcomingLineOut] = []
    # Delbetalningar (flera Transactions kan peka mot samma upcoming)
    payment_tx_ids: list[int] = []
    paid_amount: float = 0.0
    payment_status: str = "unpaid"  # unpaid | partial | paid | overpaid
    # När True räknas partial/overpaid som "paid" — användaren har
    # godkänt avvikelsen (öresavrundning, bonus, skattejust.)
    variance_accepted: bool = False


def _enrich_upcoming(
    session: Session, ups: list[UpcomingTransaction],
) -> list[dict]:
    """Bygg UpcomingOut-dicts med paid_amount/status från UpcomingPayment."""
    from ..db.models import UpcomingPayment, Account
    if not ups:
        return []
    ids = [u.id for u in ups]
    # Hämta alla payments + tx-detaljer i en query. Frontend vill se
    # belopp/datum/beskrivning per delbetalning så användaren kan
    # granska matchningar och ångra felaktiga (t.ex. för överbetalda
    # fakturor där någon tx matchats fel).
    pay_rows = (
        session.query(
            UpcomingPayment.upcoming_id,
            Transaction,
        )
        .join(Transaction, Transaction.id == UpcomingPayment.transaction_id)
        .filter(UpcomingPayment.upcoming_id.in_(ids))
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    account_names = {
        a.id: a.name for a in session.query(Account.id, Account.name).all()
    }
    by_up: dict[int, list[tuple[int, Decimal, Transaction]]] = {}
    for up_id, tx in pay_rows:
        by_up.setdefault(up_id, []).append((tx.id, tx.amount, tx))

    TOLERANCE = Decimal("2.00")
    out: list[dict] = []
    for u in ups:
        entries = by_up.get(u.id, [])
        paid = sum((abs(a) for _, a, _ in entries), Decimal("0"))
        if paid == 0:
            status = "unpaid"
        else:
            remaining = u.amount - paid
            if abs(remaining) <= TOLERANCE:
                status = "paid"
            elif remaining > 0:
                status = "partial"
            else:
                status = "overpaid"
        # Användaren kan ha godkänt avvikelsen — då räknas den som paid
        # i alla downstream-vyer (forecast, kommande-listan, huvudbok).
        if status in ("partial", "overpaid") and getattr(u, "variance_accepted", False):
            status = "paid"
        d = {
            "id": u.id, "kind": u.kind, "name": u.name,
            "amount": float(u.amount),
            "expected_date": u.expected_date.isoformat(),
            "owner": u.owner, "category_id": u.category_id,
            "recurring_monthly": u.recurring_monthly,
            "variance_accepted": bool(getattr(u, "variance_accepted", False)),
            "source": u.source, "source_image_path": u.source_image_path,
            "notes": u.notes, "invoice_number": u.invoice_number,
            "invoice_date": u.invoice_date.isoformat() if u.invoice_date else None,
            "ocr_reference": u.ocr_reference, "bankgiro": u.bankgiro,
            "plusgiro": u.plusgiro, "iban": u.iban,
            "debit_account_id": u.debit_account_id,
            "debit_date": u.debit_date.isoformat() if u.debit_date else None,
            "autogiro": u.autogiro,
            "matched_transaction_id": u.matched_transaction_id,
            "lines": [
                {
                    "id": ln.id, "description": ln.description,
                    "amount": float(ln.amount),
                    "category_id": ln.category_id, "sort_order": ln.sort_order,
                }
                for ln in u.lines
            ],
            "payment_tx_ids": [tid for tid, _, _ in entries],
            "payment_transactions": [
                {
                    "id": tid,
                    "date": tx.date.isoformat(),
                    "amount": float(tx.amount),
                    "description": tx.raw_description,
                    "account_id": tx.account_id,
                    "account_name": account_names.get(tx.account_id),
                }
                for tid, _, tx in entries
            ],
            "paid_amount": float(paid),
            "payment_status": status,
        }
        out.append(d)
    return out


@router.get("/")
def list_upcoming(
    kind: Optional[str] = None,
    only_future: bool = True,
    status: Optional[str] = None,
    session: Session = Depends(db),
) -> list[dict]:
    """List upcoming transactions.

    `status` optional: "open" (unpaid + partial — bill ej fullt betald) eller
    "paid" (fullt betald). Default None = alla.

    OBS: vi filtrerar på payment_status (räknat från UpcomingPayment-junction),
    INTE på matched_transaction_id. En delbetald faktura har
    matched_transaction_id satt men ska fortsätta synas i "open" tills hela
    beloppet är betalt.
    """
    q = session.query(UpcomingTransaction)
    if kind:
        q = q.filter(UpcomingTransaction.kind == kind)
    if only_future:
        q = q.filter(UpcomingTransaction.expected_date >= date.today())
    ups = q.order_by(UpcomingTransaction.expected_date.asc()).all()
    enriched = _enrich_upcoming(session, ups)
    if status == "open":
        enriched = [e for e in enriched if e["payment_status"] != "paid"]
    elif status == "paid":
        enriched = [e for e in enriched if e["payment_status"] == "paid"]
    return enriched


def _materialize_on_incognito_account(
    session: Session, upcoming: UpcomingTransaction,
) -> Transaction | None:
    """Om upcomingen är en inkomst med en `owner` som matchar ägaren av
    ett inkognito-konto, skapa automatiskt en riktig Transaction på det
    kontot och bind den mot upcomingen.

    Avsikt: användaren lägger in partnerns lön via /upcoming/ eller
    parse-text, och systemet genererar direkt en 'lönerad' på hennes
    inkognito-konto — så saldot, YTD och family-breakdown speglar
    verkligheten utan att hon måste exportera en CSV.

    Returnerar den skapade Transaction:en, eller None om inget konto
    hittas eller upcomingen redan är matchad."""
    if upcoming.matched_transaction_id is not None:
        return None
    if upcoming.kind != "income":
        return None
    owner = (upcoming.owner or "").strip()
    if not owner:
        return None

    # Hitta inkognito-konto där ägarens User.name matchar owner-strängen
    user_row = (
        session.query(User)
        .filter(func_lower(User.name) == owner.lower())
        .first()
    )
    if user_row is None:
        return None

    incog_acc = (
        session.query(Account)
        .filter(
            Account.owner_id == user_row.id,
            Account.incognito.is_(True),
        )
        .first()
    )
    if incog_acc is None:
        return None

    import hashlib
    from datetime import datetime as _dt
    # Unik hash baserat på konto+datum+belopp+upcoming-ID så dubbelkörning
    # inte skapar dubletter
    key = (
        f"{incog_acc.id}|{upcoming.expected_date.isoformat()}|"
        f"{upcoming.amount}|incog-up-{upcoming.id}"
    )
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()

    tx = Transaction(
        account_id=incog_acc.id,
        date=upcoming.expected_date,
        amount=upcoming.amount,  # positivt för income
        currency="SEK",
        raw_description=upcoming.name or f"Inkomst ({owner})",
        hash=h,
    )
    session.add(tx)
    session.flush()
    upcoming.matched_transaction_id = tx.id
    return tx


@router.post("/", response_model=UpcomingOut)
def create_upcoming(payload: UpcomingIn, session: Session = Depends(db)) -> UpcomingTransaction:
    if payload.kind not in ("bill", "income"):
        raise HTTPException(400, "kind must be 'bill' or 'income'")
    data = payload.model_dump()
    line_dicts = data.pop("lines", []) or []
    u = UpcomingTransaction(**data)
    # Fyll i default-debit-konto om användaren inte angav ett. Sparas i
    # app_settings som 'default_debit_account_id' via /settings-endpoint.
    if u.debit_account_id is None and u.kind == "bill":
        from ..db.models import AppSetting
        s_row = session.get(AppSetting, "default_debit_account_id")
        if s_row and isinstance(s_row.value, dict):
            default_id = s_row.value.get("v")
            if isinstance(default_id, int):
                u.debit_account_id = default_id
    for i, ld in enumerate(line_dicts):
        u.lines.append(UpcomingTransactionLine(
            description=ld["description"],
            amount=Decimal(str(ld["amount"])),
            category_id=ld.get("category_id"),
            sort_order=ld.get("sort_order", i),
        ))
    session.add(u)
    session.flush()
    # Om raden skapas retroaktivt (gammalt datum) så ska den auto-matchas
    # mot en ev. redan befintlig Transaction.
    from ..upcoming_match import UpcomingMatcher as _UM
    _UM(session).backfill_match([u])
    # Inkognito-auto-materialize: partner-lön → skapa Transaction på
    # hennes inkognito-konto så saldo och family-breakdown speglar den.
    if u.matched_transaction_id is None:
        _materialize_on_incognito_account(session, u)
    return u


@router.post("/{upcoming_id}/materialize-to-account")
def materialize_to_account(
    upcoming_id: int, payload: dict, session: Session = Depends(db),
) -> dict:
    """Skapa en riktig Transaction på ett specifikt konto och bind den
    mot en UpcomingTransaction.

    Användarkontroll: användaren klickar 'Koppla till konto' i UI:t på
    en lön-rad, väljer sitt konto (t.ex. Evelinas inkognito), systemet
    skapar en Transaction där och sätter matched_transaction_id.

    Fungerar för både kind=income och kind=bill. Tecknet på Transaction
    följer upcoming:ens kind (income = positivt, bill = negativt).
    """
    import hashlib
    u = session.get(UpcomingTransaction, upcoming_id)
    if u is None:
        raise HTTPException(404, "Upcoming not found")
    if u.matched_transaction_id is not None:
        raise HTTPException(
            409,
            f"Upcomingen är redan matchad mot transaktion "
            f"#{u.matched_transaction_id}. Koppla loss den först om du "
            "vill flytta.",
        )
    account_id = payload.get("account_id")
    if not isinstance(account_id, int):
        raise HTTPException(400, "account_id (int) krävs i body")
    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(404, "Account not found")

    amount = u.amount if u.kind == "income" else -u.amount
    key = (
        f"{acc.id}|{u.expected_date.isoformat()}|{amount}|"
        f"manual-up-{u.id}"
    )
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()

    tx = Transaction(
        account_id=acc.id,
        date=u.expected_date,
        amount=amount,
        currency=acc.currency or "SEK",
        raw_description=u.name or f"Manuell ({u.kind})",
        hash=h,
    )
    session.add(tx)
    session.flush()
    u.matched_transaction_id = tx.id

    # Om upcoming.owner är tomt och kontot har ägare, sätt owner-strängen
    # till User.name så Familje-vyn och prognos-rad visar rätt namn
    # (annars syns "Okänd" i income_by_owner).
    if not (u.owner or "").strip() and acc.owner_id is not None:
        owner_user = session.get(User, acc.owner_id)
        if owner_user is not None:
            u.owner = owner_user.name

    # Kopiera ev. lines till splits
    if u.lines:
        from ..splits import apply_upcoming_lines_to_transaction
        apply_upcoming_lines_to_transaction(session, u, tx)

    # Kör transfer-detektorn så att t.ex. en manuell lön på inkognito-
    # konto som är "Till gemensamt" paras ihop mot motsvarande bankrad.
    TransferDetector(session).detect_internal_transfers()
    session.flush()

    return {
        "upcoming_id": u.id,
        "transaction_id": tx.id,
        "account_id": acc.id,
        "amount": float(amount),
    }


@router.get("/{upcoming_id}/find-bank-tx")
def find_bank_tx_candidates(
    upcoming_id: int,
    amount_tolerance: float = 10.0,
    date_tolerance_days: int = 14,
    session: Session = Depends(db),
) -> dict:
    """Lista befintliga Transactions som kan matcha denna upcoming.

    Bredare sök än backfill_match (±10 kr, ±14 dagar som default) så
    användaren kan hitta en kreditkorts-autogiro-dragning som inte
    matchades automatiskt (t.ex. pga beloppsskillnad öresavrundning,
    eller att användaren bara betalade minimibeloppet, eller fel
    månads-faktura).

    Sorterar efter exakthet (minst amount_diff + minst date_diff).
    Exkluderar tx som redan är bundna till NÅGON upcoming.
    """
    from datetime import timedelta as _td
    u = session.get(UpcomingTransaction, upcoming_id)
    if u is None:
        raise HTTPException(404, "Upcoming not found")

    from ..db.models import UpcomingPayment as _UpPay
    from sqlalchemy import select as _select

    # Räkna ut "remaining" — om upcomingen redan är delbetald söker vi
    # primärt efter kandidater som täcker ÅTERSTOENDE, inte hela beloppet.
    paid = float(session.query(_sa_func.coalesce(
        _sa_func.sum(_sa_func.abs(Transaction.amount)), 0
    )).join(
        _UpPay, _UpPay.transaction_id == Transaction.id,
    ).filter(_UpPay.upcoming_id == u.id).scalar() or 0)
    remaining_abs = float(u.amount) - paid
    # Target = remaining (om redan delbetald) annars hela beloppet
    target_abs = remaining_abs if paid > 0.01 else float(u.amount)
    if u.kind == "income":
        expected_amount = target_abs
    else:
        expected_amount = -target_abs

    target_date = u.debit_date or u.expected_date
    low_date = target_date - _td(days=date_tolerance_days)
    high_date = target_date + _td(days=date_tolerance_days)

    q = session.query(Transaction).filter(
        Transaction.date >= low_date,
        Transaction.date <= high_date,
        Transaction.id.not_in(_select(_UpPay.transaction_id)),
    )
    all_candidates = q.all()

    amt_tol = float(amount_tolerance)
    ranked: list[tuple[float, int, Transaction]] = []
    for tx in all_candidates:
        diff = abs(float(tx.amount) - float(expected_amount))
        if diff > amt_tol:
            continue
        date_diff = abs((tx.date - target_date).days)
        ranked.append((diff, date_diff, tx))
    ranked.sort(key=lambda t: (t[0], t[1]))

    # Bygg response
    accounts = {a.id: a for a in session.query(Account).all()}
    out = []
    for diff, date_diff, tx in ranked[:30]:
        acc = accounts.get(tx.account_id)
        out.append({
            "transaction_id": tx.id,
            "date": tx.date.isoformat(),
            "amount": float(tx.amount),
            "description": tx.raw_description,
            "account_id": tx.account_id,
            "account_name": acc.name if acc else None,
            "is_transfer": tx.is_transfer,
            "amount_diff": round(diff, 2),
            "date_diff_days": date_diff,
            "exact_match": diff <= 1.0 and date_diff <= 3,
        })

    return {
        "upcoming_id": u.id,
        "upcoming_name": u.name,
        "upcoming_amount": float(u.amount),
        "paid_amount": round(paid, 2),
        "remaining_amount": round(remaining_abs, 2),
        "expected_tx_amount": float(expected_amount),
        "target_date": target_date.isoformat(),
        "candidates": out,
    }


@router.patch("/{upcoming_id}", response_model=UpcomingOut)
def update_upcoming(
    upcoming_id: int, payload: UpcomingUpdate, session: Session = Depends(db)
) -> UpcomingTransaction:
    u = session.get(UpcomingTransaction, upcoming_id)
    if u is None:
        raise HTTPException(404, "Upcoming not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(u, k, v)
    session.flush()
    return u


@router.delete("/{upcoming_id}")
def delete_upcoming(upcoming_id: int, session: Session = Depends(db)) -> dict:
    u = session.get(UpcomingTransaction, upcoming_id)
    if u is None:
        raise HTTPException(404, "Upcoming not found")
    session.delete(u)
    return {"deleted": upcoming_id}


@router.post("/{upcoming_id}/accept-variance")
def accept_variance(upcoming_id: int, session: Session = Depends(db)) -> dict:
    """Markera avvikelse i delbetalning (partial/overpaid) som godkänd.

    Användsfall: en lön är "delbetalt 19 122 kr av 19 172 kr" pga
    öresavrundning på arbetsgivarsida, eller "överbetald 6 197 av 6 072"
    pga bonus. Användaren godkänner att avvikelsen är OK och slipper
    fortsatta varningar — status räknas som 'paid' i alla downstream-vyer.
    """
    u = session.get(UpcomingTransaction, upcoming_id)
    if u is None:
        raise HTTPException(404, "Upcoming not found")
    u.variance_accepted = True
    session.flush()
    return {"id": u.id, "variance_accepted": True}


@router.post("/{upcoming_id}/reject-variance")
def reject_variance(upcoming_id: int, session: Session = Depends(db)) -> dict:
    """Ångra ett tidigare 'godkänn avvikelse' så raden visar varning igen."""
    u = session.get(UpcomingTransaction, upcoming_id)
    if u is None:
        raise HTTPException(404, "Upcoming not found")
    u.variance_accepted = False
    session.flush()
    return {"id": u.id, "variance_accepted": False}


@router.post("/materialize")
def materialize_upcoming(
    horizon_days: int = 60,
    session: Session = Depends(db),
) -> dict:
    """Skapa UpcomingTransaction-rader från lånescheman och aktiva
    prenumerationer. Idempotent — kör säkert upprepade gånger."""
    result = UpcomingMaterializer(session, horizon_days=horizon_days).run()
    return {
        "loan_upcoming_created": result.loan_upcoming_created,
        "sub_upcoming_created": result.sub_upcoming_created,
        "skipped_existing": result.skipped_existing,
        "horizon_days": horizon_days,
    }


@router.put("/{upcoming_id}/lines", response_model=list[UpcomingLineOut])
def set_upcoming_lines(
    upcoming_id: int,
    lines: list[UpcomingLineIn],
    session: Session = Depends(db),
) -> list[UpcomingTransactionLine]:
    """Ersätt alla rader på en planerad faktura. Totalsumman på
    UpcomingTransaction.amount justeras INTE automatiskt — användaren kan
    välja att behålla fakturasumman som presenterad av leverantören."""
    u = session.get(UpcomingTransaction, upcoming_id)
    if u is None:
        raise HTTPException(404, "Upcoming not found")
    # Radera befintliga rader och skapa nya
    for existing in list(u.lines):
        session.delete(existing)
    session.flush()
    new_lines: list[UpcomingTransactionLine] = []
    for i, payload in enumerate(lines):
        line = UpcomingTransactionLine(
            upcoming_id=u.id,
            description=payload.description,
            amount=payload.amount,
            category_id=payload.category_id,
            sort_order=payload.sort_order or i,
        )
        session.add(line)
        new_lines.append(line)
    session.flush()
    return new_lines


@router.post("/parse-text", response_model=UpcomingOut)
def parse_text(
    text: str = Form(...),
    kind: str = Form("bill"),
    session: Session = Depends(db),
    llm: LMStudioClient = Depends(llm_client),
) -> UpcomingTransaction:
    """Använd LM Studio för att tolka ett fritextmeddelande till en strukturerad
    kommande transaktion. Exempel: "Vattenfall 1 500 kr förfaller 2026-04-30"."""
    if not llm.is_alive():
        raise HTTPException(503, "LM Studio är inte tillgänglig")

    schema = _invoice_schema()
    schema["properties"]["owner"] = {"type": ["string", "null"]}

    system_text = (
        "Du tolkar svensk text om kommande fakturor eller löner. "
        "Returnera JSON enligt schemat. Om datum saknas, sätt sista "
        "dagen i nästa månad. Fält som inte nämns → null."
    )
    if kind == "income":
        system_text += (
            "\n\nFör inkomster (lön/utbetalning): "
            "- name = arbetsgivaren/utbetalaren (t.ex. 'Inkab', 'VP Capital'). "
            "- owner = personen som tar emot pengarna ('Robin', 'Partner'). "
            "- Om texten är 'Lön Robin 11357 från Inkab 25 april', då är name='Inkab', "
            "owner='Robin'. Om inte personen nämns, owner=null. "
            "- Inkluderar INTE personens namn i name-fältet."
        )
    else:
        system_text += (
            "\n\nFör fakturor: name = betalningsmottagaren (företaget som ska få pengar)."
        )

    try:
        parsed = llm.complete_json(
            [
                {"role": "system", "content": system_text},
                {"role": "user", "content": text},
            ],
            schema=schema,
            temperature=0.0,
        )
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    u = _build_upcoming_from_parsed(parsed, kind=kind, source="ai_text", session=session)
    u.owner = parsed.get("owner")
    session.add(u)
    session.flush()
    from ..upcoming_match import UpcomingMatcher as _UM
    _UM(session).backfill_match([u])
    if u.matched_transaction_id is None:
        _materialize_on_incognito_account(session, u)
    return u


@router.post("/parse-invoice-image", response_model=UpcomingOut)
async def parse_invoice_image(
    file: UploadFile = File(...),
    kind: str = Form("bill"),
    session: Session = Depends(db),
    llm: LMStudioClient = Depends(llm_client),
) -> UpcomingTransaction:
    """Skicka en faktura (PNG/JPG/PDF) till LM Studio för automatisk
    extraktion av mottagare, belopp, förfallodag och fakturarader.

    PDF:er med text-lager (de flesta bankfakturor) parsas text-först —
    ~10× snabbare och ofta mer exakt än vision. PDF:er utan text och
    rena bilder faller tillbaka på vision-modellen.
    """
    if not llm.is_alive():
        raise HTTPException(503, "LM Studio är inte tillgänglig")

    content = await file.read()
    if not content:
        raise HTTPException(400, "Tom fil")

    original_path = _save_invoice_file(content, file.filename)
    try:
        parsed = _llm_parse_invoice(content, file.content_type, llm, session)
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Invoice parse failed")
        raise HTTPException(500, _vision_error_hint(exc)) from exc

    u = _build_upcoming_from_parsed(
        parsed, kind=kind,
        source=parsed.get("_source_method", "vision_ai"),
        source_image_path=str(original_path),
        session=session,
    )
    parsed_lines = parsed.get("lines") or []
    if parsed_lines:
        u.lines.extend(build_lines_from_vision(session, parsed_lines))
    session.add(u)
    session.flush()
    from ..upcoming_match import UpcomingMatcher as _UM
    _UM(session).backfill_match([u])
    return u


@router.post("/parse-salary-pdf", response_model=UpcomingOut)
async def parse_salary_pdf_endpoint(
    file: UploadFile = File(...),
    owner: str | None = Form(None),
    debit_account_id: int | None = Form(None),
    session: Session = Depends(db),
) -> UpcomingTransaction:
    """Parsa en svensk lönespec-PDF (INKAB, Vättaporten, Försäkringskassan)
    och skapa en UpcomingTransaction (kind=income) med fullständig metadata.

    Extraherar brutto, netto, skatt, extra_skatt (VP), semesterdagar,
    tabell och engångsskatt%. PDF:en sparas under data_dir/invoices/
    och länkas via source_image_path. Metadata lagras i notes som JSON
    så frontend kan visa detaljer utan ytterligare API-anrop.

    Om kommande-datum är passerat och kontot är incognito materialiseras
    raden direkt som Transaction (samma logik som övriga income-upcomings).
    """
    from ..parsers.salary_pdfs import parse_salary_pdf
    import json as _json

    content = await file.read()
    if not content:
        raise HTTPException(400, "Tom fil")

    parsed = parse_salary_pdf(content)
    if parsed.detected_format == "unknown":
        raise HTTPException(
            422,
            "Okänt lönespec-format. Stöds: INKAB, Vättaporten AB, "
            "Försäkringskassan (barnbidrag + föräldrapenning). "
            f"Första 200 tecken i PDF:en: {parsed.raw_text[:200]}",
        )
    if parsed.net is None or parsed.paid_out_date is None:
        raise HTTPException(
            422,
            f"Kunde inte extrahera netto-belopp eller utbetalningsdatum från "
            f"{parsed.detected_format}-formatet. Fel: {parsed.parse_errors}",
        )

    # Spara PDF:en för ledger-referens
    original_path = _save_invoice_file(content, file.filename)

    # All strukturerad metadata in i notes som JSON så frontend kan visa
    meta = {
        "detected_format": parsed.detected_format,
        "gross": float(parsed.gross) if parsed.gross is not None else None,
        "tax": float(parsed.tax) if parsed.tax is not None else None,
        "extra_tax": float(parsed.extra_tax) if parsed.extra_tax is not None else None,
        "benefit": float(parsed.benefit) if parsed.benefit is not None else None,
        "net": float(parsed.net),
        "tax_table": parsed.tax_table,
        "one_time_tax_percent": parsed.one_time_tax_percent,
        "vacation_days_paid": parsed.vacation_days_paid,
        "vacation_days_unpaid": parsed.vacation_days_unpaid,
        "vacation_days_saved": parsed.vacation_days_saved,
        "period_start": parsed.period_start.isoformat() if parsed.period_start else None,
        "period_end": parsed.period_end.isoformat() if parsed.period_end else None,
        "employee": parsed.employee,
    }

    u = UpcomingTransaction(
        kind="income",
        name=parsed.employer or "Lön",
        amount=parsed.net,  # "ska läggas på kontot" = netto
        expected_date=parsed.paid_out_date,
        owner=owner,
        debit_account_id=debit_account_id,
        source="salary_pdf",
        source_image_path=str(original_path),
        notes=_json.dumps(meta, ensure_ascii=False),
    )
    session.add(u)
    session.flush()

    # Backfill-match mot befintliga transaktioner + auto-materialize
    # till inkognito-konto om applicable (samma som övriga incomes).
    from ..upcoming_match import UpcomingMatcher as _UM
    _UM(session).backfill_match([u])
    if u.matched_transaction_id is None:
        _materialize_on_incognito_account(session, u)
    return u


@router.post("/{upcoming_id}/attach-salary-pdf", response_model=UpcomingOut)
async def attach_salary_pdf_to_existing(
    upcoming_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(db),
) -> UpcomingTransaction:
    """Koppla en lönespec-PDF till en BEFINTLIG UpcomingTransaction (income).

    Används från /salaries för att bifoga underlag till löner som redan
    finns registrerade — antingen från CSV-import, manuellt tillagda
    eller AI-parse:ade.

    Parsar PDF:en (INKAB / Vättaporten / FK), sparar filen under
    data_dir/invoices/ och länkar via source_image_path. Metadata-
    fälten (gross, tax, extra_tax, etc.) lagras i notes som JSON så
    skatteprognos och se-underlag-länken fungerar direkt.

    Beloppet på den befintliga raden ändras INTE — man ska kunna koppla
    en PDF även om det faktiska beloppet skiljer sig något (t.ex. ören,
    eller om raden representerar flera utbetalningar). Om du vill
    synka beloppet med PDF:en får du redigera raden manuellt.
    """
    from ..parsers.salary_pdfs import parse_salary_pdf
    import json as _json

    u = session.get(UpcomingTransaction, upcoming_id)
    if u is None:
        raise HTTPException(404, "Upcoming not found")
    if u.kind != "income":
        raise HTTPException(
            400,
            "Endpoint:en gäller bara income-rader. Använd "
            "/upcoming/parse-invoice-image för fakturor.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(400, "Tom fil")

    parsed = parse_salary_pdf(content)
    if parsed.detected_format == "unknown":
        raise HTTPException(
            422,
            "Okänt lönespec-format. Stöds: INKAB, Vättaporten AB, "
            "Försäkringskassan.",
        )

    original_path = _save_invoice_file(content, file.filename)
    u.source_image_path = str(original_path)

    # Bevara existerande notes om de inte är JSON (frihandstext från
    # användaren). Annars merge:a in metadata.
    existing_meta: dict = {}
    if u.notes:
        try:
            existing_meta = _json.loads(u.notes)
            if not isinstance(existing_meta, dict):
                existing_meta = {"user_note": u.notes}
        except ValueError:
            existing_meta = {"user_note": u.notes}

    new_meta = {
        **existing_meta,
        "detected_format": parsed.detected_format,
        "gross": float(parsed.gross) if parsed.gross is not None else None,
        "tax": float(parsed.tax) if parsed.tax is not None else None,
        "extra_tax": float(parsed.extra_tax) if parsed.extra_tax is not None else None,
        "benefit": float(parsed.benefit) if parsed.benefit is not None else None,
        "net": float(parsed.net) if parsed.net is not None else None,
        "tax_table": parsed.tax_table,
        "one_time_tax_percent": parsed.one_time_tax_percent,
        "vacation_days_paid": parsed.vacation_days_paid,
        "vacation_days_unpaid": parsed.vacation_days_unpaid,
        "vacation_days_saved": parsed.vacation_days_saved,
        "period_start": parsed.period_start.isoformat() if parsed.period_start else None,
        "period_end": parsed.period_end.isoformat() if parsed.period_end else None,
        "employee": parsed.employee,
        "attached_from_pdf": True,
    }
    u.notes = _json.dumps(new_meta, ensure_ascii=False)
    # Om source var 'manual' eller 'ai_text', uppgradera till salary_pdf
    # så skatteprognos-endpointen inkluderar raden.
    u.source = "salary_pdf"
    session.flush()
    return u


@router.get("/salary-tax-prognosis")
def salary_tax_prognosis(
    year: int | None = None,
    session: Session = Depends(db),
) -> dict:
    """Skatteprognos per person baserat på lönespec-PDF:er.

    Summerar 'Extra skatt' och faktisk skatt per person och år.
    'Extra skatt' är voluntary över tabell-skatten — i teorin får man
    tillbaka det vid deklaration om årsinkomsten landar på rätt tabell.

    Returnerar per-person-buckets med:
    - total_gross, total_tax, total_extra_tax, total_net
    - months_parsed (antal lönespecs hittade i år)
    - projected_full_year_extra_tax (linjär extrapolering)
    - hint-text om återbäring eller kvarskatt
    """
    import json as _json
    from datetime import date as _date

    y = year or _date.today().year
    start = _date(y, 1, 1)
    end = _date(y + 1, 1, 1)

    salary_ups = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "income",
            UpcomingTransaction.source == "salary_pdf",
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
        )
        .all()
    )

    by_owner: dict[str, dict] = {}
    for u in salary_ups:
        owner = (u.owner or "gemensamt").strip() or "gemensamt"
        bucket = by_owner.setdefault(
            owner,
            {
                "total_gross": 0.0,
                "total_tax": 0.0,
                "total_extra_tax": 0.0,
                "total_net": 0.0,
                "months_parsed": 0,
                "payslips": [],
            },
        )
        try:
            meta = _json.loads(u.notes or "{}") if u.notes else {}
        except ValueError:
            meta = {}
        gross = float(meta.get("gross") or 0)
        tax = float(meta.get("tax") or 0)
        extra_tax = float(meta.get("extra_tax") or 0)
        net = float(u.amount)
        bucket["total_gross"] += gross
        bucket["total_tax"] += tax
        bucket["total_extra_tax"] += extra_tax
        bucket["total_net"] += net
        bucket["months_parsed"] += 1
        bucket["payslips"].append({
            "id": u.id,
            "employer": u.name,
            "paid_date": u.expected_date.isoformat(),
            "gross": gross,
            "tax": tax,
            "extra_tax": extra_tax,
            "net": net,
        })

    # Linjär projektion på helår baserat på antal månader parsade
    for bucket in by_owner.values():
        months = bucket["months_parsed"] or 1
        scale = 12.0 / months if months < 12 else 1.0
        bucket["projected_full_year_extra_tax"] = round(
            bucket["total_extra_tax"] * scale, 2,
        )
        # Enkel hint: om extra_tax > 0, troligen återbäring vid deklaration.
        # Detta är en grov skattning — faktisk återbäring beror på total
        # inkomst + avdrag + tabell.
        if bucket["total_extra_tax"] > 0:
            bucket["hint"] = (
                f"Du har betalt {bucket['total_extra_tax']:.0f} kr i 'Extra skatt' "
                f"i år — troligen återbäring vid deklaration om tabellen stämmer "
                f"med din totala inkomst. Projekterat helår: "
                f"{bucket['projected_full_year_extra_tax']:.0f} kr."
            )
        else:
            bucket["hint"] = None

    return {"year": y, "by_owner": by_owner}


@router.post("/bulk-parse-invoices")
async def bulk_parse_invoices(
    files: list[UploadFile] = File(...),
    kind: str = Form("bill"),
    session: Session = Depends(db),
    llm: LMStudioClient = Depends(llm_client),
) -> dict:
    """Ladda upp flera fakturor i ett svep. Varje fil parsas individuellt
    (text-först om PDF har text-lager, vision-fallback annars), en
    UpcomingTransaction skapas per faktura med `lines`, och backfill_match
    körs för alla på en gång så de som redan matchar en bankrad hamnar
    direkt under 'Betalda fakturor'.
    """
    if not files:
        raise HTTPException(400, "Inga filer skickades")
    if not llm.is_alive():
        raise HTTPException(503, "LM Studio är inte tillgänglig")

    results: list[dict] = []
    created: list[UpcomingTransaction] = []

    for f in files:
        content = await f.read()
        if not content:
            results.append({"filename": f.filename, "status": "skipped_empty"})
            continue
        try:
            original_path = _save_invoice_file(content, f.filename)
            parsed = _llm_parse_invoice(content, f.content_type, llm, session)
        except LLMUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except HTTPException as exc:
            results.append({
                "filename": f.filename, "status": "error",
                "error": str(exc.detail),
            })
            continue
        except Exception as exc:
            log.exception("bulk invoice parse failed for %s", f.filename)
            results.append({
                "filename": f.filename, "status": "error",
                "error": str(exc),
            })
            continue

        try:
            u = _build_upcoming_from_parsed(
                parsed, kind=kind,
                source=parsed.get("_source_method", "vision_ai"),
                source_image_path=str(original_path),
                session=session,
            )
            plines = parsed.get("lines") or []
            if plines:
                u.lines.extend(build_lines_from_vision(session, plines))
            session.add(u)
            session.flush()
            created.append(u)
            results.append({
                "filename": f.filename,
                "status": "ok",
                "upcoming_id": u.id,
                "name": u.name,
                "amount": float(u.amount),
                "expected_date": u.expected_date.isoformat(),
                "line_count": len(u.lines),
                "method": parsed.get("_source_method"),
            })
        except Exception as exc:
            log.exception("build upcoming failed for %s", f.filename)
            results.append({
                "filename": f.filename, "status": "error",
                "error": str(exc),
            })

    # Kör backfill_match SAMLAT så alla upcomings testas mot samma tx-pool
    from ..upcoming_match import UpcomingMatcher as _UM
    matched_count = _UM(session).backfill_match(created) if created else 0

    # Komplettera resultatet med match-info
    if matched_count:
        session.flush()
        by_id = {r.get("upcoming_id"): r for r in results if r.get("upcoming_id")}
        for u in created:
            r = by_id.get(u.id)
            if r and u.matched_transaction_id:
                r["matched_transaction_id"] = u.matched_transaction_id

    return {
        "processed": len(files),
        "created": len(created),
        "matched_to_existing": matched_count,
        "results": results,
    }


@router.get("/{upcoming_id}/source")
def get_upcoming_source_file(
    upcoming_id: int, session: Session = Depends(db),
):
    """Returnera originalfakturan (PDF/bild) som denna UpcomingTransaction
    extraherades ifrån. Används av UI:t för ledger-vy ("se fakturan bakom
    denna transaktion")."""
    from fastapi.responses import FileResponse
    u = session.get(UpcomingTransaction, upcoming_id)
    if u is None:
        raise HTTPException(404, "Upcoming not found")
    if not u.source_image_path:
        raise HTTPException(404, "Ingen originalfil sparad för denna rad")
    p = Path(u.source_image_path)
    if not p.exists():
        raise HTTPException(404, "Filen finns inte längre på disk")
    # Gissa mime från filändelse
    ext = p.suffix.lower()
    media = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(ext, "application/octet-stream")
    return FileResponse(p, media_type=media, filename=p.name)


def _save_invoice_file(content: bytes, filename: str | None) -> "Path":
    """Spara en originalfil under data_dir/invoices/ för ledger-referens."""
    invoice_dir = settings.data_dir / "invoices"
    invoice_dir.mkdir(parents=True, exist_ok=True)
    # Unikt filnamn via timestamp + kort hash — skyddar mot kollisioner
    import hashlib as _hashlib
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    short = _hashlib.sha1(content).hexdigest()[:8]
    safe_name = (filename or "invoice").replace("/", "_")
    p = invoice_dir / f"{ts}_{short}_{safe_name}"
    p.write_bytes(content)
    return p


def _llm_parse_invoice(
    content: bytes,
    content_type: str | None,
    llm: LMStudioClient,
    session: Session,
) -> dict:
    """Parsa en faktura till strukturerad JSON.

    Strategi:
    1. Om PDF med text-lager → extrahera text och skicka till LLM (text-mode)
    2. Om PDF utan text eller ren bild → rasterisera & använd vision-modell
    3. Efter LLM-parse: om LLM returnerade <=1 `lines` men PDF-texten
       tydligt listar flera tjänster (el, vatten, bredband etc.) →
       komplettera med deterministisk detektering.

    Returnerar parsed-dict berikad med `_source_method` så anropare kan
    markera UpcomingTransaction.source korrekt ('pdf_text_ai' eller 'vision_ai').
    """
    from ..parsers.invoice_lines import enrich_parsed_with_detected_lines

    category_names = [c.name for c in session.query(Category).all()]
    schema = _invoice_schema(category_names)
    sys_prompt = _vision_system_prompt(category_names)

    # Extrahera PDF-text — används både av text-mode-LLM och av detektorn
    pdf_text = ""
    is_pdf = content.startswith(PDF_MAGIC) or (content_type or "").lower() == "application/pdf"
    if is_pdf:
        try:
            from ..parsers.pdf_statements import extract_pdf_text_layout
            pdf_text = extract_pdf_text_layout(content)
        except Exception:
            pdf_text = ""

    # 1) Text-mode för PDF med text-lager
    if is_pdf and pdf_text and len(pdf_text.strip()) >= 200:
        user_msg = (
            "Här är texten som extraherats från en svensk faktura-PDF. "
            "Extrahera strukturerad betalningsdata enligt schemat. "
            "Om fakturan innehåller flera poster från olika områden "
            "(t.ex. el + vatten + bredband), fyll i 'lines' med en rad "
            "per post och hitta passande kategori. Annars lämna lines "
            "tom. Returnera ENDAST giltig JSON.\n\n"
            "--- PDF-TEXT ---\n"
            f"{pdf_text[:12000]}"
        )
        parsed = llm.complete_json(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            schema=schema,
            temperature=0.0,
        )
        parsed["_source_method"] = "pdf_text_ai"
        # Komplettera lines om LLM missade dem
        enrich_parsed_with_detected_lines(parsed, pdf_text)
        return parsed

    # 2) Vision-fallback
    try:
        images, img_mime = _file_to_images(content, content_type)
    except Exception as exc:
        raise HTTPException(400, f"Kunde inte läsa filen: {exc}") from exc

    user_content: list[dict] = [
        {
            "type": "text",
            "text": (
                "Extrahera ALLA betalningsrelaterade uppgifter från denna "
                "svenska faktura. Om flera sidor, slå samman info. Saknas "
                "fält, använd null. Om fakturan innehåller flera poster "
                "(t.ex. el + vatten + bredband) fyll i 'lines'."
            ),
        }
    ]
    for img_bytes in images:
        b64 = base64.b64encode(img_bytes).decode("ascii")
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{img_mime};base64,{b64}"},
        })

    parsed = llm.complete_json(
        [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content},
        ],
        schema=schema,
        temperature=0.0,
    )
    parsed["_source_method"] = "vision_ai"
    # Vision kan också missa lines — om vi har pdf_text (vilket vi kan ha
    # om PDF:en har text-lager men var för kort för LLM-text-mode) så kör
    # vi även detektorn på det.
    if pdf_text:
        enrich_parsed_with_detected_lines(parsed, pdf_text)
    return parsed


def _invoice_schema(category_names: list[str] | None = None) -> dict:
    """JSON-schema som tvingar vision-modellen att returnera rika data.

    Om `category_names` skickas in begränsas line-items category-fältet till
    dessa namn (pluss null) vilket kraftigt minskar risken för att modellen
    hittar på nya kategorier. Om None accepteras valfri sträng eller null.
    """
    if category_names:
        # JSON-schema med enum + null — matchar existerande kategorier exakt.
        line_cat_schema = {
            "type": ["string", "null"],
            "enum": [*category_names, None],
            "description": (
                "Kategori för denna rad. Använd EXAKT ett av de listade "
                "kategorinamnen, eller null om inget passar."
            ),
        }
    else:
        line_cat_schema = {
            "type": ["string", "null"],
            "description": "Kategori för denna rad (svenskt namn) eller null.",
        }

    return {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Mottagare/betalningsmottagare"},
            "amount": {"type": "number", "description": "Totalbelopp att betala i kr"},
            "expected_date": {"type": "string", "description": "Förfallodatum YYYY-MM-DD"},
            "debit_date": {"type": ["string", "null"],
                           "description": "Betalningsdag — när pengarna dras från kontot, YYYY-MM-DD"},
            "invoice_date": {"type": ["string", "null"], "description": "Fakturadatum"},
            "invoice_number": {"type": ["string", "null"]},
            "ocr_reference": {"type": ["string", "null"],
                              "description": "OCR/referensnummer/meddelande till betalningen"},
            "bankgiro": {"type": ["string", "null"],
                         "description": "Bankgiro/mottagarkonto, t.ex. 123-4567"},
            "plusgiro": {"type": ["string", "null"], "description": "PG-nummer"},
            "iban": {"type": ["string", "null"]},
            "from_account": {"type": ["string", "null"],
                             "description": "Avsändarkontonummer ('Från konto'), t.ex. '1709 20 72840'"},
            "payment_type": {"type": ["string", "null"],
                             "description": "Betalningstyp: Bankgiro, Plusgiro, Swish, IBAN"},
            "payment_status": {"type": ["string", "null"],
                               "description": "Signerad, Betald, Väntande"},
            "autogiro": {"type": "boolean",
                         "description": "true om fakturan anger autogiro / e-faktura-autobetalning"},
            "notes": {"type": ["string", "null"],
                      "description": "Övrig kort info (t.ex. period, meddelande)"},
            "lines": {
                "type": "array",
                "description": (
                    "Fakturarader — ENDAST om fakturan uttryckligen listar olika "
                    "poster som var och en kan höra till olika kategorier. "
                    "Exempel: en faktura från ett energibolag som innehåller "
                    "el, vatten OCH bredband. En vanlig faktura med bara en "
                    "produkt behöver INGA lines (lämna tom array). "
                    "Summan av lines.amount ska matcha amount."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": (
                                "Kort beskrivning av raden, t.ex. 'Elnät', "
                                "'Elförbrukning', 'Vatten och avlopp', "
                                "'Bredband 100/100 Mbit'."
                            ),
                        },
                        "amount": {
                            "type": "number",
                            "description": "Positivt belopp i kr för just denna rad.",
                        },
                        "category": line_cat_schema,
                    },
                    "required": ["description", "amount"],
                },
            },
        },
        "required": ["name", "amount", "expected_date"],
    }


def _vision_system_prompt(category_names: list[str] | None = None) -> str:
    base = (
        "Du läser svenska fakturor och betalningsbekräftelser och extraherar "
        "strukturerad data. Returnera JSON enligt det givna schemat. Viktigt:\n"
        "- Belopp = totalbeloppet att betala i SEK (inget 'kr', komma → punkt).\n"
        "- expected_date är förfallodatum/betalningsdag YYYY-MM-DD.\n"
        "- debit_date är 'Betalningsdag' på Nordeas bekräftelser (när pengarna "
        "dras från kontot). Om ingen skiljelse, samma som expected_date.\n"
        "- from_account är 'Från konto' — avsändarens kontonummer, t.ex. "
        "'1709 20 72840'. Håll blanksteg som i källan.\n"
        "- bankgiro = 'Till konto' om betalningstyp är Bankgiro, t.ex. '104-4882'.\n"
        "- plusgiro = 'Till konto' om betalningstyp är Plusgiro.\n"
        "- ocr_reference = Meddelande eller Referens-fältet.\n"
        "- autogiro=true bara om dokumentet uttryckligen anger autogiro.\n"
        "- Om ett fält inte syns, returnera null.\n\n"
        "FAKTURARADER (lines):\n"
        "- Titta efter en specifikation där fakturan listar FLERA poster som "
        "  hör till olika hushållsområden. Klassiska exempel:\n"
        "    * Hjo Energi: el (elnät + elförbrukning + energiskatt), "
        "      vatten & avlopp, bredband → 3 olika budgetkategorier.\n"
        "    * Kommunfakturor med VA + renhållning + sotning.\n"
        "    * Bostadsrättsavgift + garage + förråd på samma avi.\n"
        "- En faktura med bara ETT ämne (t.ex. rent Spotify, en enda hyra) "
        "  ska ha lines = [] (tom array). Hitta ALDRIG på rader.\n"
        "- Om fakturan har rader, ska sum(lines.amount) = amount (exakt eller "
        "  ±1 kr). Moms/avgifter fördelas proportionellt eller tas med "
        "  enskild rad.\n"
    )
    if category_names:
        base += (
            "- category-fältet i varje rad MÅSTE vara exakt en av dessa "
            "kategorier (eller null om du är osäker): "
            f"{', '.join(category_names)}\n"
        )
    return base


def _normalize_account_number(num: str | None) -> str | None:
    """Strippa blanksteg och bindestreck för matchning."""
    if not num:
        return None
    return "".join(c for c in num if c.isdigit())


def _resolve_debit_account(session: Session, from_account: str | None) -> int | None:
    """Slå upp användarens Account via account_number-fältet (normaliserat)."""
    if not from_account:
        return None
    target = _normalize_account_number(from_account)
    if not target:
        return None
    for acc in session.query(Account).filter(Account.account_number.is_not(None)).all():
        if _normalize_account_number(acc.account_number) == target:
            return acc.id
    return None


def _default_debit_account_id(session: Session) -> int | None:
    """Hämta användarens inställda default-debit-konto (app_settings)."""
    from ..db.models import AppSetting
    row = session.get(AppSetting, "default_debit_account_id")
    if row and isinstance(row.value, dict):
        v = row.value.get("v")
        if isinstance(v, int):
            return v
    return None


def _build_upcoming_from_parsed(
    parsed: dict,
    *,
    kind: str,
    source: str,
    source_image_path: str | None = None,
    session: Session | None = None,
) -> UpcomingTransaction:
    def _parse_date_opt(s: str | None) -> date | None:
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except (ValueError, TypeError):
            return None

    debit_date = _parse_date_opt(parsed.get("debit_date"))
    expected = date.fromisoformat(parsed["expected_date"])
    # Om betalningsbekräftelse har Betalningsdag men ingen förfallodag,
    # använd betalningsdagen som förfallodag också
    if debit_date is None:
        debit_date = expected

    debit_account_id: int | None = None
    if session is not None:
        debit_account_id = _resolve_debit_account(session, parsed.get("from_account"))
        # Fallback till användarens default om fakturan inte uttryckligen
        # angav ett avsändarkonto
        if debit_account_id is None and kind == "bill":
            debit_account_id = _default_debit_account_id(session)

    # Bygg ihop notes med extra fält som inte har egen kolumn
    extra_notes = []
    if parsed.get("notes"):
        extra_notes.append(str(parsed["notes"]))
    if parsed.get("payment_type"):
        extra_notes.append(f"Typ: {parsed['payment_type']}")
    if parsed.get("payment_status"):
        extra_notes.append(f"Status: {parsed['payment_status']}")
    notes = " | ".join(extra_notes) if extra_notes else None

    return UpcomingTransaction(
        kind=kind,
        name=parsed["name"],
        amount=Decimal(str(parsed["amount"])),
        expected_date=expected,
        debit_date=debit_date,
        debit_account_id=debit_account_id,
        invoice_number=parsed.get("invoice_number"),
        invoice_date=_parse_date_opt(parsed.get("invoice_date")),
        ocr_reference=parsed.get("ocr_reference"),
        bankgiro=parsed.get("bankgiro"),
        plusgiro=parsed.get("plusgiro"),
        iban=parsed.get("iban"),
        autogiro=bool(parsed.get("autogiro", False)),
        notes=notes,
        source=source,
        source_image_path=source_image_path,
    )


@router.get("/forecast")
def monthly_forecast(
    month: Optional[str] = None,
    split_ratio: float = 0.5,
    session: Session = Depends(db),
) -> dict:
    """Månadsbalans: kommande lön – kommande fakturor – genomsnittliga
    fasta utgifter = disponibelt. Dela 50/50 (eller valfritt ratio)."""
    if month is None:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    year, mon = map(int, month.split("-"))

    # Lönecykel-baserad budgetering: om användaren satt
    # salary_cycle_start_day till t.ex. 25 så räknar vi en "budget-
    # månad" från 25:e till 25:e nästa månad. Fakturor med expected_date
    # 1-24 maj tillhör april-budget (täcks av april-lönen som kommer 25
    # april). Default cycle_day=1 = kalendermånad (gammalt beteende).
    from ..db.models import AppSetting as _AppSetting
    cycle_row = session.get(_AppSetting, "salary_cycle_start_day")
    cycle_day = 1
    if cycle_row and isinstance(cycle_row.value, dict):
        v = cycle_row.value.get("v")
        if isinstance(v, int) and 1 <= v <= 28:
            cycle_day = v

    if cycle_day == 1:
        start = date(year, mon, 1)
        end = (date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1))
    else:
        start = date(year, mon, cycle_day)
        end = (
            date(year + 1, 1, cycle_day)
            if mon == 12
            else date(year, mon + 1, cycle_day)
        )

    # Endast "ännu inte fullt betalda" rader räknas — fullt betalda finns
    # redan i transaktionshistoriken och ska inte dubbelräknas.
    # Delbetalda räknas med sitt ÅTERSTÅENDE belopp (amount - paid_amount).
    # Tidigare filtrerades på matched_transaction_id.is_(None) vilket inte
    # funkar: den sätts redan vid första delbetalningen, så en 27 000 kr
    # faktura med 2 000 kr inbetalt försvann helt ur forecasten.
    # Vi exkluderar också auto:loan_schedule-materialiserade bills eftersom
    # loan_scheduled_total nedan räknar lånebetalningar direkt från
    # LoanScheduleEntry.
    from ..upcoming_match.payments import (
        FULL_PAID_TOLERANCE as _PAID_TOL,
        paid_amount as _paid_amount,
    )

    bill_candidates = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "bill",
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
            UpcomingTransaction.source != "auto:loan_schedule",
        )
        .all()
    )
    income_candidates = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "income",
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
        )
        .all()
    )

    def _remaining(u: UpcomingTransaction) -> Decimal:
        # Användaren kan ha godkänt avvikelse på partial/overpaid →
        # räknas som fullt betald i prognosen.
        if getattr(u, "variance_accepted", False):
            return Decimal("0")
        paid = _paid_amount(session, u)
        remaining = u.amount - paid
        # Inom tolerans = fullt betald → 0
        if abs(remaining) <= _PAID_TOL:
            return Decimal("0")
        # Negativt (overpaid) → 0 (kan inte "kvarstå" mer än betalt)
        return remaining if remaining > 0 else Decimal("0")

    bills = [b for b in bill_candidates if _remaining(b) > 0]
    incomes = [i for i in income_candidates if _remaining(i) > 0]
    bills_total = sum((_remaining(b) for b in bills), Decimal("0"))
    income_total = sum((_remaining(i) for i in incomes), Decimal("0"))

    # "Övriga utgifter" = snitt av senaste 3 månadernas utgifter, MINUS
    # de transaktioner som redan matchats mot en UpcomingTransaction (de
    # representerar kända återkommande fakturor som räknas separat via
    # upcoming_bills för kommande månad — annars dubbelräknar vi dem).
    from sqlalchemy import func as sql_func

    # Räkna ut lookback-fönstret korrekt över årsgräns
    lookback_month = mon - 3
    lookback_year = year
    if lookback_month <= 0:
        lookback_month += 12
        lookback_year -= 1
    lookback_start = date(lookback_year, lookback_month, 1)

    # "Övriga utgifter" = genomsnitt av VARIABLA utgifter senaste 3 mån.
    # Exkluderar från snittet:
    # 1. Transfers (is_transfer=True) — är ej riktig utgift
    # 2. Inkognito-kontons utgifter (redan via Account-filter nedan)
    # 3. Transaktioner matchade mot en UpcomingTransaction (junction) —
    #    dessa fångas av upcoming_bills för kommande månad
    # 4. Lånebetalningar (LoanPayment) — fångas av låneschemat
    # 5. Transaktioner markerade som kreditkorts-betalning (kategori
    #    "Avgifter & Ränta" eller liknande — krediten täcks via fakturan)
    from ..db.models import (
        LoanPayment as _LoanPayment, UpcomingPayment as _UpPay,
        Account as _Acc,
    )
    # Subqueries för exkluderade tx-ID
    payment_tx_ids_subq = session.query(_UpPay.transaction_id).subquery()
    # Legacy: också matched_transaction_id (för data som inte migrerats
    # till junction-tabellen ännu, t.ex. testscenarios)
    legacy_matched_subq = (
        session.query(UpcomingTransaction.matched_transaction_id)
        .filter(UpcomingTransaction.matched_transaction_id.is_not(None))
        .subquery()
    )
    loan_tx_ids_subq = session.query(_LoanPayment.transaction_id).subquery()

    monthly_exp = (
        session.query(
            sql_func.strftime("%Y-%m", Transaction.date).label("m"),
            sql_func.sum(Transaction.amount).label("tot"),
        )
        .join(_Acc, _Acc.id == Transaction.account_id)
        .filter(
            Transaction.amount < 0,
            Transaction.is_transfer.is_(False),
            _Acc.incognito.is_(False),
            Transaction.date >= lookback_start,
            Transaction.date < start,
            Transaction.id.not_in(payment_tx_ids_subq.select()),
            Transaction.id.not_in(legacy_matched_subq.select()),
            Transaction.id.not_in(loan_tx_ids_subq.select()),
        )
        .group_by("m")
        .all()
    )

    if monthly_exp:
        avg_expenses = abs(sum(float(t) for _, t in monthly_exp)) / len(monthly_exp)
    else:
        avg_expenses = 0.0

    # Lånebetalningar för månaden från schemat (räntor + amorteringar)
    from ..db.models import LoanScheduleEntry
    loan_scheduled_total = float(
        session.query(sql_func.coalesce(sql_func.sum(LoanScheduleEntry.amount), 0))
        .filter(
            LoanScheduleEntry.due_date >= start,
            LoanScheduleEntry.due_date < end,
            LoanScheduleEntry.matched_transaction_id.is_(None),
        )
        .scalar() or 0
    )

    # Två siffror:
    # 1. "Kvar efter kända fakturor" = lön - upcoming_bills - loan_schedule
    #    (vad som blir över om ingenting variabelt spenderas alls)
    # 2. "Kvar att dela" = ovanstående - avg_expenses (prognos för månaden)
    after_known = float(income_total) - float(bills_total) - loan_scheduled_total
    available = after_known - avg_expenses

    # Inkomst per person — försök härleda namn i denna ordning:
    # 1. upcoming.owner-strängen (om satt)
    # 2. Om matched_transaction_id finns → slå upp Account.owner_id → User.name
    # 3. Om upcoming.name innehåller en User.name som substring → använd det
    #    (t.ex. "Evelinas Lön" → Evelina, "Lön Robin" → Robin)
    # 4. "Okänd"
    from ..db.models import User as _User
    users_all = session.query(_User).all()
    user_name_by_id = {u.id: u.name for u in users_all}

    owners: dict[str, Decimal] = {}
    for i in incomes:
        owner_name = (i.owner or "").strip()
        if not owner_name and i.matched_transaction_id is not None:
            tx = session.get(Transaction, i.matched_transaction_id)
            if tx is not None:
                acc = session.get(Account, tx.account_id)
                if acc is not None and acc.owner_id is not None:
                    owner_name = user_name_by_id.get(acc.owner_id, "")
        if not owner_name:
            # Fallback: scanna upcoming-namnet efter en känd User.name
            name_low = (i.name or "").lower()
            for u in users_all:
                if u.name and u.name.lower() in name_low:
                    owner_name = u.name
                    break
        key = owner_name or "Okänd"
        owners[key] = owners.get(key, Decimal("0")) + i.amount

    return {
        "month": month,
        "salary_cycle_start_day": cycle_day,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "upcoming_incomes": [
            {
                "id": i.id, "name": i.name, "amount": float(i.amount),
                "expected_date": i.expected_date.isoformat(),
                "owner": i.owner,
            } for i in incomes
        ],
        "upcoming_bills": [
            {
                "id": b.id, "name": b.name, "amount": float(b.amount),
                "expected_date": b.expected_date.isoformat(),
                "category_id": b.category_id,
            } for b in bills
        ],
        "totals": {
            "expected_income": float(income_total),
            "upcoming_bills": float(bills_total),
            "loan_scheduled": round(loan_scheduled_total, 2),
            "avg_fixed_expenses": round(avg_expenses, 2),
            "after_known_bills": round(after_known, 2),
            "available_to_split": round(available, 2),
        },
        "split": {
            "ratio": split_ratio,
            "per_person_share": round(available * split_ratio, 2),
            "per_person_other": round(available * (1 - split_ratio), 2),
        },
        "income_by_owner": {k: float(v) for k, v in owners.items()},
    }


# ========== Kreditkortsfaktura — läs in hela fakturan på en gång ==========

def _cc_invoice_schema() -> dict:
    """Schema för en komplett kreditkortsfaktura: sammanfattning + alla köp."""
    return {
        "type": "object",
        "properties": {
            "card_issuer": {
                "type": ["string", "null"],
                "description": (
                    "Vilken bank/kreditgivare: 'amex' för American Express, "
                    "'seb_kort' för SEB Kort Mastercard, 'seb' för SEB, 'nordea' för Nordea."
                ),
            },
            "card_name": {
                "type": ["string", "null"],
                "description": "Kortets visningsnamn, t.ex. 'Eurobonus Amex Gold' eller 'SEB Mastercard'",
            },
            "card_last_digits": {
                "type": ["string", "null"],
                "description": "Sista 4 siffrorna på kortnumret om synligt",
            },
            "statement_period_start": {"type": ["string", "null"]},
            "statement_period_end": {"type": ["string", "null"]},
            "opening_balance": {
                "type": ["number", "null"],
                "description": (
                    "Ingående saldo / skuld vid periodens början "
                    "(POSITIV = skuld på kortet). "
                    "Visas ofta som 'Ingående saldo', 'Saldo föregående period' "
                    "eller liknande."
                ),
            },
            "closing_balance": {
                "type": ["number", "null"],
                "description": (
                    "Utgående saldo vid periodens slut — samma som 'Att betala' "
                    "på SEB/Amex-fakturor. POSITIV = skuld."
                ),
            },
            "total_amount": {
                "type": "number",
                "description": "Totalt belopp att betala",
            },
            "due_date": {
                "type": "string",
                "description": "Förfallodag, YYYY-MM-DD",
            },
            "bankgiro": {"type": ["string", "null"]},
            "ocr_reference": {"type": ["string", "null"]},
            "autogiro": {"type": "boolean"},
            "transactions": {
                "type": "array",
                "description": "ALLA enskilda köp och återbetalningar som syns i fakturan",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "YYYY-MM-DD"},
                        "amount": {
                            "type": "number",
                            "description": (
                                "Belopp i kr. Köp = NEGATIVT. Återbetalning/bonus = positivt."
                            ),
                        },
                        "merchant": {"type": "string"},
                        "city": {"type": ["string", "null"]},
                        "foreign_amount": {
                            "type": ["string", "null"],
                            "description": "Valuta+belopp om utlandsköp, t.ex. 'USD 42.00'",
                        },
                    },
                    "required": ["date", "amount", "merchant"],
                },
            },
        },
        "required": ["total_amount", "due_date", "transactions"],
    }


def _cc_invoice_system_prompt() -> str:
    return (
        "Du läser svenska kreditkortsfakturor (American Express Eurobonus, "
        "SEB Kort Mastercard, etc.) och extraherar BÅDE fakturasammanfattningen "
        "OCH alla enskilda transaktioner.\n\n"
        "Viktigt:\n"
        "- card_issuer: 'amex' för Amex, 'seb_kort' för SEB Kort/Mastercard.\n"
        "- total_amount = totalt att betala i SEK (komma → punkt, inget 'kr').\n"
        "- due_date = förfallodag (YYYY-MM-DD).\n"
        "- opening_balance = 'Ingående saldo' / 'Saldo föregående period' / "
        "  'Utestående skuld' vid periodens början. POSITIV = skuld på kortet. "
        "  Null om det inte syns.\n"
        "- closing_balance = 'Utgående saldo' / 'Saldo denna period' / "
        "  'Att betala'. På de flesta fakturor är det samma som total_amount.\n"
        "- statement_period_start / end: periodens datum (YYYY-MM-DD).\n"
        "- transactions: returnera ALLA rader som syns, även om det är många.\n"
        "  - KÖP = NEGATIVT belopp (money leaves pocket).\n"
        "  - ÅTERBETALNINGAR / BONUS = POSITIVT belopp.\n"
        "  - date = transaktionsdatum (inte bokföringsdatum om båda syns).\n"
        "  - merchant = kortet innehåller oftast 'HANDLARE STAD' — splitta "
        "    så merchant = handlarnamnet och city = orten.\n"
        "  - foreign_amount: om utlandsköp med valuta, t.ex. 'USD 42.00'.\n"
        "- autogiro=true om fakturan indikerar autogiro.\n"
        "- Om ett fält inte syns, returnera null."
    )


def _resolve_or_create_cc_account(
    session: Session, issuer: str | None, card_name: str | None,
) -> Account:
    """Hitta befintligt kreditkortskonto, eller skapa ett nytt."""
    issuer_map = {
        "amex": "amex",
        "american express": "amex",
        "seb_kort": "seb_kort",
        "seb kort": "seb_kort",
        "mastercard": "seb_kort",
    }
    bank_key = None
    if issuer:
        bank_key = issuer_map.get(issuer.strip().lower())

    if bank_key:
        existing = (
            session.query(Account)
            .filter(Account.bank == bank_key, Account.type == "credit")
            .first()
        )
        if existing:
            return existing

    # Skapa nytt credit-konto
    new = Account(
        name=card_name or (issuer or "Kreditkort"),
        bank=bank_key or "other",
        type="credit",
    )
    session.add(new)
    session.flush()
    return new


@router.post("/parse-credit-card-pdf")
async def parse_credit_card_pdf(
    file: UploadFile = File(...),
    force: Optional[str] = None,
    session: Session = Depends(db),
) -> dict:
    """Deterministisk PDF-parser för kända kortutgivare (Amex, SEB Kort).
    Använder regex-baserad extraktion direkt från PDF-textlager — ingen
    LLM/vision krävs.

    `force` kan vara 'amex' eller 'seb_kort' för att tvinga en parser när
    auto-detekteringen missar. Om `force` saknas och auto-detekteringen
    inte matchar returnerar vi 415 med extraherad text i svaret så
    frontend kan visa en felsöknings-diagnostik."""
    import hashlib
    from ..parsers.pdf_statements.detect import (
        UnknownStatementFormat,
        parse_statement,
    )

    content = await file.read()
    if not content:
        raise HTTPException(400, "Tom fil")
    if not content.startswith(b"%PDF"):
        raise HTTPException(
            400,
            "Endast PDF-filer stöds av PDF-parsern. Använd vision-"
            "flödet för bilder.",
        )

    try:
        parsed = parse_statement(content, force=force)
    except UnknownStatementFormat as exc:
        # Logga första bita av textet så användaren ser vad pypdfium2
        # extraherade (mycket hjälpsamt för felsökning)
        snippet = exc.extracted_text[:800] if exc.extracted_text else ""
        log.warning(
            "PDF-detektion misslyckades. Första 800 tecken:\n%s", snippet,
        )
        # Returnera 415 med textprov i body så frontend kan visa det
        raise HTTPException(
            415,
            detail={
                "message": (
                    "Kunde inte detektera utgivaren från PDF-texten. "
                    "Skicka med ?force=amex eller ?force=seb_kort för att "
                    "tvinga en parser, eller använd vision-flödet."
                ),
                "extracted_text_sample": snippet,
                "text_length": len(exc.extracted_text or ""),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from exc
    except Exception as exc:
        log.exception("pdf parse failed")
        raise HTTPException(400, f"Kunde inte läsa PDF: {exc}") from exc

    # Spara originalet för audit
    invoice_dir = settings.data_dir / "cc_invoices"
    invoice_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    original_path = invoice_dir / f"{ts}_{file.filename or 'cc.pdf'}"
    original_path.write_bytes(content)

    # Hitta eller skapa kortkonto
    cc_account = _resolve_or_create_cc_account(
        session,
        issuer=parsed.issuer,
        card_name=parsed.card_name,
    )

    # Sätt ingående saldo om det saknas.
    # "Föregående faktura"-beloppet = skuld vid periodens start.
    # Credit-konto konvention: skuld = NEGATIVT saldo (pengar du
    # är skyldig banken).
    if cc_account.opening_balance is None and parsed.opening_balance is not None:
        cc_account.opening_balance = -abs(parsed.opening_balance)
        if parsed.statement_period_start:
            cc_account.opening_balance_date = parsed.statement_period_start

    # Sätt bankgiro på kortkontot — används av transfer-matchern för att
    # para autogiro-dragningar från lönekontot ("Betalning BG 5127-5477")
    # med rätt kortkonto automatiskt.
    if cc_account.bankgiro is None and parsed.bankgiro:
        cc_account.bankgiro = parsed.bankgiro

    session.flush()

    # Audit-post
    imp = Import(
        filename=file.filename or "cc.pdf",
        bank=cc_account.bank,
        sha256=hashlib.sha256(content).hexdigest(),
        row_count=len(parsed.transactions),
    )
    session.add(imp)
    session.flush()

    # ALLA transaktioner hamnar på parent-kortkontot. cardholder-fältet
    # på Transaction används som fördelnings-etikett (inte ett separat
    # konto) så rapporter kan visa "Robin köpte X, Evelina köpte Y".
    # Parent är det enda riktiga kontot — fakturan betalas från BG till
    # parent, inte till varje kortinnehavare individuellt.

    # Dubblettskydd: hash som inkluderar cardholder så två identiska
    # belopp på samma dag med olika holders inte räknas som duplikat.
    existing_hashes = {
        h for (h,) in session.query(Transaction.hash)
        .filter(Transaction.account_id == cc_account.id).all()
    }

    new_txs: list[Transaction] = []
    skipped = 0
    for idx, line in enumerate(parsed.transactions):
        desc = (
            f"{line.merchant} [{line.city}]"
            if line.merchant and line.city
            else line.merchant or line.description
        )
        holder_key = (line.cardholder or "").strip().lower()
        key = (
            f"{cc_account.id}|{line.date.isoformat()}|{line.amount}|"
            f"{desc.strip().lower()}|{holder_key}|#{idx}"
        )
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if h in existing_hashes:
            skipped += 1
            continue
        existing_hashes.add(h)

        tx = Transaction(
            account_id=cc_account.id,
            date=line.date,
            amount=line.amount,
            currency="SEK",
            raw_description=desc,
            source_file_id=imp.id,
            hash=h,
            cardholder=line.cardholder,
        )
        session.add(tx)
        new_txs.append(tx)

    session.flush()

    # Kategorisering + transfers + loans + upcoming-match — samma flöde
    # som CSV-import använder.
    if new_txs:
        engine = CategorizationEngine(session, llm=None)
        results = engine.categorize_batch(new_txs)
        engine.apply_results(new_txs, results)
        session.flush()

    detector = TransferDetector(session)
    transfer_result = detector.detect_and_link(new_txs)
    internal = detector.detect_internal_transfers()
    session.flush()

    # UpcomingTransaction för hela fakturan
    payer = (
        session.query(Account)
        .filter(Account.pays_credit_account_id == cc_account.id)
        .first()
    )
    card_label = parsed.card_name or cc_account.name
    notes_parts = []
    if parsed.statement_period_start and parsed.statement_period_end:
        notes_parts.append(
            f"Period: {parsed.statement_period_start.isoformat()} – "
            f"{parsed.statement_period_end.isoformat()}"
        )
    if parsed.card_last_digits:
        notes_parts.append(f"Kort ****{parsed.card_last_digits}")

    upcoming = UpcomingTransaction(
        kind="bill",
        name=f"Kreditkortsfaktura — {card_label}",
        amount=parsed.total_amount or (parsed.closing_balance or Decimal("0")),
        expected_date=parsed.due_date or date.today(),
        debit_date=parsed.due_date or date.today(),
        debit_account_id=payer.id if payer else None,
        autogiro=False,
        bankgiro=parsed.bankgiro,
        ocr_reference=parsed.ocr_reference,
        source="pdf_parser",
        source_image_path=str(original_path),
        notes=" · ".join(notes_parts) or None,
    )
    session.add(upcoming)
    session.flush()

    # Gammal faktura? Matcha direkt mot redan befintlig bankrad så den
    # flyttas från "Kommande" → "Betalda" utan omväg.
    from ..upcoming_match import UpcomingMatcher as _UM
    _UM(session).backfill_match([upcoming])

    # Kortinnehavar-summering: hur mycket var och en köpte
    cardholders_breakdown: dict[str, float] = {}
    for tx in new_txs:
        if not tx.cardholder:
            continue
        cardholders_breakdown[tx.cardholder] = (
            cardholders_breakdown.get(tx.cardholder, 0.0) + float(tx.amount)
        )

    return {
        "parser": f"pdf:{parsed.issuer}",
        "upcoming_id": upcoming.id,
        "card_account_id": cc_account.id,
        "card_account_name": cc_account.name,
        "cardholders_breakdown": {
            k: round(v, 2) for k, v in cardholders_breakdown.items()
        },
        "transactions_created": len(new_txs),
        "transactions_skipped_duplicates": skipped,
        "transfers_marked": transfer_result.marked,
        "transfers_paired": transfer_result.paired,
        "internal_pairs": internal.pairs,
        "invoice_total": float(upcoming.amount),
        "due_date": upcoming.expected_date.isoformat(),
        "opening_balance_extracted": (
            float(parsed.opening_balance) if parsed.opening_balance else None
        ),
        "closing_balance_extracted": (
            float(parsed.closing_balance) if parsed.closing_balance else None
        ),
        "card_last_digits": parsed.card_last_digits,
        "payer_account_id": payer.id if payer else None,
    }


@router.post("/parse-credit-card-invoice")
async def parse_credit_card_invoice(
    files: list[UploadFile] = File(...),
    session: Session = Depends(db),
    llm: LMStudioClient = Depends(llm_client),
) -> dict:
    """Läs en kreditkortsfaktura (PDF eller bild) och:
    1. Skapa en UpcomingTransaction för hela fakturan (för cashflow)
    2. Skapa alla enskilda köp som Transaction-rader på kortkontot
       (med dedup + auto-kategorisering)
    3. Kör transfer-detektering så autogiro-dragningen från
       lönekontot/gemensamt paras ihop när den kommer i nästa CSV-import
    """
    if not files:
        raise HTTPException(400, "Inga filer skickades")
    if not llm.is_alive():
        raise HTTPException(503, "LM Studio är inte tillgänglig")

    invoice_dir = settings.data_dir / "cc_invoices"
    invoice_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")

    all_images: list[bytes] = []
    img_mime = "image/png"
    saved_paths: list[str] = []
    for idx, f in enumerate(files):
        data = await f.read()
        if not data:
            continue
        p = invoice_dir / f"{ts}_{idx}_{f.filename or 'cc'}"
        p.write_bytes(data)
        saved_paths.append(str(p))
        imgs, mime = _file_to_images(data, f.content_type)
        all_images.extend(imgs)
        img_mime = mime

    if not all_images:
        raise HTTPException(400, "Inga läsbara bilder")

    user_content: list[dict] = [{
        "type": "text",
        "text": (
            "Extrahera kreditkortsfakturan: sammanfattning + alla enskilda "
            "transaktioner. Returnera JSON enligt schemat."
        ),
    }]
    for img in all_images:
        b64 = base64.b64encode(img).decode("ascii")
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{img_mime};base64,{b64}"},
        })

    try:
        parsed = llm.complete_json(
            [{"role": "system", "content": _cc_invoice_system_prompt()},
             {"role": "user", "content": user_content}],
            schema=_cc_invoice_schema(),
            temperature=0.0,
        )
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        log.exception("CC invoice parse failed")
        raise HTTPException(500, _vision_error_hint(exc)) from exc

    # Hitta eller skapa kortkontot
    cc_account = _resolve_or_create_cc_account(
        session,
        issuer=parsed.get("card_issuer"),
        card_name=parsed.get("card_name"),
    )

    # Auto-sätt ingående saldo på kortkontot om det saknas.
    # "Ingående saldo" på en faktura = skuld vid periodens start.
    # I vår modell: credit-konton har NEGATIVT saldo när man har skuld
    # (pengar som ska ut), så invertera tecknet.
    if cc_account.opening_balance is None and parsed.get("opening_balance") is not None:
        try:
            ob = Decimal(str(parsed["opening_balance"]))
            # På kreditkort är positiv skuld = negativt saldo för oss
            cc_account.opening_balance = -abs(ob) if ob > 0 else ob
            # Periodstart som startdatum för saldot
            period_start = parsed.get("statement_period_start")
            if period_start:
                try:
                    cc_account.opening_balance_date = date.fromisoformat(period_start)
                except (ValueError, TypeError):
                    pass
            session.flush()
        except (ValueError, TypeError):
            pass

    # Rooten — skapa en "import"-post för audit
    imp = Import(
        filename=saved_paths[0].split("/")[-1] if saved_paths else "cc_invoice",
        bank=cc_account.bank,
        sha256="cc-" + ts + "-" + str(cc_account.id),
        row_count=0,
    )
    session.add(imp)
    session.flush()

    # Skapa enskilda transaktioner med dedup
    import hashlib
    existing_hashes = {
        h for (h,) in session.query(Transaction.hash)
        .filter(Transaction.account_id == cc_account.id).all()
    }

    new_txs: list[Transaction] = []
    skipped = 0
    for row_index, row in enumerate(parsed.get("transactions") or []):
        try:
            tx_date = date.fromisoformat(row["date"])
        except (KeyError, ValueError):
            continue
        amount = Decimal(str(row["amount"]))
        merchant = str(row.get("merchant") or "").strip()
        city = str(row.get("city") or "").strip()
        description = f"{merchant} [{city}]" if merchant and city else (merchant or "Okänt")

        # Hash nyckel: account + datum + belopp + beskrivning + row_index
        key = f"{cc_account.id}|{tx_date.isoformat()}|{amount}|{description.strip().lower()}|#{row_index}"
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if h in existing_hashes:
            skipped += 1
            continue
        existing_hashes.add(h)

        tx = Transaction(
            account_id=cc_account.id,
            date=tx_date,
            amount=amount,
            currency="SEK",
            raw_description=description,
            source_file_id=imp.id,
            hash=h,
        )
        session.add(tx)
        new_txs.append(tx)

    imp.row_count = len(new_txs)
    session.flush()

    # Kategorisering (regler + LLM fallback)
    if new_txs:
        engine = CategorizationEngine(session, llm=llm)
        results = engine.categorize_batch(new_txs)
        engine.apply_results(new_txs, results)
        session.flush()

    # Transfer-detektor kör mot hela setet
    detector = TransferDetector(session)
    transfer_result = detector.detect_and_link(new_txs)
    internal = detector.detect_internal_transfers()
    session.flush()

    # Skapa UpcomingTransaction för själva fakturan
    due_str = parsed.get("due_date")
    try:
        due_date = date.fromisoformat(due_str)
    except (TypeError, ValueError):
        due_date = date.today()

    # Hitta konto som betalar detta kreditkort via pays_credit_account_id
    payer = (
        session.query(Account)
        .filter(Account.pays_credit_account_id == cc_account.id)
        .first()
    )

    card_label = parsed.get("card_name") or cc_account.name
    notes_parts = []
    if parsed.get("statement_period_start") and parsed.get("statement_period_end"):
        notes_parts.append(
            f"Period: {parsed['statement_period_start']} – {parsed['statement_period_end']}"
        )
    if parsed.get("card_last_digits"):
        notes_parts.append(f"Kort ****{parsed['card_last_digits']}")

    upcoming = UpcomingTransaction(
        kind="bill",
        name=f"Kreditkortsfaktura — {card_label}",
        amount=Decimal(str(parsed["total_amount"])),
        expected_date=due_date,
        debit_date=due_date,
        debit_account_id=payer.id if payer else None,
        autogiro=bool(parsed.get("autogiro", False)),
        bankgiro=parsed.get("bankgiro"),
        ocr_reference=parsed.get("ocr_reference"),
        source="vision_ai",
        source_image_path=saved_paths[0] if saved_paths else None,
        notes=" · ".join(notes_parts) or None,
    )
    session.add(upcoming)
    session.flush()
    from ..upcoming_match import UpcomingMatcher as _UM
    _UM(session).backfill_match([upcoming])

    return {
        "upcoming_id": upcoming.id,
        "card_account_id": cc_account.id,
        "card_account_name": cc_account.name,
        "transactions_created": len(new_txs),
        "transactions_skipped_duplicates": skipped,
        "transfers_marked": transfer_result.marked,
        "transfers_paired": transfer_result.paired,
        "internal_pairs": internal.pairs,
        "invoice_total": float(upcoming.amount),
        "due_date": due_date.isoformat(),
        "payer_account_id": payer.id if payer else None,
        "opening_balance_extracted": parsed.get("opening_balance"),
        "closing_balance_extracted": parsed.get("closing_balance"),
        "opening_balance_set_on_account": (
            float(cc_account.opening_balance)
            if cc_account.opening_balance is not None else None
        ),
        "opening_balance_date": (
            cc_account.opening_balance_date.isoformat()
            if cc_account.opening_balance_date else None
        ),
    }
