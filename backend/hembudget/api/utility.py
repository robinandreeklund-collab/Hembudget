"""/utility - historik, realtid och PDF-parsning för förbrukning.

Två datakällor kompletterar varandra:
1. **Transaction-rader** kategoriserade som El/Vatten/Bredband/etc.
   + TransactionSplit-rader för kombinerade fakturor (Hjo Energi har
   ofta el+vatten+renhållning på samma tx med splits).
2. **UtilityReading-tabell** med faktisk fysisk förbrukning (kWh, GB,
   m³) från:
   - Uppladdade energifaktura-PDFer (Hjo Energi, Telinet, Vattenfall…)
   - Tibber Data API (månads/dag-förbrukning + realtidspris)
   - Manuell inmatning

Endpoints:
- GET /utility/history?year=YYYY[&compare_previous_year=true]
- POST /utility/parse-pdf - ladda upp fakturan, parse + preview
- POST /utility/readings - spara en reading (från preview eller manuellt)
- GET /utility/readings?year=YYYY
- DELETE /utility/readings/{id}
- POST /utility/tibber/test - verifierar API-token + listar homes
- POST /utility/tibber/sync?months=12 - hämtar månadsförbrukning
- GET /utility/tibber/realtime - senaste mätning + priser idag
- POST /utility/tibber/prices - priser idag + imorgon för home
"""
from __future__ import annotations

import hashlib as _hashlib
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings as _settings
from ..db.models import (
    AppSetting,
    Category,
    Transaction,
    TransactionSplit,
    UpcomingTransaction,
    UpcomingTransactionLine,
    UtilityReading,
)
from .deps import db, require_auth

router = APIRouter(
    prefix="/utility", tags=["utility"], dependencies=[Depends(require_auth)],
)


# Kategorier som räknas som "förbrukning". Matchar svensk standard för
# hushållskostnader som varierar per månad (skillnad mot t.ex. hyra
# som är fast). User kan skapa egna kategorier - vi pickar alla med
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


def _compute_history(session: Session, y: int) -> dict:
    """Intern helper - bygger history-dict för ett år."""
    start = date(y, 1, 1)
    end = date(y + 1, 1, 1)

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
            "category_totals": {},
            "month_totals": {},
            "summary": {
                "year_total": 0.0,
                "avg_per_month": 0.0,
                "months_with_data": 0,
            },
        }

    # Tx:er som HAR splits — deras egen category_id ska ignoreras
    # eftersom splits fordelar beloppet per kategori. Annars raknas
    # samma faktura 2 ganger: en som raw tx + en som split.
    tx_ids_with_splits = {
        tid for (tid,) in
        session.query(TransactionSplit.transaction_id).distinct().all()
    }

    tx_rows = (
        session.query(
            Transaction.id,
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

    agg: dict[tuple[int, str], Decimal] = {}
    for tx_id, cat_id, d, amt in tx_rows:
        # Skippa tx:er som har splits — deras belopp raknas via split_rows
        if tx_id in tx_ids_with_splits:
            continue
        month = _month_key(d)
        key = (cat_id, month)
        agg[key] = agg.get(key, Decimal("0")) + abs(amt)
    for cat_id, d, amt in split_rows:
        month = _month_key(d)
        key = (cat_id, month)
        agg[key] = agg.get(key, Decimal("0")) + abs(amt)

    # Inkludera KOMMANDE (unpaid) upcomings som hor till utility-
    # kategorier. Dessa ar redan bestamda fakturor (t.ex. april) som
    # annars saknas i vyn. Vi filtrerar bort fakturor som har nagon
    # UpcomingPayment-rad — de ar helt/delvis betalda och motsvarande
    # Transaction-rader ar redan raknade ovan.
    from ..db.models import UpcomingPayment, UpcomingTransaction, UpcomingTransactionLine
    paid_up_ids = {
        uid for (uid,) in
        session.query(UpcomingPayment.upcoming_id).distinct().all()
    }
    upcomings = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "bill",
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
            UpcomingTransaction.source != "auto:loan_schedule",
        )
        .all()
    )
    # Upcomings som har lines — anvand lines istallet for category_id
    line_rows = (
        session.query(UpcomingTransactionLine)
        .filter(
            UpcomingTransactionLine.category_id.in_(category_ids.keys()),
        )
        .all()
    )
    lines_by_up: dict[int, list] = {}
    for ln in line_rows:
        lines_by_up.setdefault(ln.upcoming_id, []).append(ln)

    for up in upcomings:
        if up.id in paid_up_ids:
            continue  # redan (delvis) betald — transaktion raknas istallet
        month = _month_key(up.expected_date)
        up_lines = lines_by_up.get(up.id, [])
        if up_lines:
            # Anvand lines per kategori
            for ln in up_lines:
                if ln.category_id not in category_ids:
                    continue
                key = (ln.category_id, month)
                agg[key] = agg.get(key, Decimal("0")) + abs(ln.amount)
        else:
            # Ingen uppdelning — anvand upcoming.category_id
            if up.category_id in category_ids:
                key = (up.category_id, month)
                agg[key] = agg.get(key, Decimal("0")) + abs(up.amount)

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


def _readings_summary(session: Session, y: int) -> dict:
    """Aggregera UtilityReading per månad + meter_type för ett år."""
    rows = (
        session.query(UtilityReading)
        .filter(
            UtilityReading.period_start >= date(y, 1, 1),
            UtilityReading.period_start < date(y + 1, 1, 1),
        )
        .order_by(UtilityReading.period_start.asc())
        .all()
    )
    by_meter: dict[str, dict[str, dict]] = {}
    for r in rows:
        m = _month_key(r.period_start)
        meter = r.meter_type
        month_data = by_meter.setdefault(meter, {}).setdefault(
            m, {"consumption": 0.0, "cost_kr": 0.0, "unit": r.consumption_unit},
        )
        if r.consumption is not None:
            month_data["consumption"] += float(r.consumption)
        month_data["cost_kr"] += float(r.cost_kr)
        if r.consumption_unit and not month_data.get("unit"):
            month_data["unit"] = r.consumption_unit
    return by_meter


