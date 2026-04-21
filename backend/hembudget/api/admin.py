from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..categorize.rules import seed_categories_and_rules
from ..db.models import (
    Account,
    AuditLog,
    Budget,
    ChatMessage,
    Goal,
    Import,
    Rule,
    Scenario,
    Subscription,
    TaxEvent,
    Transaction,
)
from ..security.audit import log_action
from .deps import db, require_auth

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_auth)])
log = logging.getLogger(__name__)

CONFIRMATION_PHRASE = "NOLLSTÄLL"


class ResetIn(BaseModel):
    confirm: str
    keep_accounts: bool = False
    keep_rules: bool = False


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
    }


@router.post("/reset")
def reset(payload: ResetIn, session: Session = Depends(db)) -> dict:
    if payload.confirm != CONFIRMATION_PHRASE:
        raise HTTPException(400, f"Skriv '{CONFIRMATION_PHRASE}' för att bekräfta")

    # Delete in FK-safe order
    deleted: dict[str, int] = {}
    for model in (
        ChatMessage,
        TaxEvent,
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

    if not payload.keep_accounts:
        deleted[Account.__tablename__] = session.query(Account).delete()

    session.flush()

    # Re-seed default rules (categories are kept; seed function is idempotent)
    if not payload.keep_rules:
        seed_categories_and_rules(session)

    log_action(session, "reset", meta={"deleted": deleted, "keep_accounts": payload.keep_accounts,
                                       "keep_rules": payload.keep_rules})
    log.warning("System reset performed: %s", deleted)
    return {"ok": True, "deleted": deleted}
