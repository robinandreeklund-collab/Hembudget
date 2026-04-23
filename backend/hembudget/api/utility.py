"""/utility — historik över el, vatten, bredband och andra förbrukningsposter.

MVP-version: läser från Transaction-rader kategoriserade som utility-
kategorier + UpcomingTransactionLine-splits (t.ex. Hjo Energi-fakturor
som har el/vatten/bredband på separata rader).

Framtida utökningar:
- PDF-parser för Hjo Energi + Telinet som extraherar kWh-förbrukning
  utöver kr
- Tibber Pulse API-integration för realtidspris och löpande förbrukning
- Månadsjämförelse mot föregående år
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import (
    Category,
    Transaction,
    TransactionSplit,
    UpcomingTransactionLine,
)
from .deps import db, require_auth

router = APIRouter(
    prefix="/utility", tags=["utility"], dependencies=[Depends(require_auth)],
)


# Kategorier som räknas som "förbrukning". Matchar svensk standard för
# hushållskostnader som varierar per månad (skillnad mot t.ex. hyra
# som är fast). User kan skapa egna kategorier — vi pickar alla med
# parent='Boende' som default.
UTILITY_CATEGORY_NAMES = [
    "El",
    "Vatten/Avgift",
    "Uppvärmning",
    "Bredband",
    "Internet",
    "Mobil",
    "Renhållning",
    "Hemförsäkring",
    "Fjärrvärme",
]


def _month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


@router.get("/history")
def utility_history(
    year: int | None = None,
    session: Session = Depends(db),
) -> dict:
    """Månadsvis förbrukning per kategori för ett givet år.

    Returnerar:
    - categories: lista av kategorinamn som finns i datan
    - months: YYYY-MM-rader (jan till aktuell månad)
    - by_category: { category: { month: kr } }
    - totals: { category: total_year, month: total_month }
    - summary: { year_total, avg_per_month }
    """
    y = year or date.today().year
    start = date(y, 1, 1)
    end = date(y + 1, 1, 1)

    # Samla utility-kategorier som faktiskt finns i DB
    categories = (
        session.query(Category)
        .filter(Category.name.in_(UTILITY_CATEGORY_NAMES))
        .all()
    )
    category_ids = {c.id: c.name for c in categories}
    if not category_ids:
        return {
            "year": y,
            "categories": [],
            "months": [],
            "by_category": {},
            "totals": {},
            "summary": {"year_total": 0.0, "avg_per_month": 0.0},
        }

    # Transactions med utility-kategori (negativa = utgifter)
    tx_rows = (
        session.query(
            Transaction.category_id,
            Transaction.date,
            Transaction.amount,
        )
        .filter(
            Transaction.date >= start,
            Transaction.date < end,
            Transaction.category_id.in_(category_ids.keys()),
            Transaction.amount < 0,
        )
        .all()
    )

    # TransactionSplits med utility-kategori — för fakturor som har
    # separata rader (Hjo Energi = el + vatten + renhållning på en tx)
    split_rows = (
        session.query(
            TransactionSplit.category_id,
            Transaction.date,
            TransactionSplit.amount,
        )
        .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
        .filter(
            Transaction.date >= start,
            Transaction.date < end,
            TransactionSplit.category_id.in_(category_ids.keys()),
        )
        .all()
    )

    # Aggregera: per (category_id, YYYY-MM)
    agg: dict[tuple[int, str], Decimal] = {}
    for cat_id, d, amt in tx_rows:
        month = _month_key(d)
        key = (cat_id, month)
        agg[key] = agg.get(key, Decimal("0")) + abs(amt)
    for cat_id, d, amt in split_rows:
        # Splits är redan positiva belopp per rad
        month = _month_key(d)
        key = (cat_id, month)
        agg[key] = agg.get(key, Decimal("0")) + abs(amt)

    # Bygg output-strukturen
    months = [f"{y}-{m:02d}" for m in range(1, 13)]
    used_cat_ids = sorted({k[0] for k in agg.keys()})
    out_by_category: dict[str, dict[str, float]] = {}
    cat_totals: dict[str, float] = {}
    for cat_id in used_cat_ids:
        name = category_ids[cat_id]
        per_month = {m: 0.0 for m in months}
        total = 0.0
        for m in months:
            val = float(agg.get((cat_id, m), Decimal("0")))
            per_month[m] = val
            total += val
        out_by_category[name] = per_month
        cat_totals[name] = round(total, 2)

    month_totals: dict[str, float] = {}
    for m in months:
        t = sum(out_by_category[c][m] for c in out_by_category)
        month_totals[m] = round(t, 2)
    year_total = sum(cat_totals.values())
    months_with_data = [m for m in months if month_totals[m] > 0]
    avg = (year_total / len(months_with_data)) if months_with_data else 0.0

    return {
        "year": y,
        "categories": list(out_by_category.keys()),
        "months": months,
        "by_category": out_by_category,
        "category_totals": cat_totals,
        "month_totals": month_totals,
        "summary": {
            "year_total": round(year_total, 2),
            "avg_per_month": round(avg, 2),
            "months_with_data": len(months_with_data),
        },
    }
