# Ekonomilabbet & Hembudget

> **Pengar är ett medel för välmående, inte ett mål i sig själv.**
>
> Att maximera saldot till priset av sociala band och fritid är inte ekonomisk framgång — det är en form av fattigdom. Att spendera allt på upplevelser utan buffert är heller inte rikedom — det är skörhet.
>
> Ekonomi är konsten att balansera idag mot imorgon, mig själv mot mina relationer, planering mot spontanitet.

En **pedagogisk redovisningsplattform** för privatekonomi — byggd för
klassrummet, köksbordet och (på sikt) hela familjens riktiga ekonomi.
Allt på samma kodbas, samma motor, samma datamodell.

## Vad är detta?

Ekonomilabbet är ett *redovisningssystem* (huvudbok, kontoplan,
balansräkning, kategorisering) och en *livssimulator* — på samma
gång. Där traditionella budget-appar bara räknar pengar, försöker
det här systemet göra något annat: **lära elever och unga vuxna att
ekonomi är ett verktyg för att leva ett gott liv, inte en poängjakt**.

Systemet körs i tre lägen, alla från samma kodbas:

| Läge | För | Aktivering |
|---|---|---|
| **Ekonomilabbet** (skola) | Lärare + elever, multi-tenant | `HEMBUDGET_SCHOOL_MODE=1` |
| **Familjekonto** (hemma) | Föräldrar + barn, samma vy som lärare | Signup via `/signup/parent` |
| **Hembudget** (desktop) | En vuxen, riktig ekonomi, krypterad lokalt | Tauri-appen, master-lösenord |

Publik produktionsinstans: **https://ekonomilabbet.org**

## Pedagogisk filosofi

Den centrala mätaren är inte kontosaldot — det är **Wellbeing Score**, ett
sammansatt välmående-värde 0–100 över fem dimensioner:

| Dimension | Vad den mäter |
|---|---|
| **Ekonomi** | Saldo, sparande, skuldkvot, högkostnadskredit |
| **Mat & hälsa** | Budget vs Konsumentverkets minimibelopp |
| **Sociala band** | Accepterade vs nekade events, klasskompis-relationer |
| **Fritid & balans** | Variation över kategorier, aktivitet senaste 30 dagar |
| **Trygghet** | Buffert, försäkring, hur oförutsedda kostnader hanteras |

En elev som har 80 000 kr på sparkontot men nekar varje socialt event
landar på Wellbeing 60 — inte 85. En elev som spenderar allt på
upplevelser utan buffert kan landa på Wellbeing 50 trots full
livsglädje. **Plattformen mäter den balansen, inte saldot.**

Visualiserat som en pentagon-radar på Dashboard, med transparenta
faktorer: *"Sociala band sjönk 8 p eftersom du nekade 4 av 4 förslag.
Budget för mat är 1 200 kr — under Konsumentverkets 2 840 kr — så
Mat & hälsa drabbas. Du tog ett SMS-lån, ekonomin sjönk 20 p."*

## Tre målgrupper, samma plattform

### 🏫 För skolan

- Bjud in en hel klass via 6-tecken-koder eller QR-kod — ingen e-post per elev krävs
- Tilldela samma modul till alla, eller skräddarsy per elev
- Mastery-graf visar var klassen fastnar
- **Wellbeing-klassöversikt** med rödflaggor (`social_low`, `economy_critical`, `decline_streak_high`...) så läraren ser vem hen behöver fråga *"hur har du det?"*
- Portfolio-PDF per elev eller hela klassen som ZIP — bedömningsunderlag
- AI-coachen (Sokratisk Claude) anpassar svaret efter elevens nivå

### 🏠 För hemmet

- Skapa konton för dina barn på två minuter
- Varje barn får en egen sandlåda — riktiga pengar är aldrig inblandade
- Du följer samma vy som läraren har: vad har barnet gjort, var har hen fastnat, vad har hen frågat AI:n
- Modulerna täcker kontoutdrag, bolån, kreditkort, sparande, bjudningar, aktier, kreditbeslut

