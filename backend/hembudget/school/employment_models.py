"""ClassmateEmployment · klasskompis-anställning över scope-gränser.

Spec: dev/employment-flows.md (Fas C)

Företaget bor i ägarens scope-DB (TenantMixin) men en anställning
binder TVÅ elever (ägaren + den anställde) som har olika scope-
DB:s. Anställnings-raden måste därför ligga i MASTER-DB:n så att
båda kan läsa och skriva mot samma rad.

`company_id` är scope-DB-id:t på Company-raden — vi lagrar inte FK
eftersom master-DB inte kan referera till scope-tabeller. Istället
har vi `owner_student_id` som låter oss slå upp rätt scope för
ad-hoc lookup. För display lagrar vi `company_name` direkt så vi
slipper cross-scope-query för att rendera lärar-vy.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date, DateTime, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .models import MasterBase


class ClassmateEmployment(MasterBase):
    """En klasskompis-anställning (lager mellan företag i scope-DB
    och anställd i annan scope-DB).

    status:
      'pending_offer' · erbjudande skickat, väntar på accept/decline
      'active'        · klasskompis tackat ja, lönespecar kan börja
      'declined'      · klasskompis tackat nej (terminal)
      'terminated'    · uppsagd, last_day passerat eller satt
    """

    __tablename__ = "classmate_employments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Företagets ägare (för att slå upp rätt scope-DB)
    owner_student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Scope-DB:s Company.id · refereras INTE som FK eftersom master
    # inte kan se scope-tabeller. För uppslag: scope_for_student(
    # owner_student_id) → öppna scope → SELECT Company WHERE id = X.
    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Cache · undviker cross-scope-query för rendering. Uppdateras
    # vid hire och om Company.name ändras.
    company_name: Mapped[str] = mapped_column(String(160), nullable=False)

    # Den anställde klasskompisen
    employee_student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Anställningsvillkor
    role: Mapped[str] = mapped_column(String(80), nullable=False)
    monthly_gross: Mapped[int] = mapped_column(Integer, nullable=False)

    # Status-livscykel
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending_offer",
        server_default="pending_offer", index=True,
    )

    # Tidsstämplar
    offer_sent_on: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    accepted_on: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
    )
    # Sista anställningsdag enligt LAS-uppsägning · NULL = ingen
    # uppsägning ännu. salary_phase stoppar lön från detta datum.
    last_day: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
    )
    termination_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    # Bevarat efter uppsägning · employer-namnet vid uppsägningen så
    # vi kan visa 'Uppsagd från X' även om Company senare bytt namn.
    terminated_company_name: Mapped[Optional[str]] = mapped_column(
        String(160), nullable=True,
    )
