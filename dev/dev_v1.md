# Dev plan v1 — fyra stora feature-områden

Den här filen är en levande implementationsplan för fyra större idéer
(arbetsgivar-dynamik, lönesamtal, banken, bank-features) — kopplade till
hur kodbasen redan är strukturerad. Skrivs inkrementellt: varje commit
lägger till nästa idé eller skärper sektioner som blivit otydliga.

Ingen kod skrivs här — bara analys, datamodeller, risker, faseordning.

## Status

| Idé | Status |
|---|---|
| 1. Arbetsgivar-nöjdhetsfaktor + kollektivavtal | utkast |
| 2. Lönesamtal (AI-förhandling) | utkast |
| 3. Banken (BankID-flöde + signering) | utkast |
| 4. Bank-features (kontoutdrag, kommande, lån) | utkast |
| Fas-plan + sekvensering | TODO |

---

## Befintlig grund (referens)

Innan vi planerar ovanpå plattformen — vad finns redan?

- **Yrken**: 17 yrken med löneintervall i `school/profile_fixtures.py`,
  hårdkodad employer-namn per yrke. SCB 2024-data + 5 % för 2026.
  `StudentProfile` har `profession`, `employer`, `gross_salary_monthly`,
  `net_salary_monthly`, `tax_rate_effective`. Deterministisk seed per
  `student_id`. Ingen koppling till kollektivavtal.
- **Kursmoduler**: `Module` + `ModuleStep` (master-DB). 5 step-typer:
  `read`, `watch`, `reflect`, `task`, `quiz`. Tilldelning via
  `Assignment`, framstegslogg via `StudentStepProgress`.
- **AI-infrastruktur**: Haiku 4.5 + Sonnet 4.6 via `school/ai.py`.
  Token-räkning per lärare (`Teacher.ai_*`-fält), per-elev daglig
  chattkvot, `AskAiThread/AskAiMessage` för audit. System-prompt
  cachas via `cache_control: ephemeral`.
- **Upcoming-flödet**: `UpcomingTransaction(kind=bill|income)` planerad
  faktura, matchas mot bank-`Transaction` via `matched_transaction_id`.
  Inga signeringssteg, ingen påminnelse-generering idag.
- **Batch-flödet**: `teacher/batch.py:create_batch_for_student()`
  renderar PDF:er (lönespec, kontoutdrag, lånebesked, kreditkort),
  lagrar som `BatchArtifact` BLOB i master-DB. Eleven ser dem under
  /my-batches och importerar manuellt.
- **Lån**: `CreditApplication` (ansökan) → `Loan` (godkänd) →
  `LoanPayment` (ränta/amortering). Existerande UI finns på /loans.

---

## Idé 1 — Arbetsgivar-nöjdhetsfaktor + kollektivavtal

**Pedagogisk kärna**: eleven ska se att arbetslivet INTE är ett vakuum.
Beslut man tar (sjukdag, VAB, ärlighet i frågor) påverkar hur chefen
ser på en. Och det finns en yttre ram: kollektivavtalet sätter
spelregler som chefen och facket gemensamt avtalat — eleven ska lära
sig att läsa och referera till dem.

### 1.1 Datamodell

Tre nya master-DB-tabeller:

```
CollectiveAgreement
├── id, code (t.ex. "if_metall_2025"), name, union, employer_org
├── valid_from, valid_to (date)
├── source_url (officiella avtals-PDF:n)
├── meta (JSON): semesterdagar, övertidsersättning %, tjänstepension %,
│         min-höjning_per_år %, ob-tillägg, sjuklön-trappa
└── summary_md (kort pedagogisk text för UI:n)

ProfessionAgreement (länkar yrke → avtal)
├── id, profession (sträng-nyckel som matchar profile_fixtures.py)
├── agreement_id → CollectiveAgreement.id (NULL = "småföretag utan avtal")
├── pension_rate_pct (default tas från avtal, men kan overridea)
└── notes (varför just detta avtal)

EmployerSatisfaction (per elev, levande siffra)
├── id, student_id (master-DB, eftersom yrket lever på master-nivå)
├── score (0–100, default 70)
├── updated_at, last_event_at
└── trend ("rising"|"falling"|"stable") — beräknas från senaste 5 events
```

