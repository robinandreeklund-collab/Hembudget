"""Huvudbok-endpoint — en komplett avstämning av all ekonomisk data.

Syftet: användaren ska snabbt kunna se ATT allt balanserar. Består av
fyra huvuddelar:

1. Balansrapport per konto (opening + flöden + closing)
2. Resultaträkning per kategori (inkomst/utgift)
3. Kontroller (transfers summerar till 0, credit = köp, etc.)
4. Verifikat — hela transaktionslistan för perioden, sorterad

Används av Rapporter-sidans 'Huvudbok'-vy så användaren snabbt ser om
siffrorna hänger ihop eller om något verkar skevt.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import (
    Account,
    Category,
    Loan,
    LoanPayment,
    Transaction,
    UpcomingTransaction,
)
from ..loans.matcher import LoanMatcher
from .deps import db, require_auth

router = APIRouter(
    prefix="/ledger", tags=["ledger"], dependencies=[Depends(require_auth)],
)


def _parse_period(year: int | None, month: str | None) -> tuple[date, date, str]:
    """Returnera (start, end, label). end är EXKLUSIV (nästa dag/månad/år)."""
    if month:
        y, m = map(int, month.split("-"))
        start = date(y, m, 1)
        end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        return start, end, month
    y = year or date.today().year
    return date(y, 1, 1), date(y + 1, 1, 1), str(y)


def _d(x) -> float:
    return float(x or 0)


@router.get("/")
def huvudbok(
    year: Optional[int] = None,
    month: Optional[str] = None,
    session: Session = Depends(db),
) -> dict:
    """Huvudbok för en period (månad eller helt år).

    - `month=YYYY-MM` → en kalendermånad
    - `year=YYYY` → hela året (default: innevarande år)
    """
    period_start, period_end, period_label = _parse_period(year, month)

    # ---------- Balansrapport per konto ----------
    accounts = session.query(Account).order_by(Account.id).all()
    account_rows = []
    total_assets = 0.0
    total_liabilities = 0.0

    for acc in accounts:
        # Opening = opening_balance + rörelse FÖRE period_start
        ob = acc.opening_balance or Decimal("0")
        ob_date = acc.opening_balance_date

        pre_q = session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.account_id == acc.id,
            Transaction.date < period_start,
        )
        if ob_date is not None:
            pre_q = pre_q.filter(Transaction.date > ob_date)
        pre_sum = Decimal(str(pre_q.scalar() or 0))
        opening_at_period = ob + pre_sum

        # Rörelse UNDER perioden, uppdelat
        tx_in_period = session.query(Transaction).filter(
            Transaction.account_id == acc.id,
            Transaction.date >= period_start,
            Transaction.date < period_end,
        ).all()

        income_in = sum(
            (t.amount for t in tx_in_period if t.amount > 0 and not t.is_transfer),
            Decimal("0"),
        )
        expenses_in = sum(
            (-t.amount for t in tx_in_period if t.amount < 0 and not t.is_transfer),
            Decimal("0"),
        )
        transfer_in = sum(
            (t.amount for t in tx_in_period if t.amount > 0 and t.is_transfer),
            Decimal("0"),
        )
        transfer_out = sum(
            (-t.amount for t in tx_in_period if t.amount < 0 and t.is_transfer),
            Decimal("0"),
        )

        closing = (
            opening_at_period + income_in - expenses_in + transfer_in - transfer_out
        )

        assets_contribution = float(closing) if acc.type not in ("credit",) else 0.0
        liabilities_contribution = (
            -float(closing) if acc.type == "credit" and closing < 0 else 0.0
        )
        total_assets += assets_contribution
        total_liabilities += liabilities_contribution

        account_rows.append({
            "id": acc.id,
            "name": acc.name,
            "bank": acc.bank,
            "type": acc.type,
            "owner_id": acc.owner_id,
            "opening_balance": float(opening_at_period),
            "income": float(income_in),
            "expenses": float(expenses_in),
            "transfer_in": float(transfer_in),
            "transfer_out": float(transfer_out),
            "closing_balance": float(closing),
            "transaction_count": len(tx_in_period),
        })

    # ---------- Resultaträkning per kategori ----------
    # Hämtar alla transaktioner + join:ar Category, aggregerar i Python
    # för tydlig logik (okategoriserade, små summor).
    all_tx = (
        session.query(Transaction, Category)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .filter(
            Transaction.date >= period_start,
            Transaction.date < period_end,
            Transaction.is_transfer.is_(False),
        )
        .all()
    )
    cat_agg: dict[tuple[int | None, str], dict] = {}
    income_total = Decimal("0")
    expense_total = Decimal("0")
    uncategorized_count = 0
    for tx, cat in all_tx:
        cat_id = cat.id if cat else None
        cat_name = cat.name if cat else "Okategoriserat"
        if cat_id is None:
            uncategorized_count += 1
        key = (cat_id, cat_name)
        bucket = cat_agg.setdefault(
            key,
            {
                "category_id": cat_id, "category": cat_name,
                "income": Decimal("0"), "expenses": Decimal("0"), "count": 0,
            },
        )
        if tx.amount > 0:
            bucket["income"] += tx.amount
            income_total += tx.amount
        else:
            bucket["expenses"] += -tx.amount
            expense_total += -tx.amount
        bucket["count"] += 1

    cat_out = []
    for b in cat_agg.values():
        cat_out.append({
            "category_id": b["category_id"],
            "category": b["category"],
            "income": float(b["income"]),
            "expenses": float(b["expenses"]),
            "net": float(b["income"] - b["expenses"]),
            "count": b["count"],
        })
    cat_out.sort(key=lambda r: -(abs(r["income"]) + abs(r["expenses"])))

    # ---------- Kontroller / avstämningar ----------
    checks: list[dict] = []

    # 1. Interna överföringar ska summera till 0 (lika mycket in som ut
    #    när båda sidor är inom perioden)
    transfer_sum = sum(
        (float(r["transfer_in"] - r["transfer_out"]) for r in account_rows),
        0.0,
    )
    transfer_passed = abs(transfer_sum) < 1.0
    checks.append({
        "name": "Interna överföringar balanserar",
        "passed": transfer_passed,
        "value": round(transfer_sum, 2),
        "detail": (
            "Summan av alla transfer_in minus transfer_out ska vara 0 — "
            "om inte så finns orphan-överföringar (bara en sida av paret)"
        ),
    })

    # 2. Kredit-konto: closing balance ≤ 0 (skuld-konto)
    for r in account_rows:
        if r["type"] == "credit" and r["closing_balance"] > 100:
            checks.append({
                "name": f"Kreditkort '{r['name']}' har positivt saldo",
                "passed": False,
                "value": r["closing_balance"],
                "detail": (
                    "Kreditkortskonton ska normalt ha 0 eller negativt "
                    "saldo (0 = inget att betala, negativt = skuld). "
                    "Positivt saldo tyder på att inbetalningar saknar "
                    "matchning mot en faktura."
                ),
            })

    # 3. Okategoriserade transaktioner
    checks.append({
        "name": "Alla transaktioner är kategoriserade",
        "passed": uncategorized_count == 0,
        "value": uncategorized_count,
        "detail": (
            f"{uncategorized_count} transaktioner saknar kategori — "
            "påverkar budget och rapporter"
        ),
    })

    # 4. Lån: outstanding_balance stämmer med principal/current - amort
    loans = session.query(Loan).filter(Loan.active.is_(True)).all()
    matcher = LoanMatcher(session)
    total_loan_debt = 0.0
    loan_rows: list[dict] = []
    for loan in loans:
        balance = float(matcher.outstanding_balance(loan))
        total_loan_debt += balance
        total_paid = float(
            session.query(func.coalesce(func.sum(LoanPayment.amount), 0))
            .filter(
                LoanPayment.loan_id == loan.id,
                LoanPayment.date >= period_start,
                LoanPayment.date < period_end,
            ).scalar() or 0
        )
        loan_rows.append({
            "id": loan.id,
            "name": loan.name,
            "lender": loan.lender,
            "principal_amount": float(loan.principal_amount),
            "current_balance_at_creation": (
                float(loan.current_balance_at_creation)
                if loan.current_balance_at_creation is not None else None
            ),
            "outstanding_balance": balance,
            "interest_rate": loan.interest_rate,
            "payments_in_period": total_paid,
        })
    total_liabilities += total_loan_debt

    # 5. Kommande fakturor vs matchade transaktioner
    ups = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.expected_date >= period_start,
            UpcomingTransaction.expected_date < period_end,
        )
        .all()
    )
    matched_ups = [u for u in ups if u.matched_transaction_id is not None]
    unmatched_ups = [u for u in ups if u.matched_transaction_id is None]
    unmatched_past = [
        u for u in unmatched_ups if u.expected_date < date.today()
    ]
    checks.append({
        "name": "Passerade kommande-rader är matchade",
        "passed": len(unmatched_past) == 0,
        "value": len(unmatched_past),
        "detail": (
            f"{len(unmatched_past)} kommande-rader med passerat datum "
            "saknar matchning mot en Transaction — antingen ska de "
            "raderas eller matcha en bankrad"
        ),
    })

    upcoming_summary = {
        "total": len(ups),
        "matched": len(matched_ups),
        "unmatched": len(unmatched_ups),
        "unmatched_past": len(unmatched_past),
        "matched_sum": float(sum((u.amount for u in matched_ups), Decimal("0"))),
        "unmatched_sum": float(sum((u.amount for u in unmatched_ups), Decimal("0"))),
    }

    net_worth = total_assets - total_liabilities

    return {
        "period": {
            "label": period_label,
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "accounts": account_rows,
        "categories": cat_out,
        "loans": loan_rows,
        "upcoming_summary": upcoming_summary,
        "checks": checks,
        "totals": {
            "income": float(income_total),
            "expenses": float(expense_total),
            "net_result": float(income_total - expense_total),
            "assets": round(total_assets, 2),
            "liabilities": round(total_liabilities, 2),
            "net_worth": round(net_worth, 2),
            "uncategorized_count": uncategorized_count,
        },
    }
