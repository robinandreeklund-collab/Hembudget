from __future__ import annotations

import base64
import io
import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import Account, Loan, LoanPayment, LoanScheduleEntry, Transaction
from ..llm.client import LMStudioClient, LLMUnavailable
from ..loans.matcher import LoanMatcher
from .deps import db, llm_client, require_auth

log = logging.getLogger(__name__)

router = APIRouter(prefix="/loans", tags=["loans"], dependencies=[Depends(require_auth)])


class LoanIn(BaseModel):
    name: str
    lender: str
    loan_number: Optional[str] = None
    principal_amount: Decimal
    start_date: date
    interest_rate: float
    binding_type: str = "rörlig"
    binding_end_date: Optional[date] = None
    amortization_monthly: Optional[Decimal] = None
    property_value: Optional[Decimal] = None
    match_pattern: Optional[str] = None
    notes: Optional[str] = None


class LoanUpdate(BaseModel):
    name: Optional[str] = None
    lender: Optional[str] = None
    loan_number: Optional[str] = None
    principal_amount: Optional[Decimal] = None
    start_date: Optional[date] = None
    interest_rate: Optional[float] = None
    binding_type: Optional[str] = None
    binding_end_date: Optional[date] = None
    amortization_monthly: Optional[Decimal] = None
    property_value: Optional[Decimal] = None
    match_pattern: Optional[str] = None
    notes: Optional[str] = None
    active: Optional[bool] = None


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    lender: str
    loan_number: Optional[str]
    principal_amount: Decimal
    start_date: date
    interest_rate: float
    binding_type: str
    binding_end_date: Optional[date]
    amortization_monthly: Optional[Decimal]
    property_value: Optional[Decimal]
    match_pattern: Optional[str]
    notes: Optional[str]
    active: bool


class LoanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    lender: str
    principal_amount: Decimal
    outstanding_balance: Decimal
    amortization_paid: Decimal
    interest_paid: Decimal
    interest_rate: float
    binding_type: str
    binding_end_date: Optional[date]
    ltv: Optional[float] = None     # balance / property_value
    payments_count: int


@router.get("/", response_model=list[LoanOut])
def list_loans(session: Session = Depends(db)) -> list[Loan]:
    return session.query(Loan).order_by(Loan.id).all()


@router.post("/", response_model=LoanOut)
def create_loan(payload: LoanIn, session: Session = Depends(db)) -> Loan:
    loan = Loan(**payload.model_dump())
    session.add(loan)
    session.flush()
    # Match existing transactions against the new loan
    txs = session.query(Transaction).filter(Transaction.amount < 0).all()
    LoanMatcher(session).match_and_classify(txs)
    return loan


@router.patch("/{loan_id}", response_model=LoanOut)
def update_loan(loan_id: int, payload: LoanUpdate, session: Session = Depends(db)) -> Loan:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(loan, k, v)
    session.flush()
    if payload.match_pattern is not None:
        txs = session.query(Transaction).filter(Transaction.amount < 0).all()
        LoanMatcher(session).match_and_classify(txs)
    return loan


@router.delete("/{loan_id}")
def delete_loan(loan_id: int, session: Session = Depends(db)) -> dict:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    # Remove associated payment links (not the underlying transactions)
    session.query(LoanPayment).filter(LoanPayment.loan_id == loan_id).delete()
    session.delete(loan)
    return {"deleted": loan_id}


@router.get("/{loan_id}/summary", response_model=LoanSummary)
def loan_summary(loan_id: int, session: Session = Depends(db)) -> LoanSummary:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    m = LoanMatcher(session)
    balance = m.outstanding_balance(loan)
    interest = m.total_interest_paid(loan)
    amortized = loan.principal_amount - balance
    count = session.query(LoanPayment).filter(LoanPayment.loan_id == loan.id).count()
    ltv = None
    if loan.property_value and loan.property_value > 0:
        ltv = float(balance / loan.property_value)
    return LoanSummary(
        id=loan.id,
        name=loan.name,
        lender=loan.lender,
        principal_amount=loan.principal_amount,
        outstanding_balance=balance,
        amortization_paid=amortized,
        interest_paid=interest,
        interest_rate=loan.interest_rate,
        binding_type=loan.binding_type,
        binding_end_date=loan.binding_end_date,
        ltv=ltv,
        payments_count=count,
    )


