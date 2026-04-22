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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    bank: Mapped[str] = mapped_column(String(60), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # checking, credit, isk, savings
    currency: Mapped[str] = mapped_column(String(8), default="SEK")
    account_number: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    opening_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    opening_balance_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Kreditgräns — sätts bara för credit-kort. Används för att visa
    # kvar att utnyttja ("kredit kvar") och varna vid nära-gräns.
    credit_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    # För kreditkort: bankgiro som används för att betala fakturan.
    # Används för att para autogiro-transaktioner från lönekontot mot
    # rätt kortkonto ("Betalning BG 5127-5477 American Exp" → Amex-kort).
    bankgiro: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    # Sista 4 siffror på kortnumret. Används för att skilja på sub-konton
    # för olika kortinnehavare (huvudkort + extrakort på samma faktura).
    card_last_digits: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    # Parent-kort-konto: när vi delar upp en MC-faktura per kortinnehavare
    # pekar sub-kontona på parent som håller fakturasumman + betalningen.
    parent_account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    pays_credit_account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    budget_monthly: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("hash", name="uq_tx_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="SEK")
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_merchant: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    subcategory_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_file_id: Mapped[Optional[int]] = mapped_column(ForeignKey("imports.id"), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ai_confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    user_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_transfer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    transfer_pair_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="transactions")
    category: Mapped[Optional[Category]] = relationship(foreign_keys=[category_id])
    splits: Mapped[list["TransactionSplit"]] = relationship(
        back_populates=None,
        primaryjoin="Transaction.id == TransactionSplit.transaction_id",
        foreign_keys="[TransactionSplit.transaction_id]",
        cascade="all, delete-orphan",
        order_by="TransactionSplit.sort_order",
    )


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern: Mapped[str] = mapped_column(String(200), nullable=False)
    is_regex: Mapped[bool] = mapped_column(Boolean, default=False)
    merchant: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    source: Mapped[str] = mapped_column(String(20), default="user")  # user, seed, llm


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("month", "category_id", name="uq_budget_month_cat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id"), nullable=True)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant: Mapped[str] = mapped_column(String(120), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="SEK")
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    next_expected_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # mortgage, savings_goal, move
    params: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Import(Base):
    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    bank: Mapped[str] = mapped_column(String(60), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user, assistant, tool, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    lender: Mapped[str] = mapped_column(String(80), nullable=False)  # SBAB, SEB, Länsförsäkringar…
    loan_number: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    principal_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # "Aktuellt lånebelopp" när lånet registrerades (från bankens vy via vision).
    # Om satt används detta som bas i outstanding_balance i stället för
    # principal_amount — så gamla amorteringar före vi började tracka inte
    # behöver matchas för att saldot ska stämma. Nya amorteringar drar detta
    # belopp på vanligt sätt.
    current_balance_at_creation: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)

    interest_rate: Mapped[float] = mapped_column(nullable=False)         # nominell, t.ex. 0.042
    binding_type: Mapped[str] = mapped_column(String(40), default="rörlig")  # rörlig, 3mån, 1år, 3år, 5år
    binding_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    amortization_monthly: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    property_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)

    match_pattern: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Budgetkategori — "Huslån", "Billån", "Studielån" etc. Ränta och
    # amortering från detta lån kategoriseras automatiskt som den här
    # kategorin när matchern länkar bankbetalningen.
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LoanPayment(Base):
    """Koppling transaktion → lån, klassificerad som ränta eller amortering.

    EJ unique på transaction_id — en bankrad kan splitta i både ränta och
    amortering (t.ex. Nordeas "Omsättning lån 4662 kr" = amort 2700 + ränta
    1962). Unikheten upprätthålls i stället av (transaction_id, payment_type)
    så vi inte dubblar samma typ.
    """
    __tablename__ = "loan_payments"
    __table_args__ = (
        UniqueConstraint(
            "transaction_id", "payment_type", name="uq_loan_payment_tx_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"), nullable=False, index=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # alltid positivt
    payment_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "interest" | "amortization"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LoanScheduleEntry(Base):
    """Planerad kommande lånebetalning — används för exakt belopp+datum-
    matchning mot nya transaktioner. Betydligt pålitligare än textmatchning
    eftersom bankens autogiro-beloppen är exakta.
    """
    __tablename__ = "loan_schedule_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"), nullable=False, index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_type: Mapped[str] = mapped_column(String(20), nullable=False)  # interest | amortization
    # Ej unique — samma bankpost kan täcka två schedule-rader
    # (ränta + amortering) i ett svep, t.ex. Nordeas "Omsättning lån".
    matched_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id"), nullable=True, index=True
    )
    matched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UpcomingTransaction(Base):
    """Planerade kommande transaktioner — fakturor och löner som ännu inte
    bokats, men som vi vet kommer. Används för cashflow-prognos + att räkna
    ut hur mycket pengar som kan fördelas 50/50 som privata pengar.
    """
    __tablename__ = "upcoming_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # "bill" | "income"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # positivt
    expected_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)   # förfallodag
    owner: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)  # "Robin", "Partner"
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    recurring_monthly: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | vision_ai | ocr
    source_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Extraherad fakturadata
    invoice_number: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    invoice_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    ocr_reference: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    bankgiro: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    plusgiro: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    iban: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # Debitering: vilket konto och vilket datum
    debit_account_id: Mapped[Optional[int]] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    debit_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)   # default = expected_date
    autogiro: Mapped[bool] = mapped_column(Boolean, default=False)

    matched_transaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("transactions.id"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    lines: Mapped[list["UpcomingTransactionLine"]] = relationship(
        back_populates="upcoming",
        cascade="all, delete-orphan",
        order_by="UpcomingTransactionLine.sort_order",
    )


class UpcomingTransactionLine(Base):
    """Enskild post på en planerad faktura.

    Exempel: en faktura från Hjo Energi kan innehålla rader för el,
    vatten och bredband. Totalsumman på fakturan = sum(lines.amount)
    (alla positiva). När fakturan matchas mot en riktig bankrad kopieras
    raderna till transaction_splits med tecken enligt UpcomingTransaction.kind.
    """

    __tablename__ = "upcoming_transaction_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upcoming_id: Mapped[int] = mapped_column(
        ForeignKey("upcoming_transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # positivt
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    upcoming: Mapped[UpcomingTransaction] = relationship(back_populates="lines")
    category: Mapped[Optional[Category]] = relationship(foreign_keys=[category_id])


class TransactionSplit(Base):
    """Uppdelning av en faktisk transaktion i flera budgetposter.

    När en UpcomingTransaction med lines matchas mot en bankrad kopieras
    lines hit — varje split har tecken enligt transaktionen (negativt för
    utgifter, positivt för inkomster). Budget/rapporter ska använda splits
    om de finns, annars falla tillbaka på transactions.category_id + amount.

    Invariant: sum(splits.amount) == transactions.amount (toleranstestas i
    apply-lagret men DB-constraint är inte möjlig i sqlite).
    """

    __tablename__ = "transaction_splits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)  # tecken bevaras
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="upcoming")
    # "upcoming" (kopierad från UpcomingTransactionLine), "manual", "llm"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    category: Mapped[Optional[Category]] = relationship(foreign_keys=[category_id])


class TaxEvent(Base):
    __tablename__ = "tax_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(24), nullable=False)  # isk_deposit, k4_sale, rot, rut, interest
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    transaction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transactions.id"), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


def create_all() -> None:
    from .base import get_engine

    Base.metadata.create_all(get_engine())
