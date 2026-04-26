"""Master-DB-modeller för sociala mekanismer mellan elever.

ClassEventInvite — när en elev bjuder en klasskompis på ett event.
Lever i master-DB:n eftersom det går mellan olika elev-scopes (varje
elev har isolerad scope-DB, så en delad bridge-tabell behövs).

ClassDisplaySettings — lärarens super-admin-toggles för klassrums-
gemensamma funktioner (klasslista, bjudningar, namn-display).
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .models import MasterBase


class ClassEventInvite(MasterBase):
    """Bjudning från en elev till en annan inom samma lärares klass.

    status:
      "pending"  — väntar på svar
      "accepted" — mottagaren tog emot (Swish-skuld eller egen kostnad)
      "declined" — mottagaren tackade nej
      "expired"  — deadline passerade
      "cancelled" — bjudaren ångrade
    """
    __tablename__ = "class_event_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    to_student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Event-mall + datumförslag (mottagaren får ett identiskt event i
    # sin scope om hen accepterar).
    event_code: Mapped[str] = mapped_column(String(60), nullable=False)
    event_title: Mapped[str] = mapped_column(String(160), nullable=False)
    proposed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    deadline: Mapped[date] = mapped_column(Date, nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Kostnadsdelnings-modell: "split" (50/50), "inviter_pays" (gratis),
    # "each_pays_own" (full kostnad var för sig). Kopieras från
    # ClassDisplaySettings vid skapelse — låses så reglen inte ändras
    # mitt i en bjudning.
    cost_split_model: Mapped[str] = mapped_column(
        String(20), default="split", nullable=False,
    )
    # Personligt meddelande från bjudaren — pedagogiskt: ger kontext
    # och låter eleven öva på social kommunikation.
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True,
    )
    # Vid 'split' eller 'each_pays_own' — Swish-skuld från mottagaren
    # till bjudaren. Sparas som en UpcomingTransaction i mottagarens
    # scope när status='accepted'.
    swish_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    responded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )


class ClassDisplaySettings(MasterBase):
    """Per lärar-konto: opt-in toggles för klassgemensamma funktioner.
    Default: allt AV förutom invite_classmates_enabled.

    3-stegs opt-in:
      1. Super-admin sätter denna (per lärare)
      2. Lärare slår på per klass (i V2 — finns inte separat klass-
         tabell ännu, så detta är per-lärare)
      3. Elev kan välja att visas under sitt namn (PersonalityProfile-
         flagga eller separat — V2)
    """
    __tablename__ = "class_display_settings"
    __table_args__ = (
        UniqueConstraint("teacher_id", name="uq_class_display_teacher"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Anonymiserad rangordning på elev-dashboard
    class_list_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    # Visa elever med fullständigt namn (kräver opt-in per elev)
    show_full_names: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    # Tillåt klasskompis-bjudningar
    invite_classmates_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    cost_split_model: Mapped[str] = mapped_column(
        String(20), default="split", nullable=False,
    )
    # Lärare kan skapa klassgemensamma events (V2-feature)
    class_event_creation_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    # Max bjudningar per elev per vecka — anti-spam
    max_invites_per_week: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class TeacherClassEvent(MasterBase):
    """Klassgemensamt event som läraren skapar och som distribueras
    till alla elever. Pedagogiskt: 'klassresan till Berlin' känns
    annorlunda att neka när 25 av 26 sa ja.

    Status (event-livscykel):
      "draft"        — läraren skapar men har inte distribuerat
      "distributed"  — alla elever har fått det i sina inboxar
      "closed"       — deadline passerat, ingen kan svara mer
    """
    __tablename__ = "teacher_class_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Valfritt class_label-filter (None = alla elever, annars bara
    # eleverna i den klassen)
    class_label: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(20), default="culture", nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    proposed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    deadline: Mapped[date] = mapped_column(Date, nullable=False)
    # Wellbeing-impact när elev accepterar (samma fält som EventTemplate)
    impact_economy: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact_health: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact_social: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact_leisure: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact_safety: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False, index=True,
    )
    distributed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
