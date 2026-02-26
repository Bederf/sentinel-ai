#!/usr/bin/env bash
# sentinel-disk-monitor.sh — Daily VPS health check with email alerts
# Runs daily at 07:00 SAST via systemd timer
# Alerts via Gmail API (gmail_helper.py)
#
# Checks:
#   1. Root disk usage (warn 80%, critical 90%)
#   2. Docker storage breakdown
#   3. Supabase _analytics table bloat (if container running)
#   4. Orphaned Docker backup directories
#   5. Docker dangling images/volumes

set -euo pipefail

# --- Configuration ---
WARN_PERCENT=80
CRIT_PERCENT=90
ANALYTICS_WARN_GB=5
LOG_DIR="/var/log/sentinel"
LOG_FILE="${LOG_DIR}/disk-monitor.log"
GMAIL_HELPER="/home/bederf/.sentry/tools/gmail_helper.py"
ALERT_EMAIL="bederf@gmail.com"
DB_CONTAINER="supabase_db_bms-intelligence"

# --- Ensure log directory exists ---
sudo mkdir -p "$LOG_DIR" 2>/dev/null || true
sudo chown bederf:bederf "$LOG_DIR" 2>/dev/null || true

# --- Helpers ---
timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

log() { echo "[$(timestamp)] $*" >> "$LOG_FILE"; }

send_email() {
    local subject="$1"
    local body="$2"
    if [[ -x "$GMAIL_HELPER" ]] || [[ -f "$GMAIL_HELPER" ]]; then
        python3 "$GMAIL_HELPER" send "$subject" "$body" "$ALERT_EMAIL" 2>>"$LOG_FILE" \
            && log "Email sent: $subject" \
            || log "WARN: gmail send failed"
    else
        log "WARN: gmail_helper.py not found at $GMAIL_HELPER, alert logged only"
    fi
}

# --- Collect metrics ---
log "=== Disk monitor run started ==="

ALERTS=""
REPORT=""

# 1. Root disk usage
DISK_USAGE=$(df / --output=pcent | tail -1 | tr -d ' %')
DISK_USED=$(df -h / --output=used | tail -1 | tr -d ' ')
DISK_AVAIL=$(df -h / --output=avail | tail -1 | tr -d ' ')
DISK_SIZE=$(df -h / --output=size | tail -1 | tr -d ' ')

log "Disk: ${DISK_USAGE}% used (${DISK_USED}/${DISK_SIZE}, ${DISK_AVAIL} free)"
REPORT="Disk: ${DISK_USAGE}% (${DISK_USED} used, ${DISK_AVAIL} free)"

if [[ "$DISK_USAGE" -ge "$CRIT_PERCENT" ]]; then
    ALERTS="${ALERTS}CRITICAL: Disk at ${DISK_USAGE}% — only ${DISK_AVAIL} free!\n"
elif [[ "$DISK_USAGE" -ge "$WARN_PERCENT" ]]; then
    ALERTS="${ALERTS}WARNING: Disk at ${DISK_USAGE}% — ${DISK_AVAIL} free\n"
fi

# 2. Docker storage
if command -v docker &>/dev/null; then
    DOCKER_SIZE=$(sudo du -sh /var/lib/docker 2>/dev/null | cut -f1 || echo "unknown")
    log "Docker storage: $DOCKER_SIZE"
    REPORT="${REPORT}\nDocker: ${DOCKER_SIZE}"

    # Check for orphaned docker backup dirs
    ORPHANS=$(find /var/lib/ -maxdepth 1 -name "docker.*" -not -name "docker" 2>/dev/null)
    if [[ -n "$ORPHANS" ]]; then
        ALERTS="${ALERTS}Orphaned Docker dirs found:\n${ORPHANS}\n"
        log "ORPHAN DIRS: $ORPHANS"
    fi

    # Dangling images
    DANGLING=$(docker images -f dangling=true -q 2>/dev/null | wc -l)
    if [[ "$DANGLING" -gt 5 ]]; then
        ALERTS="${ALERTS}${DANGLING} dangling Docker images — run 'docker image prune'\n"
        log "Dangling images: $DANGLING"
    fi
fi

# 3. Supabase analytics table bloat
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "$DB_CONTAINER"; then
    ANALYTICS_SIZE=$(docker exec "$DB_CONTAINER" psql -U postgres -d _supabase -tAc \
        "SELECT pg_size_pretty(pg_database_size('_supabase'));" 2>/dev/null || echo "unknown")
    log "Supabase _supabase DB: $ANALYTICS_SIZE"
    REPORT="${REPORT}\nSupabase analytics DB: ${ANALYTICS_SIZE}"

    # Check if analytics tables are over threshold
    ANALYTICS_BYTES=$(docker exec "$DB_CONTAINER" psql -U postgres -d _supabase -tAc \
        "SELECT COALESCE(SUM(pg_total_relation_size(schemaname||'.'||tablename)), 0) FROM pg_tables WHERE schemaname='_analytics';" 2>/dev/null || echo "0")
    ANALYTICS_GB=$(( ${ANALYTICS_BYTES:-0} / 1073741824 ))

    if [[ "$ANALYTICS_GB" -ge "$ANALYTICS_WARN_GB" ]]; then
        ALERTS="${ALERTS}Supabase _analytics tables: ${ANALYTICS_GB} GB — needs truncation\n"
        log "ANALYTICS BLOAT: ${ANALYTICS_GB} GB"
    fi

    # Main DB size
    MAIN_DB_SIZE=$(docker exec "$DB_CONTAINER" psql -U postgres -tAc \
        "SELECT pg_size_pretty(pg_database_size('postgres'));" 2>/dev/null || echo "unknown")
    REPORT="${REPORT}\nSupabase main DB: ${MAIN_DB_SIZE}"
    log "Supabase main DB: $MAIN_DB_SIZE"
else
    REPORT="${REPORT}\nSupabase: container not running"
    log "Supabase container not running — skipping DB checks"
fi

# --- Send alerts or weekly summary ---
HOSTNAME=$(hostname)
REPORT_BODY=$(echo -e "$REPORT")

if [[ -n "$ALERTS" ]]; then
    ALERT_BODY=$(echo -e "$ALERTS")
    SUBJECT="[SENTINEL] VPS Health Alert — ${HOSTNAME}"
    BODY="SENTINEL VPS Health Alert
=============================

${ALERT_BODY}

Report
------
${REPORT_BODY}

Timestamp: $(timestamp)"

    log "SENDING ALERT EMAIL"
    send_email "$SUBJECT" "$BODY"
else
    # Weekly summary (only on Mondays, or if FORCE_SUMMARY=1)
    if [[ "$(date +%u)" == "1" ]] || [[ "${FORCE_SUMMARY:-0}" == "1" ]]; then
        SUBJECT="[SENTINEL] VPS Weekly Report — ${HOSTNAME}"
        BODY="SENTINEL VPS Weekly Report
=============================

${REPORT_BODY}

All clear — no issues detected.

Timestamp: $(timestamp)"

        log "Sending weekly summary email"
        send_email "$SUBJECT" "$BODY"
    fi
fi

log "=== Disk monitor run complete ==="