@router.get("/history")
def utility_history(
    year: int | None = None,
    compare_previous_year: bool = False,
    session: Session = Depends(db),
) -> dict:
    """Manadsvis forbrukning per kategori for ett givet ar.

    Med compare_previous_year=true inkluderas aven foregaende ars
    samma period for manadsvis y/y-jamforelse.
    """
    y = year or date.today().year
    hist = _compute_history(session, y)
    # Kompletterar med fysisk förbrukning (kWh/GB/m³) från UtilityReading
    hist["readings"] = _readings_summary(session, y)
    if compare_previous_year:
        prev = _compute_history(session, y - 1)
        hist["previous"] = prev
        hist["previous_readings"] = _readings_summary(session, y - 1)
        # Månadsvis diff per kategori (kr)
        diffs: dict[str, dict[str, float]] = {}
        for cat in hist["categories"]:
            per_month = {}
            for m_curr, m_prev in zip(hist["months"], prev["months"]):
                curr_val = hist["by_category"][cat].get(m_curr, 0.0)
                prev_val = prev["by_category"].get(cat, {}).get(m_prev, 0.0)
                per_month[m_curr] = round(curr_val - prev_val, 2)
            diffs[cat] = per_month
        hist["yoy_diff"] = diffs
        hist["yoy_summary"] = {
            "year_diff": round(
                hist["summary"]["year_total"]
                - prev["summary"]["year_total"],
                2,
            ),
            "avg_diff": round(
                hist["summary"]["avg_per_month"]
                - prev["summary"]["avg_per_month"],
                2,
            ),
        }
    return hist


# -------- Breakdown (vad ingar i en cell?) --------

@router.get("/breakdown")
def utility_breakdown(
    category: str,
    month: str,
    session: Session = Depends(db),
) -> dict:
    """Lista alla transaktioner + splits som bidrar till en specifik
    cell i /utility-tabellen (kategori x manad). Anvands for att se
    "vad ingar har?" och for att kunna flytta fel-datade rader."""
    from hembudget.db.models import Account

    cat = session.query(Category).filter(Category.name == category).first()
    if cat is None:
        return {"items": [], "category": category, "month": month, "total": 0}

    y, m = map(int, month.split("-"))
    start = date(y, m, 1)
    end = date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)

    # Tx:er som HAR splits — hoppas over eftersom splits redan fordelar
    # beloppet. Annars raknas samma rad 2 ganger i totalen.
    tx_ids_with_splits = {
        tid for (tid,) in
        session.query(TransactionSplit.transaction_id).distinct().all()
    }

    # Fullstandiga Transaction-rader med den har kategorin
    tx_rows = (
        session.query(Transaction)
        .filter(
            Transaction.date >= start,
            Transaction.date < end,
            Transaction.category_id == cat.id,
            Transaction.amount < 0,
        )
        .all()
    )

    # Splits med den har kategorin (tx.date styr manaden)
    split_rows = (
        session.query(TransactionSplit, Transaction)
        .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
        .filter(
            Transaction.date >= start,
            Transaction.date < end,
            TransactionSplit.category_id == cat.id,
        )
        .all()
    )

    accounts = {a.id: a.name for a in session.query(Account).all()}

    # Kartlagg tx_id -> upcoming (om matchad) sa vi kan visa "Oppna
    # faktura" + "Parsa om" direkt i breakdown-modalen.
    tx_to_upcoming: dict[int, UpcomingTransaction] = {}
    relevant_tx_ids = (
        {tx.id for tx in tx_rows if tx.id not in tx_ids_with_splits}
        | {tx.id for _, tx in split_rows}
    )
    if relevant_tx_ids:
        ups_matched = (
            session.query(UpcomingTransaction)
            .filter(UpcomingTransaction.matched_transaction_id.in_(relevant_tx_ids))
            .all()
        )
        for u in ups_matched:
            if u.matched_transaction_id is not None:
                tx_to_upcoming[u.matched_transaction_id] = u
        # Plus de via UpcomingPayment-junction
        from ..db.models import UpcomingPayment as _UP
        pay_rows = (
            session.query(_UP.transaction_id, _UP.upcoming_id)
            .filter(_UP.transaction_id.in_(relevant_tx_ids))
            .all()
        )
        up_by_id = {}
        if pay_rows:
            up_ids = {up_id for _, up_id in pay_rows}
            for u in session.query(UpcomingTransaction).filter(
                UpcomingTransaction.id.in_(up_ids),
            ).all():
                up_by_id[u.id] = u
        for tid, up_id in pay_rows:
            u = up_by_id.get(up_id)
            if u is not None and tid not in tx_to_upcoming:
                tx_to_upcoming[tid] = u

    # Kommande, unpaid upcomings som bidrar till cellen (precis som i
    # /utility/history). Inkludera inte om nagon betalning redan finns
    # (da raknas transaktionen istallet).
    from ..db.models import UpcomingPayment as _UP2, UpcomingTransactionLine as _UL
    paid_up_ids = {
        uid for (uid,) in
        session.query(_UP2.upcoming_id).distinct().all()
    }
    ups_in_month = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.kind == "bill",
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
            UpcomingTransaction.source != "auto:loan_schedule",
        )
        .all()
    )
    # Lines med just denna kategori
    up_lines_for_cat = (
        session.query(_UL, UpcomingTransaction)
        .join(UpcomingTransaction, UpcomingTransaction.id == _UL.upcoming_id)
        .filter(
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date < end,
            _UL.category_id == cat.id,
        )
        .all()
    )
    ups_with_lines_in_cat = {up.id for _, up in up_lines_for_cat}

    # Kartlagg upcoming_id -> reading_id for "Parsa om" per rad
    all_up_ids = set(ups_with_lines_in_cat) | {u.id for u in tx_to_upcoming.values()}
    for u in ups_in_month:
        if u.category_id == cat.id:
            all_up_ids.add(u.id)
    reading_by_up: dict[int, int] = {}
    if all_up_ids:
        for rid, uid in (
            session.query(UtilityReading.id, UtilityReading.upcoming_id)
            .filter(UtilityReading.upcoming_id.in_(all_up_ids))
            .all()
        ):
            if uid is not None:
                reading_by_up[uid] = rid

    def _enrich_item(base: dict, tx_id: int) -> dict:
        up = tx_to_upcoming.get(tx_id)
        base["upcoming_id"] = up.id if up else None
        base["has_invoice_pdf"] = bool(up and up.source_image_path)
        base["reading_id"] = reading_by_up.get(up.id) if up else None
        return base

    items = []
    total = 0.0
    for tx in tx_rows:
        # Skippa om tx har splits — dess bidrag kommer via split_rows
        if tx.id in tx_ids_with_splits:
            continue
        amt = float(abs(tx.amount))
        items.append(_enrich_item({
            "type": "transaction",
            "id": tx.id,
            "date": tx.date.isoformat(),
            "amount": amt,
            "description": tx.raw_description,
            "normalized_merchant": tx.normalized_merchant,
            "account_id": tx.account_id,
            "account_name": accounts.get(tx.account_id, f"#{tx.account_id}"),
            "can_move": True,
        }, tx.id))
        total += amt
    for split, tx in split_rows:
        amt = float(abs(split.amount))
        items.append(_enrich_item({
            "type": "split",
            "id": split.id,
            "transaction_id": tx.id,
            "date": tx.date.isoformat(),
            "amount": amt,
            "description": f"{tx.raw_description} > {split.description}",
            "normalized_merchant": tx.normalized_merchant,
            "account_id": tx.account_id,
            "account_name": accounts.get(tx.account_id, f"#{tx.account_id}"),
            "can_move": False,  # splits foljer tx:ens datum
        }, tx.id))
        total += amt

    # Kommande fakturor (whole-category) som bidrar
    for u in ups_in_month:
        if u.id in paid_up_ids:
            continue
        if u.category_id != cat.id:
            continue
        if u.id in ups_with_lines_in_cat:
            continue  # kommer via lines istallet
        amt = float(abs(u.amount))
        items.append({
            "type": "upcoming",
            "id": u.id,
            "date": u.expected_date.isoformat(),
            "amount": amt,
            "description": u.name,
            "normalized_merchant": None,
            "account_id": u.debit_account_id or 0,
            "account_name": accounts.get(u.debit_account_id, "—"),
            "can_move": False,  # upcomings flyttas via /upcoming
            "upcoming_id": u.id,
            "has_invoice_pdf": bool(u.source_image_path),
            "reading_id": reading_by_up.get(u.id),
        })
        total += amt

    # Kommande fakturor lines (t.ex. Hjo kombinerad med splits)
    for line, u in up_lines_for_cat:
        if u.id in paid_up_ids:
            continue
        amt = float(abs(line.amount))
        items.append({
            "type": "upcoming_line",
            "id": line.id,
            "upcoming_id": u.id,
            "date": u.expected_date.isoformat(),
            "amount": amt,
            "description": f"{u.name} > {line.description}",
            "normalized_merchant": None,
            "account_id": u.debit_account_id or 0,
            "account_name": accounts.get(u.debit_account_id, "—"),
            "can_move": False,
            "has_invoice_pdf": bool(u.source_image_path),
            "reading_id": reading_by_up.get(u.id),
        })
        total += amt

    items.sort(key=lambda i: i["date"])
    return {
        "category": category,
        "month": month,
        "total": round(total, 2),
        "items": items,
    }


