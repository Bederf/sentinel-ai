#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="${REPO_ROOT}/backups/logs"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/postgres_backup_refresh_${TIMESTAMP}.log"
STATUS_FILE="${LOG_DIR}/postgres_backup_refresh_status.json"
START_EPOCH="$(date +%s)"

mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

BACKUP_MODE="${BACKUP_MODE:-daily}"
RESTORE_DOCKER_CONTAINER="${RESTORE_DOCKER_CONTAINER:-sentinel-postgres-backup-db}"
TARGET_DATABASE="${TARGET_DATABASE:-sentinel_backup}"
export RESTORE_DOCKER_CONTAINER

write_status() {
  local result="$1"
  local message="${2:-}"
  local now
  local duration
  now="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  duration="$(( $(date +%s) - START_EPOCH ))"
  "${REPO_ROOT}/scripts/backup/write_backup_refresh_status.py" \
    "${STATUS_FILE}" \
    "${result}" \
    "${now}" \
    "${TARGET_DATABASE}" \
    "${RESTORE_DOCKER_CONTAINER}" \
    --backup-dir "${BACKUP_DIR:-}" \
    --duration-seconds "${duration}" \
    --message "${message}" || true
}

on_error() {
  local exit_code="$?"
  write_status "failed" "refresh exited with status ${exit_code}"
  exit "${exit_code}"
}

trap on_error ERR

echo "Refreshing dedicated backup Postgres target"
echo "Timestamp: ${TIMESTAMP}"
echo "Mode: ${BACKUP_MODE}"
echo "Restore container: ${RESTORE_DOCKER_CONTAINER}"

"${SCRIPT_DIR}/postgres_logical_backup.sh" "${BACKUP_MODE}"
BACKUP_DIR="$(find "${REPO_ROOT}/backups/postgres/${BACKUP_MODE}" -mindepth 1 -maxdepth 1 -type d | sort | tail -n1)"
if [[ -z "${BACKUP_DIR}" || ! -d "${BACKUP_DIR}" ]]; then
  echo "No ${BACKUP_MODE} backup directory found after backup run" >&2
  exit 1
fi
echo "Restoring latest ${BACKUP_MODE} backup: ${BACKUP_DIR}"
"${REPO_ROOT}/scripts/restore/restore_postgres_backup.sh" \
  "${BACKUP_DIR}"

TABLE_COUNT="$(docker exec "${RESTORE_DOCKER_CONTAINER}" psql -U postgres -d "${TARGET_DATABASE}" -tAc "select count(*) from information_schema.tables where table_schema='public';" | xargs)"
DATABASE_SIZE_BYTES="$(docker exec "${RESTORE_DOCKER_CONTAINER}" psql -U postgres -d postgres -tAc "select pg_database_size('${TARGET_DATABASE}');" | xargs)"
CRITICAL_ROW_COUNTS_JSON="$(
  docker exec "${RESTORE_DOCKER_CONTAINER}" psql -U postgres -d "${TARGET_DATABASE}" -tAc "
    select jsonb_object_agg(table_name, row_count)::text
    from (
      select 'sites' as table_name, count(*)::bigint as row_count from public.sites
      union all select 'recommendations', count(*)::bigint from public.recommendations
      union all select 'work_orders', count(*)::bigint from public.work_orders
      union all select 'technicians', count(*)::bigint from public.technicians
      union all select 'equipment', count(*)::bigint from public.equipment
      union all select 'alerts', count(*)::bigint from public.alerts
      union all select 'audit_log', count(*)::bigint from public.audit_log
      union all select 'adapter_health', count(*)::bigint from public.adapter_health
      union all select 'site_module_configs', count(*)::bigint from public.site_module_configs
      union all select 'system_settings', count(*)::bigint from public.system_settings
    ) critical_counts;
  " | tr -d '\n'
)"
DURATION_SECONDS="$(( $(date +%s) - START_EPOCH ))"
"${REPO_ROOT}/scripts/backup/write_backup_refresh_status.py" \
  "${STATUS_FILE}" \
  "success" \
  "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
  "${TARGET_DATABASE}" \
  "${RESTORE_DOCKER_CONTAINER}" \
  --backup-dir "${BACKUP_DIR}" \
  --duration-seconds "${DURATION_SECONDS}" \
  --table-count "${TABLE_COUNT}" \
  --database-size-bytes "${DATABASE_SIZE_BYTES}" \
  --critical-row-counts-json "${CRITICAL_ROW_COUNTS_JSON}" \
  --message "local restore target refreshed successfully"

echo "Dedicated backup Postgres refresh completed"
