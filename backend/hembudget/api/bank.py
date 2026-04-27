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
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..school import is_enabled as school_enabled
from ..db.base import session_scope
from ..db.models import (
    Account,
    PaymentReminder,
    ScheduledPayment,
    Transaction,
    UpcomingTransaction,
)
from ..school.bank_models import BankSession, CreditScoreSnapshot
from ..school.credit_scoring import compute_score
from ..school.engines import master_session
from ..school.models import BatchArtifact, ScenarioBatch, Student
from ..security.crypto import hash_password, verify_password
from .deps import TokenInfo, db as scope_db, require_token

log = logging.getLogger(__name__)

router = APIRouter(prefix="/bank", tags=["bank"])


SESSION_TTL_MINUTES = 15
PIN_PATTERN = re.compile(r"^\d{4}$")


def _require_school() -> None:
    if not school_enabled():
        raise HTTPException(404, "School mode inaktivt")


def _student_from_info(info: TokenInfo) -> int:
    """Hämta vilken elev requesten gäller.

    - Elev-token: ``info.student_id`` är satt direkt vid token-skapande.
    - Lärare med ``x-as-student``-impersonation: middleware har redan
      verifierat ägarskap och satt ``current_actor_student`` i
      ContextVar:n. Vi läser den.
      OBS: ``info.student_id`` är alltid None på lärar-tokens — fick
      alla impersonerade lärare att få 400 här i tidigare versioner."""
    if info.role == "student" and info.student_id:
        return info.student_id
    if info.role == "teacher":
        from ..school.engines import get_current_actor_student
        sid = get_current_actor_student()
        if sid is not None:
            return sid
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


# ---------- Kommande betalningar — signera + execute ----------

class UpcomingPaymentRow(BaseModel):
    upcoming_id: int
    name: str
    amount: float
    expected_date: str
    debit_account_id: Optional[int] = None
    already_signed: bool
    scheduled_payment_id: Optional[int] = None
    scheduled_status: Optional[str] = None
    scheduled_date: Optional[str] = None


class SignBatchIn(BaseModel):
    upcoming_ids: list[int] = Field(min_length=1)
    account_id: int
    bank_session_token: str
    # Default = upcoming.expected_date; överskrivs via override
    override_date: Optional[str] = None  # ISO YYYY-MM-DD


class SignBatchOut(BaseModel):
    signed_count: int
    scheduled_payment_ids: list[int]


def _verify_bank_session(
    info: TokenInfo, token: str, required_purpose_prefix: Optional[str] = None,
) -> BankSession:
    """Lita på sessionens existens och att den är confirmed inom 15 min.
    Vi använder den som 'bevis' att eleven nyligen genomfört BankID."""
    student_id = _student_from_info(info)
    with master_session() as s:
        sess = (
            s.query(BankSession)
            .filter(BankSession.token == token)
            .first()
        )
        if not sess:
            raise HTTPException(404, "BankID-sessionen finns inte")
        if sess.student_id != student_id:
            raise HTTPException(403, "Sessionen tillhör annan elev")
        if not sess.confirmed_at:
            raise HTTPException(401, "BankID-sessionen är inte bekräftad")
        if sess.expires_at < datetime.utcnow():
            raise HTTPException(410, "BankID-sessionen har löpt ut")
        if required_purpose_prefix and not sess.purpose.startswith(
            required_purpose_prefix
        ):
            raise HTTPException(
                403,
                f"Sessionens syfte ({sess.purpose}) tillåter inte detta",
            )
        # Detacha — vi behöver bara token-string utåt
        return BankSession(
            id=sess.id,
            student_id=sess.student_id,
            token=sess.token,
            purpose=sess.purpose,
            created_at=sess.created_at,
            expires_at=sess.expires_at,
            confirmed_at=sess.confirmed_at,
            ip_address=sess.ip_address,
        )


