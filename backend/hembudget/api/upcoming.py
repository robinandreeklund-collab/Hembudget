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

from ..categorize.engine import CategorizationEngine
from ..config import settings
from ..db.models import Account, Category, Import, Transaction, UpcomingTransaction
from ..llm.client import LMStudioClient, LLMUnavailable
from ..transfers.detector import TransferDetector
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
        raise HTTPException(500, _vision_error_hint(exc)) from exc

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

    # Endast ännu-ej-matchade rader räknas — redan bokförda finns redan
    # i transaktionshistoriken och ska inte dubbelräknas.
    bills = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "bill",
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
            UpcomingTransaction.matched_transaction_id.is_(None),
        )
        .all()
    )
    incomes = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "income",
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
            UpcomingTransaction.matched_transaction_id.is_(None),
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
