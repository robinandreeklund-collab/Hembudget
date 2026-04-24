# CLAUDE.md

Guidelines and context for Claude Code when working on this repo. Det här är
en levande instruktion — uppdatera vid arkitekturförändringar så nästa
session slipper återupptäcka samma saker.

## Projektet

**Ekonomilabbet** (skolläge) och **Hembudget** (desktop-läge) delar samma
kodbas. Samma FastAPI-backend + React/TS-frontend; vilket läge som körs
styrs av env-vars.

- `HEMBUDGET_SCHOOL_MODE=1` → Ekonomilabbet. Lärare + elever, multi-tenant
  SQLite per elev/familj, seed av 12 systemkompetenser + "Din första
  månad"-modul vid startup. Bootstrap-läraren blir super-admin.
- `HEMBUDGET_DEMO_MODE=1` → öppet demo utan inloggning (auto-seed från
  `data/`).
- Inget satt → desktop-läge (Tauri + krypterad SQLite, master-password).

Publik produktionsinstans: https://ekonomilabbet.org (Cloud Run,
`europe-north1`, `--max-instances=1` — SQLite delas inte över instanser).

## Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.x, SQLite (+ SQLCipher på
  desktop), reportlab, anthropic-SDK, matplotlib, pandas.
- **Frontend:** React 18 + TypeScript 5, Vite 5, TailwindCSS, react-router,
  recharts, lucide-react.
- **Deploy:** Google Cloud Run via `deploy.sh` (Cloud Build, ingen lokal
  Docker krävs). Persistens via GCS-fuse på `/mnt/school-data`.
- **LLM:** Claude (Anthropic SDK, Haiku 4.5 + Sonnet 4.6) för skolfunktioner;
  LM Studio (Nemotron Nano 3) för desktop-AI.

## Arkitekturnycklar (måste förstås innan du ändrar)

- **Multi-tenant scope:** Skolläget använder en `ContextVar` satt av
  `StudentScopeMiddleware` i `main.py` — scope-nyckeln är `s_<id>` för solo-
  elever och `f_<id>` för familjemedlemmar. `session_scope()` i `db/base.py`
  läser ContextVar:n och öppnar rätt SQLite-fil under `data/school/students/`.
  **FastAPI Depends körs i threadpool med kopierad context**, så ContextVar
  måste sättas i middleware, inte i en dep.
- **Master-DB migrationer:** `MasterBase.metadata.create_all()` lägger inte
  till kolumner på befintliga tabeller. När `Teacher`/`Family`/`Student` får
  nya fält → lägg till ALTER TABLE i `school/engines.py::_run_master_migrations`.
  Per-scope-DB använder `db/migrate.py::run_migrations` som körs via
  `get_scope_engine`.
- **Roller:** `teacher` (email+lösen), `student` (6-teckenskod), `demo`
  (ephemeral). Super-admin = `teachers.is_super_admin=True` (bootstrap-lärare
  får det automatiskt).
- **AI-gating:** Alla `/ai/*`-endpoints kräver att lärarkontots
  `ai_enabled=True` AND att `ANTHROPIC_API_KEY` finns. Eleven räknas mot sin
  lärares token-konto. Om något saknas → 503, inte 500.
- **Rate limiting:** In-memory sliding window i
  `security/rate_limit.py`. Funkar bara med `--max-instances=1`; om
  skalning införs måste detta flyttas till Redis.

## Arbetsprinciper (icke-förhandlingsbara)

Dessa är instruktioner från ägaren till den här kodbasen.

1. **Bugs fixas alltid** — även om de inte hör till den PR/uppgift du håller
   på med. Om du ser ett fel, åtgärda det och commita separat med tydligt
   meddelande. Lämna aldrig en känd bug efter dig.
2. **Inga genvägar.** Ingen `--no-verify`, ingen `# type: ignore` utan
   kommentar, ingen catch-all `except:` som sväljer fel, ingen mock där en
   riktig implementation krävs, ingen "TODO: fix later" istället för att
   fixa. Hittar du rotsorsaken — fixa rotsorsaken.
3. **Allt testas.** Ny backend-kod → `pytest`-test. Ny endpoint → åtminstone
   ett happy-path-test + ett 4xx-test. Ny frontend-komponent → manuell
   verifiering i browser (start dev-servern och klicka) + `npx tsc --noEmit`.
   Om du inte kan testa något, säg det i commit-meddelandet — ljug inte.
4. **Migrationer är idempotenta** och körs på varje uppstart. Skriv dem så
   att de kan köras hundra gånger utan effekt.
5. **Svenska i UI, svenska i kommentarer, engelska i kodidentifierare.**
   Matchar kodbasens nuvarande stil.

## Kör och testa

```bash
# Backend tests (måste alla passera innan commit)
cd backend && python -m pytest tests/ -x -q

# Frontend typecheck + build
cd frontend && npx tsc --noEmit && npx vite build

# Backend lokalt (school-läge)
cd backend && HEMBUDGET_SCHOOL_MODE=1 HEMBUDGET_DATA_DIR=/tmp/hb \
    python -m hembudget.main --host 127.0.0.1 --port 8765

# Frontend lokalt
cd frontend && npm run dev

# Deploy till Cloud Run
./deploy.sh
```

