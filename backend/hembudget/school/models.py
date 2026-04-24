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
    # Markerar en "demo"-lärare + alla dennes elever/familjer/batcher.
    # Demo-data rensas automatiskt var 10 min och återskapas från kod.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Super-admin kan toggla AI-funktioner på/av för andra lärare.
    # Första läraren (bootstrap) blir auto super-admin.
    is_super_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    # AI-funktioner (Claude-anrop) aktiveras per-lärare av super-admin.
    # Som default = False; inga AI-anrop görs för läraren/elever.
    ai_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    # Räkne-siffror för AI-användning (enkel kostnadskontroll)
    ai_requests_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # NULL = ej verifierad (open-signup-lärare som inte klickat länk än).
    # Bootstrap-läraren + demo-läraren sätts verifierade direkt vid skapelse.
    # Login blockeras för lärare med NULL (förutom super-admin).
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    students: Mapped[list["Student"]] = relationship(back_populates="teacher")
    families: Mapped[list["Family"]] = relationship(back_populates="teacher")


class EmailToken(MasterBase):
    """Engångs-token för e-post-verifiering och lösenords-återställning.

    Vi lagrar endast SHA-256-hash av tokenvärdet — själva strängen syns
    bara i mailet. Om DB:n läcker kan angriparen inte använda dem.

    kind:
      "verify" — klick i mailet sätter Teacher.email_verified_at
      "reset"  — klick i mailet leder till ny-lösenord-form
    """
    __tablename__ = "email_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_email_token_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True,
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


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

    # Barnens åldrar (lista av ints) — endast meningsfullt om
    # family_status == "familj_med_barn", annars tom lista.
    # Används för att räkna ut Konsumentverkets matkostnad per barn.
    children_ages: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Partnerns ålder (för 2-vuxen-hushåll). None om family_status == "ensam".
    partner_age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

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

    meta kan bl.a. innehålla "category_hints": [{description, date,
    amount, hint}] som används av facit-kontrollen när läraren ska
    utvärdera elevens kategoriseringar.
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
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
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
    # Manuell "klar"-markering — används främst för kind="free_text"
    # där servern inte kan avgöra status automatiskt. När satt
    # returneras status="completed" oavsett vad checkern säger.
    manually_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    # Lärarens kommentar på elevens inlämning. När satt ber läraren
    # eleven försöka igen; frontend visar texten som "rätta mig"-
    # banner och tillåter ny markering-som-klar.
    teacher_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    teacher_feedback_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class InterestRateSeries(MasterBase):
    """Historiska + aktuella räntor för bolåne-scenariot.

    rate_type: "policy" (Riksbankens styrränta), "stibor3m",
               "bolan_rorlig", "bolan_3ar", "bolan_5ar"
    year_month: "YYYY-MM" (månadsslut-värde)
    rate: decimalränta, t.ex. 0.0325 för 3,25%
    """
    __tablename__ = "interest_rate_series"
    __table_args__ = (
        UniqueConstraint(
            "rate_type", "year_month",
            name="uq_rate_series",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rate_type: Mapped[str] = mapped_column(String(40), nullable=False)
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    rate: Mapped[float] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="static")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class MortgageDecision(MasterBase):
    """Elevens bolåne-val i samband med ett mortgage_decision-uppdrag.

    När uppdraget skapas fryses räntan som var aktuell vid beslutsmånaden.
    När horisonten passerat räknar vi kostnad rörlig vs bunden via
    InterestRateSeries och rapporterar vilket val som blev billigast.
    """
    __tablename__ = "mortgage_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # "rorlig" | "3ar" | "5ar"
    chosen: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_month: Mapped[str] = mapped_column(String(7), nullable=False)
    horizon_months: Mapped[int] = mapped_column(Integer, nullable=False)
    principal: Mapped[float] = mapped_column(nullable=False)  # kvarvarande lån vid beslutet
    # Räntan som fryses om eleven väljer bunden
    locked_rate: Mapped[Optional[float]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class Message(MasterBase):
    """Meddelande mellan elev och deras lärare.

    Konversationen är 1-till-1 (elev↔lärare), ingen broadcast. Varje
    meddelande har en sender_role som avgör om det kom från elev
    eller lärare. Olästa räknas per mottagare.
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id"), nullable=False, index=True,
    )
    # "student" | "teacher"
    sender_role: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Valfri referens till en transaktion eller uppdrag för tråd-koppling
    # (vi använder bara som kontext/etikett — ingen FK cross-DB)
    context_type: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True,
    )
    context_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True,
    )


class Module(MasterBase):
    """En lärmodul — en ordnad sekvens av steg (read/watch/reflect/task/quiz).
    Tillhör en lärare. Kan markeras som mall så andra lärare kan kopiera.
    """
    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    # NULL teacher_id = system-mall (tillgänglig för alla)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Rekommenderad ordning i lärarens kursplan — högre = senare
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    steps: Mapped[list["ModuleStep"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="ModuleStep.sort_order",
    )


class ModuleStep(MasterBase):
    """Ett enskilt steg i en modul.
    kind:
      "read"    — markdown-text eleven läser
      "watch"   — embed-URL (YouTube/Vimeo) + ev. frågor
      "reflect" — öppen fråga, eleven skriver svar
      "task"    — kopplar till ett Assignment (via assignment_id i params)
      "quiz"    — flervalsfråga (params = {question, options, correct_index, explanation})
    """
    __tablename__ = "module_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_id: Mapped[int] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Typ-specifik data (video-url, quiz-alternativ, assignment-ref osv)
    params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    module: Mapped[Module] = relationship(back_populates="steps")


class StudentModule(MasterBase):
    """Eleven har tilldelats en modul. Håll ihop enrollment-metadata."""
    __tablename__ = "student_modules"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "module_id",
            name="uq_student_module",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    module_id: Mapped[int] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class StudentStepHeartbeat(MasterBase):
    """Spårar när eleven är aktiv på ett steg. opened_at = första heartbeaten,
    last_heartbeat_at = senaste. Duration (last - opened) används av lärar-UI
    för att se vilka steg som fastnar.

    Separat tabell från StudentStepProgress för att kunna logga även steg
    där eleven aldrig klickade "klar" (fastnade/gav upp).
    """
    __tablename__ = "student_step_heartbeats"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "step_id",
            name="uq_student_step_heartbeat",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    step_id: Mapped[int] = mapped_column(
        ForeignKey("module_steps.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )


class StudentStepProgress(MasterBase):
    """Elevens framsteg på ett enskilt steg. data lagrar svar/reflektion."""
    __tablename__ = "student_step_progress"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "step_id",
            name="uq_student_step",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    step_id: Mapped[int] = mapped_column(
        ForeignKey("module_steps.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Lagrar svar: {"reflection": "..."} eller {"quiz_answer": 2, "correct": True}
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Lärarens feedback-text (för reflect-steg)
    teacher_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Rubric-bedömning: {criterion_key: level_index (0..N-1)}.
    # Criterion-definition ligger i ModuleStep.params.rubric.
    rubric_scores: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class StudentAchievement(MasterBase):
    """Badge/prestation som en elev har tjänat. Unik per (student, key);
    samma prestation kan inte delas ut två gånger.

    key = kort stabil identifierare som mappas till metadata i
    `school/achievements.py::ACHIEVEMENTS` (titel, emoji, beskrivning).
    """
    __tablename__ = "student_achievements"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "key", name="uq_student_achievement",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    earned_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class PeerFeedback(MasterBase):
    """Anonym feedback från en elev till en annan på en reflektion.

    reviewer och target är båda Student-id inom samma lärare. Visas
    anonymt för target-eleven; läraren ser båda i moderations-vyn.
    """
    __tablename__ = "peer_feedback"
    __table_args__ = (
        UniqueConstraint(
            "reviewer_student_id", "target_progress_id",
            name="uq_peer_feedback_pair",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reviewer_student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    target_progress_id: Mapped[int] = mapped_column(
        ForeignKey("student_step_progress.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class Competency(MasterBase):
    """En inlärningsfärdighet, t.ex. 'läsa lönespec', 'förstå skatteavdrag'.

    Systemkompetenser (teacher_id=NULL, is_system=True) finns för alla;
    lärare kan skapa egna kompetenser för specifika klasser/ämnesområden.
    """
    __tablename__ = "competencies"
    __table_args__ = (
        UniqueConstraint("key", name="uq_competency_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(60), nullable=False)  # ex 'salary_slip'
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # "grund" | "fordjup" | "expert"
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="grund")
    teacher_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class ModuleStepCompetency(MasterBase):
    """Koppling: detta steg tränar dessa färdigheter med viss vikt."""
    __tablename__ = "module_step_competencies"
    __table_args__ = (
        UniqueConstraint("step_id", "competency_id", name="uq_step_competency"),
    )

    step_id: Mapped[int] = mapped_column(
        ForeignKey("module_steps.id", ondelete="CASCADE"),
        primary_key=True,
    )
    competency_id: Mapped[int] = mapped_column(
        ForeignKey("competencies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # 0.0-1.0 — hur mycket detta steg räknar mot kompetensen
    weight: Mapped[float] = mapped_column(nullable=False, default=1.0)


class AskAiThread(MasterBase):
    """En AskAI-chattråd mellan en elev/lärare och Claude. Varje tråd
    har flera meddelanden — möjliggör multi-turn där modellen "minns"
    tidigare frågor i samma session."""
    __tablename__ = "ask_ai_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # student_id är primärt ägare-fält; lärare kan ha egna trådar med
    # teacher_id istället.
    student_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    teacher_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    title: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    module_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("modules.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class AskAiMessage(MasterBase):
    """Ett meddelande i en AskAI-tråd. role = "user" eller "assistant"."""
    __tablename__ = "ask_ai_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("ask_ai_threads.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class RubricTemplate(MasterBase):
    """Återanvändbar rubric-mall som en lärare kan koppla på valfritt
    reflect-steg istället för att sätta om kriterier manuellt.

    criteria lagras som lista av {key, name, levels:[...]} — samma format
    som ModuleStep.params.rubric.

    teacher_id=NULL + is_shared=True = systemmall, visas för alla lärare.
    """
    __tablename__ = "rubric_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Lista av {"key": "...", "name": "...", "levels": ["...", ...]}
    criteria: Mapped[list] = mapped_column(JSON, nullable=False)
    # Om True syns mallen för andra lärare (via /teacher/rubric-templates)
    is_shared: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class AppConfig(MasterBase):
    """Lärarens globala inställningar — skattesatser, budgetstartmånad etc.
    Key-value-form så vi slipper migrera schemat vid varje nytt fält.
    """
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )
