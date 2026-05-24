#!/bin/bash
# =============================================================================
# SENTINEL Infrastructure Health Check
# =============================================================================
# Run: ./infrastructure-health.sh
# Checks: Prometheus jobs, backend API, bridge, database
# Schedule: Daily via cron or on-demand
#
# Prerequisites: curl, docker
# =============================================================================

set -euo pipefail

PROMETHEUS="${PROMETHEUS:-http://localhost:9090}"
BACKEND="${BACKEND:-http://localhost:9095}"
TOKEN="${METRICS_BEARER_TOKEN:-BErktNRmBMUi1Yh4v9U0/WP9C4l/REd9pFKT4s11kYs=}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

check_job() {
  local job="$1"
  local expected="${2:-1}"

  # sum() aggregates across all scrape targets for this job
  result=$(curl -sfG --data-urlencode "query=sum(up{job=\"$job\"})" "$PROMETHEUS/api/v1/query" 2>/dev/null | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('result',[{}])[0].get('value',[0,'0'])[1])" 2>/dev/null || echo "ERR")

  if [ "$result" = "$expected" ]; then
    echo -e "  ${GREEN}[PASS]${NC}  $job (up=$result)"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}[FAIL]${NC}  $job (up=$result, expected $expected)"
    FAIL=$((FAIL + 1))
  fi
}

check_endpoint() {
  local name="$1"
  local url="$2"
  local auth="${3:-}"

  if [ -n "$auth" ]; then
    code=$(curl -sfo /dev/null -w "%{http_code}" -H "Authorization: Bearer $auth" "$url" 2>/dev/null || echo "ERR")
  else
    code=$(curl -sfo /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "ERR")
  fi

  if [ "$code" = "200" ]; then
    echo -e "  ${GREEN}[PASS]${NC}  $name (HTTP $code)"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}[FAIL]${NC}  $name (HTTP ${code:-ERR})"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== SENTINEL Infrastructure Health Check ==="
echo "Time: $(date '+%Y-%m-%d %H:%M:%S SAST')"
echo ""

# ── Prometheus scrape jobs ────────────────────────────────────────────────
echo "Prometheus scrape jobs:"
check_job "prometheus" "1"
check_job "sentinel-governance" "1"
check_job "sentinel-discipline" "1"
check_job "node-exporter" "1"
check_job "cadvisor" "1"

# ── Backend API ────────────────────────────────────────────────────────────
echo ""
echo "Backend API endpoints:"
check_endpoint "Backend /health" "$BACKEND/api/health"
check_endpoint "Backend /metrics" "$BACKEND/metrics" "$TOKEN"

# ── Database ─────────────────────────────────────────────────────────────────
echo ""
echo "Database:"
db_result=$(docker exec sentinel-postgres-backup-db pg_isready -U supabase_admin -d postgres 2>&1 | grep -o "accepting connections" || echo "down")
if [ "$db_result" = "accepting connections" ]; then
  echo -e "  ${GREEN}[PASS]${NC}  PostgreSQL (up)"
  PASS=$((PASS + 1))
else
  echo -e "  ${RED}[FAIL]${NC}  PostgreSQL (down)"
  FAIL=$((FAIL + 1))
fi

# ── Grafana ──────────────────────────────────────────────────────────────────
echo ""
echo "Grafana:"
grafana_status=$(curl -sf -o /dev/null -w "%{http_code}" "http://localhost:3000/api/health" 2>/dev/null || echo "ERR")
if [ "$grafana_status" = "200" ]; then
  echo -e "  ${GREEN}[PASS]${NC}  Grafana (HTTP $grafana_status)"
  PASS=$((PASS + 1))
else
  echo -e "  ${RED}[FAIL]${NC}  Grafana (HTTP ${grafana_status:-ERR})"
  FAIL=$((FAIL + 1))
fi

# ── Loki ─────────────────────────────────────────────────────────────────────
echo ""
echo "Loki:"
loki_status=$(curl -sf -o /dev/null -w "%{http_code}" "http://localhost:3100/ready" 2>/dev/null || echo "ERR")
if [ "$loki_status" = "200" ]; then
  echo -e "  ${GREEN}[PASS]${NC}  Loki (HTTP $loki_status)"
  PASS=$((PASS + 1))
else
  echo -e "  ${RED}[FAIL]${NC}  Loki (HTTP ${loki_status:-ERR})"
  FAIL=$((FAIL + 1))
fi

# ── Bridge / SIMBIOT ─────────────────────────────────────────────────────────
echo ""
echo "Bridge:"
bridge_status=$(curl -sf -o /dev/null -w "%{http_code}" "http://localhost:9096/health" 2>/dev/null || echo "ERR")
if [ "$bridge_status" = "200" ]; then
  echo -e "  ${GREEN}[PASS]${NC}  SIMBIOT Bridge (HTTP $bridge_status)"
  PASS=$((PASS + 1))
else
  echo -e "  ${YELLOW}[WARN]${NC}  SIMBIOT Bridge (HTTP ${bridge_status:-ERR}) — may be expected if no site is connected"
  PASS=$((PASS + 1))
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo -e "Results: ${GREEN}${PASS} passed${NC} | ${RED}${FAIL} failed${NC}"
echo "========================================"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