@router.get("/summaries/all", response_model=list[LoanSummary])
def all_summaries(session: Session = Depends(db)) -> list[LoanSummary]:
    loans = session.query(Loan).filter(Loan.active.is_(True)).all()
    out: list[LoanSummary] = []
    m = LoanMatcher(session)
    for loan in loans:
        balance = m.outstanding_balance(loan)
        interest = m.total_interest_paid(loan)
        amortized = loan.principal_amount - balance
        count = session.query(LoanPayment).filter(LoanPayment.loan_id == loan.id).count()
        ltv = None
        if loan.property_value and loan.property_value > 0:
            ltv = float(balance / loan.property_value)
        out.append(LoanSummary(
            id=loan.id, name=loan.name, lender=loan.lender,
            principal_amount=loan.principal_amount,
            outstanding_balance=balance, amortization_paid=amortized,
            interest_paid=interest, interest_rate=loan.interest_rate,
            binding_type=loan.binding_type, binding_end_date=loan.binding_end_date,
            ltv=ltv, payments_count=count,
        ))
    return out


@router.get("/{loan_id}/payments")
def list_payments(loan_id: int, session: Session = Depends(db)) -> dict:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    rows = (
        session.query(LoanPayment)
        .filter(LoanPayment.loan_id == loan_id)
        .order_by(LoanPayment.date.asc())
        .all()
    )
    return {
        "payments": [
            {
                "id": p.id,
                "date": p.date.isoformat(),
                "amount": float(p.amount),
                "type": p.payment_type,
                "transaction_id": p.transaction_id,
            }
            for p in rows
        ]
    }


@router.post("/rescan")
def rescan(session: Session = Depends(db)) -> dict:
    """Kör om matchning mot alla historiska transaktioner."""
    # Rensa tidigare länkar så att mönster- och schemaändringar slår igenom
    session.query(LoanPayment).delete()
    session.query(LoanScheduleEntry).filter(
        LoanScheduleEntry.matched_transaction_id.is_not(None)
    ).update({"matched_transaction_id": None, "matched_at": None})
    session.flush()
    txs = session.query(Transaction).filter(Transaction.amount < 0).all()
    r = LoanMatcher(session).match_and_classify(txs)
    return {
        "linked": r.linked,
        "unclassified": r.unclassified,
        "matched_via_schedule": r.matched_via_schedule,
        "matched_via_pattern": r.matched_via_pattern,
    }


# ----- Schema / planerade betalningar -----

class ScheduleEntryIn(BaseModel):
    due_date: date
    amount: Decimal
    payment_type: str  # "interest" | "amortization"
    notes: Optional[str] = None


class ScheduleEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    loan_id: int
    due_date: date
    amount: Decimal
    payment_type: str
    matched_transaction_id: Optional[int]
    notes: Optional[str]


@router.get("/{loan_id}/schedule", response_model=list[ScheduleEntryOut])
def list_schedule(loan_id: int, session: Session = Depends(db)) -> list[LoanScheduleEntry]:
    return (
        session.query(LoanScheduleEntry)
        .filter(LoanScheduleEntry.loan_id == loan_id)
        .order_by(LoanScheduleEntry.due_date.asc())
        .all()
    )


@router.post("/{loan_id}/schedule", response_model=ScheduleEntryOut)
def create_schedule_entry(
    loan_id: int,
    payload: ScheduleEntryIn,
    session: Session = Depends(db),
) -> LoanScheduleEntry:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    if payload.payment_type not in ("interest", "amortization"):
        raise HTTPException(400, "payment_type must be 'interest' or 'amortization'")
    entry = LoanScheduleEntry(
        loan_id=loan_id,
        due_date=payload.due_date,
        amount=payload.amount,
        payment_type=payload.payment_type,
        notes=payload.notes,
    )
    session.add(entry)
    session.flush()
    # Kör matcher så nya schemaraden kan plocka upp befintliga transaktioner
    txs = session.query(Transaction).filter(Transaction.amount < 0).all()
    LoanMatcher(session).match_and_classify(txs)
    return entry


