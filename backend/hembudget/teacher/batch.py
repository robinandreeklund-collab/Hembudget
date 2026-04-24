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
)
from ..parsers.ekonomilabbet import (
    EkonomilabbetParseResult,
    parse_ekonomilabbet,
)
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

    batch = ScenarioBatch(
        student_id=student.id,
        year_month=year_month,
        seed=seed,
    )
    master_session.add(batch)
    master_session.flush()

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

    stats: dict = {
        "kind": parsed.kind,
        "imported_tx": 0,
        "skipped_tx": 0,
        "accounts_touched": [],
    }
    with scope_context(scope_key):
        with session_scope() as s:
            if parsed.kind == "kontoutdrag":
                _import_kontoutdrag(s, parsed, stats)
            elif parsed.kind == "lonespec":
                _import_lonespec(s, parsed, stats, artifact)
            elif parsed.kind == "lan_besked":
                _import_lan(s, parsed, stats, artifact)
            elif parsed.kind == "kreditkort_faktura":
                _import_kreditkort(s, parsed, stats, artifact)

    artifact.imported_at = datetime.utcnow()
    return {"ok": True, **stats}


def _ensure_account(
    s: Session, name: str, type_: str, bank: str = "ekonomilabbet",
    credit_limit: int | None = None, account_no: str | None = None,
) -> Account:
    acc = s.query(Account).filter(Account.name == name).first()
    if acc:
        return acc
    acc = Account(
        name=name, bank=bank, type=type_,
        currency="SEK",
        account_number=account_no,
        credit_limit=Decimal(credit_limit) if credit_limit else None,
        opening_balance=Decimal("0"),
    )
    s.add(acc)
    s.flush()
    return acc


def _import_kontoutdrag(
    s: Session, parsed: EkonomilabbetParseResult, stats: dict,
) -> None:
    acc = _ensure_account(
        s, "Lönekonto", "checking",
        account_no=parsed.account_no,
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


def _import_lonespec(
    s: Session, parsed: EkonomilabbetParseResult, stats: dict,
    artifact: BatchArtifact,
) -> None:
    """Lönespec sätter ingen ny tx i sig — kontoutdraget innehåller
    redan löneutbetalningen. Vi använder istället metadata för att
    upplysa eleven om bruttolön och berika lön-tx med kategori."""
    acc = _ensure_account(s, "Lönekonto", "checking")
    cat = s.query(Category).filter(Category.name == "Lön").first()
    if not cat:
        return
    if not parsed.transactions:
        return
    target_date = parsed.transactions[0].date
    target_amount = parsed.total_amount or parsed.transactions[0].amount
    matched = (
        s.query(Transaction)
        .filter(
            Transaction.account_id == acc.id,
            Transaction.date == target_date,
            Transaction.amount == target_amount,
        )
        .first()
    )
    if matched:
        if matched.category_id != cat.id:
            matched.category_id = cat.id
            matched.user_verified = True
            stats["imported_tx"] += 1
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
) -> None:
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
