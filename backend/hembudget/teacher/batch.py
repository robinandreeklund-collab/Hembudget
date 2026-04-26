"""Batch-skapande: tar en elev + månad, bygger scenario, renderar PDF:er
och lagrar dem som BatchArtifacts i master-DB:n.

Eleven importerar sedan dessa PDF:er en i taget via /student/batches/...
endpoints.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from ..db.base import session_scope
from ..db.models import (
    Account,
    Category,
    Loan,
    LoanPayment,
    Transaction,
    UpcomingTransaction,
    UpcomingTransactionLine,
)
from ..parsers.ekonomilabbet import (
    EkonomilabbetParseResult,
    parse_ekonomilabbet,
)
from ..config import settings
from ..school.engines import scope_context
from ..school.models import (
    BatchArtifact,
    ScenarioBatch,
    Student,
    StudentProfile,
)
from .pdfs import (
    render_kontoutdrag,
    render_kreditkort,
    render_lanbesked,
    render_lonespec,
)
from .scenario import build_scenario, MonthScenario

log = logging.getLogger(__name__)


def _save_artifact_to_disk(artifact: BatchArtifact) -> str:
    """Spara en artefakts PDF-bytes till data_dir/invoices/ och returnera
    sökvägen. Behövs för att UpcomingTransaction.source_image_path ska
    kunna peka på en fil som /upcoming/{id}/source kan servera.

    Idempotent — om filen redan finns för samma artefakt återanvänds den.
    """
    import hashlib as _h
    invoice_dir = settings.data_dir / "invoices"
    invoice_dir.mkdir(parents=True, exist_ok=True)
    short = _h.sha1(artifact.pdf_bytes or b"").hexdigest()[:8]
    safe = (artifact.filename or f"artifact_{artifact.id}.pdf").replace("/", "_")
    p = invoice_dir / f"batch_{artifact.id}_{short}_{safe}"
    if not p.exists():
        p.write_bytes(artifact.pdf_bytes or b"")
    return str(p)


def create_batch_for_student(
    master_session: Session,
    student: Student,
    year_month: str,
    overwrite: bool = False,
) -> ScenarioBatch:
    """Renderar PDF:er för månaden och sparar som BatchArtifacts.

    Idempotent: om batch redan finns för (student, year_month) och
    overwrite=False → returnerar den befintliga. Med overwrite=True
    raderas den gamla batchen + skapas en ny med samma seed.
    """
    if not student.profile:
        raise ValueError("Student saknar profil")

    existing = (
        master_session.query(ScenarioBatch)
        .filter(
            ScenarioBatch.student_id == student.id,
            ScenarioBatch.year_month == year_month,
        )
        .first()
    )
    if existing and not overwrite:
        return existing
    if existing and overwrite:
        master_session.delete(existing)
        master_session.flush()

    seed = abs(hash((student.id, year_month, "batch_v1"))) & 0xFFFFFFFF
    scenario = build_scenario(
        student_id=student.id,
        year_month=year_month,
        profile=student.profile,
        seed=seed,
    )

    # Spara facit för kategorisering-check (tx-beskrivning + datum +
    # belopp → elevens "rätt" kategori). Läraren använder detta för
    # att betygsätta elevens kategoriseringar.
    category_hints = []
    for t in scenario.transactions:
        if t.category_hint:
            category_hints.append({
                "description": t.description,
                "date": t.date.isoformat(),
                "amount": float(t.amount),
                "hint": t.category_hint,
            })
    for ce in scenario.card_events:
        if ce.category_hint:
            category_hints.append({
                "description": ce.description,
                "date": ce.date.isoformat(),
                "amount": -float(ce.amount),  # negativt pga kortköp
                "hint": ce.category_hint,
            })

    batch = ScenarioBatch(
        student_id=student.id,
        year_month=year_month,
        seed=seed,
        meta={"category_hints": category_hints},
    )
    master_session.add(batch)
    master_session.flush()

    # Skapa UpcomingTransaction för lön + återkommande fakturor i
    # elevens scope-DB — så att /upcoming visar "kommande poster" innan
    # eleven importerar bank-PDF:n. Dessa matchas sedan automatiskt mot
    # motsvarande bank-tx vid import.
    from ..school.engines import scope_context, scope_for_student
    scope_key = scope_for_student(student)
    BILL_DESCRIPTIONS_TO_UPCOMING = {
        "HYRA", "BRF AVGIFT", "DRIFT VILLA",
        "VATTENFALL", "FORTUM", "ELLEVIO", "TIBBER",
        "TELIA", "BAHNHOF", "COM HEM", "TELE2",
        "TELENOR ABONNEMANG", "TELIA MOBIL", "TRE",
        "IF FORSAKRING", "TRYGG HANSA", "FOLKSAM", "LANSFORSAKRINGAR",
        "BOLÅN", "BILLÅN", "CSN",
    }
    with scope_context(scope_key):
        with session_scope() as s:
            # Säkerställ lönekonto finns (för debit_account_id)
            lonekonto = s.query(Account).filter(
                Account.name == "Lönekonto"
            ).first()
            if not lonekonto:
                from decimal import Decimal as _Dec
                # Realistisk startposition så hyran kan dras innan lönen kommer.
                # Matchar DEFAULT_ACCOUNTS i fixtures.py.
                lonekonto = Account(
                    name="Lönekonto", bank="ekonomilabbet",
                    type="checking", currency="SEK",
                    opening_balance=_Dec("25000"),
                )
                s.add(lonekonto)
                s.flush()

            # Lön som planerad "income"
            if scenario.salary:
                sal = scenario.salary
                if not s.query(UpcomingTransaction).filter(
                    UpcomingTransaction.kind == "income",
                    UpcomingTransaction.expected_date == sal.pay_date,
                    UpcomingTransaction.amount == sal.net,
                ).first():
                    s.add(UpcomingTransaction(
                        kind="income",
                        name=f"Lön {sal.employer}",
                        amount=sal.net,
                        expected_date=sal.pay_date,
                        recurring_monthly=True,
                        source="scenario",
                        debit_account_id=lonekonto.id,
                        debit_date=sal.pay_date,
                    ))

            # Bills — identifiera via description-prefix
            for t in scenario.transactions:
                desc_u = t.description.upper()
                if not any(k in desc_u for k in BILL_DESCRIPTIONS_TO_UPCOMING):
                    continue
                if t.amount >= 0:
                    continue
                amount_pos = abs(t.amount)
                # Idempotens: skippa om redan finns
                if s.query(UpcomingTransaction).filter(
                    UpcomingTransaction.name == t.description,
                    UpcomingTransaction.expected_date == t.date,
                    UpcomingTransaction.amount == amount_pos,
                ).first():
                    continue
                s.add(UpcomingTransaction(
                    kind="bill",
                    name=t.description,
                    amount=amount_pos,
                    expected_date=t.date,
                    recurring_monthly=True,
                    source="scenario",
                    debit_account_id=lonekonto.id,
                    debit_date=t.date,
                    autogiro=True,
                ))

    sort_order = 0

    # 1. Lönespec (alltid)
    if scenario.salary:
        pdf = render_lonespec(scenario.salary, scenario)
        master_session.add(BatchArtifact(
            batch_id=batch.id,
            kind="lonespec",
            title=f"Lönespec {year_month} – {scenario.salary.employer}",
            filename=f"lonespec_{year_month}.pdf",
            sort_order=sort_order,
            pdf_bytes=pdf,
            meta={
                "employer": scenario.salary.employer,
                "net": float(scenario.salary.net),
                "gross": float(scenario.salary.gross),
            },
        ))
        sort_order += 1

    # 2. Kontoutdrag (alltid)
    pdf = render_kontoutdrag(scenario)
    master_session.add(BatchArtifact(
        batch_id=batch.id,
        kind="kontoutdrag",
        title=f"Kontoutdrag {year_month}",
        filename=f"kontoutdrag_{year_month}.pdf",
        sort_order=sort_order,
        pdf_bytes=pdf,
        meta={
            "tx_count": len(scenario.transactions),
            "account_no": scenario.bank_account_no,
        },
    ))
    sort_order += 1

    # 3. Lånebesked (en per lån)
    for loan in scenario.loans:
        pdf = render_lanbesked(loan, scenario)
        master_session.add(BatchArtifact(
            batch_id=batch.id,
            kind="lan_besked",
            title=f"Lånebesked {loan.loan_name} – {loan.lender}",
            filename=f"lan_{loan.loan_name.lower()}_{year_month}.pdf",
            sort_order=sort_order,
            pdf_bytes=pdf,
            meta={
                "loan_name": loan.loan_name,
                "lender": loan.lender,
                "interest": float(loan.interest),
                "amortization": float(loan.amortization),
            },
        ))
        sort_order += 1

    # 4. Kreditkortsfaktura (om kortköp finns)
    if scenario.card_events:
        pdf = render_kreditkort(scenario.card_events, scenario)
        master_session.add(BatchArtifact(
            batch_id=batch.id,
            kind="kreditkort_faktura",
            title=f"Kreditkortsfaktura {year_month}",
            filename=f"kreditkort_{year_month}.pdf",
            sort_order=sort_order,
            pdf_bytes=pdf,
            meta={
                "card_no": scenario.card_account_no,
                "total": float(sum(e.amount for e in scenario.card_events)),
                "event_count": len(scenario.card_events),
            },
        ))
        sort_order += 1

    master_session.flush()
    return batch


# ---------- Importering till elevens DB ----------

def import_artifact(
    master_session: Session,
    artifact: BatchArtifact,
    student: Student,
) -> dict:
    """Parse:a artefaktens PDF och skapa motsvarande poster i elevens
    scope-DB (eller familje-DB). Idempotent — kan köras igen utan att
    dubblera (transaktion-hash skyddar)."""
    from ..school.engines import scope_for_student
    parsed = parse_ekonomilabbet(artifact.pdf_bytes)
    if not parsed:
        return {"ok": False, "error": "Kunde inte parsa PDF:en"}

    scope_key = scope_for_student(student)

    # Facit-mappning för kategorisering: {(description, date, amount) → hint}
    facit: dict[tuple, str] = {}
    batch = artifact.batch
    if batch and batch.meta:
        for h in batch.meta.get("category_hints", []):
            key = (h["description"], h["date"], float(h["amount"]))
            facit[key] = h["hint"]

    stats: dict = {
        "kind": parsed.kind,
        "imported_tx": 0,
        "skipped_tx": 0,
        "accounts_touched": [],
    }
    with scope_context(scope_key):
        with session_scope() as s:
            if parsed.kind == "kontoutdrag":
                _import_kontoutdrag(s, parsed, stats, facit)
                _auto_match_upcoming(s)
            elif parsed.kind == "lonespec":
                _import_lonespec(s, parsed, stats, artifact)
            elif parsed.kind == "lan_besked":
                _import_lan(s, parsed, stats, artifact)
            elif parsed.kind == "kreditkort_faktura":
                _import_kreditkort(s, parsed, stats, artifact, facit)
                _create_credit_invoice_upcoming(s, parsed, artifact)

    artifact.imported_at = datetime.utcnow()
    return {"ok": True, **stats}


def _auto_match_upcoming(s: Session) -> None:
    """Matcha alla obetalda UpcomingTransactions mot bank-tx via den
    befintliga matchern. Körs efter import av kontoutdrag så elevens
    /upcoming-vy visar korrekt status."""
    try:
        from ..upcoming_match import UpcomingMatcher
        UpcomingMatcher(s).auto_match_all()
    except Exception:
        pass


def _create_credit_invoice_upcoming(
    s: Session, parsed: EkonomilabbetParseResult, artifact: BatchArtifact,
) -> None:
    """Skapa en UpcomingTransaction för kreditkortsfakturan så eleven
    ser förfallodagen i /upcoming. Beloppet = totalsumman."""
    if not parsed.total_amount or parsed.total_amount <= 0:
        return
    # Hitta kort-kontot
    card = s.query(Account).filter(Account.type == "credit").first()
    lonekonto = s.query(Account).filter(Account.type == "checking").first()
    if not lonekonto:
        return
    # Förfallodag ~28:e följande månad (standard för kort)
    if parsed.period:
        y, m = map(int, parsed.period.split("-"))
        import calendar
        from datetime import date as _date
        due_m = m + 1 if m < 12 else 1
        due_y = y if m < 12 else y + 1
        last = calendar.monthrange(due_y, due_m)[1]
        due = _date(due_y, due_m, min(28, last))
    else:
        from datetime import date as _date, timedelta
        due = _date.today() + timedelta(days=20)
    name = f"Kreditkortsfaktura {parsed.period or ''}".strip()
    existing = s.query(UpcomingTransaction).filter(
        UpcomingTransaction.name == name,
        UpcomingTransaction.expected_date == due,
    ).first()
    # Spara fakturans PDF till disk så /attachments kan visa den
    path = _save_artifact_to_disk(artifact)
    if existing:
        # Berika befintlig rad med path om den saknades (idempotent
        # uppgradering vid re-import).
        if existing.source_image_path is None:
            existing.source_image_path = path
        return
    s.add(UpcomingTransaction(
        kind="bill",
        name=name,
        amount=parsed.total_amount,
        expected_date=due,
        source="scenario",
        source_image_path=path,
        debit_account_id=lonekonto.id,
        debit_date=due,
        autogiro=True,
    ))


def _ensure_account(
    s: Session, name: str, type_: str, bank: str = "ekonomilabbet",
    credit_limit: int | None = None, account_no: str | None = None,
    opening_balance: Decimal | int = 0,
) -> Account:
    acc = s.query(Account).filter(Account.name == name).first()
    if acc:
        return acc
    acc = Account(
        name=name, bank=bank, type=type_,
        currency="SEK",
        account_number=account_no,
        credit_limit=Decimal(credit_limit) if credit_limit else None,
        opening_balance=Decimal(str(opening_balance or 0)),
    )
    s.add(acc)
    s.flush()
    return acc


def _import_kontoutdrag(
    s: Session, parsed: EkonomilabbetParseResult, stats: dict,
    facit: dict | None = None,
) -> None:
    # facit-argumentet tas emot för bakåtkompat men används INTE — facit
    # slås upp direkt mot batch.meta i /teacher/facit-endpointen, så
    # vi undviker att skriva över elevens egna notes-fält.
    _ = facit
    acc = _ensure_account(
        s, "Lönekonto", "checking",
        account_no=parsed.account_no,
        opening_balance=25_000,
    )
    stats["accounts_touched"].append(acc.name)
    # Försäkra att Sparkonto + Kreditkort också existerar — matchar
    # DEFAULT_ACCOUNTS i fixtures.py. Behövs eftersom kontoutdraget har
    # 'ÖVERFÖRING SPARKONTO'-rader (vi parar dem på Sparkonto nedan) och
    # kreditkortsfakturan vid senare import behöver Kreditkort att
    # landa på.
    sparkonto = _ensure_account(
        s, "Sparkonto", "savings", opening_balance=5_000,
    )
    _ensure_account(
        s, "Kreditkort", "credit", credit_limit=40_000, opening_balance=0,
    )

    existing_hashes = {
        h for (h,) in s.query(Transaction.hash).filter(
            Transaction.account_id == acc.id
        ).all()
    }
    new_transfer_txs: list[Transaction] = []
    for raw in parsed.transactions:
        h = raw.stable_hash(acc.id)
        if h in existing_hashes:
            stats["skipped_tx"] += 1
            continue
        existing_hashes.add(h)
        tx = Transaction(
            account_id=acc.id,
            date=raw.date,
            amount=raw.amount,
            currency="SEK",
            raw_description=raw.description,
            normalized_merchant=raw.description.split()[0].title()
                if raw.description else None,
            hash=h,
            user_verified=False,
        )
        s.add(tx)
        stats["imported_tx"] += 1
        # Spara referens om det är en sparkonto-överföring så vi kan
        # para den nedan
        if (
            raw.description
            and "ÖVERFÖRING SPARKONTO" in raw.description.upper()
            and raw.amount < 0
        ):
            new_transfer_txs.append(tx)
    s.flush()

    # Para sparkonto-överföringar: skapa motsvarande +rad på Sparkonto
    # och länka via transfer_pair_id. Annars försvinner pengarna —
    # Lönekonto -2000 utan motpar = ledger ur balans.
    sparkonto_existing = {
        h for (h,) in s.query(Transaction.hash).filter(
            Transaction.account_id == sparkonto.id
        ).all()
    }
    for src_tx in new_transfer_txs:
        # Idempotent hash baserat på (sparkonto, datum, belopp, src-id)
        pair_hash = f"transfer_pair_{sparkonto.id}_{src_tx.id}"[:64]
        if pair_hash in sparkonto_existing:
            continue
        pair = Transaction(
            account_id=sparkonto.id,
            date=src_tx.date,
            amount=-src_tx.amount,  # spegelvänd belopp
            currency="SEK",
            raw_description="ÖVERFÖRING FRÅN LÖNEKONTO",
            normalized_merchant="Överföring",
            hash=pair_hash,
            user_verified=False,
            is_transfer=True,
            transfer_pair_id=src_tx.id,
        )
        s.add(pair)
        s.flush()
        # Bind tillbaka från src till pair
        src_tx.is_transfer = True
        src_tx.transfer_pair_id = pair.id
        stats["imported_tx"] += 1
        if "Sparkonto" not in stats["accounts_touched"]:
            stats["accounts_touched"].append("Sparkonto")


def _import_lonespec(
    s: Session, parsed: EkonomilabbetParseResult, stats: dict,
    artifact: BatchArtifact,
) -> None:
    """Lönespec sätter ingen ny tx i sig — kontoutdraget innehåller
    redan löneutbetalningen. Vi använder istället metadata för att
    upplysa eleven om bruttolön och berika lön-tx med kategori.

    Skapar dessutom en UpcomingTransaction(kind=income) med PDF:en
    sparad till disk + source_image_path satt — så lönespecen syns
    under /attachments (Bildunderlag) som en riktig bilaga."""
    acc = _ensure_account(s, "Lönekonto", "checking")
    cat = s.query(Category).filter(Category.name == "Lön").first()
    if not parsed.transactions:
        return
    target_date = parsed.transactions[0].date
    target_amount = parsed.total_amount or parsed.transactions[0].amount

    # Berika existerande lön-tx med kategori
    matched = (
        s.query(Transaction)
        .filter(
            Transaction.account_id == acc.id,
            Transaction.date == target_date,
            Transaction.amount == target_amount,
        )
        .first()
    )
    if matched and cat and matched.category_id != cat.id:
        matched.category_id = cat.id
        matched.user_verified = True
        stats["imported_tx"] += 1

    # Skapa Upcoming-bilaga så PDF:en syns i /attachments (Bildunderlag).
    # Idempotent — om vi redan har en lönespec-Upcoming för samma
    # datum + belopp, skippa.
    artifact_meta = artifact.meta or {}
    employer = artifact_meta.get("employer", "Arbetsgivare")
    name = f"Lönespec {employer}"
    existing = s.query(UpcomingTransaction).filter(
        UpcomingTransaction.kind == "income",
        UpcomingTransaction.expected_date == target_date,
        UpcomingTransaction.amount == target_amount,
        UpcomingTransaction.source == "salary_pdf",
    ).first()
    if existing is None:
        path = _save_artifact_to_disk(artifact)
        s.add(UpcomingTransaction(
            kind="income",
            name=name,
            amount=target_amount,
            expected_date=target_date,
            recurring_monthly=True,
            source="salary_pdf",
            source_image_path=path,
            debit_account_id=acc.id,
            debit_date=target_date,
            matched_transaction_id=matched.id if matched else None,
        ))
    elif existing.source_image_path is None:
        # Befintlig upcoming utan path — lägg till path:en (idempotent
        # uppgradering för historik).
        existing.source_image_path = _save_artifact_to_disk(artifact)

    stats["accounts_touched"].append(acc.name)


def _import_lan(
    s: Session, parsed: EkonomilabbetParseResult,
    stats: dict, artifact: BatchArtifact,
) -> None:
    """Skapa Loan om det är första gången, annars lägg till LoanPayment."""
    meta = parsed.meta
    loan_name = artifact.meta.get("loan_name", "Bolån") if artifact.meta else "Bolån"
    lender = meta.get("lender") or (
        artifact.meta.get("lender") if artifact.meta else "Bank"
    )
    loan = (
        s.query(Loan).filter(Loan.name == loan_name, Loan.lender == lender)
        .first()
    )
    if not loan:
        # Approximera principal från restskuld + amortering
        principal = (
            Decimal(str(meta.get("remaining", 0)))
            + Decimal(str(meta.get("amortization", 0)))
        )
        loan = Loan(
            name=loan_name,
            lender=lender,
            principal_amount=principal if principal > 0 else Decimal("1000000"),
            current_balance_at_creation=
                principal if principal > 0 else Decimal("1000000"),
            start_date=parsed.transactions[0].date if parsed.transactions
                else datetime.utcnow().date(),
            interest_rate=meta.get("rate_pct", 4.0) / 100,
            binding_type="rörlig",
            amortization_monthly=Decimal(str(meta.get("amortization", 0)))
                or None,
        )
        s.add(loan)
        s.flush()
    # Säkerställ att kontot för betalning finns
    acc = _ensure_account(s, "Lönekonto", "checking")
    # Knyt betalningen till en existerande tx om sådan finns
    if parsed.transactions:
        target = parsed.transactions[0]
        tx = (
            s.query(Transaction)
            .filter(
                Transaction.account_id == acc.id,
                Transaction.date == target.date,
                Transaction.amount == target.amount,
            )
            .first()
        )
        if tx:
            interest_amt = Decimal(str(meta.get("interest", 0)))
            amort_amt = Decimal(str(meta.get("amortization", 0)))
            for amount, ptype in [
                (interest_amt, "interest"),
                (amort_amt, "amortization"),
            ]:
                if amount > 0 and not s.query(LoanPayment).filter(
                    LoanPayment.transaction_id == tx.id,
                    LoanPayment.payment_type == ptype,
                ).first():
                    s.add(LoanPayment(
                        loan_id=loan.id,
                        transaction_id=tx.id,
                        date=tx.date,
                        amount=amount,
                        payment_type=ptype,
                    ))
                    stats["imported_tx"] += 1
    stats["accounts_touched"].append(loan.name)


def _import_kreditkort(
    s: Session, parsed: EkonomilabbetParseResult,
    stats: dict, artifact: BatchArtifact,
    facit: dict | None = None,
) -> None:
    _ = facit  # Facit lagras i batch.meta, inte i tx.notes — se _import_kontoutdrag
    card_no = parsed.account_no or "Ekonomilabbet Kort"
    acc = _ensure_account(
        s, "Kreditkort", "credit",
        bank="ekonomilabbet_kort",
        credit_limit=40_000,
        account_no=card_no,
    )
    stats["accounts_touched"].append(acc.name)

    existing_hashes = {
        h for (h,) in s.query(Transaction.hash).filter(
            Transaction.account_id == acc.id
        ).all()
    }
    for raw in parsed.transactions:
        h = raw.stable_hash(acc.id)
        if h in existing_hashes:
            stats["skipped_tx"] += 1
            continue
        existing_hashes.add(h)
        s.add(Transaction(
            account_id=acc.id,
            date=raw.date,
            amount=raw.amount,
            currency="SEK",
            raw_description=raw.description,
            normalized_merchant=raw.description.split()[0].title()
                if raw.description else None,
            hash=h,
            user_verified=False,
        ))
        stats["imported_tx"] += 1
