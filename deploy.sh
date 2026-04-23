#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy.sh — Automatisk deploy av Hembudget-demo till Google Cloud Run.
#
# Vad skriptet gör:
#   1. Verifierar att gcloud CLI finns
#   2. Kollar att du är inloggad (annars: gcloud auth login)
#   3. Hämtar/frågar efter GCP-projekt-ID
#   4. Aktiverar nödvändiga API:er (Cloud Run, Cloud Build, Artifact Registry)
#   5. Bygger Docker-imagen via Cloud Build och deployar till Cloud Run
#   6. Printar den publika URL:en
#
# Kör: ./deploy.sh
# Eller: PROJECT_ID=mitt-projekt REGION=europe-north1 ./deploy.sh
# ---------------------------------------------------------------------------

set -euo pipefail

# ----- Konfiguration (kan åsidosättas via env) -----
SERVICE_NAME="${SERVICE_NAME:-hembudget-demo}"
REGION="${REGION:-europe-north1}"
# Default-projekt — används automatiskt om ingen PROJECT_ID är satt och
# gcloud config saknar projekt. Överstyrs via env: PROJECT_ID=xxx ./deploy.sh
DEFAULT_PROJECT_ID="${DEFAULT_PROJECT_ID:-hembudget}"
MEMORY="${MEMORY:-1Gi}"
CPU="${CPU:-1}"
CONCURRENCY="${CONCURRENCY:-40}"
TIMEOUT="${TIMEOUT:-300}"
MAX_INSTANCES="${MAX_INSTANCES:-5}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"

# ----- Färger för output -----
C_RESET=$'\033[0m'
C_GREEN=$'\033[0;32m'
C_YELLOW=$'\033[0;33m'
C_RED=$'\033[0;31m'
C_BLUE=$'\033[0;34m'
C_BOLD=$'\033[1m'

info()  { printf "%b\n" "${C_BLUE}→${C_RESET} $*"; }
ok()    { printf "%b\n" "${C_GREEN}✓${C_RESET} $*"; }
warn()  { printf "%b\n" "${C_YELLOW}!${C_RESET} $*"; }
err()   { printf "%b\n" "${C_RED}✗${C_RESET} $*" >&2; }

cd "$(dirname "$0")"

printf "%b\n" "${C_BOLD}${C_BLUE}Hembudget → Google Cloud Run (demo-läge)${C_RESET}"
echo

# ----- 1. gcloud CLI -----
if ! command -v gcloud >/dev/null 2>&1; then
    err "gcloud CLI hittades inte."
    echo "Installera från https://cloud.google.com/sdk/docs/install"
    echo "På macOS: brew install --cask google-cloud-sdk"
    echo "På Linux: curl https://sdk.cloud.google.com | bash"
    exit 1
fi
ok "gcloud CLI hittad: $(gcloud --version | head -1)"

# ----- 2. Autentisering -----
ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1 || true)"
if [[ -z "$ACTIVE_ACCOUNT" ]]; then
    warn "Ingen aktiv gcloud-session hittad. Öppnar inloggning…"
    gcloud auth login --update-adc
    ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -1)"
fi
ok "Inloggad som: $ACTIVE_ACCOUNT"

# ----- 3. Project-ID -----
# Prioritetsordning:
#   1. PROJECT_ID via miljövariabel
#   2. gcloud config get-value project (aktivt projekt)
#   3. DEFAULT_PROJECT_ID ("hembudget") — verifieras att det existerar
#   4. Om inget fungerar: interaktiv prompt (bara om stdin är tty)
if [[ -z "${PROJECT_ID:-}" ]]; then
    PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
    # Försök default-projektet om det existerar på kontot
    if gcloud projects describe "$DEFAULT_PROJECT_ID" >/dev/null 2>&1; then
        PROJECT_ID="$DEFAULT_PROJECT_ID"
        ok "Använder default-projekt: $PROJECT_ID"
    elif [[ -t 0 ]]; then
        echo
        warn "Inget GCP-projekt valt (default '$DEFAULT_PROJECT_ID' hittades inte)."
        echo "Tillgängliga projekt på ditt konto:"
        gcloud projects list --format="table(projectId, name, projectNumber)" || true
        echo
        read -r -p "Ange PROJECT_ID (eller tryck enter för att skapa nytt): " PROJECT_ID
        if [[ -z "$PROJECT_ID" ]]; then
            DEFAULT_NEW="hembudget-$(date +%s | tail -c 7)"
            read -r -p "Nytt projekt-ID [$DEFAULT_NEW]: " NEW_ID
            PROJECT_ID="${NEW_ID:-$DEFAULT_NEW}"
            info "Skapar projekt $PROJECT_ID…"
            gcloud projects create "$PROJECT_ID"
            echo
            warn "Nytt projekt skapat. Du MÅSTE koppla ett billing-konto till det"
            warn "innan Cloud Run kan användas (gratis-tier räcker för demo):"
            echo "  → https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID"
            read -r -p "Tryck enter när billing är kopplat… "
        fi
    else
        err "Inget projekt satt och ingen tty för interaktiv prompt."
        err "Kör om med: PROJECT_ID=<ditt-projekt> ./deploy.sh"
        exit 1
    fi
fi

info "Sätter aktivt projekt till $PROJECT_ID"
gcloud config set project "$PROJECT_ID" >/dev/null
ok "Projekt: $PROJECT_ID"

# ----- 4. API:er -----
info "Aktiverar nödvändiga Google Cloud API:er (tar ~30 s första gången)…"
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    --quiet
ok "API:er aktiva"

# ----- 5. Deploy -----
echo
info "Startar bygge + deploy. Detta tar 3-5 minuter…"
info "  Service : $SERVICE_NAME"
info "  Region  : $REGION"
info "  Minne   : $MEMORY   CPU: $CPU"
info "  Instans : $MIN_INSTANCES - $MAX_INSTANCES  (auto-skalning)"
echo

gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --memory "$MEMORY" \
    --cpu "$CPU" \
    --concurrency "$CONCURRENCY" \
    --timeout "$TIMEOUT" \
    --max-instances "$MAX_INSTANCES" \
    --min-instances "$MIN_INSTANCES" \
    --set-env-vars "HEMBUDGET_DEMO_MODE=1,HEMBUDGET_SERVE_STATIC=1,HEMBUDGET_HOST=0.0.0.0,HEMBUDGET_DATA_DIR=/tmp/hembudget,HEMBUDGET_LM_STUDIO_BASE_URL=http://disabled.invalid:1234/v1" \
    --port 8080 \
    --quiet

# ----- 6. Visa URL -----
echo
URL="$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)')"
echo
printf "%b\n" "${C_BOLD}${C_GREEN}✓ Deploy klart!${C_RESET}"
printf "%b\n" "${C_BOLD}Publik URL:${C_RESET} ${C_BLUE}$URL${C_RESET}"
echo
echo "Dela med eleverna. Appen är i demo-läge (ingen inloggning, öppet)."
echo "Ephemeral databas — data resetas när Cloud Run-instansen startar om."
echo
echo "Uppdatera:        ./deploy.sh"
echo "Se loggar:        gcloud run services logs read $SERVICE_NAME --region $REGION --limit 50"
echo "Radera deployen:  gcloud run services delete $SERVICE_NAME --region $REGION"
