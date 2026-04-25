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
    storage.googleapis.com \
    --quiet
ok "API:er aktiva"

# ----- 5. Deploy -----
# MODE: "school" (default, lärare/elev-läge med multi-tenant-DB:er) eller
# "demo" (öppet demo-läge utan inloggning). Styrs via env-var
# MODE=demo ./deploy.sh om du vill tillbaka till öppet demoläge.
MODE="${MODE:-school}"

if [[ "$MODE" == "school" ]]; then
    # Skol-läge kräver:
    #   - max-instances 1 (SQLite-filer per elev delas inte mellan instanser)
    #   - bootstrap-secret (skyddar första lärarregistreringen)
    #   - ev. bootstrap-teacher (email+password) för automatisk skapelse vid start
    BOOTSTRAP_SECRET="${BOOTSTRAP_SECRET:-$(openssl rand -hex 16)}"
    TEACHER_EMAIL="${TEACHER_EMAIL:-}"
    TEACHER_PASSWORD="${TEACHER_PASSWORD:-}"
    TEACHER_NAME="${TEACHER_NAME:-Lärare}"

    # PERSIST: "cloudsql" (default — Cloud SQL Postgres, riktigt
    #             managed med backup + point-in-time-restore)
    #          "ephemeral" (utveckling/testning — data försvinner)
    #
    # OBS: GCS-fuse-volymen togs bort — SQLite + GCS-fuse är ett
    # antimönster (POSIX-låsning stöds inte → korrupta skrivningar
    # och förlorad data). Vi lagrar därför allt i Postgres istället.
    PERSIST="${PERSIST:-cloudsql}"
    # /tmp används för throw-away-data (uploads-cache osv) — DB:n
    # ligger i Cloud SQL.
    DATA_DIR="/tmp/hembudget"

    CLOUDSQL_INSTANCE_CONN=""
    DATABASE_URL=""

    if [[ "$PERSIST" == "cloudsql" ]]; then
        DB_INSTANCE="${DB_INSTANCE:-hembudget-pg}"
        DB_NAME="${DB_NAME:-hembudget}"
        DB_USER="${DB_USER:-hembudget}"
        DB_TIER="${DB_TIER:-db-f1-micro}"

        info "Persistens: Cloud SQL Postgres ($DB_INSTANCE / $DB_NAME)"

        # Aktivera SQL-API om inte redan på
        gcloud services enable sqladmin.googleapis.com \
            --project="$PROJECT_ID" --quiet 2>/dev/null || true

        # Skapa instansen om den inte finns. db-f1-micro är gratis-
        # tier-kompatibel för testning. För prod bumpa till db-g1-small
        # eller större via DB_TIER=db-g1-small ./deploy.sh.
        if ! gcloud sql instances describe "$DB_INSTANCE" \
                --project="$PROJECT_ID" >/dev/null 2>&1; then
            info "Skapar Cloud SQL-instans $DB_INSTANCE ($DB_TIER) — tar 5-10 min…"
            gcloud sql instances create "$DB_INSTANCE" \
                --project="$PROJECT_ID" \
                --database-version=POSTGRES_15 \
                --tier="$DB_TIER" \
                --region="$REGION" \
                --backup-start-time=03:00 \
                --enable-point-in-time-recovery \
                --storage-auto-increase \
                --quiet
        else
            ok "Cloud SQL-instans $DB_INSTANCE finns"
        fi

        # Skapa databas om saknas
        if ! gcloud sql databases describe "$DB_NAME" \
                --instance="$DB_INSTANCE" --project="$PROJECT_ID" \
                >/dev/null 2>&1; then
            info "Skapar databas $DB_NAME"
            gcloud sql databases create "$DB_NAME" \
                --instance="$DB_INSTANCE" --project="$PROJECT_ID" \
                --quiet
        fi

        # Skapa app-user om saknas. Lösen ligger i Secret Manager —
        # genereras nytt om hemligheten saknas, återanvänds annars.
        if ! gcloud secrets describe hembudget-db-password \
                --project="$PROJECT_ID" >/dev/null 2>&1; then
            info "Skapar Secret hembudget-db-password"
            DB_PASSWORD="$(openssl rand -base64 32)"
            printf "%s" "$DB_PASSWORD" | gcloud secrets create \
                hembudget-db-password \
                --data-file=- --project="$PROJECT_ID" --quiet
        else
            DB_PASSWORD="$(gcloud secrets versions access latest \
                --secret=hembudget-db-password --project="$PROJECT_ID")"
        fi

        # Skapa user (idempotent — set-password fungerar både för
        # ny och befintlig user)
        if ! gcloud sql users list --instance="$DB_INSTANCE" \
                --project="$PROJECT_ID" --format='value(name)' \
                | grep -q "^${DB_USER}$"; then
            info "Skapar DB-user $DB_USER"
            gcloud sql users create "$DB_USER" \
                --instance="$DB_INSTANCE" --project="$PROJECT_ID" \
                --password="$DB_PASSWORD" --quiet
        else
            gcloud sql users set-password "$DB_USER" \
                --instance="$DB_INSTANCE" --project="$PROJECT_ID" \
                --password="$DB_PASSWORD" --quiet
        fi

        # Ge Cloud Run-SA åtkomst till hemligheten (idempotent)
        SA_EMAIL=$(gcloud iam service-accounts list \
            --project="$PROJECT_ID" \
            --filter="displayName:Default compute service account" \
            --format='value(email)' 2>/dev/null | head -1)
        if [[ -n "$SA_EMAIL" ]]; then
            gcloud secrets add-iam-policy-binding hembudget-db-password \
                --member="serviceAccount:${SA_EMAIL}" \
                --role="roles/secretmanager.secretAccessor" \
                --project="$PROJECT_ID" --quiet 2>/dev/null || true
            gcloud projects add-iam-policy-binding "$PROJECT_ID" \
                --member="serviceAccount:${SA_EMAIL}" \
                --role="roles/cloudsql.client" \
                --quiet 2>/dev/null || true
        fi

        CLOUDSQL_INSTANCE_CONN="${PROJECT_ID}:${REGION}:${DB_INSTANCE}"
        # Cloud Run-Postgres-via-unix-socket-URL (proxy går automatiskt
        # via --add-cloudsql-instances)
        DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${CLOUDSQL_INSTANCE_CONN}"
        ok "Cloud SQL klar: $CLOUDSQL_INSTANCE_CONN"
    else
        warn "Persistens: ephemeral — data försvinner vid container-restart!"
    fi

    ENV_VARS="HEMBUDGET_SCHOOL_MODE=1"
    ENV_VARS+=",HEMBUDGET_SERVE_STATIC=1"
    ENV_VARS+=",HEMBUDGET_HOST=0.0.0.0"
    ENV_VARS+=",HEMBUDGET_DATA_DIR=${DATA_DIR}"
    ENV_VARS+=",HEMBUDGET_LM_STUDIO_BASE_URL=http://disabled.invalid:1234/v1"
    ENV_VARS+=",HEMBUDGET_BOOTSTRAP_SECRET=$BOOTSTRAP_SECRET"
    if [[ -n "$DATABASE_URL" ]]; then
        # OBS: lösenord står i URL:en — vi sätter den som Cloud Run-secret
        # nedan i stället för --update-env-vars för att inte hamna i
        # `gcloud run revisions describe` plain-text.
        SECRET_NAME="hembudget-database-url"
        if ! gcloud secrets describe "$SECRET_NAME" \
                --project="$PROJECT_ID" >/dev/null 2>&1; then
            printf "%s" "$DATABASE_URL" | gcloud secrets create \
                "$SECRET_NAME" --data-file=- \
                --project="$PROJECT_ID" --quiet
        else
            printf "%s" "$DATABASE_URL" | gcloud secrets versions add \
                "$SECRET_NAME" --data-file=- \
                --project="$PROJECT_ID" --quiet
        fi
        if [[ -n "$SA_EMAIL" ]]; then
            gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
                --member="serviceAccount:${SA_EMAIL}" \
                --role="roles/secretmanager.secretAccessor" \
                --project="$PROJECT_ID" --quiet 2>/dev/null || true
        fi
    fi
    # SMTP för verifierings- och reset-mail. Host/port/user sätts här;
    # lösenordet ska ligga som Cloud Run-secret (HEMBUDGET_SMTP_PASSWORD)
    # och pekas in med --update-secrets. Se SMTP_*-sektionen i CLAUDE.md.
    ENV_VARS+=",HEMBUDGET_SMTP_HOST=smtp.gmail.com"
    ENV_VARS+=",HEMBUDGET_SMTP_PORT=587"
    ENV_VARS+=",HEMBUDGET_SMTP_USER=info@ekonomilabbet.org"
    ENV_VARS+=",HEMBUDGET_MAIL_FROM=info@ekonomilabbet.org"
    ENV_VARS+=",HEMBUDGET_MAIL_FROM_NAME=Ekonomilabbet"
    ENV_VARS+=",HEMBUDGET_PUBLIC_BASE_URL=https://ekonomilabbet.org"
    if [[ -n "$TEACHER_EMAIL" && -n "$TEACHER_PASSWORD" ]]; then
        ENV_VARS+=",HEMBUDGET_BOOTSTRAP_TEACHER_EMAIL=$TEACHER_EMAIL"
        ENV_VARS+=",HEMBUDGET_BOOTSTRAP_TEACHER_PASSWORD=$TEACHER_PASSWORD"
        ENV_VARS+=",HEMBUDGET_BOOTSTRAP_TEACHER_NAME=$TEACHER_NAME"
    fi

    # Skol-läge låser till 1 instans — SQLite-filer delas inte över instanser
    MAX_INSTANCES=1
    MIN_INSTANCES=1

    info "MODE=school: lärare/elev-läge aktiveras"
    info "  Bootstrap-kod: $BOOTSTRAP_SECRET (spara den — behövs för första lärarinlog)"
    if [[ -n "$TEACHER_EMAIL" ]]; then
        info "  Bootstrap-lärare: $TEACHER_EMAIL (skapas automatiskt vid första start)"
    fi