# -------- UtilityReading CRUD --------

@router.get("/readings")
def list_readings(
    year: int | None = None,
    session: Session = Depends(db),
) -> dict:
    """Lista alla UtilityReading-rader för ett år. Om year=None
    returneras alla rader (senaste först)."""
    q = session.query(UtilityReading)
    if year is not None:
        q = q.filter(
            UtilityReading.period_start >= date(year, 1, 1),
            UtilityReading.period_start < date(year + 1, 1, 1),
        )
    rows = q.order_by(UtilityReading.period_start.desc()).all()
    return {
        "readings": [
            {
                "id": r.id,
                "supplier": r.supplier,
                "meter_type": r.meter_type,
                "period_start": r.period_start.isoformat(),
                "period_end": r.period_end.isoformat(),
                "consumption": float(r.consumption) if r.consumption is not None else None,
                "consumption_unit": r.consumption_unit,
                "cost_kr": float(r.cost_kr),
                "source": r.source,
                "source_file": r.source_file,
                "notes": r.notes,
                "upcoming_id": r.upcoming_id,
            }
            for r in rows
        ],
    }


@router.post("/readings")
def create_reading(payload: dict, session: Session = Depends(db)) -> dict:
    """Skapa en UtilityReading manuellt. Body: {supplier, meter_type,
    period_start, period_end, consumption?, consumption_unit?,
    cost_kr, notes?}."""
    try:
        r = UtilityReading(
            supplier=payload["supplier"],
            meter_type=payload["meter_type"],
            period_start=date.fromisoformat(payload["period_start"]),
            period_end=date.fromisoformat(payload["period_end"]),
            consumption=(
                Decimal(str(payload["consumption"]))
                if payload.get("consumption") is not None else None
            ),
            consumption_unit=payload.get("consumption_unit"),
            cost_kr=Decimal(str(payload["cost_kr"])),
            source=payload.get("source", "manual"),
            source_file=payload.get("source_file"),
            upcoming_id=payload.get("upcoming_id"),
            notes=payload.get("notes"),
        )
    except (KeyError, ValueError, Exception) as exc:
        raise HTTPException(400, f"Ogiltiga fält: {exc}") from exc
    session.add(r)
    session.flush()
    return {"id": r.id}


@router.delete("/readings/{reading_id}")
def delete_reading(reading_id: int, session: Session = Depends(db)) -> dict:
    r = session.get(UtilityReading, reading_id)
    if r is None:
        raise HTTPException(404, "Reading not found")
    session.delete(r)
    return {"deleted": reading_id}


