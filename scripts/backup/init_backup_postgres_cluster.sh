#!/usr/bin/env bash
set -euo pipefail

PG_BIN_DIR="${PG_BIN_DIR:-/usr/lib/postgresql/15/bin}"
BACKUP_PGDATA="${BACKUP_PGDATA:-/opt/bms-intelligence/backups/postgres/standby-data}"
BACKUP_PGHOST="${BACKUP_PGHOST:-127.0.0.1}"
BACKUP_PGPORT="${BACKUP_PGPORT:-55432}"
BACKUP_PGUSER="${BACKUP_PGUSER:-postgres}"
BACKUP_PGPASSWORD="${BACKUP_PGPASSWORD:-postgres}"
BACKUP_DB_NAME="${BACKUP_DB_NAME:-sentinel_backup}"

mkdir -p "${BACKUP_PGDATA}"

if [[ -f "${BACKUP_PGDATA}/PG_VERSION" ]]; then
  echo "Backup Postgres cluster already initialized at ${BACKUP_PGDATA}"
  exit 0
fi

if [[ ! -x "${PG_BIN_DIR}/initdb" ]]; then
  echo "initdb not found at ${PG_BIN_DIR}/initdb" >&2
  exit 1
fi

TMP_PW="$(mktemp)"
trap 'rm -f "${TMP_PW}"' EXIT
printf '%s' "${BACKUP_PGPASSWORD}" > "${TMP_PW}"

"${PG_BIN_DIR}/initdb" \
  --username="${BACKUP_PGUSER}" \
  --pwfile="${TMP_PW}" \
  --auth-host=scram-sha-256 \
  --auth-local=trust \
  --encoding=UTF8 \
  --locale=C.UTF-8 \
  --pgdata="${BACKUP_PGDATA}"

cat >> "${BACKUP_PGDATA}/postgresql.conf" <<EOF
listen_addresses = '${BACKUP_PGHOST}'
port = ${BACKUP_PGPORT}
max_connections = 100
unix_socket_directories = '${BACKUP_PGDATA}'
logging_collector = on
log_directory = 'log'
log_filename = 'standby-postgres-%Y-%m-%d_%H%M%S.log'
EOF

cat > "${BACKUP_PGDATA}/pg_hba.conf" <<EOF
# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             all                                     trust
host    all             all             127.0.0.1/32            scram-sha-256
host    all             all             ::1/128                 scram-sha-256
EOF

echo "Initialized backup Postgres cluster at ${BACKUP_PGDATA}"
echo "Standalone backup DB will listen on ${BACKUP_PGHOST}:${BACKUP_PGPORT}"
echo "Target restore database name: ${BACKUP_DB_NAME}"
