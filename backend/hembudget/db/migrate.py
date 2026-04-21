"""In-place schema migrations for SQLite.

Kör alla vid startup efter `create_all()`. Nya kolumner läggs till om de
saknas. Idempotent — säker att köra flera gånger.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)


def _columns(engine: Engine, table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _add_column(engine: Engine, table: str, column_sql: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_sql}"))


def run_migrations(engine: Engine) -> list[str]:
    """Apply all pending migrations. Returns list of applied changes."""
    applied: list[str] = []

    # transactions.is_transfer
    tx_cols = _columns(engine, "transactions")
    if "is_transfer" not in tx_cols:
        _add_column(engine, "transactions", "is_transfer BOOLEAN NOT NULL DEFAULT 0")
        applied.append("transactions.is_transfer")
    if "transfer_pair_id" not in tx_cols:
        _add_column(
            engine,
            "transactions",
            "transfer_pair_id INTEGER REFERENCES transactions(id)",
        )
        applied.append("transactions.transfer_pair_id")

    # accounts.pays_credit_account_id
    acc_cols = _columns(engine, "accounts")
    if "pays_credit_account_id" not in acc_cols:
        _add_column(
            engine,
            "accounts",
            "pays_credit_account_id INTEGER REFERENCES accounts(id)",
        )
        applied.append("accounts.pays_credit_account_id")

    # New tables (loans, loan_payments) are created by Base.metadata.create_all
    # in auth routes; nothing to ALTER here.

    if applied:
        log.info("Schema migrations applied: %s", ", ".join(applied))
    return applied
