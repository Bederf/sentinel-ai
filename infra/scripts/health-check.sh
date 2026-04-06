#!/usr/bin/env bash
# =============================================================================
# SENTINEL Infrastructure Health Check
# =============================================================================
# Checks all services required for SENTINEL to operate.
# Exit code 0 = all healthy, 1 = one or more failures.
#
# Usage:
#   ./infra/scripts/health-check.sh          # Full check
#   ./infra/scripts/health-check.sh --quiet  # Exit code only (for cron/monitoring)
# =============================================================================

set -euo pipefail

QUIET=false
[[ "${1:-}" == "--quiet" ]] && QUIET=true

PASS=0
WARN=0
FAIL=0
CONTEXT_WARN=0
CONTEXT_NOTES=()

add_context_note() {
  local note="$1"
  CONTEXT_WARN=1
  CONTEXT_NOTES+=("$note")
}

check() {
  local name="$1"
  local result="$2"  # 0=pass, 1=fail, 2=warn
  local detail="${3:-}"

  if [[ "$result" -eq 0 ]]; then
    PASS=$((PASS + 1))
    $QUIET || printf "  %-40s %s\n" "$name" "[OK] $detail"
  elif [[ "$result" -eq 2 ]]; then
    WARN=$((WARN + 1))
    $QUIET || printf "  %-40s %s\n" "$name" "[WARN] $detail"
  else
    FAIL=$((FAIL + 1))
    $QUIET || printf "  %-40s %s\n" "$name" "[FAIL] $detail"
  fi
}

systemd_service_active() {
  local svc="$1"
  local active_state=""
  active_state=$(systemctl show "$svc" --property=ActiveState --value 2>/dev/null || true)
  [[ "$active_state" == "active" ]]
}

detect_execution_context() {
  # This script is intended to run on the host. When executed inside a sandbox
  # or container namespace, localhost, systemd, and Docker checks can report
  # false negatives even while the host stack is healthy.
  if [[ -f "/.dockerenv" ]]; then
    add_context_note "Detected container execution via /.dockerenv; localhost/systemd/Docker results may reflect the container, not the host."
  elif grep -qaE '(docker|containerd|kubepods|podman)' /proc/1/cgroup 2>/dev/null; then
    add_context_note "Detected containerized cgroup context; health results may not reflect the host environment."
  fi

  if [[ ! -S /var/run/docker.sock ]]; then
    add_context_note "Docker socket is not visible from this environment; Supabase container checks may be false negatives."
  elif [[ ! -r /var/run/docker.sock || ! -w /var/run/docker.sock ]]; then
    add_context_note "Docker socket exists but is not accessible; container checks may be permission-limited."
  fi

  if [[ ! -d /run/systemd/system ]]; then
    add_context_note "systemd runtime directory is not visible; service checks may not reflect host units."
  fi
}

detect_execution_context

$QUIET || {
  if [[ "$CONTEXT_WARN" -eq 1 ]]; then
    echo "=== Execution Context Warning ==="
    for note in "${CONTEXT_NOTES[@]}"; do
      echo "  [WARN] $note"
    done
    echo ""
  fi
}

# --- Systemd Services ---
$QUIET || echo "=== Systemd Services ==="

for svc in sentinel-backend sentinel-frontend n8n n8n-batch-worker sentry redis-server sentinel-cloudflared; do
  if systemd_service_active "$svc"; then
    check "$svc.service" 0 "active"
  else
    check "$svc.service" 1 "not running"
  fi
done

# Optional services (warn if not running)
for svc in ollama; do
  if systemd_service_active "$svc"; then
    check "$svc.service (optional)" 0 "active"
  else
    check "$svc.service (optional)" 2 "not running"
  fi
done

# --- HTTP Endpoints ---
$QUIET || echo ""
$QUIET || echo "=== HTTP Endpoints ==="

