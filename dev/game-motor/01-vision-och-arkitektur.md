# 01 · Vision och arkitektur

## Vision

Ekonomilabbet ska vara den **första svenska skol-plattformen där eleven
faktiskt LEVER en vuxen-ekonomi i klassrumstid**. Inte en spel-version
av ekonomi, utan ett komprimerat liv: 1 år på 8–10 veckor, med riktiga
siffror, riktiga val och riktig konsekvens.

Spelmotorn är det som gör skillnad mellan ett interaktivt läromedel och
en levande simulering. När motorn körs:

- Eleven får lön på 25:e (med korrekt lönespec)
- Fakturor landar i postlådan (med korrekta belopp och förfallodatum)
- Tandläkaren ringer en oväntad dag (och kostnaden beror på om eleven
  hade tandförsäkring)
- Pentagonen tippar i realtid baserat på beslutet
- Allt detta händer **utan att läraren behöver röra något**

## Designprinciper

### 1. Eleven ÄR karaktären

Det finns ingen separation mellan elev och avatar. När Sara A. spelar
sin Linnéa-karaktär är det Sara som driver Linnéas ekonomi. Pronomen i
UI:t använder **du-tilltal** (inte "hon" / "han") eftersom det är
elevens egen vardag som spelas.

Karaktären har attribut (yrke, lön, stad, familj) men ingen själv-
ständig agency. Eleven fattar varje beslut.

### 2. Allt är data, inget är magi

Varje wellbeing-förändring ska kunna spåras till en konkret händelse:
- "Hälsa -4" → "Tandläkaren ringde 17 apr · 4 200 kr · ej försäkrad"
- "Ekonomi +2" → "ISK-överföring 600 kr · sparmål"
- "Karriär +1" → "Anders höjde Bokföring till GRUND"

Inga svarta lådor. Lärare och elev kan alltid se VARFÖR.

### 3. Determinism med variation

Profile Generator är **seed-baserad**. Samma seed → samma karaktär.
Detta är viktigt för:
- Reproducerbarhet (lärare kan testa scenarion)
- Audit (vi kan rekonstruera elevens situation vid bedömning)
- Forskning (Monte Carlo-validering med kontrollerad variation)

Men inom en seed finns realistisk variation — två elever på samma
nivå får olika startkapital, olika startpentagon, olika livsmanus.

### 4. Komprimerad tid, expanderad upplevelse

1 spelmånad = 1 realvecka. På 4 veckors klassrumstid hinner eleven
uppleva en hel termins ekonomi. Tids-axeln är komprimerad, men
upplevelsetätheten är hög: lönen kommer, hyran ska betalas, tand-
läkaren ringer, jobbintervjun bokas — allt händer faktiskt.

### 5. Friktion bevarad där det är pedagogiskt

BankID-flödet är 6 steg med flit. Bokföring kräver klick. Bolåneval
kräver KALP-räkning. Vi automatiserar för **konsekvens** (lön kommer
varje vecka), inte för **bekvämlighet** (man måste fortfarande läsa
fakturan innan man signerar).

## Tre-motors-arkitekturen

```
                    ┌─────────────────────────┐
                    │  Profile Generator      │
                    │  (1 gång, vid skapelse) │
                    │                         │
                    │  • Yrke + lön           │
                    │  • Stad + boende        │
                    │  • Familj + relationer  │
                    │  • Initial pentagon     │
                    │  • Startkapital         │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   Karaktären finns       │
                    │   (StudentProfile +      │
                    │    scope-DB seedad)      │
                    └────────────┬────────────┘
                                 │
                  ┌──────────────┴──────────────┐
                  │                             │
                  ▼                             ▼
    ┌──────────────────────┐       ┌──────────────────────┐
    │  Monthly Engine      │       │  Event & Decision    │
    │  (varje 7:e dag)     │       │  Engine              │
    │                      │       │  (realtid + daglig)  │
    │  • Lönespec          │       │                      │
    │  • Fasta fakturor    │       │  • Slumpade händelser│
    │  • Variabla utgifter │       │  • Försäkrings-check │
    │  • Pentagon-drift    │       │  • Echo-triggers     │
    │  • Värderingar       │       │  • Lärar-injektion   │
    │  • Säsongsevent      │       │  • Beslut-portar     │
    └──────────────────────┘       └──────────────────────┘
                  │                             │
                  └──────────────┬──────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │  Eleven upplever         │
                    │  (Postlåda, pentagon,    │
                    │   notiser, val)          │
                    └─────────────────────────┘
```

