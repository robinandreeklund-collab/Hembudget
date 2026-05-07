"""Kanonisk kassa-helper för bolaget · använd överallt.

Tidigare hade vi 4-5 olika formler för bolagets kassa (foretag.py:
biz_bank_overview, foretag_growth.py:_kassa, business/service.py:
compute_business_pentagon, api/allabolag.py:sync_class_company_share).
De gav olika svar för samma företag — t.ex. /v2/foretag visade
−22 500 kr medan /v2/foretag/tillvaxt visade 2 500 kr för samma bolag.
Diff var oftast share_capital som ena formeln addade och den andra
inte.

Den här modulen är ENDA sanningen. Alla vyer ska importera och kalla
compute_company_cash().

Definition:
    kassa = Σ(income tx) − Σ(expense + salary + vat_payment +
                            tax_payment + asset_purchase tx)

share_capital som attribut på Company representerar BUNDET eget
kapital (legal AB-status). Kontant insättning bokförs vid create_
company som en CompanyTransaction(kind="income", kategori="Aktiekapital
· insättning"). Loan-funded AB har redan en loan-income-tx som
representerar samma 25 000 kr — så vi DUBBELRÄKNAR ALDRIG
share_capital. Detta höll bank-overview tidigare korrekt; _kassa-
formeln var den buggiga (och drev fel siffra in i Tillväxt).
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from .models import Company, CompanyTransaction


# Tx-kinds som drar från kassan (cash-flow-out)
_OUTFLOW_KINDS = {
    "expense",
    "salary",
    "vat_payment",
    "tax_payment",
    "asset_purchase",
}


def compute_company_cash(s: Session, company: Company) -> int:
    """Returnera bolagets nuvarande kassa (likviditet) i hela kronor.

    Räknas som summan av alla CompanyTransaction där kind=income drar
    in pengar och övriga kinds drar ut. Fail-soft mot saknad data."""
    txs = (
        s.query(CompanyTransaction)
        .filter(CompanyTransaction.company_id == company.id)
        .all()
    )
    bal = Decimal(0)
    for t in txs:
        amt = Decimal(t.amount_excl_vat or 0)
        if t.kind == "income":
            bal += amt
        elif t.kind in _OUTFLOW_KINDS:
            bal -= amt
        # Okänd kind: räkna inte alls (logik-fel ska inte forma kassa)
    return int(bal)


def can_afford(
    s: Session, company: Company, cost: int,
) -> tuple[bool, int]:
    """Kontroll inför ett köp. Returnerar (ok, kassa).

    Eleven får bara köpa något som täcks av kassan. Negativa saldon
    drivs av engångskostnader som passerar oblockerat (t.ex.
    avskrivnings-bokningar i tick) och ska aldrig komma från ett
    medvetet köp. Användning:

        ok, bal = can_afford(s, co, cost)
        if not ok:
            raise HTTPException(402, ...)
    """
    bal = compute_company_cash(s, company)
    return bal >= cost, bal