@router.post("/readings/{reading_id}/reparse")
def reparse_reading(reading_id: int, session: Session = Depends(db)) -> dict:
    """Kor parse_utility_pdf igen pa reading:s source_file och
    uppdatera fälten. Paverkar INTE den eventuellt kopplade
    UpcomingTransaction eller dess Transaction — bara readingen.

    Anvandsfall: du har forbattrat parsern eller fakturans format har
    andrats, och vill uppdatera readingen utan att behova skapa ny.
    """
    from ..parsers.utility_pdfs import parse_utility_pdf

    r = session.get(UtilityReading, reading_id)
    if r is None:
        raise HTTPException(404, "Reading not found")
    if not r.source_file:
        raise HTTPException(
            400,
            "Readingen har ingen kopplad PDF (source_file tom) — kan inte re-parsa.",
        )
    p = Path(r.source_file)
    if not p.exists():
        raise HTTPException(
            404,
            f"Filen finns inte langre pa disk: {r.source_file}",
        )
    try:
        content = p.read_bytes()
        res = parse_utility_pdf(content)
    except Exception as exc:
        raise HTTPException(500, f"Parse-fel: {exc}") from exc

    if res.supplier == "unknown" and (
        res.period_start is None or res.cost_kr is None
    ):
        raise HTTPException(
            422,
            "Kunde inte tolka om PDF:en — varken format detekterat eller "
            "period+kostnad extraherat.",
        )

    # Uppdatera bara fält som faktiskt parsades
    if res.supplier != "unknown":
        r.supplier = res.supplier
    if res.meter_type:
        r.meter_type = res.meter_type
    if res.period_start:
        r.period_start = res.period_start
    if res.period_end:
        r.period_end = res.period_end
    if res.consumption is not None:
        r.consumption = res.consumption
        r.consumption_unit = res.consumption_unit
    if res.cost_kr is not None:
        r.cost_kr = res.cost_kr
    session.flush()
    return {
        "id": r.id,
        "supplier": r.supplier,
        "meter_type": r.meter_type,
        "period_start": r.period_start.isoformat(),
        "period_end": r.period_end.isoformat(),
        "consumption": float(r.consumption) if r.consumption is not None else None,
        "consumption_unit": r.consumption_unit,
        "cost_kr": float(r.cost_kr),
        "detected_format": res.supplier,
    }


@router.post("/parse-upcoming/{upcoming_id}")
def parse_from_upcoming(
    upcoming_id: int, session: Session = Depends(db),
) -> dict:
    """Parsa PDF:en kopplad till en UpcomingTransaction och UPSERTa en
    UtilityReading. Om det redan finns en reading for denna upcoming
    uppdateras den. Detta ar huvudflodet fran breakdown-modalen: klicka
    pa faktura-rad → Parsa om → reading skapas/uppdateras direkt.

    Berakvit INTE tx/upcoming, bara utility-data bakom scenen.
    """
    from ..parsers.utility_pdfs import parse_utility_pdf

    up = session.get(UpcomingTransaction, upcoming_id)
    if up is None:
        raise HTTPException(404, "Upcoming saknas")
    if not up.source_image_path:
        raise HTTPException(400, "Upcoming har ingen bifogad PDF")
    p = Path(up.source_image_path)
    if not p.exists():
        raise HTTPException(
            404, f"Filen saknas pa disk: {up.source_image_path}",
        )
    try:
        res = parse_utility_pdf(p.read_bytes())
    except Exception as exc:
        raise HTTPException(500, f"Parse-fel: {exc}") from exc

    if res.period_start is None or res.cost_kr is None:
        raise HTTPException(
            422,
            "Kunde inte tolka period eller kostnad fran fakturan. "
            f"Format: {res.supplier}. Fel: {res.parse_errors}",
        )

    existing = (
        session.query(UtilityReading)
        .filter(UtilityReading.upcoming_id == up.id)
        .first()
    )
    if existing:
        existing.supplier = res.supplier if res.supplier != "unknown" else existing.supplier
        existing.meter_type = res.meter_type or existing.meter_type
        existing.period_start = res.period_start
        existing.period_end = res.period_end or res.period_start
        if res.consumption is not None:
            existing.consumption = res.consumption
            existing.consumption_unit = res.consumption_unit
        existing.cost_kr = res.cost_kr
        existing.source = "pdf_rescan"
        existing.source_file = str(p)
        session.flush()
        action = "updated"
        reading_id = existing.id
        supplier_name = existing.supplier
        consumption = existing.consumption
        consumption_unit = existing.consumption_unit
        cost_kr_val = existing.cost_kr
        period_start = existing.period_start
        period_end = existing.period_end
    else:
        reading = UtilityReading(
            supplier=res.supplier,
            meter_type=res.meter_type,
            period_start=res.period_start,
            period_end=res.period_end or res.period_start,
            consumption=res.consumption,
            consumption_unit=res.consumption_unit,
            cost_kr=res.cost_kr,
            source="pdf_rescan",
            source_file=str(p),
            upcoming_id=up.id,
        )
        session.add(reading)
        session.flush()
        action = "created"
        reading_id = reading.id
        supplier_name = reading.supplier
        consumption = reading.consumption
        consumption_unit = reading.consumption_unit
        cost_kr_val = reading.cost_kr
        period_start = reading.period_start
        period_end = reading.period_end

    # Bonus: om fakturan inkluderar en månadsvis historik-tabell (typiskt
    # Hjo Energi — 12-13 mån bakåt) fyller vi på UtilityReading för de
    # månader som saknas i DB. Ingen kr-data, bara kWh.
    history_added = 0
    history_skipped = 0
    if res.history:
        for hp in res.history:
            hp_start = date(hp.year, hp.month, 1)
            # Hoppa över fakturans egen period — den hanteras av
            # huvud-reading:en ovan med full kr-data.
            if hp_start == period_start:
                continue
            existing_hist = (
                session.query(UtilityReading)
                .filter(
                    UtilityReading.supplier == res.supplier,
                    UtilityReading.meter_type == "electricity",
                    UtilityReading.period_start == hp_start,
                )
                .first()
            )
            if existing_hist is not None:
                history_skipped += 1
                continue
            from calendar import monthrange
            hp_end = date(
                hp.year, hp.month, monthrange(hp.year, hp.month)[1],
            )
            session.add(UtilityReading(
                supplier=res.supplier,
                meter_type="electricity",
                period_start=hp_start,
                period_end=hp_end,
                consumption=hp.kwh,
                consumption_unit="kWh",
                cost_kr=Decimal("0"),  # Historiken har inte kostnads-data
                source="pdf_history",
                source_file=str(p),
                notes="Hämtad från Hjo Energi historik-tabell",
            ))
            history_added += 1
        session.flush()

    return {
        "action": action,
        "reading_id": reading_id,
        "detected_format": res.supplier,
        "supplier": supplier_name,
        "consumption": float(consumption) if consumption is not None else None,
        "consumption_unit": consumption_unit,
        "cost_kr": float(cost_kr_val),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "history_added": history_added,
        "history_skipped": history_skipped,
    }


