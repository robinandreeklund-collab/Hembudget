#!/usr/bin/env bash
# entrypoint.sh — startar PgBouncer (om Cloud SQL-config finns) + uvicorn.
#
# Cloud Run kör en process per container men accepterar att den processen
# är en wrapper som spawnar barn-processer. Vi kör PgBouncer i bakgrund +
# uvicorn i förgrund. Om uvicorn dör går containern ner (Cloud Run
# startar om). Om PgBouncer dör (oväntat) kör vi den igen utan att ta
# ner appen — den läser av sig själv vid varje query.
#
# PgBouncer enabled bara när HEMBUDGET_DATABASE_URL pekar på Cloud SQL
# (postgresql://...host=/cloudsql/...). I lokal SQLite-mode kör vi bara
# uvicorn direkt.

set -uo pipefail

# PgBouncer är OPT-IN. Tidigare default-på-vid-cloudsql visade sig
# spränga Cloud SQL conn-cap (login-500 i prod) — antingen för att
# PgBouncer inte startade rent, eller för att dess egna server-conn
# adderades på toppen av appens. Tills vi har kunnat debugga
# beteendet säkert kör vi direct-connect till Cloud SQL.
#
# Återaktivera per-revision via:
#   gcloud run services update hembudget --region=europe-west1 \
#     --update-env-vars=HEMBUDGET_ENABLE_PGBOUNCER=1
PGBOUNCER_ENABLED=0
if [[ "${HEMBUDGET_ENABLE_PGBOUNCER:-0}" == "1" ]] \
   && [[ -n "${HEMBUDGET_DATABASE_URL:-}" ]] \
   && [[ "${HEMBUDGET_DATABASE_URL}" == *"cloudsql"* ]]; then
    PGBOUNCER_ENABLED=1
fi

