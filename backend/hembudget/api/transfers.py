from __future__ import annotations

import hashlib
from datetime import date as _date_type, date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db.models import Account, DismissedTransferSuggestion, Transaction
from ..transfers.detector import TransferDetector
from .deps import db, require_auth


def _dismissal_key(a: int, b: int) -> tuple[int, int]:
    """Par-nyckel oberoende av ordning — tabellen lagrar (min, max)."""
    return (a, b) if a < b else (b, a)

router = APIRouter(prefix="/transfers", tags=["transfers"], dependencies=[Depends(require_auth)])


def _tx_out(tx: Transaction, accounts: dict[int, Account]) -> dict:
    acc = accounts.get(tx.account_id)
    return {
        "id": tx.id,
        "account_id": tx.account_id,
        "account_name": acc.name if acc else None,
        "date": tx.date.isoformat(),
        "amount": float(tx.amount),
        "description": tx.raw_description,
        "is_transfer": tx.is_transfer,
        "transfer_pair_id": tx.transfer_pair_id,
    }


@router.get("/paired")
def list_paired(session: Session = Depends(db)) -> dict:
    """Alla transaktioner där båda sidor är markerade som transfer och parade."""
    rows = (
        session.query(Transaction)
        .filter(
            Transaction.is_transfer.is_(True),
            Transaction.transfer_pair_id.is_not(None),
            Transaction.amount < 0,
        )
        .order_by(Transaction.date.desc())
        .all()
    )
    accounts = {a.id: a for a in session.query(Account).all()}
    tx_by_id = {t.id: t for t in session.query(Transaction).all()}

    pairs = []
    for src in rows:
        dst = tx_by_id.get(src.transfer_pair_id)
        if dst is None:
            continue
        pairs.append({
            "source": _tx_out(src, accounts),
            "destination": _tx_out(dst, accounts),
        })
    return {"pairs": pairs, "count": len(pairs)}


@router.get("/unpaired")
def list_unpaired(session: Session = Depends(db)) -> dict:
    """Markerade som transfer men utan motpart — kräver granskning."""
    rows = (
        session.query(Transaction)
        .filter(
            Transaction.is_transfer.is_(True),
            Transaction.transfer_pair_id.is_(None),
        )
        .order_by(Transaction.date.desc())
        .all()
    )
    accounts = {a.id: a for a in session.query(Account).all()}
    return {
        "transactions": [_tx_out(t, accounts) for t in rows],
        "count": len(rows),
    }


@router.get("/suggestions")
def list_suggestions(
    date_tolerance_days: int = 5,
    amount_tolerance: float = 0.01,
    session: Session = Depends(db),
) -> dict:
    """Okategoriserade rader som SER UT som möjliga transfers — en negativ
    på ett konto och en positiv med liknande belopp på ett annat konto."""
    account_ids = [a.id for a in session.query(Account).all()]
    if len(account_ids) < 2:
        return {"suggestions": []}

    accounts = {a.id: a for a in session.query(Account).all()}
    unpaired = (
        session.query(Transaction)
        .filter(
            Transaction.account_id.in_(account_ids),
            Transaction.transfer_pair_id.is_(None),
            Transaction.is_transfer.is_(False),
        )
        .all()
    )

    tol = Decimal(str(amount_tolerance))
    suggestions = []
    seen: set[tuple[int, int]] = set()
    # Användaren har klickat bort vissa par — de ska inte dyka upp igen.
    dismissed: set[tuple[int, int]] = {
        (r.tx_a_id, r.tx_b_id)
        for r in session.query(DismissedTransferSuggestion).all()
    }

    for src in unpaired:
        if src.amount >= 0:
            continue
        abs_amt = -src.amount
        low = abs_amt * (Decimal("1") - tol)
        high = abs_amt * (Decimal("1") + tol)
        for dst in unpaired:
            if dst.amount <= 0 or dst.account_id == src.account_id:
                continue
            if not (low <= dst.amount <= high):
                continue
            if abs((dst.date - src.date).days) > date_tolerance_days:
                continue
            key = tuple(sorted((src.id, dst.id)))
            if key in seen:
                continue
            if _dismissal_key(src.id, dst.id) in dismissed:
                continue
            seen.add(key)
            suggestions.append({
                "source": _tx_out(src, accounts),
                "destination": _tx_out(dst, accounts),
                "date_diff_days": abs((dst.date - src.date).days),
                "amount_diff": float(abs(dst.amount - abs_amt)),
            })

    # Sortera: mest uppenbara först (samma dag + exakt belopp)
    suggestions.sort(key=lambda s: (s["date_diff_days"], s["amount_diff"]))
    return {"suggestions": suggestions[:100], "count": len(suggestions)}


