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

# Source env vars — check both backend/.env and root .env for bridge tokens
# (BRIDGE_API_TOKEN_SITE002 lives in root .env, not backend/.env)
if [[ -f /opt/bms-intelligence/backend/.env ]]; then
  BRIDGE_API_TOKEN="$(grep '^BRIDGE_API_TOKEN=' /opt/bms-intelligence/backend/.env 2>/dev/null | cut -d= -f2- | tr -d '"' || echo '')"
  SUPABASE_URL="$(grep '^SUPABASE_URL=' /opt/bms-intelligence/backend/.env 2>/dev/null | cut -d= -f2- | tr -d '"' || echo '')"
fi
if [[ -f /opt/bms-intelligence/.env ]]; then
  BRIDGE_API_TOKEN_SITE002="$(grep '^BRIDGE_API_TOKEN_SITE002=' /opt/bms-intelligence/.env 2>/dev/null | cut -d= -f2- | tr -d '"' || echo '')"
  # Fall back to root-level global token if per-site not present
  [[ -z "$BRIDGE_API_TOKEN" ]] && BRIDGE_API_TOKEN="$(grep '^BRIDGE_API_TOKEN=' /opt/bms-intelligence/.env 2>/dev/null | cut -d= -f2- | tr -d '"' || echo '')"
fi

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
curl -sf -m 5 -o /dev/null http://localhost:9096/api/health 2>/dev/null \
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

# --- Site Bridge (WireGuard + Sentinel Bridge API) ---
$QUIET || echo ""
$QUIET || echo "=== Site Bridge (S002 / WireGuard) ==="

# WireGuard tunnel — check peer handshake and transfer stats
if command -v wg &>/dev/null; then
  wg_show=$(sudo wg show wg0 2>/dev/null || echo "")
  if [[ -n "$wg_show" ]]; then
    # Check for active handshake (latest handshake line)
    handshake_age=$(echo "$wg_show" | grep "latest handshake" | awk '{print $4, $5, $6}' || echo "unknown")
    if echo "$wg_show" | grep -q "latest handshake:.*1 minute"; then
      check "WireGuard wg0" 0 "active (handshake: $handshake_age)"
    elif echo "$wg_show" | grep -q "latest handshake"; then
      check "WireGuard wg0" 0 "active (handshake: $handshake_age)"
    elif echo "$wg_show" | grep -q "no handshake"; then
      check "WireGuard wg0" 1 "no handshake — tunnel may be stale"
    else
      # No latest-handshake line = never established
      check "WireGuard wg0" 2 "handshake unknown — verify peer is reachable"
    fi

    # Transfer stats — non-zero TX means we can reach peer
    tx_bytes=$(echo "$wg_show" | grep "transfer:" | awk '{print $2}' | tr -d 'MiB KiB' || echo "0")
    rx_bytes=$(echo "$wg_show" | grep "transfer:" | awk '{print $5}' | tr -d 'MiB KiB' || echo "0")
    if [[ "${tx_bytes:-0}" != "0" && "${rx_bytes:-0}" != "0" ]]; then
      check "WireGuard tx/rx" 0 "tx=${tx_bytes}B rx=${rx_bytes}B"
    elif [[ "${tx_bytes:-0}" != "0" ]]; then
      check "WireGuard tx/rx" 2 "tx only (${tx_bytes}B) — no return traffic"
    else
      check "WireGuard tx/rx" 1 "no traffic on tunnel"
    fi

    # Check endpoint is correct (should be VPS public IP, not old IP)
    endpoint=$(echo "$wg_show" | grep "endpoint:" | awk '{print $2}' || echo "unknown")
    expected_endpoint="158.220.87.183:51820"
    if [[ "$endpoint" == "$expected_endpoint" ]]; then
      check "WireGuard endpoint" 0 "$endpoint"
    else
      check "WireGuard endpoint" 2 "endpoint=$endpoint (expected $expected_endpoint)"
    fi
  else
    check "WireGuard wg0" 1 "interface not found or no peers"
  fi
else
  check "WireGuard (wg cmd)" 2 "wg command not available"
fi