# Backend health
backend_resp=$(curl -sf -m 5 http://localhost:9095/api/health 2>/dev/null) && {
  version=$(echo "$backend_resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo "?")
  check "Backend API :9095" 0 "v$version"
} || check "Backend API :9095" 1 "unreachable"

# Frontend
curl -sf -m 5 -o /dev/null http://localhost:9096 2>/dev/null \
  && check "Frontend :9096" 0 "serving" \
  || check "Frontend :9096" 1 "unreachable"

# n8n
curl -sf -m 5 -o /dev/null http://localhost:5678/healthz 2>/dev/null \
  && check "n8n :5678" 0 "healthy" \
  || check "n8n :5678" 1 "unreachable"

# --- Docker Containers (Supabase) ---
$QUIET || echo ""
$QUIET || echo "=== Supabase (Docker) ==="

if ! command -v docker &>/dev/null; then
  check "Docker" 1 "not installed"
else
  docker_err_file=$(mktemp)
  if ! docker info >/dev/null 2>"$docker_err_file"; then
    docker_err=$(tr '\n' ' ' <"$docker_err_file" | sed 's/[[:space:]]\+/ /g; s/^ //; s/ $//')
    rm -f "$docker_err_file"
    add_context_note "Docker daemon is not reachable from this execution context; container checks may be false negatives."
    check "Docker daemon access" 2 "${docker_err:-inaccessible}"
  else
    rm -f "$docker_err_file"
    for container in supabase_db_bms-intelligence supabase_kong_bms-intelligence supabase_auth_bms-intelligence supabase_rest_bms-intelligence supabase_realtime_bms-intelligence supabase_storage_bms-intelligence; do
      short_name="${container#supabase_}"
      short_name="${short_name%_bms-intelligence}"
      health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$container" 2>/dev/null || echo "missing")
      running=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null || echo "missing")
      if [[ "$health" == "healthy" ]]; then
        check "supabase/$short_name" 0 "healthy"
      elif [[ "$health" == "no-healthcheck" && "$running" == "running" ]]; then
        check "supabase/$short_name" 0 "running (no healthcheck)"
      elif [[ "$running" == "missing" ]]; then
        check "supabase/$short_name" 1 "container not found"
      else
        check "supabase/$short_name" 1 "$running ($health)"
      fi
    done

    # Supabase API reachability
    curl -sf -m 5 -o /dev/null http://localhost:55321/rest/v1/ -H "apikey: $(grep 'ANON_KEY' /opt/supabase/bms-intelligence/.env 2>/dev/null | cut -d= -f2 || echo 'none')" 2>/dev/null \
      && check "Supabase REST API :55321" 0 "responding" \
      || check "Supabase REST API :55321" 2 "unreachable (check ANON_KEY)"
  fi
fi

# --- Data Stores ---
$QUIET || echo ""
$QUIET || echo "=== Data Stores ==="

redis-cli ping 2>/dev/null | grep -q PONG \
  && check "Redis" 0 "PONG" \
  || check "Redis" 1 "no response"

# Supabase Postgres direct connectivity
if command -v psql &>/dev/null; then
  pg_result=$(psql "postgresql://postgres:postgres@localhost:55322/postgres" -c "SELECT 1" -t -A 2>/dev/null || echo "fail")
  if [[ "$pg_result" == "1" ]]; then
    check "Supabase Postgres :55322" 0 "connected"
  else
    check "Supabase Postgres :55322" 1 "query failed"
  fi
else
  # Fallback: check port is open
  (echo > /dev/tcp/localhost/55322) 2>/dev/null \
    && check "Supabase Postgres :55322" 0 "port open (psql not installed)" \
    || check "Supabase Postgres :55322" 1 "port closed"
fi

# Supabase Studio
curl -sf -m 5 -o /dev/null http://localhost:55323 2>/dev/null \
  && check "Supabase Studio :55323" 0 "serving" \
  || check "Supabase Studio :55323" 2 "unreachable (optional)"

# --- Summary ---
$QUIET || echo ""
$QUIET || echo "=== Summary ==="
TOTAL=$((PASS + WARN + FAIL))
$QUIET || echo "  $PASS/$TOTAL passed, $WARN warnings, $FAIL failures"

if [[ "$FAIL" -gt 0 ]]; then
  $QUIET || echo ""
  if [[ "$CONTEXT_WARN" -eq 1 ]]; then
    $QUIET || echo "  This script appears to be running outside the host context."
    $QUIET || echo "  Re-run it on the host before treating these failures as a real outage."
    $QUIET || echo ""
  fi
  $QUIET || echo "  Run 'systemctl status <service>' or 'docker logs <container>' to investigate."
  exit 1
fi

exit 0
