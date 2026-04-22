from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from ..categorize.engine import normalize_merchant
from ..categorize.rules import create_rule_from_correction
from ..db.models import Account, Category, Import, Transaction
from ..transfers.detector import TransferDetector
from .deps import db, require_auth
from .schemas import (
    AccountIn, AccountOut, AccountUpdate,
    CategoryIn, CategoryOut, CategoryUpdate,
    TransactionOut, TransactionUpdate, TransferLinkIn,
)

router = APIRouter(tags=["transactions"], dependencies=[Depends(require_auth)])


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(session: Session = Depends(db)) -> list[Account]:
    return session.query(Account).order_by(Account.id).all()


@router.post("/accounts", response_model=AccountOut)
def create_account(payload: AccountIn, session: Session = Depends(db)) -> Account:
    a = Account(**payload.model_dump())
    session.add(a)
    session.flush()
    return a


@router.post("/accounts/parse-pdf")
async def parse_account_statement_pdf(
    file: UploadFile = File(...),
    account_type: str = "checking",
    session: Session = Depends(db),
) -> dict:
    """Läs en Nordea "Kontohändelser"-PDF och skapa konto + transaktioner
    automatiskt. Om kontot finns (matchar på account_number) uppdateras
    det och nya transaktioner läggs till (dubblett-skyddat via hash).

    Stödjer ISK, Privatkonto, Sparkonto m.fl. — alla Nordea-konton som
    exporterar Kontohändelser-PDF.
    """
    import hashlib
    from ..parsers.pdf_statements.nordea_account import (
        parse_nordea_statement_pdf,
    )
    from ..categorize.engine import CategorizationEngine
    from ..transfers.detector import TransferDetector
    from ..upcoming_match import UpcomingMatcher

    content = await file.read()
    if not content:
        raise HTTPException(400, "Tom fil")
    if not content.startswith(b"%PDF"):
        raise HTTPException(400, "Endast PDF-filer stöds")

    try:
        stmt = parse_nordea_statement_pdf(content)
    except Exception as exc:
        raise HTTPException(400, f"Kunde inte läsa PDF: {exc}") from exc

    if not stmt.account_number:
        raise HTTPException(
            415,
            "PDF:en saknar kontonummer — är det verkligen en Nordea "
            "Kontohändelser-utskrift?",
        )

    # Normalisera account_number för jämförelse
    def _norm(s: str | None) -> str:
        import re
        return re.sub(r"[^0-9]", "", s or "")

    target_num = _norm(stmt.account_number)

    # Hitta befintligt konto via normaliserat kontonummer
    existing = None
    for acc in session.query(Account).filter(
        Account.account_number.is_not(None)
    ).all():
        if _norm(acc.account_number) == target_num and target_num:
            existing = acc
            break

    created_account = False
    if existing is None:
        # Skapa konto. ISK-konton får type="isk", annars användarens val
        atype = account_type
        name_low = (stmt.account_name or "").lower()
        if "isk" in name_low:
            atype = "isk"
        acc = Account(
            name=stmt.account_name or f"Nordea {stmt.account_number}",
            bank="nordea",
            type=atype,
            currency=stmt.currency,
            account_number=stmt.account_number,
            opening_balance=stmt.opening_balance,
            opening_balance_date=stmt.period_start,
        )
        session.add(acc)
        session.flush()
        created_account = True
    else:
        acc = existing
        # Uppdatera ev. saknande opening_balance + datum
        if acc.opening_balance is None and stmt.opening_balance is not None:
            acc.opening_balance = stmt.opening_balance
            acc.opening_balance_date = stmt.period_start
        session.flush()

    # Audit-post
    imp = Import(
        filename=file.filename or "kontohandelser.pdf",
        bank="nordea",
        sha256=hashlib.sha256(content).hexdigest(),
        row_count=len(stmt.transactions),
    )
    session.add(imp)
    session.flush()

    existing_hashes = {
        h for (h,) in session.query(Transaction.hash).filter(
            Transaction.account_id == acc.id,
        ).all()
    }

    new_txs: list[Transaction] = []
    skipped = 0
    for idx, t in enumerate(stmt.transactions):
        key = (
            f"{acc.id}|{t.date.isoformat()}|{t.amount}|"
            f"{t.description.strip().lower()}|#{idx}"
        )
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if h in existing_hashes:
            skipped += 1
            continue
        existing_hashes.add(h)
        tx = Transaction(
            account_id=acc.id,
            date=t.date,
            amount=t.amount,
            currency=stmt.currency,
            raw_description=t.description,
            source_file_id=imp.id,
            hash=h,
        )
        session.add(tx)
        new_txs.append(tx)

    session.flush()

    # Samma efter-import-pipeline som CSV-importen
    if new_txs:
        engine = CategorizationEngine(session, llm=None)
        results = engine.categorize_batch(new_txs)
        engine.apply_results(new_txs, results)
        session.flush()

    detector = TransferDetector(session)
    transfer_result = detector.detect_and_link(new_txs)
    detector.detect_internal_transfers()

    UpcomingMatcher(session).match(new_txs)
    session.flush()

    return {
        "account_id": acc.id,
        "account_name": acc.name,
        "account_number": acc.account_number,
        "created": created_account,
        "transactions_created": len(new_txs),
        "transactions_skipped_duplicates": skipped,
        "opening_balance": float(stmt.opening_balance),
        "closing_balance": float(stmt.closing_balance),
        "period_start": stmt.period_start.isoformat() if stmt.period_start else None,
        "period_end": stmt.period_end.isoformat() if stmt.period_end else None,
        "transfers_marked": transfer_result.marked,
    }


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def update_account(
    account_id: int, payload: AccountUpdate, session: Session = Depends(db)
) -> Account:
    a = session.get(Account, account_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    session.flush()
    return a


@router.delete("/accounts/{account_id}")
def delete_account(
    account_id: int,
    force: bool = False,
    session: Session = Depends(db),
) -> dict:
    """Radera ett konto.

    Utan `force`: tillåter bara radering av tomma konton (inga transaktioner,
    inte ett återbetalningskonto för ett lån eller kreditkort).
    Med `force=true`: raderar även transaktioner + loan_payments + splits
    kopplade till kontot. Irreversibelt.
    """
    a = session.get(Account, account_id)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")

    tx_count = session.query(Transaction).filter(
        Transaction.account_id == account_id
    ).count()
    # Om ett annat konto pekar hit via pays_credit_account_id
    dependents = session.query(Account).filter(
        Account.pays_credit_account_id == account_id
    ).all()

    if not force:
        if tx_count > 0:
            raise HTTPException(
                409,
                f"Kontot har {tx_count} transaktioner. Använd force=true "
                "för att radera ändå (alla transaktioner försvinner).",
            )
        if dependents:
            names = ", ".join(d.name for d in dependents)
            raise HTTPException(
                409,
                f"Kontot är kopplat som återbetalningskonto för: {names}. "
                "Koppla bort innan du raderar.",
            )

    # Vid force: koppla bort ev. dependents så FK inte bryter
    for d in dependents:
        d.pays_credit_account_id = None

    # Radera relaterade rader FK-säkert
    from ..db.models import LoanPayment, TransactionSplit
    tx_ids = [t.id for t in session.query(Transaction).filter(
        Transaction.account_id == account_id
    ).all()]
    if tx_ids:
        session.query(LoanPayment).filter(
            LoanPayment.transaction_id.in_(tx_ids)
        ).delete(synchronize_session=False)
        session.query(TransactionSplit).filter(
            TransactionSplit.transaction_id.in_(tx_ids)
        ).delete(synchronize_session=False)
        # Nollställ upcoming som matchats till dessa transaktioner
        from ..db.models import UpcomingTransaction, LoanScheduleEntry
        session.query(UpcomingTransaction).filter(
            UpcomingTransaction.matched_transaction_id.in_(tx_ids)
        ).update(
            {"matched_transaction_id": None}, synchronize_session=False
        )
        session.query(LoanScheduleEntry).filter(
            LoanScheduleEntry.matched_transaction_id.in_(tx_ids)
        ).update(
            {"matched_transaction_id": None, "matched_at": None},
            synchronize_session=False,
        )
        # Rensa transfer_pair_id på transaktioner som pekar hit
        session.query(Transaction).filter(
            Transaction.transfer_pair_id.in_(tx_ids)
        ).update(
            {"transfer_pair_id": None, "is_transfer": False},
            synchronize_session=False,
        )
        # Ta bort själva transaktionerna
        session.query(Transaction).filter(
            Transaction.account_id == account_id
        ).delete(synchronize_session=False)

    # Nollställ upcoming.debit_account_id som pekar på kontot
    from ..db.models import UpcomingTransaction
    session.query(UpcomingTransaction).filter(
        UpcomingTransaction.debit_account_id == account_id
    ).update({"debit_account_id": None}, synchronize_session=False)

    session.flush()
    session.delete(a)
    return {
        "deleted": account_id,
        "deleted_transactions": tx_count,
    }


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(session: Session = Depends(db)) -> list[Category]:
    return session.query(Category).order_by(Category.name).all()


@router.post("/categories", response_model=CategoryOut)
def create_category(payload: CategoryIn, session: Session = Depends(db)) -> Category:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Namn får inte vara tomt")
    existing = session.query(Category).filter(Category.name == name).first()
    if existing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Kategori '{name}' finns redan",
        )
    c = Category(
        name=name,
        parent_id=payload.parent_id,
        color=payload.color,
        icon=payload.icon,
    )
    session.add(c)
    session.flush()
    return c


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int, payload: CategoryUpdate, session: Session = Depends(db)
) -> Category:
    c = session.get(Category, category_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    session.flush()
    return c


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, session: Session = Depends(db)) -> dict:
    c = session.get(Category, category_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    # Flytta bort transaktioner som pekar hit (blir okategoriserade)
    session.query(Transaction).filter(Transaction.category_id == category_id).update(
        {"category_id": None}
    )
    session.delete(c)
    return {"deleted": category_id}


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    uncategorized: bool = False,
    limit: int = Query(500, le=2000),
    offset: int = 0,
    session: Session = Depends(db),
) -> list[Transaction]:
    q = session.query(Transaction)
    if account_id is not None:
        q = q.filter(Transaction.account_id == account_id)
    if category_id is not None:
        q = q.filter(Transaction.category_id == category_id)
    if from_date:
        q = q.filter(Transaction.date >= from_date)
    if to_date:
        q = q.filter(Transaction.date <= to_date)
    if uncategorized:
        q = q.filter(Transaction.category_id.is_(None))
    return q.order_by(Transaction.date.desc(), Transaction.id.desc()).offset(offset).limit(limit).all()


