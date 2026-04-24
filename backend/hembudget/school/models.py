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


class Student(MasterBase):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("login_code", name="uq_student_login_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id"), nullable=False, index=True,
    )
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    class_label: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    login_code: Mapped[str] = mapped_column(String(12), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    teacher: Mapped[Teacher] = relationship(back_populates="students")
    generation_runs: Mapped[list["StudentDataGenerationRun"]] = relationship(
        back_populates="student", cascade="all, delete-orphan",
    )


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
