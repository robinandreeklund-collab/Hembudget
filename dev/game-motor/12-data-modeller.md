# 12 · Data-modeller

> Befintliga + nya tabeller som spelmotorn kräver. Följer mönstret
> `master::TableName` (delas mellan elever) eller `scope::TableName`
> (per elev).

## Befintliga modeller (återanvänds)

### master-DB

| Tabell | Roll i spelmotorn |
|---|---|
| `Teacher` | Ägare, AI-budget |
| `Student` | Eleven (utökas med `paused_until`) |
| `StudentProfile` | Karaktärsdata (utökas — se nedan) |
| `Family` | Familj-koppling |
| `ScenarioBatch` | PDF-utskick (lönespec mm) — behåll |
| `ScenarioArtifact` | Per-PDF-artefakt — behåll |
| `EventTemplate` | Event-mallar — utökas |
| `Module`, `ModuleStep` | Lärar-skapade moduler |
| `Competency`, `ModuleStepCompetency` | Kompetens-koppling |
| `StudentCompetencyOverride` | Lärar-höjningar (Fas 2AG) |
| `SalaryNegotiation`, `NegotiationRound` | Maria-rundor |
| `CollectiveAgreement`, `ProfessionAgreement` | Avtal |
| `MarketSalaryRange` | Lönespann (utökas till alla yrken) |
| `InterestRateSeries` | Räntor månadsvis |
| `MortgageDecision` | Bolåneval |
| `BankIDSession` | Signering |
| `V2OnboardingEvent` | Onboarding-spår |
| `StudentActivity` | Audit-trail |
| `Assignment` | Lärar-uppdrag |
| `Message` | Lärar-elev-dialog |
| `WellbeingEvent` | (saknas idag — införs i P2, se nedan) |

### scope-DB (per elev)

| Tabell | Roll |
|---|---|
| `Account` | Konton (lönekonto, sparkonto, ISK, kredit) |
| `Transaction` | Transaktioner |
| `Category` | Kategorier (default + lärar-egna) |
| `Rule` | Bokförings-regler |
| `MailItem` | Postlåda — bärare av events och fakturor |
| `Loan`, `LoanProduct` | Lån |
| `PaymentMark` | Betalningsanmärkning |
| `CreditCheck` | UC-koll |
| `KALPCalculation` | KALP-spår |
| `Goal` | Sparmål |
| `UpcomingTransaction` | Kommande dragningar |
| `RentalContract`, `RentalNotice` | Hyresavtal |
| `InsurancePolicy`, `InsuranceClaim` | Försäkringar |
| `UtilitySubscription`, `UtilityReading` | El, mobil, bredband |
| `PensionAssumption` | Pensionsprognos |
| `StockHolding`, `StockTransaction`, `FundHolding` | Avanza |
| `Scenario` | Sparat scenario |
| `WellbeingScore` | Per-månads-snapshot |

## Utökningar av befintliga modeller

### `StudentProfile` (utökas)

```python
class StudentProfile:
    # Befintligt
    student_id: int (PK)
    character_first_name: str
    character_last_name: str
    profession: str
    employer: str
    gross_salary_monthly: int
    net_salary_monthly: int
    tax_rate_effective: float
    personality: str
    age: int
    city: str
    family_status: str
    housing_type: str
    housing_monthly: int
    has_mortgage: bool
    has_car_loan: bool
    has_student_loan: bool
    has_credit_card: bool
    children_ages: list[int]
    partner_age: int | None
    
    # NYA · spelmotorn
    yrkespool_key: str             # "it_konsult_junior"
    stadspool_key: str             # "stockholm" / "medelstad" / ...
    seed: str                      # Profile Generator-seed (deterministisk)
    initial_pentagon: dict         # JSON · {"economy": 58, ...}
    has_chronic_condition: bool    # Slumpas vid Profile Generator
    commute_minutes: int           # Beräknas från stad + yrke
    spend_profile_initial: str     # "sparsam" | "balanserad" | "slosa"
    boende_kvm: int                # m² på nuvarande bostad
    boende_value_at_purchase: int  # SEK om bostadsrätt/villa
```

### `Student` (utökas)

```python
class Student:
    # Befintligt
    paused_until: datetime | None  # NY · per-elev-paus
```

### `EventTemplate` (utökas)

Befintlig är minimal. Utökas med:

```python
class EventTemplate:
    # Befintligt
    key: str
    display: str
    cost_range: tuple[int, int]
    
    # NYA · spelmotorn
    severity: str                  # "mild_positive" | "moderate" | "severe"
    frequency_per_year: float      # 0.5 = 50% chans/år
    age_range: tuple[int, int]
    family_status_filter: list[str] | None
    relevant_insurance_kinds: list[str]
    mitigation_rules: dict         # JSON: hur försäkringar mildrar
    pentagon_unmitigated: dict     # JSON: påverkan utan mildring
    pentagon_mitigated: dict       # JSON: påverkan med mildring
    follow_up_chain: list[dict] | None  # Konsekvens-kedjor
    echo_trigger_text: str | None
    actor_route: str | None        # "/v2/lan" etc
```