class LinkIn(BaseModel):
    tx_a_id: int
    tx_b_id: int


class DismissIn(BaseModel):
    src_id: int
    dst_id: int


@router.post("/suggestions/dismiss")
def dismiss_suggestion(payload: DismissIn, session: Session = Depends(db)) -> dict:
    """Ta bort ett föreslaget transfer-par så det inte dyker upp igen.
    Lagrar (min_id, max_id) så ordning spelar ingen roll."""
    a, b = _dismissal_key(payload.src_id, payload.dst_id)
    existing = (
        session.query(DismissedTransferSuggestion)
        .filter_by(tx_a_id=a, tx_b_id=b)
        .first()
    )
    if existing is None:
        session.add(DismissedTransferSuggestion(tx_a_id=a, tx_b_id=b))
        session.flush()
    return {"dismissed": True, "tx_a_id": a, "tx_b_id": b}


@router.post("/link")
def link_pair(payload: LinkIn, session: Session = Depends(db)) -> dict:
    try:
        TransferDetector(session).link_manual(payload.tx_a_id, payload.tx_b_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"ok": True}


class BulkLinkIn(BaseModel):
    pairs: list[LinkIn]


@router.post("/diagnose-pairing")
def diagnose_pairing(payload: dict, session: Session = Depends(db)) -> dict:
    """Per tx_id: förklara exakt varför auto-pair missar den.

    Body: `{"tx_ids": [...]}`. Returnerar lista av
    `{tx_id, amount, date, reason, partner_candidates}`.
    Används när 'Auto-para uppenbara' returnerar scanned=0 trots att
    åtgärda-listan visar rader.
    """
    from datetime import timedelta

    tx_ids = payload.get("tx_ids") or []
    if not isinstance(tx_ids, list) or not tx_ids:
        raise HTTPException(400, "tx_ids (list) krävs i body")

    AMOUNT_EPS = Decimal("0.01")
    DATE_EPS = 3

    out: list[dict] = []
    for tid in tx_ids:
        t = session.get(Transaction, tid)
        if t is None:
            out.append({"tx_id": tid, "reason": "tx saknas i DB"})
            continue
        base = {
            "tx_id": t.id,
            "date": t.date.isoformat(),
            "amount": float(t.amount),
            "description": t.raw_description,
            "account_id": t.account_id,
            "category_id": t.category_id,
            "is_transfer": t.is_transfer,
            "transfer_pair_id": t.transfer_pair_id,
        }
        if t.category_id is not None:
            out.append({**base, "reason": "redan kategoriserad"})
            continue
        if t.transfer_pair_id is not None:
            out.append({**base, "reason": "redan parad (transfer_pair_id satt)"})
            continue
        if t.is_transfer:
            out.append({**base, "reason": "is_transfer=True men ingen pair_id — orphan transfer"})
            continue
        if t.amount >= 0:
            # Positiv — partner vi söker är någon negativ med samma belopp
            abs_amt = t.amount
        else:
            abs_amt = -t.amount

        partners = (
            session.query(Transaction)
            .filter(
                Transaction.account_id != t.account_id,
                Transaction.amount >= (abs_amt if t.amount < 0 else -abs_amt) - AMOUNT_EPS,
                Transaction.amount <= (abs_amt if t.amount < 0 else -abs_amt) + AMOUNT_EPS,
                Transaction.date >= t.date - timedelta(days=DATE_EPS),
                Transaction.date <= t.date + timedelta(days=DATE_EPS),
                Transaction.transfer_pair_id.is_(None),
                Transaction.id != t.id,
            )
            .all()
        )
        # Om src är negativ ska partner vara positiv (och tvärtom)
        if t.amount < 0:
            partners = [p for p in partners if p.amount > 0]
        else:
            partners = [p for p in partners if p.amount < 0]
        partner_info = [
            {
                "tx_id": p.id,
                "account_id": p.account_id,
                "date": p.date.isoformat(),
                "amount": float(p.amount),
                "description": p.raw_description,
            }
            for p in partners
        ]
        if not partners:
            reason = "ingen motpart med samma belopp inom ±3 dagar på annat konto"
        elif len(partners) > 1:
            reason = f"{len(partners)} kandidater — ambigous"
        else:
            reason = "OK, kan paras"
        out.append({**base, "reason": reason, "partner_candidates": partner_info})
    return {"rows": out}