Plus en event-logg så lärare kan spåra varför scoren rör sig:

```
EmployerSatisfactionEvent
├── id, student_id, ts
├── kind ("vab", "sick", "question_answered", "late", "manual_teacher")
├── delta_score (kan vara negativ)
├── reason_md (pedagogisk förklaring som visas i UI:n)
└── meta (JSON: vilken fråga, vilket svar, antal sjuk-dagar etc.)
```

Varför master-DB och inte scope-DB för satisfaction: eleven ÄR samma
person mot sin arbetsgivare oavsett vilken klassrums-DB hon ligger i.
Plus läraren behöver tvärsnitt över hela klassen utan att öppna varje
scope.

### 1.2 Påverkanskällor

Alla deltas är pedagogiskt motiverade och dokumenterade i `reason_md`.

| Händelse | Default-delta | Kollektivavtal-modifierare |
|---|---|---|
| Sjukanmälan dag 1–7 | 0 | OK enligt SjukLL — påverkar ej |
| Sjukanmälan dag 8+ utan läkarintyg | −5 | Avtal kräver intyg |
| VAB-dag (max 60/år) | 0 | Lagstadgad rätt |
| VAB-dag över 60/år | −3 | Får inte ersättning, chef noterar |
| För sen ankomst (slumpas) | −2 | Vanligt missnöje |
| Slumpad fråga: bra svar | +2 till +5 | Visar engagemang |
| Slumpad fråga: dåligt svar | −2 till −5 | Visar bristande omdöme |
| Lärare-korrigering (manuellt) | ±valfritt | För edge-case |

### 1.3 Slumpade frågor

En `WorkplaceQuestion`-tabell (master-DB) med ~30–50 seedade frågor:

```
WorkplaceQuestion
├── id, scenario_md (situationen, t.ex. "Kollegan glömmer kort
│   och du måste ta hens skift")
├── options (JSON: 3–4 alternativ, varje med ett delta)
├── correct_path_md (varför det "bra" svaret är pedagogiskt rätt)
└── tags (JSON: ["lojalitet", "rakryggad", "konflikt", ...])
```

UI: en notification-pop-up i Sidebar (likt befintliga `StudentEvent`)
en gång per simulerad arbetsvecka, med rate-limit max 1 per dygn.
Frågan kan skjutas upp en gång — om eleven ignorerar den helt räknas
det som "−1 visat lite engagemang".

### 1.4 Pedagogiskt UI

Ny vy `/workplace` (eller integrerad i `/dashboard`-elev-kort):
- Stor satisfaction-mätare (radial chart, 0–100)
- Trend de senaste 30 dagarna
- Lista över senaste 10 events med klickbar `reason_md`
- Knapp "Visa kollektivavtal" → modal med `summary_md` + länk till PDF
- Tjänstepensionssats per månad (kr) med koppling vidare till
  pensions-modulen (förberedelse — pension-modulen byggs senare)

Lärar-vy `/teacher/students/:id` får ett satisfaction-kort:
- Aktuellt värde + trend
- Eventlogg (samma som elev ser, plus möjlighet att lägga till
  manuell delta med motivering)

### 1.5 Kursmodul

En ny systemmodul "Arbete och avtal" seedas via `module_seed.py` med
6 steg:

1. `read` — Vad är ett kollektivavtal, varför har vi dem
2. `task` — "Slå upp ditt yrkes avtal" (öppnar `/workplace`)
3. `quiz` — 4 frågor om sjukanmälan, VAB, semester
4. `read` — Tjänstepension: vad är ITP1, SAF-LO, KAP-KL, AKAP-KR
5. `reflect` — "Hur skulle du agera om en kollega bad dig täcka för
   den?" (öppen reflektion)
