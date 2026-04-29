"""Master-DB-modeller för bank-flödet (idé 3 i dev_v1.md).

`BankSession` är vår BankID-simulering. När eleven trycker 'Logga
in' på desktop genereras en token + (på mobilen) PIN-konfirmation,
desktop pollar tills sessionen blir confirmed=True.

`ScheduledPayment` och `PaymentReminder` ligger i scope-DB
(db/models.py) eftersom de hör till elevens egen ekonomi och måste
isoleras per elev — de modellerna byggs i PR 6.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .models import MasterBase


class CreditScoreSnapshot(MasterBase):
    """Per-elev kreditbetyg ('EkonomiSkalan'). 300–850-skala likt UC.

    Beräknas vid:
    - Varje PaymentReminder.issued (negativt på score)
    - Varje CreditApplication.submitted (cache vid handläggning)
    - Lazy från frontend när /bank/credit-score öppnas

    `factors` är en JSON med faktor → värde + delta, så eleven kan
    se exakt vad som drev scoren upp/ner. Pedagogisk transparens.
    """
    __tablename__ = "credit_score_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    grade: Mapped[str] = mapped_column(String(2), nullable=False)
    # JSON: {"late_payments": 3, "reschedules": 1, "debt_ratio": 0.4,
    #        "savings_buffer_months": 1.5, "satisfaction": 72,
    #        "_score_components": {factor: delta_pts}, ...}
    factors: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Pedagogisk text: 3-5 punkter om vad som drev scoren just nu
    reasons_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class BankSession(MasterBase):
    """En BankID-session — token-baserad inlogg/signering.

    Workflow:
    1. Eleven trycker 'Logga in i banken' på desktop → vi skapar
       BankSession med token (UUID) och visar QR-kod
    2. Eleven öppnar mobil-flödet, läser QR och anger PIN. Backend
       hashar PIN, jämför mot Student.bank_pin_hash. Om OK →
       confirmed_at sätts.
    3. Desktop pollar GET /bank/session/{token} var 2:a sek tills
       confirmed_at är satt.
    4. När confirmed → desktop får 'bank-token' med bredare scope
       (15 min timeout) och kan göra bank-actions.

    Purpose styr vad sessionen får göra:
    - 'login' → öppnar /bank/dashboard
    - 'sign_payment_batch:<n>' → signera N kommande betalningar
    - 'loan_application' → låneansökan med BankID
    """
    __tablename__ = "bank_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # UUID-token; refrenseras i URL:er (QR-kod, polling)
    token: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True,
    )
    # Vad sessionen ska användas till. login är default,
    # sign_payment_batch:<id> låser sessionen till en specifik batch.
    purpose: Mapped[str] = mapped_column(
        String(80), default="login", nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    # IP där sessionen startade (audit för misstänkta inloggningar)
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True,
    )