@router.post("/auto-pair-uncategorized")
def auto_pair_uncategorized(
    payload: dict, session: Session = Depends(db),
) -> dict:
    """Scanna alla okategoriserade rader inom en period och para de som
    har EXAKT en motpart med samma datum + exakt belopp på ett annat
    konto. Mer aggressiv än detect_internal_transfers som har fler
    säkerhetsvillkor (BG-match, kontonummer i description, osv.) —
    denna tittar bara på date+amount+olika_konto.

    Body: `{"year": 2026}` eller `{"month": "2026-04"}`.
    Body: `{"tx_ids": [...]}` för att begränsa till specifika rader
    (t.ex. de som syns i huvudbokens åtgärda-list).

    Mjuka filter på source-sidan: vi kräver ENDAST att raden är
    okategoriserad. is_transfer och transfer_pair_id kollas per rad —
    om raden redan är parad skippas den tyst (inget att göra). Så
    källsetet matchar vad åtgärda-listan visar.

    Returnerar `{"linked": N, "ambiguous": [tx_id, ...], "no_match": [...]}`.
    """
    from datetime import date as _date

    year = payload.get("year")
    month = payload.get("month")
    tx_ids = payload.get("tx_ids")

    q = session.query(Transaction).filter(
        Transaction.category_id.is_(None),
    )
    if tx_ids and isinstance(tx_ids, list):
        q = q.filter(Transaction.id.in_(tx_ids))
    elif month:
        y, m = map(int, month.split("-"))
        start = _date(y, m, 1)
        end = _date(y + 1, 1, 1) if m == 12 else _date(y, m + 1, 1)
        q = q.filter(Transaction.date >= start, Transaction.date < end)
    elif year:
        q = q.filter(
            Transaction.date >= _date(year, 1, 1),
            Transaction.date < _date(year + 1, 1, 1),
        )

    candidates = q.all()
    linked = 0
    ambiguous: list[int] = []
    no_match: list[int] = []
    claimed: set[int] = set()
    detector = TransferDetector(session)

    # SQLite kan lagra Decimal som REAL → exakt == kan missa pga float-
    # precision. Använd ±0.01 kr-fönster + ±3 dagar för att fånga
    # öresavrundning och autogiro-dröjsmål (en transfer kan ligga på
    # fredag på avsändande sida och måndag på mottagande — 3 dagar).
    AMOUNT_EPS = Decimal("0.01")
    DATE_EPS_DAYS = 3

    from datetime import timedelta

    # Inkludera ALLA okategoriserade rader på alla konton som potentiella
    # motparter — inte bara de i candidates-listan, eftersom partnern
    # ofta finns på ett kortkonto och är felklassad som "Inkomst" (= har
    # category_id satt). Vi söker per src bland ALLA oparade rader.
    for src in candidates:
        if src.id in claimed or src.amount >= 0:
            continue
        # Om raden redan har en partner eller är markerad som transfer →
        # inget att göra, skippa tyst. Vi tar INTE bort filtret i queryn
        # så scanned räknas rätt (matchar åtgärda-listan).
        if src.transfer_pair_id is not None or src.is_transfer:
            continue
        abs_amt = -src.amount
        partners = (
            session.query(Transaction)
            .filter(
                Transaction.account_id != src.account_id,
                Transaction.amount >= abs_amt - AMOUNT_EPS,
                Transaction.amount <= abs_amt + AMOUNT_EPS,
                Transaction.date >= src.date - timedelta(days=DATE_EPS_DAYS),
                Transaction.date <= src.date + timedelta(days=DATE_EPS_DAYS),
                Transaction.transfer_pair_id.is_(None),
                Transaction.id != src.id,
            )
            .all()
        )
        partners = [p for p in partners if p.id not in claimed]
        if len(partners) == 0:
            no_match.append(src.id)
            continue
        if len(partners) > 1:
            # Försök föredra exakt samma datum → kan reda ut tvetydighet
            same_day = [p for p in partners if p.date == src.date]
            if len(same_day) == 1:
                partners = same_day
            else:
                ambiguous.append(src.id)
                continue
        dst = partners[0]
        try:
            detector.link_manual(src.id, dst.id)
            claimed.add(src.id)
            claimed.add(dst.id)
            linked += 1
        except ValueError:
            ambiguous.append(src.id)

    return {
        "linked": linked,
        "ambiguous_count": len(ambiguous),
        "ambiguous": ambiguous,
        "no_match_count": len(no_match),
        "scanned": len(candidates),
    }


