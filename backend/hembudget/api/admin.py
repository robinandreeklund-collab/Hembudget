from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..categorize.engine import CategorizationEngine
from ..categorize.rules import seed_categories_and_rules
from ..llm.client import LMStudioClient
from ..db.models import (
    Account,
    AuditLog,
    Budget,
    ChatMessage,
    Goal,
    Import,
    Loan,
    LoanPayment,
    LoanScheduleEntry,
    Rule,
    Scenario,
    Subscription,
    TaxEvent,
    Transaction,
    UpcomingTransaction,
)
from ..security.audit import log_action
from ..transfers.detector import TransferDetector
from .deps import db, require_auth

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_auth)])
log = logging.getLogger(__name__)

CONFIRMATION_PHRASE = "NOLLSTÄLL"


class ResetIn(BaseModel):
    confirm: str
    # Konton och lån bevaras alltid vid nollställning — de är dyra att sätta
    # upp (bankvision + lånescheman) och måste raderas manuellt var för sig.
    # Fälten finns kvar för bakåtkompatibilitet med frontend men ignoreras.
    keep_accounts: bool = True
    keep_rules: bool = False
    keep_loans: bool = True


@router.get("/stats")
def stats(session: Session = Depends(db)) -> dict:
    return {
        "accounts": session.query(Account).count(),
        "transactions": session.query(Transaction).count(),
        "imports": session.query(Import).count(),
        "budgets": session.query(Budget).count(),
        "rules": session.query(Rule).count(),
        "subscriptions": session.query(Subscription).count(),
        "scenarios": session.query(Scenario).count(),
        "chat_messages": session.query(ChatMessage).count(),
        "tax_events": session.query(TaxEvent).count(),
        "goals": session.query(Goal).count(),
        "loans": session.query(Loan).count(),
        "loan_payments": session.query(LoanPayment).count(),
    }


@router.post("/recategorize")
def recategorize(
    reseed: bool = True,
    session: Session = Depends(db),
) -> dict:
    """Blåser bort gamla seed-regler, re-seedar från koden, och kör om
    kategoriseringen på alla transaktioner som inte är användarverifierade
    (respekterar dina manuella rättningar)."""
    removed = 0
    if reseed:
        removed = session.query(Rule).filter(Rule.source == "seed").delete()
        session.flush()
        seed_categories_and_rules(session)
        session.flush()

    # Nollställ kategorin på icke-verifierade, icke-transfer transaktioner
    # så att engine.categorize_batch kör om dem från början
    txs = (
        session.query(Transaction)
        .filter(
            Transaction.user_verified.is_(False),
            Transaction.is_transfer.is_(False),
        )
        .all()
    )
    for t in txs:
        t.category_id = None
        t.ai_confidence = None
    session.flush()

    # Kör kategoriseringen igen (bara regler + historik — hoppa över LLM
    # här för att undvika långsamt LM Studio-anrop; användaren kan kalla
    # LLM manuellt via nästa import eller en annan knapp)
    engine = CategorizationEngine(session, llm=None)
    results = engine.categorize_batch(txs)
    engine.apply_results(txs, results)
    session.flush()

    categorized = sum(1 for r in results if r.category_id is not None)
    log_action(
        session, "recategorize",
        meta={"seed_rules_removed": removed, "txs_processed": len(txs),
              "categorized": categorized},
    )
    return {
        "seed_rules_removed": removed,
        "txs_processed": len(txs),
        "categorized": categorized,
        "still_uncategorized": len(txs) - categorized,
    }


@router.post("/scan-transfers")
def scan_transfers(
    date_tolerance_days: int = 3,
    amount_tolerance: float = 0.005,
    session: Session = Depends(db),
) -> dict:
    """Retroaktiv scan av alla okategoriserade transfers mellan egna konton."""
    result = TransferDetector(session).detect_internal_transfers(
        date_tolerance_days=date_tolerance_days,
        amount_tolerance=amount_tolerance,
    )
    log_action(
        session, "scan-transfers",
        meta={"pairs": result.pairs, "ambiguous": result.ambiguous},
    )
    return {
        "pairs": result.pairs,
        "ambiguous": result.ambiguous,
        "details": result.details,
    }


@router.post("/reset")
def reset(payload: ResetIn, session: Session = Depends(db)) -> dict:
    """Nollställ data — BEVARAR konton och lån alltid (användaren måste
    radera dem manuellt en i taget). Raderar transaktioner, budgetar,
    prenumerationer, chatt, kommande fakturor m.fl."""
    if payload.confirm != CONFIRMATION_PHRASE:
        raise HTTPException(400, f"Skriv '{CONFIRMATION_PHRASE}' för att bekräfta")

    deleted: dict[str, int] = {}

    # Lånekopplingar rensas (LoanPayment + matched_transaction_id nollas på
    # schedule) men själva Loan- och LoanScheduleEntry-raderna behålls.
    deleted[LoanPayment.__tablename__] = session.query(LoanPayment).delete()
    # Nollställ schema-raders matchning så de kan paras ihop på nytt efter
    # nästa import. Själva rad-innehållet (datum/belopp/typ) behålls.
    session.query(LoanScheduleEntry).update(
        {"matched_transaction_id": None, "matched_at": None}
    )

    for model in (
        ChatMessage,
        TaxEvent,
        UpcomingTransaction,
        Subscription,
        Transaction,
        Import,
        Budget,
        Scenario,
        Goal,
        AuditLog,
    ):
        deleted[model.__tablename__] = session.query(model).delete()

    if not payload.keep_rules:
        deleted[Rule.__tablename__] = session.query(Rule).delete()

    session.flush()

    # Re-seed default rules (categories are kept; seed function is idempotent)
    if not payload.keep_rules:
        seed_categories_and_rules(session)

    log_action(
        session, "reset",
        meta={
            "deleted": deleted,
            "keep_accounts": True,
            "keep_loans": True,
            "keep_rules": payload.keep_rules,
        },
    )
    log.warning("System reset performed: %s", deleted)
    return {"ok": True, "deleted": deleted}