if [[ "${PGBOUNCER_ENABLED}" == "1" ]]; then
    echo "[entrypoint] Cloud SQL detekterat → startar PgBouncer som connection-multiplexer"

    # Parsea HEMBUDGET_DATABASE_URL för att extrahera komponenter:
    # postgresql://USER:PASS@/DB?host=/cloudsql/CONN
    PG_URL="${HEMBUDGET_DATABASE_URL}"

    # Extrahera user, password, db-namn, host
    DB_USER=$(echo "${PG_URL}" | sed -E 's|postgresql://([^:]+):.*|\1|')
    DB_PASSWORD=$(echo "${PG_URL}" | sed -E 's|postgresql://[^:]+:([^@]+)@.*|\1|')
    DB_NAME=$(echo "${PG_URL}" | sed -E 's|.*@/([^?]+).*|\1|')
    DB_HOST=$(echo "${PG_URL}" | sed -E 's|.*host=([^&]+).*|\1|')
    DB_PORT="5432"

    DB_PASSWORD_RAW=$(printf '%b' "${DB_PASSWORD//%/\\x}")

    # Pool-storlek per Cloud Run-instans · konfigurerbar via env så
    # admin kan justera när Cloud SQL bumpas till större tier utan
    # kod-deploy.
    #
    # Riktlinje:
    #   db-f1-micro (25 conn)         → 6
    #   db-g1-small (50 conn)         → 12
    #   db-custom-1-3840 (100 conn)   → 25
    #   db-custom-2-7680 (200 conn)   → 50
    #
    # Total = N_INSTANCES × PGBOUNCER_POOL_SIZE + Postgres-internal (5-10)
    # Måste hållas under Cloud SQL-cap.
    PGB_POOL_SIZE="${PGBOUNCER_POOL_SIZE:-8}"
    PGB_MAX_CLIENT="${PGBOUNCER_MAX_CLIENT_CONN:-200}"

    # Skriv pgbouncer.ini med substituerade värden + dynamisk pool-storlek
    sed \
        -e "s|__DB_HOST__|${DB_HOST}|g" \
        -e "s|__DB_PORT__|${DB_PORT}|g" \
        -e "s|__DB_NAME__|${DB_NAME}|g" \
        -e "s|__DB_USER__|${DB_USER}|g" \
        -e "s|__DB_PASSWORD__|${DB_PASSWORD_RAW}|g" \
        -e "s|^default_pool_size = .*|default_pool_size = ${PGB_POOL_SIZE}|" \
        -e "s|^max_client_conn = .*|max_client_conn = ${PGB_MAX_CLIENT}|" \
        -e "s|pool_size=8|pool_size=${PGB_POOL_SIZE}|" \
        /etc/pgbouncer/pgbouncer.template.ini \
        > /tmp/pgbouncer.ini

    echo "[entrypoint] PgBouncer pool_size=${PGB_POOL_SIZE} max_client=${PGB_MAX_CLIENT}"

    # Skriv userlist · format: "username" "password"
    printf '"%s" "%s"\n' "${DB_USER}" "${DB_PASSWORD_RAW}" \
        > /tmp/pgbouncer-userlist.txt
    chmod 600 /tmp/pgbouncer-userlist.txt

    # Starta PgBouncer i bakgrunden. -d daemon-flagga undviker eftersom
    # vi vill ha den som child-proc av entrypoint så Cloud Run-loggar
    # ser stdout.
    pgbouncer /tmp/pgbouncer.ini &
    PGBOUNCER_PID=$!
    echo "[entrypoint] PgBouncer startad · PID=${PGBOUNCER_PID}"

    # Probe TCP localhost:6432 tills PgBouncer accepterar connections.
    # Tidigare 'sleep 1' lät uvicorn starta även om pgbouncer dog
    # direkt (config-fel, auth-fel, port redan tagen) — appen kraschade
    # då på första query och Cloud Run-loggen blev förvirrande.
    # Nu: max ~10s vänt + tydligt fel om pgbouncer inte kommer upp.
    PGB_READY=0
    for i in $(seq 1 20); do
        # Verifiera först att processen lever — annars är det meningslöst
        # att probe:a porten.
        if ! kill -0 "${PGBOUNCER_PID}" 2>/dev/null; then
            echo "[entrypoint] FATAL: PgBouncer-processen (PID=${PGBOUNCER_PID}) dog under start"
            wait "${PGBOUNCER_PID}" 2>/dev/null || true
            exit 1
        fi
        # bash /dev/tcp · 2>/dev/null sväljer "Connection refused"-skräp.
        if (echo > /dev/tcp/127.0.0.1/6432) 2>/dev/null; then
            PGB_READY=1
            echo "[entrypoint] PgBouncer redo efter ${i} probe(s)"
            break
        fi
        sleep 0.5
    done
    if [[ "${PGB_READY}" != "1" ]]; then
        echo "[entrypoint] FATAL: PgBouncer band inte 127.0.0.1:6432 inom 10s"
        kill "${PGBOUNCER_PID}" 2>/dev/null || true
        exit 1
    fi

    # Skriv om HEMBUDGET_DATABASE_URL så appen ansluter mot PgBouncer
    # (TCP localhost:6432) istället för direkt mot Cloud SQL.
    export HEMBUDGET_DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@127.0.0.1:6432/${DB_NAME}"
    echo "[entrypoint] App pekar nu på localhost:6432 (PgBouncer)"
else
    if [[ -n "${HEMBUDGET_DATABASE_URL:-}" \
          && "${HEMBUDGET_DATABASE_URL}" == *"cloudsql"* ]]; then
        echo "[entrypoint] PgBouncer disabled (HEMBUDGET_ENABLE_PGBOUNCER!=1) → direct-connect till Cloud SQL"
    else
        echo "[entrypoint] Ingen Cloud SQL detekterat → kör utan PgBouncer"
    fi
fi

# Starta uvicorn i förgrund (Cloud Run förväntar sig PID 1 = appen).
exec python -m hembudget.main --host 0.0.0.0 --port "${PORT:-8080}"
