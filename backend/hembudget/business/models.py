"""Scope-DB-modeller för företagsläget.

Spec: dev/v2/foretag.md (kommer i denna PR · Bug #7-utbyggnad)

Modellerna lever i scope-DB (per elev/familj) eftersom företagets
ekonomi är personlig. En elev kan ha max 1 aktiv Company.

Bolagsformer som stöds:
- enskild_firma · ej juridisk person, allt går igenom IB
- ab          · aktiebolag, separat juridisk person, bolagsskatt 20.6 %
- handelsbolag · ej implementerat ännu (Coming soon i UI)
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, TenantMixin


class Company(TenantMixin, Base):
    """Elevens bolag · max 1 aktiv per scope."""
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    org_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    form: Mapped[str] = mapped_column(
        String(20), nullable=False, default="enskild_firma",
    )  # "enskild_firma" | "ab" | "handelsbolag"
    started_on: Mapped[date] = mapped_column(Date, nullable=False)

    # Aktiebolags-specifikt
    share_capital: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )  # Aktiekapital i SEK (min 25 000 för AB 2026)

    # Moms
    vat_registered: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    vat_period: Mapped[str] = mapped_column(
        String(20), nullable=False, default="kvartal",
    )  # "kvartal" | "ar" | "manad"

    # Branschkod (SCB SNI 2007 5-siffrig)
    sni_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    industry_label: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True,
    )

    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    closed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    transactions: Mapped[list["CompanyTransaction"]] = relationship(
        back_populates="company", cascade="all, delete-orphan",
    )
    customers: Mapped[list["CompanyCustomer"]] = relationship(
        back_populates="company", cascade="all, delete-orphan",
    )
    invoices: Mapped[list["CompanyInvoice"]] = relationship(
        back_populates="company", cascade="all, delete-orphan",
    )


class CompanyTransaction(TenantMixin, Base):
    """Inkomster och utgifter i bolaget — separat från privatekonomins
    Transaction-tabell så vi inte blandar."""
    __tablename__ = "company_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )  # "income" | "expense" | "salary" | "vat_payment" | "tax_payment"
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)

    # Belopp i SEK (positiva tal · `kind` styr riktning)
    amount_excl_vat: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False,
    )
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.25"),
    )  # 0.25 / 0.12 / 0.06 / 0.0
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal(0),
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    company: Mapped[Company] = relationship(back_populates="transactions")


class CompanyCustomer(TenantMixin, Base):
    """En kund som bolaget kan fakturera."""
    __tablename__ = "company_customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    org_number: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
    )
    email: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    company: Mapped[Company] = relationship(back_populates="customers")
    invoices: Mapped[list["CompanyInvoice"]] = relationship(
        back_populates="customer",
    )


class CompanyInvoice(TenantMixin, Base):
    """Faktura som bolaget skickat till en kund."""
    __tablename__ = "company_invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("company_customers.id"), nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False)
    issued_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    amount_excl_vat: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False,
    )
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.25"),
    )
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal(0),
    )

    # Status: "draft" | "sent" | "paid" | "overdue" | "cancelled"
    status: Mapped[str] = mapped_column(String(20), default="sent")
    paid_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ROT/RUT-arbete (svensk skattereduktion 2026)
    rot_rut_kind: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True,
    )  # "rot" | "rut" | None
    rot_rut_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    company: Mapped[Company] = relationship(back_populates="invoices")
    customer: Mapped[CompanyCustomer] = relationship(back_populates="invoices")


class CompanyVatPeriod(TenantMixin, Base):
    """En momsrapport-period (kvartal eller år)."""
    __tablename__ = "company_vat_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    period_label: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )  # "2026-Q1" | "2026"
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Beräknat
    output_vat: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal(0),
    )  # Utgående moms (försäljning)
    input_vat: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal(0),
    )  # Ingående moms (inköp)
    net_vat: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal(0),
    )  # Att betala (positivt) eller få tillbaka (negativt)

    # Status: "open" | "filed" | "paid"
    status: Mapped[str] = mapped_column(String(20), default="open")
    filed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    paid_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class CompanyOwnerSalary(TenantMixin, Base):
    """Lön ägaren tar ut till sig själv (gäller AB · enskild firma har
    inte 'lön' utan 'eget uttag')."""
    __tablename__ = "company_owner_salaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    gross_salary: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False,
    )

    # Arbetsgivaravgift 31.42 % (2026 standard, sänkt för unga)
    employer_fee_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.3142"),
    )
    employer_fee_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False,
    )

    # Personal A-skatt (preliminär) — förenklad 30 %
    prel_tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.30"),
    )
    prel_tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False,
    )

    net_to_owner: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False,
    )
    total_cost_to_company: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False,
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
