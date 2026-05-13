#!/usr/bin/env bash
# Mät tiden för alla teacher-endpoints mot prod.
# Output: tabell sorterad efter total tid → ser direkt vad som är slow.
#
# Användning:
#   1. Hämta din lärar-token från DevTools eller mobil-debugger:
#      - Öppna https://ekonomilabbet.org → logga in
#      - DevTools → Application → Local Storage → kopiera "auth_token"
#        (eller liknande nyckelnamn)
#   2. Kör:  TOKEN='din_token_här' ./dev/perf-prod.sh
#   3. Se vilka endpoints som tar > 1 s
set -euo pipefail

URL="${URL:-https://ekonomilabbet.org}"
TOKEN="${TOKEN:?Sätt TOKEN-env-var: TOKEN='Bearer xxx' ./dev/perf-prod.sh}"

# Strip ev. "Bearer " prefix om användaren inkluderade det
TOKEN="${TOKEN#Bearer }"

# Kritiska teacher-endpoints (det användaren faktiskt klickar på)
endpoints=(
  "GET /healthz"
  "GET /healthz/db"
  "GET /school/status"
  "GET /teacher/me"
  "GET /admin/ai/me"
  "GET /v2/teacher/klass-overview"
  "GET /v2/teacher/classes"
  "GET /v2/teacher/students/created"
  "GET /v2/notifications"
)

# Ta första studenten via klass-overview, lägg till student-specific endpoints
echo "Hämtar första elev från klass-overview..."
SID=$(curl -s -m 30 -H "Authorization: Bearer $TOKEN" \
  "$URL/v2/teacher/klass-overview" \
  | python3 -c 'import sys, json; d=json.load(sys.stdin); m=d.get("mini_pentagons", []); print(m[0]["student_id"] if m else "")' 2>/dev/null)

if [ -n "$SID" ]; then
  echo "  → student_id $SID hittad — testar student-specifika endpoints"
  endpoints+=(
    "GET /v2/teacher/students/$SID"
    "GET /v2/teacher/students/$SID/student-detail"
    "GET /v2/teacher/students/$SID/credit-overview"
    "GET /v2/teacher/students/$SID/employer-overview"
    "GET /v2/teacher/students/$SID/insurance-overview"
    "GET /v2/teacher/students/$SID/utility-overview"
    "GET /v2/teacher/students/$SID/pension-overview"
    "GET /v2/teacher/students/$SID/avanza-overview"
    "GET /v2/teacher/students/$SID/bokforing-overview"
    "GET /v2/teacher/students/$SID/moduler-overview"
    "GET /v2/teacher/students/$SID/tax-overview"
  )
fi

echo
echo "=== Endpoint-timing (sorterat efter Total) ==="
printf "%-50s  %8s  %8s  %4s\n" "Endpoint" "Total" "TTFB" "HTTP"

results=()
for spec in "${endpoints[@]}"; do
  method="${spec%% *}"
  path="${spec#* }"
  out=$(curl -s -o /dev/null -m 30 \
    -X "$method" \
    -H "Authorization: Bearer $TOKEN" \
    -w "%{time_total}|%{time_starttransfer}|%{http_code}" \
    "$URL$path" 2>/dev/null || echo "30.000|30.000|TIMEOUT")
  total=$(echo "$out" | cut -d'|' -f1)
  ttfb=$(echo "$out" | cut -d'|' -f2)
  code=$(echo "$out" | cut -d'|' -f3)
  results+=("$total|$ttfb|$code|$path")
done

# Sortera efter total tid (descending)
printf '%s\n' "${results[@]}" | sort -t'|' -k1 -gr | while IFS='|' read -r total ttfb code path; do
  # Färga rött om > 1s
  total_ms=$(awk -v t="$total" 'BEGIN { printf "%.0f", t*1000 }')
  ttfb_ms=$(awk -v t="$ttfb" 'BEGIN { printf "%.0f", t*1000 }')
  if (( total_ms > 2000 )); then
    flag="🔴"
  elif (( total_ms > 500 )); then
    flag="🟡"
  else
    flag="🟢"
  fi
  printf "%s %-48s  %5d ms  %5d ms  %s\n" "$flag" "$path" "$total_ms" "$ttfb_ms" "$code"
done

echo
echo "🔴 = >2s (måste fixas), 🟡 = 0.5-2s (förbättra), 🟢 = <0.5s (OK)"
