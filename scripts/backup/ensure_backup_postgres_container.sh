#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

BACKUP_CONTAINER_NAME="${BACKUP_CONTAINER_NAME:-sentinel-postgres-backup-db}"
BACKUP_CONTAINER_IMAGE="${BACKUP_CONTAINER_IMAGE:-public.ecr.aws/supabase/postgres:17.4.1.068}"
BACKUP_CONTAINER_PORT="${BACKUP_CONTAINER_PORT:-55432}"
BACKUP_CONTAINER_DATA_DIR="${BACKUP_CONTAINER_DATA_DIR:-${REPO_ROOT}/backups/postgres/standby-supabase-data}"

mkdir -p "${BACKUP_CONTAINER_DATA_DIR}"

if docker ps --format '{{.Names}}' | grep -qx "${BACKUP_CONTAINER_NAME}"; then
  echo "Backup Postgres container already running: ${BACKUP_CONTAINER_NAME}"
  exit 0
fi

if docker ps -a --format '{{.Names}}' | grep -qx "${BACKUP_CONTAINER_NAME}"; then
  echo "Starting existing backup Postgres container: ${BACKUP_CONTAINER_NAME}"
  docker start "${BACKUP_CONTAINER_NAME}" >/dev/null
  exit 0
fi

echo "Creating backup Postgres container: ${BACKUP_CONTAINER_NAME}"
docker run -d \
  --name "${BACKUP_CONTAINER_NAME}" \
  -p "${BACKUP_CONTAINER_PORT}:5432" \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_HOST=/var/run/postgresql \
  -e JWT_SECRET=super-secret-jwt-token-with-at-least-32-characters-long \
  -e JWT_EXP=3600 \
  -e PGDATA=/var/lib/postgresql/data \
  -e POSTGRES_USER=supabase_admin \
  -e POSTGRES_DB=postgres \
  -e POSTGRES_INITDB_ARGS='--allow-group-access --locale-provider=icu --encoding=UTF-8 --icu-locale=en_US.UTF-8' \
  -e LANG=en_US.UTF-8 \
  -e LANGUAGE=en_US:en \
  -e LC_ALL=en_US.UTF-8 \
  -e LOCALE_ARCHIVE=/usr/lib/locale/locale-archive \
  -v "${BACKUP_CONTAINER_DATA_DIR}:/var/lib/postgresql/data" \
  "${BACKUP_CONTAINER_IMAGE}" >/dev/null

echo "Waiting for backup Postgres container to accept connections..."
for _ in $(seq 1 30); do
  if PGPASSWORD=postgres psql "postgresql://postgres:postgres@127.0.0.1:${BACKUP_CONTAINER_PORT}/postgres" -tAc "select 1" >/dev/null 2>&1; then
    echo "Backup Postgres container is ready on 127.0.0.1:${BACKUP_CONTAINER_PORT}"
    exit 0
  fi
  sleep 1
done

echo "Backup Postgres container failed to become ready in time." >&2
exit 1
