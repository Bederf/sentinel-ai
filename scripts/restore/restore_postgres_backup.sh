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
RESTORE_DOCKER_CONTAINER="${RESTORE_DOCKER_CONTAINER:-}"  # set to use docker exec for pg_restore (e.g. sentinel-postgres-backup-db)

if [[ -n "${RESTORE_DOCKER_CONTAINER}" && "${TARGET_PGUSER}" == "postgres" ]]; then
  container_pg_user="$(docker exec "${RESTORE_DOCKER_CONTAINER}" sh -lc 'printf "%s" "${POSTGRES_USER:-}"' 2>/dev/null || true)"
  if [[ -n "${container_pg_user}" ]]; then
    TARGET_PGUSER="${container_pg_user}"
  fi
fi

export PGPASSWORD="${TARGET_PGPASSWORD}"

# Determine which pg_restore to use (host binary vs Docker container)
if [[ -n "${RESTORE_DOCKER_CONTAINER}" ]]; then
  _container_pg() {
    local tool="$1"
    shift
    docker exec -i "${RESTORE_DOCKER_CONTAINER}" sh -lc \
      'PGPASSWORD="${POSTGRES_PASSWORD:-}" exec "$0" "$@"' \
      "${tool}" "$@"
  }

  _pg_restore() { _container_pg pg_restore "$@"; }
  _psql() { _container_pg psql "$@"; }
  _createdb() { _container_pg createdb "$@"; }
  _dropdb() { _container_pg dropdb "$@"; }
else
  for tool in psql pg_restore createdb dropdb; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
      echo "Required tool '${tool}' is not installed or not on PATH." >&2
      exit 1
    fi
  done
  _pg_restore() { pg_restore "$@"; }
  _psql() { psql "$@"; }
  _createdb() { createdb "$@"; }
  _dropdb() { dropdb "$@"; }
fi

echo "Restoring backup from: ${BACKUP_DIR}"
echo "Target Postgres: ${TARGET_PGHOST}:${TARGET_PGPORT}"
echo "Target database: ${TARGET_DATABASE}"

if [[ "${RESTORE_RESET_DB}" == "true" ]]; then
  if [[ -n "${RESTORE_DOCKER_CONTAINER}" ]]; then
    _dropdb -U "${TARGET_PGUSER}" "${TARGET_DATABASE}" 2>/dev/null || true
  else
    _dropdb \
      --if-exists \
      --host="${TARGET_PGHOST}" \
      --port="${TARGET_PGPORT}" \
      --username="${TARGET_PGUSER}" \
      "${TARGET_DATABASE}"
  fi
fi

if [[ -n "${RESTORE_DOCKER_CONTAINER}" ]]; then
  _createdb -U "${TARGET_PGUSER}" "${TARGET_DATABASE}" 2>/dev/null || true
else
  _createdb \
    --host="${TARGET_PGHOST}" \
    --port="${TARGET_PGPORT}" \
    --username="${TARGET_PGUSER}" \
    "${TARGET_DATABASE}" \
    2>/dev/null || true
fi

if [[ -f "${BACKUP_DIR}/globals.sql" ]]; then
  if [[ -n "${RESTORE_DOCKER_CONTAINER}" ]]; then
    # Pipe globals.sql into the container's psql
    cat "${BACKUP_DIR}/globals.sql" | _psql -U "${TARGET_PGUSER}" -d postgres >/dev/null 2>&1 || true
  else
    _psql \
      --host="${TARGET_PGHOST}" \
      --port="${TARGET_PGPORT}" \
      --username="${TARGET_PGUSER}" \
      --dbname=postgres \
      --file="${BACKUP_DIR}/globals.sql" \
      >/dev/null 2>&1 || true
  fi
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
  if [[ -n "${RESTORE_DOCKER_CONTAINER}" ]]; then
    # File-based restore: copy dump into container first
    container_tmp="/tmp/$(basename ${dump_file})"
    docker cp "${dump_file}" "${RESTORE_DOCKER_CONTAINER}:${container_tmp}"
    restore_args=(-U "${TARGET_PGUSER}" -d "${TARGET_DATABASE}" --no-owner --no-privileges)
    if [[ "${RESTORE_RESET_DB}" != "true" ]]; then
      restore_args+=(--clean --if-exists)
    fi
    _pg_restore "${restore_args[@]}" "${container_tmp}"
    docker exec "${RESTORE_DOCKER_CONTAINER}" rm -f "${container_tmp}"
  else
    restore_args=(
      --host="${TARGET_PGHOST}" \
      --port="${TARGET_PGPORT}" \
      --username="${TARGET_PGUSER}" \
      --dbname="${TARGET_DATABASE}" \
      --no-owner \
      --no-privileges
    )
    if [[ "${RESTORE_RESET_DB}" != "true" ]]; then
      restore_args+=(--clean --if-exists)
    fi
    _pg_restore "${restore_args[@]}" "${dump_file}"
  fi
done

if [[ "${RESTORE_VERIFY_EXTENSIONS}" == "true" && -n "${REQUIRED_EXTENSIONS:-}" ]]; then
  IFS=',' read -r -a REQUIRED <<< "${REQUIRED_EXTENSIONS}"
  for ext in "${REQUIRED[@]}"; do
    ext="$(echo "${ext}" | xargs)"
    [[ -z "${ext}" ]] && continue
    cmd="SELECT extname FROM pg_extension WHERE extname = '${ext}';"
    if [[ -n "${RESTORE_DOCKER_CONTAINER}" ]]; then
      echo "${cmd}" | _psql -U "${TARGET_PGUSER}" -d "${TARGET_DATABASE}" -t --no-align 2>/dev/null | grep -qx "${ext}" || {
        echo "Required extension missing after restore: ${ext}" >&2
        exit 1
      }
    else
      _psql \
        --host="${TARGET_PGHOST}" \
        --port="${TARGET_PGPORT}" \
        --username="${TARGET_PGUSER}" \
        --dbname="${TARGET_DATABASE}" \
        --tuples-only \
        --no-align \
        --command="${cmd}" \
        | grep -qx "${ext}" || {
          echo "Required extension missing after restore: ${ext}" >&2
          exit 1
        }
    fi
  done
fi

echo "Restore completed successfully"
