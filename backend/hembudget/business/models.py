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
    # Bransch-nyckel · en av de 10 fasta branscherna i industries.py.
    # Driver pris-baseline, marginal, säsong, segmentmix m.m.
    industry_key: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True,
    )
    # Stad · ärvs från karaktären vid create. Styr lokal-kostnad,
    # pipeline-täthet och pris-multiplicator.
    city_key: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True,
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
    # Tidsstämpel för senaste auto-tick. Används av auto_tick_if_due-
    # helpern: när en biz-endpoint anropas och `last_auto_tick_at` är
    # äldre än AUTO_TICK_INTERVAL_HOURS körs så många run_business_week
    # som behövs för att fånga upp. Ger en levande spelmotor utan att
    # eleven ska klicka "Stega vecka". Default `created_at` så bolag
    # som skapas precis nu inte tickar igen direkt (vi kör 2 init-tickar
    # i create_company).
    last_auto_tick_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    # Leveranskapacitet (1 = själv, +1 per anställd)
    delivery_capacity: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False,
    )
    # Bas-utrustning · spärrar pipeline-generering tills inköpt.
    # Eleven måste köpa kontant från privatkonto, från bolagets kassa
    # eller via lån INNAN nya offertförfrågningar kommer in.
    has_base_equipment: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    base_equipment_purchased_on: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
    )
    # Bil-unlock · krävs av vissa branscher (snickare, rörmokare,
    # elektriker, fotograf, catering) för att över huvud taget kunna
    # ta jobb. Branscher som requires_car=False struntar i denna.
    has_car: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    car_purchased_on: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
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
    # Kräver bil att utföra (sätts vid emit baserat på industri +
    # privat-kund-segment) · spärrar submitQuote om eleven saknar bil
    requires_car: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
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

    # Tids-kapacitet (Fas K)
    # Skattat antal arbetstimmar för uppdraget. Sätts från industri-spec
    # vid create. Används av time-capacity-helpern och overload-fasen.
    estimated_hours: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    hours_per_week: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )

    # Försenings-spårning · drivs av _phase_overload_consequences
    delays_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    last_delayed_on: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
    )
    # Original-deadline · sparas så vi kan visa "förväntad: X, faktisk: Y"
    original_deadline: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
    )

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


class CompanyAnnualReport(TenantMixin, Base):
    """Årsbokslut + deklaration som AI Bolagsverket granskar.

    Spec: dev/feature-allabolag.md (Fas B)

    Flow:
      1. Eleven samlar transaktioner under året
      2. Klickar "Skicka in årsredovisning" → status=submitted
      3. AI läser auto-genererat bokslut (intäkter, kostnader,
         resultat, eget kapital) + ev. lärar-prompt anpassning
      4. AI returnerar approved (med kommentarer) eller rejected
         (med vilken rättning som krävs)
      5. Approved → ClassCompanyShare.annual_report_status = "approved"
         → syns på Allabolag

    Vi sparar både input (snapshot vid submit) och AI:s svar för audit.
    """
    __tablename__ = "biz_annual_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Bokslutsår (kalenderår) — t.ex. 2025
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)

    # Status: draft | submitted | reviewing | approved | rejected
    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False,
    )

    # Snapshot vid submit (immutable efter submit)
    revenue_total: Mapped[int] = mapped_column(Integer, default=0)
    expense_total: Mapped[int] = mapped_column(Integer, default=0)
    salary_total: Mapped[int] = mapped_column(Integer, default=0)
    profit_before_tax: Mapped[int] = mapped_column(Integer, default=0)
    corporate_tax: Mapped[int] = mapped_column(Integer, default=0)
    profit_after_tax: Mapped[int] = mapped_column(Integer, default=0)
    equity_end: Mapped[int] = mapped_column(Integer, default=0)
    n_invoices_paid: Mapped[int] = mapped_column(Integer, default=0)
    n_invoices_unpaid: Mapped[int] = mapped_column(Integer, default=0)

    # Elevens kommentar (frivillig) som följer med deklarationen
    student_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # AI-svar
    ai_decision: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
    )  # approved | rejected
    ai_feedback_md: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )  # markdown-text · pedagogisk feedback från AI
    ai_issues: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
    )  # lista av issues vid rejected (kategori + förklaring)

    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class CompanyLoan(TenantMixin, Base):
    """Företagslån · syns på balansräkningen + AI Bolagsverket-granskning.

    Spec: dev/feature-allabolag.md (Fas E)

    Kan vara:
    - "startup_capital" · använt för aktiekapital vid AB-start
    - "growth" · för investering i lokal/utrustning/anställning
    - "buffer" · likviditets-buffert vid svag period

    Ränta + amorteringsplan beräknas vid skapande baserat på företags-UC.
    Privat-lån (eleven står som personlig borgensman) syns i privat-
    scope-DB:n via vanliga Loan-modellen · CompanyLoan här ÄR bolagets
    lån i bolagets namn.
    """
    __tablename__ = "biz_company_loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    purpose: Mapped[str] = mapped_column(
        String(40), default="growth", nullable=False,
    )  # startup_capital | growth | buffer
    lender: Mapped[str] = mapped_column(
        String(80), default="Företagsbanken AB", nullable=False,
    )

    # Finansiella villkor
    principal: Mapped[int] = mapped_column(Integer, nullable=False)
    outstanding: Mapped[int] = mapped_column(Integer, nullable=False)
    interest_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False,
    )  # 0.0950 = 9.50 %
    monthly_payment: Mapped[int] = mapped_column(Integer, nullable=False)
    months_total: Mapped[int] = mapped_column(Integer, nullable=False)
    months_left: Mapped[int] = mapped_column(Integer, nullable=False)

    # Personlig borgen · ägaren riskerar privat-ekonomi om bolaget går omkull
    is_personal_guarantee: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )

    # Status: active | repaid | defaulted
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False,
    )

    started_on: Mapped[date] = mapped_column(
        Date, server_default=func.current_date(),
    )
    last_payment_on: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class CompanyLocation(TenantMixin, Base):
    """Företagets lokal · gates max-anställda och max-jobs i tid.

    Spec: Fas F"""
    __tablename__ = "biz_company_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    location_kind: Mapped[str] = mapped_column(
        String(40), nullable=False,
    )  # home | rented_1r | rented_2r | office_50 | office_120
    monthly_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_employees: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_concurrent_jobs: Mapped[int] = mapped_column(
        Integer, default=2, nullable=False,
    )
    is_owned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    purchase_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_on: Mapped[date] = mapped_column(
        Date, server_default=func.current_date(),
    )
    ended_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CompanyEquipment(TenantMixin, Base):
    """Investering i bättre utrustning. Multiplicerar speed_per_employee.

    Spec: Fas F"""
    __tablename__ = "biz_company_equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    equipment_kind: Mapped[str] = mapped_column(
        String(40), nullable=False,
    )  # standard | second_hand | premium | specialist
    purchase_price: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    speed_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("1.00"), nullable=False,
    )
    breakdown_risk: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("0.000"), nullable=False,
    )
    purchased_on: Mapped[date] = mapped_column(
        Date, server_default=func.current_date(),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CompanyMcpRental(TenantMixin, Base):
    """MCP · 'More Capacity Programmatically' = inhyrd frilansare för
    1 vecka. Snabb-fix när ingen anställd finns och deadlines pressar.

    Spec: Fas F"""
    __tablename__ = "biz_mcp_rentals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    weeks: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cost_total: Mapped[int] = mapped_column(Integer, nullable=False)
    started_on: Mapped[date] = mapped_column(
        Date, server_default=func.current_date(),
    )
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False,
    )  # active | finished
