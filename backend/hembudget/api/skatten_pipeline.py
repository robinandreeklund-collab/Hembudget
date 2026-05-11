"""Skatteverket-deklarations-pipeline · fördröjd verdict + utbetalningsvågor.

Flödet efter att eleven submittat:

  Submit (T=0)
    ├─ Mottagningsmail direkt i postlådan (released_at = utcnow)
    ├─ TaxYearReturn.status = 'submitted'
    │  besked_due_on = T+3 spel-dagar
    │
    ▼ 3 spel-dagar senare (en GET-burst som passerar besked_due_on)
  process_pending_besked() seedar slutskattebesked-mail
    ├─ Rudolf-AI verdict (godkand/avslag/kontroll)
    ├─ TaxYearReturn.status = 'besked_klar'
    │  verdict + payout_wave + payout_due_on
    │
    ▼ utbetalningsvåg-datum
  process_pending_payouts() bokför Transaction
    ├─ Återbäring: tx(income) på lönekonto, mail
    ├─ Kvarskatt: faktura med due_date 12 mars Y+2
    └─ TaxYearReturn.status = 'klar' (eller 'vantar_utbetalning' om
       påminnelse-mail om kvarskatt)

Allt seedas idempotent · varje pending row processas exakt en gång.
Cachat per request-burst (5 min) som övriga månadliga ticks.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session as SASession

from ..db.base import session_scope
from ..db.models import (
    Account, MailItem, TaxDeduction, TaxYearReturn, Transaction,
)
from .skatten_window import (
    SKV_KVARSKATT_DUE, SKV_LATE_FEE_KR, SKV_REFUND_WAVE_1, SKV_REFUND_WAVE_2,
)


log = logging.getLogger(__name__)


# === Konstanter ===

# Hur många SPEL-dagar Skatteverket "granskar" innan besked.
# Verkligheten ~3 veckor. I spel-tid (1h real = 1 vecka) ger 3 spel-dagar
# = ca 25 min real-tid — tillräckligt för att eleven hinner glömma att
# hen submittade och får en överraskning.
BESKED_DELAY_SPEL_DAGAR = 3


# === Submit-tid logik · sätter ut alla framtida steg ===


def setup_after_submit(
    s: SASession,
    *,
    tax_return: TaxYearReturn,
    today_game: date,
) -> dict:
    """Kallas direkt efter submit_tax_year() har skrivit raden.
    Skriver besked_due_on + payout_due_on + payout_wave på raden,
    skapar mottagningsmail i postlådan (direkt synligt) och
    förseningsavgift om submit skedde efter 4 maj.

    Returnerar en dict med pedagogiskt klartext-summary för UI.
    """
    tax_return.submitted_on = today_game
    tax_return.status = "submitted"
    tax_return.verdict = None
    tax_return.besked_due_on = today_game + timedelta(
        days=BESKED_DELAY_SPEL_DAGAR,
    )

    # Vilken våg eleven hamnar i baserat på submit-datum
    digital_deadline = date(today_game.year, 3, 31)
    final_deadline = date(today_game.year, 5, 4)

    if today_game <= digital_deadline:
        tax_return.payout_wave = 1
        tax_return.payout_due_on = date(today_game.year, *SKV_REFUND_WAVE_1)
        wave_msg = "Du hamnar i utbetalningsvåg 1 (7-10 april)."
    elif today_game <= final_deadline:
        tax_return.payout_wave = 2
        tax_return.payout_due_on = date(today_game.year, *SKV_REFUND_WAVE_2)
        wave_msg = "Du hamnar i utbetalningsvåg 2 (9-12 juni)."
    else:
        # Sen inlämning · förseningsavgift + senare våg (juni nästa år)
        tax_return.payout_wave = 0
        tax_return.payout_due_on = None
        tax_return.late_fee = Decimal(str(SKV_LATE_FEE_KR))
        wave_msg = (
            f"Sen inlämning · förseningsavgift {SKV_LATE_FEE_KR} kr. "
            "Eventuell återbäring skjuts upp till nästa juni-våg."
        )

    # Mottagningsmail · direkt synligt i postlådan
    case_no = (
        f"SKV-{tax_return.year}-{tax_return.tenant_id or 0}-"
        f"{tax_return.id:03d}"
    )
    s.add(MailItem(
        sender="Skatteverket",
        sender_short="SKV",
        sender_kind="agency",
        sender_meta=f"Mottagning · Deklaration {tax_return.year}",
        mail_type="authority",
        subject=f"Mottagningskvitto · Deklaration {tax_return.year}",
        body_meta=f"Ärendenr {case_no}",
        body=(
            f"Hej! Vi har mottagit din deklaration för inkomstår "
            f"{tax_return.year}.\n\n"
            f"Ärendenummer: {case_no}\n"
            f"Mottagen: {today_game.isoformat()} (spel-tid)\n\n"
            f"Vad händer nu?\n"
            f"• Granskning klar inom 3 spel-dagar (~25 min real-tid).\n"
            f"• Slutskattebesked landar i postlådan när granskningen "
            f"är klar (cirka {tax_return.besked_due_on.isoformat()}).\n"
            f"• {wave_msg}\n\n"
            f"Med vänliga hälsningar,\n"
            f"Skatteverket"
        ),
        amount=None,
        due_date=None,
        status="unhandled",
        released_at=None,  # synlig direkt
    ))
    s.flush()

    return {
        "status": tax_return.status,
        "besked_due_on": tax_return.besked_due_on.isoformat(),
        "payout_wave": tax_return.payout_wave,
        "payout_due_on": (
            tax_return.payout_due_on.isoformat()
            if tax_return.payout_due_on else None
        ),
        "late_fee": float(tax_return.late_fee or 0),
        "wave_message": wave_msg,
        "case_no": case_no,
    }


# === Besked-fas · släpps 3 spel-dagar efter submit ===


def _rudolf_verdict_for(s: SASession, *, year: int) -> dict:
    """Förenklad Rudolf-AI lokalt så besked-fasen kan köras utan
    Anthropic-API. Returnerar {verdict, message, score, flagged}.

    Heuristik: rese-avdrag > 15 000 kr utan beskrivning → 'kontroll',
    > 30 000 → 'avslag'. Annars 'godkand'.
    """
    deductions = (
        s.query(TaxDeduction)
        .filter(TaxDeduction.year == year)
        .all()
    )
    flagged = []
    verdict = "godkand"
    score = 95
    msg = "Tack för din deklaration. Allt ser rätt ut."
    for d in deductions:
        if d.kind == "rese":
            if d.amount > Decimal("30000"):
                verdict = "avslag"
                score = 30
                flagged.append({
                    "category": "rese",
                    "amount": float(d.amount),
                    "reason": (
                        "Reseavdraget överstiger 30 000 kr · kräver "
                        "körjournal eller kollektivtrafik-kvitto."
                    ),
                })
                msg = (
                    "Reseavdraget är för stort utan dokumentation. "
                    "Du behöver komplettera med körjournal/kvitton."
                )
            elif d.amount > Decimal("15000") and not d.description:
                verdict = "kontroll"
                score = max(score, 60)
                flagged.append({
                    "category": "rese",
                    "amount": float(d.amount),
                    "reason": (
                        "Reseavdrag > 15 000 kr utan beskrivning · "
                        "vi vill se hur du räknat (km × 18,5 öre)."
                    ),
                })
                msg = (
                    "Vi behöver mer info om reseavdraget. Komplettera "
                    "med beskrivning och försök igen."
                )
    return {
        "verdict": verdict,
        "message": msg,
        "score": score,
        "flagged": flagged,
    }


def process_pending_besked(
    s: SASession, *, today_game: date,
) -> int:
    """Hitta TaxYearReturn med status=submitted där besked_due_on <=
    today_game. Genererar slutskattebesked-mail + uppdaterar status.

    Returnerar antal raders som processats.
    """
    pending = (
        s.query(TaxYearReturn)
        .filter(
            TaxYearReturn.status == "submitted",
            TaxYearReturn.besked_due_on.isnot(None),
            TaxYearReturn.besked_due_on <= today_game,
        )
        .all()
    )
    n = 0
    for ret in pending:
        try:
            rudolf = _rudolf_verdict_for(s, year=ret.year)
            ret.verdict = rudolf["verdict"]

            if rudolf["verdict"] == "godkand":
                # Lås raden, vänta på utbetalningsvåg
                ret.status = (
                    "klar" if float(ret.diff) == 0
                    else "vantar_utbetalning"
                )
            else:
                # avslag/kontroll · eleven måste komplettera
                # Lås upp deklarationen så hen kan ändra avdrag.
                ret.status = "besked_klar"  # i UI: omarbeta
                ret.locked = False

            # Slutskattebesked-mail
            verdict_label = {
                "godkand": "GODKÄND",
                "avslag": "AVSLAG · komplettera",
                "kontroll": "KONTROLL · komplettera",
            }[rudolf["verdict"]]
            diff = float(ret.diff)
            if diff > 0:
                belopp_text = (
                    f"Skatteåterbäring: {int(diff):,} kr".replace(",", " ")
                )
                if rudolf["verdict"] == "godkand":
                    next_text = (
                        f"Utbetalning sker "
                        f"{ret.payout_due_on.isoformat() if ret.payout_due_on else '?'} "
                        f"(våg {ret.payout_wave})."
                    )
                else:
                    next_text = (
                        "Pga avslag/kontroll: omarbeta deklarationen "
                        "och skicka in igen via Skatteverket-aktören."
                    )
            elif diff < 0:
                belopp_text = (
                    f"Kvarskatt: {int(-diff):,} kr".replace(",", " ")
                )
                if rudolf["verdict"] == "godkand":
                    kvarskatt_due = date(
                        ret.year + 2, *SKV_KVARSKATT_DUE,
                    )
                    next_text = (
                        f"Kvarskatten förfaller "
                        f"{kvarskatt_due.isoformat()} (12 mars nästa år). "
                        "Faktura med autogiro-möjlighet kommer separat."
                    )
                else:
                    next_text = (
                        "Pga avslag/kontroll: omarbeta deklarationen "
                        "och skicka in igen."
                    )
            else:
                belopp_text = "Skatten går jämnt upp · varken kvar eller åter."
                next_text = "Ärendet är klart."

            late_fee_text = (
                f"\n⚠ Förseningsavgift: {int(ret.late_fee)} kr "
                "(inlämning efter 4 maj)\n"
                if ret.late_fee and ret.late_fee > 0 else ""
            )

            s.add(MailItem(
                sender="Skatteverket",
                sender_short="SKV",
                sender_kind="agency",
                sender_meta=f"Slutskattebesked · {ret.year}",
                mail_type="authority",
                subject=(
                    f"Slutskattebesked · {ret.year} · {verdict_label}"
                ),
                body_meta=belopp_text,
                body=(
                    f"Hej. Här är ditt slutskattebesked för "
                    f"{ret.year}.\n\n"
                    f"Status: {verdict_label}\n"
                    f"{belopp_text}\n"
                    f"{late_fee_text}\n"
                    f"Rudolf (handläggare) säger:\n"
                    f"{rudolf['message']}\n\n"
                    f"{next_text}\n\n"
                    f"Hälsningar,\n"
                    f"Skatteverket"
                ),
                amount=(
                    Decimal(str(abs(diff))) if diff != 0 else None
                ),
                due_date=None,
                status="unhandled",
                released_at=None,
            ))
            n += 1
        except Exception:
            log.exception(
                "process_pending_besked: misslyckades för "
                "tax_return.id=%s",
                ret.id,
            )
    if n > 0:
        s.flush()
    return n


# === Utbetalnings-/inbetalningsfas vid våg-datum ===


def _get_lonekonto(s: SASession) -> Optional[Account]:
    """Hämta lönekontot från scope-DB · första kontot med type='checking'
    (matchar konventionen i monthly_engine/scope_seed.py där lönekontot
    seedas som checking-typ)."""
    acc = (
        s.query(Account)
        .filter(Account.type == "checking")
        .order_by(Account.id.asc())
        .first()
    )
    return acc


def process_pending_payouts(
    s: SASession, *, today_game: date,
) -> int:
    """Hitta TaxYearReturn där:
      - status = vantar_utbetalning
      - payout_due_on <= today_game
      - verdict = godkand
    Bokför återbäring/kvarskatt på lönekontot + skickar bekräftelse-mail.
    """
    pending = (
        s.query(TaxYearReturn)
        .filter(
            TaxYearReturn.status == "vantar_utbetalning",
            TaxYearReturn.verdict == "godkand",
            TaxYearReturn.payout_due_on.isnot(None),
            TaxYearReturn.payout_due_on <= today_game,
        )
        .all()
    )
    n = 0
    for ret in pending:
        try:
            diff = Decimal(str(ret.diff or 0))
            acc = _get_lonekonto(s)
            if acc is None:
                log.warning(
                    "process_pending_payouts: lönekonto saknas, kan "
                    "inte boka tx för tax_return.id=%s",
                    ret.id,
                )
                continue

            if diff > 0:
                # Återbäring · positiv tx till lönekontot. hash genereras
                # deterministiskt så samma våg-utbetalning inte
                # dubbel-bokförs vid eventuell retry (UniqueConstraint
                # på (tenant_id, hash) i scope-DB).
                import hashlib as _h
                desc = (
                    f"Skatteåterbäring {ret.year} · "
                    f"våg {ret.payout_wave}"
                )
                tx_hash = _h.sha256(
                    f"skv-aterbaring-{ret.id}-{ret.payout_due_on.isoformat()}-{diff}".encode()
                ).hexdigest()
                s.add(Transaction(
                    account_id=acc.id,
                    date=ret.payout_due_on,
                    amount=diff,
                    raw_description=desc,
                    hash=tx_hash,
                    is_transfer=False,
                    released_at=None,
                ))
                # Glatt mail
                s.add(MailItem(
                    sender="Skatteverket",
                    sender_short="SKV",
                    sender_kind="agency",
                    sender_meta=f"Återbäring · {ret.year}",
                    mail_type="authority",
                    subject=(
                        f"Skatteåterbäring utbetald · {int(diff)} kr"
                    ),
                    body_meta=(
                        f"Insatt på lönekontot {ret.payout_due_on.isoformat()}"
                    ),
                    body=(
                        f"Idag har {int(diff)} kr betalats ut till ditt "
                        f"lönekonto.\n\nAvser inkomstår {ret.year}. "
                        f"Tack för att du deklarerade i tid.\n\n"
                        f"Hälsningar,\nSkatteverket"
                    ),
                    amount=diff,
                    due_date=None,
                    status="unhandled",
                    released_at=None,
                ))
                ret.status = "klar"
            elif diff < 0:
                # Kvarskatt · skapa faktura-mail med autogiro
                # Förfallodatum 12 mars Y+2 (slutskattebesked-året + 1)
                kvarskatt_due = date(ret.year + 2, *SKV_KVARSKATT_DUE)
                s.add(MailItem(
                    sender="Skatteverket",
                    sender_short="SKV",
                    sender_kind="agency",
                    sender_meta=f"Kvarskatt · {ret.year}",
                    mail_type="invoice",
                    subject=(
                        f"Kvarskatt · {int(-diff)} kr · "
                        f"förfaller {kvarskatt_due.isoformat()}"
                    ),
                    body_meta=(
                        f"Betala via autogiro eller manuellt senast "
                        f"{kvarskatt_due.isoformat()}"
                    ),
                    body=(
                        f"Hej.\n\nDu har kvarskatt på "
                        f"{int(-diff)} kr för inkomstår {ret.year}. "
                        f"Förfallodatum: {kvarskatt_due.isoformat()}. "
                        f"Sen betalning ger ränta + förseningsavgift.\n\n"
                        f"Använd OCR-numret nedan vid manuell betalning.\n"
                        f"OCR: {ret.year}{ret.id:08d}\n\n"
                        f"Hälsningar,\nSkatteverket"
                    ),
                    amount=-diff,
                    due_date=kvarskatt_due,
                    status="unhandled",
                    released_at=None,
                ))
                # Status flippar till klar när eleven betalar (annan flow)
                ret.status = "klar"
            else:
                ret.status = "klar"

            n += 1
        except Exception:
            log.exception(
                "process_pending_payouts: misslyckades för "
                "tax_return.id=%s",
                ret.id,
            )
    if n > 0:
        s.flush()
    return n


# === Auto-process · cachad per request-burst ===


_PROCESS_CACHE: dict[int, float] = {}
_PROCESS_TTL = 60.0  # 1 min · billigt nog att köra ofta


def process_for_student_if_due(student_id: int) -> dict:
    """Wrapper som kallas från GET /v2/skatten och GET /v2/postladan-listor.
    Kör besked + payout-pipelines för aktuell elev. Idempotent + cachad.
    """
    import time as _t
    last = _PROCESS_CACHE.get(student_id, 0.0)
    if _t.time() - last < _PROCESS_TTL:
        return {"cached": True, "besked": 0, "payouts": 0}
    _PROCESS_CACHE[student_id] = _t.time()

    try:
        from ..business.game_clock import current_game_date_for_student
        from ..school.engines import (
            scope_context as _sctx,
            scope_for_student as _sfs,
            master_session,
        )
        from ..school.models import Student

        today_game = current_game_date_for_student(student_id)

        with master_session() as ms:
            stu = ms.get(Student, student_id)
            if stu is None:
                return {"besked": 0, "payouts": 0}
            scope_key = _sfs(stu)

        with _sctx(scope_key):
            with session_scope() as s:
                besked = process_pending_besked(s, today_game=today_game)
                payouts = process_pending_payouts(s, today_game=today_game)
        return {"besked": besked, "payouts": payouts}
    except Exception:
        log.exception(
            "process_for_student_if_due: failed för student=%s",
            student_id,
        )
        return {"besked": 0, "payouts": 0}