@router.get("/readings/{reading_id}/source")
def get_reading_source(reading_id: int, session: Session = Depends(db)):
    """Returnera PDF-filen for en reading (om den finns)."""
    from fastapi.responses import FileResponse
    r = session.get(UtilityReading, reading_id)
    if r is None or not r.source_file:
        raise HTTPException(404, "Ingen PDF kopplad till denna reading")
    p = Path(r.source_file)
    if not p.exists():
        raise HTTPException(404, "Filen saknas pa disk")
    media = "application/pdf" if p.suffix.lower() == ".pdf" else "application/octet-stream"
    return FileResponse(p, media_type=media, filename=p.name)


# -------- PDF parser endpoint --------

@router.post("/parse-pdf")
async def parse_utility_pdf_endpoint(
    file: UploadFile = File(...),
    save: bool = Form(False),
    session: Session = Depends(db),
) -> dict:
    """Parsa en energi-/bredbandsfaktura-PDF. Returnerar forhandsvisning
    med detected supplier, period, forbrukning (kWh/GB/m3) och kostnad.

    Om save=true sparas resultatet direkt som en UtilityReading. Annars
    returneras bara preview så användaren kan granska innan save.

    Stod: Hjo Energi, Telinet, Tibber, Vattenfall, E.ON, Fortum,
    Hjo kommun (vatten/avlopp), Fjarrvarme -- men parsern ar tolerant
    och forsoker lasa ut datum + kWh + belopp fran valfri faktura.
    """
    from ..parsers.utility_pdfs import parse_utility_pdf

    content = await file.read()
    if not content:
        raise HTTPException(400, "Tom fil")
    res = parse_utility_pdf(content)

    # Spara filen för ledger-referens oavsett om vi saves eller bara parses
    saved_path: str | None = None
    invoice_dir = _settings.data_dir / "utility_bills"
    invoice_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    short = _hashlib.sha1(content).hexdigest()[:8]
    safe_name = (file.filename or "utility_bill.pdf").replace("/", "_")
    p = invoice_dir / f"{ts}_{short}_{safe_name}"
    p.write_bytes(content)
    saved_path = str(p)

    result_dict = {
        "supplier": res.supplier,
        "meter_type": res.meter_type,
        "period_start": res.period_start.isoformat() if res.period_start else None,
        "period_end": res.period_end.isoformat() if res.period_end else None,
        "consumption": float(res.consumption) if res.consumption is not None else None,
        "consumption_unit": res.consumption_unit,
        "cost_kr": float(res.cost_kr) if res.cost_kr is not None else None,
        "source_file": saved_path,
        "parse_errors": res.parse_errors,
    }

    if save:
        if res.period_start is None or res.cost_kr is None:
            raise HTTPException(
                422,
                "Kunde inte tolka period eller kostnad - kan ej spara "
                "automatiskt. Komplettera manuellt via POST /utility/readings.",
            )
        reading = UtilityReading(
            supplier=res.supplier,
            meter_type=res.meter_type,
            period_start=res.period_start,
            period_end=res.period_end or res.period_start,
            consumption=res.consumption,
            consumption_unit=res.consumption_unit,
            cost_kr=res.cost_kr,
            source="pdf",
            source_file=saved_path,
        )
        session.add(reading)
        session.flush()
        result_dict["saved_id"] = reading.id

    return result_dict


# -------- Rescan av befintliga fakturor --------

@router.post("/rescan-existing")
def rescan_existing_invoices(session: Session = Depends(db)) -> dict:
    """Gar igenom alla UpcomingTransaction med source_image_path satt
    och forsoker extrahera utility-data fran PDF:en. Skapar
    UtilityReading-rader for de som ar energifakturor (Hjo Energi,
    Telinet, Vattenfall etc.) och som inte redan har en reading
    kopplad (dedup via source_file-path).

    Anvandsfall: du har redan laddat upp fakturor via /upcoming-vision-
    parser innan /utility-parsern fanns. Denna endpoint bygger historisk
    utility-data utan att du behover ladda upp PDF:erna igen.
    """
    from ..parsers.utility_pdfs import parse_utility_pdf

    # Alla UpcomingTransactions med bifogad PDF (oavsett kind eftersom
    # en del vision-parsade fakturor kan klassas som bill men innehalla
    # elforbrukning)
    ups = (
        session.query(UpcomingTransaction)
        .filter(UpcomingTransaction.source_image_path.is_not(None))
        .all()
    )

    # Befintliga reading source-filer for dedup
    existing_sources = {
        r.source_file for r in session.query(UtilityReading).all()
        if r.source_file
    }

    scanned = 0
    parsed_ok = 0
    created = 0
    skipped_dup = 0
    skipped_no_data = 0
    errors: list[dict] = []

    for up in ups:
        scanned += 1
        path_str = up.source_image_path
        if not path_str:
            continue
        p = Path(path_str)
        if not p.exists():
            errors.append({"upcoming_id": up.id, "error": f"filen saknas: {path_str}"})
            continue
        # Skip non-PDF files (bilder parsas inte av utility-parsern)
        if p.suffix.lower() not in (".pdf",):
            continue
        # Dedup via source_file — redan scannade hoppar vi over
        if path_str in existing_sources:
            skipped_dup += 1
            continue
        try:
            content = p.read_bytes()
            res = parse_utility_pdf(content)
        except Exception as exc:
            errors.append({"upcoming_id": up.id, "error": str(exc)})
            continue
        parsed_ok += 1
        # Kvalitetsgate: for att skapa en reading ska vi antingen
        # detektera formatet ELLER ha bade period + kostnad
        if res.supplier == "unknown" and (
            res.period_start is None or res.cost_kr is None
        ):
            skipped_no_data += 1
            continue
        if res.cost_kr is None or res.period_start is None:
            skipped_no_data += 1
            continue
        reading = UtilityReading(
            supplier=res.supplier,
            meter_type=res.meter_type,
            period_start=res.period_start,
            period_end=res.period_end or res.period_start,
            consumption=res.consumption,
            consumption_unit=res.consumption_unit,
            cost_kr=res.cost_kr,
            source="pdf_rescan",
            source_file=path_str,
            upcoming_id=up.id,
        )
        session.add(reading)
        existing_sources.add(path_str)
        created += 1

    session.flush()
    return {
        "scanned": scanned,
        "parsed_ok": parsed_ok,
        "created": created,
        "skipped_duplicate": skipped_dup,
        "skipped_no_data": skipped_no_data,
        "errors": errors,
    }


