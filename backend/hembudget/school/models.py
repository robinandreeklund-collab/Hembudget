"""SQLAlchemy-modeller för master-DB (lärare, elever, generering-runs).

Separat Declarative Base från student-DB:ns modeller — master innehåller
inte elev-data och student-DB:ar innehåller inte lärare/elever.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class MasterBase(DeclarativeBase):
    """Separat Base så master-DB och student-DB inte krockar på
    metadata.create_all()."""
    pass


class Teacher(MasterBase):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    students: Mapped[list["Student"]] = relationship(back_populates="teacher")
    families: Mapped[list["Family"]] = relationship(back_populates="teacher")


class Family(MasterBase):
    """En "familj" = grupp av elever som delar hushållsekonomi (samma
    student-DB). Används pedagogiskt: två elever kan vara sambo/föräldrar
    som planerar tillsammans.
    """
    __tablename__ = "families"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    teacher: Mapped[Teacher] = relationship(back_populates="families")
    members: Mapped[list["Student"]] = relationship(back_populates="family")


class Student(MasterBase):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("login_code", name="uq_student_login_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id"), nullable=False, index=True,
    )
    family_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("families.id"), nullable=True, index=True,
    )
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    class_label: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    login_code: Mapped[str] = mapped_column(String(12), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    teacher: Mapped[Teacher] = relationship(back_populates="students")
    family: Mapped[Optional[Family]] = relationship(back_populates="members")
    profile: Mapped[Optional["StudentProfile"]] = relationship(
        back_populates="student",
        uselist=False,
        cascade="all, delete-orphan",
    )
    generation_runs: Mapped[list["StudentDataGenerationRun"]] = relationship(
        back_populates="student", cascade="all, delete-orphan",
    )


class StudentProfile(MasterBase):
    """Elevens "ekonomi-identitet" — sätts vid skapelse, deterministiskt
    seedat på student_id. Driver onboardingen och scenario-genereringen
    (lön, fakturor, köp matchar profilens personlighet och livsmanus).
    """
    __tablename__ = "student_profiles"

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Karriär
    profession: Mapped[str] = mapped_column(String(80), nullable=False)
    employer: Mapped[str] = mapped_column(String(120), nullable=False)
    gross_salary_monthly: Mapped[int] = mapped_column(Integer, nullable=False)
    # Beräknat på server enl. _compute_net_salary i tax.py — cachas här
    # så onboardingen inte behöver räkna om varje gång
    net_salary_monthly: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_rate_effective: Mapped[float] = mapped_column(nullable=False)

    # Personlighet styr scenario-generatorn
    # "sparsam" | "slosaktig" | "blandad"
    personality: Mapped[str] = mapped_column(
        String(20), nullable=False, default="blandad",
    )

    # Livsmanus
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    city: Mapped[str] = mapped_column(String(60), nullable=False)
    # "ensam" | "sambo" | "familj_med_barn"
    family_status: Mapped[str] = mapped_column(String(30), nullable=False)
    # "hyresratt" | "bostadsratt" | "villa"
    housing_type: Mapped[str] = mapped_column(String(20), nullable=False)
    housing_monthly: Mapped[int] = mapped_column(Integer, nullable=False)

    has_mortgage: Mapped[bool] = mapped_column(Boolean, default=False)
    has_car_loan: Mapped[bool] = mapped_column(Boolean, default=False)
    has_student_loan: Mapped[bool] = mapped_column(Boolean, default=False)
    has_credit_card: Mapped[bool] = mapped_column(Boolean, default=True)

    # Backstory som visas i onboardingen
    backstory: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    student: Mapped[Student] = relationship(back_populates="profile")


class StudentDataGenerationRun(MasterBase):
    """Logg av genererad månadsdata per elev. Används för idempotens
    (hoppa över om redan kört) och för att visa i lärar-UI vilka månader
    som är inskickade."""
    __tablename__ = "student_generation_runs"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "year_month",
            name="uq_student_generation_month",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    student: Mapped[Student] = relationship(back_populates="generation_runs")


class ScenarioBatch(MasterBase):
    """En batch av PDF-artefakter som läraren skickar ut för en månad.

    Ersätter den gamla "spruta data direkt i DB:n"-modellen — istället
    skapar batchen ett antal BatchArtifacts (PDF:er) som eleven själv
    måste ladda ned + importera via /upload. Pedagogiskt: eleven lär
    sig flödet bank-PDF → import → kategorisering.
    """
    __tablename__ = "scenario_batches"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "year_month",
            name="uq_scenario_batch_month",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    artifacts: Mapped[list["BatchArtifact"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="BatchArtifact.sort_order",
    )


class BatchArtifact(MasterBase):
    """En enskild PDF i en batch — kontoutdrag, lönespec, lånebesked,
    kreditkortsfaktura osv. Lagras som binär (BLOB) i master-DB:n så vi
    slipper hantera fillagring separat. Storleksordning < 100 KB per fil.
    """
    __tablename__ = "batch_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("scenario_batches.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # "kontoutdrag" | "lonespec" | "lan_besked" | "kreditkort_faktura"
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pdf_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # Strukturerad metadata för parsern (totalbelopp, period, ev.
    # transaktioner) — gör att vi kan validera att eleven importerat
    # rätt fil och kontrollera matchning.
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    imported_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    batch: Mapped[ScenarioBatch] = relationship(back_populates="artifacts")


class Assignment(MasterBase):
    """Uppdrag som läraren ger en elev (eller "alla mina elever").

    Statusen utvärderas dynamiskt på server (kör _check_status mot
    elevens DB) — vi cachar inte bool, utan räknar varje gång läraren
    öppnar dashboardet. Snabbt nog då en elev har lite data.
    """
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id"), nullable=False, index=True,
    )
    # NULL = "alla elever till denna lärare"
    student_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # "set_budget" | "import_batch" | "balance_month" | "review_loan"
    # | "categorize_all" | "save_amount" | "free_text"
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_year_month: Mapped[Optional[str]] = mapped_column(
        String(7), nullable=True,
    )
    params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
