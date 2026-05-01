# 11 · Implementations-plan

> Hur vi bygger det här utan att bryta v1 eller v2. Faser med
> tydlig prioritet, beroenden och delbara delleveranser.

## Princip · stegvis utrullning

Spelmotorn är **inte** en stor-bang-omskrivning. Vi bygger fas för
fas, varje fas är produktivt levererbar och kan släppas in i prod
oberoende.

V2 är referensvyn — alla nya features hamnar där först. V1 lämnas
orört.

## Fas-grupper

### Grupp 1 · Fundament (måste-finnas)

| Fas | Namn | Beskrivning | Beroenden |
|---|---|---|---|
| **G1** | Yrkespool & Stadspool | YAML/Python-konstanter med 150 yrken + 22 städer | — |
| **G2** | ClassCalendar-modell | Master-tabell för klass-tid + endpoints | — |
| **G3** | Profile Generator v1 | Slumpa yrke/stad/boende/familj | G1 |
| **G4** | Initial pentagon-variation | ±12 modifikatorer per axel | G3 |
| **G5** | Profile-preview-endpoint | Förhandsvisning före creation | G3 |

Leverans-mål: Lärare kan skapa elever med realistiska, varierade
profiler där pentagonen redan har en unik startposition.

### Grupp 2 · Monthly Engine (kärna)

| Fas | Namn | Beskrivning | Beroenden |
|---|---|---|---|
| **M1** | Salary phase | Lönespec-generering 25:e | G3 |
| **M2** | Fixed expenses phase | Hyra/el/abonnemang staggered | G3 |
| **M3** | Variable expenses phase | Konsumentverket × spend_profile | G3 |
| **M4** | Drift calculator | Månads-drift på pentagonen | M1, M2, M3 |
| **M5** | Idempotent week-tick orchestrator | Kör alla faser idempotent | M1-M4 |
| **M6** | Cron + manuell trigger | Schemalagd + lärar-snabbspola | M5 |

Leverans-mål: Klassen tickar automatiskt varje vecka. Lönen kommer,
fakturor landar, eleverna har riktig vardag att hantera.

### Grupp 3 · Event Engine (livet)

| Fas | Namn | Beskrivning | Beroenden |
|---|---|---|---|
| **E1** | Event template-pool 1.0 | 30–50 templates (tandläkare, cykelstöld, bonus etc) | — |
| **E2** | Försäkrings-mildring | Match templates × policies | E1 |
| **E3** | Konsekvens-kedjor | Påminnelse → inkasso → KFM | E1 |
| **E4** | Daily tick + scheduling | Schemalagda events triggar | E1 |
| **E5** | Echo-topics + minne | Reaktiv coaching | M5 |
| **E6** | Säsongsevent | Q1-Q4 garanterade events | E1 |
| **E7** | Lärar-injektion av events | Bulk-inject via templates | E1 |

Leverans-mål: Det händer **oväntade** saker varje månad. Försäkringar
spelar roll. Echo coachar utan att ge svar.

### Grupp 4 · Arbetsförmedlingen

| Fas | Namn | Beskrivning | Beroenden |
|---|---|---|---|
| **A1** | Yrkespool-frontend (lista jobb) | UI för att se tillgängliga jobb | G1 |
| **A2** | match_score-beräkning | Backend matchning | G1 |
| **A3** | 5-rond intervju-flöde | State-machine | A2 |
| **A4** | AI Mats prompts | LLM-koppling (Claude) | A3 |
| **A5** | Bytes-konsekvenser | Pentagon + lön + boende | A3 |

Leverans-mål: Eleven kan söka och få nytt jobb realistiskt.

### Grupp 5 · Boendemarknad

| Fas | Namn | Beskrivning | Beroenden |
|---|---|---|---|
| **B1** | Marknadsdata + drift | Per-stad pris-uppdatering månadsvis | G2 |
| **B2** | Listings-pool per stad | Köp-bara bostäder | G1 |
| **B3** | Köp-flödet | KALP → bolån → boende-byte | B1, B2 |
| **B4** | Sälj-flödet | Marknadstid + skatt | B3 |
| **B5** | Stadsbyte | Auto-trigger vid jobbyte | B3, A5 |

Leverans-mål: Eleven kan köpa, sälja och flytta. Bostadsmarknaden är
levande.

### Grupp 6 · Pentagon-djup

