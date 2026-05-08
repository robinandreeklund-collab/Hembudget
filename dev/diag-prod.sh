#!/usr/bin/env bash
# Kör mot prod för att se EXAKT vad som händer i Cloud SQL just nu.
# Visar: aktiva revisioner, pool-status, alla connections per
# application_name (= vi ser om gamla revisioner spöker), oldest
# connection age, total connections vs Cloud SQL max.
#
# Usage:  ./dev/diag-prod.sh [prod-base-url]
#
# Ex:     ./dev/diag-prod.sh
#         ./dev/diag-prod.sh https://ekonomilabbet.org
set -euo pipefail

URL="${1:-https://ekonomilabbet.org}"

echo "=== Cloud Run service describe ==="
gcloud run services describe hembudget --region=europe-west1 \
    --format='value(
      spec.template.spec.containers[0].resources.limits.memory,
      spec.template.spec.containerConcurrency,
      status.traffic[].revisionName,
      status.traffic[].percent
    )' 2>/dev/null || echo "(gcloud kunde inte beskriva service — har du auth?)"
echo

echo "=== Senaste 5 revisioner ==="
gcloud run revisions list --service=hembudget --region=europe-west1 \
    --limit=5 --format='table(name,creationTimestamp,active)' 2>/dev/null \
    || echo "(gcloud-fel)"
echo

echo "=== /healthz/db (pool + pg_stat_activity) ==="
echo "URL: ${URL}/healthz/db"
echo
curl -s -m 15 "${URL}/healthz/db" | python3 -m json.tool 2>/dev/null \
    || echo "(svar kunde inte parsas som JSON — ev. timeout)"
echo

echo "=== 10 parallella healthz/db för att se pool under load ==="
for i in $(seq 1 10); do
    (curl -s -m 12 -w "[%{http_code}] %{time_total}s\n" \
         -o /dev/null "${URL}/healthz/db" &)
done
wait
echo

echo "=== Senaste 50 fel från Cloud Logging (om gcloud auth) ==="
gcloud logging read \
    'resource.type=cloud_run_revision
     resource.labels.service_name=hembudget
     severity>=ERROR' \
    --limit=20 --format='value(timestamp,textPayload,jsonPayload.message)' \
    2>/dev/null | head -60 || echo "(gcloud logging miss — auth?)"
