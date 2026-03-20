#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

BACKUP_SOURCE="${1:-latest}"
BACKUP_MODE="${BACKUP_MODE:-manual}"

SOURCE_ROOT="${REPO_ROOT}/backups/postgres/${BACKUP_MODE}"
if [[ "${BACKUP_SOURCE}" == "latest" ]]; then
  BACKUP_DIR="$(find "${SOURCE_ROOT}" -mindepth 1 -maxdepth 1 -type d | sort | tail -n1)"
else
  BACKUP_DIR="${BACKUP_SOURCE}"
fi

if [[ -z "${BACKUP_DIR:-}" || ! -d "${BACKUP_DIR}" ]]; then
  echo "Backup directory not found: ${BACKUP_DIR:-<empty>}" >&2
  exit 1
fi

if [[ ! -f "${BACKUP_DIR}/backup.env" ]]; then
  echo "backup.env missing in ${BACKUP_DIR}" >&2
  exit 1
fi

set -a
source "${BACKUP_DIR}/backup.env"
set +a

TARGET_PGHOST="${TARGET_PGHOST:-127.0.0.1}"
TARGET_PGPORT="${TARGET_PGPORT:-55432}"
TARGET_PGUSER="${TARGET_PGUSER:-postgres}"
TARGET_PGPASSWORD="${TARGET_PGPASSWORD:-postgres}"
TARGET_DATABASE="${TARGET_DATABASE:-sentinel_backup}"
RESTORE_RESET_DB="${RESTORE_RESET_DB:-true}"
RESTORE_VERIFY_EXTENSIONS="${RESTORE_VERIFY_EXTENSIONS:-true}"
export PGPASSWORD="${TARGET_PGPASSWORD}"

for tool in psql pg_restore createdb dropdb; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Required tool '${tool}' is not installed or not on PATH." >&2
    exit 1
  fi
done

echo "Restoring backup from: ${BACKUP_DIR}"
echo "Target Postgres: ${TARGET_PGHOST}:${TARGET_PGPORT}"
echo "Target database: ${TARGET_DATABASE}"

if [[ "${RESTORE_RESET_DB}" == "true" ]]; then
  dropdb \
    --if-exists \
    --host="${TARGET_PGHOST}" \
    --port="${TARGET_PGPORT}" \
    --username="${TARGET_PGUSER}" \
    "${TARGET_DATABASE}"
fi

createdb \
  --host="${TARGET_PGHOST}" \
  --port="${TARGET_PGPORT}" \
  --username="${TARGET_PGUSER}" \
  "${TARGET_DATABASE}" \
  2>/dev/null || true

if [[ -f "${BACKUP_DIR}/globals.sql" ]]; then
  psql \
    --host="${TARGET_PGHOST}" \
    --port="${TARGET_PGPORT}" \
    --username="${TARGET_PGUSER}" \
    --dbname=postgres \
    --file="${BACKUP_DIR}/globals.sql" \
    >/dev/null
fi

IFS=',' read -r -a DATABASES <<< "${DATABASES:-postgres}"

for db in "${DATABASES[@]}"; do
  db="$(echo "${db}" | xargs)"
  [[ -z "${db}" ]] && continue
  dump_file="${BACKUP_DIR}/${db}.dump"
  if [[ ! -f "${dump_file}" ]]; then
    echo "Dump file missing: ${dump_file}" >&2
    exit 1
  fi

  echo "Restoring ${dump_file} into ${TARGET_DATABASE}"
  pg_restore \
    --host="${TARGET_PGHOST}" \
    --port="${TARGET_PGPORT}" \
    --username="${TARGET_PGUSER}" \
    --dbname="${TARGET_DATABASE}" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    "${dump_file}"
done

if [[ "${RESTORE_VERIFY_EXTENSIONS}" == "true" && -n "${REQUIRED_EXTENSIONS:-}" ]]; then
  IFS=',' read -r -a REQUIRED <<< "${REQUIRED_EXTENSIONS}"
  for ext in "${REQUIRED[@]}"; do
    ext="$(echo "${ext}" | xargs)"
    [[ -z "${ext}" ]] && continue
    psql \
      --host="${TARGET_PGHOST}" \
      --port="${TARGET_PGPORT}" \
      --username="${TARGET_PGUSER}" \
      --dbname="${TARGET_DATABASE}" \
      --tuples-only \
      --no-align \
      --command="SELECT extname FROM pg_extension WHERE extname = '${ext}';" \
      | grep -qx "${ext}" || {
        echo "Required extension missing after restore: ${ext}" >&2
        exit 1
      }
  done
fi

echo "Restore completed successfully"
