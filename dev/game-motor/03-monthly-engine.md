# 03 · Monthly Engine

> Den automatiska kalendern. Tickar varje vecka (= 1 spelmånad i
> kompresserad tid) och skapar lönespec, fakturor, drift, värderingar
> och pentagon-justeringar. Idempotent per `(student_id, year_month)`.

## Översikt

```
Söndag 23:59           Cron triggar week-tick
Eller manuellt          (lärare trycker "Snabbspola månad")
                            │
                            ▼
                    ┌───────────────────┐
                    │ Monthly Engine    │
                    │ för varje aktiv   │
                    │ elev parallellt   │
                    └─────────┬─────────┘
                              │
        ┌─────────────┬───────┴───────┬─────────────┐
        ▼             ▼               ▼             ▼
   ┌────────┐  ┌──────────┐  ┌─────────────┐  ┌─────────┐
   │ Lön    │  │ Fakturor │  │ Pentagon-   │  │ Värd-   │
   │ 25:e   │  │ staggered│  │ drift       │  │ eringar │
   └────────┘  └──────────┘  └─────────────┘  └─────────┘
```

## Schema per spelmånad

Varje spelmånad genereras i 4 faser:

### Fas A · Lönespec (genereras dag 25 i spelmånad)

Skapar:
- `MailItem` med kind="salary_slip" + amount + body_meta
- Inbetalning till lönekontot (Transaction)
- Eventuell pension-avsättning (PensionAssumption-uppdatering)

Lönespecens innehåll följer existerande `school::SalaryNegotiation`-
flow + nya fält:
- Bruttolön, OB, semesterersättning
- Skatt (kommunal + statlig), grundavdrag
- ITP1/AKAP-KL pensionsavgift
- Nettolön
- Eventuell löneförhöjning från Maria-rond

### Fas B · Fasta utgifter (staggered dag 1–10)

| Dag | Faktura | Belopp | Källa |
|---|---|---|---|
| 1 | Hyra/avgift | profile.housing_monthly | RentalContract eller bolån |
| 3 | El (Tibber spotpris) | 600–1200 kr (säsong) | UtilitySubscription |
| 5 | Bredband | 389 kr | UtilitySubscription |
| 7 | Mobil | 119–399 kr | UtilitySubscription |
| 8 | Hemförsäkring | 100–200 kr | InsurancePolicy |
| 10 | SL-kort / pendling | 970 kr | Optional baserat på stad |

Staggering är viktigt — om allt kommer dag 1 så krockar med hyran och
eleven får alltid likviditetsproblem första veckan. Realistiskt sprider
fakturor sig ojämnt över månaden.

### Fas C · Variabla utgifter (slumpas över hela månaden)

Genereras med Konsumentverkets schabloner × elevens spend_profile:

```python
def variable_expenses(profile, year_month, level, spend_profile):
    base = consumer_authority_baseline(
        family_status=profile.family_status,
        age=profile.age,
        children_ages=profile.children_ages,
    )
    # base = {"mat": 4500, "klader": 800, "kultur_fritid": 1200, ...}
    
    multiplier = {
        "sparsam": 0.85,
        "balanserad": 1.00,
        "slosa": 1.25,
    }[spend_profile]
    
    variation = {1: 0.05, 2: 0.12, 3: 0.20}[level]
    
    return {
        cat: int(amount * multiplier * (1 + rng.uniform(-variation, variation)))
        for cat, amount in base.items()
    }
```

Varje kategori bryts ned i 3–10 delkostnader (transaktioner) som
fördelas på olika dagar i månaden. T.ex. mat → 4–8 Coop/ICA-köp,
restaurang → 2–4 lunchbesök etc.

### Fas D · Pentagon-drift

Efter all data är genererad körs en automatisk drift:

```python
def monthly_drift(pentagon, balance_state, profile):
    drift = {"economy": 0, "safety": 0, "health": 0, "social": 0, "leisure": 0}
    
    # ECONOMY: ackumulerad sparkvot
    save_rate = month_savings / month_income
    if save_rate >= 0.15: drift["economy"] += 2
    elif save_rate >= 0.10: drift["economy"] += 1
    elif save_rate < 0: drift["economy"] -= 3  # gick i minus
    
    # SAFETY: kompetens-engagemang
    if month_completed_module_steps >= 3: drift["safety"] += 2
    elif month_completed_module_steps == 0: drift["safety"] -= 1
    
    # HEALTH: vårdfakturor + kost
    if has_unpaid_health_bills: drift["health"] -= 2
    if month_alcohol_purchases > threshold: drift["health"] -= 1
    
    # SOCIAL: dialog med lärare + peer
    if unread_teacher_feedback >= 5: drift["social"] -= 2
    if engaged_in_dialog: drift["social"] += 1
    
    # LEISURE: balans
    if leisure_spend == 0 and other_categories_high: drift["leisure"] -= 2
    if leisure_spend > leisure_budget * 1.5: drift["leisure"] -= 1
    elif 0.5 <= leisure_spend / budget <= 1.0: drift["leisure"] += 1
    
    # Tröghet: max ±5 per axel per månad via drift
    return {k: max(-5, min(5, v)) for k, v in drift.items()}
```