### 🚀 För familjens riktiga ekonomi (kommer 2026)

- Anslut bankkonton, kreditkort och lån via Tink (PSD2)
- Ladda upp era fakturor — vi läser av förbrukning, datum och belopp
- Bygg månadsbudget för kommande period — automatisk huvudbok med debet/kredit
- Fråga AI-coachen: *"Vad spenderade vi mest på i mars?"*

## Vad systemet faktiskt gör (komplett bild)

Det här är inte bara en budget-app. Det är **ett redovisningssystem
med en livssimulator ovanpå**, där varje elev får en unik värld med
verkliga pedagogiska konsekvenser.

### Redovisningsmotorn

- **Kontoplan & transaktioner**: lönekonto, sparkonto, kreditkort, ISK, depå. Saldo räknas live från transaktioner.
- **Kategoriseringsmotor**: regelbaserad + LLM-fallback, Konsumentverkets 2026-siffror som referens
- **Budgetering** med live-validering mot Konsumentverket: sätt 1 200 kr för mat → varning + lägre Wellbeing→Hälsa
- **Överföringar mellan egna konton** med proaktivt flöde — sparkonto/ISK/pension blockeras från att gå minus
- **Kommande räkningar** (Upcoming) med autogiro-matching och Swish-skuld från klasskompis-bjudningar
- **Lån** (bolån, billån, studielån, privatlån, SMS-lån) med ränta, amortering och bindningstid
- **PDF-import** (kontoutdrag, lönespec, lånebesked, kreditkortsfaktura) + lärar-PDF-generering så elever importerar sin egen data
- **Bankavstämning** för Företagsekonomi 2-fördjupning

### Livssimulatorn (gamification)

- **78 event-mallar** från verkligheten: bio på Filmstaden, AIK-Hammarby på Tele2 Arena, julbord på Operaterrassen, tandläkare akut, mormors 80-årskalas, Stockholm Marathon...
- **Trigger-engine** som drar 0–3 events per vecka per elev, deterministiskt seedat (samma elev + samma vecka = samma events)
- **Acceptera/neka med konsekvens**: kostnad bokförs som transaktion, Wellbeing per dimension uppdateras, decline-streak räknas
- **Klasskompis-bjudningar** med tre kostnadsmodeller (50/50, pro-rata, allt-delas) + Swish-skuld i Upcoming-listan
- **Klassgemensamma events** ("Klassresan till Berlin") — läraren skapar, distribueras till alla elever på en knapptryckning
- **PersonalityQuiz** vid onboarding (introvert/extrovert, thrill-seeker, familje-orienterad) — påverkar event-mix

### "Veil of ignorance"-onboarding för sambo-profiler

När en elev får en sambo-profil måste hen välja fördelningsmodell
för hushållskostnader (50/50 / pro-rata / allt-delas) **innan**
partnerns lön avslöjas. Detta är ett ärligt etiskt val (Rawls 1971),
inte ett rationellt självoptimerings-val. Efter beslutet visas en
reflektionsbanner som binder ihop matematiken med värderingarna —
*"Du valde pro-rata och tjänar mer. Det innebär att DU bär en större
del — men båda får samma marginal kvar att leva på. Det är ett moget val."*

### Aktiehandel (pedagogisk simulator)

- **30 svenska large-caps** (OMXS30) med kursdata var 5:e minut
- **Finnhub** som primär datakälla (gratis 60 req/min) eller yfinance som fallback — sätts via super-admin-UI
- **Avanza Mini-courtage** (1 kr min, 0,25 % över ~400 kr)
- **Append-only ledger** med `quote_id`-länk till exakt kursdata vid affären (revisionsspår)
- **Stockholmsbörsen-kalender** med svenska helgdagar inklusive påskberäkning
- **Pedagogisk modul** "Aktier — komma igång": öppna ISK → flytta pengar dit → riskspridd köp av 5 aktier över 3 sektorer
- AI-funktioner som **förklarar termer** men aldrig rekommenderar köp/sälj