| Fas | Namn | Beskrivning | Beroenden |
|---|---|---|---|
| **P1** | Tröghet (momentum) | Klamp per event/dag/månad | M4 |
| **P2** | WellbeingEvent-logg | Varje förändring spåras | M4, E2 |
| **P3** | Wellbeing-mål | Eleven sätter mål per axel | P2 |
| **P4** | Wellbeing-trail-vy | `/teacher/v2/elev/:id/wellbeing-trail` | P2 |
| **P5** | Echo-minne | Kontextuella påminnelser | E5 |

### Grupp 7 · Tids-kontroll

| Fas | Namn | Beskrivning | Beroenden |
|---|---|---|---|
| **T1** | Snabbspola-knapp + endpoint | Klass-nivå advance | G2, M5 |
| **T2** | Pausa klass | Per-klass paus | G2 |
| **T3** | Pausa elev | Per-elev paus | G2 |
| **T4** | Rewind | Rollback till tidigare ym | G2 + snapshot |
| **T5** | What-if-läge | Parallell-grenshantering | G2 + snapshot |

### Grupp 8 · Validering

| Fas | Namn | Beskrivning | Beroenden |
|---|---|---|---|
| **V1** | Monte Carlo-skript | 10 000 simuleringar per nivå | M5, E2 |
| **V2** | Difficulty-balans-iteration | Justera tills mål-kvantil nås | V1 |
| **V3** | Audit-tester | Spårbarhets-tester | P2 |
| **V4** | Performance-tester | Skala till 100 klasser | M6 |

## Prioritetsordning (tidsuppskattning)

För att få ett **MVP som faktiskt fungerar** krävs minimum:

1. **Sprint 1 (1–2 v):** G1, G2, G3, G4 — Profile Generator klar
2. **Sprint 2 (1–2 v):** M1, M2, M3, M5 — Monthly Engine kärnfunkar
3. **Sprint 3 (1 v):** E1, E2, E4 — Event Engine med försäkring
4. **Sprint 4 (1 v):** M4, M6, P1 — Drift + cron + tröghet
5. **MVP-release** — Hela systemet körs autonomt 🎉

Sen kan vi iterera med:
- **Sprint 5+:** A* (Arbetsförmedlingen)
- **Sprint 7+:** B* (Boendemarknad)
- **Sprint 9+:** T* + V* (Tids-kontroll + Validering)

## Kompatibilitet med v2

| V2-fas | Spelmotor-impact |
|---|---|
| Fas 2X (Skapa elev) | Anropar Profile Generator (G3) istället för dagens basic |
| Fas 2U (Postlådor) | Får automatisk feed från Monthly Engine + Event Engine |
| Fas 2V (Maria-lista) | Behöver inga ändringar — Maria-motorn är oberoende |
| Fas 2Z (Pentagon flip) | Visar nu också driftsdata + mål |
| Fas 2AB (Notiser) | Får mer realistiskt innehåll från events |
| Fas 2AG (Kompetens-override) | Inga ändringar |

## Migrering av befintliga elever

Vid roll-out:
1. Alla v1-elever utan StudentProfile → Profile Generator triggas i
   bakgrunden
2. v1-elever MED StudentProfile → behåll, men kör Monthly Engine för
   kommande månader
3. v1-elev-progress (assignments, modules) bevaras

Tekniskt: ny one-shot-migrering-skript `migrate_to_game_engine.py`
som läraren triggar via lärar-vyn.

## Beslut som behöver tas

Innan vi börjar:

1. **AI-budget:** Hur mycket Anthropic-tokens får vi spendera per klass?
2. **Snabbspola-kontroll:** Får ELEVER snabbspola sin egen tid? Eller
   bara lärare?
3. **Default-hastighet:** 1, 2 eller 4 verkliga veckor per spelmånad?
4. **What-if-tillgång:** Bara lärare? Eller även elev som "spara"?
5. **Profile Generator-randomness:** Helt seed-baserad eller blandning
   med lärar-vägledning?

Mitt förslag: starta strikt (lärare bestämmer det mesta), öppna
gradvis när vi ser hur klassrumstempot fungerar.

## Open questions för forskning

- Hur balanserar vi "för många events = stress" mot "för få = tråkigt"?
- Kan Echo verkligen vara sokratisk utan att gå i intelletuellt cirkulär?
- Hur vi mäter att eleven faktiskt **lär sig** (inte bara navigerar)?

Dessa besvaras genom Monte Carlo + lärar-feedback + elev-reflektioner
under pilot-perioden.
