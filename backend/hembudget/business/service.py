"""Domänlogik för företagsläget — moms-beräkning, lönekostnad, bolagsskatt."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .models import (
    Company,
    CompanyInvoice,
    CompanyOwnerSalary,
    CompanyTransaction,
    CompanyVatPeriod,
)


# === Konstanter ===

EMPLOYER_FEE_DEFAULT = Decimal("0.3142")    # 31.42% 2026
EMPLOYER_FEE_YOUNG = Decimal("0.1949")      # 18-24 år 2026
PREL_TAX_DEFAULT = Decimal("0.30")          # Personal A-skatt enkel
CORPORATE_TAX = Decimal("0.206")            # Bolagsskatt 20.6 % 2026
VAT_RATES = (Decimal("0.25"), Decimal("0.12"), Decimal("0.06"), Decimal("0.0"))


# === Lön ===


def compute_owner_salary(
    *,
    gross_salary: int,
    is_young: bool = False,
) -> dict:
    """Räkna ut lönekostnad för ägarens uttag (AB)."""
    gross = Decimal(gross_salary)
    fee_rate = EMPLOYER_FEE_YOUNG if is_young else EMPLOYER_FEE_DEFAULT
    fee = (gross * fee_rate).quantize(Decimal("0.01"))
    prel_tax = (gross * PREL_TAX_DEFAULT).quantize(Decimal("0.01"))
    net = (gross - prel_tax).quantize(Decimal("0.01"))
    total_cost = (gross + fee).quantize(Decimal("0.01"))
    return {
        "gross_salary": float(gross),
        "employer_fee_rate": float(fee_rate),
        "employer_fee_amount": float(fee),
        "prel_tax_rate": float(PREL_TAX_DEFAULT),
        "prel_tax_amount": float(prel_tax),
        "net_to_owner": float(net),
        "total_cost_to_company": float(total_cost),
    }


def book_owner_salary(
    s: Session,
    *,
    company: Company,
    gross_salary: int,
    paid_on: date,
    is_young: bool = False,
    notes: Optional[str] = None,
) -> CompanyOwnerSalary:
    """Skapa CompanyOwnerSalary + matchande CompanyTransaction."""
    calc = compute_owner_salary(
        gross_salary=gross_salary, is_young=is_young,
    )
    row = CompanyOwnerSalary(
        company_id=company.id,
        paid_on=paid_on,
        gross_salary=Decimal(calc["gross_salary"]),
        employer_fee_rate=Decimal(str(calc["employer_fee_rate"])),
        employer_fee_amount=Decimal(str(calc["employer_fee_amount"])),
        prel_tax_rate=Decimal(str(calc["prel_tax_rate"])),
        prel_tax_amount=Decimal(str(calc["prel_tax_amount"])),
        net_to_owner=Decimal(str(calc["net_to_owner"])),
        total_cost_to_company=Decimal(str(calc["total_cost_to_company"])),
        notes=notes,
    )
    s.add(row)

    # Bokföring · skapa expense-transaction för bolagets kostnad
    s.add(CompanyTransaction(
        company_id=company.id,
        occurred_on=paid_on,
        kind="salary",
        category="Lön till ägare",
        description=f"Lön + arb.giv.avg. ({calc['gross_salary']:.0f} kr brutto)",
        amount_excl_vat=Decimal(str(calc["total_cost_to_company"])),
        vat_rate=Decimal("0.0"),
        vat_amount=Decimal("0.0"),
    ))
    s.flush()
    return row


# === Moms ===


def compute_period_vat(
    s: Session,
    *,
    company: Company,
    start: date,
    end: date,
) -> dict:
    """Räkna utgående/ingående moms och netto för en period."""
    txs = (
        s.query(CompanyTransaction)
        .filter(
            CompanyTransaction.company_id == company.id,
            CompanyTransaction.occurred_on >= start,
            CompanyTransaction.occurred_on <= end,
        )
        .all()
    )
    output_vat = sum(
        (Decimal(t.vat_amount or 0) for t in txs if t.kind == "income"),
        Decimal(0),
    )
    input_vat = sum(
        (Decimal(t.vat_amount or 0) for t in txs if t.kind == "expense"),
        Decimal(0),
    )
    net = output_vat - input_vat
    return {
        "output_vat": float(output_vat),
        "input_vat": float(input_vat),
        "net_vat": float(net),
        "n_transactions": len(txs),
    }


def file_vat_period(
    s: Session,
    *,
    company: Company,
    period_label: str,
    start: date,
    end: date,
    due: date,
) -> CompanyVatPeriod:
    """Skapa eller uppdatera VatPeriod-rad och bokför moms-betalning."""
    existing = (
        s.query(CompanyVatPeriod)
        .filter(
            CompanyVatPeriod.company_id == company.id,
            CompanyVatPeriod.period_label == period_label,
        )
        .one_or_none()
    )
    calc = compute_period_vat(s, company=company, start=start, end=end)

    if existing is None:
        existing = CompanyVatPeriod(
            company_id=company.id,
            period_label=period_label,
            start_date=start,
            end_date=end,
            due_date=due,
            output_vat=Decimal(str(calc["output_vat"])),
            input_vat=Decimal(str(calc["input_vat"])),
            net_vat=Decimal(str(calc["net_vat"])),
            status="filed",
            filed_on=date.today(),
        )
        s.add(existing)
    else:
        existing.output_vat = Decimal(str(calc["output_vat"]))
        existing.input_vat = Decimal(str(calc["input_vat"]))
        existing.net_vat = Decimal(str(calc["net_vat"]))
        existing.status = "filed"
        existing.filed_on = date.today()

    # Bokför moms-betalning som expense (om netto > 0)
    if calc["net_vat"] > 0:
        s.add(CompanyTransaction(
            company_id=company.id,
            occurred_on=due,
            kind="vat_payment",
            category="Moms",
            description=f"Moms-inbetalning {period_label}",
            amount_excl_vat=Decimal(str(calc["net_vat"])),
            vat_rate=Decimal("0.0"),
            vat_amount=Decimal("0.0"),
        ))
    s.flush()
    return existing


# === Bolagsskatt ===


def estimate_corporate_tax_for_year(
    s: Session,
    *,
    company: Company,
    year: int,
) -> dict:
    """Räkna förväntad bolagsskatt för aktuellt år (gäller AB).

    Bolagsskatt 2026: 20.6 % av skattepliktigt resultat.
    Resultat = inkomster - utgifter (inklusive lön + arb.giv.avg.).
    """
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    txs = (
        s.query(CompanyTransaction)
        .filter(
            CompanyTransaction.company_id == company.id,
            CompanyTransaction.occurred_on >= start,
            CompanyTransaction.occurred_on <= end,
        )
        .all()
    )
    incomes = sum(
        (Decimal(t.amount_excl_vat or 0) for t in txs if t.kind == "income"),
        Decimal(0),
    )
    expenses = sum(
        (Decimal(t.amount_excl_vat or 0) for t in txs
         if t.kind in ("expense", "salary")),
        Decimal(0),
    )
    profit = incomes - expenses
    tax = max(Decimal(0), profit * CORPORATE_TAX).quantize(Decimal("0.01"))
    return {
        "year": year,
        "income_total": float(incomes),
        "expense_total": float(expenses),
        "profit_before_tax": float(profit),
        "corporate_tax_rate": float(CORPORATE_TAX),
        "estimated_tax": float(tax),
        "profit_after_tax": float(profit - tax),
        "n_transactions": len(txs),
    }
