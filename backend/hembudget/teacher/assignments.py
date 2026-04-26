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
    UpcomingTransaction,
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
    # Manuell "klar"-markering vinner alltid över automatiska checkers.
    if getattr(assignment, "manually_completed_at", None):
        return CheckResult(
            "completed",
            f"Klarmarkerad av lärare {assignment.manually_completed_at:%Y-%m-%d}",
        )
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
            if kind == "mortgage_decision":
                return _check_mortgage_decision(assignment, student)
            if kind == "link_transfer":
                return _check_link_transfer(s, assignment)
            if kind == "make_transfer":
                return _check_make_transfer(s, assignment)
            if kind == "stock_open_account":
                return _check_stock_open_account(s, assignment)
            if kind == "stock_diversify":
                return _check_stock_diversify(s, assignment)
            if kind == "add_upcoming":
                return _check_add_upcoming(s, assignment)
            # free_text: bara manuellt — läraren klickar "Klarmarkera"
            # i UI:n så sätts manually_completed_at.
            return CheckResult(
                "in_progress",
                "Bedöms manuellt — läraren klarmarkerar",
            )


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


def _check_mortgage_decision(assignment, student) -> CheckResult:
    """Kolla om eleven har gjort sitt val + om horisonten passerat
    (så vi kan visa facit). Status-logik:
    - Inget val: not_started
    - Val gjort men horisont ej klar: in_progress ('Väntar på facit')
    - Horisont klar: completed med kostnadsdiff rapporterad
    """
    from ..school.engines import master_session
    from ..school.models import MortgageDecision
    from datetime import date as _date
    with master_session() as ms:
        mc = ms.query(MortgageDecision).filter(
            MortgageDecision.assignment_id == assignment.id
        ).first()
        if not mc:
            return CheckResult("not_started", "Du har inte valt ännu")
        y, m = map(int, mc.decision_month.split("-"))
        end_m = m + mc.horizon_months
        end_y = y + end_m // 12
        end_m = end_m % 12 + 1
        end_ym = f"{end_y:04d}-{end_m:02d}"
        today = _date.today().strftime("%Y-%m")
        if today < end_ym:
            return CheckResult(
                "in_progress",
                f"Du valde {mc.chosen} — facit visas efter {end_ym}",
            )
        return CheckResult(
            "completed",
            f"Du valde {mc.chosen}. Se facit i uppdraget.",
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


def _check_link_transfer(s: Session, assignment) -> CheckResult:
    """Kolla att eleven manuellt eller via detektorn länkat ihop minst
    `params.target_count` (default 1) transaktioner som överföringar.
    Visualiserar momentet "när är ett uttag faktiskt en överföring".
    """
    target = int((assignment.params or {}).get("target_count", 1))
    n = s.query(Transaction).filter(Transaction.is_transfer.is_(True)).count()
    if n == 0:
        return CheckResult("not_started", f"0/{target} länkade överföringar")
    if n < target:
        return CheckResult(
            "in_progress",
            f"{n}/{target} länkade överföringar",
        )
    return CheckResult(
        "completed",
        f"{n} länkade överföringar (mål: {target})",
        detail={"count": n, "target": target},
    )


def _check_make_transfer(s: Session, assignment) -> CheckResult:
    """Kolla att eleven proaktivt skapat en överföring som matchar
    parametrarna.

    params:
      - target_count (int, default 1)
      - min_amount (Decimal/float, default 0) — minsta belopp per överföring
      - to_account_kind (str, default None) — t.ex. "savings", "isk"
      - max_age_days (int, default 30) — bara överföringar inom intervallet räknas
    """
    from datetime import timedelta

    p = assignment.params or {}
    target = int(p.get("target_count", 1))
    min_amount = Decimal(str(p.get("min_amount", 0)))
    to_kind = p.get("to_account_kind")
    max_age = int(p.get("max_age_days", 30))
    cutoff = date.today() - timedelta(days=max_age)

    q = (
        s.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Transaction.is_transfer.is_(True),
            Transaction.transfer_pair_id.is_not(None),
            Transaction.amount > 0,
            Transaction.amount >= min_amount,
            Transaction.date >= cutoff,
        )
    )
    if to_kind:
        q = q.filter(Account.type == to_kind)
    n = q.count()

    label_extra = ""
    if to_kind:
        label_extra = f" till {to_kind}-konto"
    if min_amount > 0:
        label_extra += f" på minst {min_amount} kr"

    if n == 0:
        return CheckResult("not_started", f"0/{target} överföringar{label_extra}")
    if n < target:
        return CheckResult("in_progress", f"{n}/{target} överföringar{label_extra}")
    return CheckResult(
        "completed",
        f"{n} överföringar{label_extra} (mål: {target})",
        detail={"count": n, "target": target},
    )


