#!/usr/bin/env bash
# scripts/healthcheck.sh — SignalForge deployment health check
# Usage: ./scripts/healthcheck.sh [API_URL]
# Default API URL: http://localhost:8000

set -euo pipefail

API_URL="${1:-http://localhost:8000}"
WEB_URL="${2:-http://localhost:5174}"
PASS=0
FAIL=0

green() { printf '\033[0;32m✓ %s\033[0m\n' "$1"; }
red()   { printf '\033[0;31m✗ %s\033[0m\n' "$1"; }
info()  { printf '\033[0;34m  %s\033[0m\n' "$1"; }

check() {
  local name="$1"
  local url="$2"
  local expected="${3:-200}"
  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")
  if [ "$http_code" = "$expected" ]; then
    green "$name (HTTP $http_code)"
    PASS=$((PASS+1))
  else
    red "$name (got HTTP $http_code, expected $expected)"
    FAIL=$((FAIL+1))
  fi
}

echo ""
echo "=== SignalForge Health Check ==="
echo "API:  $API_URL"
echo "Web:  $WEB_URL"
echo ""

echo "── Core endpoints ──────────────────────────────────────"
check "API root"                    "$API_URL/"
check "API /health"                 "$API_URL/health"
check "API /system/health/detailed" "$API_URL/system/health/detailed"
check "API /system/telemetry"       "$API_URL/system/telemetry"
check "API /workers/health"         "$API_URL/workers/health"
check "API /workers/queue-depth"    "$API_URL/workers/queue-depth"
check "API /system/indexes"         "$API_URL/system/indexes"
check "API /system/metrics"         "$API_URL/system/metrics"
check "Web frontend"                "$WEB_URL"

echo ""
echo "── Workflow endpoints ──────────────────────────────────"
check "GET /workflow-assets"        "$API_URL/workflow-assets"
check "GET /approval-requests"      "$API_URL/approval-requests"
check "GET /agent-tasks"            "$API_URL/agent-tasks"
check "GET /orchestrations"         "$API_URL/orchestrations"

echo ""
echo "── Memory / autonomy endpoints ─────────────────────────"
check "GET /client-memory"          "$API_URL/client-memory"
check "GET /autonomy/config"        "$API_URL/autonomy/config"
check "GET /recommendations"        "$API_URL/recommendations"

echo ""
echo "════════════════════════════════"
if [ "$FAIL" -eq 0 ]; then
  printf '\033[0;32m All %d checks passed\033[0m\n\n' "$PASS"
  exit 0
else
  printf '\033[0;31m %d passed, %d failed\033[0m\n\n' "$PASS" "$FAIL"
  exit 1
fi