### Kreditflöde med pedagogisk gradering

- **Affordability-check** vid varje uttag: räcker saldot?
- Om nej → **modal "Din ekonomi går inte ihop"** med tre val: privatlån (kreditupplysning) / SMS-lån (sista utväg) / avbryt
- **Simulerad kreditscore** 300–850 med 6 transparenta faktorer (inkomst, skuldkvot, sparkonto-buffert, nyligt lånetagande, tidigare avslag, lånebelopp vs inkomst)
- Eleven ser **exakt vilken faktor** som gav vilken poäng — kan inte cheata, kan inte gissa
- SMS-lån är **medvetet enkelt att få** (det är poängen) men varnings-UX är tydligt: röd banner, effektiv ränta 80–200 %, pedagogisk reflektionsfråga efter
- **CreditApplication-tabell** som audit-spår för läraren — alla kreditförsök loggas, även avslag och elev-rejected
- Lärarvy med rödflaggor för `is_high_cost_credit=True`-lån

### AI-integration (Claude Sonnet/Haiku, opt-in per lärare)

- **Sokratisk princip**: AI frågar mer än den svarar. Aldrig "rekommendera" — bara hjälpa eleven se mönster
- **Månadsreflektion** baserat på Wellbeing-snapshoten
- **Decline-streak-nudge** vid 3+ nej i rad
- **Klasskompis-invite-motivation** (neutral kommentar, både sidor)
- **Ekonomisk Q&A** — eleven frågar "vad är ränta-på-ränta?", AI svarar med Sokratisk metod på elevens mastery-nivå
- **Token-räkning per lärare** för kostnadskontroll
- Stöder **Anthropic Claude Haiku 4.5** (lättvikt) och **Sonnet 4.6** (nyanserat)

### Lärarvyer

| Sökväg | Vad |
|---|---|
| `/teacher` | Översikt, klass-status, alla elever |
| `/teacher/wellbeing` | Wellbeing per elev med 6 rödflagg-typer |
| `/teacher/credit` | Kredit-historik per elev |
| `/teacher/investments` | Aktieportföljer + ledger-drilldown |
| `/teacher/reflections` | Alla reflektionssvar med rubric |
| `/teacher/all-batches` | Genererade månadsdokument |
| `/teacher/modules` | Skapa egna moduler eller klona systemmallar |

### Super-admin (3-stegs opt-in för integritet)

- Per-lärar-toggles för klassdisplay (anonymiserad rangordning, visa namn, klasskompis-bjudningar, kostnadsmodell)
- Anthropic + Finnhub API-nycklar via UI (sparas i master-DB, bytbara utan redeploy)
- AI-aktivering per lärare (gate som hindrar slumpmässiga Anthropic-kostnader)
- Cost_split_decided_at sparas alltid — elevens *första* ärliga val bevaras även om hen ändrar senare

## Pedagogiska systemmoduler (seedade vid uppstart)

| Modul | Innehåll |
|---|---|
| Din första månad | Lön, skatt, budget, kontoutdrag, kategorisering |
| Kontoutdraget — vart tog pengarna vägen? | Import + AI-bedömd kategorisering |
| Buffert — när livet smäller till | Buffertmål, tumregel 2-3 månadslöner |
| Första bolånet — rörlig vs bunden | Räntor, amortering, historiska data från Riksbanken |
| Kreditkort utan att gå under | Nominell/effektiv ränta, minim-fallorna |
| Att börja spara på riktigt | Sparkonto, indexfond, ränta-på-ränta över 30 år |
| Familjeekonomi — när två delar | Proportionell budget, sambolag |
| Lär känna systemet | Överföringar, kommande räkningar |
| **Aktier — komma igång** | ISK, riskspridning, courtage, peer-revision |
| **Kreditmånaden — när pengarna inte räcker** | Privatlån vs SMS-lån, kreditscore, reflektion |