@router.get(
    "/upcoming-payments", response_model=list[UpcomingPaymentRow],
)
def list_upcoming_for_signing(
    scope = Depends(scope_db),
    info: TokenInfo = Depends(require_token),
) -> list[UpcomingPaymentRow]:
    """Lista obetalda fakturor + redan signerade (status). Senast först.

    Tar med matchade-fakturor som redan har en ScheduledPayment så
    eleven ser status. Exkluderar matched_transaction_id IS NOT NULL
    (= redan betalda i bokföringen).
    """
    _require_school()
    _student_from_info(info)
    rows = (
        scope.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "bill",
            UpcomingTransaction.matched_transaction_id.is_(None),
        )
        .order_by(UpcomingTransaction.expected_date.asc())
        .all()
    )
    out: list[UpcomingPaymentRow] = []
    for u in rows:
        sched = (
            scope.query(ScheduledPayment)
            .filter(ScheduledPayment.upcoming_id == u.id)
            .order_by(ScheduledPayment.id.desc())
            .first()
        )
        out.append(UpcomingPaymentRow(
            upcoming_id=u.id,
            name=u.name,
            amount=float(u.amount),
            expected_date=u.expected_date.isoformat(),
            debit_account_id=u.debit_account_id,
            already_signed=sched is not None,
            scheduled_payment_id=sched.id if sched else None,
            scheduled_status=sched.status if sched else None,
            scheduled_date=(
                sched.scheduled_date.isoformat() if sched else None
            ),
        ))
    return out


@router.post("/upcoming-payments/sign", response_model=SignBatchOut)
def sign_payment_batch(
    payload: SignBatchIn,
    scope = Depends(scope_db),
    info: TokenInfo = Depends(require_token),
) -> SignBatchOut:
    """Signera en batch av kommande betalningar.

    Kräver bekräftad BankSession (verifieras via token). Skapar
    ScheduledPayment per upcoming_id. Sparar bank_session_token
    så audit-spåret är komplett.

    Idempotent: redan signerade upcoming_ids hoppas över (inget fel).
    """
    _require_school()
    _student_from_info(info)
    _verify_bank_session(info, payload.bank_session_token)

    acc = scope.get(Account, payload.account_id)
    if not acc:
        raise HTTPException(404, "Kontot finns inte")
    if acc.type != "checking":
        raise HTTPException(
            400,
            "Endast lönekonto/checkingkonto kan användas för betalning",
        )

    from datetime import date as _date
    override: Optional[_date] = None
    if payload.override_date:
        try:
            override = _date.fromisoformat(payload.override_date)
        except ValueError:
            raise HTTPException(400, "override_date måste vara YYYY-MM-DD")

    created_ids: list[int] = []
    for uid in payload.upcoming_ids:
        u = scope.get(UpcomingTransaction, uid)
        if not u or u.kind != "bill":
            continue
        if u.matched_transaction_id is not None:
            continue
        # Skippa redan signerade
        existing = (
            scope.query(ScheduledPayment)
            .filter(
                ScheduledPayment.upcoming_id == uid,
                ScheduledPayment.status == "scheduled",
            )
            .first()
        )
        if existing:
            continue
        sched_date = override or u.expected_date
        sp = ScheduledPayment(
            upcoming_id=uid,
            account_id=payload.account_id,
            amount=u.amount,
            scheduled_date=sched_date,
            signed_via_session_token=payload.bank_session_token,
            status="scheduled",
        )
        scope.add(sp)
        scope.flush()
        created_ids.append(sp.id)

    return SignBatchOut(
        signed_count=len(created_ids),
        scheduled_payment_ids=created_ids,
    )


def _balance_for_account(scope, account_id: int) -> Decimal:
    from sqlalchemy import func as sa_func
    acc = scope.get(Account, account_id)
    if acc is None:
        return Decimal("0")
    base = acc.opening_balance or Decimal("0")
    q = scope.query(
        sa_func.coalesce(sa_func.sum(Transaction.amount), 0),
    ).filter(Transaction.account_id == account_id)
    if acc.opening_balance_date is not None:
        q = q.filter(Transaction.date >= acc.opening_balance_date)
    total = q.scalar() or Decimal("0")
    if not isinstance(total, Decimal):
        total = Decimal(str(total))
    return base + total