Backend-tester tar ~90 s. Om ett test failar, fixa; hoppa inte över det.

## Env-vars (produktion)

Sätta via Cloud Run — använd `--update-env-vars`/`--update-secrets`, aldrig
`--set-env-vars` (som raderar allt).

| Variabel | Vad | Krav |
|---|---|---|
| `HEMBUDGET_SCHOOL_MODE` | `1` för Ekonomilabbet | alltid i prod |
| `HEMBUDGET_SERVE_STATIC` | `1` för att serva `frontend/dist` från samma container | alltid i prod |
| `HEMBUDGET_DATA_DIR` | Persistens-mount (typ `/mnt/school-data`) | alltid i prod |
| `HEMBUDGET_BOOTSTRAP_SECRET` | Skyddar första lärarregistreringen | alltid |
| `HEMBUDGET_BOOTSTRAP_TEACHER_EMAIL`/`_PASSWORD`/`_NAME` | Auto-skapa första läraren | valfritt |
| `ANTHROPIC_API_KEY` | Aktiverar `/ai/*`-endpoints | valfritt — utan = AI tyst av |
| `TURNSTILE_SITE_KEY` | Publik Cloudflare Turnstile-nyckel | valfritt |
| `TURNSTILE_SECRET` | Privat Turnstile-nyckel | valfritt — utan = bot-check off |
| `HEMBUDGET_SMTP_HOST` | SMTP-server (Gmail: `smtp.gmail.com`) | krävs för signup + reset |
| `HEMBUDGET_SMTP_PORT` | SMTP-port (587 STARTTLS, 465 SSL) | default 587 |
| `HEMBUDGET_SMTP_USER` | SMTP-användare (`info@ekonomilabbet.org`) | krävs om SMTP på |
| `HEMBUDGET_SMTP_PASSWORD` | Gmail **app password** (16 tecken) — sätts som Cloud Run-secret | krävs om SMTP på |
| `HEMBUDGET_SMTP_STARTTLS` | STARTTLS på 587 (default `true`) | valfritt |
| `HEMBUDGET_MAIL_FROM` | Avsändar-mail (`info@ekonomilabbet.org`) | krävs om SMTP på |
| `HEMBUDGET_MAIL_FROM_NAME` | Visningsnamn (default `Ekonomilabbet`) | valfritt |
| `HEMBUDGET_PUBLIC_BASE_URL` | URL som används i mail-länkar (`https://ekonomilabbet.org`) | rekommenderas — utan byggs länkarna från requesten |

**Sätta Gmail-lösenordet som secret första gången:**
```bash
# Skapa secret i Secret Manager
printf "dinAppPassword16teck" | gcloud secrets create hembudget-smtp-password \
  --data-file=- --project=hembudget
# Ge Cloud Run-SA åtkomst
gcloud secrets add-iam-policy-binding hembudget-smtp-password \
  --member="serviceAccount:$(gcloud projects describe hembudget \
    --format='value(projectNumber)')-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" --project=hembudget
# Peka in till Cloud Run
gcloud run services update hembudget-demo --region=europe-north1 \
  --update-secrets=HEMBUDGET_SMTP_PASSWORD=hembudget-smtp-password:latest
```
Gmail kräver ett *app password* (google.com → Säkerhet → 2-stegs → App-lösenord). Normalt Gmail-lösen funkar INTE via SMTP.

## Kataloger

```
backend/hembudget/
  api/           # FastAPI-routers (en fil per domän)
  school/        # Multi-tenant scope, ai-klient, demo-seed, moduler
  security/      # Crypto, audit, rate_limit (Turnstile + IP-buckets)
  db/            # Base, session_scope, per-scope migrations
  teacher/       # PDF-generering (lönespec, kontoutdrag, portfolio)
  categorize/    # Kategoriserings-regelmotor + LLM-bakfall
  parsers/       # CSV/XLSX/PDF-import
  llm/           # LM Studio-klient (desktop-AI, inte Claude)

frontend/src/
  pages/         # Route-nivå (Teacher, StudentDetail, ModuleView, osv.)
  components/    # Sidebar, AskAI, Turnstile, MasteryChart …
  hooks/useAuth  # Token + school-status + impersonation
  api/client     # fetch-wrapper, hanterar 401/403 + Turnstile-header
```

## Återkommande gotchas

- Tar du bort en `.tsx`-fil? Kolla `App.tsx` så routen inte är kvar.
- Ny env-var → lägg den i CLAUDE.md-tabellen ovan OCH i `deploy.sh`.
- Ny Teacher-kolumn → lägg till ALTER TABLE i `_run_master_migrations`.
- Frontend-build varnar om chunks >500 kB — ignorera, har varnat länge och
  är inget problem för Cloud Run.
- `on_event("startup")` ger deprecation-warning — OK att låta ligga tills
  hela startup-logiken bryts ut i lifespan.
