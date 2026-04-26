"""Master-DB-modell för EventTemplate (delad över alla elever).

Ett event är ett *förslag* eleven får på dashboard ("middag med
familjen — 350 kr, accepterar du?"). Mallen säger vad eventet
heter, hur det kostar, hur det påverkar Wellbeing per dimension,
och vilka triggers som kan låta det dyka upp.

StudentEvent-tabellen (per scope) hanterar elevens individuella
beslut — den ligger i db/models.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .models import MasterBase


class EventTemplate(MasterBase):
    """Delade event-mallar — ~80 stycken seedade vid uppstart.

    Alla elever ser samma mallar; deras individuella StudentEvent-
    instans (per scope) refererar tillbaka via code.

    Kategorier:
      social     — utebjudningar (bio, restaurang, fest)
      family     — familjehändelser (kalas, present, semester)
      culture    — musik/teater/museum
      sport      — match, träningsanmälan, race
      opportunity — chans-baserade ('rea på cykeln', 'jobb-erbjudande')
      unexpected — oförutsedda kostnader (tandläkare, diskmaskin)
      mat        — restaurangmiddag, leverans, food court
      lifestyle  — kläder, frisör, prenumerationer
    """
    __tablename__ = "event_templates"
    __table_args__ = (
        UniqueConstraint("code", name="uq_event_template_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    brand: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    # Kostnadsintervall — exakt belopp slumpas mellan min och max
    cost_min: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_max: Mapped[int] = mapped_column(Integer, nullable=False)
    # Wellbeing-impact när eleven ACCEPTERAR (i poäng per dimension)
    impact_economy: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact_health: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact_social: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact_leisure: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impact_safety: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Hur lång tid eleven har på sig att svara (default 5 dagar)
    duration_days: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # Triggers — JSON med när-villkor:
    #   {"weekday": [4,5], "month_day_min": 25}
    #   {"reactive": "low_savings_buffer"}
    #   {"random_weight": 1.0}
    triggers: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Får eleven bjuda klasskompisar?
    social_invite_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    # Vissa events går inte att neka (oförutsedda kostnader). Då
    # appliceras impact direkt utan att eleven får välja.
    declinable: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    # AI-prompt-mall för personlig version (V2). Om null används description
    # rakt av.
    ai_text_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
