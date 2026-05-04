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

    # Spelmotor (Fas 2 i deb/README) ============================
    # Affärsidé · fri text från eleven, AI-modererad innan sparning
    business_idea: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Svårighetsnivå: basics → grund (ÄK1), advanced → fördjupning (ÄK2)
    level: Mapped[str] = mapped_column(
        String(20), default="basics", nullable=False,
    )  # "basics" | "advanced"
    # Rykte 0–100 · drivs upp av kvalitet/marknadsföring, ner av klagomål
    reputation: Mapped[int] = mapped_column(
        Integer, default=50, nullable=False,
    )
    # Antal levererade jobb (used för engine-beräkning)
    jobs_delivered: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    # Snitt-kvalitet på levererade jobb (0–100, exponentiellt utjämnad)
    avg_quality: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    # Antal aktiva klagomål (drar ner pipelinen)
    open_complaints: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    # Senaste tick-vecka (deterministisk seed)
    week_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Leveranskapacitet (1 = själv, +1 per anställd)
    delivery_capacity: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False,
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


# === Spelmotor: offert · jobb · marknadsföring · beslut · leverantör ===
#
# Spec: deb/README.md avsnitt 4–6 + 12.
# Allt deterministiskt seedat på (company_id, week_no) — läraren kan
# spela om en vecka för att förstå utfall.


class JobOpportunity(TenantMixin, Base):
    """En offertförfrågan från en simulerad kund.

    Genereras av pipeline_generator vid varje veckostick.
    """
    __tablename__ = "biz_job_opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Kund
    customer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    customer_segment: Mapped[str] = mapped_column(
        String(20), default="privat",
    )  # privat | foretag | kommun
    price_sensitivity: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("0.5"),
    )
    quality_sensitivity: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("0.5"),
    )
    payment_morality: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("0.9"),
    )

    # Jobbets innehåll
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    industry_tag: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True,
    )

    # Marknad och deadline
    market_price: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_delivery_days: Mapped[int] = mapped_column(
        Integer, default=14, nullable=False,
    )
    deadline_on: Mapped[date] = mapped_column(Date, nullable=False)

    # Status: open | quoted | won | lost | cancelled | expired
    status: Mapped[str] = mapped_column(
        String(20), default="open", nullable=False,
    )

    week_no: Mapped[int] = mapped_column(Integer, nullable=False)
    received_on: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    quote: Mapped[Optional["Quote"]] = relationship(
        back_populates="opportunity", uselist=False,
        cascade="all, delete-orphan",
    )


class Quote(TenantMixin, Base):
    """Elevens offert på en JobOpportunity."""
    __tablename__ = "biz_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_opportunities.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    offered_price: Mapped[int] = mapped_column(Integer, nullable=False)
    offered_delivery_days: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    pitch_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    pitch_quality: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(4, 3), nullable=True,
    )  # 0..1 från evaluate_quote_pitch
    accept_probability: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(4, 3), nullable=True,
    )
    accepted: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    decision_explanation: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )

    submitted_on: Mapped[date] = mapped_column(Date, nullable=False)
    decided_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    opportunity: Mapped[JobOpportunity] = relationship(
        back_populates="quote",
    )


class Job(TenantMixin, Base):
    """Vunnen offert som blir uppdrag eleven ska leverera."""
    __tablename__ = "biz_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("biz_job_opportunities.id"),
        nullable=False, unique=True,
    )
    quote_id: Mapped[int] = mapped_column(
        ForeignKey("biz_quotes.id"), nullable=False,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    agreed_price: Mapped[int] = mapped_column(Integer, nullable=False)
    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    expected_complete_on: Mapped[date] = mapped_column(
        Date, nullable=False,
    )

    # Status: in_progress | delivered | invoiced | paid | disputed
    status: Mapped[str] = mapped_column(
        String(20), default="in_progress", nullable=False,
    )

    quality_score: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    delivered_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    invoice_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("company_invoices.id"), nullable=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class MarketingCampaign(TenantMixin, Base):
    """En marknadsföringskampanj som ger pipeline-boost."""
    __tablename__ = "biz_marketing_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    kind: Mapped[str] = mapped_column(
        String(40), nullable=False,
    )  # social | flygblad | google | sponsring | event
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    copy_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    cost: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_weeks: Mapped[int] = mapped_column(
        Integer, default=4, nullable=False,
    )

    ai_quality_factor: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(4, 3), nullable=True,
    )  # 0.5..1.5 från evaluate_marketing_copy
    ai_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    base_pipeline_boost: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("1.0"),
    )

    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class BusinessDecision(TenantMixin, Base):
    """Strategiskt beslut: anställa, friskvård, leasing, försäkring."""
    __tablename__ = "biz_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    kind: Mapped[str] = mapped_column(
        String(40), nullable=False,
    )  # hire_part_time | wellness | car_lease | insurance | new_office
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    monthly_cost: Mapped[int] = mapped_column(Integer, default=0)
    one_time_cost: Mapped[int] = mapped_column(Integer, default=0)

    capacity_delta: Mapped[int] = mapped_column(Integer, default=0)
    reputation_delta: Mapped[int] = mapped_column(Integer, default=0)
    insurance_kind: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True,
    )

    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class SupplierInvoice(TenantMixin, Base):
    """Inkommande leverantörsfaktura.

    Källa: 'system' (genererad av tick_engine), 'teacher' (mass-skick),
    'manual' (eleven matar in själv från ett papper).
    """
    __tablename__ = "biz_supplier_invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    sender_name: Mapped[str] = mapped_column(String(160), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(40), nullable=False)
    issued_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    amount_excl_vat: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.25"),
    )

    source: Mapped[str] = mapped_column(String(20), default="system")
    teacher_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )

    # Status: open | paid | overdue | disputed
    status: Mapped[str] = mapped_column(String(20), default="open")
    paid_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class BusinessTickJob(TenantMixin, Base):
    """En körning av tick_engine för audit och re-spelning."""
    __tablename__ = "biz_tick_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    week_no: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )

    # Status: queued | running | done | failed
    status: Mapped[str] = mapped_column(
        String(20), default="done", nullable=False,
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Vad hände i denna tick (för audit + debug)
    summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    n_new_opportunities: Mapped[int] = mapped_column(Integer, default=0)
    n_quotes_decided: Mapped[int] = mapped_column(Integer, default=0)
    n_jobs_delivered: Mapped[int] = mapped_column(Integer, default=0)
    n_invoices_paid: Mapped[int] = mapped_column(Integer, default=0)
    reputation_after: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