## Kalender-vetenskap

### Helger och skol-lov

Veckotick:en pausas:
- **Sommarlov** (ca 9–24 v) → eleven loggar in lite, men **kör inte**
  vidare i tid. När eleven återvänder fortsätter där hen släppte.
- **Höstlov / Sportlov / Påsk** → frivillig paus, lärare avgör
- **Helgdagar** (julafton, nyår) → händelser flyttas till närmaste
  vardag

### Datum-mappning

Vi behöver en mapping mellan **klassrumsdatum** (verklig kalender) och
**spelkalender** (komprimerad tid):

```python
class ClassCalendar(MasterBase):
    teacher_id: int
    real_start_date: date          # När klassen startade Ekonomilabbet
    sim_start_year_month: str      # T.ex. "2026-01"
    weeks_per_sim_month: int = 1   # Default 1 vecka per månad
    paused_until: date | None
    
    def real_date_to_sim_ym(real_dt) -> str:
        weeks_elapsed = (real_dt - real_start_date).days // 7
        return add_months(sim_start_year_month, weeks_elapsed)
```

Alla Monthly Engine-anrop slår mot `ClassCalendar` för att veta
vilken spelmånad som ska tickas.

## Idempotens

Varje månads-tick taggar varje genererad rad med `year_month`. Vid
re-run körs:

```python
existing = scope_db.query(MailItem).filter(
    MailItem.scenario_year_month == year_month,
    MailItem.kind == "salary_slip",
).first()
if existing:
    return  # Redan tickad
```

Det säger att en lärare kan trycka "Snabbspola" två gånger utan
duplicering.

## Existerande integration

| Befintligt | Återanvänds för |
|---|---|
| `school::ScenarioBatch` | Behåll för PDF-generering av lönespec |
| `db::MailItem` | Mottagare av genererade fakturor |
| `db::Transaction` | Mottagare av lönen + fakturornas autogiro |
| `wellbeing::calculator` | Räkna pentagon vid varje tick |
| `pension::pension_forecast` | Uppdatera prognos månadsvis |
| `loans::credit::compute_kalp` | Ny KALP varje månad om bolån finns |
| `tax::compute_tax_summary` | Ackumulera mot årsbokslut |

## Performance

- 28 elever × 1 tick/vecka × ~50 ms per tick = ~1.4 s per veckotick
- Parallelliseras med multiprocessing (1 process per scope-DB)
- Cron körs nattetid (söndag → måndag) så lärare ser nya data måndag
  morgon

## Lärar-kontroll

| Action | Endpoint | Effekt |
|---|---|---|
| Snabbspola en månad | `POST /v2/teacher/calendar/advance` | Tickar nästa spelmånad nu |
| Pausa klass | `POST /v2/teacher/calendar/pause` | Stoppar autotick |
| Återställ till månad X | `POST /v2/teacher/calendar/rewind` | Rollback till tidigare ym |
| What-if-scenario | `POST /v2/teacher/calendar/branch` | Skapa parallell timeline |
| Justera weeks_per_month | `PATCH /v2/teacher/calendar` | Ändra hastighet (1=normal, 2=halv-fart) |

## Implementation

```
backend/hembudget/game_engine/
  monthly_engine/
    __init__.py
    calendar.py          # ClassCalendar-modell + mapping
    week_tick.py         # Huvud-entry: tick_for_student(sid, ym)
    salary_phase.py      # Fas A
    fixed_expenses.py    # Fas B
    variable_expenses.py # Fas C (Konsumentverket-tabeller)
    drift_calculator.py  # Fas D
    cron.py              # Schemalagd cron-runner
```

## Cron-konfiguration (Cloud Run)

```yaml
# Cloud Scheduler
- name: ekonomilabbet-week-tick
  schedule: "59 23 * * 0"  # Söndag 23:59
  target_uri: https://ekonomilabbet.org/internal/cron/week-tick
  http_method: POST
  oidc_token: { service_account: scheduler-sa }
```

Internal-endpoint kräver IAM-auth (inte vanlig user-auth).
