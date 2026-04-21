from __future__ import annotations

import hashlib
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..categorize.engine import CategorizationEngine
from ..db.models import Account, Import, Transaction
from ..llm.client import LMStudioClient
from ..loans.matcher import LoanMatcher
from ..parsers import detect_parser, parser_for_bank
from ..transfers.detector import TransferDetector
from ..upcoming_match import UpcomingMatcher
from ..upcoming_match.materializer import UpcomingMaterializer
from .deps import db, llm_client, require_auth

router = APIRouter(prefix="/import", tags=["import"], dependencies=[Depends(require_auth)])
log = logging.getLogger(__name__)


@router.post("/csv")
async def import_csv(
    account_id: int = Form(...),
    bank: str | None = Form(default=None),
    file: UploadFile = File(...),
    session: Session = Depends(db),
    llm: LMStudioClient = Depends(llm_client),
) -> dict:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")

    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")

    parser = parser_for_bank(bank, content) if bank else detect_parser(content)
    if parser is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Unknown CSV format; specify bank= explicitly",
        )

    sha = hashlib.sha256(content).hexdigest()
    # Skip re-import if same file already processed
    dup = session.query(Import).filter(Import.sha256 == sha).first()
    if dup:
        return {"status": "duplicate", "import_id": dup.id, "rows": dup.row_count}

    try:
        raw_rows = parser.parse(content)
    except Exception as exc:
        log.exception("parser failed")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Parser error: {exc}") from exc

    imp = Import(filename=file.filename or "upload.csv", bank=parser.bank, sha256=sha,
                 row_count=len(raw_rows))
    session.add(imp)
    session.flush()

    new_transactions: list[Transaction] = []
    existing_hashes = {
        h for (h,) in session.query(Transaction.hash).filter(
            Transaction.account_id == account_id
        ).all()
    }
    for raw in raw_rows:
        h = raw.stable_hash(account_id)
        if h in existing_hashes:
            continue
        existing_hashes.add(h)
        tx = Transaction(
            account_id=account_id,
            date=raw.date,
            amount=Decimal(str(raw.amount)),
            currency=raw.currency,
            raw_description=raw.description,
            source_file_id=imp.id,
            hash=h,
        )
        new_transactions.append(tx)
        session.add(tx)

    session.flush()

    # Categorize
    engine = CategorizationEngine(session, llm=llm)
    results = engine.categorize_batch(new_transactions)
    engine.apply_results(new_transactions, results)
    session.flush()

    # Detect transfers (credit-card payments etc.) to avoid double-counting
    detector = TransferDetector(session)
    transfer_result = detector.detect_and_link(new_transactions)

    # Retroactive pass over all still-unpaired internal transactions.
    # Catches own-account transfers (lönekonto → hushållskonto) that only
    # become visible once both sides are imported.
    internal = detector.detect_internal_transfers()

    # Link matching expenses to registered loans (bolåneränta / amortering)
    loan_result = LoanMatcher(session).match_and_classify(new_transactions)

    # Matcha planerade UpcomingTransaction mot de nya riktiga rader så
    # fakturor markeras som "bokförda" och forecasten inte dubbelräknar.
    upcoming_matched = UpcomingMatcher(session).match(new_transactions)

    # Materialisera kommande lån och prenumerationer — idempotent, rör inte
    # redan materialiserade rader. Gör Dashboard:s "upcoming"-vy
    # självuppdaterande efter varje import.
    mat_result = UpcomingMaterializer(session).run()
    session.flush()

    return {
        "status": "ok",
        "import_id": imp.id,
        "bank": parser.bank,
        "rows_parsed": len(raw_rows),
        "rows_inserted": len(new_transactions),
        "categorized": sum(
            1 for r, tx in zip(results, new_transactions)
            if r.category_id is not None and not tx.is_transfer
        ),
        "transfers_marked": transfer_result.marked,
        "transfers_paired": transfer_result.paired,
        "internal_pairs": internal.pairs,
        "internal_ambiguous": internal.ambiguous,
        "loan_payments_linked": loan_result.linked,
        "loan_payments_unclassified": loan_result.unclassified,
        "upcoming_matched": upcoming_matched,
        "upcoming_materialized_loans": mat_result.loan_upcoming_created,
        "upcoming_materialized_subs": mat_result.sub_upcoming_created,
    }
