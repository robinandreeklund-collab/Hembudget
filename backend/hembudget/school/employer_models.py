"""Master-DB-modeller för arbetsgivar-dynamik (idé 1 i dev_v1.md).

Globalt delade tabeller (kollektivavtal, frågor) + per-elev-tabeller
(satisfaction-score, eventlogg). Master-DB eftersom eleven har samma
arbetsgivare oavsett vilken klassrums-DB hen ligger i, och läraren
behöver tvärsnitt över hela klassen utan att öppna varje scope.

Importeras från school/models.py så att MasterBase.metadata.create_all()
hittar tabellerna vid uppstart.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column

from .models import MasterBase


class CollectiveAgreement(MasterBase):
    """Ett kollektivavtal — globalt delat över alla lärare/elever.

    Seedat ur faktagranskade källor (förbundens egna sammanfattningar
    + officiella avtals-PDF:er). En `valid_from`/`valid_to` så vi kan
    versionera när avtal uppdateras.

    `meta` håller strukturerade fält som UI:n och AI-promptar läser:
    revisionsökning per år, semesterdagar, övertidsersättning,
    sjuklön-trappa, tjänstepension-system + procentsats. Schemat är
    JSON för att tillåta avtalsspecifika fält utan att blåsa upp
    tabellen.
    """
    __tablename__ = "collective_agreements"
    __table_args__ = (
        UniqueConstraint("code", name="uq_agreement_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stabil nyckel som koden refererar till (t.ex. "if_metall_2026")
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Förbund + arbetsgivarpart för pedagogisk transparens
    union: Mapped[str] = mapped_column(String(80), nullable=False)
    employer_org: Mapped[str] = mapped_column(String(80), nullable=False)
    # Giltighetsperiod (NULL = pågående / okänt slutdatum)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Länk till officiella PDF:n så eleven kan dyka djupare
    source_url: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    # Pedagogisk lättläst sammanfattning (~300–400 ord, markdown)
    summary_md: Mapped[str] = mapped_column(Text, nullable=False)
    # Strukturerade nyckeltal — UI och AI-prompt läser från detta:
    # {
    #   "revision_pct_year": {"2026": 2.5, "2025": 2.4},
    #   "vacation_days": 25,
    #   "overtime_pct": 50,
    #   "sick_pay_steps": [{"days": "1-14", "pct": 80}, ...],
    #   "pension_system": "ITP1",
    #   "pension_pct": 4.5,
    #   ...
    # }
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # När summaryn senast faktagranskades (visa i UI som disclaimer)
    verified_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class ProfessionAgreement(MasterBase):
    """Mappar yrke (sträng-nyckel mot profile_fixtures.PROFESSIONS)
    till ett kollektivavtal. NULL = "småföretag utan avtal", där
    arbetstidslagen + semesterlagen utgör golv.

    Vissa employers inom ett yrke kan vara småföretag medan andra har
    avtal — `employer_pattern` används för att precisera. Tom = matchar
    alla employers för yrket.
    """
    __tablename__ = "profession_agreements"
    __table_args__ = (
        UniqueConstraint(
            "profession", "employer_pattern",
            name="uq_profession_agreement",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Måste matcha Profession.title i profile_fixtures.py exakt
    profession: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # Substring-matcha mot StudentProfile.employer för att skilja
    # avtalsbundna employers från småföretag (t.ex. "Egen verksamhet"
    # för Frisör → ingen agreement, "Cutters" → agreement). Tom =
    # default för yrket.
    employer_pattern: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    agreement_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("collective_agreements.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Tjänstepension i % — defaultas från avtalets meta men kan
    # overridea per employer. NULL → ingen tjänstepension.
    pension_rate_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True,
    )
    # Pedagogisk anteckning ("Bilia AB tillhör Motorbranschens avtal")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class EmployerSatisfaction(MasterBase):
    """Levande satisfaction-score per elev. En rad per elev.

    Score 0–100, default 70 (neutralt utgångsläge — eleven börjar inte
    perfekt och inte dåligt). Trend-fältet beräknas från senaste 5
    events och cachas här så UI:t inte måste räkna om varje pageload.
    """
    __tablename__ = "employer_satisfaction"
    __table_args__ = (
        UniqueConstraint("student_id", name="uq_employer_satisfaction_student"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    # "rising" | "falling" | "stable" — beräknas från sum av senaste 5
    # events delta. UI visar pil/färg.
    trend: Mapped[str] = mapped_column(String(10), nullable=False, default="stable")
    last_event_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class EmployerSatisfactionEvent(MasterBase):
    """Append-only logg över deltas till satisfaction-score.

    Pedagogiskt centrum: varje delta har en `reason_md` som förklarar
    VARFÖR scoren rörde sig. Eleven (och läraren) ska kunna räkna
    efter genom att läsa kedjan av events. Score är trubbigt; texten
    är lärandet.
    """
    __tablename__ = "employer_satisfaction_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True,
    )
    # "vab" | "sick" | "question_answered" | "late" | "manual_teacher"
    # | "salary_negotiation_completed"
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    delta_score: Mapped[int] = mapped_column(Integer, nullable=False)
    # Pedagogisk förklaring — visas direkt i eventlogg-UI:n
    reason_md: Mapped[str] = mapped_column(Text, nullable=False)
    # Strukturerad metadata (vilken fråga, vilket svar, antal sjuk-dagar
    # etc.). UI:n behöver inte parsa det, men lärar-vyn kan visa rådata
    # vid utredning.
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class WorkplaceQuestion(MasterBase):
    """Slumpade scenario-frågor som skickas till eleven från
    arbetsgivaren. Pedagogiskt syfte: eleven ställs inför en konkret
    arbetsplats-situation och får välja hur hen agerar — varje val
    ger ett delta på satisfaction.

    Globalt delade (samma frågor för alla elever); slumpning gör att
    olika elever får olika frågor i olika ordning. ~30–50 frågor i
    seedet. Alla åldersanpassade, inga politiska eller känsliga
    ämnen.
    """
    __tablename__ = "workplace_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stabil nyckel ("late_for_meeting_001") så seedet kan
    # uppdatera utan att skapa dubletter
    code: Mapped[str] = mapped_column(
        String(60), nullable=False, unique=True,
    )
    # Situations-text i markdown ("Du har glömt att svara på en
    # viktig kollegas mejl i 3 dagar...")
    scenario_md: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON-lista: [{"text": "Be om ursäkt direkt", "delta": +3,
    #              "explanation": "..."}, ...]
    options: Mapped[list] = mapped_column(JSON, nullable=False)
    # Pedagogisk reflektion efter att eleven svarat — visar VARFÖR
    # det "bra" svaret var bättre (men utan att skämma ut eleven).
    correct_path_md: Mapped[str] = mapped_column(Text, nullable=False)
    # Tags för filtrering ("lojalitet", "konflikt", "tidshantering")
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Difficulty 1-5 — påverkar hur tidigt frågan dyker upp i flödet
    difficulty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class WorkplaceQuestionAnswer(MasterBase):
    """Per-elev-rad när hen svarat på en fråga. En rad per (student,
    question) — eleven kan svara på samma fråga max 1 gång (frågan
    rotas bort ur slumpningen efter besvarad).
    """
    __tablename__ = "workplace_question_answers"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "question_id",
            name="uq_workplace_answer_student_q",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("workplace_questions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Vilket alternativ eleven valde (0-baserat index i question.options)
    chosen_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Delta som applicerades — kopia för spårbarhet om frågan ändras
    delta_applied: Mapped[int] = mapped_column(Integer, nullable=False)
    # Länk till motsvarande EmployerSatisfactionEvent för revisionsspår
    event_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employer_satisfaction_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    answered_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
