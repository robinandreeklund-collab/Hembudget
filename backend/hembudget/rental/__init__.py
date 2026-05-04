"""Default-seed för Aktör 08 · Hyresvärden (Fas 2F).

Skapar ett standard-hyreskontrakt enligt prototypen
(/proposals/vol-7/elev.html · p-hyra) — Stockholmshem 2 r o k i
Hökarängen, 7 240 kr/mån, första-handskontrakt på tillsvidare.

Seedа även 4 standard-notiser (hyresavi, trapphusrenovering,
hyresförhandling 0 %, brandsyn) så eleven får en levande timeline.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from ..db.models import RentalContract, RentalNotice


DEFAULT_CONTRACT = dict(
    landlord="Stockholmshem",
    address="Mårdvägen 9C, lgh 1402",
    rooms_label="2 r o k",
    area_sqm=Decimal("47"),
    city="Stockholm",
    district="Hökarängen",
    contract_type="forsta_hand",
    duration_type="tillsvidare",
    monthly_rent=Decimal("7240"),
    deposit=Decimal("0"),
    ocr_reference="21 41 552 88",
    autogiro=True,
    notice_period_months=3,
    queue_years=8,
    queue_priority="snitt 14 år för Hökarängen 2:a",
    market_price_per_sqm=Decimal("51000"),
    status="active",
    notes=(
        "Bostadsrätten i samma hus såldes 2,4 Mkr — bra "
        "köpa-vs-hyra-jämförelse för pedagogiskt syfte."
    ),
)


def _today_minus(days: int) -> date:
    return date.today() - timedelta(days=days)


def _default_notices(contract_id: int) -> list[dict]:
    return [
        {
            "contract_id": contract_id,
            "occurred_on": _today_minus(2),
            "notice_type": "hyresavi",
            "title": "Hyresavi — innevarande månad",
            "description": "Standardhyra · ingen höjning · OCR 21 41 552 88",
            "amount": Decimal("7240"),
            "change_pct": Decimal("0"),
            "status": "paid",
        },
        {
            "contract_id": contract_id,
            "occurred_on": _today_minus(16),
            "notice_type": "trapphusrenovering",
            "title": "Trapphusrenovering",
            "description": (
                "15–17 nästa månad · entré stängd 09–16 · använd "
                "baktrappan via gården"
            ),
            "status": "info",
        },
        {
            "contract_id": contract_id,
            "occurred_on": _today_minus(29),
            "notice_type": "forhandling",
            "title": "Hyresförhandling klar",
            "description": (
                "Förhandling klar mellan Stockholmshem och "
                "Hyresgästföreningen · ingen höjning för "
                "9C-kvarteret"
            ),
            "change_pct": Decimal("0"),
            "status": "acknowledged",
        },
        {
            "contract_id": contract_id,
            "occurred_on": _today_minus(50),
            "notice_type": "brand",
            "title": "Brandsyn klar",
            "description": (
                "Brandsyn genomförd · brandvarnare OK · inga åtgärder"
            ),
            "status": "info",
        },
    ]


def seed_default_rental(s: Session) -> tuple[int, int]:
    """Seedа standardkontrakt + 4 notiser. Idempotent.

    Returnerar (contracts_created, notices_created).
    """
    contracts_created = 0
    notices_created = 0

    existing = (
        s.query(RentalContract)
        .filter(
            RentalContract.landlord == DEFAULT_CONTRACT["landlord"],
            RentalContract.address == DEFAULT_CONTRACT["address"],
        )
        .first()
    )
    if existing is None:
        c = RentalContract(**DEFAULT_CONTRACT)
        s.add(c)
        s.flush()
        contracts_created += 1
        contract_id = c.id
    else:
        contract_id = existing.id

    # Seedа notiser om inga finns för detta kontrakt
    has_notices = (
        s.query(RentalNotice)
        .filter(RentalNotice.contract_id == contract_id)
        .count()
    )
    if has_notices == 0:
        for spec in _default_notices(contract_id):
            s.add(RentalNotice(**spec))
            notices_created += 1
        s.flush()

    return contracts_created, notices_created