6. `task` — Svara på 3 workplace-frågor i ditt egna flöde

### 1.6 Avtals-data — varifrån

Officiella avtal finns publicerade fritt:
- IF Metall: industrins kollektivavtal
- Unionen + Sveriges Ingenjörer: tjänstemannaavtalet
- Kommunal: HÖK kommun/region
- Vision + Vårdförbundet: vårdpersonal
- Handels: detaljhandeln
- HRF: hotell- och restaurangbranschen
- Småföretag utan avtal: "fri lönesättning, ingen tjänstepension,
  semesterlagen 25 dagar minimum" — pedagogiskt intressant kontrast

För V1 räcker 6–8 avtal som täcker våra 17 yrken. Resten markeras
"avtal saknas". Avtals-summary skrivs av oss som en faktagranskad
lättläst version (~300–400 ord per avtal) med länk till officiella PDF
för djupdykning.

### 1.7 Risker

- **Faktariktighet**: avtals-uppgifter måste stämma. Bygg en process
  där varje `summary_md` granskas av en faktaläsare (kanske facket
  själv). Versionera via `valid_from`/`valid_to` så förändringar
  spåras. UI:n visar "Senast verifierat: 2026-XX-XX".
- **Övertramp i frågor**: slumpade frågor måste vara åldersanpassade.
  Inga frågor om alkohol, droger, sex på arbetsplatsen. Politiska
  frågor undviks helt.
- **Score-spelifiering**: vi vill INTE att eleven jagar poäng. UI:n
  framhåller resonemanget i `reason_md` mer än siffran. Score är ett
  trubbigt sammanfattningsmått — texten är lärandet.
- **Notification fatigue**: max 1 fråga/dygn, kan stängas av per
  modul, lärare kan pausa hela klassen.

### 1.8 Insats (uppskattning)

- Backend: 4 nya tabeller + migrations + seed (8 avtal, 30 frågor) + 6
  endpoints + event-listener för sjuk/VAB-koppling: ~12–16 h
- Frontend: `/workplace`-vy + lärarkort + question-popup + module:
  ~10–14 h
- Faktagranskning av avtals-texter: extern, ~4–6 h
- Tester: ~6 h

Totalt: ~32–42 h. Levereras i 2 PR:ar (datamodell + endpoints
först, UI sedan) så det går att testa stegvis.

---

## Idé 2 — Lönesamtal (AI-förhandling)

**Pedagogisk kärna**: lönesamtalet är skarp tillämpad förhandling som
de flesta vuxna ändå hanterar dåligt. Vi simulerar fem-rond med en
AI-arbetsgivare som har elevens hela kontext (yrke, satisfaction-score,
år i tjänst, avtals-norm) och svarar i samma logik som en riktig chef
skulle: balanserar lojalitet, marknadsläge och budget-utrymme.

Eleven lär sig:
1. Vad avtalet säger om revisionsökning detta år
2. Hur satisfaction-faktorn flyttar förhandlingsutrymmet
3. Att förbereda argument med data, inte känslor
4. Att läsa motpartens "nej" — en gräns, inte ett avslut

### 2.1 Beroenden

**Förutsätter idé 1** — utan kollektivavtal-data och satisfaction-score
blir lönesamtalet hängande i luften. Ordningen i fas-planen
respekterar detta.

### 2.2 Datamodell

Tre nya master-DB-tabeller:

```
SalaryNegotiation (en lönesamtals-session per år och elev)
├── id, student_id, profile_id (snapshot vilket yrke)
├── started_at, completed_at
├── status ("active"|"completed"|"abandoned")
├── starting_salary (Decimal — bruttolön när samtalet började)
├── final_salary (Decimal — efter alla rondar, NULL om abandoned)
├── final_pct (avtals-norm för året som referens)
├── teacher_id (vem som äger lärarsynen — Student.teacher_id-snapshot)
└── teacher_summary_md (auto-genererat efter completion: vad eleven
    argumenterade, hur AI svarade, jämförelse mot avtal)

NegotiationRound (5 rader per session)
├── id, negotiation_id, round_no (1–5)
├── student_message (vad eleven skrev)
├── employer_response (AI-svaret)
├── proposed_pct (AI:ns aktuella bud)
├── student_counter_pct (NULL om eleven inte motbjuder)
├── input_tokens, output_tokens
└── created_at

NegotiationConfig (singleton master-DB)
├── max_rounds (5, men admin-justerbar för specialfall)
├── max_input_tokens_per_round (default 800)
├── max_output_tokens_per_round (default 600)
├── model ("haiku" eller "sonnet" — vi börjar med Haiku, escalate vid behov)
└── disabled (kill-switch om kostnaderna skenar)
```

### 2.3 Tokens och kostnad

Kostnadskalkyl (Haiku 4.5):
- Input: ~$0.80/MTok
- Output: ~$4.00/MTok
- Per rond: 800 input + 600 output → ~$0.0029
- Per session (5 rondar): ~$0.015
- Per klass (30 elever × 1 session/år): ~$0.45

Acceptabelt. Använd cache_control på system-prompt så avtals-kontexten
inte räknas om varje rond. Vid skarpa kostnadsproblem: byt till Haiku
exklusivt + sänk max_output till 400.

Hård gräns per session lagras i `NegotiationConfig` — om en elev
försöker omsstarta efter att ha klarat samtalet, blockeras hen tills
nästa simulerade år. Lärare kan tvinga reset för demo.

### 2.4 AI-prompt-struktur

System-prompt (cachad):
```
Du är arbetsgivar-personen Maria, HR-chef på {employer}.
Du har precis fått {student_name} på lönesamtal. Hen är {profession}
och har varit anställd i {years} år.

Faktagrund för dig (eleven ser INTE detta direkt):
- Aktuell bruttolön: {salary} kr/mån
- Kollektivavtal: {agreement_name} → revisionsutrymme {pct}% i år
- Satisfaction-score: {score}/100 ({trend})
- Senaste 3 events: {events_summary}

Dina principer:
- Du är generös men inom ramen — kan ge ±2 procentenheter över
  avtals-norm vid hög satisfaction; ±1 under vid låg.
- Du bemöter argumentet, inte personen.
- Du säger ALDRIG vad avtalet sätter — eleven ska själv hänvisa.
- Om eleven ger sakliga argument (marknadsdata, prestation, ny
  kompetens) → flyttar du dig 0.5–1 pp.
- Du avslutar varje rond med ett konkret bud i procent.
- Max 150 ord per svar. Ingen emoji. Ingen rubriker-markdown.
```

User-prompt per rond: bara elevens senaste meddelande + "Detta är
rond X av 5".

### 2.5 Flöde i UI

Ny vy `/salary-negotiation` (eller `/lonesamtal`):

1. **Briefing-sida**: visar elevens nuvarande lön, satisfaction,
   avtalets förhandlingsutrymme, tips på argument. Stor "Starta
   samtal"-knapp.
2. **Samtals-läge**: chat-UI likt /chat men med en räknare "Rond 2
   av 5" och AI:ns nuvarande bud framträdande till höger.