## Nya tabeller (master-DB)

### `ClassCalendar`

```python
class ClassCalendar(MasterBase):
    __tablename__ = "class_calendars"
    
    id: int (PK)
    teacher_id: int (FK → teachers)
    real_start_date: date          # Klassens start i verklig tid
    sim_start_year_month: str      # "2026-01"
    weeks_per_sim_month: int       # 1 / 2 / 4
    paused_until: datetime | None
    last_tick_year_month: str      # Senast tickade spelmånaden
    last_tick_at: datetime
    created_at: datetime
```

### `WellbeingEvent`

```python
class WellbeingEvent(MasterBase):
    __tablename__ = "wellbeing_events"
    
    id: int (PK)
    student_id: int (FK → students, indexed)
    occurred_at: datetime (indexed)
    axis: str                      # "economy" | "health" | ...
    delta: int                     # +/- N
    new_value: int                 # Värdet EFTER ändringen
    reason_kind: str               # "event" | "drift" | "decision" | "goal_achieved"
    reason_id: int | None          # FK till MailItem/Module/etc
    reason_table: str | None       # "mail_items" / "modules" / ...
    explanation: str               # Människo-läsbar
```

### `WellbeingGoal`

```python
class WellbeingGoal(MasterBase):
    __tablename__ = "wellbeing_goals"
    
    id: int (PK)
    student_id: int (FK)
    axis: str
    target_value: int              # 0-100
    deadline: date
    set_at: datetime
    achieved_at: datetime | None
    motivation: str | None
```

### `EchoMemory`

```python
class EchoMemory(MasterBase):
    __tablename__ = "echo_memories"
    
    id: int (PK)
    student_id: int (FK)
    memory_kind: str               # "wellbeing_trend" | "decision" | ...
    summary: str                   # Kondenserad text
    importance: int                # 1-10
    relevant_axis: str | None
    expires_at: datetime
    referenced_count: int
    created_at: datetime
```

### `JobApplication`

```python
class JobApplication(MasterBase):
    __tablename__ = "job_applications"
    
    id: int (PK)
    student_id: int (FK)
    job_pool_key: str              # FK-likt till yrkespoolen
    started_at: datetime
    current_round: int             # 1-5
    status: str                    # "active" | "completed" | "abandoned" | "rejected"
    match_score: int               # 0-100
    final_offer_salary: int | None
    accepted: bool
```

### `JobApplicationRound`

```python
class JobApplicationRound(MasterBase):
    __tablename__ = "job_application_rounds"
    
    id: int (PK)
    application_id: int (FK)
    round_no: int                  # 1-5
    student_input: str             # Vad eleven skrev/valde
    mats_response: str             # AI Mats svar
    score: int                     # 0-10 per rond
    completed_at: datetime
```

### `EventInstance`

Spelmotorn skapar konkret event-instans per elev (inte bara MailItem):

```python
class EventInstance(MasterBase):
    __tablename__ = "event_instances"
    
    id: int (PK)
    student_id: int (FK)
    template_key: str              # FK-likt EventTemplate.key
    triggered_at: datetime
    scheduled_for: datetime        # När eleven ska se det
    cost_actual: int
    mitigation_applied: str | None # "tandvård_premium" osv
    pentagon_delta: dict           # JSON
    follow_up_parent_id: int | None  # Om del av kedja
    seen_at: datetime | None       # När eleven såg det
    decision_made: str | None      # "paid" | "ignored" | ...
```

## Nya tabeller (scope-DB)

### `HousingValuation`

```python
class HousingValuation:
    __tablename__ = "housing_valuations"
    
    id: int (PK)
    year_month: str                # "2026-04"
    estimated_value: int           # SEK
    market_drift_pct: float        # Det månadens drift
    recorded_at: datetime
```

Per-månads-snapshot av elevens boendevärde.

### `HousingTransaction`

```python
class HousingTransaction:
    __tablename__ = "housing_transactions"
    
    id: int (PK)
    kind: str                      # "buy" | "sell" | "rent_change" | "move_city"
    started_at: datetime
    completed_at: datetime | None
    listing_key: str | None        # Vilken bostad köpts/sålts
    purchase_price: int | None
    sale_price: int | None
    realisation_tax: int | None
    new_loan_id: int | None        # FK till Loan om bolån skapats
```

## Avoidance · vad vi INTE gör

- **Inte** lägg till en gigantisk "GameState"-tabell. Spel-state är
  härledd från befintliga tabellers tillstånd (transaktioner,
  fakturor, lån, försäkringar).
- **Inte** dubblera data mellan master och scope. Master-DB är
  klass-läran, scope-DB är elevens privata ekonomi.
- **Inte** skapa "FlavorText"-tabell. AI-text genereras on-demand och
  cachas i klient-state.

## Migrationer

Alla nya tabeller skapas via `MasterBase.metadata.create_all()` (för
master) och `Base.metadata.create_all()` (för scope). Idempotent.

ALTER TABLE för utökningar av `StudentProfile`, `Student`,
`EventTemplate` läggs i `school::engines._run_master_migrations`
enligt befintligt mönster.