# Bridge API reachable via WireGuard — use site-002 bearer auth for real status
BRIDGE_BASE_URL="${BRIDGE_BASE_URL:-http://10.99.0.1:8080}"
# Prefer per-site token for site-002; fall back to global token
BRIDGE_TOKEN_SITE002="${BRIDGE_API_TOKEN_SITE002:-${BRIDGE_API_TOKEN:-}}"
if [[ -n "$BRIDGE_TOKEN_SITE002" ]]; then
  bridge_health=$(curl -sf -m 15 "$BRIDGE_BASE_URL/api/sites/site-002/health" \
    -H "Authorization: Bearer $BRIDGE_TOKEN_SITE002" 2>/dev/null || echo "fail")
  if [[ "$bridge_health" != "fail" ]]; then
    telemetry_fresh=$(echo "$bridge_health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('telemetry_fresh','?'))" 2>/dev/null || echo "?")
    last_telemetry=$(echo "$bridge_health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('last_telemetry_at','?'))" 2>/dev/null || echo "?")
    if [[ "$telemetry_fresh" == "True" || "$telemetry_fresh" == "true" ]]; then
      check "Bridge API $BRIDGE_BASE_URL" 0 "up (telemetry_fresh=true, last=${last_telemetry:-?})"
    else
      check "Bridge API $BRIDGE_BASE_URL" 2 "telemetry_fresh=$telemetry_fresh (last=${last_telemetry:-?})"
    fi
  else
    # Fallback: /health without auth (bridge-level, no per-site token needed)
    bridge_base_health=$(curl -sf -m 5 "$BRIDGE_BASE_URL/health" 2>/dev/null || echo "fail")
    if [[ "$bridge_base_health" != "fail" ]]; then
      check "Bridge API $BRIDGE_BASE_URL" 2 "unreachable on /api/sites/site-002/health (bridge up at /health, check token)"
    else
      check "Bridge API $BRIDGE_BASE_URL" 1 "unreachable via WireGuard tunnel"
    fi
  fi
else
  check "Bridge API token" 2 "BRIDGE_API_TOKEN (site-002) not set"
fi