### Profile Generator

**Körs:** En gång, när läraren skapar elev (eller eleven själv via
self-signup om det aktiveras).

**Input:**
- Lärarens val (arketyp, partner-modell, startnivå, ev. seed-overrides)
- Slumpfunktion (deterministisk via seed)

**Output:**
- `StudentProfile` (yrke, lön, stad, boende, familj)
- Initial pentagon (med ±12 poäng variation per axel)
- Seedade konton (lönekonto, sparkonto, ISK)
- Första månadens lönespec + fakturor
- Bostadslån om bostadsrätt/villa
- Initial försäkringsstatus

**Tekniskt:** Helt deterministisk givet (teacher_id, seed). Modulen
ligger i `backend/hembudget/game_engine/profile_generator/`.

### Monthly Engine

**Körs:** Cron varje vecka (i prod) eller manuellt via lärar-dashboard
("Snabbspola till nästa månad").

**Ansvar:**
- **Lönespec** den 25:e med korrekt skatt + OB + semesterersättning
- **Fasta utgifter** (hyra/ränta + el + vatten + abonnemang) staggered
- **Variabla utgifter** (mat, kläder, transport) med ±5–20 % variation
- **Pentagon-drift** (automatisk justering baserat på balans)
- **Bostadsvärdering** (månatlig uppdatering med lätt slump)
- **Säsongsevent** (var 3:e månad: kvartalsrapport, bonus, sjuksk.)
- **Pension/ISK** uppdaterad månadsvis

**Tekniskt:** Kör som SQLAlchemy-transaktion per elev, idempotent
per (student_id, year_month). Modulen i `backend/hembudget/game_engine/
monthly_engine/`. Återanvänder existerande `scenarios/engine.py` +
`wellbeing/calculator.py`.

### Event & Decision Engine

**Körs:** På varje API-anrop som ändrar elevstate, samt schemalagda
ticks (t.ex. dagligen för "tandläkaren ringer").

**Ansvar:**
- **Oväntade händelser** (1–3 per spelmånad beroende på nivå)
- **Försäkrings-check** vid varje händelse (mildra / förstärka)
- **Echo-triggers** (proaktiv coaching, sokratiska frågor)
- **Beslut-portar** (KALP, bolåneval, jobbyte, försäkringsval)
- **Lärar-injektioner** (extra händelser via TeacherMailbox-bulk)
- **Konsekvens-kedjor** (försenad faktura → påminnelse → inkasso)

**Tekniskt:** Trigger-driven via SQLAlchemy event-listeners + ett
job-queue (initialt synkron, senare async). Modulen i
`backend/hembudget/game_engine/event_engine/`. Återanvänder
existerande `events/engine.py`.

## Hur de samverkar

```
T+0 (skapelse)
  Profile Generator → StudentProfile + scope-DB seedad

T+1 vecka (= 1 spelmånad)
  Monthly Engine tickar:
    → Lönespec, fakturor, drift
    → Pentagon-drift räknas
  Event Engine tickar:
    → Slumpa 1–3 händelser för månaden
    → Schemalägg dem på olika dagar
  Eleven upplever via UI

Realtid under veckan
  Eleven gör val (signera, klassa, byta jobb)
  Event Engine reagerar:
    → Pentagon uppdateras
    → Echo kan trigga
    → Konsekvens-kedjor uppdateras
  Lärare ser allt live i klass-hub
```

## Integration med existerande system

| Befintligt | Roll i spelmotorn |
|---|---|
| `school::Student` | Eleven (login, teacher-koppling) |
| `school::StudentProfile` | Karaktärsdata (utökas med fler fält) |
| `school::ScenarioBatch` | Behålls för dokument-genereringen (lönespec, fakturor) |
| `events::EventTemplate` | Mall-pool för Event Engine |
| `wellbeing::calculator` | Pentagon-räknare (utökas med drift) |
| `scenarios::engine` | Bolåne-scenariomotor (KALP, amortering) |
| `loans::*` | Bolån-domänen (skuldkvot, ränteberäkning) |
| `insurance::*` | Försäkringsdomänen (kopplas till Event Engine) |

Spelmotorn är inte en ny silo — den är **orkestrerings-lagret** över
de domänmoduler vi redan har.
