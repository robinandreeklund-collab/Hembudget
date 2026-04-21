"""Demo-mode: automatisk seed av databasen med användarens CSV/XLSX-data
från repo:ts data/-mapp. Aktiveras via HEMBUDGET_DEMO_MODE=1.

När aktivt:
1. Ingen master-password krävs — alla endpoints tillgängliga utan auth.
2. Vid första startup, om databasen är tom, skapas standardkonton och
   alla filer under data/ importeras automatiskt.
3. Transfer-scan körs retroaktivt så parningar hittas över filer.

Syftet är att en utomstående (eller en recensent) ska kunna öppna en
publik Render-URL och direkt se ett fullt ifyllt exempel — ingen setup.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy.orm import Session

from .categorize.rules import seed_categories_and_rules
from .db.base import get_engine, init_engine, session_scope
from .db.migrate import run_migrations
from .db.models import Account, Transaction, create_all
from .parsers import detect_parser, parser_for_bank
from .transfers.detector import TransferDetector
from .categorize.engine import CategorizationEngine

log = logging.getLogger(__name__)


def is_enabled() -> bool:
    return os.environ.get("HEMBUDGET_DEMO_MODE", "").lower() in ("1", "true", "yes")


def bootstrap_if_empty(data_root: Path | None = None) -> dict:
    """Kör en gång vid startup i demo-mode. Idempotent."""
    if not is_enabled():
        return {"skipped": "not demo mode"}

    # Initiera DB utan master-nyckel (plain SQLite)
    init_engine(key=None)
    create_all()
    run_migrations(get_engine())

    with session_scope() as s:
        seed_categories_and_rules(s)
        if s.query(Account).count() > 0:
            return {"already_initialized": True, "accounts": s.query(Account).count()}

        accounts = _create_demo_accounts(s)

    data_root = data_root or Path(__file__).resolve().parents[2] / "data"
    if not data_root.exists():
        return {"no_data_dir": str(data_root)}

    stats = {"imported": {}, "errors": []}
    with session_scope() as s:
        _import_all(s, data_root, accounts, stats)

    return stats


def _create_demo_accounts(session: Session) -> dict[str, int]:
    """Skapa 3 standardkonton med kontonummer + kreditkortskoppling."""
    lon = Account(
        name="Nordea lönekonto", bank="nordea", type="checking",
        account_number="1709 20 72840",
    )
    gem = Account(
        name="Nordea gemensamt", bank="nordea", type="shared",
        account_number="1722 20 34439",
    )
    seb = Account(name="SEB Kort", bank="seb_kort", type="credit")
    session.add_all([lon, gem, seb])
    session.flush()
    seb.pays_credit_account_id = gem.id
    session.flush()
    return {"lon": lon.id, "gem": gem.id, "seb": seb.id}


def _import_all(
    session: Session, data_root: Path, accounts: dict[str, int], stats: dict,
) -> None:
    # Nordea lönekonto
    lon_dir = data_root / "Nordea" / "1709 20 72840"
    if lon_dir.exists():
        for f in sorted(lon_dir.glob("*.csv")):
            _import_one(session, f, accounts["lon"], "nordea", stats)

    # Nordea gemensamt
    gem_dir = data_root / "Nordea" / "1722 20 34439"
    if gem_dir.exists():
        for f in sorted(gem_dir.glob("*.csv")):
            _import_one(session, f, accounts["gem"], "nordea", stats)

    # SEB Kort XLSX
    seb_dir = data_root / "seb"
    if seb_dir.exists():
        for f in sorted(seb_dir.glob("*.xlsx")):
            _import_one(session, f, accounts["seb"], "seb_kort", stats)

    # Retroaktiv transfer-scan
    detector = TransferDetector(session)
    result = detector.detect_internal_transfers()
    stats["transfer_scan_pairs"] = result.pairs


def _import_one(
    session: Session, f: Path, account_id: int, bank: str, stats: dict,
) -> None:
    import hashlib
    from decimal import Decimal

    from .db.models import Import as ImportModel

    content = f.read_bytes()
    parser = parser_for_bank(bank, content) or detect_parser(content)
    if parser is None:
        stats["errors"].append(f"No parser for {f.name}")
        return

    sha = hashlib.sha256(content).hexdigest()
    if session.query(ImportModel).filter(ImportModel.sha256 == sha).first():
        return

    rows = parser.parse(content)
    imp = ImportModel(
        filename=f.name, bank=parser.bank, sha256=sha, row_count=len(rows),
    )
    session.add(imp)
    session.flush()

    existing_hashes = {
        h for (h,) in session.query(Transaction.hash).filter(
            Transaction.account_id == account_id
        ).all()
    }
    new_txs: list[Transaction] = []
    for raw in rows:
        h = raw.stable_hash(account_id)
        if h in existing_hashes:
            continue
        existing_hashes.add(h)
        tx = Transaction(
            account_id=account_id, date=raw.date,
            amount=Decimal(str(raw.amount)),
            currency=raw.currency, raw_description=raw.description,
            source_file_id=imp.id, hash=h,
        )
        session.add(tx)
        new_txs.append(tx)
    session.flush()

    engine = CategorizationEngine(session, llm=None)
    results = engine.categorize_batch(new_txs)
    engine.apply_results(new_txs, results)
    TransferDetector(session).detect_and_link(new_txs)
    session.flush()
    stats["imported"][f.name] = len(new_txs)
    log.info("demo: imported %s (%d rows)", f.name, len(new_txs))
