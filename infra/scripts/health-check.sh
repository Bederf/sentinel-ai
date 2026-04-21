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

# --- MQTT Broker (Mosquitto) ---
$QUIET || echo ""
$QUIET || echo "=== MQTT Broker ==="

# Mosquitto process
if pgrep -x mosquitto >/dev/null 2>&1; then
  check "Mosquitto (process)" 0 "running"
else
  check "Mosquitto (process)" 1 "not running"
fi

# Mosquitto port 1883
(echo > /dev/tcp/localhost/1883) 2>/dev/null \
  && check "Mosquitto port :1883" 0 "open" \
  || check "Mosquitto port :1883" 1 "closed"

# Mosquitto auth - try anonymous connection (should fail but confirm broker responds)
# Use { } to capture pipefail correctly; mosquitto_sub exits 5 (auth rejected)
auth_output=$(timeout 2 mosquitto_sub -t '$SYS/test/health' -C 1 -W 1 2>&1 || true)
if echo "$auth_output" | grep -qiE "connection refused|not authorised|connection error"; then
  check "Mosquitto auth" 0 "auth required (good)"
else
  check "Mosquitto auth" 2 "broker may allow anonymous or unreachable"
fi

# Recent node connections from Mosquitto log
if [[ -f /var/log/mosquitto/mosquitto.log ]]; then
  recent_window=$(date -d '15 minutes ago' +%s 2>/dev/null || echo "0")
  recent_nodes=$(sudo grep -cE "node_001|node_002" /var/log/mosquitto/mosquitto.log 2>/dev/null || echo "0")
  node_001_recent=$(sudo grep -c "node_001" /var/log/mosquitto/mosquitto.log 2>/dev/null || echo "0")
  node_002_recent=$(sudo grep -c "node_002" /var/log/mosquitto/mosquitto.log 2>/dev/null || echo "0")
  node_001_last=$(sudo grep "node_001" /var/log/mosquitto/mosquitto.log 2>/dev/null | tail -1 | awk '{print $2}' || echo "unknown")
  node_002_last=$(sudo grep "node_002" /var/log/mosquitto/mosquitto.log 2>/dev/null | tail -1 | awk '{print $2}' || echo "unknown")

  if [[ "$node_001_recent" -gt 0 && "$node_002_recent" -gt 0 ]]; then
    check "ESP32 node_001" 0 "connected (last: $node_001_last)"
    check "ESP32 node_002" 0 "connected (last: $node_002_last)"
  elif [[ "$node_001_recent" -gt 0 ]]; then
    check "ESP32 node_001" 0 "seen in log (last: $node_001_last)"
    check "ESP32 node_002" 1 "not in log"
  elif [[ "$node_002_recent" -gt 0 ]]; then
    check "ESP32 node_001" 1 "not in log"
    check "ESP32 node_002" 0 "seen in log (last: $node_002_last)"
  else
    check "ESP32 node_001" 1 "no recent log activity"
    check "ESP32 node_002" 1 "no recent log activity"
  fi
else
  check "Mosquitto log" 2 "/var/log/mosquitto/mosquitto.log not accessible"
  check "ESP32 node_001" 2 "cannot check (no log access)"
  check "ESP32 node_002" 2 "cannot check (no log access)"
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

# --- Streaming WAL Replica (Mirror DB) ---
$QUIET || echo ""
$QUIET || echo "=== Streaming WAL Replica ==="

REPLICA_HOST="${REPLICA_HOST:-164.90.235.216}"
REPLICA_PORT="${REPLICA_PORT:-55432}"
REPLICA_CONN="postgresql://postgres:postgres@${REPLICA_HOST}:${REPLICA_PORT}/postgres"

if (echo > /dev/tcp/${REPLICA_HOST}/${REPLICA_PORT}) 2>/dev/null; then
  check "Replica port :${REPLICA_PORT}" 0 "open"

  if command -v psql &>/dev/null; then
    # Check replica is in recovery mode (i.e., really a standby)
    repl_status=$(psql "${REPLICA_CONN}" -c "SELECT pg_is_in_recovery()" -t -A 2>/dev/null || echo "error")
    if [[ "$repl_status" == "t" ]]; then
      check "Replica in recovery" 0 "standby active"

      # Replication lag in bytes — NULL means WAL receiver not connected
      repl_lag=$(psql "${REPLICA_CONN}" -c "SELECT pg_wal_lag_diff(pg_current_wal_lsn(), replay_location)" -t -A 2>/dev/null || echo "NULL")
      if [[ "$repl_lag" == "NULL" || "$repl_lag" == "" ]]; then
        check "Replica WAL lag" 2 "not connected to primary (pg_wal_lag_diff returned NULL)"
      else
        # Convert bytes to MB for readability
        repl_lag_mb=$(echo "scale=1; ${repl_lag:-0} / 1024 / 1024" | bc 2>/dev/null || echo "unknown")
        if [[ "$repl_lag" -lt 10485760 ]]; then  # < 10 MB
          check "Replica WAL lag" 0 "~${repl_lag_mb} MB"
        elif [[ "$repl_lag" -lt 104857600 ]]; then  # < 100 MB
          check "Replica WAL lag" 2 "~${repl_lag_mb} MB (elevated)"
        else
          check "Replica WAL lag" 1 "~${repl_lag_mb} MB (critical lag)"
        fi
      fi

      # Last WAL received timestamp
      last_wal=$(psql "${REPLICA_CONN}" -c "SELECT now() - pg_last_xact_replay_timestamp()" -t -A 2>/dev/null || echo "NULL")
      if [[ "$last_wal" != "NULL" && -n "$last_wal" ]]; then
        # Extract seconds for threshold check
        repl_age_sec=$(echo "$last_wal" | grep -oE '[0-9]+' | head -1 || echo "0")
        if [[ "${repl_age_sec:-0}" -lt 60 ]]; then
          check "Replica WAL age" 0 "~${repl_age_sec}s ago"
        elif [[ "${repl_age_sec:-0}" -lt 300 ]]; then
          check "Replica WAL age" 2 "~${repl_age_sec}s ago (delayed)"
        else
          check "Replica WAL age" 1 "~${repl_age_sec}s ago (stalled?)"
        fi
      else
        check "Replica WAL age" 2 "pg_last_xact_replay_timestamp() returned NULL"
      fi
    elif [[ "$repl_status" == "f" ]]; then
      check "Replica in recovery" 1 "is PRIMARY (replica expected)"
    else
      check "Replica in recovery" 2 "could not determine (pg_is_in_recovery=${repl_status})"
    fi
  else
    check "Replica psql" 2 "psql not installed (cannot run deep checks)"
    check "Replica WAL lag" 2 "psql not installed"
  fi
else
  check "Replica port :${REPLICA_PORT}" 1 "closed or unreachable"
fi

# Summary
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