else
    ENV_VARS="HEMBUDGET_DEMO_MODE=1"
    ENV_VARS+=",HEMBUDGET_SERVE_STATIC=1"
    ENV_VARS+=",HEMBUDGET_HOST=0.0.0.0"
    ENV_VARS+=",HEMBUDGET_DATA_DIR=/tmp/hembudget"
    ENV_VARS+=",HEMBUDGET_LM_STUDIO_BASE_URL=http://disabled.invalid:1234/v1"
fi

echo
info "Startar bygge + deploy. Detta tar 3-5 minuter…"
info "  Service : $SERVICE_NAME"
info "  Region  : $REGION"
info "  Läge    : $MODE"
info "  Minne   : $MEMORY   CPU: $CPU"
info "  Instans : $MIN_INSTANCES - $MAX_INSTANCES  (auto-skalning)"
echo

DEPLOY_ARGS=(
    --source . --region "$REGION" --platform managed
    --allow-unauthenticated
    --memory "$MEMORY" --cpu "$CPU"
    --concurrency "$CONCURRENCY" --timeout "$TIMEOUT"
    --max-instances "$MAX_INSTANCES" --min-instances "$MIN_INSTANCES"
    # --update-env-vars (inte --set-env-vars) — bevarar manuellt satta
    # variabler som ANTHROPIC_API_KEY och TURNSTILE_SECRET över deploys.
    # --set hade raderat allt som inte står i $ENV_VARS.
    --update-env-vars "$ENV_VARS"
    --port 8080
    --quiet
)