3. **Avslut-sida**: efter rond 5 (eller om eleven trycker "acceptera"):
   - Slutbud i % och kr
   - Jämförelse mot avtals-norm: "Du fick 3.2 %, avtalet säger 2.5 %
     — bra jobbat" / "Du fick 1.8 %, avtalet säger 2.5 % — du gick
     med på under norm"
   - 3–5 punkter feedback från AI ("Bra: du nämnde marknadsdata.
     Förbättring: du angav en hög siffra utan att backa upp")
   - Knapp "Visa kollektivavtalet" → modal från idé 1
4. **Effekt**: `StudentProfile.gross_salary_monthly` uppdateras
   omedelbart. Lönespec nästa månad reflekterar nya beloppet.

### 2.6 Lärar-vy

`/teacher/students/:id/negotiations`:
- Lista över alla negotiations (en per år)
- Klick på en → full transkript + final_pct vs avtal
- Filter: "elever som hamnade under avtalsnivå" (pedagogisk
  varningsflagga)
- Klass-aggregat: snitt-pct, varians, "antal som accepterade rond 1"

### 2.7 Kursmodul

Bygger ovanpå "Arbete och avtal" från idé 1, ny modul "Förhandla din
lön":

1. `read` — Vad är ett lönesamtal, varför har vi det
2. `read` — Lönerevisionsutrymme: hur fungerar det i ditt avtal
3. `task` — Förbered 3 argument inför ditt samtal (skrivuppgift)
4. `task` — Genomför lönesamtalet (kopplat till `/lonesamtal`)
5. `reflect` — "Vad gick bra? Vad skulle du göra annorlunda?"
6. `quiz` — 4 frågor om förhandlingstaktik och avtalsläsning

### 2.8 Risker

- **AI-bias**: modellen kan vara slappare/strängare än verkligheten.
  Mitigering: kalibrera mot satisfaction + avtal i system-prompten,
  testa med 50 sessioner i staging och mäta delta_pct-fördelning.
- **Eleven gamear**: skriver "ge mig 50 % annars säger jag upp mig".
  Lägg in guardrail i system-prompt: "om eleven hotar säga upp sig
  utan plan, säg lugnt 'det vore tråkigt, men beslutet är ditt' och
  håll ditt bud".
- **Token-skena**: sätt hård quota per elev per år (1 lyckad
  session). Kvotmotor kan återanvända `Teacher.ai_chat_daily_quota`-
  mönstret men på årsnivå istället.
- **Pedagogisk låsning**: om eleven gör ett dåligt samtal — kan hen
  "ångra"? Nej i V1: lärdomen är att lönen man förhandlar är den man
  får. Lärare kan dock manuellt resetta via lärar-vyn för demo.
- **Verbositet**: max 150 ord i AI-svar är hårt. Annars äter elev-läs
  upp tiden.

### 2.9 Insats (uppskattning)

- Backend: 3 nya tabeller + migrations + 6 endpoints (start, send-message,
  history, complete, list-for-teacher, force-reset) + AI-promptmodul:
  ~10–12 h
- Frontend: 3 vyer (briefing, chat, summary) + lärarvy + module: ~12–14 h
- Calibrering: 50-session-test i staging för att tuna delta-regler: ~4 h
- Tester: ~5 h

Totalt: ~31–35 h. Levereras i 1 PR efter idé 1 är ute, eftersom
beroendet är hårt.

---

## Idé 3 — Banken (ny undersida + BankID-flöde + signering)

**Pedagogisk kärna**: i verkligheten flyttas inte pengar i en
budget-app — pengar flyttas i banken, med BankID, med saldo-kontroll,
med konsekvenser. Vår nuvarande "kontoutdrag-PDF i Dina dokument →
import"-flöde är ett pedagogiskt steg ifrån vekligheten. Banken-vyn
slår igen det glappet:

- Eleven loggar in i "banken" som en separat sak
- Hen ser kontoutdrag direkt där (inte som en PDF att ladda ner)
- Hen exporterar kontoutdrag → de hamnar i bokföringen (`/transactions`)
- Hen exporterar kommande fakturor → signerar betalning + datum
- Saldo-kontroll vid signering → måste flytta fakturan om det inte täcker
- Sen betalning → påminnelse → påverkar kreditbedömning

Det här är där "ekonomi blir verklig" — inte en formell labb.

### 3.1 Stort flödesschema

```
   ┌──────────────┐                ┌──────────────┐
   │  Banken      │                │  /transactions│
   │  (ny vy)     │  ── export ──► │  (befintlig)  │
   └──────┬───────┘                └──────────────┘
          │
          ▼
   ┌──────────────┐                ┌──────────────┐
   │  /upcoming   │  ── signera ─► │ ScheduledPay │
   │  (befintlig) │                │ (ny tabell)   │
   └──────────────┘                └──────┬───────┘
                                          │
                       ┌──────────────────┼──────────────────┐
                       ▼                  ▼                  ▼
                  betalas i tid    saldo saknas       sen betalning
                       │                  │                  │
                       ▼                  ▼                  ▼
                  Transaction      blockera + flytta   PaymentReminder
                                                       (artifact + delta)
```

### 3.2 BankID-simulering

I verkligheten BankID = nyckelpar på telefon + biometri + bankens
identitetsserver. Vi bygger en pedagogisk approximation:

**Desktop-flödet**:
1. Eleven trycker "Logga in i banken" på `/bank`
2. UI:t visar en QR-kod (genererad från en `BankSession`-token)
3. Eleven öppnar mobilen (eller en sekundär tab) och går till
   `/bank/sign?token=...` — där matar hen in sitt EkonomilabbetID
   (samma som student-koden, omdöpt i UI:n) och ett 4-siffrigt
   PIN
4. Server matchar: BankSession.confirmed=True
5. Desktop pollar var 2:a sekund, ser confirmation, släpper in eleven

**Mobil-flödet** (eleven redan på mobilen):
- Direkt PIN-inmatning utan QR

Datamodell:
```
BankSession (master-DB)
├── id, student_id, token (UUID), pin_hash
├── created_at, expires_at (15 min)
├── confirmed_at, ip_address
└── purpose ("login" | "sign_payment_batch:<id>" | "loan_application")
```

PIN-koden är 4 siffror, hashad med bcrypt. Sätts vid första inloggning
(onboarding-steg som ber eleven välja). Lagras `Student.bank_pin_hash`
i master-DB. Eleven kan resetta via lärare.

**Pedagogiskt**: visa elever att riktiga BankID är säkrare än vår
simulering, men logiken är likadan — något du har (telefon/QR) +
något du vet (PIN/biometri).

### 3.3 Kontoutdrag — flytta från Dina dokument till Banken

Idag genererar `teacher/batch.py` ett kontoutdrag-PDF som blir en
`BatchArtifact`. Eleven importerar manuellt under `/my-batches`.

Nytt flöde:
1. Vid generering: kontoutdraget skapas fortfarande som
   `BatchArtifact(kind="kontoutdrag")` — INGEN ändring i batch-koden
   för att inte bryta lärarens befintliga vy
2. Banken-vyn listar de senaste kontoutdragen via en ny endpoint
   `/bank/statements` som hämtar dessa artifacts
3. Eleven trycker "Exportera till bokföringen" — backend kör samma
   `import_artifact()` som /my-batches gör. Stat: importerad=True
4. Eleven kan ALDRIG importera samma kontoutdrag två gånger (befintlig
   idempotens). Knappen visas som "Redan exporterat" efter

`/my-batches` får alla utom kontoutdrag — kvar är lönespec, lånebesked
och kreditkortsfaktura (de som verkligen hör hemma i "papper i lådan").

### 3.4 Kommande betalningar — signering + execution

Nya tabeller (scope-DB):

```
ScheduledPayment (en signerad betalning)
├── id, upcoming_id (→ UpcomingTransaction.id)
├── account_id (→ Account, vilket konto pengarna dras från)
├── amount (Decimal — kopia, för spårbarhet)
├── scheduled_date
├── signed_at, signed_via_session_id (→ BankSession)
├── status ("scheduled"|"executed"|"failed_no_funds"|"rescheduled"|"cancelled")
├── executed_transaction_id (→ Transaction, sätts vid execution)
└── failure_reason (TEXT, NULL om OK)

PaymentReminder (genereras vid sen betalning)
├── id, upcoming_id, scheduled_payment_id
├── reminder_no (1, 2, 3 — ökar)
├── issued_date
├── late_fee (Decimal — accumuleras: 60kr, 120kr, 180kr)
├── artifact_id (→ BatchArtifact, PDF som hamnar i Dina dokument)
└── settled_at (NULL om obetalt, sätts när elev sen betalar)
```

**Signerings-flöde**:
1. På `/bank/upcoming` ser eleven alla `UpcomingTransaction(kind=bill)`
   som inte är matchade och inte redan har en `ScheduledPayment`
2. Hen markerar 1 eller flera, väljer datum + konto, trycker "Signera"
3. BankID-flödet öppnas (`BankSession.purpose="sign_payment_batch:<n>"`)
4. När bekräftat: backend skapar `ScheduledPayment`-rader

**Execution-flöde** (jobb som körs varje natt):
- För varje `ScheduledPayment(status="scheduled", scheduled_date<=today)`:
  - Kolla saldo på `account_id`
  - Tillräckligt → skapa `Transaction`, sätt status="executed",
    matcha `UpcomingTransaction`
  - Otillräckligt → status="failed_no_funds", trigga reminder-flödet
    om förfallodatum passerat

Implementation av "varje natt"-jobb: i lokal/desktop-app är det
on-demand vid pageload. I Cloud Run kör vi en endpoint
`/internal/run-scheduled-payments` (skyddad med shared secret) som
Cloud Scheduler triggar 06:00 europe-stockholm.

### 3.5 Påminnelse-flödet

När en faktura inte betalas i tid:

1. **Dag 0** (förfallodatum + 5 dagar buffer): genererar
   `PaymentReminder(reminder_no=1, late_fee=60)`. PDF:en hamnar i
   `/my-batches` (eller `/attachments`) som artifact. Eleven får en
   notifikation.
2. **Dag 14**: reminder_no=2, late_fee=120. Ny PDF.
3. **Dag 30**: reminder_no=3, late_fee=180 + meddelande "ärendet kan
   skickas till inkasso".
4. **Dag 45**: påminnelse går till "Kronofogden" (simulerat) →
   markant negativ delta på kreditbedömning.

`late_fee` läggs till som extra `UpcomingTransaction(kind=bill,
source="reminder")` som eleven måste signera separat.

### 3.6 Kreditbedömning-koppling

Idag: `CreditApplication`-flödet använder hårdkodade regler för
godkännande. Med banken kommer en faktisk historik att finnas.

Ny tabell (master-DB):
```
CreditScoreSnapshot (per elev, senast räknat)
├── id, student_id, computed_at
├── score (300–850 likt UC men eget skala-namn "EkonomiSkalan")
├── factors (JSON: {late_payments: 3, reschedules: 1, debt_ratio: 0.4,
│           savings_buffer_months: 1.5, satisfaction: 72, age_at_account: 18})
├── grade ("A+"|"A"|"B"|"C"|"D")
└── reasons_md (pedagogisk text per factor med vad det betyder)
```

Beräknas automatiskt vid varje `PaymentReminder.issued`-event och vid
varje `CreditApplication.submitted`. Visa eleven på `/bank/credit-score`
så hen ser hur sina vanor förändrar siffran.

`CreditApplication`-handläggning byter regel: använd `CreditScoreSnapshot.
score` istället för rule-baserad summa-koll.

### 3.7 UI på `/bank`

Vy-struktur:

```
/bank                    → Inloggning (BankID-flöde) eller dashboard
/bank/dashboard          → Saldo per konto, senaste 5 transaktioner,
                           kommande betalningar (5 närmaste), CTA till
                           kontoutdrag
/bank/statements         → Kontoutdrag-PDF:er + Exportera-knapp
/bank/upcoming           → Lista över obetalda fakturor + signera
/bank/scheduled          → Mina signerade betalningar (status, datum)
/bank/loan-application   → Låneansökan (befintlig logik, flyttad hit)
/bank/credit-score       → EkonomiSkalan + förklaring
```

Vyn ska kännas annorlunda än resten av appen — banker har en mer
formell/safe-vibe. Använd en separat färgton (mörkblå header, vit
yta), markera "Du är inloggad i banken" tydligt, sessionstid räknas
ner.

### 3.8 Kursmodul

Ny modul "Banken — så funkar pengaflöden":

1. `read` — Vad är ett kontoutdrag, hur läser jag rader
2. `task` — Exportera ditt senaste kontoutdrag till bokföringen
3. `read` — Signering, BankID, varför man inte ska ge bort PIN
4. `task` — Signera dina kommande fakturor i banken
5. `quiz` — 4 frågor om saldokontroll, sen betalning, kreditbedömning
6. `reflect` — "En faktura passerar förfallodatum — vad gör du?"

### 3.9 Risker

- **Ökad kognitiv belastning**: två platser (banken + bokföringen)
  istället för en. Mitigering: tydliga CTA:er, t.ex. på `/dashboard`
  ett stort kort "3 fakturor väntar på signering — gå till banken".
- **Eleven glömmer signera**: alla fakturor blir sena. Mitigering:
  notifikation på Dashboard + Sidebar-badge för osignerade fakturor.
- **PIN-glömska**: lärare måste kunna resetta. Lärare-knapp på
  /teacher/students/:id "Återställ bank-PIN" → tvingar elev sätta ny
  vid nästa inlogg.
- **QR-koden funkar inte i mobiles utan kamera**: fallback "Logga in
  med kod" → eleven läser av en 6-siffrig kod på desktop och knappar
  in på mobilen. Räknas som "second factor" pedagogiskt.
- **Cloud Scheduler-kostnad**: en ping per dygn → försumbart.
- **Race condition vid signering**: två elever på samma familje-DB
  signerar samma faktura. Lägg unique-constraint på
  `(upcoming_id, status="scheduled")` så bara en kan vara aktiv.
- **Saldo vid signering vs vid execution**: en faktura signeras med
  täckning idag, men eleven hinner spendera bort det innan
  scheduled_date. Då fail:as betalningen. Pedagogiskt: visa eleven
  vid signering "OBS — du har 800 kr kvar efter denna betalning",
  inte "förbjudet att signera om saldo blir under 500 kr".

### 3.10 Insats (uppskattning)

Stor. Bästa att splittas i tre delar:

**3a — BankID + bank-skelett** (stor):
- BankSession-tabell + endpoints + QR-flow + PIN-onboarding
- /bank/dashboard + login-vyn
- ~16–20 h

**3b — Kontoutdrag + signering** (stor):
- ScheduledPayment-tabell + endpoints + execution-jobb
- /bank/statements + /bank/upcoming + /bank/scheduled
- Cloud Scheduler-integration
- Migrering: ta bort kontoutdrag från /my-batches
- ~20–24 h

**3c — Påminnelser + kreditbedömning** (medel):
- PaymentReminder + CreditScoreSnapshot + scoring-funktion
- PDF-mall för påminnelser
- /bank/credit-score
- Kursmodul-seedning
- ~14–18 h

Totalt: ~50–62 h. Levereras i 3 PR:ar — varje del fungerar i sig
själv så testning kan ske stegvis.

---

## Idé 4 — Bank-features konsoliderade

Den här är inte en separat feature utan en sammanfattning av vad
`/bank` ska innehålla — i sin helhet, alla från idé 3:

- **Kontoutdrag** (3.3): lista över historiska perioder, exportera
  till `/transactions`
- **Kommande betalningar** (3.4): obetalda fakturor, signering,
  status på schemalagda
- **Låneansökan** (existerande, flyttas): `/loans` blir kvar för
  befintliga lån; ansökan-formuläret flyttas till `/bank/loan-application`
  så hela "behöver låna pengar"-flödet sker inne i banken
- **EkonomiSkalan** (3.6): kreditbetyg + faktor-förklaring

**Migrationsfråga**: ska vi ta bort `/loans`-vyn helt och flytta in
allt i `/bank`? Mitt råd: NEJ, behåll `/loans` som "min lånebok"
(visar pågående lån, betalningsplan, tidsplan), och låt `/bank`
hantera ansökan + ny-lån. Det matchar verkligheten: banken är där du
går när du behöver låna; din egen översikt är något separat.

---