# -------- Tibber integration --------

def _get_tibber_token(session: Session) -> str | None:
    row = session.get(AppSetting, "tibber_api_token")
    if row and isinstance(row.value, dict):
        v = row.value.get("v")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


# ----- OAuth helpers -----

OAUTH_CONFIG_KEY = "tibber_oauth_config"  # client_id + client_secret + redirect_uri
OAUTH_TOKENS_KEY = "tibber_oauth"  # TibberTokenSet JSON
OAUTH_STATE_KEY = "tibber_oauth_state"  # CSRF-state mellan start/callback


def _get_oauth_config(session: Session) -> dict | None:
    row = session.get(AppSetting, OAUTH_CONFIG_KEY)
    if row and isinstance(row.value, dict):
        if row.value.get("client_id") and row.value.get("client_secret"):
            return row.value
    return None


def _save_oauth_config(session: Session, cfg: dict) -> None:
    row = session.get(AppSetting, OAUTH_CONFIG_KEY)
    if row is None:
        session.add(AppSetting(key=OAUTH_CONFIG_KEY, value=cfg))
    else:
        row.value = cfg
    session.flush()


def _get_oauth_tokens(session: Session):
    from ..utility.tibber_oauth import TibberTokenSet
    row = session.get(AppSetting, OAUTH_TOKENS_KEY)
    if row and isinstance(row.value, dict):
        try:
            return TibberTokenSet.from_dict(row.value)
        except (KeyError, ValueError):
            return None
    return None


def _save_oauth_tokens(session: Session, tokens) -> None:
    row = session.get(AppSetting, OAUTH_TOKENS_KEY)
    if row is None:
        session.add(AppSetting(key=OAUTH_TOKENS_KEY, value=tokens.to_dict()))
    else:
        row.value = tokens.to_dict()
    session.flush()


def _save_oauth_state(session: Session, state: str) -> None:
    row = session.get(AppSetting, OAUTH_STATE_KEY)
    if row is None:
        session.add(AppSetting(key=OAUTH_STATE_KEY, value={"state": state}))
    else:
        row.value = {"state": state}
    session.flush()


def _verify_oauth_state(session: Session, state: str) -> bool:
    row = session.get(AppSetting, OAUTH_STATE_KEY)
    if row is None or not isinstance(row.value, dict):
        return False
    return row.value.get("state") == state


def _get_oauth_client(session: Session):
    """Returnerar en TibberOAuthClient eller None om ingen session finns.
    Om tokens refresha:s under klientens livstid sparas de automatiskt
    tillbaka när `_flush_oauth_client_tokens()` kallas."""
    from ..utility.tibber_oauth import TibberOAuthClient
    cfg = _get_oauth_config(session)
    tokens = _get_oauth_tokens(session)
    if cfg is None or tokens is None:
        return None
    return TibberOAuthClient(tokens=tokens, client_secret=cfg["client_secret"])


def _flush_oauth_client_tokens(session: Session, client) -> None:
    if client is None:
        return
    new_tokens = getattr(client, "tokens_after", None)
    if new_tokens is not None:
        _save_oauth_tokens(session, new_tokens)


@router.get("/tibber/oauth/config")
def tibber_oauth_config_get(session: Session = Depends(db)) -> dict:
    """Returnerar OAuth-konfiguration (client_id + redirect_uri) men
    DÖLJER client_secret. Användaren uppdaterar via PUT."""
    cfg = _get_oauth_config(session) or {}
    return {
        "client_id": cfg.get("client_id") or "",
        "redirect_uri": cfg.get("redirect_uri") or "http://localhost:1420/Callback",
        "has_secret": bool(cfg.get("client_secret")),
    }


@router.put("/tibber/oauth/config")
def tibber_oauth_config_put(
    payload: dict, session: Session = Depends(db)
) -> dict:
    """Spara client_id + client_secret + redirect_uri. Ta new OAuth-
    tokens när dessa byts ut (annars kan man använda gamla mot ny app)."""
    client_id = (payload.get("client_id") or "").strip()
    client_secret = (payload.get("client_secret") or "").strip()
    redirect_uri = (
        payload.get("redirect_uri") or "http://localhost:1420/Callback"
    ).strip()
    if not client_id or not client_secret:
        raise HTTPException(400, "client_id och client_secret krävs")
    _save_oauth_config(session, {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    })
    # Om vi byter app — rensa gamla tokens
    existing_tokens = session.get(AppSetting, OAUTH_TOKENS_KEY)
    if existing_tokens:
        session.delete(existing_tokens)
        session.flush()
    return {"ok": True, "has_secret": True}


