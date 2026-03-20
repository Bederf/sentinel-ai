#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

BACKUP_MODE="${BACKUP_MODE:-${1:-manual}}"
if [[ "${BACKUP_MODE}" != "daily" && "${BACKUP_MODE}" != "manual" ]]; then
  echo "Invalid backup mode '${BACKUP_MODE}'. Use 'daily' or 'manual'." >&2
  exit 1
fi

BACKUP_ROOT="${REPO_ROOT}/backups/postgres/${BACKUP_MODE}"
LOG_DIR="${REPO_ROOT}/backups/logs"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TARGET_DIR="${BACKUP_ROOT}/${TIMESTAMP}"
LOG_FILE="${LOG_DIR}/postgres_backup_${TIMESTAMP}.log"

PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-55322}"
PGUSER="${PGUSER:-postgres}"
export PGPASSWORD="${PGPASSWORD:-postgres}"

DATABASES_CSV="${SENTINEL_BACKUP_DATABASES:-${DATABASES:-postgres}}"
SCHEMAS_CSV="${SENTINEL_BACKUP_SCHEMAS:-${SCHEMAS:-}}"
REQUIRED_EXTENSIONS="${SENTINEL_REQUIRED_EXTENSIONS:-vector,pgcrypto,uuid-ossp}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

mkdir -p "${TARGET_DIR}" "${LOG_DIR}"

exec > >(tee -a "${LOG_FILE}") 2>&1

echo "Starting PostgreSQL logical backup"
echo "Timestamp: ${TIMESTAMP}"
echo "Mode: ${BACKUP_MODE}"
echo "Target dir: ${TARGET_DIR}"
echo "Host: ${PGHOST}:${PGPORT}"
echo "User: ${PGUSER}"
echo "Databases: ${DATABASES_CSV}"
echo "Schemas: ${SCHEMAS_CSV:-ALL}"
echo

for tool in pg_dump pg_dumpall; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Required tool '${tool}' is not installed or not on PATH." >&2
    exit 1
  fi
done

IFS=',' read -r -a DATABASES <<< "${DATABASES_CSV}"
IFS=',' read -r -a SCHEMAS <<< "${SCHEMAS_CSV}"

SCHEMA_ARGS=()
if [[ -n "${SCHEMAS_CSV}" ]]; then
  for schema in "${SCHEMAS[@]}"; do
    schema="$(echo "${schema}" | xargs)"
    [[ -z "${schema}" ]] && continue
    SCHEMA_ARGS+=("--schema=${schema}")
  done
fi

{
  echo "BACKUP_TIMESTAMP=${TIMESTAMP}"
  echo "BACKUP_MODE=${BACKUP_MODE}"
  echo "PGHOST=${PGHOST}"
  echo "PGPORT=${PGPORT}"
  echo "PGUSER=${PGUSER}"
  echo "DATABASES=${DATABASES_CSV}"
  echo "SCHEMAS=${SCHEMAS_CSV}"
  echo "REQUIRED_EXTENSIONS=${REQUIRED_EXTENSIONS}"
} > "${TARGET_DIR}/backup.env"

pg_dumpall \
  --host="${PGHOST}" \
  --port="${PGPORT}" \
  --username="${PGUSER}" \
  --globals-only \
  > "${TARGET_DIR}/globals.sql"

for db in "${DATABASES[@]}"; do
  db="$(echo "${db}" | xargs)"
  [[ -z "${db}" ]] && continue

  echo
  echo "Backing up database '${db}'"

  pg_dump \
    --host="${PGHOST}" \
    --port="${PGPORT}" \
    --username="${PGUSER}" \
    --format=custom \
    --no-owner \
    --no-privileges \
    "${SCHEMA_ARGS[@]}" \
    --file="${TARGET_DIR}/${db}.dump" \
    "${db}"

  pg_dump \
    --host="${PGHOST}" \
    --port="${PGPORT}" \
    --username="${PGUSER}" \
    --schema-only \
    --no-owner \
    --no-privileges \
    "${SCHEMA_ARGS[@]}" \
    --file="${TARGET_DIR}/${db}.schema.sql" \
    "${db}"
done

if [[ "${RETENTION_DAYS}" =~ ^[0-9]+$ ]] && [[ "${RETENTION_DAYS}" -gt 0 ]]; then
  echo
  echo "Applying retention policy: ${RETENTION_DAYS} days"
  find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime +"${RETENTION_DAYS}" -print -exec rm -rf {} +
fi

echo
echo "PostgreSQL logical backup completed successfully"