@router.post("/link-bulk")
def link_pairs_bulk(payload: BulkLinkIn, session: Session = Depends(db)) -> dict:
    """Para ihop många par i ett svep — användsfall: alla "100 % säkra"
    förslag (samma dag + exakt belopp). Hoppar över par som redan har
    pair_id satt (idempotent), rapporterar fel per par utan att kasta.
    """
    detector = TransferDetector(session)
    linked = 0
    skipped = 0
    errors: list[dict] = []
    for p in payload.pairs:
        # Skippa om någon sida redan parad — undviker att skriva över
        # tidigare manuella matchningar som användaren redan godkänt.
        a = session.get(Transaction, p.tx_a_id)
        b = session.get(Transaction, p.tx_b_id)
        if a is None or b is None:
            errors.append({"pair": [p.tx_a_id, p.tx_b_id], "error": "not_found"})
            continue
        if a.transfer_pair_id is not None or b.transfer_pair_id is not None:
            skipped += 1
            continue
        try:
            detector.link_manual(p.tx_a_id, p.tx_b_id)
            linked += 1
        except ValueError as exc:
            errors.append({"pair": [p.tx_a_id, p.tx_b_id], "error": str(exc)})
    return {"linked": linked, "skipped": skipped, "errors": errors}


@router.post("/unlink/{tx_id}")
def unlink(tx_id: int, session: Session = Depends(db)) -> dict:
    TransferDetector(session).unlink(tx_id)
    return {"ok": True}