# Cloud SQL: koppla in Postgres-instansen + injicera DATABASE_URL
# som secret så lösenordet inte hamnar i revisionsbeskrivningen
if [[ "$MODE" == "school" && -n "$CLOUDSQL_INSTANCE_CONN" ]]; then
    DEPLOY_ARGS+=(
        --add-cloudsql-instances="$CLOUDSQL_INSTANCE_CONN"
        --update-secrets="HEMBUDGET_DATABASE_URL=hembudget-database-url:latest"
    )
fi

gcloud run deploy "$SERVICE_NAME" "${DEPLOY_ARGS[@]}"

# ----- 6. Visa URL -----
echo
URL="$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)')"
echo
printf "%b\n" "${C_BOLD}${C_GREEN}✓ Deploy klart!${C_RESET}"
printf "%b\n" "${C_BOLD}Publik URL:${C_RESET} ${C_BLUE}$URL${C_RESET}"
echo
if [[ "$MODE" == "school" ]]; then
    echo "Skol-läge aktivt. Logga in som lärare på URL:en ovan."
    echo "Bootstrap-kod (för första lärarregistrering): $BOOTSTRAP_SECRET"
    if [[ "$PERSIST" == "gcs" ]]; then
        echo "Persistens: gs://$BUCKET_NAME (data överlever container-restart)"
    else
        echo "Persistens: ephemeral (/tmp) — data resetas vid restart"
    fi
else
    echo "Dela med eleverna. Appen är i demo-läge (ingen inloggning, öppet)."
    echo "OBS: /tmp/hembudget är ephemeral — data resetas när instansen startar om."
fi
echo
echo "Uppdatera:        ./deploy.sh"
echo "Se loggar:        gcloud run services logs read $SERVICE_NAME --region $REGION --limit 50"
echo "Radera deployen:  gcloud run services delete $SERVICE_NAME --region $REGION"
