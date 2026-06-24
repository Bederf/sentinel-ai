#!/usr/bin/env bash
# SENTINEL Infra Config Drift Detector
#
# Read-only check: compares live system configs against the versioned
# copies in infrastructure/. Exits non-zero on any drift.
#
# Safe to run as a cron job or pre-commit hook. Never auto-remediates.
#
# Covered files:
#   - systemd unit files (service definitions)
#   - Caddy reverse-proxy config
#   - Cloudflare tunnel ingress config
#   - Mosquitto MQTT broker config (listener + ACL)
#   - Cron/APScheduler definitions (systemd timers)
#
# Usage:
#   ./infrastructure/check-drift.sh
#   ./infrastructure/check-drift.sh --quiet   # exit code only, no output
set -euo pipefail

QUIET=false
if [[ "${1:-}" == "--quiet" ]]; then
  QUIET=true
fi

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INFRA_DIR="$REPO_DIR/infrastructure"

DRIFT=0
log()   { $QUIET || echo "$@"; }
error() { log "DRIFT: $@"; DRIFT=1; }

check_file() {
  local label="$1"
  local live="$2"      # path on the live system
  local infra="$3"     # path in infrastructure/

  if [[ ! -f "$live" ]]; then
    log "  SKIP $label — live file not found at $live"
    return
  fi
  if [[ ! -f "$infra" ]]; then
    error "$label — infrastructure/ copy missing at $infra"
    return
  fi
  if ! diff -q "$live" "$infra" &>/dev/null; then
    error "$label — live and infrastructure/ differ"
    $QUIET || diff "$live" "$infra" 2>/dev/null | head -30
  fi
}

check_dir_exists() {
  local label="$1"
  local path="$2"
  if [[ ! -d "$path" ]]; then
    error "$label — directory not found at $path"
  fi
}

# ── Systemd units ──────────────────────────────────────────────────────────
log "=== Systemd units ==="
check_dir_exists "systemd dir" "$INFRA_DIR/systemd"
for unit in "$INFRA_DIR"/systemd/*.service; do
  name=$(basename "$unit")
  check_file "systemd/$name" "/etc/systemd/system/$name" "$unit"
done

# ── Caddy ──────────────────────────────────────────────────────────────────
log "=== Caddy ==="
check_file "Caddyfile" "$REPO_DIR/Caddyfile" "$INFRA_DIR/caddy/Caddyfile"

# ── Cloudflare Tunnel ──────────────────────────────────────────────────────
log "=== Cloudflare Tunnel ==="
check_file "cloudflared/config.yml" "/etc/cloudflared/config.yml" "$INFRA_DIR/cloudflared/config.yml"

# ── Mosquitto ──────────────────────────────────────────────────────────────
log "=== Mosquitto ==="
check_file "mosquitto/sentinel.conf" "/etc/mosquitto/conf.d/sentinel.conf" "$INFRA_DIR/mosquitto/sentinel.conf"
check_file "mosquitto/sentinel.acl" "/etc/mosquitto/conf.d/sentinel.acl" "$INFRA_DIR/mosquitto/sentinel.acl"

# ── Systemd timers (cron/APScheduler equivalents) ──────────────────────────
log "=== Systemd timers ==="
for timer in "$INFRA_DIR"/systemd/*.timer; do
  [[ -f "$timer" ]] || continue
  name=$(basename "$timer")
  check_file "systemd/$name" "/etc/systemd/system/$name" "$timer"
done

log "=== Summary ==="
if [[ "$DRIFT" -eq 0 ]]; then
  log "  No drift detected."
else
  log "  $DRIFT drift(s) detected. infrastructure/ is out of sync with live config."
  log "  After confirming the live config is correct, run:"
  log "    cp <live-path> infrastructure/<path>"
fi
exit "$DRIFT"
