"""SQLAlchemy-modeller för master-DB (lärare, elever, generering-runs).

Separat Declarative Base från student-DB:ns modeller — master innehåller
inte elev-data och student-DB:ar innehåller inte lärare/elever.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, deferred, relationship,
)


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
    # Dagsgräns för AI-chatt-meddelanden per elev. Super-admin kan höja.
    # 0 = AI-chatt avstängd även om ai_enabled=True. Default 10 = lagom
    # för en lektion utan att eleven kan "kosta ihjäl" Anthropic-kontot.
    ai_chat_daily_quota: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False,
    )
    # NULL = ej verifierad (open-signup-lärare som inte klickat länk än).
    # Bootstrap-läraren + demo-läraren sätts verifierade direkt vid skapelse.
    # Login blockeras för lärare med NULL (förutom super-admin).
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    # Familjekonto: tekniskt samma som ett vanligt lärarkonto, men signupen
    # gick via /signup/parent. Påverkar copy + default-moduler i UI:n
    # (Sidebar visar "Familjepanel", elever kallas "barn", osv). Samma
    # databas-modell, ingen extra tabell — bara en pedagogisk flagga.
    is_family_account: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
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


class AuthToken(MasterBase):
    """Persistent session-token (lärare/elev) — DB-backat så det
    funkar över flera Cloud Run-instanser.

    Tidigare lagrat i process-lokal `_ACTIVE_TOKENS`-dict. Det fungerade
    bara med max-instances=1 — när vi skalar horisontellt måste tokens
    delas mellan instanser så att login på instans A funkar på instans B.

    Kolumnerna speglar TokenInfo-dataclass i api/deps.py:
      role: 'teacher' | 'student' | 'demo'
      teacher_id / student_id: en av dem populerad beroende på role
      last_seen_at: uppdateras vid varje request → används för
        sliding-window expiration (settings.session_timeout_minutes)
    """
    __tablename__ = "auth_tokens"
    __table_args__ = (
        UniqueConstraint("token", name="uq_auth_token"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(
        String(80), nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
    )
    teacher_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True,
    )
    student_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
        nullable=False, index=True,
    )


class BetaCode(MasterBase):
    """Beta-tillgångskod för stängd registrering.

    Plattformen är i beta — vi vill inte öppna /signup/teacher och
    /signup/parent helt fritt än. Användare måste maila
    info@ekonomilabbet.org för att få en kod.

    Lifecycle:
      - Admin lägger till nya koder via INSERT (eller framtida UI).
      - Vid signup matchas inputed code (case-insensitive) mot DB.
      - Vid lyckad signup ökas `uses_count`. När `uses_count >= max_uses`
        stängs koden (active=False).
      - `expires_at` (optional) hård gräns även om uses_count < max.

    Designval:
      - Lagras i klartext (inte hashad) eftersom koderna delas via
        e-post och lärare/föräldrar ska kunna jämföra ord-för-ord.
      - `notes` är fri admin-text (vem fick koden, sammanhang etc.).
    """
    __tablename__ = "beta_codes"
    __table_args__ = (
        UniqueConstraint("code_norm", name="uq_beta_code_norm"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Original-kod (visas i admin-UI med rätt case)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    # Normaliserad kod för uniqueness + lookup (UPPER + strip)
    code_norm: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True,
    )
    max_uses: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False,
    )
    uses_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )


class WaitlistEntry(MasterBase):
    """Intresseanmälan till beta-väntelistan.

    Lagrar e-post + roll (teacher/parent) + tidpunkt så vi kan kontakta
    dem när vi öppnar upp fler beta-platser. Idempotent på e-posten —
    om någon registrerar sig flera gånger uppdateras `last_signup_at`
    istället för att skapa duplicat.
    """
    __tablename__ = "waitlist_entries"
    __table_args__ = (
        UniqueConstraint("email_norm", name="uq_waitlist_email_norm"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(160), nullable=False)
    # Lower-cased för uniqueness + lookup
    email_norm: Mapped[str] = mapped_column(
        String(160), nullable=False, index=True,
    )
    # "teacher" | "parent" | "other" — vilken roll de signade upp för
    role: Mapped[str] = mapped_column(
        String(20), default="other", nullable=False,
    )
    # Anti-spam: spara IP som hashad värde + user-agent (truncerad).
    ip_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
    )
    # När admin kontaktade dem (för att invitera in)
    contacted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    # Anti-doublesignup: när hen senast hörde av sig
    last_signup_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    signup_count: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    # Bank-PIN för BankID-simulering på /bank (idé 3 i dev_v1.md).
    # 4-siffrig PIN som eleven sätter vid första bank-inlogg, hashad
    # med bcrypt. Lärare kan resetta via /teacher/students/:id/reset-pin.
    bank_pin_hash: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True,
    )
    # === V2-fält (parallell migration · ny dashboard) ===
    # Per-elev-toggle: läraren bestämmer vilka elever som ska se v2.
    # Default False — eleven får v1 tills läraren aktiverar v2.
    # Super-admin är alltid v2-eligible oavsett denna flagga.
    v2_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    # Sätts under v2-onboardingen och styr nya UI:t. Saknas värde →
    # eleven har inte gått v2-onboardingen och hänvisas till v1.
    v2_onboarding_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    # Spelets svårighetsgrad. 1 = Sparsam (start), 2 = Balanserad
    # (lärare aktiverar), 3 = Slösa (fortsättning). Ändras enbart av
    # läraren via /v2/teacher/students/:id/level.
    v2_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Spenderprofil: "sparsam" / "balanserad" / "slosa". Styr hur
    # förra-månadens-data genereras (kreditkortsfakturor, postlådan).
    # Default "sparsam" eftersom alla börjar på Nivå 1.
    v2_spend_profile: Mapped[str] = mapped_column(
        String(20), default="sparsam", nullable=False,
    )
    # Värderingsval om sambo-ekonomi (50/50, proportionellt, pool).
    # Sparas innan AI-partnern avslöjas så svaret inte rationaliseras.
    # NULL om inte besvarat eller om karaktären är solo.
    v2_fairness_choice: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
    )
    # Partner-modell: "solo" / "ai" / "klasskompis". Sätts vid karaktärs-
    # generering. "klasskompis" kräver att läraren aktiverar paret.
    v2_partner_model: Mapped[str] = mapped_column(
        String(20), default="solo", nullable=False,
    )
    # Bug #7-utbyggnad · läraren aktiverar företagsläget per elev.
    # När True kan eleven flippa dashboarden till business-mode och
    # driva enskild firma eller AB. Eget företag blir då huvudsakligt
    # 'jobb' — Maria-lönesamtal pausas, intäkter genereras via fakturor.
    business_mode_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    # Seed-livscykel · sätts vid student-skapande till "pending" och
    # markeras "complete" av background-tasken när initial seed (lön,
    # postlådan, försäkringar, pension, rental, events) är klar. Frontend
    # läser detta för att visa "Bygger upp ditt liv..."-overlay tills
    # statusen är complete — annars ser eleven tomma vyer i 3-5 s medan
    # background-tasken jobbar (race condition mot v2_create_student som
    # returnerar direkt och schemalägger seed:en async). "failed" sätts
    # om seed:en kastat exception så lärar-detaljvyn kan trigga
    # auto-recovery via _ensure_student_has_initial_data.
    seed_status: Mapped[str] = mapped_column(
        String(20), default="complete", nullable=False,
        server_default="complete",
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

    # Karaktärsnamn — den persona eleven får. Skiljer sig från
    # student.display_name som är inloggningsnamnet/elevkontot.
    # Används i v2-vyer ("Sara", "Hennes vardag", etc.). deferred()
    # så lazy-load inte kraschar innan migrationen hunnit lägga till
    # kolumnerna i prod-Postgres.
    character_first_name: Mapped[Optional[str]] = deferred(mapped_column(
        String(60), nullable=True,
    ))
    character_last_name: Mapped[Optional[str]] = deferred(mapped_column(
        String(60), nullable=True,
    ))

    # Karriär
    profession: Mapped[str] = mapped_column(String(80), nullable=False)
    employer: Mapped[str] = mapped_column(String(120), nullable=False)
    gross_salary_monthly: Mapped[int] = mapped_column(Integer, nullable=False)
    # Beräknat på server enl. _compute_net_salary i tax.py — cachas här
    # så onboardingen inte behöver räkna om varje gång
    net_salary_monthly: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_rate_effective: Mapped[float] = mapped_column(nullable=False)

    # Anställningsstatus · styr om eleven får lön via salary_phase och
    # hur HubV2/Arbetsgivaren-vyn renderas.
    #   'employed'      · default · har anställning hos `employer`
    #   'self_employed' · har sagt upp privat-jobbet, driver eget AB
    #   'unemployed'    · har inget jobb (uppsagd, konkurs, eller mellan jobb)
    #
    # Sätts från startup (employed), uppdateras vid:
    #   resign-flöde (→ self_employed om eget AB, annars unemployed)
    #   bankruptcy (→ unemployed)
    #   hire-classmate-accept (→ employed)
    #   terminate-classmate (→ unemployed efter last_day)
    employment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="employed",
        server_default="employed",
    )
    # När eleven sagt upp sig · sätter sista-dag för LAS-period.
    # Lön genereras fortfarande fram till detta datum, sedan stoppas
    # salary_phase. NULL = ingen pågående uppsägning.
    employment_end_on: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True,
    )

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
    # Partnerns yrke och bruttolön — krävs för att hushållsekonomin ska gå
    # ihop. Sätts vid profilgenerering om family_status != "ensam".
    # deferred() = exkludera från default-SELECT så att lazy-load av
    # student.profile inte kraschar när migration ännu inte hunnit lägga
    # till kolumnen i prod-Postgres. Värdet hämtas först vid explicit
    # access (cost-split-endpoint, generator).
    partner_profession: Mapped[Optional[str]] = deferred(mapped_column(
        String(80), nullable=True,
    ))
    partner_gross_salary: Mapped[Optional[int]] = deferred(mapped_column(
        Integer, nullable=True,
    ))
    # Hushållets fördelningsmodell — eleven väljer vid onboarding INNAN
    # hen ser sin egen profil ('veil of ignorance' — pedagogiskt ärligt
    # val). Påverkar generatorn: vilken andel av gemensamma kostnader
    # eleven får på sitt konto.
    # "even_50_50" | "pro_rata" | "all_shared" | None (ej onboardad/ensam)
    cost_split_preference: Mapped[Optional[str]] = deferred(mapped_column(
        String(20), nullable=True,
    ))
    cost_split_decided_at: Mapped[Optional[datetime]] = deferred(mapped_column(
        DateTime, nullable=True,
    ))

    # Backstory som visas i onboardingen
    backstory: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # === Bil + pendling (Feature SKV-3 · realistisk vardag) ===
    # Sätts av car_picker.pick_car() vid profilgenerering. Driver
    # bilförsäkring + drivmedelskostnader + bil-events + Skatteverket-
    # reseavdrag. Alla fält deferred() så lazy-load inte kraschar
    # innan migrationen kört på prod-Postgres.
    has_car: Mapped[bool] = deferred(mapped_column(
        Boolean, nullable=False, default=False,
    ))
    # "car" | "public" | "bike" | "remote"
    commute_transport: Mapped[Optional[str]] = deferred(mapped_column(
        String(20), nullable=True,
    ))
    commute_km: Mapped[int] = deferred(mapped_column(
        Integer, nullable=False, default=0,
    ))
    car_brand: Mapped[Optional[str]] = deferred(mapped_column(
        String(40), nullable=True,
    ))
    car_model: Mapped[Optional[str]] = deferred(mapped_column(
        String(60), nullable=True,
    ))
    car_year: Mapped[Optional[int]] = deferred(mapped_column(
        Integer, nullable=True,
    ))
    car_fuel_type: Mapped[Optional[str]] = deferred(mapped_column(
        String(20), nullable=True,
    ))
    car_market_value_sek: Mapped[Optional[int]] = deferred(mapped_column(
        Integer, nullable=True,
    ))
    car_license_plate: Mapped[Optional[str]] = deferred(mapped_column(
        String(10), nullable=True,
    ))
    car_insurance_provider: Mapped[Optional[str]] = deferred(mapped_column(
        String(40), nullable=True,
    ))
    car_insurance_premium_monthly: Mapped[Optional[int]] = deferred(
        mapped_column(Integer, nullable=True),
    )
    # "cash" | "loan" | "leasing"
    car_financing: Mapped[Optional[str]] = deferred(mapped_column(
        String(20), nullable=True,
    ))
    car_loan_principal: Mapped[Optional[int]] = deferred(mapped_column(
        Integer, nullable=True,
    ))
    car_loan_monthly_payment: Mapped[Optional[int]] = deferred(
        mapped_column(Integer, nullable=True),
    )
    car_leasing_monthly: Mapped[Optional[int]] = deferred(mapped_column(
        Integer, nullable=True,
    ))
    car_monthly_fuel_cost: Mapped[int] = deferred(mapped_column(
        Integer, nullable=False, default=0,
    ))
    car_monthly_electric_extra: Mapped[int] = deferred(mapped_column(
        Integer, nullable=False, default=0,
    ))
    car_monthly_public_transport: Mapped[int] = deferred(mapped_column(
        Integer, nullable=False, default=0,
    ))

    # === Frisktandvård (SKV-4 · realistisk tandförsäkring) ===
    # ~40 % av karaktärerna har frisktandvårdsavtal. Tier 1-10 baseras
    # på tandhälsa · premie skalas med ålder (ATB 20-23/67+ vs normal
    # 24-66). När tandhälsa-event triggas (karieskontroll, lagning)
    # täcker frisktandvården 100 % om policy är aktiv.
    has_frisktandvard: Mapped[bool] = deferred(mapped_column(
        Boolean, nullable=False, default=False,
    ))
    frisktandvard_tier: Mapped[Optional[int]] = deferred(mapped_column(
        Integer, nullable=True,
    ))
    # "atb" (20-23 eller 67+) | "normal" (24-66)
    frisktandvard_age_category: Mapped[Optional[str]] = deferred(
        mapped_column(String(10), nullable=True),
    )
    frisktandvard_premium_monthly: Mapped[Optional[int]] = deferred(
        mapped_column(Integer, nullable=True),
    )

    # === Sprint 8 · företag-vs-jobb-balans ===
    # Veckotid på det vanliga jobbet · default 40h heltid. Eleven kan
    # gå ner till 50% (20h) eller säga upp helt (0h) som beslut när
    # företaget växer. Lön justeras proportionerligt nästa månadstick.
    weekly_hours_employed: Mapped[int] = deferred(mapped_column(
        Integer, nullable=False, default=40, server_default="40",
    ))
    # Anställnings-status: "employed" (heltid/deltid · lön kommer)
    # | "unemployed" (uppsagd) | "freelance_only" (egen företagare som
    # sagt upp jobbet helt). Driver lönespec-generation.
    employment_status: Mapped[str] = deferred(mapped_column(
        String(20), nullable=False, default="employed",
        server_default="employed",
    ))
    # Konsekutiva veckor över 50h totalt (anställd+biz). Spåras av
    # combined_weekly_tick · driver Maria-säg-upp-prompt vid 4+.
    consecutive_overload_weeks: Mapped[int] = deferred(mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    ))

    # Lönesamtals-resultat: ny lön committas inte direkt — den lagras
    # här tills lönespec-generatorn körs för en månad >= effective_from,
    # då skrivs gross_salary_monthly om och pending-fälten nollas. Det
    # speglar verkligheten där samtalet sker en månad och nya lönen syns
    # på nästa lönespec.
    pending_salary_monthly: Mapped[Optional[int]] = deferred(mapped_column(
        Integer, nullable=True,
    ))
    pending_effective_from: Mapped[Optional[date]] = deferred(mapped_column(
        Date, nullable=True,
    ))

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )

    student: Mapped[Student] = relationship(back_populates="profile")


class V2OnboardingEvent(MasterBase):
    """Per-stegs-loggning för v2-onboardingen.

    Läraren behöver komplett insyn i elevens onboarding-resa: vilka
    steg eleven sett, hur länge hen var på varje, eventuella backsteg
    och avhopp. Frontend loggar event vid varje stegväxling.

    Event-typer:
      "viewed"     — eleven visade ett steg (skickas vid mount/byte)
      "back"       — klickade ← Tillbaka
      "next"       — klickade Nästa →
      "completed"  — hela onboardingen klar (sista stegets next)
      "abandoned"  — eleven stängde fönstret (skickas via beacon vid unload)

    `payload` är frivillig JSON (t.ex. fairness-svar i steg 7).
    """

    __tablename__ = "v2_onboarding_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    payload: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
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
    # BigInteger eftersom seed:s är hela uint32-rangen (0..2**32-1)
    # och Postgres INTEGER bara går till 2**31-1 ≈ 2.1 mrd.
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
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
    # BigInteger eftersom seed:s är hela uint32-rangen (0..2**32-1)
    # och Postgres INTEGER bara går till 2**31-1 ≈ 2.1 mrd.
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
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
    # Bank-flödet (idé 3 i dev_v1.md): bank-relaterade artefakter
    # (kontoutdrag, kreditkort_faktura, lan_besked) syns FÖRST i banken.
    # Eleven måste exportera dem ur banken → då sätts denna flagga →
    # de blir synliga i /my-batches. Lönespec hör inte till bank-flödet
    # (synlig direkt på /arbetsgivare) — flaggan är NULL på dem.
    exported_to_my_batches: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    exported_at: Mapped[Optional[datetime]] = mapped_column(
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


class FeedbackRead(MasterBase):
    """Tracking av lästa lärar-feedback-items per elev.

    Aggregator-vyn /v2/feedback samlar feedback från flera källor
    (Message, StudentStepProgress.teacher_feedback, Assignment.
    teacher_feedback). För att markera enskilda items som lästa per
    elev har vi en separat tabell istället för att lägga read-fält
    på respektive källa.

    UNIQUE per (student, kind, source_id) — items markeras som lästa
    en gång och består.
    """
    __tablename__ = "feedback_reads"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "kind", "source_id",
            name="uq_feedback_read",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # "module_step" | "assignment" | "message" (även om message har
    # eget read_at — vi speglar för konsekvent UI)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    read_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
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


class StudentCompetencyOverride(MasterBase):
    """Lärarens manuella nivå-höjning/sänkning av en kompetens för en elev.

    När den finns vinner den över mastery-beräkning. Pedagogiskt vill
    läraren kunna säga "Sara har visat fördjupning genom klassrum-
    diskussion även om mastery-talet inte hunnit klättra dit än".
    """
    __tablename__ = "student_competency_overrides"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "competency_id",
            name="uq_student_competency_override",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    competency_id: Mapped[int] = mapped_column(
        ForeignKey("competencies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # "B" | "G" | "F"
    level: Mapped[str] = mapped_column(String(1), nullable=False)
    motivation: Mapped[str] = mapped_column(Text, nullable=False)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


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


class LandingAsset(MasterBase):
    """Skärmdumpar + texter för landningssidans Vyerna-galleri.

    Sex fasta slot:ar seedas vid uppstart (slot = "dashboard",
    "modules", "mastery", "portfolio", "ai", "time-on-task"). Super-
    admin kan ladda upp/byta bilden via /admin/landing/gallery och
    redigera title/body utan deploy. Image_blob lagras direkt i
    master-DB:n så det följer med backupen — ingen separat fil-store
    behövs.

    Bilder serveras via en publik /landing/gallery/{id}/image-endpoint
    så landningssidan kan visa dem utan auth.
    """
    __tablename__ = "landing_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stabil slot-nyckel ("dashboard", "modules", osv) — låter UI:n
    # placera specifika bilder i specifika kort. Unik så vi aldrig
    # dubblerar slots av misstag.
    slot: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    chip: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    chip_color: Mapped[str] = mapped_column(
        String(20), nullable=False, default="grund",
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Bild + mimetype. NULL betyder "ingen uppladdad bild — visa
    # placeholder-kortet på landningssidan".
    image_blob: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True,
    )
    image_mime: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class StudentActivity(MasterBase):
    """Audit-spår för meningsfulla handlingar eleven gör i scope-DB:n.

    Skapas av endpoints i transactions/budget/loans/imports osv via
    helper:n `school.activity::log_activity`. Lärare ser flödet under
    StudentDetail → "Senaste aktivitet" och kan på så sätt följa elevens
    arbete utan att behöva impersonera.

    Inga PII-värden lagras i payload — bara siffror och rubriker (ex.
    "kategoriserade 4 transaktioner i 2025-08"). Hela elevens scope-DB
    har redan persondata och raderas vid /reset.

    Vi sparar inte här någon koppling till en Assignment — använd
    matrix-endpointen för det. Aktivitetsflödet är en separat tidslinje.
    """
    __tablename__ = "student_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Stabil sträng-identifierare. Mappas till människo-läsbar text i
    # frontend (StudentDetail.tsx). Exempel:
    # "transaction.created", "budget.set", "loan.created",
    # "transaction.recategorized", "transfer.linked", "batch.imported"
    kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    # Sammanfattande rubrik som visas direkt i flödet utan klick.
    summary: Mapped[str] = mapped_column(String(240), nullable=False)
    # Frivilliga strukturerade detaljer (belopp, antal, månad osv).
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True,
    )


class ClassCompanyShare(MasterBase):
    """Klass-skopig spegling av en elev-ägd Company.

    Företaget bor i elevens scope-DB (per-tenant Postgres-rader eller
    per-fil SQLite). Den här raden är en cache i master-DB:n så att
    /v2/allabolag-aktören kan lista ALLA klassens företag i en query
    utan att fan-out:a läsningar över N elever.

    Cachen uppdateras av `sync_class_company_share` som anropas från
    auto_tick_if_due (varje gång företaget tickas) + från
    annual_report_submit-flow. Stale-tolerance ~1 timme — Allabolag
    är ingen realtidsvy.

    Privacy: bara aggregat (omsättning, vinst, antal anställda)
    speglas hit. Aldrig transaktionslistor eller kund-namn.
    """
    __tablename__ = "class_company_shares"
    __table_args__ = (
        UniqueConstraint(
            "owner_student_id", "company_id_in_scope",
            name="uq_class_company_share_owner_company",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    owner_student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Klass-filter (om läraren har flera klasser)
    class_label: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True, index=True,
    )
    # Lokal id i ägarens scope-DB · för djuplänk vid behov
    company_id_in_scope: Mapped[int] = mapped_column(Integer, nullable=False)

    # Speglade fält (läraren ser alltid namn/bransch oavsett publish-status)
    company_name: Mapped[str] = mapped_column(String(160), nullable=False)
    industry_label: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True,
    )
    industry_key: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True,
    )
    city_key: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True,
    )
    form: Mapped[str] = mapped_column(
        String(20), default="enskild_firma", nullable=False,
    )
    started_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Publish-toggle: ägaren kan dölja företaget från klasskompisar.
    # Lärare ser ALLTID alla. Default True — kollegial transparens.
    is_published: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )

    # Aggregat-cache (uppdateras vid varje auto-tick)
    revenue_4w: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    profit_4w: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    margin_pct: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False,
    )
    kassa: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    n_employees: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    n_invoices_open: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    n_invoices_overdue: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
    )
    reputation: Mapped[int] = mapped_column(
        Integer, default=50, nullable=False,
    )
    week_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Bolagsverket-status (Fas B: deklaration)
    annual_report_status: Mapped[str] = mapped_column(
        String(20), default="not_due", nullable=False,
    )  # not_due | draft | submitted | reviewing | approved | rejected
    annual_report_year: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    annual_report_decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )

    # Fas G · företags-UC + nivå-progression
    uc_score: Mapped[int] = mapped_column(
        Integer, default=50, nullable=False,
    )  # 0-100 · företagets kreditvärdighet
    uc_rating: Mapped[str] = mapped_column(
        String(4), default="B", nullable=False,
    )  # AAA | A | B | C | D
    company_level: Mapped[str] = mapped_column(
        String(20), default="startup", nullable=False,
    )  # startup | vaxande | etablerat | marknadsledare
    level_unlocked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )

    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class SharedOpportunity(MasterBase):
    """Klass-skopig offertförfrågan · delas mellan flera elev-företag.

    Spec: dev/feature-allabolag.md (Fas C)

    Genereras periodiskt per (teacher_id, industry_key) — alla elever
    med matchande bransch ser samma förfrågan och tävlar med varsin
    SharedQuote. När deadline_at passerar väljer AI vinnare baserat
    på pris + pitch + leveranstid + rykte. Förlorarna får pedagogisk
    förklaring varför.

    Detta är pedagogiskt mycket starkare än per-elev-opps eftersom
    eleven ser KONKRET varför AI valde någon annans offert — och
    kan iaktta hur klasskompisar prissätter."""
    __tablename__ = "shared_opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    class_label: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True, index=True,
    )
    industry_key: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True,
    )
    customer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    customer_segment: Mapped[str] = mapped_column(
        String(20), default="privat", nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    market_price: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_delivery_days: Mapped[int] = mapped_column(
        Integer, default=14, nullable=False,
    )
    deadline_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True,
    )
    # Status: open | decided | expired
    status: Mapped[str] = mapped_column(
        String(20), default="open", nullable=False,
    )
    winner_student_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"), nullable=True,
    )
    decision_explanation: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class SharedQuote(MasterBase):
    """En elevs offert till en SharedOpportunity. Max ETT bud per elev
    och förfrågan."""
    __tablename__ = "shared_quotes"
    __table_args__ = (
        UniqueConstraint(
            "shared_opportunity_id", "student_id",
            name="uq_shared_quote_opp_student",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shared_opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("shared_opportunities.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    company_name: Mapped[str] = mapped_column(String(160), nullable=False)
    offered_price: Mapped[int] = mapped_column(Integer, nullable=False)
    offered_delivery_days: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    pitch_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pitch_quality: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
    )
    is_winner: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class CompanyJobAd(MasterBase):
    """Jobbannons från ett klass-företag · syns på Arbetsförmedlingen
    för andra elever att söka.

    Spec: dev/feature-allabolag.md (Fas D)

    Företagsägaren publicerar jobb. Andra elever i samma klass kan söka
    via /v2/arbetsformedlingen/klass-jobb. Vid anställning skapas en
    CompanyEmployment-rad och eleven får 'klass-företag · {bolagsnamn}'-
    badge i sin arbetsmarknad-vy."""
    __tablename__ = "company_job_ads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_share_id: Mapped[int] = mapped_column(
        ForeignKey("class_company_shares.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    posted_by_student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    monthly_salary: Mapped[int] = mapped_column(Integer, nullable=False)
    # Status: open | filled | closed
    status: Mapped[str] = mapped_column(
        String(20), default="open", nullable=False,
    )
    hired_student_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"), nullable=True,
    )
    posted_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    filled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )


class CompanyJobApplication(MasterBase):
    """Elevs ansökan till en CompanyJobAd."""
    __tablename__ = "company_job_applications"
    __table_args__ = (
        UniqueConstraint(
            "job_ad_id", "applicant_student_id",
            name="uq_company_job_app",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_ad_id: Mapped[int] = mapped_column(
        ForeignKey("company_job_ads.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    applicant_student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
    )
    cover_letter: Mapped[str] = mapped_column(Text, nullable=False)
    # Status: pending | accepted | rejected
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False,
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class CompanyEmployment(MasterBase):
    """Aktiv anställning: en elev jobbar i en annan elevs klass-företag."""
    __tablename__ = "company_employments"
    __table_args__ = (
        UniqueConstraint(
            "company_share_id", "employee_student_id",
            name="uq_company_employment",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_share_id: Mapped[int] = mapped_column(
        ForeignKey("class_company_shares.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    employee_student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    monthly_salary: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[date] = mapped_column(
        Date, server_default=func.current_date(),
    )
    ended_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Status: active | terminated
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False,
    )


class ClassSeasonEvent(MasterBase):
    """Säsong-event aktiverat av läraren · Black Friday, kris osv.

    Spec: Fas J"""
    __tablename__ = "class_season_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    event_kind: Mapped[str] = mapped_column(
        String(40), nullable=False,
    )  # black_friday | recruitment_crisis | sustainability | bankruptcy_chain
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )


class CompanyMentorship(MasterBase):
    """Mentor-relation · framgångsrikt bolag hjälper svagare.

    Båda bolagen får poäng. Mentorn får 'mentor_helps'-räknare,
    mentee:n får tillfällig +rykte-boost.
    Spec: Fas I"""
    __tablename__ = "company_mentorships"
    __table_args__ = (
        UniqueConstraint(
            "mentor_share_id", "mentee_share_id",
            name="uq_company_mentorship",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mentor_share_id: Mapped[int] = mapped_column(
        ForeignKey("class_company_shares.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    mentee_share_id: Mapped[int] = mapped_column(
        ForeignKey("class_company_shares.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )


class StudentEntrepreneurScore(MasterBase):
    """Elevens entreprenörspoäng + badges. Beräknas av compute helper
    från ClassCompanyShare-data + relevanta events.

    Spec: Fas H · multi-leaderboard"""
    __tablename__ = "student_entrepreneur_scores"

    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        primary_key=True,
    )
    total_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    badges: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
    )  # {badge_key: earned_at_iso}
    last_recomputed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class ClassWeeklyAward(MasterBase):
    """Veckans vinnare per kategori. Skapas av compute helper.

    Spec: Fas H"""
    __tablename__ = "class_weekly_awards"
    __table_args__ = (
        UniqueConstraint(
            "teacher_id", "category", "iso_year", "iso_week",
            name="uq_class_weekly_award",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    iso_year: Mapped[int] = mapped_column(Integer, nullable=False)
    iso_week: Mapped[int] = mapped_column(Integer, nullable=False)
    winner_student_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"), nullable=True,
    )
    winner_company_name: Mapped[Optional[str]] = mapped_column(
        String(160), nullable=True,
    )
    metric_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4), nullable=True,
    )
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class TeacherAiPrompt(MasterBase):
    """Lärares anpassning av en AI-system-prompt.

    Varje lärare kan skriva sin egen variant av Marias HR-prompt,
    Mats Arbetsförmedlings-prompt, pitch-bedömaren osv. Vid
    AI-anrop letas first lärar-id → custom-text upp via
    `resolve_prompt(prompt_key, teacher_id, default)`. Saknas rad
    eller är `is_active=False` används default-prompten från koden.

    `prompt_key` mappar mot konstanter i `school/ai_prompt_registry.py`
    (en katalog över alla prompts som får anpassas). Inte alla AI-
    anrop exponeras — tekniska klassificerare (kategori-match,
    klasskompis-bjudningar) hålls hårdkodade i koden.

    Nivåer: en lärare = en uppsättning prompts. Familje-konton räknas
    som lärare med is_family_account=True. Super-admin kan i
    nästa fas publicera mallar som blir tillgängliga för alla lärare.
    """
    __tablename__ = "teacher_ai_prompts"
    __table_args__ = (
        UniqueConstraint(
            "teacher_id", "prompt_key", name="uq_teacher_ai_prompt",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    prompt_key: Mapped[str] = mapped_column(String(80), nullable=False)
    # Lärarens custom-text. Tom sträng tillåten · betyder "stäng av
    # AI för denna prompt" om is_active=True. Använd hellre is_active
    # för on/off så att texten kan bevaras mellan av/på-cykler.
    custom_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # is_active=False → fall tillbaka till default-prompten utan att
    # läraren behöver radera sin text. Bra för A/B-testning.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


# Aktie-master-modeller (StockMaster, StockQuote, LatestStockQuote,
# MarketCalendar) — importeras här så att MasterBase.metadata känner
# till dem vid create_all.
from . import stock_models as _stock_models  # noqa: E402, F401

# EventTemplate (delade event-mallar för Wellbeing-events) — samma
# import-trick.
from . import event_models as _event_models  # noqa: E402, F401

# Sociala mekanismer (ClassEventInvite, ClassDisplaySettings).
from . import social_models as _social_models  # noqa: E402, F401

# Arbetsgivar-dynamik (CollectiveAgreement, ProfessionAgreement,
# EmployerSatisfaction[+Event], WorkplaceQuestion[+Answer]) — idé 1
# i dev_v1.md.
from . import employer_models as _employer_models  # noqa: E402, F401

# Bank-flöde (BankSession för BankID-simulering) — idé 3 i dev_v1.md.
# ScheduledPayment + PaymentReminder ligger i scope-DB.
from . import bank_models as _bank_models  # noqa: E402, F401

# Spelmotor-tabeller (ClassCalendar driver Monthly Engine-tickarna).
# Spec: dev/game-motor/12-data-modeller.md
from . import game_engine_models as _game_engine_models  # noqa: E402, F401

# Klasskompis-anställning (Fas C) · ClassmateEmployment binder ägare +
# anställd i olika scope-DB:s via master-DB-tabellen classmate_employments.
from . import employment_models as _employment_models  # noqa: E402, F401