@router.post("/tibber/oauth/start")
def tibber_oauth_start(session: Session = Depends(db)) -> dict:
    """Generera authorization-URL som användaren öppnar i browser.
    Sparar state-parametern för CSRF-skydd mellan start och callback."""
    from ..utility.tibber_oauth import build_authorization_url
    cfg = _get_oauth_config(session)
    if cfg is None:
        raise HTTPException(
            400,
            "Spara client_id + client_secret först via PUT /utility/tibber/oauth/config",
        )
    url, state = build_authorization_url(
        client_id=cfg["client_id"],
        redirect_uri=cfg["redirect_uri"],
    )
    _save_oauth_state(session, state)
    return {"authorize_url": url, "state": state}


@router.post("/tibber/oauth/callback")
def tibber_oauth_callback(
    payload: dict, session: Session = Depends(db)
) -> dict:
    """Byt authorization-code mot tokens. Frontend skickar hit efter
    att ha fått code+state tillbaka från Tibber-callback."""
    from ..utility.tibber_oauth import (
        TibberOAuthClient, TibberOAuthError, exchange_code_for_token,
    )
    code = (payload.get("code") or "").strip()
    state = (payload.get("state") or "").strip()
    if not code:
        raise HTTPException(400, "code saknas")
    if not _verify_oauth_state(session, state):
        raise HTTPException(
            400,
            "Ogiltig state-parameter — CSRF-skydd. Starta om OAuth-flödet.",
        )
    cfg = _get_oauth_config(session)
    if cfg is None:
        raise HTTPException(400, "Ingen OAuth-config sparad")
    try:
        tokens = exchange_code_for_token(
            client_id=cfg["client_id"],
            client_secret=cfg["client_secret"],
            code=code,
            redirect_uri=cfg["redirect_uri"],
        )
    except TibberOAuthError as exc:
        raise HTTPException(502, str(exc)) from exc
    _save_oauth_tokens(session, tokens)
    # Hämta profil för att verifiera
    client = TibberOAuthClient(
        tokens=tokens, client_secret=cfg["client_secret"],
    )
    try:
        profile = client.viewer_profile()
    except TibberOAuthError:
        profile = {}
    _flush_oauth_client_tokens(session, client)
    return {
        "ok": True,
        "profile": profile,
        "scope": tokens.scope,
        "expires_at": tokens.expires_at.isoformat(),
    }


@router.get("/tibber/oauth/status")
def tibber_oauth_status(session: Session = Depends(db)) -> dict:
    """Snabb status för UI:t — är användaren auktoriserad?"""
    cfg = _get_oauth_config(session)
    tokens = _get_oauth_tokens(session)
    return {
        "configured": cfg is not None,
        "authorized": tokens is not None,
        "client_id": (cfg or {}).get("client_id", ""),
        "redirect_uri": (cfg or {}).get(
            "redirect_uri", "http://localhost:1420/Callback"
        ),
        "scope": tokens.scope if tokens else "",
        "expires_at": tokens.expires_at.isoformat() if tokens else None,
    }


@router.post("/tibber/oauth/logout")
def tibber_oauth_logout(session: Session = Depends(db)) -> dict:
    """Ta bort sparade tokens (behåll config). Användaren måste
    auktorisera på nytt innan API:et används igen."""
    row = session.get(AppSetting, OAUTH_TOKENS_KEY)
    if row is not None:
        session.delete(row)
        session.flush()
    return {"ok": True}


@router.post("/tibber/test")
def tibber_test(session: Session = Depends(db)) -> dict:
    """Verifiera Tibber-auth och lista användarens hem.

    Prioriterar OAuth-session om den finns (nya Data API:et), annars
    faller tillbaka på bearer-token mot gamla v1-beta-API:et.
    Returnerar homes-listan så användaren kan välja vilket hem som
    ska synkas."""
    from ..utility.tibber_oauth import TibberOAuthError

    # 1. Försök OAuth-sessionen först — det är där Data API-hem finns
    oauth_client = _get_oauth_client(session)
    if oauth_client is not None:
        try:
            raw_homes = oauth_client.list_homes()
            _flush_oauth_client_tokens(session, oauth_client)
        except TibberOAuthError as exc:
            raise HTTPException(502, str(exc)) from exc
        homes_out = []
        for h in raw_homes:
            addr = h.get("address") or {}
            addr_str = ", ".join(
                x for x in [
                    addr.get("address1"),
                    addr.get("postalCode"),
                    addr.get("city"),
                ] if x
            ) or "Okänd adress"
            features = h.get("features") or {}
            homes_out.append({
                "id": h.get("id"),
                "address": addr_str,
                "size": h.get("size"),
                "main_fuse_size": h.get("mainFuseSize"),
                "currency": "SEK",
                "has_pulse": bool(features.get("realTimeConsumptionEnabled")),
            })
        return {"ok": True, "auth": "oauth", "homes": homes_out}

    # 2. Fallback: legacy bearer-token
    from ..utility.tibber import TibberClient, TibberError
    token = _get_tibber_token(session)
    if not token:
        raise HTTPException(
            400,
            "Ingen Tibber-auth konfigurerad. Antingen: (a) anslut via "
            "OAuth på /settings, eller (b) sätt en bearer-token via "
            "PUT /settings/tibber_api_token.",
        )
    try:
        client = TibberClient(token)
        homes = client.list_homes()
    except TibberError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {
        "ok": True,
        "auth": "bearer",
        "homes": [
            {
                "id": h.id, "address": h.address, "size": h.size,
                "main_fuse_size": h.main_fuse_size,
                "currency": h.currency, "has_pulse": h.has_pulse,
            }
            for h in homes
        ],
    }


