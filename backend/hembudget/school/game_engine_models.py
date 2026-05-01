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
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .models import MasterBase, Teacher


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
