# Hembudget

Lokal AI-driven familjeekonomiplattform. All finansdata stannar på din dator.
Drivs av en lokal LLM (Nemotron Nano 3) via [LM Studio](https://lmstudio.ai/)
och en krypterad SQLite-databas.

## 🚀 Prova direkt i browsern

### Google Cloud Run (rekommenderas för klassrum)

[![Run on Google Cloud](https://deploy.cloud.run/button.svg)](https://deploy.cloud.run/?git_repo=https://github.com/robinandreeklund-collab/Hembudget)

Ett klick ovan → Google öppnar Cloud Shell, klonar repot och kör
Dockerfile:n automatiskt. Du blir frågad om projekt + region, sen
deployar den till Cloud Run. Efter deploy är klar får du en publik URL
att skicka till eleverna.

**Alternativt — kör lokalt:**

```bash
./deploy.sh
```

Skriptet sköter allt automatiskt:
1. Kontrollerar `gcloud` CLI och aktiv inloggning
2. Frågar efter GCP-projekt-ID (eller skapar ett nytt)
3. Aktiverar Cloud Run, Cloud Build och Artifact Registry
4. Bygger Docker-imagen i molnet (Cloud Build — ingen lokal Docker krävs)
5. Deployar till Cloud Run i `europe-north1` (Finland)
6. Skriver ut den publika URL:en

Efter första deployen: kör `./deploy.sh` igen för att uppdatera. Se loggar
med `gcloud run services logs read hembudget-demo --region europe-north1`.

**Arkitektur:** en enda container servar både frontend (statisk React-build)
och backend (FastAPI) på samma port, så inga CORS-problem och en URL till
eleverna. Demo-läget auto-seedar data från `data/`-mappen vid start.

**Kostnad:** Cloud Run skalar till 0 när ingen är inne → typiskt under $1/mån
för klassbruk. Ephemeral SQLite — data återställs när containern startar om.

### Render.com (alternativ)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/robinandreeklund-collab/Hembudget)

Ett klick ovan → Render läser `render.yaml`, sätter upp backend + frontend
som separata services, startar i **demo-mode** och auto-importerar CSV/XLSX
från `data/`. Efter deploy: sätt frontendens `VITE_API_BASE` till backendens
URL och gör en re-deploy.

**Begränsningar:** ingen LM Studio (AI-chat fungerar ej, men 96 % av
kategoriseringen sker via regler). SQLite-databasen är ephemeral —
återställs vid inaktivitet, men bootstrap fyller den igen automatiskt.

## Funktioner

- 📥 **CSV-import** — Amex Eurobonus, Nordea, SEB Kort (Mastercard Eurobonus).
- 🤖 **AI-kategorisering** — regelbaserad först (svensk merchant-lista
  inbyggd), LLM-fallback för okända. Lär sig av dina rättningar.
- 📊 **Månadsbudget & dashboard** — planerat vs faktiskt, sparkvot, topp-kategorier.
- 💬 **AI-chatt** — fråga Nemotron om din ekonomi via tool-use
  (han anropar backend-funktioner för deterministisk matematik).
- 🔮 **Scenarioanalys** — bolån (FI:s amorteringskrav, ränteavdrag),
  sparmål, flytt-break-even.
- 🧾 **Svensk skatt** — ISK-schablonbeskattning, K4-kapitalvinst,
  ROT/RUT-summering med tak.
- 🔁 **Abonnemangsdetektor** — hittar återkommande dragningar.
- 📈 **Cashflow-prognos** — 6 månader framåt baserat på historik.
- 📑 **Rapport-export** — Excel och PDF per månad.
- 🔐 **SQLCipher-kryptering** — master-lösenord + Argon2id key derivation.
- 🌐 **Offline** — enda externa anropet är till `http://localhost:1234`
  (LM Studio).

## Arkitektur

```
Tauri (Rust) ──► React (Vite)
     │                │
     └── sidecar ─────┘
         FastAPI (Python)
         └── SQLCipher-krypterad SQLite
             └── LM Studio (lokalt, via OpenAI-SDK)
```

Python-backenden spawnas som sidecar av Tauri, lyssnar på lokal port,
och frontend kommunicerar via `http://127.0.0.1:<port>`.

## Förutsättningar

- **Python 3.11+**
- **Node.js 20+**
- **Rust** (för Tauri) — `rustup`
- **LM Studio** med Nemotron Nano 3 nedladdad och startad servern på
  `http://localhost:1234/v1`
- **Tesseract** (valfritt, för kvitto-OCR) — `brew install tesseract tesseract-lang`

## Första installation

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd ../frontend
npm install

# Tauri (behöver Rust)
cd ../src-tauri
cargo build
```

## Kör i utvecklingsläge

Terminal 1 — backend (manuellt):
```bash
cd backend
python -m hembudget.main --port 8765
```

Terminal 2 — frontend + Tauri:
```bash
cd frontend
echo 'VITE_API_PORT=8765' > .env.local
npm run tauri dev
```

Eller enbart webbversionen:
```bash
cd frontend && npm run dev
# öppna http://localhost:1420
```

Första gången sätter du ett master-lösenord (minst 8 tecken). Detta krypterar
din databas — det går inte att återställa om du glömmer det.

## Bygga releasebar desktop-app

```bash
# 1. Bygg Python-binären med PyInstaller
cd backend
pyinstaller --onefile --name hembudget-backend -p hembudget hembudget/main.py
# Kopiera dist/hembudget-backend* till src-tauri/binaries/hembudget-backend-<target-triple>

# 2. Bygg Tauri-appen
cd ../frontend && npm run build
cd ../src-tauri && cargo tauri build
```

Installerare hamnar i `src-tauri/target/release/bundle/`.

## Köra tester

```bash
cd backend
pytest tests/ -q          # enhetstester (18+ stycken)
pytest -m integration     # kräver körande LM Studio
```

## Projektstruktur

```
backend/hembudget/
├── parsers/          # CSV-parsers (Amex, Nordea, SEB Kort)
├── categorize/       # Regelbaserad + LLM-fallback, lär sig av rättningar
├── llm/              # LM Studio-klient (OpenAI-kompatibel)
├── budget/           # Månadssammanställning, cashflow-prognos
├── scenarios/        # Bolån, sparmål, flytt — deterministiska beräkningar
├── tax/              # ISK-schablon, K4, ROT/RUT
├── subscriptions/    # Återkommande-detektor
├── chat/             # Tool-using agent (query_transactions, calculate_scenario, …)
├── security/         # Argon2id + SQLCipher-nyckel
├── ocr/              # Kvitto-OCR (Tesseract)
└── api/              # FastAPI-routers

frontend/src/
├── pages/            # Dashboard, Transactions, Import, Budget, Chat,
│                     # Scenarios, Tax, Reports, Settings
├── components/
├── api/              # fetch-klient mot sidecar
└── hooks/

src-tauri/            # Rust shell (spawnar Python-sidecar)
```

## Säkerhet

- Databasen krypteras med **SQLCipher** (AES-256). Nyckeln härleds från ditt
  lösenord via Argon2id.
- Appens CSP tillåter bara anrop till `http://127.0.0.1:*` och
  `http://localhost:*` — ingen utgående trafik.
- Alla skrivoperationer loggas i `audit_log`-tabellen.
- **Telemetri:** 0. Ingen analytics, inga externa anrop.

## Licens

Privat familjeprojekt. Lägg till licens om det görs publikt.
