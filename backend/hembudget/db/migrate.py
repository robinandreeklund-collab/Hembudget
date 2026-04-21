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


def _table_exists(engine: Engine, table: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
            {"n": table},
        ).first()
    return row is not None


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

    # accounts.pays_credit_account_id + account_number
    acc_cols = _columns(engine, "accounts")
    if "pays_credit_account_id" not in acc_cols:
        _add_column(
            engine,
            "accounts",
            "pays_credit_account_id INTEGER REFERENCES accounts(id)",
        )
        applied.append("accounts.pays_credit_account_id")
    if "account_number" not in acc_cols:
        _add_column(engine, "accounts", "account_number VARCHAR(40)")
        applied.append("accounts.account_number")
    if "opening_balance" not in acc_cols:
        _add_column(engine, "accounts", "opening_balance NUMERIC(14, 2)")
        applied.append("accounts.opening_balance")
    if "opening_balance_date" not in acc_cols:
        _add_column(engine, "accounts", "opening_balance_date DATE")
        applied.append("accounts.opening_balance_date")

    # upcoming_transactions — rika fakturafält + debitering
    if _table_exists(engine, "upcoming_transactions"):
        up_cols = _columns(engine, "upcoming_transactions")
        for col_name, col_sql in [
            ("invoice_number", "invoice_number VARCHAR(80)"),
            ("invoice_date", "invoice_date DATE"),
            ("ocr_reference", "ocr_reference VARCHAR(40)"),
            ("bankgiro", "bankgiro VARCHAR(20)"),
            ("plusgiro", "plusgiro VARCHAR(20)"),
            ("iban", "iban VARCHAR(40)"),
            ("debit_account_id", "debit_account_id INTEGER REFERENCES accounts(id)"),
            ("debit_date", "debit_date DATE"),
            ("autogiro", "autogiro BOOLEAN NOT NULL DEFAULT 0"),
        ]:
            if col_name not in up_cols:
                _add_column(engine, "upcoming_transactions", col_sql)
                applied.append(f"upcoming_transactions.{col_name}")

    # New tables (loans, loan_payments, upcoming_transactions) are created
    # by Base.metadata.create_all in auth routes; nothing to ALTER here.

    if applied:
        log.info("Schema migrations applied: %s", ", ".join(applied))
    return applied