## Teknisk arkitektur

### Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.x, SQLite (lokalt) + Postgres (prod via Cloud SQL), reportlab, Anthropic SDK, matplotlib, pandas, httpx
- **Frontend:** React 18 + TypeScript 5, Vite 5, TailwindCSS, react-router, recharts, lucide-react, @tanstack/react-query
- **Deploy:** Google Cloud Run via `deploy.sh` (Cloud Build, ingen lokal Docker krävs)
- **AI:** Claude (Anthropic SDK, Haiku 4.5 + Sonnet 4.6) för skolfunktioner; LM Studio (Nemotron Nano 3) för desktop-AI
- **Marknadsdata:** Finnhub.io (gratis 60 req/min) eller Yahoo Finance via yfinance som fallback
- **Mobil/desktop:** Tauri (Rust + WebView) för krypterad lokal version

### Multi-tenant-arkitektur

Skolläget använder en **ContextVar-driven scope-isolering**:

- `StudentScopeMiddleware` läser `Authorization` + `X-As-Student`-headers
- Sätter `_current_scope` ContextVar (`s_<id>` för solo-elev, `f_<id>` för familjemedlem)
- `session_scope()` öppnar rätt SQLite-fil under `data/school/students/`
- I prod: gemensam Postgres med `tenant_id`-filter på alla tabeller via `TenantMixin`

Lärar-impersonation av elev sker via `X-As-Student`-header — middleware verifierar att läraren äger eleven, sätter sedan ContextVar:n.

### Domänmoduler

```
backend/hembudget/
  api/           # FastAPI-routers (en fil per domän)
  school/        # Multi-tenant scope, AI-klient, demo-seed, moduler, events
  security/      # Crypto, audit, rate_limit (Turnstile + IP-buckets)
  db/            # Base, session_scope, per-scope migrations, modeller
  teacher/       # PDF-generering, scenario-data, batch-distribution
  categorize/    # Kategoriserings-regelmotor + LLM-bakfall
  parsers/       # CSV/XLSX/PDF-import
  llm/           # LM Studio-klient (desktop-AI, inte Claude)
  wellbeing/     # Wellbeing-Score-beräkning + Konsumentverket-validering
  events/        # Event-trigger-engine (78 event-mallar)
  credit/        # Kreditscoring + privatlån/SMS-lån-flöde
  stocks/        # Aktiekurspolling, courtage-beräkning, börstidskalender

frontend/src/
  pages/         # Route-nivå (Teacher, StudentDetail, ModuleView, Investments, ...)
  components/    # WellbeingCard, EventModal, CreditModal, HouseholdSplitQuiz, ...
  hooks/useAuth  # Token + school-status + impersonation
  api/client     # fetch-wrapper, hanterar 401/403 + Turnstile-header
  data/          # Delade datafiler (cell-info för landningssidan)
```

### Tester

- **705 backend-tester** (pytest), körs på ~4 min
- TypeScript-typecheck via `npx tsc --noEmit`
- Vite-build verifierar produktionsbundle
- CI-vänligt: alla tester använder in-memory SQLite, inga externa beroenden

## Snabbstart

### Google Cloud Run (rekommenderas för klassrum)

```bash
./deploy.sh
```

Skriptet sköter allt automatiskt:
1. Kontrollerar `gcloud` CLI och aktiv inloggning
2. Frågar efter GCP-projekt-ID
3. Aktiverar Cloud Run, Cloud Build och Artifact Registry
4. Bygger Docker-imagen i molnet — **ingen lokal Docker krävs**
5. Deployar till Cloud Run i `europe-north1`
6. Skriver ut den publika URL:en

**Loggar:** `gcloud run services logs read hembudget-demo --region europe-north1`
**Radera:** `gcloud run services delete hembudget-demo --region europe-north1`

### Utveckling lokalt

Förkrav: Python 3.11+, Node 20+, Rust (för Tauri).

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd ../frontend
npm install