@router.patch("/transactions/{tx_id}", response_model=TransactionOut)
def update_transaction(
    tx_id: int, payload: TransactionUpdate, session: Session = Depends(db)
) -> Transaction:
    tx = session.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    fields = payload.model_dump(exclude_unset=True)
    create_rule = fields.pop("create_rule", True)

    # Handle is_transfer toggle (clears category, unlinks pair if set)
    if "is_transfer" in fields:
        new_flag = bool(fields.pop("is_transfer"))
        if new_flag and not tx.is_transfer:
            tx.is_transfer = True
            tx.category_id = None
        elif not new_flag and tx.is_transfer:
            TransferDetector(session).unlink(tx.id)

    if "category_id" in fields and fields["category_id"] is not None:
        tx.category_id = fields["category_id"]
        tx.user_verified = True
        tx.is_transfer = False       # kategorisering motsäger transfer
        if create_rule and tx.normalized_merchant:
            create_rule_from_correction(
                session,
                pattern=tx.normalized_merchant.lower(),
                category_id=fields["category_id"],
                priority=120,
            )
    for k, v in fields.items():
        if k == "category_id":
            continue
        setattr(tx, k, v)
    session.flush()
    return tx


@router.post("/transactions/transfers/link")
def link_transfer(payload: TransferLinkIn, session: Session = Depends(db)) -> dict:
    try:
        TransferDetector(session).link_manual(payload.tx_a_id, payload.tx_b_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"ok": True}


@router.post("/transactions/{tx_id}/transfers/unlink")
def unlink_transfer(tx_id: int, session: Session = Depends(db)) -> dict:
    TransferDetector(session).unlink(tx_id)
    return {"ok": True}


@router.post("/transactions/{tx_id}/reclassify", response_model=TransactionOut)
def reclassify(tx_id: int, session: Session = Depends(db)) -> Transaction:
    tx = session.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    tx.normalized_merchant = normalize_merchant(tx.raw_description)
    session.flush()
    return tx
