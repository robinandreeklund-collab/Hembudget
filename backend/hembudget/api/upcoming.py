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
from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import Account, Category, Transaction, UpcomingTransaction
from ..llm.client import LMStudioClient, LLMUnavailable
from .deps import db, llm_client, require_auth

log = logging.getLogger(__name__)

router = APIRouter(prefix="/upcoming", tags=["upcoming"], dependencies=[Depends(require_auth)])

PDF_MAGIC = b"%PDF"
MAX_PDF_PAGES = 5     # inte fler sidor än så till vision-modellen


def _rasterize_pdf(pdf_bytes: bytes, max_pages: int = MAX_PDF_PAGES) -> list[bytes]:
    """Renderar PDF-sidor till PNG. Returnerar PNG-bytes per sida."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise HTTPException(
            500,
            "pypdfium2 saknas — kör 'pip install -e .[dev]' i backend/",
        ) from exc

    pdf = pdfium.PdfDocument(pdf_bytes)
    if len(pdf) == 0:
        raise HTTPException(400, "PDF:en innehåller inga sidor")

    images: list[bytes] = []
    for i in range(min(len(pdf), max_pages)):
        page = pdf[i]
        # scale=2.0 ≈ 144 DPI — bra balans mellan OCR-läsbarhet och filstorlek
        pil_image = page.render(scale=2.0).to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG", optimize=True)
        images.append(buf.getvalue())
    return images


def _file_to_images(content: bytes, content_type: str | None) -> tuple[list[bytes], str]:
    """Returnera (lista med bild-bytes, mime-type för varje bild).
    Bilder skickas direkt; PDF rasteriseras till PNG per sida.
    """
    if content.startswith(PDF_MAGIC) or (content_type or "").lower() == "application/pdf":
        return _rasterize_pdf(content), "image/png"
    return [content], content_type or "image/png"


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


@router.get("/", response_model=list[UpcomingOut])
def list_upcoming(
    kind: Optional[str] = None,
    only_future: bool = True,
    session: Session = Depends(db),
) -> list[UpcomingTransaction]:
    q = session.query(UpcomingTransaction)
    if kind:
        q = q.filter(UpcomingTransaction.kind == kind)
    if only_future:
        q = q.filter(UpcomingTransaction.expected_date >= date.today())
    return q.order_by(UpcomingTransaction.expected_date.asc()).all()


@router.post("/", response_model=UpcomingOut)
def create_upcoming(payload: UpcomingIn, session: Session = Depends(db)) -> UpcomingTransaction:
    if payload.kind not in ("bill", "income"):
        raise HTTPException(400, "kind must be 'bill' or 'income'")
    u = UpcomingTransaction(**payload.model_dump())
    session.add(u)
    session.flush()
    return u


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

    try:
        parsed = llm.complete_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Du tolkar svensk text om kommande fakturor eller löner. "
                        "Returnera JSON enligt schemat. Om datum saknas, sätt sista "
                        "dagen i nästa månad. Om det är en lön/inkomst, sätt owner till "
                        "personens namn. Fält som inte nämns → null."
                    ),
                },
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
    return u


@router.post("/parse-invoice-image", response_model=UpcomingOut)
async def parse_invoice_image(
    file: UploadFile = File(...),
    kind: str = Form("bill"),
    session: Session = Depends(db),
    llm: LMStudioClient = Depends(llm_client),
) -> UpcomingTransaction:
    """Skicka en faktura (PNG/JPG/PDF) till en vision-kapabel modell i LM Studio
    (t.ex. Qwen2.5-VL, Llava, Pixtral) för automatisk extraktion av
    mottagare, belopp och förfallodag. PDF:er rasteriseras till PNG per sida
    först (upp till 5 sidor) eftersom vision-modeller bara tar bilder.
    """
    if not llm.is_alive():
        raise HTTPException(503, "LM Studio är inte tillgänglig")

    # Spara originalfilen lokalt för audit
    content = await file.read()
    if not content:
        raise HTTPException(400, "Tom fil")

    invoice_dir = settings.data_dir / "invoices"
    invoice_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    original_path = invoice_dir / f"{ts}_{file.filename or 'invoice'}"
    original_path.write_bytes(content)

    # Konvertera till lista av bild-bytes (PDF → en bild per sida)
    try:
        images, img_mime = _file_to_images(content, file.content_type)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("PDF rasterization failed")
        raise HTTPException(400, f"Kunde inte läsa filen: {exc}") from exc

    # Bygg multi-image-payload till vision-modellen
    user_content: list[dict] = [
        {
            "type": "text",
            "text": (
                "Extrahera ALLA betalningsrelaterade uppgifter du kan hitta från "
                "denna svenska faktura. Om flera sidor visas, titta på alla och "
                "slå samman informationen. Om något fält inte syns, använd null."
            ),
        }
    ]
    for img_bytes in images:
        b64 = base64.b64encode(img_bytes).decode("ascii")
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{img_mime};base64,{b64}"},
        })

    schema = _invoice_schema()

    try:
        parsed = llm.complete_json(
            [{"role": "system", "content": _vision_system_prompt()},
             {"role": "user", "content": user_content}],
            schema=schema,
            temperature=0.0,
        )
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        log.exception("Vision parse failed")
        raise HTTPException(
            500,
            f"Modellen kunde inte tolka bilden — byt till en vision-kapabel modell "
            f"i LM Studio (t.ex. Qwen2.5-VL). Fel: {exc}",
        ) from exc

    u = _build_upcoming_from_parsed(parsed, kind=kind, source="vision_ai",
                                    source_image_path=str(original_path),
                                    session=session)
    session.add(u)
    session.flush()
    return u


def _invoice_schema() -> dict:
    """JSON-schema som tvingar vision-modellen att returnera rika data."""
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
        },
        "required": ["name", "amount", "expected_date"],
    }


def _vision_system_prompt() -> str:
    return (
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
        "- Om ett fält inte syns, returnera null."
    )


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
    start = date(year, mon, 1)
    if mon == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, mon + 1, 1)

    bills = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "bill",
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
        )
        .all()
    )
    incomes = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "income",
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
        )
        .all()
    )

    bills_total = sum((b.amount for b in bills), Decimal("0"))
    income_total = sum((i.amount for i in incomes), Decimal("0"))

    # Fasta kostnader = snitt av senaste 3 månadernas utgifter
    # (exkl. transfers, exkl. redan matchade kommande fakturor så de inte
    # räknas dubbelt när de dyker upp som riktiga transaktioner nästa gång)
    from sqlalchemy import func as sql_func

    # Räkna ut lookback-fönstret korrekt över årsgräns
    lookback_month = mon - 3
    lookback_year = year
    if lookback_month <= 0:
        lookback_month += 12
        lookback_year -= 1
    lookback_start = date(lookback_year, lookback_month, 1)

    monthly_exp = (
        session.query(
            sql_func.strftime("%Y-%m", Transaction.date).label("m"),
            sql_func.sum(Transaction.amount).label("tot"),
        )
        .filter(
            Transaction.amount < 0,
            Transaction.is_transfer.is_(False),
            Transaction.date >= lookback_start,
            Transaction.date < start,
        )
        .group_by("m")
        .all()
    )

    if monthly_exp:
        avg_expenses = abs(sum(float(t) for _, t in monthly_exp)) / len(monthly_exp)
    else:
        avg_expenses = 0.0

    available = float(income_total) - float(bills_total) - avg_expenses

    owners: dict[str, Decimal] = {}
    for i in incomes:
        key = i.owner or "Okänd"
        owners[key] = owners.get(key, Decimal("0")) + i.amount

    return {
        "month": month,
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
            "avg_fixed_expenses": round(avg_expenses, 2),
            "available_to_split": round(available, 2),
        },
        "split": {
            "ratio": split_ratio,
            "per_person_share": round(available * split_ratio, 2),
            "per_person_other": round(available * (1 - split_ratio), 2),
        },
        "income_by_owner": {k: float(v) for k, v in owners.items()},
    }