# Tauri (om desktop-app)
cd ../src-tauri
cargo build
```

Kör i utvecklingsläge:

```bash
# Terminal 1 — backend (skol-läge)
cd backend && HEMBUDGET_SCHOOL_MODE=1 HEMBUDGET_DATA_DIR=/tmp/hb \
    python -m hembudget.main --host 127.0.0.1 --port 8765

# Terminal 2 — frontend
cd frontend && npm run dev   # öppna http://localhost:1420

# Backend tester (måste alla passera innan commit)
cd backend && python -m pytest tests/ -x -q

# Frontend typecheck + build
cd frontend && npx tsc --noEmit && npx vite build
```

Första gången på desktop sätter du ett master-lösenord (minst 8 tecken). Detta krypterar din databas — det går inte att återställa om du glömmer det.

## Env-vars (produktion)

| Variabel | Vad | Krav |
|---|---|---|
| `HEMBUDGET_SCHOOL_MODE` | `1` för Ekonomilabbet | alltid i prod |
| `HEMBUDGET_SERVE_STATIC` | `1` för att serva `frontend/dist` från samma container | alltid i prod |
| `HEMBUDGET_DATABASE_URL` | Cloud SQL Postgres-connection-string | krävs i prod |
| `HEMBUDGET_DATA_DIR` | Sökväg för throw-away-data (cache, uploads) | alltid i prod |
| `HEMBUDGET_BOOTSTRAP_SECRET` | Skyddar första lärarregistreringen | alltid |
| `ANTHROPIC_API_KEY` | Aktiverar `/ai/*`-endpoints — kan istället sättas via UI | valfritt |
| `FINNHUB_API_KEY` | Aktiekursdata — kan istället sättas via UI | valfritt |
| `HEMBUDGET_QUOTE_PROVIDER` | `finnhub` / `yfinance` / `mock` (auto-väljer om ej satt) | valfritt |
| `HEMBUDGET_COURTAGE_MODEL` | `mini` (default) / `start` / `none` | valfritt |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET` | Cloudflare bot-skydd | valfritt |
| `HEMBUDGET_SMTP_*` | SMTP för signup + reset-mail | krävs för signup |
| `HEMBUDGET_PUBLIC_BASE_URL` | URL i mail-länkar (`https://ekonomilabbet.org`) | rekommenderas |

**Viktigt vid Cloud Run-deploy:** använd `--update-env-vars` (additivt) istället för `--set-env-vars` (raderar allt).

## Designprinciper (icke-förhandlingsbara)

1. **Bugs fixas alltid** — även om de inte hör till den uppgift du jobbar på
2. **Inga genvägar** — ingen `--no-verify`, ingen `# type: ignore` utan kommentar, ingen catch-all-except, ingen mock där en riktig implementation krävs
3. **Allt testas** — ny endpoint = happy path + 4xx-test, ny komponent = manuell verifiering i browser
4. **Migrationer är idempotenta** — körs på varje uppstart utan effekt om redan körda
5. **Svenska i UI, svenska i kommentarer, engelska i kodidentifierare**
6. **Pedagogiskt fokus, inte spelmässigt** — inga konfetti-explosioner, ingen poängjakt utan koppling till lärande
7. **Determinism för rättvisa** — samma elev + samma vecka → samma events
8. **Konsekvenser kvarstår** — beslut idag påverkar Wellbeing nästa månad
9. **Aldrig fördömande** — AI:n säger aldrig "du gjorde fel", den säger "din relationsdimension har sjunkit. Det är OK — men varför?"
10. **3-stegs opt-in för all social funktionalitet** — super-admin, lärare, elev. Skyddar elever som inte vill jämföras

## Bidra

Det här är ett pilotprojekt med fokus på pedagogisk användning i svenska
gymnasieskolor. Buggrapporter, pedagogiska förslag och pull requests
välkomnas. Se `CLAUDE.md` för utvecklingsguidelines.

Frågor: **info@ekonomilabbet.org**