def _check_stock_open_account(s: Session, assignment) -> CheckResult:
    """Kolla att eleven skapat ett ISK-konto.

    params:
      - target_count (int, default 1)
      - account_kind (str, default "isk")
    """
    p = assignment.params or {}
    target = int(p.get("target_count", 1))
    kind = p.get("account_kind", "isk")
    n = s.query(Account).filter(Account.type == kind).count()
    if n == 0:
        return CheckResult("not_started", f"0/{target} {kind}-konton skapade")
    if n < target:
        return CheckResult("in_progress", f"{n}/{target} {kind}-konton skapade")
    return CheckResult(
        "completed",
        f"{n} {kind}-konton skapade (mål: {target})",
        detail={"count": n, "target": target},
    )


def _check_stock_diversify(s: Session, assignment) -> CheckResult:
    """Kolla att eleven har en diversifierad portfölj.

    params:
      - min_holdings (int, default 5) — antal olika tickers
      - min_sectors (int, default 3) — antal olika sektorer
        Sektorinformation hämtas från StockMaster i master-DB.
    """
    from ..db.models import StockHolding
    from ..school.engines import master_session as _master
    from ..school.stock_models import StockMaster

    p = assignment.params or {}
    min_holdings = int(p.get("min_holdings", 5))
    min_sectors = int(p.get("min_sectors", 3))

    holdings = s.query(StockHolding).filter(StockHolding.quantity > 0).all()
    n_holdings = len({h.ticker for h in holdings})

    if n_holdings == 0:
        return CheckResult(
            "not_started",
            f"0/{min_holdings} olika aktier i portföljen",
        )

    # Slå upp sektorer från master
    tickers = {h.ticker for h in holdings}
    sectors: set[str] = set()
    with _master() as ms:
        for sm in (
            ms.query(StockMaster).filter(StockMaster.ticker.in_(tickers)).all()
        ):
            sectors.add(sm.sector)

    n_sectors = len(sectors)
    if n_holdings < min_holdings or n_sectors < min_sectors:
        return CheckResult(
            "in_progress",
            f"{n_holdings}/{min_holdings} aktier, {n_sectors}/{min_sectors} sektorer",
        )

    return CheckResult(
        "completed",
        f"{n_holdings} aktier över {n_sectors} sektorer (mål: {min_holdings}/{min_sectors})",
        detail={
            "holdings": n_holdings,
            "sectors": n_sectors,
            "sector_list": sorted(sectors),
        },
    )


def _check_add_upcoming(s: Session, assignment) -> CheckResult:
    """Kolla att eleven lagt till minst `params.target_count` (default 1)
    kommande räkningar/inkomster i UpcomingTransaction. Verifierar att
    eleven förstår skillnaden mellan bokat och planerat."""
    target = int((assignment.params or {}).get("target_count", 1))
    n = s.query(UpcomingTransaction).count()
    if n == 0:
        return CheckResult("not_started", f"0/{target} kommande räkningar")
    if n < target:
        return CheckResult(
            "in_progress",
            f"{n}/{target} kommande räkningar tillagda",
        )
    return CheckResult(
        "completed",
        f"{n} kommande räkningar tillagda (mål: {target})",
        detail={"count": n, "target": target},
    )


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