@router.delete("/{loan_id}/schedule/{entry_id}")
def delete_schedule_entry(
    loan_id: int, entry_id: int, session: Session = Depends(db)
) -> dict:
    entry = session.get(LoanScheduleEntry, entry_id)
    if entry is None or entry.loan_id != loan_id:
        raise HTTPException(404, "Schedule entry not found")
    # Rensa kopplade LoanPayment om schemat matchade en transaktion
    if entry.matched_transaction_id:
        session.query(LoanPayment).filter(
            LoanPayment.transaction_id == entry.matched_transaction_id,
            LoanPayment.loan_id == loan_id,
        ).delete()
    session.delete(entry)
    return {"deleted": entry_id}


class ScheduleGenerateIn(BaseModel):
    months: int = 3
    day_of_month: Optional[int] = None


@router.post("/{loan_id}/schedule/generate", response_model=list[ScheduleEntryOut])
def generate_schedule(
    loan_id: int,
    payload: ScheduleGenerateIn,
    session: Session = Depends(db),
) -> list[LoanScheduleEntry]:
    loan = session.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(404, "Loan not found")
    m = LoanMatcher(session)
    entries = m.generate_schedule(
        loan, months=payload.months, day_of_month=payload.day_of_month
    )
    # Direkt-matcha mot befintliga transaktioner
    txs = session.query(Transaction).filter(Transaction.amount < 0).all()
    m.match_and_classify(txs)
    return entries


# ---- Skapa lån automatiskt från bankbilder via vision AI ----

PDF_MAGIC = b"%PDF"


def _file_to_images(content: bytes, content_type: str | None) -> tuple[list[bytes], str]:
    """Samma bild/PDF-logik som i upcoming.py."""
    if content.startswith(PDF_MAGIC) or (content_type or "").lower() == "application/pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(content)
        if len(pdf) == 0:
            raise HTTPException(400, "PDF:en innehåller inga sidor")
        images: list[bytes] = []
        for i in range(min(len(pdf), 5)):
            page = pdf[i]
            pil_image = page.render(scale=2.0).to_pil()
            buf = io.BytesIO()
            pil_image.save(buf, format="PNG", optimize=True)
            images.append(buf.getvalue())
        return images, "image/png"
    return [content], content_type or "image/png"


def _loan_schema() -> dict:
    """JSON-schema för vision-extraktion av svensk banks lånesida."""
    return {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Beskrivande namn på lånet, t.ex. 'Bolån Nordea'.",
            },
            "lender": {
                "type": "string",
                "description": "Långivare, t.ex. 'Nordea Hypotek AB', 'SBAB'.",
            },
            "loan_number": {"type": ["string", "null"]},
            "principal_amount": {
                "type": ["number", "null"],
                "description": "Ursprungligt lånebelopp",
            },
            "current_balance": {
                "type": ["number", "null"],
                "description": "Aktuellt lånebelopp / återstående skuld",
            },
            "start_date": {
                "type": ["string", "null"],
                "description": "Utbetalningsdag / startdatum YYYY-MM-DD",
            },
            "interest_rate": {
                "type": ["number", "null"],
                "description": "Nominell ränta som decimaltal (0.042 = 4.2 %). null om ej synlig.",
            },
            "binding_type": {
                "type": ["string", "null"],
                "description": "'rörlig', '3mån', '1år', '3år' etc. '3 månaders bunden' → '3mån'.",
            },
            "amortization_monthly": {"type": ["number", "null"]},
            "repayment_account_number": {
                "type": ["string", "null"],
                "description": "Återbetalningskonto - användarens konto, t.ex. '1722 20 34439'.",
            },
            "security": {
                "type": ["string", "null"],
                "description": "Säkerhet/pant, t.ex. 'Fastighet: HJO, KAKTUSEN :5'",
            },
            "schedule": {
                "type": "array",
                "description": "Kommande betalningar från 'Betalningsplan'-fliken",
                "items": {
                    "type": "object",
                    "properties": {
                        "due_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "total_amount": {"type": "number"},
                        "remaining_balance_after": {"type": ["number", "null"]},
                        "amortization_amount": {
                            "type": ["number", "null"],
                            "description": "Om 'Amortering' syns separat",
                        },
                    },
                    "required": ["due_date", "total_amount"],
                },
            },
        },
        "required": ["lender"],
    }