@router.post("/batch-create-counterparts")
def batch_create_counterparts(
    payload: dict, session: Session = Depends(db),
) -> dict:
    """Skapa motsvarigheter för ALLA orphan-transfers mot ett valt konto.

    Typiskt användsfall: du har massor av insättningar från partnerns
    sida som flaggats som transfer utan motpart. Välj hennes inkognito-
    konto, klicka "Skapa motsvarande för alla" → systemet gör det i ett
    svep.

    Body: `{"target_account_id": int, "tx_ids"?: list[int]}`. Om tx_ids
    är None körs det för ALLA orphans (is_transfer=True, inget pair-id,
    och inte redan på target-kontot).
    """
    import hashlib

    target_id = payload.get("target_account_id")
    if not isinstance(target_id, int):
        raise HTTPException(400, "target_account_id (int) krävs i body")
    target = session.get(Account, target_id)
    if target is None:
        raise HTTPException(404, "Target account not found")

    tx_ids_raw = payload.get("tx_ids")
    q = (
        session.query(Transaction)
        .filter(
            Transaction.is_transfer.is_(True),
            Transaction.transfer_pair_id.is_(None),
            Transaction.account_id != target_id,
        )
    )
    if tx_ids_raw:
        q = q.filter(Transaction.id.in_(tx_ids_raw))
    orphans = q.all()

    created_ids: list[int] = []
    detector = TransferDetector(session)
    for tx in orphans:
        counterpart_amount = -tx.amount
        key = f"batch-counter|{target_id}|{tx.date}|{counterpart_amount}|from-{tx.id}"
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        counter = Transaction(
            account_id=target_id,
            date=tx.date,
            amount=counterpart_amount,
            currency=tx.currency,
            raw_description=f"Motpart till {tx.raw_description or 'tx #' + str(tx.id)}",
            hash=h,
        )
        session.add(counter)
        session.flush()
        try:
            detector.link_manual(tx.id, counter.id)
            created_ids.append(counter.id)
        except ValueError:
            # Något gick fel med pairing — rulla inte tillbaka hela batchen
            continue
    session.flush()
    return {
        "target_account_id": target_id,
        "target_account_name": target.name,
        "orphans_processed": len(orphans),
        "counterparts_created": len(created_ids),
        "counterpart_tx_ids": created_ids,
    }


@router.post("/{tx_id}/create-counterpart")
def create_counterpart(
    tx_id: int, payload: dict, session: Session = Depends(db),
) -> dict:
    """Skapa en motsatt-tecknad Transaction på ett annat konto och para
    ihop de som överföring. Används för att manuellt dokumentera
    partnerns sida när man bara ser en orphan-transfer på gemensamt
    kontot.

    Body: `{account_id: int, description?: str, date?: YYYY-MM-DD}`.
    Datumet defaultar till source-tx:s datum.
    """
    import hashlib
    from datetime import date as _date

    tx = session.get(Transaction, tx_id)
    if tx is None:
        raise HTTPException(404, "Transaction not found")
    account_id = payload.get("account_id")
    if not isinstance(account_id, int):
        raise HTTPException(400, "account_id (int) krävs")
    if account_id == tx.account_id:
        raise HTTPException(400, "Motparten måste vara ett ANNAT konto")
    acc = session.get(Account, account_id)
    if acc is None:
        raise HTTPException(404, "Target account not found")

    date_s = payload.get("date")
    if date_s:
        try:
            tx_date = _date.fromisoformat(date_s)
        except ValueError:
            raise HTTPException(400, f"Ogiltigt datum: {date_s}") from None
    else:
        tx_date = tx.date

    description = (payload.get("description") or "").strip()
    if not description:
        description = f"Motpart till tx #{tx.id}"

    counterpart_amount = -tx.amount  # motsatt tecken
    key = f"counterpart|{account_id}|{tx_date}|{counterpart_amount}|from-tx-{tx.id}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()

    counter = Transaction(
        account_id=account_id,
        date=tx_date,
        amount=counterpart_amount,
        currency=tx.currency,
        raw_description=description,
        hash=h,
    )
    session.add(counter)
    session.flush()

    # Para ihop dem som transfer
    TransferDetector(session).link_manual(tx.id, counter.id)
    session.flush()

    return {
        "source_tx_id": tx.id,
        "counterpart_tx_id": counter.id,
        "account_id": account_id,
        "amount": float(counterpart_amount),
        "paired_as_transfer": True,
    }


class CreateTransferIn(BaseModel):
    """Proaktiv elev-överföring mellan egna konton.

    Skapar två länkade Transactions i samma DB-transaktion. Saldot
    uppdateras direkt eftersom api/balances.py räknar live."""

    from_account_id: int
    to_account_id: int
    amount: Decimal = Field(gt=0)
    date: Optional[_date_type] = None
    description: Optional[str] = None
    idempotency_key: Optional[str] = None


