from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

from ..categorize.engine import normalize_merchant
from ..categorize.rules import create_rule_from_correction
from ..db.models import Account, Category, Import, Transaction, User
from ..llm.client import LMStudioClient
from ..transfers.detector import TransferDetector
from .deps import db, llm_client, require_auth
from .schemas import (
    AccountIn, AccountOut, AccountUpdate,
    CategoryIn, CategoryOut, CategoryUpdate,
    TransactionOut, TransactionUpdate, TransferLinkIn,
    UserIn, UserOut,
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


@router.get("/users", response_model=list[UserOut])
def list_users(session: Session = Depends(db)) -> list[User]:
    """Hushållsmedlemmar — används för att sätta ägare på konton."""
    return session.query(User).order_by(User.id).all()


@router.post("/users", response_model=UserOut)
def create_user(payload: UserIn, session: Session = Depends(db)) -> User:
    u = User(name=payload.name.strip())
    session.add(u); session.flush()
    return u


@router.delete("/users/{user_id}")
def delete_user(user_id: int, session: Session = Depends(db)) -> dict:
    u = session.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    # Nolla owner_id på konton som pekade på användaren
    session.query(Account).filter(Account.owner_id == user_id).update(
        {"owner_id": None},
    )
    session.delete(u)
    session.flush()
    return {"deleted": user_id}


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
    rows = (
        q.order_by(Transaction.date.desc(), Transaction.id.desc())
        .offset(offset).limit(limit).all()
    )
    _attach_upcoming_matches(session, rows)
    return rows


def _attach_upcoming_matches(
    session: Session, txs: list[Transaction],
) -> None:
    """Sätt .upcoming_matches på varje tx (läses av Pydantic via
    from_attributes). Tom lista om ingen match — användaren ser då ingen
    badge."""
    from ..db.models import UpcomingPayment, UpcomingTransaction

    if not txs:
        return
    tx_ids = [t.id for t in txs]
    rows = (
        session.query(UpcomingPayment, UpcomingTransaction)
        .join(UpcomingTransaction, UpcomingTransaction.id == UpcomingPayment.upcoming_id)
        .filter(UpcomingPayment.transaction_id.in_(tx_ids))
        .all()
    )
    by_tx: dict[int, list] = {tid: [] for tid in tx_ids}
    for pay, up in rows:
        by_tx[pay.transaction_id].append({
            "upcoming_id": up.id,
            "name": up.name,
            "kind": up.kind,
            "amount": up.amount,
        })
    for t in txs:
        t.upcoming_matches = by_tx.get(t.id, [])


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


@router.delete("/transactions/{tx_id}")
def delete_transaction(
    tx_id: int, session: Session = Depends(db),
) -> dict:
    """Radera en transaktion permanent + städa upp alla referenser:

    - UpcomingPayment-rader (om tx ingick i en delbetalning)
    - LoanPayment-rader (om tx var en lånebetalning)
    - TransactionSplits (kopior av upcoming-lines)
    - Transfer-pair: om tx var del av ett par, koppla loss motparten
    - matched_transaction_id på upcomings: om denna tx var primär match
      → flytta till nästa kvarvarande payment eller null

    Användsfall: dubbletter (t.ex. en lön inlagd både via upcoming-
    materialize och via CSV-import).
    """
    from ..db.models import (
        LoanPayment as _LoanPayment,
        TransactionSplit as _Split,
        UpcomingTransaction as _UT,
    )
    from ..upcoming_match.payments import remove_all_payments_for_tx

    tx = session.get(Transaction, tx_id)
    if tx is None:
        raise HTTPException(404, "Transaction not found")

    cleanup: dict[str, int] = {}

    # 1. UpcomingPayment + matched_transaction_id-flytt
    affected_upcomings = remove_all_payments_for_tx(session, tx_id)
    cleanup["upcoming_payments_removed"] = len(affected_upcomings)

    # 2. LoanPayment
    lp_count = (
        session.query(_LoanPayment)
        .filter(_LoanPayment.transaction_id == tx_id)
        .delete(synchronize_session=False)
    )
    cleanup["loan_payments_removed"] = lp_count

    # 3. TransactionSplits
    split_count = (
        session.query(_Split)
        .filter(_Split.transaction_id == tx_id)
        .delete(synchronize_session=False)
    )
    cleanup["splits_removed"] = split_count

    # 4. Transfer-pair: koppla loss motparten
    if tx.transfer_pair_id is not None:
        partner = session.get(Transaction, tx.transfer_pair_id)
        if partner is not None:
            partner.transfer_pair_id = None
            # Behåll is_transfer på partnern så användaren kan välja
            # om hen vill avmarkera den eller skapa ny motpart
            cleanup["partner_unlinked"] = partner.id

    # 5. Sätt eventuella loan_schedule_entries med matched_transaction_id
    #    till null
    from ..db.models import LoanScheduleEntry as _LSE
    cleared = (
        session.query(_LSE)
        .filter(_LSE.matched_transaction_id == tx_id)
        .update(
            {"matched_transaction_id": None, "matched_at": None},
            synchronize_session=False,
        )
    )
    cleanup["loan_schedule_entries_unmatched"] = cleared

    # 6. Slutligen: radera transaktionen
    session.delete(tx)
    session.flush()
    cleanup["deleted"] = tx_id
    return cleanup


@router.post("/accounts/{account_id}/manual-transaction", response_model=TransactionOut)
def create_manual_transaction(
    account_id: int, payload: dict, session: Session = Depends(db),
) -> Transaction:
    """Skapa en manuell Transaction på ett konto. Används främst för att
    dokumentera inkognito-kontots löner och överföringar.

    Body: `{date: YYYY-MM-DD, amount: number, description: str,
    category_id?: int}`. Körs igenom kategoriserings- och transfer-
    detektorns pipeline så den paras automatiskt mot motsvarande rader
    på andra konton.
    """
    import hashlib
    from datetime import date as _date

    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(404, "Account not found")

    date_s = payload.get("date")
    amount_raw = payload.get("amount")
    description = (payload.get("description") or "").strip()
    category_id = payload.get("category_id")

    if not date_s or amount_raw is None or not description:
        raise HTTPException(400, "date, amount och description krävs")

    try:
        tx_date = _date.fromisoformat(date_s)
    except ValueError:
        raise HTTPException(400, f"Ogiltigt datum: {date_s}") from None

    try:
        amount = Decimal(str(amount_raw))
    except Exception:
        raise HTTPException(400, f"Ogiltigt belopp: {amount_raw}") from None

    # Unik hash för dedup
    key = f"manual|{account_id}|{date_s}|{amount}|{description.lower()}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()

    tx = Transaction(
        account_id=account_id, date=tx_date, amount=amount,
        currency=acc.currency or "SEK",
        raw_description=description, hash=h,
        normalized_merchant=normalize_merchant(description),
        category_id=category_id,
        user_verified=bool(category_id),
    )
    session.add(tx)
    session.flush()

    # Kör transfer-detektorn så överföringar mellan inkognito och
    # gemensamma konton paras ihop automatiskt
    TransferDetector(session).detect_internal_transfers()
    session.flush()

    return tx


@router.post("/accounts/{account_id}/parse-pasted-statement")
def parse_pasted_statement(
    account_id: int, payload: dict, session: Session = Depends(db),
) -> dict:
    """Tolka ett klistrat kontoutdrag (text). Returnerar förhandsvisning
    + dedup-info mot existerande transaktioner — INGEN data sparas här.

    Body: `{text: str}`. Användaren får sedan godkänna och kalla
    /import-pasted-statement med samma rader för faktisk import.

    Svar:
    - candidates: [{date, amount, description, duplicate, dup_reason}]
    - latest_existing_date: senaste befintliga tx på kontot (som hint)
    - parse_errors: rader som ignorerades och varför
    """
    import hashlib
    from ..parsers.paste_text import parse_pasted

    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(404, "Account not found")
    text = (payload.get("text") or "").strip()
    if not text:
        return {"candidates": [], "latest_existing_date": None}

    rows = parse_pasted(text)

    # Hämta existerande hashar + beskrivningar för dedup-detektion.
    # Vi har två nivåer:
    #  1. Exakt hash-match → garanterad dubblett.
    #  2. Samma datum + samma belopp → trolig dubblett (fuzzy desc).
    existing_hashes = {
        h for (h,) in session.query(Transaction.hash)
        .filter(Transaction.account_id == account_id).all()
    }
    by_date_amount = {}
    for tx in (
        session.query(Transaction)
        .filter(Transaction.account_id == account_id).all()
    ):
        by_date_amount.setdefault(
            (tx.date.isoformat(), str(tx.amount)), []
        ).append(tx.raw_description)

    def _paste_hash(account_id: int, dt, amount: Decimal, desc: str) -> str:
        # Normalisera amount till exakt 2 decimaler så att 6400 och
        # 6400.0 och 6400.00 alltid blir samma hash.
        amt_str = f"{Decimal(str(amount)).quantize(Decimal('0.01')):f}"
        key = f"paste|{account_id}|{dt.isoformat()}|{amt_str}|{desc.lower()}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    candidates = []
    for r in rows:
        h = _paste_hash(account_id, r.date, r.amount, r.description)
        dup = h in existing_hashes
        dup_reason = None
        if dup:
            dup_reason = "exakt match (samma datum, belopp och beskrivning)"
        else:
            # Fuzzy: samma datum + samma belopp finns redan
            existing_descs = by_date_amount.get(
                (r.date.isoformat(), str(r.amount)), []
            )
            if existing_descs:
                dup = True
                dup_reason = (
                    f"samma datum + belopp finns: \"{existing_descs[0]}\""
                )
        candidates.append({
            "date": r.date.isoformat(),
            "amount": float(r.amount),
            "description": r.description,
            "duplicate": dup,
            "dup_reason": dup_reason,
        })

    latest = (
        session.query(func.max(Transaction.date))
        .filter(Transaction.account_id == account_id).scalar()
    )
    return {
        "candidates": candidates,
        "latest_existing_date": latest.isoformat() if latest else None,
        "parsed_count": len(rows),
        "raw_lines": len(text.splitlines()),
    }


@router.post("/accounts/{account_id}/import-pasted-statement")
def import_pasted_statement(
    account_id: int, payload: dict, session: Session = Depends(db),
    llm: LMStudioClient = Depends(llm_client),
) -> dict:
    """Importera de godkända raderna från ett klistrat kontoutdrag.

    Body: `{rows: [{date, amount, description}], skip_duplicates: bool}`.
    Skapar Transactions med proper hash + kör auto-kategorisering +
    transfer-detektor. Hoppar över rader som redan finns (samma hash)
    om skip_duplicates=True (default).
    """
    import hashlib
    from datetime import date as _date
    from ..categorize.engine import CategorizationEngine

    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(404, "Account not found")
    rows = payload.get("rows") or []
    skip_dups = bool(payload.get("skip_duplicates", True))
    if not isinstance(rows, list):
        raise HTTPException(400, "rows måste vara en lista")

    existing_hashes = {
        h for (h,) in session.query(Transaction.hash)
        .filter(Transaction.account_id == account_id).all()
    }

    created_txs: list[Transaction] = []
    skipped_dups = 0
    errors: list[dict] = []
    for i, r in enumerate(rows):
        try:
            tx_date = _date.fromisoformat(r["date"])
            amount = Decimal(str(r["amount"]))
            description = (r.get("description") or "").strip()
        except (KeyError, ValueError, Exception) as exc:
            errors.append({"index": i, "error": str(exc)})
            continue
        if not description or amount == 0:
            errors.append({"index": i, "error": "saknar beskrivning eller belopp = 0"})
            continue
        # Samma hash-format som parse-pasted-statement för dedup
        amt_str = f"{amount.quantize(Decimal('0.01')):f}"
        key = (
            f"paste|{account_id}|{tx_date.isoformat()}|{amt_str}|"
            f"{description.lower()}"
        )
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if h in existing_hashes:
            if skip_dups:
                skipped_dups += 1
                continue
        tx = Transaction(
            account_id=account_id, date=tx_date, amount=amount,
            currency=acc.currency or "SEK",
            raw_description=description, hash=h,
            normalized_merchant=normalize_merchant(description),
        )
        session.add(tx)
        created_txs.append(tx)
        existing_hashes.add(h)
    session.flush()

    # Kör auto-kategorisering på nyimporterade rader. Default = bara
    # rules + history (snabbt, deterministiskt). LLM-fallback kräver
    # explicit opt-in eftersom den kan ta tid om LM Studio är osäker.
    use_llm = bool(payload.get("use_llm", False))
    categorized_count = 0
    if created_txs:
        engine = CategorizationEngine(session, llm=llm if use_llm else None)
        try:
            results = engine.categorize_batch(created_txs)
            engine.apply_results(created_txs, results)
            categorized_count = sum(1 for tx in created_txs if tx.category_id)
        except Exception as exc:
            log.warning("auto-categorization failed for pasted import: %s", exc)
        # Transfer-detektor parar interna överföringar
        try:
            TransferDetector(session).detect_internal_transfers()
        except Exception as exc:
            log.warning("transfer-detection failed: %s", exc)
        session.flush()

    return {
        "imported": len(created_txs),
        "skipped_duplicates": skipped_dups,
        "categorized": categorized_count,
        "errors": errors,
    }


@router.get("/transactions/{tx_id}/match-candidates")
def list_match_candidates(
    tx_id: int,
    kind: Optional[str] = Query(None, description="'income' eller 'bill'"),
    session: Session = Depends(db),
) -> dict:
    """Lista UpcomingTransactions som kan bindas manuellt till denna
    transaktion, inklusive PARTIAL-kandidater.

    Returnerar upcomings där:
    1. Exakt beloppsmatch (±1 kr) — denna tx kan helbetala upcomingen
    2. Närhet i belopp (±10 kr) — nära-matchning
    3. PARTIAL: upcoming.amount > |tx.amount| + 1 — denna tx kan vara
       en delbetalning. Vi inkluderar bara om upcomingen har öppen
       'remaining' (amount − paid_amount ≥ |tx.amount|)

    Max 30 kandidater. Sorterade efter matchgrad + datumnärhet.
    """
    from ..db.models import UpcomingPayment, UpcomingTransaction

    tx = session.get(Transaction, tx_id)
    if tx is None:
        raise HTTPException(404, "Transaction not found")

    default_kind = "income" if tx.amount > 0 else "bill"
    use_kind = kind or default_kind

    q = session.query(UpcomingTransaction)
    if use_kind in ("income", "bill"):
        q = q.filter(UpcomingTransaction.kind == use_kind)
    # Acceptera även upcomings som redan har match (delbetalningar tillåts)
    ups = q.all()

    # Hämta paid_amount per upcoming i en query
    paid_rows = (
        session.query(
            UpcomingPayment.upcoming_id,
            func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("paid"),
        )
        .join(Transaction, Transaction.id == UpcomingPayment.transaction_id)
        .group_by(UpcomingPayment.upcoming_id)
        .all()
    )
    paid_by_id = {u_id: float(p) for u_id, p in paid_rows}

    tx_date = tx.date
    tx_amount = tx.amount
    tx_abs = abs(float(tx_amount))
    scored: list[tuple[int, int, bool, str, UpcomingTransaction]] = []
    for up in ups:
        expected = up.amount if up.kind == "income" else -up.amount
        expected_f = float(expected)
        date_diff = abs((up.expected_date - tx_date).days)
        amount_diff = abs(float(tx_amount) - expected_f)
        paid = paid_by_id.get(up.id, 0.0)
        remaining = float(up.amount) - paid

        match_type = "full"
        same_sign = (tx_amount < 0) == (up.kind == "bill")
        if amount_diff <= 1.0 and date_diff <= 10:
            rank = 0
        elif amount_diff <= 10.0 and date_diff <= 30:
            rank = 1
        elif (
            # Partial: tx är MINDRE än remaining (≤), inte samma belopp,
            # och samma tecken-riktning.
            same_sign
            and tx_abs > 0.01
            and tx_abs <= remaining + 1.0
            and date_diff <= 30
        ):
            rank = 2
            match_type = "partial"
        else:
            continue  # skippa helt orelevanta

        exact = amount_diff <= 1.0 and date_diff <= 5
        scored.append((rank, date_diff, exact, match_type, up))

    scored.sort(key=lambda t: (t[0], t[1]))
    top = scored[:30]

    return {
        "transaction": {
            "id": tx.id,
            "date": tx.date.isoformat(),
            "amount": float(tx.amount),
            "description": tx.raw_description,
            "account_id": tx.account_id,
        },
        "kind": use_kind,
        "candidates": [
            {
                "id": up.id,
                "kind": up.kind,
                "name": up.name,
                "amount": float(up.amount),
                "paid_amount": paid_by_id.get(up.id, 0.0),
                "remaining_amount": float(up.amount) - paid_by_id.get(up.id, 0.0),
                "expected_date": up.expected_date.isoformat(),
                "owner": up.owner,
                "source": up.source,
                "amount_diff": round(abs(float(tx_amount) - float(
                    up.amount if up.kind == "income" else -up.amount
                )), 2),
                "date_diff_days": abs((up.expected_date - tx_date).days),
                "exact_match": bool(exact),
                "match_type": match_type,
            }
            for rank, date_diff, exact, match_type, up in top
        ],
    }


@router.post("/transactions/{tx_id}/match-upcoming")
def match_upcoming(
    tx_id: int,
    payload: dict,
    session: Session = Depends(db),
) -> dict:
    """Koppla manuellt en Transaction till en UpcomingTransaction som
    en (del)betalning.

    Flera Transactions kan kopplas till samma upcoming — användbart för
    fakturor som betalas i två omgångar (t.ex. Amex 13 445 kr = 5 000 +
    8 445 från två bankdagar). Varje samtal adderar en ny betalning via
    UpcomingPayment-junctiontabellen.

    Body: `{"upcoming_id": N}`.
    """
    from ..db.models import UpcomingTransaction
    from ..splits import apply_upcoming_lines_to_transaction
    from ..upcoming_match.payments import (
        add_payment, paid_amount, payment_status,
    )

    tx = session.get(Transaction, tx_id)
    if tx is None:
        raise HTTPException(404, "Transaction not found")
    upcoming_id = payload.get("upcoming_id")
    if not isinstance(upcoming_id, int):
        raise HTTPException(400, "upcoming_id (int) krävs i body")
    up = session.get(UpcomingTransaction, upcoming_id)
    if up is None:
        raise HTTPException(404, "Upcoming not found")

    created = add_payment(session, up, tx)
    splits_created = False
    # Kopiera splits bara vid första matchningen (fler tx:er ska inte
    # generera flera uppsättningar splits för samma faktura-rader)
    if created and up.lines and up.matched_transaction_id == tx.id:
        apply_upcoming_lines_to_transaction(session, up, tx)
        splits_created = True
    session.flush()

    return {
        "transaction_id": tx.id,
        "upcoming_id": up.id,
        "upcoming_name": up.name,
        "amount": float(up.amount),
        "paid_amount": float(paid_amount(session, up)),
        "remaining_amount": float(up.amount - paid_amount(session, up)),
        "status": payment_status(session, up),
        "kind": up.kind,
        "splits_created": splits_created,
        "already_matched": not created,
    }


@router.post("/transactions/{tx_id}/unmatch-upcoming")
def unmatch_upcoming(tx_id: int, session: Session = Depends(db)) -> dict:
    """Koppla bort en Transaction från sin matchade upcoming + rensa splits
    som kom från upcoming:en (source='upcoming'). Transaktionen finns kvar.

    Rensar även UpcomingPayment-rader (junction) så delbetalnings-summan
    räknas om korrekt. Om upcomingen hade flera betalningar och denna
    var den 'primära' matchningen flyttas primary till nästa kvarvarande
    betalning."""
    from ..db.models import TransactionSplit
    from ..upcoming_match.payments import remove_all_payments_for_tx

    tx = session.get(Transaction, tx_id)
    if tx is None:
        raise HTTPException(404, "Transaction not found")

    affected = remove_all_payments_for_tx(session, tx_id)
    if not affected:
        raise HTTPException(404, "Ingen upcoming matchad mot denna tx")

    # Radera splits som skapats från upcoming (behåll manuella)
    session.query(TransactionSplit).filter(
        TransactionSplit.transaction_id == tx_id,
        TransactionSplit.source == "upcoming",
    ).delete(synchronize_session=False)
    session.flush()
    return {"transaction_id": tx_id, "unmatched": affected}


@router.post("/transactions/{tx_id}/attach-invoice")
async def attach_invoice_to_transaction(
    tx_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(db),
    llm: LMStudioClient = Depends(llm_client),
):
    """Bifoga en faktura till en befintlig transaktion.

    - Parsar fakturan (PDF-text eller vision) via samma pipeline som
      /upcoming/parse-invoice-image.
    - Skapar en UpcomingTransaction direkt i 'betald'-läge (matched_transaction_id=tx_id).
    - Kopierar ev. fakturarader till transaction_splits så budget och
      rapporter kan fördela utgiften per kategori (t.ex. el/vatten/
      bredband på Hjo Energi-fakturan).
    - Sparar originalfilen under data_dir/invoices så ledger-vyn kan
      visa PDFen senare.
    """
    from ..api.upcoming import (
        _llm_parse_invoice, _save_invoice_file, _build_upcoming_from_parsed,
    )
    from ..llm.client import LLMUnavailable
    from ..splits import build_lines_from_vision, apply_upcoming_lines_to_transaction

    tx = session.get(Transaction, tx_id)
    if tx is None:
        raise HTTPException(404, "Transaction not found")

    content = await file.read()
    if not content:
        raise HTTPException(400, "Tom fil")

    if not llm.is_alive():
        raise HTTPException(503, "LM Studio är inte tillgänglig")

    original_path = _save_invoice_file(content, file.filename)
    try:
        parsed = _llm_parse_invoice(content, file.content_type, llm, session)
    except LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    # Matcha dates: om LLM:n gav expected_date men vi vet att tx.date är
    # den faktiska debiteringen, använd tx.date för debit_date så
    # ledger-vyn visar rätt period.
    u = _build_upcoming_from_parsed(
        parsed,
        kind="bill",
        source=parsed.get("_source_method", "vision_ai"),
        source_image_path=str(original_path),
        session=session,
    )
    u.matched_transaction_id = tx.id
    if u.debit_account_id is None:
        u.debit_account_id = tx.account_id
    plines = parsed.get("lines") or []
    if plines:
        u.lines.extend(build_lines_from_vision(session, plines))
    session.add(u)
    session.flush()

    # Kopiera lines till transaction_splits så rapporter fördelar rätt
    if u.lines:
        apply_upcoming_lines_to_transaction(session, u, tx)
        session.flush()

    return {
        "upcoming_id": u.id,
        "transaction_id": tx.id,
        "name": u.name,
        "amount": float(u.amount),
        "line_count": len(u.lines),
        "method": parsed.get("_source_method"),
        "source_file": original_path.name,
    }


@router.get("/transactions/invoiced-ids")
def list_invoiced_transaction_ids(session: Session = Depends(db)) -> dict:
    """Returnera IDs för transaktioner som har en bifogad faktura
    (matchad UpcomingTransaction med source_image_path satt). UI:t
    använder detta för att veta var den ska visa "Se faktura"-knappen."""
    from ..db.models import UpcomingTransaction as _UT
    rows = (
        session.query(_UT.matched_transaction_id)
        .filter(
            _UT.matched_transaction_id.is_not(None),
            _UT.source_image_path.is_not(None),
        )
        .all()
    )
    ids = sorted({r[0] for r in rows if r[0] is not None})
    return {"ids": ids}


@router.get("/transactions/{tx_id}/invoice")
def get_transaction_invoice(
    tx_id: int, session: Session = Depends(db),
):
    """Returnera bifogad faktura-PDF (eller bild) för en transaktion.

    Hittar den UpcomingTransaction som är matchad mot denna tx och där
    source_image_path är satt, och serverar filen. 404 om ingen faktura
    är bifogad."""
    from fastapi.responses import FileResponse
    from pathlib import Path
    from ..db.models import UpcomingTransaction

    tx = session.get(Transaction, tx_id)
    if tx is None:
        raise HTTPException(404, "Transaction not found")

    u = (
        session.query(UpcomingTransaction)
        .filter(UpcomingTransaction.matched_transaction_id == tx_id)
        .first()
    )
    if u is None or not u.source_image_path:
        raise HTTPException(404, "Ingen faktura bifogad till denna transaktion")

    p = Path(u.source_image_path)
    if not p.exists():
        raise HTTPException(404, "Fakturafilen finns inte längre på disk")
    ext = p.suffix.lower()
    media = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(ext, "application/octet-stream")
    return FileResponse(p, media_type=media, filename=p.name)
