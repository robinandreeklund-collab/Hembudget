"""Master-DB-modeller för spelmotorn (game_engine).

Spec: dev/game-motor/12-data-modeller.md

Dessa tabeller bor i master-DB eftersom de är klass-nivå (lärare driver
sin klass tid framåt) eller cross-scope (per-elev wellbeing-historik
som lärare aggregerar). Per-månad-artefakter (lönespecar, fakturor)
ligger däremot i scope-DB:n.

Importeras från models.py så att MasterBase.metadata känner till dem
vid create_all.
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .models import MasterBase, Student, Teacher


class ClassCalendar(MasterBase):
    """Klassens spel-tid. En per (lärare, klass-etikett).

    Driver Monthly Engine-tickarna: cron läser `last_tick_year_month`,
    räknar ut nästa månad, och om `paused_until` är passerad tickar
    alla elever i klassen vidare en spelmånad.

    `weeks_per_sim_month` styr tempot:
      1 = snabb (default · 1 realvecka = 1 spelmånad)
      2 = normal (2 realveckor per spelmånad)
      4 = långsam (1 realmånad per spelmånad)

    `last_tick_year_month` är `"YYYY-MM"` (sträng för enkel sortering
    och jämförelse i SQLite + Postgres). När klassen skapas sätts den
    till `sim_start_year_month` minus 1 månad så att första cron-ticken
    landar på sim_start.
    """

    __tablename__ = "class_calendars"
    __table_args__ = (
        UniqueConstraint(
            "teacher_id", "class_label",
            name="uq_class_calendar_teacher_class",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # NULL = "default-kalender för läraren" (alla elever utan klass-etikett).
    # Annars matchar Student.class_label.
    class_label: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True,
    )
    sim_start_year_month: Mapped[str] = mapped_column(
        String(7), nullable=False,  # "YYYY-MM"
    )
    weeks_per_sim_month: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False,
    )
    paused_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    # Senast tickade spelmånaden ("YYYY-MM"). Cron jämför mot beräknad
    # nuvarande sim-månad och tickar diff:en månad-för-månad.
    last_tick_year_month: Mapped[str] = mapped_column(
        String(7), nullable=False,
    )
    last_tick_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    real_start_date: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )

    teacher: Mapped[Teacher] = relationship()


class WeekTickRun(MasterBase):
    """Logg över Monthly Engine-tick per (elev, spelmånad).

    Garanterar idempotens: orchestrator slår upp denna tabell innan
    något genereras. Om en run finns för (student_id, year_month) →
    return utan att röra scope-DB:n.

    `phase_summary` är en JSON-blob med per-fas-statistik:
      {
        "salary":  {"gross": 32000, "net": 22500, "mail_id": 17},
        "fixed":   {"items_created": 6, "total_amount": 12500},
        "variable":{"transactions": 14, "total_amount": 8900},
      }

    Felade ticks markeras med `status="failed"` + `error_message`.
    Lärare kan retry:a genom att radera raden + tick:a om.
    """

    __tablename__ = "week_tick_runs"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "year_month",
            name="uq_week_tick_student_ym",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    year_month: Mapped[str] = mapped_column(
        String(7), nullable=False,  # "YYYY-MM"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="completed",
    )  # "completed" | "failed" | "in_progress"
    seed_used: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        # Profilens seed — möjliggör reproducerbar regenerering
    )
    phase_summary: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )

    student: Mapped[Student] = relationship()


class SchoolClass(MasterBase):
    """Bug #1 · Lärare kan skapa klasser så att elev-creation kan välja
    från dropdown istället för fritext.

    En lärare kan ha flera klasser (t.ex. "8A", "9B", "Vux21"). När en
    lärare loggar in kan hen växla mellan klasser i sin dashboard.
    Elever kan tillhöra max en klass åt gången via Student.class_label
    (sträng-koppling, inte FK, för bakåt-kompatibilitet).
    """
    __tablename__ = "school_classes"
    __table_args__ = (
        UniqueConstraint("teacher_id", "label", name="uq_school_class_teacher_label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(
        String(160), nullable=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    teacher: Mapped[Teacher] = relationship()


class WellbeingEvent(MasterBase):
    """En pentagon-axel-förändring (delta) loggad för audit + Echo-coaching.

    Spec: dev/game-motor/07-pentagon-mekanik.md (Wellbeing-event-loggen)

    Varje gång Monthly Engine, Event Engine eller en lärar-handling
    ändrar pentagonen skrivs en rad här. Echo-modulen läser senaste 30
    dagarna för att förstå vad eleven varit med om.

    `reason_kind`:
      "drift"          — automatisk månadsdrift (M4)
      "event"          — oväntad händelse (Sprint 3)
      "decision"       — eleven accepterade/nekade ett social-förslag
      "goal_achieved"  — mål uppnått
      "init"           — initial pentagon-variation vid karaktärsskapelse

    `applied_delta` är vad som faktiskt skrevs efter momentum-klamp;
    `requested_delta` är vad reason_kind försökte sätta innan klampen.
    Diff:en (clamped) är pedagogiskt intressant: läraren kan se "Eva
    försökte få +20 economy men trögheten klampade till +12".
    """

    __tablename__ = "wellbeing_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True,
    )
    axis: Mapped[str] = mapped_column(String(20), nullable=False)
    requested_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    new_value: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reason_table: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True,
    )
    explanation: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    year_month: Mapped[Optional[str]] = mapped_column(
        String(7), nullable=True, index=True,
    )

    student: Mapped[Student] = relationship()


def shift_year_month(ym: str, months: int) -> str:
    """Lägg till `months` på en 'YYYY-MM'-sträng. Hanterar negativa tal.

    Exempel:
      shift_year_month("2026-01", 1)  -> "2026-02"
      shift_year_month("2026-01", -1) -> "2025-12"
      shift_year_month("2026-12", 3)  -> "2027-03"
    """
    year, month = ym.split("-")
    total = int(year) * 12 + (int(month) - 1) + months
    new_year, new_month = divmod(total, 12)
    return f"{new_year:04d}-{new_month + 1:02d}"


def compute_current_sim_year_month(
    sim_start_year_month: str,
    real_start_date: datetime,
    now: datetime,
    weeks_per_sim_month: int,
) -> str:
    """Beräkna vilken spelmånad klassen "borde" vara på just nu.

    Baseras på real-tid sedan klass-start. Cron jämför resultatet mot
    `last_tick_year_month` och tickar diff:en framåt.
    """
    if now <= real_start_date:
        return sim_start_year_month
    real_weeks = (now - real_start_date).days / 7.0
    sim_months_elapsed = int(real_weeks // max(weeks_per_sim_month, 1))
    return shift_year_month(sim_start_year_month, sim_months_elapsed)