def _balance_for(session: Session, account_id: int) -> Decimal:
    """Live saldo: opening_balance (om satt) + summa transaktioner från
    opening_balance_date och framåt. Speglar logiken i api/balances.py
    men hålls lokal för att undvika cyklisk import."""
    acc = session.get(Account, account_id)
    if acc is None:
        return Decimal("0")
    base = acc.opening_balance or Decimal("0")
    q = session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.account_id == account_id,
    )
    if acc.opening_balance_date is not None:
        q = q.filter(Transaction.date >= acc.opening_balance_date)
    total = q.scalar() or Decimal("0")
    if not isinstance(total, Decimal):
        total = Decimal(str(total))
    return base + total


@router.post("/create")
def create_transfer(payload: CreateTransferIn, session: Session = Depends(db)) -> dict:
    """Skapa en proaktiv överföring mellan två egna konton.

    Två Transaction-rader skapas i samma session:
      - avsändaren: amount = -X, is_transfer=True
      - mottagaren: amount = +X, is_transfer=True
    transfer_pair_id sätts korsvis. Saldot räknas live i balances.py."""
    if payload.from_account_id == payload.to_account_id:
        raise HTTPException(400, "Från- och till-konto måste vara olika")

    src = session.get(Account, payload.from_account_id)
    dst = session.get(Account, payload.to_account_id)
    if src is None:
        raise HTTPException(404, "Avsändarkonto saknas")
    if dst is None:
        raise HTTPException(404, "Mottagarkonto saknas")

    amount = payload.amount
    if amount <= 0:
        raise HTTPException(400, "Belopp måste vara större än noll")

    # Sparkonto får inte gå negativt — pedagogisk regel.
    if src.type == "savings":
        balance = _balance_for(session, src.id)
        if balance - amount < 0:
            raise HTTPException(
                400, f"Sparkontot skulle gå minus ({balance - amount} kr)",
            )

    tx_date = payload.date or date.today()
    description = (payload.description or "").strip()
    if not description:
        description = f"Överföring till {dst.name}"

    # Idempotency: samma key får aldrig skapa två överföringar. Lagra som
    # del av hash-strängen så UNIQUE-constrain på (tenant_id, hash) fångar
    # dubblar utan ny tabell.
    idem = (payload.idempotency_key or "").strip()
    if idem:
        existing = (
            session.query(Transaction)
            .filter(Transaction.hash == f"transfer-{idem}-out")
            .first()
        )
        if existing is not None:
            pair = (
                session.get(Transaction, existing.transfer_pair_id)
                if existing.transfer_pair_id
                else None
            )
            if existing.amount < 0:
                src_tx, dst_tx = existing, pair
            else:
                src_tx, dst_tx = pair, existing
            return {
                "ok": True,
                "idempotent": True,
                "source_tx_id": src_tx.id if src_tx else None,
                "destination_tx_id": dst_tx.id if dst_tx else None,
            }

    # Hash som är queryable för idempotency. Lagras direkt — inte sha256:at.
    # UNIQUE (tenant_id, hash) garanterar unikhet per scope.
    key = idem or f"{tx_date.isoformat()}-{src.id}-{dst.id}-{amount}"
    src_hash = f"transfer-{key}-out"
    dst_hash = f"transfer-{key}-in"

    src_tx = Transaction(
        account_id=src.id,
        date=tx_date,
        amount=-amount,
        currency=src.currency or "SEK",
        raw_description=description,
        is_transfer=True,
        hash=src_hash,
    )
    dst_tx = Transaction(
        account_id=dst.id,
        date=tx_date,
        amount=amount,
        currency=dst.currency or "SEK",
        raw_description=f"Överföring från {src.name}",
        is_transfer=True,
        hash=dst_hash,
    )
    session.add_all([src_tx, dst_tx])
    session.flush()
    src_tx.transfer_pair_id = dst_tx.id
    dst_tx.transfer_pair_id = src_tx.id
    session.flush()

    return {
        "ok": True,
        "source_tx_id": src_tx.id,
        "destination_tx_id": dst_tx.id,
        "amount": float(amount),
        "from_account_id": src.id,
        "to_account_id": dst.id,
        "from_balance_after": float(_balance_for(session, src.id)),
        "to_balance_after": float(_balance_for(session, dst.id)),
        "date": tx_date.isoformat(),
    }