def _loan_system_prompt() -> str:
    return (
        "Du läser svenska banksidor och skärmdumpar om bolån/privatlån "
        "(Nordea, SBAB, SEB, Handelsbanken, Länsförsäkringar m.fl.) och "
        "extraherar strukturerad lånedata. Returnera JSON enligt schemat.\n\n"
        "Viktigt:\n"
        "- Belopp som TAL i SEK (inget 'kr', komma → punkt). \n"
        "- Datum YYYY-MM-DD.\n"
        "- 'Utbetalningsdag' är lånets start_date.\n"
        "- 'Återbetalningskonto' är användarens bankkonto — lägg i "
        "  repayment_account_number (med blanksteg som i källan).\n"
        "- Om flera bilder visas, kombinera data: Låneinformation-bilden ger "
        "  grunden, Betalningsplan-bilden ger schedule[], Transaktioner-bilden "
        "  visar historiska betalningar (ignorera — vi läser dessa ur CSV).\n"
        "- För schedule: returnera ALLA kommande rader som syns. "
        "  'total_amount' = 'Belopp'-kolumnen. "
        "  'remaining_balance_after' = 'Återstående belopp'.\n"
        "- 'Ränta: 3 månaders bunden' → binding_type='3mån'.\n"
        "- Om ränta inte står explicit, sätt null — backend beräknar."
    )


def _derive_interest_rate(
    schedule: list[dict], current_balance: float | None
) -> float | None:
    """När räntan inte står ut: beräkna från snitt-ränta per månad.

    Räntedelen per rad = total_amount − amortization (om amort>0)
    Om amort = 0: hela total_amount är ränta.
    Årsränta = 12 × snitt(ränta) / återstående saldo.
    """
    if not schedule or not current_balance or current_balance <= 0:
        return None
    interest_amounts: list[float] = []
    for row in schedule:
        total = row.get("total_amount")
        amort = row.get("amortization_amount") or 0
        if total is None:
            continue
        interest = max(float(total) - float(amort), 0.0)
        if interest > 0:
            interest_amounts.append(interest)
    if not interest_amounts:
        return None
    avg = sum(interest_amounts) / len(interest_amounts)
    rate = (avg * 12) / current_balance
    return round(rate, 5)