@router.post("/scheduled-payments/run-due")
def run_due_payments(
    scope = Depends(scope_db),
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Execute alla 'scheduled'-payments vars datum passerats.

    Kallas lazy från frontend (varje gång eleven öppnar /bank/scheduled
    eller /transactions). På Cloud Run kan vi även lägga till en
    Cloud Scheduler-trigg en gång per dygn — men lazy räcker för
    det pedagogiska flödet.

    Per payment:
    - Saldo räcker → skapa Transaction, status='executed',
      matcha UpcomingTransaction
    - Saldo räcker inte → status='failed_no_funds' (PR 7 triggar
      påminnelse-flödet)

    Returnerar {executed, failed, skipped}.
    """
    _require_school()
    _student_from_info(info)
    from datetime import date as _date
    today = _date.today()
    due = (
        scope.query(ScheduledPayment)
        .filter(
            ScheduledPayment.status == "scheduled",
            ScheduledPayment.scheduled_date <= today,
        )
        .all()
    )
    executed = 0
    failed = 0
    for sp in due:
        bal = _balance_for_account(scope, sp.account_id)
        if bal < sp.amount:
            sp.status = "failed_no_funds"
            sp.failure_reason = (
                f"Saldo {int(bal)} kr räckte inte för {int(sp.amount)} kr"
            )
            sp.executed_at = datetime.utcnow()
            failed += 1
            continue
        # Skapa transaktion (debet på lönekontot)
        u = scope.get(UpcomingTransaction, sp.upcoming_id)
        desc = u.name if u else f"Signerad betalning #{sp.id}"
        # Hash för dedup vid rerun
        import hashlib as _h
        h = _h.sha256(
            f"sched:{sp.id}:{sp.scheduled_date}:{sp.amount}".encode()
        ).hexdigest()[:32]
        tx = Transaction(
            account_id=sp.account_id,
            date=sp.scheduled_date,
            amount=-sp.amount,
            currency="SEK",
            raw_description=desc,
            is_transfer=False,
            hash=h,
        )
        scope.add(tx)
        scope.flush()
        sp.executed_transaction_id = tx.id
        sp.executed_at = datetime.utcnow()
        sp.status = "executed"
        if u:
            u.matched_transaction_id = tx.id
        executed += 1

    return {
        "executed": executed,
        "failed": failed,
        "skipped": 0,
        "due_count": len(due),
    }


# Stege för late-fee per påminnelsenivå
_REMINDER_FEE_STEPS = {
    1: Decimal("60"),
    2: Decimal("120"),
    3: Decimal("180"),
    4: Decimal("180"),  # 'Kronofogden'-steget
}

_REMINDER_DAY_TRIGGERS = {1: 5, 2: 14, 3: 30, 4: 45}


def _create_reminder(
    scope, upcoming_id: int, scheduled_payment_id: Optional[int],
    reminder_no: int,
) -> PaymentReminder:
    """Skapa en PaymentReminder + en separat UpcomingTransaction
    för avgiften så eleven måste betala även den."""
    from datetime import date as _date, timedelta as _td
    fee = _REMINDER_FEE_STEPS.get(reminder_no, Decimal("180"))
    today = _date.today()
    u = scope.get(UpcomingTransaction, upcoming_id)
    name = (
        f"Påminnelseavgift {u.name if u else 'okänd'}"
        if reminder_no < 4
        else f"Inkasso/Kronofogden {u.name if u else 'okänd'}"
    )
    fee_due = today + _td(days=14)
    fee_upc = UpcomingTransaction(
        kind="bill",
        name=name,
        amount=fee,
        expected_date=fee_due,
        source="reminder",
    )
    if u:
        fee_upc.debit_account_id = u.debit_account_id
    scope.add(fee_upc)
    scope.flush()
    rem = PaymentReminder(
        upcoming_id=upcoming_id,
        scheduled_payment_id=scheduled_payment_id,
        reminder_no=reminder_no,
        issued_date=today,
        late_fee=fee,
        fee_upcoming_id=fee_upc.id,
    )
    scope.add(rem)
    scope.flush()
    return rem


@router.post("/reminders/run")
def run_reminders(
    scope = Depends(scope_db),
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Trigga påminnelse-flödet:

    1. För varje failed_no_funds ScheduledPayment OCH för varje
       UpcomingTransaction(kind=bill) som inte signerats och passerat
       förfallodag + 5 dagar:
       - Om reminder_no=1 inte finns → skapa
    2. För befintliga reminders, eskalera om dagar passerats:
       - 14 dagar efter reminder_no=1 → reminder_no=2
       - 30 dagar efter förfall → reminder_no=3
       - 45 dagar → reminder_no=4 (kronofogden)

    Idempotent: re-run skapar inga dubletter (UNIQUE-konstraint på
    (upcoming_id, reminder_no) skulle vara säkrast — för V1 räcker
    en lookup-check).
    """
    _require_school()
    _student_from_info(info)
    from datetime import date as _date, timedelta as _td
    today = _date.today()
    triggered: list[int] = []

    # Hitta alla obetalda fakturor som passerat förfall + 5d
    overdue = (
        scope.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "bill",
            UpcomingTransaction.matched_transaction_id.is_(None),
            UpcomingTransaction.source != "reminder",
            UpcomingTransaction.expected_date <= today - _td(days=5),
        )
        .all()
    )
    for u in overdue:
        # Hitta senaste reminder för fakturan
        latest = (
            scope.query(PaymentReminder)
            .filter(PaymentReminder.upcoming_id == u.id)
            .order_by(PaymentReminder.reminder_no.desc())
            .first()
        )
        days_overdue = (today - u.expected_date).days
        # Vilken nivå borde fakturan vara på?
        target_no = 1
        for n, threshold in _REMINDER_DAY_TRIGGERS.items():
            if days_overdue >= threshold:
                target_no = n
        # Eskalera bara framåt
        current = latest.reminder_no if latest else 0
        if target_no > current:
            sp = (
                scope.query(ScheduledPayment)
                .filter(ScheduledPayment.upcoming_id == u.id)
                .order_by(ScheduledPayment.id.desc())
                .first()
            )
            rem = _create_reminder(
                scope,
                upcoming_id=u.id,
                scheduled_payment_id=sp.id if sp else None,
                reminder_no=target_no,
            )
            triggered.append(rem.id)

    return {
        "triggered": len(triggered),
        "reminder_ids": triggered,
        "checked_overdue": len(overdue),
    }


