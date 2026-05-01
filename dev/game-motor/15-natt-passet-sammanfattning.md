# 15 · Spelmotor · Komplett genomgång (natt-passet)

> Sammanfattning av allt som byggts i denna PR · Sprint 1-6 + Fas 8 +
> post-analys-fixar.

## Statistik

- **12 commits** över sessionen
- **~12 000 rader ny kod** (backend + frontend + tester + docs)
- **165 game-engine-tester** alla gröna lokalt
- **10 nya backend-moduler** under `game_engine/`
- **3 nya frontend-vyer** under `v2/`
- **30+ nya endpoints** under `/v2/`
- **Frontend typecheck + Vite build** OK

## Komplett pipeline

Monthly Engine kör följande 8 faser per spelmånad per elev:

```
Fas A · Salary phase           (M1)  → MailItem(salary_slip) + lön-in-tx
Fas B · Fixed expenses         (M2)  → 5-7 staggered invoices dag 1-10
Fas C · Variable expenses      (M3)  → Konsumentverket × spend_profile
Fas E · Oväntade händelser     (E1+E2+E4)  → Försäkrings-mildring
Fas F · Social-förslag         (legacy events/)  → StudentEvent
Fas G · Pentagon-drift + tröghet (M4+P1+P2)  → WellbeingEvent
Fas H · Sjuk + VAB             (post-analys)  → Lönebortfall + EmployerSat
       ↓
   WeekTickRun.summary samlar allt
   wellbeing_events-loggen visar varje delta med tröghets-info
```

## Datamodellsöversikt

### Master-DB (delad över elever)
- `class_calendars` — klasstid, snabbspola-kontroller (G2)
- `week_tick_runs` — idempotensregister, audit (M5)
- `wellbeing_events` — pentagon-delta-logg (P2)

### Scope-DB (per elev/familj)
- `active_homes` — vad eleven bor i just nu (Sprint 5b)
- `job_applications` — pågående 5-rond intervju (Sprint 6)
- + befintliga: `Account`, `Transaction`, `MailItem`, `Loan`, `InsurancePolicy`,
  `InsuranceClaim`, `StudentEvent`, `Category`, `RentalContract`...

## Aktörer i v2-hub-kompassen

| # | Aktör | Status | Källkod |
|---|---|---|---|
| 01 | Banken | befintligt | api/bank.py |
| 02 | Skatteverket | befintligt | SkattenV2 |
| 03 | Lånegivaren | befintligt | LanV2 |
| 04 | Avanza | befintligt | AvanzaV2 |
| 05 | Försäkringar | befintligt | ForsakringarV2 |
| 06 | Förbrukning | befintligt | ForbrukningV2 |
| 07 | Arbetsgivaren | befintligt | + post-analys: sjuk + VAB |
| 08 | **Boendemarknaden** | **NY · Sprint 5+5b** | BoendemarknadV2 (tabb hyra/köp) |
| 09 | Pension | befintligt | PensionV2 |
| 10 | **Arbetsförmedlingen** | **NY · Sprint 6** | ArbetsformedlingenV2 (Mats 5-rond) |

## Vad eleven kan göra (sammanfattat)

**Boende:**
- Se sin nuvarande bostad (ActiveHome) med termination-status
- Säga upp hyreskontrakt (3 mån svensk uppsägning)
- Flytta till mindre/billigare hyresrätt
- Se listings i sin stad (filter: hushållsstorlek-anpassat)
- Köpa BR/villa (LTV 85/75%, kontantinsats-kontroll)
- Sälja sin bostad (mäklarkostnad 3% + reavinstskatt 22%)
- Se månatlig värdering med orealiserad vinst/förlust

**Jobbsök:**
- Se 6 lediga jobb i sin stad sorterade på match-score
- Söka jobb (max 2 aktiva åt gången)
- Köra 5-rond intervju med pedagogiska val per rond
- Acceptera/tacka nej till erbjudande
- Avbryta ansökan (med pentagon-konsekvens)

**Spelmotorn (automatiskt):**
- Lön kommer 25:e varje månad
- Fakturor staggered över dag 1-10
- Variabla utgifter spreads över hela månaden
- Slumpade oväntade händelser (försäkrings-mildring om policy finns)
- Sjuk/VAB-perioder (svensk lön-påverkan korrekt räknad)
- Pentagon driver + dräller med tröghets-klamp

## Vad läraren kan göra

**Klasshantering:**
- Skapa ClassCalendar med tempo (1 / 2 / 4 veckor per spelmånad)
- Pausa/återuppta kalender
- Snabbspola hela klassen en spelmånad framåt

**Per-elev (TeacherStudentDetailV2):**
- Se elevens kompletta tick-historik
- Se senaste 30 dagars pentagon-händelser med "(clamp)"-indikator
- Tick:a en specifik spelmånad manuellt
- Se aktiva job-applications

**Validering (Fas 8):**
- POST /v2/teacher/monte-carlo med valfri konfig
- CLI: `python -m hembudget.game_engine.monte_carlo --grid`
- Få percentil-statistik + classification (positive/marginal/negative)

## Pedagogisk slutsats av Monte Carlo

Initial körning visar att vi behöver kalibrera difficulty:
- Nivå 1 sparsam: 95.7 % positiv ✅ (matchar designmål)
- Nivå 3 slösa: 97.3 % positiv ❌ (bör vara 30-40%)

Detta är förväntad upptäckt — verktyget gör sitt jobb. Kalibrering är
arbete för Fas 8b/V2 (difficulty-multiplikator på events + sjuk + boende).

## Källor (svenska 2026-data)

- SCB Strukturlönestatistik 2024 (uppjusterad 3 % för 2026)
- Konsumentverket hushållskostnader 2026
- Försäkringskassan VAB-statistik 2023
- Arbetsgivarverket "Staten i siffror — sjukfrånvaro" 2023
- Hyresgästföreningen Bostadsbarometern 2024
- Svensk Mäklarstatistik / Booli BRF-snitt 2024
- AFA-försäkring sjukperiods-fördelning

## Nästa steg

Inte gjort i denna PR (väntar på besked):
- Fas 8b · Difficulty-kalibrering (justera nivå 2-3)
- Fas 9 · Elev-tester (anti-fusk veckotest)
- Sprint 7 · Cron-runner i Cloud Scheduler (automatiska tickar)
- Sprint 8 · Echo-AI-integration (LLM-koppling med kontextuell coaching)
