#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="${REPO_ROOT}/backups/logs"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/postgres_backup_refresh_${TIMESTAMP}.log"

mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

BACKUP_MODE="${BACKUP_MODE:-daily}"

echo "Refreshing dedicated backup Postgres target"
echo "Timestamp: ${TIMESTAMP}"
echo "Mode: ${BACKUP_MODE}"

"${SCRIPT_DIR}/postgres_logical_backup.sh" "${BACKUP_MODE}"
"${REPO_ROOT}/scripts/restore/restore_postgres_backup.sh" latest

echo "Dedicated backup Postgres refresh completed"