@router.post("/parse-from-images", response_model=LoanOut)
async def parse_loan_from_images(
    files: list[UploadFile] = File(...),
    session: Session = Depends(db),
    llm: LMStudioClient = Depends(llm_client),
) -> Loan:
    """Läs en eller flera skärmdumpar/PDF:er från bankens lånesidor
    (Låneinformation, Betalningsplan, Transaktioner) och skapa lånet
    + hela betalningsplanen automatiskt."""
    if not files:
        raise HTTPException(400, "Inga filer skickades")
    if not llm.is_alive():
        raise HTTPException(503, "LM Studio är inte tillgänglig")

    # Spara originalen + bygg listan av bild-bytes
    loan_dir = settings.data_dir / "loan_sources"
    loan_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")

    all_images: list[bytes] = []
    img_mime = "image/png"
    saved_paths: list[str] = []
    for idx, f in enumerate(files):
        data = await f.read()
        if not data:
            continue
        p = loan_dir / f"{ts}_{idx}_{f.filename or 'src'}"
        p.write_bytes(data)
        saved_paths.append(str(p))
        try:
            imgs, mime = _file_to_images(data, f.content_type)
        except HTTPException:
            raise
        except Exception as exc:
            log.exception("source conversion failed")
            raise HTTPException(400, f"Kunde inte läsa {f.filename}: {exc}") from exc
        all_images.extend(imgs)
        img_mime = mime

    if not all_images:
        raise HTTPException(400, "Inga läsbara bilder")

    user_content: list[dict] = [
        {
            "type": "text",
            "text": (
                "Extrahera lånedata + betalningsplan från dessa bilder av "
                "bankens lånesida. Sammanställ från alla bilder till en "
                "strukturerad JSON enligt schemat."
            ),
        }
    ]
    for img in all_images:
        b64 = base64.b64encode(img).decode("ascii")
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{img_mime};base64,{b64}"},
        })

    try:
        parsed = llm.complete_json(
            [{"role": "system", "content": _loan_system_prompt()},
             {"role": "user", "content": user_content}],
            schema=_loan_schema(),
            temperature=0.0,
        )
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        log.exception("Loan vision parse failed")
        raise HTTPException(
            500,
            f"Modellen kunde inte tolka bilderna. Byt till en vision-kapabel "
            f"modell i LM Studio (t.ex. Qwen2.5-VL). Fel: {exc}",
        ) from exc

    # Plocka ut fält med säkra defaultvärden
    principal = parsed.get("principal_amount") or parsed.get("current_balance") or 0
    current_balance = parsed.get("current_balance") or parsed.get("principal_amount") or 0
    start_date_str = parsed.get("start_date")
    try:
        start_date_val = date.fromisoformat(start_date_str) if start_date_str else date.today()
    except ValueError:
        start_date_val = date.today()

    schedule_raw = parsed.get("schedule") or []

    interest_rate = parsed.get("interest_rate")
    if interest_rate is None:
        interest_rate = _derive_interest_rate(schedule_raw, float(current_balance))
    if interest_rate is None:
        interest_rate = 0.0

    # Amortering: från schema om möjligt, annars nyligen historik (nej —
    # vi har inget här), default 0
    amort_monthly = parsed.get("amortization_monthly")
    if amort_monthly is None and schedule_raw:
        amorts = [r.get("amortization_amount") or 0 for r in schedule_raw]
        if any(a > 0 for a in amorts):
            amort_monthly = max(amorts, default=0) or None

    # match_pattern: lånnummer är bäst, annars långivarnamn
    loan_number = parsed.get("loan_number")
    match_pattern = loan_number or parsed.get("lender")

    loan_name = parsed.get("name") or (
        f"{parsed.get('lender')} {loan_number or ''}".strip()
    )

    # Skapa lånet
    loan = Loan(
        name=loan_name,
        lender=parsed["lender"],
        loan_number=loan_number,
        principal_amount=Decimal(str(principal)),
        start_date=start_date_val,
        interest_rate=float(interest_rate),
        binding_type=parsed.get("binding_type") or "rörlig",
        amortization_monthly=(
            Decimal(str(amort_monthly)) if amort_monthly else None
        ),
        match_pattern=match_pattern,
        notes=parsed.get("security"),
    )
    session.add(loan)
    session.flush()

    # Auto-länka återbetalningskontot till användarens Account via account_number
    repay = parsed.get("repayment_account_number")
    if repay:
        target = "".join(c for c in repay if c.isdigit())
        for acc in session.query(Account).filter(Account.account_number.is_not(None)).all():
            acc_num = "".join(c for c in (acc.account_number or "") if c.isdigit())
            if acc_num and acc_num == target:
                # Sparar vi inte direkt på Loan — men vi kan använda som
                # extra info i notes för synlighet.
                prefix = loan.notes or ""
                loan.notes = (prefix + f"\nÅterbetalningskonto: {acc.name}").strip()
                break

    # Skapa schedule-rader
    for row in schedule_raw:
        try:
            due = date.fromisoformat(row["due_date"])
        except (KeyError, ValueError):
            continue
        total = Decimal(str(row.get("total_amount", 0)))
        amort = Decimal(str(row.get("amortization_amount") or 0))
        # Dela upp i ränta + amort
        if amort > 0:
            session.add(LoanScheduleEntry(
                loan_id=loan.id, due_date=due,
                amount=amort, payment_type="amortization",
            ))
            interest_part = max(total - amort, Decimal("0"))
            if interest_part > 0:
                session.add(LoanScheduleEntry(
                    loan_id=loan.id, due_date=due,
                    amount=interest_part, payment_type="interest",
                ))
        else:
            # Hela beloppet är ränta
            session.add(LoanScheduleEntry(
                loan_id=loan.id, due_date=due,
                amount=total, payment_type="interest",
            ))

    session.flush()

    # Kör matchern över befintliga transaktioner — loan_number i beskrivningen
    # kan matcha äldre betalningar också
    txs = session.query(Transaction).filter(Transaction.amount < 0).all()
    LoanMatcher(session).match_and_classify(txs)

    return loan