@router.post("/tibber/sync")
def tibber_sync(
    home_id: str | None = None,
    months: int = 12,
    session: Session = Depends(db),
) -> dict:
    """Hämta senaste N månadernas förbrukning + kostnad från Tibber
    och spara som UtilityReading-rader. Idempotent - befintliga rader
    för samma (home_id, period_start) uppdateras istället för dupliceras.

    Om home_id är None används första hemmet i listan.
    """
    from ..utility.tibber import (
        TibberClient, TibberError, monthly_consumption_to_readings,
    )

    token = _get_tibber_token(session)
    if not token:
        raise HTTPException(400, "Ingen Tibber-token sparad")
    try:
        client = TibberClient(token)
        homes = client.list_homes()
        if not homes:
            raise HTTPException(404, "Inga hem registrerade på tokenen")
        home = homes[0]
        if home_id:
            matched = [h for h in homes if h.id == home_id]
            if not matched:
                raise HTTPException(404, f"Home {home_id} saknas")
            home = matched[0]
        nodes = client.consumption(
            home.id, resolution="MONTHLY", last=months,
        )
    except TibberError as exc:
        raise HTTPException(502, str(exc)) from exc

    readings = monthly_consumption_to_readings(home, nodes)
    saved = 0
    updated = 0
    for r in readings:
        existing = (
            session.query(UtilityReading)
            .filter(
                UtilityReading.supplier == "tibber",
                UtilityReading.period_start == r["period_start"],
            )
            .first()
        )
        if existing:
            existing.period_end = r["period_end"]
            existing.consumption = Decimal(str(r["consumption"]))
            existing.consumption_unit = r["consumption_unit"]
            existing.cost_kr = Decimal(str(r["cost_kr"]))
            existing.notes = r["notes"]
            updated += 1
        else:
            session.add(UtilityReading(
                supplier=r["supplier"],
                meter_type=r["meter_type"],
                period_start=r["period_start"],
                period_end=r["period_end"],
                consumption=Decimal(str(r["consumption"])),
                consumption_unit=r["consumption_unit"],
                cost_kr=Decimal(str(r["cost_kr"])),
                source="tibber_api",
                notes=r["notes"],
            ))
            saved += 1
    session.flush()
    return {
        "home_id": home.id,
        "home_address": home.address,
        "nodes_fetched": len(nodes),
        "saved": saved,
        "updated": updated,
    }


@router.get("/tibber/realtime")
def tibber_realtime(
    home_id: str | None = None,
    session: Session = Depends(db),
) -> dict:
    """Senaste Pulse-mätning + dagens pris.

    OAuth-session prioriteras. Fallback till legacy bearer-token om
    OAuth inte är konfigurerat. Returnerar tom realtime om Pulse saknas
    men hemmet finns."""
    from ..utility.tibber_oauth import TibberOAuthError

    oauth_client = _get_oauth_client(session)
    if oauth_client is not None:
        try:
            homes = oauth_client.list_homes()
            if not homes:
                raise HTTPException(404, "Inga hem i Tibber-kontot")
            home = homes[0]
            if home_id:
                match = next(
                    (h for h in homes if h.get("id") == home_id), None,
                )
                if match is not None:
                    home = match
            hid = home.get("id")
            measurement = oauth_client.current_measurement(hid)
            _flush_oauth_client_tokens(session, oauth_client)
        except TibberOAuthError as exc:
            raise HTTPException(502, str(exc)) from exc

        addr = home.get("address") or {}
        features = home.get("features") or {}
        has_pulse = bool(features.get("realTimeConsumptionEnabled"))
        price_cur = (measurement or {}).get("price_current") if measurement else None
        daily = (measurement or {}).get("daily_latest") if measurement else None
        return {
            "auth": "oauth",
            "home": {
                "id": hid,
                "address": ", ".join(
                    x for x in [
                        addr.get("address1"), addr.get("postalCode"),
                        addr.get("city"),
                    ] if x
                ) or "Okänd adress",
                "has_pulse": has_pulse,
            },
            "realtime": {
                "power_watts": None,  # Pulse-subscription kommer senare
                "consumption_today_kwh": (
                    float(daily["consumption"]) if daily and daily.get("consumption") is not None else None
                ),
                "cost_today_kr": (
                    float(daily["cost"]) if daily and daily.get("cost") is not None else None
                ),
                "currency": (price_cur or {}).get("currency", "SEK"),
                "timestamp": datetime.utcnow().isoformat(),
            } if has_pulse and daily else None,
            "prices": {
                "current": price_cur or None,
                # Tibber Data API inkluderar inte today/tomorrow i current-
                # frågan; vi kan utöka schemat senare vid behov.
                "today": [],
                "tomorrow": [],
            },
        }

    # Fallback: legacy bearer-token
    from ..utility.tibber import TibberClient, TibberError
    token = _get_tibber_token(session)
    if not token:
        raise HTTPException(
            400,
            "Ingen Tibber-auth. Anslut via OAuth på /settings.",
        )
    try:
        client = TibberClient(token)
        homes = client.list_homes()
        if not homes:
            raise HTTPException(404, "Inga hem")
        home = homes[0] if not home_id else next(
            (h for h in homes if h.id == home_id), homes[0],
        )
        rt = client.realtime(home.id)
        prices = client.price_info_today_and_tomorrow(home.id)
    except TibberError as exc:
        raise HTTPException(502, str(exc)) from exc

    return {
        "auth": "bearer",
        "home": {
            "id": home.id, "address": home.address, "has_pulse": home.has_pulse,
        },
        "realtime": {
            "power_watts": rt.power_watts if rt else None,
            "consumption_today_kwh": rt.consumption_since_last_reset_kwh if rt else None,
            "cost_today_kr": rt.cost_since_last_reset_kr if rt else None,
            "currency": rt.currency if rt else "SEK",
            "timestamp": rt.timestamp.isoformat() if rt else None,
        } if rt else None,
        "prices": prices,
    }


@router.get("/tibber/prices")
def tibber_prices(
    home_id: str | None = None,
    session: Session = Depends(db),
) -> dict:
    """Alla priser idag + imorgon (timvis) för hemmet."""
    from ..utility.tibber import TibberClient, TibberError

    token = _get_tibber_token(session)
    if not token:
        raise HTTPException(400, "Ingen Tibber-token sparad")
    try:
        client = TibberClient(token)
        homes = client.list_homes()
        if not homes:
            raise HTTPException(404, "Inga hem")
        home = homes[0] if not home_id else next(
            (h for h in homes if h.id == home_id), homes[0],
        )
        return {"home_id": home.id, "prices": client.price_info_today_and_tomorrow(home.id)}
    except TibberError as exc:
        raise HTTPException(502, str(exc)) from exc
