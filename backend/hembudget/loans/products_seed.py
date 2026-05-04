"""Default-katalog för låneprodukter.

Innehåller 5 standard-produkter som speglar svenska 2026-marknaden
(CSN, bolån, billån, privatlån, sms-lån). Lärare kan seedа dessa per
scope eller anpassa via /v2/teacher/loan-products.

Källor:
- CSN-räntan 2026: 1,7 % (från CSN.se)
- Bolåneränta 2026: 3-4 % (Riksbanken + bolåneindex)
- Privatlån: 8-15 % (Konsumentverket)
- Sms-lån: 25-40 % (Konsumentverket — finansiell rovdrift)
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from ..db.models import LoanProduct


DEFAULT_LOAN_PRODUCTS = [
    {
        "lender": "CSN",
        "name": "Studielån (annuitet)",
        "kind": "csn",
        "interest_rate_min": Decimal("0.017"),
        "interest_rate_max": Decimal("0.017"),
        "max_amount": None,  # CSN har olika tak per termin
        "binding_required": False,
        "description": (
            "CSN-lån för högskolestudier. Återbetalning på 25 år "
            "vanligen. Ränteavdrag 30 % gör räntan effektivt ~1,2 %."
        ),
        "risk_class": "billig",
    },
    {
        "lender": "SEB Bank",
        "name": "Bolån (rörlig)",
        "kind": "bolan",
        "interest_rate_min": Decimal("0.035"),
        "interest_rate_max": Decimal("0.045"),
        "max_amount": Decimal("5000000"),
        "binding_required": False,
        "description": (
            "Bolån mot bostadens säkerhet. Belåningsgrad max 85 %. "
            "Amorteringskrav 1-3 % beroende på belåningsgrad. "
            "Ränteavdrag 30 % på räntor under 100 000 kr/år."
        ),
        "risk_class": "billig",
    },
    {
        "lender": "Volkswagen Finans",
        "name": "Billån",
        "kind": "billan",
        "interest_rate_min": Decimal("0.05"),
        "interest_rate_max": Decimal("0.08"),
        "max_amount": Decimal("400000"),
        "binding_required": True,
        "description": (
            "Lån med bilen som säkerhet. Max 80 % av bilens värde. "
            "Räntan beror på UC-score och bilens värde."
        ),
        "risk_class": "medel",
    },
    {
        "lender": "Resurs Bank",
        "name": "Privatlån (blanco)",
        "kind": "privatlan",
        "interest_rate_min": Decimal("0.08"),
        "interest_rate_max": Decimal("0.15"),
        "max_amount": Decimal("400000"),
        "binding_required": False,
        "description": (
            "Lån utan säkerhet — banken tar all risk, så räntan är hög. "
            "Effektiv ränta 8-15 %. Använd bara om bilig skuld inte är "
            "möjlig."
        ),
        "risk_class": "dyr",
    },
    {
        "lender": "Snabblån AB",
        "name": "Sms-lån (avråds)",
        "kind": "smslan",
        "interest_rate_min": Decimal("0.25"),
        "interest_rate_max": Decimal("0.40"),
        "max_amount": Decimal("30000"),
        "binding_required": False,
        "description": (
            "Mycket dyr kortfristig kredit. 25-40 % effektiv ränta. "
            "En av de vanligaste orsakerna till skuldfälla för unga "
            "vuxna. Avråds starkt."
        ),
        "risk_class": "dyr",
    },
]


def seed_default_loan_products(s: Session) -> int:
    """Seedа default-katalogen i en scope-DB.

    Idempotent: hoppar över produkter som redan finns (matchar på
    lender + kind + name). Returnerar antal nya rader.
    """
    created = 0
    for spec in DEFAULT_LOAN_PRODUCTS:
        existing = (
            s.query(LoanProduct)
            .filter(
                LoanProduct.lender == spec["lender"],
                LoanProduct.kind == spec["kind"],
                LoanProduct.name == spec["name"],
            )
            .first()
        )
        if existing is not None:
            continue
        s.add(LoanProduct(**spec))
        created += 1
    if created:
        s.flush()
    return created
