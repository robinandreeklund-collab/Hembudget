"""Default-katalog för svenska förbruknings-abonnemang (Fas 2E).

Innehåller 6 vanliga abonnemang som speglar en typisk hyresgästs
förbruknings-portfölj 2026 (Stockholm). Lärare seedar via
/v2/teacher/students/{id}/utility/seed-default eller eleven själv
skapar via /v2/forbrukning/subscriptions.

Källor (faktagranskat 2026-04):
- Tibber: 0 kr fast, spotpris + 39 öre/kWh påslag
- Ellevio nät (Sthlm): ~320 kr/mån fast överföringsavgift
- Telia bredband 250/250: 389 kr/mån, 24-mån bindning vanligt
- Telia mobil 5GB SVA: 119 kr/mån
- Spotify Premium: 119 kr/mån
- SL reskassa autoladd: ~320 kr/mån (snitt-pendlare)
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from ..db.models import UtilitySubscription


def _binding_in_months(months: int) -> date:
    """Returnerar ett datum `months` månader fram i tiden, för
    bindningstid-simulering. Bara ungefärligt — 30 dagar/månad."""
    return date.today() + timedelta(days=30 * months)


def _default_specs() -> list[dict]:
    """Returnerar default-katalogen med dynamiska bindningstider.

    Beräknas vid varje seed-anrop så att Telia-bindningen alltid är
    "10 månader fram" från seed-datumet (pedagogiskt: visar realistisk
    "snart slut"-position).
    """
    return [
        {
            "supplier": "Tibber",
            "name": "El · spotpris",
            "category": "electricity",
            "monthly_cost": Decimal("0"),
            "grid_fee_monthly": Decimal("320"),
            "spot_pricing": True,
            "binding_end": None,
            "notice_days": 14,
            "invoice_day": 4,
            "status": "active",
            "included_in_rent": False,
            "notes": (
                "Spotpris + 39 öre/kWh påslag · ingen bindning · "
                "Ellevio nätavgift 320 kr/mån tillkommer"
            ),
        },
        {
            "supplier": "Stockholmshem",
            "name": "Värme & vatten",
            "category": "heating",
            "monthly_cost": Decimal("0"),
            "grid_fee_monthly": None,
            "spot_pricing": False,
            "binding_end": None,
            "notice_days": 0,
            "invoice_day": None,
            "status": "active",
            "included_in_rent": True,
            "notes": "Ingår i hyran · ej separat faktura",
        },
        {
            "supplier": "Telia",
            "name": "Bredband 250/250",
            "category": "broadband",
            "monthly_cost": Decimal("389"),
            "grid_fee_monthly": None,
            "spot_pricing": False,
            "binding_end": _binding_in_months(10),
            "notice_days": 90,
            "invoice_day": 12,
            "status": "active",
            "included_in_rent": False,
            "notes": (
                "Sthlms stadsnät · 24 mån-bindning · vid slut: byt "
                "till Bahnhof/Bredband2 ~80 kr/mån billigare"
            ),
        },
        {
            "supplier": "Telia",
            "name": "Mobil · 5 GB SVA",
            "category": "mobile",
            "monthly_cost": Decimal("119"),
            "grid_fee_monthly": None,
            "spot_pricing": False,
            "binding_end": None,
            "notice_days": 30,
            "invoice_day": 27,
            "status": "active",
            "included_in_rent": False,
            "notes": (
                "Sverige-abo med 5 GB · Comviq finns från 49 kr/mån "
                "med samma surf"
            ),
        },
        {
            "supplier": "Spotify",
            "name": "Premium",
            "category": "streaming",
            "monthly_cost": Decimal("119"),
            "grid_fee_monthly": None,
            "spot_pricing": False,
            "binding_end": None,
            "notice_days": 0,
            "invoice_day": 29,
            "status": "active",
            "included_in_rent": False,
            "notes": (
                "Privat · familj-prenum 199 kr för 6 personer = "
                "~33 kr/person"
            ),
        },
        {
            "supplier": "SL",
            "name": "Reskassa autoladd",
            "category": "transport",
            "monthly_cost": Decimal("320"),
            "grid_fee_monthly": None,
            "spot_pricing": False,
            "binding_end": None,
            "notice_days": 0,
            "invoice_day": 30,
            "status": "active",
            "included_in_rent": False,
            "notes": "Auto-laddar 320 kr när saldot < 100 kr",
        },
    ]


DEFAULT_UTILITY_SUBSCRIPTIONS = _default_specs()


def seed_default_utility_subscriptions(s: Session) -> int:
    """Seedа default-katalogen i en scope-DB.

    Idempotent: hoppar över subscriptions som redan finns (matchar på
    supplier + name). Returnerar antal nya rader.
    """
    created = 0
    for spec in _default_specs():
        existing = (
            s.query(UtilitySubscription)
            .filter(
                UtilitySubscription.supplier == spec["supplier"],
                UtilitySubscription.name == spec["name"],
            )
            .first()
        )
        if existing is not None:
            continue
        s.add(UtilitySubscription(**spec))
        created += 1
    if created:
        s.flush()
    return created