@router.get("/reminders")
def list_reminders(
    scope = Depends(scope_db),
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Lista alla påminnelser för aktuell elev."""
    _require_school()
    _student_from_info(info)
    rows = (
        scope.query(PaymentReminder)
        .order_by(PaymentReminder.issued_date.desc())
        .all()
    )
    out = []
    for r in rows:
        u = scope.get(UpcomingTransaction, r.upcoming_id)
        out.append({
            "id": r.id,
            "reminder_no": r.reminder_no,
            "issued_date": r.issued_date.isoformat(),
            "late_fee": float(r.late_fee),
            "upcoming_name": u.name if u else "—",
            "fee_upcoming_id": r.fee_upcoming_id,
            "settled_at": r.settled_at.isoformat() if r.settled_at else None,
        })
    return {"reminders": out, "count": len(out)}


# ---------- EkonomiSkalan / kreditbetyg ----------

class CreditScoreOut(BaseModel):
    score: int
    grade: str
    factors: dict
    reasons_md: str
    computed_at: str


def _compute_credit_for_student(
    scope, student_id: int,
) -> CreditScoreOut:
    """Räkna fram aktuellt kreditbetyg och cachea i master-DB."""
    from datetime import date as _date

    # Antalet sena betalningar
    late_payments = (
        scope.query(PaymentReminder)
        .count()
    )
    reminders_high = (
        scope.query(PaymentReminder)
        .filter(PaymentReminder.reminder_no >= 3)
        .count()
    )
    failed_payments = (
        scope.query(ScheduledPayment)
        .filter(ScheduledPayment.status == "failed_no_funds")
        .count()
    )

    # Skuldkvot: totala lån / (gross-lön * 12)
    from ..db.models import Loan
    debt_total = Decimal("0")
    for L in scope.query(Loan).filter(Loan.active.is_(True)).all():
        debt_total += Decimal(L.principal_amount or 0)

    # Sparande-buffert
    savings_balance = Decimal("0")
    avg_monthly_expense = Decimal("0")
    for acc in scope.query(Account).filter(
        Account.type.in_({"savings", "isk"})
    ).all():
        if acc.opening_balance:
            savings_balance += Decimal(acc.opening_balance)
    # Minimal hint: räkna utgifter senaste 3 månaderna
    from sqlalchemy import func as sa_func
    today = _date.today()
    three_months_ago = today.replace(day=1)
    if three_months_ago.month <= 3:
        three_months_ago = three_months_ago.replace(
            year=three_months_ago.year - 1,
            month=12 - (3 - three_months_ago.month),
        )
    else:
        three_months_ago = three_months_ago.replace(
            month=three_months_ago.month - 3,
        )
    expenses = (
        scope.query(sa_func.coalesce(sa_func.sum(Transaction.amount), 0))
        .filter(
            Transaction.amount < 0,
            Transaction.date >= three_months_ago,
        )
        .scalar() or 0
    )
    avg_monthly_expense = abs(Decimal(str(expenses))) / 3
    savings_buffer_months = (
        float(savings_balance / avg_monthly_expense)
        if avg_monthly_expense > 0 else 0.0
    )

    # Hämta lön + satisfaction från master
    with master_session() as ms:
        from ..school.models import StudentProfile
        from ..school.employer_models import EmployerSatisfaction
        profile = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        gross = profile.gross_salary_monthly if profile else 30000
        annual_income = Decimal(str(gross * 12))
        debt_ratio = float(debt_total / annual_income) if annual_income > 0 else 0.0

        sat = (
            ms.query(EmployerSatisfaction)
            .filter(EmployerSatisfaction.student_id == student_id)
            .first()
        )
        sat_score = sat.score if sat else 70

        st = ms.get(Student, student_id)
        months_on_platform = 0
        if st and st.created_at:
            delta_days = (datetime.utcnow() - st.created_at).days
            months_on_platform = delta_days // 30

        result = compute_score(
            late_payments=late_payments,
            failed_payments=failed_payments,
            reminders_l3_or_higher=reminders_high,
            debt_ratio=debt_ratio,
            savings_buffer_months=savings_buffer_months,
            satisfaction_score=sat_score,
            months_on_platform=months_on_platform,
        )

        # Cachea i master-DB (insert always — håller historik)
        snap = CreditScoreSnapshot(
            student_id=student_id,
            score=result.score,
            grade=result.grade,
            factors=result.factors,
            reasons_md=result.reasons_md,
        )
        ms.add(snap)
        ms.flush()
        computed_at = snap.computed_at

    return CreditScoreOut(
        score=result.score,
        grade=result.grade,
        factors=result.factors,
        reasons_md=result.reasons_md,
        computed_at=computed_at.isoformat(),
    )


@router.get("/credit-score", response_model=CreditScoreOut)
def get_credit_score(
    scope = Depends(scope_db),
    info: TokenInfo = Depends(require_token),
) -> CreditScoreOut:
    """Räkna fram + cachea aktuellt kreditbetyg.

    Eleven får läsa varje gång — vi sparar snapshot i master-DB så
    läraren kan se historiken via /teacher/employer/* (PR 7d eller
    senare).
    """
    _require_school()
    student_id = _student_from_info(info)
    return _compute_credit_for_student(scope, student_id)


@router.get("/scheduled-payments")
def list_scheduled_payments(
    scope = Depends(scope_db),
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Lista alla ScheduledPayments för aktuell elev — senaste först."""
    _require_school()
    _student_from_info(info)
    rows = (
        scope.query(ScheduledPayment)
        .order_by(ScheduledPayment.scheduled_date.desc())
        .all()
    )
    out = []
    for sp in rows:
        u = scope.get(UpcomingTransaction, sp.upcoming_id)
        out.append({
            "id": sp.id,
            "upcoming_id": sp.upcoming_id,
            "name": u.name if u else "—",
            "account_id": sp.account_id,
            "amount": float(sp.amount),
            "scheduled_date": sp.scheduled_date.isoformat(),
            "status": sp.status,
            "executed_at": sp.executed_at.isoformat() if sp.executed_at else None,
            "failure_reason": sp.failure_reason,
        })
    return {"scheduled_payments": out, "count": len(out)}


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
