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
    for cat_id, d, amt in tx_rows:
        month = _month_key(d)
        key = (cat_id, month)
        agg[key] = agg.get(key, Decimal("0")) + abs(amt)
    for cat_id, d, amt in split_rows:
        month = _month_key(d)
        key = (cat_id, month)
        agg[key] = agg.get(key, Decimal("0")) + abs(amt)

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
    items = []
    total = 0.0
    for tx in tx_rows:
        amt = float(abs(tx.amount))
        items.append({
            "type": "transaction",
            "id": tx.id,
            "date": tx.date.isoformat(),
            "amount": amt,
            "description": tx.raw_description,
            "normalized_merchant": tx.normalized_merchant,
            "account_id": tx.account_id,
            "account_name": accounts.get(tx.account_id, f"#{tx.account_id}"),
            "can_move": True,
        })
        total += amt
    for split, tx in split_rows:
        amt = float(abs(split.amount))
        items.append({
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


# -------- Tibber integration --------

def _get_tibber_token(session: Session) -> str | None:
    row = session.get(AppSetting, "tibber_api_token")
    if row and isinstance(row.value, dict):
        v = row.value.get("v")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


@router.post("/tibber/test")
def tibber_test(session: Session = Depends(db)) -> dict:
    """Verifiera Tibber API-token och lista användarens hem.

    Token måste vara satt via PUT /settings/tibber_api_token innan
    endpointen funkar. Returnerar homes-listan så användaren kan välja
    vilket hem som ska synkas.
    """
    from ..utility.tibber import TibberClient, TibberError

    token = _get_tibber_token(session)
    if not token:
        raise HTTPException(
            400,
            "Ingen Tibber-token sparad. Sätt via PUT /settings/tibber_api_token "
            "med en token från https://developer.tibber.com",
        )
    try:
        client = TibberClient(token)
        homes = client.list_homes()
    except TibberError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {
        "ok": True,
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
    """Senaste Pulse-mätning + dagens pris. Returnerar tomma värden om
    Pulse inte är konfigurerad för hemmet."""
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
        rt = client.realtime(home.id)
        prices = client.price_info_today_and_tomorrow(home.id)
    except TibberError as exc:
        raise HTTPException(502, str(exc)) from exc

    return {
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
