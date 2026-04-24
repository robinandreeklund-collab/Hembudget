"""Status-utvärdering för Assignments.

Kör mot elevens scope-DB (öppnas via scope_context från caller). Varje
"kind" har en checker som returnerar (status, progress_text).

Status: "not_started" | "in_progress" | "completed"
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from ..db.base import session_scope
from ..db.models import (
    Account,
    Budget,
    Loan,
    Transaction,
)
from ..school.engines import scope_context, scope_for_student


Status = Literal["not_started", "in_progress", "completed"]


@dataclass
class CheckResult:
    status: Status
    progress: str
    detail: dict | None = None


def evaluate(assignment, student) -> CheckResult:
    """Kör rätt checker baserat på assignment.kind."""
    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            kind = assignment.kind
            if kind == "set_budget":
                return _check_set_budget(s, assignment)
            if kind == "import_batch":
                return _check_import_batch(s, assignment, student)
            if kind == "balance_month":
                return _check_balance_month(s, assignment)
            if kind == "review_loan":
                return _check_review_loan(s)
            if kind == "categorize_all":
                return _check_categorize_all(s, assignment)
            if kind == "save_amount":
                return _check_save_amount(s, assignment)
            # free_text: bara manuellt — alltid "in_progress" tills läraren
            # markerar i UI:n. För nu returnerar vi "in_progress".
            return CheckResult("in_progress", "Bedöms manuellt av läraren")


def _check_set_budget(s: Session, assignment) -> CheckResult:
    month = assignment.target_year_month
    if not month:
        # Om ingen specifik månad: räcker att ÅTMINSTONE en månad har budget
        any_budget = s.query(Budget).first() is not None
        return CheckResult(
            "completed" if any_budget else "not_started",
            "Budget satt" if any_budget else "Ingen budget satt än",
        )
    rows = s.query(Budget).filter(Budget.month == month).count()
    if rows == 0:
        return CheckResult("not_started", f"Ingen budget för {month}")
    if rows < 5:
        return CheckResult(
            "in_progress", f"{rows} kategorier satta, sätt fler för fullständig budget"
        )
    return CheckResult("completed", f"{rows} budgetposter satta för {month}")


def _check_import_batch(s: Session, assignment, student) -> CheckResult:
    """Kolla via master-DB om alla artefakter i månadens batch är
    importerade. Detta kräver master-session — vi öppnar den separat."""
    from ..school.engines import master_session
    from ..school.models import ScenarioBatch
    month = assignment.target_year_month
    if not month:
        return CheckResult(
            "in_progress",
            "Saknar målmånad — kan inte utvärdera",
        )
    with master_session() as ms:
        batch = ms.query(ScenarioBatch).filter(
            ScenarioBatch.student_id == student.id,
            ScenarioBatch.year_month == month,
        ).first()
        if not batch:
            return CheckResult(
                "not_started",
                f"Ingen batch utdelad för {month} än",
            )
        total = len(batch.artifacts)
        imp = sum(1 for a in batch.artifacts if a.imported_at is not None)
        if imp == 0:
            return CheckResult("not_started", f"0/{total} dokument importerade")
        if imp < total:
            return CheckResult(
                "in_progress", f"{imp}/{total} dokument importerade"
            )
        return CheckResult(
            "completed", f"Alla {total} dokument importerade"
        )


def _check_balance_month(s: Session, assignment) -> CheckResult:
    month = assignment.target_year_month
    if not month:
        return CheckResult("in_progress", "Saknar målmånad")
    y, m = map(int, month.split("-"))
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    rows = (
        s.query(Transaction)
        .filter(Transaction.date >= start, Transaction.date < end)
        .all()
    )
    if not rows:
        return CheckResult("not_started", f"Inga transaktioner för {month}")
    net = sum(t.amount for t in rows)
    if net >= 0:
        return CheckResult(
            "completed", f"Plusresultat: +{net:.0f} kr för {month}",
            detail={"net": float(net)},
        )
    return CheckResult(
        "in_progress",
        f"Underskott: {net:.0f} kr för {month} — du måste dra ner någonstans",
        detail={"net": float(net)},
    )


def _check_review_loan(s: Session) -> CheckResult:
    n = s.query(Loan).count()
    if n == 0:
        return CheckResult("not_started", "Inget lån registrerat")
    return CheckResult("completed", f"{n} lån registrerat")


def _check_categorize_all(s: Session, assignment) -> CheckResult:
    month = assignment.target_year_month
    q = s.query(Transaction)
    if month:
        y, m = map(int, month.split("-"))
        start = date(y, m, 1)
        end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        q = q.filter(Transaction.date >= start, Transaction.date < end)
    total = q.count()
    if total == 0:
        return CheckResult("not_started", "Inga transaktioner att kategorisera")
    uncategorized = q.filter(Transaction.category_id.is_(None)).count()
    if uncategorized == 0:
        return CheckResult("completed", f"Alla {total} transaktioner kategoriserade")
    if uncategorized == total:
        return CheckResult(
            "not_started",
            f"0/{total} kategoriserade",
        )
    return CheckResult(
        "in_progress",
        f"{total - uncategorized}/{total} kategoriserade",
    )


def _check_save_amount(s: Session, assignment) -> CheckResult:
    """Verifiera att eleven sparat minst params.amount under perioden."""
    target = (assignment.params or {}).get("amount", 0)
    month = assignment.target_year_month
    q = s.query(Transaction).filter(
        Transaction.raw_description.ilike("%SPARKONTO%")
        | Transaction.raw_description.ilike("%SPARANDE%")
    )
    if month:
        y, m = map(int, month.split("-"))
        start = date(y, m, 1)
        end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        q = q.filter(Transaction.date >= start, Transaction.date < end)
    rows = q.all()
    saved = sum(abs(t.amount) for t in rows)
    if not target:
        return CheckResult(
            "completed" if saved > 0 else "not_started",
            f"Sparat {saved:.0f} kr"
            if saved else "Inget sparat ännu",
        )
    if saved >= target:
        return CheckResult("completed", f"Sparat {saved:.0f} kr (mål: {target} kr)")
    if saved > 0:
        pct = int(100 * saved / target)
        return CheckResult(
            "in_progress",
            f"Sparat {saved:.0f} av {target} kr ({pct}%)",
        )
    return CheckResult("not_started", f"Sparat 0 av {target} kr")


# --- Hjälp att skapa standard-uppdrag åt en elev ---

DEFAULT_ASSIGNMENTS_FOR_NEW_STUDENT = [
    {
        "kind": "set_budget",
        "title": "Sätt din första budget",
        "description": (
            "Bestäm hur mycket du vill lägga på varje kategori varje "
            "månad. Tips: gå igenom Konsumentverkets siffror först!"
        ),
    },
]


DEFAULT_ASSIGNMENT_FOR_NEW_BATCH = {
    "kind": "import_batch",
    "title": "Importera månadens dokument",
    "description": (
        "Du har fått nya kontoutdrag, lönespec och eventuella lån-/"
        "kreditkortsbesked. Ladda ner och importera dem i appen."
    ),
}
