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
    if "cardholder" not in tx_cols:
        _add_column(engine, "transactions", "cardholder VARCHAR(80)")
        applied.append("transactions.cardholder")

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
    if "credit_limit" not in acc_cols:
        _add_column(engine, "accounts", "credit_limit NUMERIC(14, 2)")
        applied.append("accounts.credit_limit")
    if "bankgiro" not in acc_cols:
        _add_column(engine, "accounts", "bankgiro VARCHAR(20)")
        applied.append("accounts.bankgiro")
    if "card_last_digits" not in acc_cols:
        _add_column(engine, "accounts", "card_last_digits VARCHAR(4)")
        applied.append("accounts.card_last_digits")
    if "parent_account_id" not in acc_cols:
        _add_column(
            engine, "accounts",
            "parent_account_id INTEGER REFERENCES accounts(id)",
        )
        applied.append("accounts.parent_account_id")
    if "incognito" not in acc_cols:
        _add_column(
            engine, "accounts",
            "incognito BOOLEAN NOT NULL DEFAULT 0",
        )
        applied.append("accounts.incognito")

    # upcoming_payments junction (om inte skapad via create_all)
    if not _table_exists(engine, "upcoming_payments"):
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE upcoming_payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    upcoming_id INTEGER NOT NULL REFERENCES upcoming_transactions(id) ON DELETE CASCADE,
                    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_upcoming_payment UNIQUE (upcoming_id, transaction_id)
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_upcoming_payments_upcoming_id "
                "ON upcoming_payments(upcoming_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_upcoming_payments_transaction_id "
                "ON upcoming_payments(transaction_id)"
            ))
        applied.append("upcoming_payments (table)")

    # Migrera existerande matched_transaction_id till upcoming_payments
    # så vi har EN källa av sanning (ingen dubbelräkning)
    if _table_exists(engine, "upcoming_payments"):
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT OR IGNORE INTO upcoming_payments (upcoming_id, transaction_id)
                SELECT id, matched_transaction_id
                FROM upcoming_transactions
                WHERE matched_transaction_id IS NOT NULL
            """))

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

    # loan_payments: transaction_id måste få ha två rader per transaktion
    # (ränta + amortering i en och samma bankpost). Gammal UNIQUE-constraint
    # stoppar detta — byggs om till composite unique på (transaction_id,
    # payment_type). SQLite stödjer inte ALTER DROP CONSTRAINT så vi gör
    # table-rebuild.
    if _table_exists(engine, "loan_payments"):
        with engine.begin() as conn:
            # Hitta alla unique-index på tabellen
            idx_rows = conn.execute(
                text("PRAGMA index_list(loan_payments)")
            ).fetchall()
            has_standalone_tx_unique = False
            has_composite = False
            for idx in idx_rows:
                # columns: seq, name, unique, origin, partial
                if idx[2] != 1:
                    continue
                idx_name = idx[1]
                info = conn.execute(
                    text(f"PRAGMA index_info({idx_name})")
                ).fetchall()
                cols = [r[2] for r in info]
                if cols == ["transaction_id"]:
                    has_standalone_tx_unique = True
                if set(cols) == {"transaction_id", "payment_type"}:
                    has_composite = True

            if has_standalone_tx_unique and not has_composite:
                # Rebuild utan standalone unique, med composite
                conn.execute(text("PRAGMA foreign_keys = OFF"))
                conn.execute(text(
                    """
                    CREATE TABLE loan_payments_new (
                        id INTEGER PRIMARY KEY,
                        loan_id INTEGER NOT NULL REFERENCES loans(id),
                        transaction_id INTEGER NOT NULL REFERENCES transactions(id),
                        date DATE NOT NULL,
                        amount NUMERIC(14, 2) NOT NULL,
                        payment_type VARCHAR(20) NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT uq_loan_payment_tx_type
                            UNIQUE (transaction_id, payment_type)
                    )
                    """
                ))
                conn.execute(text(
                    "INSERT INTO loan_payments_new "
                    "(id, loan_id, transaction_id, date, amount, "
                    "payment_type, created_at) "
                    "SELECT id, loan_id, transaction_id, date, amount, "
                    "payment_type, created_at FROM loan_payments"
                ))
                conn.execute(text("DROP TABLE loan_payments"))
                conn.execute(text(
                    "ALTER TABLE loan_payments_new RENAME TO loan_payments"
                ))
                conn.execute(text(
                    "CREATE INDEX ix_loan_payments_loan_id "
                    "ON loan_payments(loan_id)"
                ))
                conn.execute(text(
                    "CREATE INDEX ix_loan_payments_transaction_id "
                    "ON loan_payments(transaction_id)"
                ))
                conn.execute(text("PRAGMA foreign_keys = ON"))
                applied.append("loan_payments.transaction_id drop unique → composite")

    # loan_schedule_entries: släpp unique på matched_transaction_id av
    # samma skäl (en bankpost matchar både amort + ränta). SQLite kräver
    # table-rebuild.
    if _table_exists(engine, "loan_schedule_entries"):
        with engine.begin() as conn:
            idx_rows = conn.execute(
                text("PRAGMA index_list(loan_schedule_entries)")
            ).fetchall()
            has_tx_unique = False
            for idx in idx_rows:
                if idx[2] != 1:
                    continue
                idx_name = idx[1]
                info = conn.execute(
                    text(f"PRAGMA index_info({idx_name})")
                ).fetchall()
                if [r[2] for r in info] == ["matched_transaction_id"]:
                    has_tx_unique = True
                    break

            if has_tx_unique:
                conn.execute(text("PRAGMA foreign_keys = OFF"))
                conn.execute(text(
                    """
                    CREATE TABLE loan_schedule_entries_new (
                        id INTEGER PRIMARY KEY,
                        loan_id INTEGER NOT NULL REFERENCES loans(id),
                        due_date DATE NOT NULL,
                        amount NUMERIC(12, 2) NOT NULL,
                        payment_type VARCHAR(20) NOT NULL,
                        matched_transaction_id INTEGER REFERENCES transactions(id),
                        matched_at DATETIME,
                        notes TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                ))
                conn.execute(text(
                    "INSERT INTO loan_schedule_entries_new "
                    "(id, loan_id, due_date, amount, payment_type, "
                    "matched_transaction_id, matched_at, notes, created_at) "
                    "SELECT id, loan_id, due_date, amount, payment_type, "
                    "matched_transaction_id, matched_at, notes, created_at "
                    "FROM loan_schedule_entries"
                ))
                conn.execute(text("DROP TABLE loan_schedule_entries"))
                conn.execute(text(
                    "ALTER TABLE loan_schedule_entries_new "
                    "RENAME TO loan_schedule_entries"
                ))
                conn.execute(text(
                    "CREATE INDEX ix_schedule_loan_id "
                    "ON loan_schedule_entries(loan_id)"
                ))
                conn.execute(text(
                    "CREATE INDEX ix_schedule_due_date "
                    "ON loan_schedule_entries(due_date)"
                ))
                conn.execute(text(
                    "CREATE INDEX ix_schedule_matched_tx "
                    "ON loan_schedule_entries(matched_transaction_id)"
                ))
                conn.execute(text("PRAGMA foreign_keys = ON"))
                applied.append("loan_schedule_entries.matched_transaction_id drop unique")

    # loans.current_balance_at_creation — saldo när lånet registrerades
    # loans.category_id — valfri budgetkategori (Huslån/Billån/…)
    if _table_exists(engine, "loans"):
        loan_cols = _columns(engine, "loans")
        if "current_balance_at_creation" not in loan_cols:
            _add_column(
                engine,
                "loans",
                "current_balance_at_creation NUMERIC(14, 2)",
            )
            applied.append("loans.current_balance_at_creation")
        if "category_id" not in loan_cols:
            _add_column(
                engine,
                "loans",
                "category_id INTEGER REFERENCES categories(id)",
            )
            applied.append("loans.category_id")

    # Fakturarader på planerade fakturor (el/vatten/bredband etc.)
    if not _table_exists(engine, "upcoming_transaction_lines"):
        with engine.begin() as conn:
            conn.execute(text(
                """
                CREATE TABLE upcoming_transaction_lines (
                    id INTEGER PRIMARY KEY,
                    upcoming_id INTEGER NOT NULL REFERENCES upcoming_transactions(id) ON DELETE CASCADE,
                    description VARCHAR(200) NOT NULL,
                    amount NUMERIC(14, 2) NOT NULL,
                    category_id INTEGER REFERENCES categories(id),
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            ))
            conn.execute(text(
                "CREATE INDEX ix_upcoming_lines_upcoming_id "
                "ON upcoming_transaction_lines(upcoming_id)"
            ))
        applied.append("upcoming_transaction_lines (new table)")

    # Splits på faktiska transaktioner — samma struktur, men med tecken.
    if not _table_exists(engine, "transaction_splits"):
        with engine.begin() as conn:
            conn.execute(text(
                """
                CREATE TABLE transaction_splits (
                    id INTEGER PRIMARY KEY,
                    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
                    description VARCHAR(200) NOT NULL,
                    amount NUMERIC(14, 2) NOT NULL,
                    category_id INTEGER REFERENCES categories(id),
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    source VARCHAR(20) NOT NULL DEFAULT 'upcoming',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            ))
            conn.execute(text(
                "CREATE INDEX ix_tx_splits_transaction_id "
                "ON transaction_splits(transaction_id)"
            ))
        applied.append("transaction_splits (new table)")

    # New tables (loans, loan_payments, upcoming_transactions) are created
    # by Base.metadata.create_all in auth routes; nothing to ALTER here.

    if applied:
        log.info("Schema migrations applied: %s", ", ".join(applied))

    # Data-migration: flytta transaktioner från sub-konton (med
    # parent_account_id satt) till deras parent-konto. Sätt
    # transactions.cardholder från sub-kontots namn. Radera sub-kontona.
    # Detta körs efter schema-migrationen så `cardholder`-kolumnen finns.
    if (
        _table_exists(engine, "accounts")
        and "parent_account_id" in _columns(engine, "accounts")
        and "cardholder" in _columns(engine, "transactions")
    ):
        with engine.begin() as conn:
            subs = conn.execute(text(
                "SELECT id, name, parent_account_id FROM accounts "
                "WHERE parent_account_id IS NOT NULL"
            )).fetchall()
            migrated = 0
            for sub_id, sub_name, parent_id in subs:
                # Härled cardholder-namnet ur sub-kontots namn:
                # "SAS Amex Premium — Karl Robin Ludvig Fröjd" → "Karl Robin…"
                name_for_holder = (sub_name or "").strip()
                if " — " in name_for_holder:
                    name_for_holder = name_for_holder.split(" — ", 1)[1].strip()
                # Flytta transaktioner till parent + sätt cardholder
                result = conn.execute(
                    text(
                        "UPDATE transactions "
                        "SET account_id = :parent, cardholder = :holder "
                        "WHERE account_id = :sub"
                    ),
                    {
                        "parent": parent_id,
                        "holder": name_for_holder or None,
                        "sub": sub_id,
                    },
                )
                migrated += result.rowcount
                # Ta bort subkontot
                conn.execute(
                    text("DELETE FROM accounts WHERE id = :sub"),
                    {"sub": sub_id},
                )
            if subs:
                log.info(
                    "Merged %d sub-accounts (%d transactions) into parents",
                    len(subs), migrated,
                )
                applied.append(
                    f"accounts.parent_account_id → cardholder "
                    f"({len(subs)} sub, {migrated} tx)"
                )

    # Normalisera UpcomingTransaction.amount till positivt. Gamla bills
    # som skapats från Subscriptions hade negativt tecken, vilket gör
    # att formeln (+tecken för income, -tecken för bill) inte fungerar.
    if _table_exists(engine, "upcoming_transactions"):
        with engine.begin() as conn:
            result = conn.execute(text(
                "UPDATE upcoming_transactions "
                "SET amount = -amount "
                "WHERE amount < 0"
            ))
            if result.rowcount:
                applied.append(
                    f"upcoming_transactions.amount normaliserad till positivt "
                    f"({result.rowcount} rader)"
                )

    return applied