# Sentinel backend shadow mode polling job
shadow_status=$(curl -sf -m 5 "http://localhost:9095/api/debug/health-snapshot/status" 2>/dev/null || echo "")
if [[ -n "$shadow_status" ]]; then
  # Check shadow_mode_polling job exists and next_run is near
  shadow_job=$(echo "$shadow_status" | python3 -c "
import sys, json, datetime
d = json.load(sys.stdin)
jobs = d.get('all_jobs', [])
for j in jobs:
    if j['id'] == 'shadow_mode_polling':
        nr = j.get('next_run', '')
        pending = j.get('pending', False)
        # Flag if next_run > 20 min away (job stalled)
        if nr:
            try:
                from datetime import datetime
                from dateutil import parser as dp
                next_run = dp.parse(nr)
                now = datetime.now(next_run.tzinfo)
                diff_min = (next_run - now).total_seconds() / 60
                stale = diff_min > 20
                print(f\"next={nr} pending={pending} diff_min={diff_min:.0f} stale={stale}\")
            except:
                print(f\"next={nr} pending={pending}\")
        else:
            print('not scheduled')
        break
else:
    print('NOT FOUND')
" 2>/dev/null || echo "ERROR")

  if [[ "$shadow_job" == "NOT FOUND" ]]; then
    check "Shadow polling job" 1 "not registered in APScheduler"
  elif echo "$shadow_job" | grep -q "stale=True"; then
    diff=$(echo "$shadow_job" | grep -oE 'diff_min=[0-9]+' | cut -d= -f2)
    check "Shadow polling job" 2 "stale — next run ${diff}m away (job may be stalled)"
  elif echo "$shadow_job" | grep -q "pending=True"; then
    check "Shadow polling job" 0 "$(echo $shadow_job | grep -oE 'next=[^ ]+' | head -1)"
  else
    check "Shadow polling job" 0 "$(echo $shadow_job | grep -oE 'next=[^ ]+' | head -1)"
  fi

  # Check last poll result from energy-accum endpoint
  energy_data=$(curl -sf -m 5 "http://localhost:9095/api/debug/energy-accum" 2>/dev/null || echo "")
  if [[ -n "$energy_data" ]]; then
    poll_count=$(echo "$energy_data" | python3 -c "import sys,json; d=json.load(sys.stdin); lp=d.get('last_poll_result',{}); print(lp.get('poll_count','?'))" 2>/dev/null || echo "?")
    ml_hours=$(echo "$energy_data" | python3 -c "import sys,json; d=json.load(sys.stdin); lp=d.get('last_poll_result',{}); print(lp.get('ml_hours_ingested','?'))" 2>/dev/null || echo "?")
    errors=$(echo "$energy_data" | python3 -c "import sys,json; d=json.load(sys.stdin); lp=d.get('last_poll_result',{}); e=lp.get('errors',[]); print(len(e))" 2>/dev/null || echo "0")
    missing_eq=$(echo "$energy_data" | python3 -c "import sys,json; d=json.load(sys.stdin); lp=d.get('last_poll_result',{}); m=lp.get('equipment_missing_from_bridge',[]); print(len(m))" 2>/dev/null || echo "0")
    trends_data=$(echo "$energy_data" | python3 -c "import sys,json; d=json.load(sys.stdin); lp=d.get('last_poll_result',{}); print(lp.get('trends_with_data','0'))" 2>/dev/null || echo "0")
    setpoints_polled=$(echo "$energy_data" | python3 -c "import sys,json; d=json.load(sys.stdin); lp=d.get('last_poll_result',{}); print(lp.get('setpoints_polled','0'))" 2>/dev/null || echo "0")

    check "Bridge poll count" 0 "polls=$poll_count ml_hours=$ml_hours"
    [[ "$errors" -gt 0 ]] && check "Bridge poll errors" 1 "$errors errors" || check "Bridge poll errors" 0 "none"

    if [[ "$missing_eq" -gt 0 ]]; then
      missing_list=$(echo "$energy_data" | python3 -c "import sys,json; d=json.load(sys.stdin); lp=d.get('last_poll_result',{}); m=lp.get('equipment_missing_from_bridge',[]); print(', '.join(m[:5]))" 2>/dev/null || echo "$missing_eq items")
      check "Equipment missing from bridge" 2 "$missing_eq missing: $missing_list"
    else
      check "Equipment catalog sync" 0 "all equipment found in bridge"
    fi

    if [[ "$trends_data" == "0" ]]; then
      check "Bridge trend data" 0 "push store empty by design — IPMVP energy endpoint in use"
    else
      check "Bridge trend data" 0 "$trends_data sensors with data"
    fi

    if [[ "$setpoints_polled" == "0" ]]; then
      check "Bridge setpoints" 0 "none configured (expected for BACnet)"
    else
      check "Bridge setpoints" 0 "$setpoints_polled polled"
    fi
  else
    check "Energy-accum debug endpoint" 2 "not reachable"
  fi
else
  check "Scheduler debug endpoint" 2 "not reachable (backend may be down)"
fi

# Bridge API bridge-level alarms
if [[ -n "$BRIDGE_API_TOKEN" ]]; then
  bridge_alarms=$(curl -sf -m 5 "$BRIDGE_BASE_URL/api/sites/site-002/alarms" -H "Authorization: Bearer $BRIDGE_API_TOKEN" 2>/dev/null || echo '{"count":"?"}')
  alarm_count=$(echo "$bridge_alarms" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if isinstance(d, list): print(len(d))
    elif isinstance(d, dict):
        if 'count' in d: print(d['count'])
        elif 'alarms' in d: print(len(d['alarms']))
        else: print(len(d))
except: print('parse_err')
" 2>/dev/null || echo "?")
  if [[ "$alarm_count" == "parse_err" || "$alarm_count" == "?" ]]; then
    check "Bridge alarm count" 2 "could not parse alarm response"
  elif [[ "$alarm_count" -gt 500 ]]; then
    check "Bridge alarms" 2 "HIGH — $alarm_count active alarms (ingestion may be stalled)"
  elif [[ "$alarm_count" -gt 100 ]]; then
    check "Bridge alarms" 2 "ELEVATED — $alarm_count active alarms"
  elif [[ "$alarm_count" -gt 0 ]]; then
    check "Bridge alarms" 0 "$alarm_count active (normal)"
  else
    check "Bridge alarms" 0 "none active"
  fi

  # Bridge telemetry — policy_stage and source_mode
  bridge_telemetry=$(curl -sf -m 5 "$BRIDGE_BASE_URL/api/sites/site-002/telemetry" -H "Authorization: Bearer $BRIDGE_API_TOKEN" 2>/dev/null || echo "")
  if [[ -n "$bridge_telemetry" ]]; then
    policy_stage=$(echo "$bridge_telemetry" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('policy_stage','?'))" 2>/dev/null || echo "?")
    source_mode=$(echo "$bridge_telemetry" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('source_mode','?'))" 2>/dev/null || echo "?")
    if [[ "$policy_stage" == "commissioning" ]]; then
      check "Bridge policy_stage" 2 "commissioning (site still being onboarded)"
    elif [[ "$policy_stage" == "live" || "$policy_stage" == "shadow_live" || "$policy_stage" == "advisory" || "$policy_stage" == "supervised" || "$policy_stage" == "automatic" ]]; then
      check "Bridge policy_stage" 0 "$policy_stage"
    else
      check "Bridge policy_stage" 2 "$policy_stage"
    fi
    [[ "$source_mode" == "live" ]] && check "Bridge source_mode" 0 "live" || check "Bridge source_mode" 2 "source_mode=$source_mode"
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

# Space MQTT listener (backend) — check that backend is connected to broker
# The listener uses client_id "sentinel-space-backend", which appears as <unknown>
# in mosquitto logs. We check instead for recent inbound traffic from non-localhost
# (ESP32 nodes would connect from their own IPs, not 127.0.0.1).
space_mqtt_recent=$(sudo grep -vE "protocol error|disconnected|not authorised|New connection|closed its|127.0.0.1" \
  /var/log/mosquitto/mosquitto.log 2>/dev/null | \
  grep -cE "sentinel|space|node|device|room" 2>/dev/null || echo "0")
mosquitto_log_recent=$(sudo grep -cv "^" /var/log/mosquitto/mosquitto.log 2>/dev/null || echo "0")

# ESP32 nodes publish to topics like "sentinel/space/node_001" and similar.
# Check if mosquitto has any active client connections (non-<unknown> clients).
esp32_nodes_seen=$(sudo awk '
  /New connection/ {
    # Extract IP — last field before "on port"
    ip=$(NF-1)
    # Skip localhost and gateway IPs
    if (ip != "127.0.0.1" && ip != "127.0.0.1:" && ip !~ /^172\./ && ip !~ /^10\./ && ip !~ /^192\.168\./) {
      count++ }}
  END { print count+0 }
' /var/log/mosquitto/mosquitto.log 2>/dev/null || echo "0")

if [[ "$esp32_nodes_seen" -gt 0 ]]; then
  check "ESP32 space nodes" 0 "$esp32_nodes_seen external connections in log"
elif [[ "$space_mqtt_recent" -gt 0 ]]; then
  check "ESP32 space nodes" 0 "backend space MQTT activity in log"
else
  check "ESP32 space nodes" 1 "no space-node traffic (devices offline or not yet deployed)"
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

REPLICA_HOST="${REPLICA_HOST:-10.146.169.2}"
REPLICA_PORT="${REPLICA_PORT:-55322}"
# Replica is NAT'd behind WireGuard — it initiates outbound but we can't reach it directly.
# The health check below is best-effort; failure is expected if the replica doesn't expose ports.
REPLICA_CONN="postgresql://repluser:replic8r_secur3_pw@${REPLICA_HOST}:${REPLICA_PORT}/postgres"
PRIMARY_CONN="postgresql://postgres:postgres@127.0.0.1:55322/postgres"

if nc -z -w5 "$REPLICA_HOST" "$REPLICA_PORT" 2>/dev/null; then
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
  # Replica is NAT'd behind WireGuard — initiates outbound, not reachable inbound.
  # Check if the primary's replication slot shows it's connected.
  slot_active=$(psql "${PRIMARY_CONN}" -t -A -c "SELECT count(*) FROM pg_replication_slots WHERE active AND slot_type='physical'" 2>/dev/null || echo "0")
  if [[ "$slot_active" -gt 0 ]]; then
    check "Replica (NAT'd)" 0 "connected via replication slot"
  else
    check "Replica (NAT'd)" 2 "no active replication slot — replica may be down"
  fi
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
